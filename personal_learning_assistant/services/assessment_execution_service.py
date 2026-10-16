"""Source-only AP/PS candidate: persisted active clock and typed self-assessment.

Only the standalone synthetic fixture mounts this service. Production activation,
migration allocation and B writer provenance are intentionally unavailable.
"""

from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import re
from personal_learning_assistant.domain.assessment_self_evaluation import (
    parse_rubric,
    mark_rubric,
)
from personal_learning_assistant.repositories.sqlite.assessment_execution_repository import (
    AssessmentExecutionRepository,
)
from personal_learning_assistant.services.assessment_runner_service import (
    AssessmentRunnerService,
    AssessmentRunnerValidationError,
)


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(
        timespec="milliseconds"
    )


def timestamp(value):
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("An aware server clock is required.")
    delta = value.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


def integer(value):
    if type(value) is not int or value < 1:
        raise ValueError("Invalid revision.")
    return value


def bounded(value, limit=2000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid text field.")
    return value


class AssessmentExecutionService:
    def __init__(self, path, *, now_fn=None, production=False):
        self.repository = AssessmentExecutionRepository(path, production=production)
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def _load(self, db, sid):
        row = db.execute(
            "SELECT * FROM assessment_candidate_execution WHERE session_id=?", (sid,)
        ).fetchone()
        header = db.execute(
            "SELECT * FROM assessment_test_sessions WHERE id=?", (sid,)
        ).fetchone()
        if row is None or header is None:
            raise LookupError("Attempt not found.")
        meta = json.loads(row["metadata_json"])
        meta["revision"] = row["revision"]
        questions = [
            dict(q)
            for q in db.execute(
                "SELECT q.*,r.response_json,r.revision AS response_revision,r.state AS response_state FROM assessment_test_session_questions q JOIN assessment_test_responses r ON r.session_question_id=q.id WHERE q.session_id=? ORDER BY q.ordinal",
                (sid,),
            )
        ]
        if (
            digest(
                [
                    {
                        k: q[k]
                        for k in (
                            "id",
                            "question_id",
                            "question_type",
                            "question_text",
                            "max_marks_milli",
                            "options_json",
                            "answer_key_json",
                            "solution_text",
                            "rubric_text",
                        )
                    }
                    for q in questions
                ]
            )
            != meta["snapshot_sha256"]
        ):
            raise ValueError("Immutable source identity mismatch.")
        return dict(header), meta, questions

    @staticmethod
    def _clock(h, m, now):
        current = max(now, m["last_ms"])
        anomaly = now < m["last_ms"]
        used = m["consumed_ms"]
        if h["status"] == "active" and m["paused_ms"] is None:
            used += max(0, current - m["segment_ms"])
        used = min(m["duration_ms"], used)
        status = h["status"]
        if status == "active":
            status = (
                "paused"
                if m["paused_ms"] is not None
                else ("expired" if used >= m["duration_ms"] else "active")
            )
        return status, used, current, anomaly

    @staticmethod
    def _authored_rubric_id(meta, question):
        """Frozen package question identity, never derived from a display label."""
        return meta.get("authored_question_ids", {}).get(
            question["id"], question["question_id"]
        )

    def adopt(self, sid, *, kind="online_timed", reviewed_fixture=False,
              self_review_acknowledged=False):
        """Explicit adoption in the disposable store; cannot grant production approval."""
        if kind not in {"online_timed", "paper_subjective"}:
            raise ValueError("Invalid attempt kind.")
        with self.repository.open(write=True) as db:
            now = timestamp(self.now_fn())
            if db.execute(
                "SELECT 1 FROM assessment_candidate_execution WHERE session_id=?",
                (sid,),
            ).fetchone():
                raise ValueError("Attempt already adopted.")
            h = db.execute(
                "SELECT * FROM assessment_test_sessions WHERE id=?", (sid,)
            ).fetchone()
            if h is None or h["status"] != "active":
                raise ValueError("Only active attempts can be adopted.")
            questions = [
                dict(q)
                for q in db.execute(
                    "SELECT * FROM assessment_test_session_questions WHERE session_id=? ORDER BY ordinal",
                    (sid,),
                )
            ]
            if not questions:
                raise ValueError("Empty assessment.")
            authored_question_ids = {}
            if self.repository.production and h["mode"] != "practice":
                raise ValueError("Local extended attempts are practice only.")
            if kind == "paper_subjective":
                if (
                    h["mode"] != "practice"
                    or (not self.repository.production and reviewed_fixture is not True)
                    or (self.repository.production and self_review_acknowledged is not True)
                    or any(
                        q["question_type"]
                        not in {"short_subjective", "long_subjective"}
                        or not q["solution_text"].strip()
                        for q in questions
                    )
                ):
                    raise ValueError("Reviewed all-subjective practice is required.")
                if self.repository.production:
                    from personal_learning_assistant.services.assessment_paper_admission import inspect_paper_import
                    admission = inspect_paper_import(
                        db, h["assessment_id"], _trusted_write_transaction=True
                    )
                    if admission["structural_status"] != "PASS":
                        raise ValueError("Approved package and exact paper rubric lineage required.")
                for q in questions:
                    identity = db.execute(
                        "SELECT package_question_id FROM assessment_question_specs "
                        "WHERE question_id=?", (q["question_id"],)
                    ).fetchone()
                    if identity is None or not identity[0]:
                        raise ValueError("Reviewed package question identity unavailable.")
                    # The author knows the stable package ID; canonical SQLite
                    # IDs are allocated only when the package is approved.
                    authored_question_ids[q["id"]] = identity[0]
                    parse_rubric(
                        q["rubric_text"], identity[0], q["max_marks_milli"]
                    )
            started = timestamp(
                datetime.fromisoformat(h["started_at"].replace("Z", "+00:00"))
            )
            duration = h["duration_seconds"] * 1000
            if now >= started + duration:
                raise ValueError("Attempt already expired.")
            snapshot = [
                {
                    k: q[k]
                    for k in (
                        "id",
                        "question_id",
                        "question_type",
                        "question_text",
                        "max_marks_milli",
                        "options_json",
                        "answer_key_json",
                        "solution_text",
                        "rubric_text",
                    )
                }
                for q in questions
            ]
            meta = dict(
                kind=kind,
                mode=h["mode"],
                duration_ms=duration,
                consumed_ms=max(0, now - started),
                segment_ms=now,
                paused_ms=None,
                last_ms=now,
                pause_allowed=h["mode"] == "practice",
                clock_anomaly=False,
                snapshot_sha256=digest(snapshot),
                authored_question_ids=authored_question_ids,
                paper={},
                package_identity=dict(
                    authority=("user_private_self_check" if self.repository.production else "synthetic_review_only"),
                    production_authority="BLOCKED",
                    snapshot_sha256=digest(snapshot),
                ),
            )
            db.execute(
                "INSERT INTO assessment_candidate_execution VALUES (?,1,?)",
                (sid, encoded(meta)),
            )
            db.execute(
                "INSERT INTO assessment_test_events VALUES (?,?,NULL,'execution_adopted',?,?)",
                (
                    digest([sid, now]),
                    sid,
                    encoded({"kind": kind, "consumed_ms": meta["consumed_ms"]}),
                    iso(now),
                ),
            )
        return self.state(sid)

    def _project(self, db, h, m, questions, now):
        status, used, current, anomaly = self._clock(h, m, now)
        projected = []
        for q in questions:
            p = m["paper"].get(q["id"], {})
            projected.append(
                dict(
                    session_question_id=q["id"],
                    question_id=q["question_id"],
                    ordinal=q["ordinal"],
                    question_type=q["question_type"],
                    question_text=q["question_text"],
                    max_marks_milli=q["max_marks_milli"],
                    options=json.loads(q["options_json"]),
                    response=json.loads(q["response_json"]),
                    response_revision=q["response_revision"],
                    marked="marked_for_review" in q["response_state"],
                    attempted=p.get("attempted", False),
                    revealed_at=p.get("revealed_at"),
                )
            )
        review = db.execute(
            "SELECT snapshot_json FROM assessment_candidate_self_reviews WHERE session_id=? ORDER BY revision DESC LIMIT 1",
            (h["id"],),
        ).fetchone()
        return dict(
            session_id=h["id"],
            title=h["title_snapshot"],
            instructions=h["instructions_snapshot"],
            kind=m["kind"],
            mode=m["mode"],
            status=status,
            revision=m["revision"],
            terminal_persisted=h["status"] != "active",
            current_ordinal=h["current_ordinal"],
            remaining_ms=max(0, m["duration_ms"] - used),
            consumed_ms=used,
            server_now=iso(current),
            clock_anomaly=anomaly or m["clock_anomaly"],
            pause_allowed=m["pause_allowed"],
            questions=projected,
            review=json.loads(review[0]) if review else None,
            package_identity=m["package_identity"],
        )

    def state(self, sid):
        now = timestamp(self.now_fn())
        with self.repository.open() as db:
            h, m, questions = self._load(db, sid)
            return self._project(db, h, m, questions, now)

    def _review(self, db, sid):
        row = db.execute(
            "SELECT snapshot_json FROM assessment_candidate_self_reviews WHERE session_id=? ORDER BY revision DESC LIMIT 1",
            (sid,),
        ).fetchone()
        if row is None:
            raise ValueError("Finish solving before self-check.")
        return json.loads(row[0])

    @staticmethod
    def _write_review(db, sid, review, new=False):
        if new:
            db.execute(
                "INSERT INTO assessment_candidate_self_reviews VALUES (?,?,?,'self_assessed',?)",
                (sid, review["revision"], review["status"], encoded(review)),
            )
        else:
            db.execute(
                "UPDATE assessment_candidate_self_reviews SET status=?,snapshot_json=? WHERE session_id=? AND revision=?",
                (review["status"], encoded(review), sid, review["revision"]),
            )

    def command(self, sid, command, payload):
        allowed = {
            "pause": {
                "question_id",
                "expected_response_revision",
                "response",
                "marked",
            },
            "resume": set(),
            "save": {"question_id", "expected_response_revision", "response", "marked"},
            "navigate": {
                "ordinal",
                "question_id",
                "expected_response_revision",
                "response",
                "marked",
            },
            "heartbeat": set(),
            "submit": set(),
            "finish_solving": set(),
            "attempt": {"question_id", "attempted"},
            "reveal": {"question_id"},
            "self_save": {
                "question_id",
                "marks",
                "steps",
                "unattempted",
                "reason",
                "reflection",
                "step_reasons",
            },
            "self_submit": {"confirmed"},
            "amend": {"reason"},
        }
        if (
            command not in allowed
            or not isinstance(payload, dict)
            or set(payload) - allowed[command] - {"request_id", "expected_revision"}
        ):
            raise ValueError("Invalid command fields.")
        rid = payload.get("request_id")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", rid):
            raise ValueError("Invalid request identity.")
        expected = integer(payload.get("expected_revision"))
        request_hash = digest([command, payload])
        with self.repository.open(write=True) as db:
            now = timestamp(self.now_fn())
            h, m, questions = self._load(db, sid)
            receipt = db.execute(
                "SELECT * FROM assessment_candidate_receipts WHERE session_id=? AND request_id=?",
                (sid, rid),
            ).fetchone()
            if receipt:
                if receipt["payload_sha256"] != request_hash:
                    raise ValueError("Conflict: request identity reused.")
                # Original receipt is audit-only. Always repaint from current state.
                return dict(
                    replayed=True,
                    receipt={
                        k: receipt[k]
                        for k in (
                            "command",
                            "prior_revision",
                            "result_revision",
                            "occurred_at",
                        )
                    },
                    state=self._project(db, h, m, questions, now),
                )
            if expected != m["revision"]:
                raise ValueError(
                    "Conflict: stale attempt revision. Reload before retrying."
                )
            status, used, now, anomaly = self._clock(h, m, now)
            m["clock_anomaly"] = m["clock_anomaly"] or anomaly
            result = {}
            q = None
            qid = payload.get("question_id")
            if qid is not None:
                q = next((q for q in questions if q["id"] == qid), None)
                if q is None:
                    raise LookupError("Question does not belong to this attempt.")
            review_commands = {"self_save", "self_submit", "amend", "reveal"}
            if status == "expired" and h["status"] == "active":
                self._terminal(db, h, m, now, used, "expired")
                result["error"] = "expired"
                if m["kind"] == "paper_subjective":
                    self._new_review(db, sid, m, now)
            else:
                if h["status"] != "active" and command not in review_commands:
                    raise ValueError("Conflict: attempt has ended.")
                if status == "paused" and command not in {
                    "resume",
                    "submit",
                    "finish_solving",
                }:
                    raise ValueError("Conflict: attempt paused; resume explicitly.")
                if (
                    command
                    in {
                        "self_save",
                        "self_submit",
                        "amend",
                        "reveal",
                        "attempt",
                        "finish_solving",
                    }
                    and m["kind"] != "paper_subjective"
                ):
                    raise ValueError("Paper practice only.")
                if command in {"save", "navigate"} or (
                    command == "pause" and "response" in payload
                ):
                    if m["kind"] != "online_timed" or q is None:
                        raise ValueError("Online question required.")
                    if q["ordinal"] != h["current_ordinal"]:
                        raise ValueError("Conflict: question is no longer current.")
                    if (
                        integer(payload.get("expected_response_revision"))
                        != q["response_revision"]
                    ):
                        raise ValueError("Conflict: stale response revision.")
                    response = payload.get("response")
                    if not isinstance(response, dict):
                        raise ValueError("Response must be an object.")
                    qtype = q["question_type"]
                    keys = (
                        {"selected_option_ids"}
                        if qtype in {"mcq", "msq"}
                        else (
                            {"value", "parts"}
                            if qtype == "fill_blank"
                            else (
                                {"value"}
                                if qtype in {"numerical", "true_false"}
                                else {"text"}
                            )
                        )
                    )
                    if set(response) - keys:
                        raise ValueError("Invalid response fields.")
                    if qtype in {"mcq", "msq"}:
                        options = response.get("selected_option_ids", [])
                        if (
                            not isinstance(options, list)
                            or len(options) > 100
                            or any(not isinstance(v, str) for v in options)
                        ):
                            raise ValueError("Invalid option response.")
                    elif any(
                        not isinstance(v, str)
                        for k, v in response.items()
                        if k != "parts"
                    ):
                        raise ValueError("Invalid text response.")
                    if "parts" in response and (
                        not isinstance(response["parts"], list)
                        or any(not isinstance(v, str) for v in response["parts"])
                    ):
                        raise ValueError("Invalid fill response.")
                    try:
                        normalized, answered = (
                            AssessmentRunnerService._normalize_response(q, response)
                        )
                    except AssessmentRunnerValidationError as error:
                        raise ValueError(str(error)) from error
                    marked = payload.get(
                        "marked", "marked_for_review" in q["response_state"]
                    )
                    if type(marked) is not bool:
                        raise ValueError("Invalid review flag.")
                    state = (
                        "answered_marked_for_review"
                        if marked and answered
                        else (
                            "marked_for_review"
                            if marked
                            else "answered" if answered else "not_answered"
                        )
                    )
                    db.execute(
                        "UPDATE assessment_test_responses SET response_json=?,state=?,saved_at=?,updated_at=?,revision=revision+1 WHERE session_question_id=?",
                        (encoded(normalized), state, iso(now), iso(now), qid),
                    )
                if command == "pause":
                    if status != "active" or not m["pause_allowed"]:
                        raise ValueError(
                            "Pause is not permitted by this attempt policy."
                        )
                    m.update(consumed_ms=used, segment_ms=None, paused_ms=now)
                elif command == "resume":
                    if status != "paused":
                        raise ValueError("Conflict: attempt is not paused.")
                    m.update(segment_ms=now, paused_ms=None)
                elif command == "navigate":
                    ordinal = payload.get("ordinal")
                    if type(ordinal) is not int or not 1 <= ordinal <= len(questions):
                        raise ValueError("Invalid question number.")
                    db.execute(
                        "UPDATE assessment_test_sessions SET current_ordinal=? WHERE id=?",
                        (ordinal, sid),
                    )
                elif command in {"submit", "finish_solving"}:
                    if m["kind"] == "paper_subjective" and command == "submit":
                        raise ValueError("Use Finish solving for paper practice.")
                    self._terminal(db, h, m, now, used, "submitted")
                    if m["kind"] == "paper_subjective":
                        self._new_review(db, sid, m, now)
                elif command == "attempt":
                    if q is None or type(payload.get("attempted")) is not bool:
                        raise ValueError("Explicit attempted acknowledgement required.")
                    m["paper"].setdefault(qid, {})["attempted"] = payload["attempted"]
                elif command == "reveal":
                    if q is None or (
                        h["status"] == "active"
                        and not m["paper"].get(qid, {}).get("attempted")
                    ):
                        raise ValueError(
                            "Acknowledge attempted on paper before revealing."
                        )
                    p = m["paper"].setdefault(qid, {})
                    p.setdefault("revealed_at", iso(now))
                    p["rubric_sha256"] = digest(q["rubric_text"])
                    result["guide"] = dict(
                        solution=q["solution_text"],
                        rubric=parse_rubric(
                            q["rubric_text"], self._authored_rubric_id(m, q), q["max_marks_milli"]
                        ),
                        rubric_sha256=p["rubric_sha256"],
                        reviewer_status=("student_self_review_unverified" if self.repository.production else "synthetic_review_only"),
                    )
                elif command == "self_save":
                    if h["status"] == "active":
                        raise ValueError("Finish solving first.")
                    review = self._review(db, sid)
                    if review["status"] != "draft" or q is None:
                        raise ValueError("Amend a submitted review before editing.")
                    unattempted = payload.get("unattempted", False)
                    if type(unattempted) is not bool:
                        raise ValueError("Invalid unattempted flag.")
                    step_reasons = payload.get("step_reasons", {})
                    if not isinstance(step_reasons, dict):
                        raise ValueError("Invalid criterion reasons.")
                    rubric = parse_rubric(
                        q["rubric_text"], self._authored_rubric_id(m, q), q["max_marks_milli"]
                    )
                    step_ids = {step["id"] for step in rubric.get("steps", [])}
                    if set(step_reasons) - step_ids:
                        raise ValueError("Unknown rubric criterion.")
                    step_reasons = {
                        key: bounded(value) for key, value in step_reasons.items()
                    }
                    if unattempted:
                        if "marks" in payload or "steps" in payload:
                            raise ValueError("Unattempted cannot contain awards.")
                        score = 0
                        awards = None
                    else:
                        if not m["paper"].get(qid, {}).get("revealed_at"):
                            raise ValueError(
                                "Reveal the reviewed guide before marking."
                            )
                        rubric = parse_rubric(
                            q["rubric_text"], self._authored_rubric_id(m, q), q["max_marks_milli"]
                        )
                        awards = {
                            k: payload[k] for k in ("marks", "steps") if k in payload
                        }
                        score = mark_rubric(rubric, awards)
                    review["items"][qid] = dict(
                        awarded_marks_milli=score,
                        unattempted=unattempted,
                        awards=awards,
                        marking_mode=rubric["kind"],
                        step_reasons=step_reasons,
                        reason=bounded(payload.get("reason", "")),
                        reflection=bounded(payload.get("reflection", "")),
                        rubric_sha256=digest(q["rubric_text"]),
                        revealed_at=m["paper"].get(qid, {}).get("revealed_at"),
                    )
                    self._write_review(db, sid, review)
                elif command == "self_submit":
                    review = self._review(db, sid)
                    if (
                        review["status"] != "draft"
                        or payload.get("confirmed") is not True
                    ):
                        raise ValueError("Confirm these are your self-entered marks.")
                    if set(review["items"]) != {q["id"] for q in questions}:
                        raise ValueError(
                            "Every question needs a mark or explicit unattempted acknowledgement."
                        )
                    review.update(status="submitted", submitted_at=iso(now))
                    self._write_review(db, sid, review)
                elif command == "amend":
                    review = self._review(db, sid)
                    reason = bounded(payload.get("reason", ""))
                    if review["status"] != "submitted" or not reason.strip():
                        raise ValueError(
                            "A submitted review and correction reason are required."
                        )
                    previous = review["revision"]
                    review.update(
                        revision=previous + 1,
                        supersedes=previous,
                        status="draft",
                        correction_reason=reason,
                        submitted_at=None,
                        created_at=iso(now),
                    )
                    self._write_review(db, sid, review, new=True)
            m["last_ms"] = now
            prior = m.pop("revision")
            m["revision"] = prior + 1
            db.execute(
                "UPDATE assessment_candidate_execution SET revision=?,metadata_json=? WHERE session_id=?",
                (m["revision"], encoded(m), sid),
            )
            if h["status"] == "active" and m["paused_ms"] is None:
                _, consumed, _, _ = self._clock(h, m, now)
                db.execute(
                    "UPDATE assessment_test_sessions SET expires_at=? WHERE id=?",
                    (iso(now + m["duration_ms"] - consumed), sid),
                )
            db.execute(
                "INSERT INTO assessment_test_events VALUES (?,?,NULL,?,?,?)",
                (
                    digest([sid, rid]),
                    sid,
                    "candidate_" + command,
                    encoded({"revision": m["revision"], "question_id": qid}),
                    iso(now),
                ),
            )
            db.execute(
                "INSERT INTO assessment_candidate_receipts VALUES (?,?,?,?,?,?,?,?)",
                (
                    sid,
                    rid,
                    command,
                    request_hash,
                    prior,
                    m["revision"],
                    iso(now),
                    encoded({k: v for k, v in result.items() if k != "guide"}),
                ),
            )
            h, m, questions = self._load(db, sid)
            return dict(
                replayed=False, state=self._project(db, h, m, questions, now), **result
            )

    @staticmethod
    def _terminal(db, h, m, now, used, status):
        m.update(consumed_ms=used, segment_ms=None, paused_ms=None)
        db.execute(
            "UPDATE assessment_test_sessions SET status=?,submitted_at=?,submission_reason=?,revision=revision+1 WHERE id=?",
            (status, iso(now), "timeout" if status == "expired" else "user", h["id"]),
        )
        h["status"] = status

    def _new_review(self, db, sid, m, now):
        review = dict(
            revision=1,
            status="draft",
            provenance="self_assessed",
            items={},
            supersedes=None,
            correction_reason="",
            created_at=iso(now),
            submitted_at=None,
            package_identity=m["package_identity"],
        )
        self._write_review(db, sid, review, new=True)

    def review_history(self, sid):
        with self.repository.open() as db:
            self._load(db, sid)
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT snapshot_json FROM assessment_candidate_self_reviews WHERE session_id=? ORDER BY revision",
                    (sid,),
                )
            ]

    def review_summary(self, sid):
        state = self.state(sid)
        review = state["review"]
        items = review["items"] if review else {}
        maximum = sum(q["max_marks_milli"] for q in state["questions"])
        missing = len(state["questions"]) - len(items)
        total = sum(i["awarded_marks_milli"] for i in items.values())
        return dict(
            provenance="self_assessed",
            independence="assisted_or_unknown",
            eligible_for_recovery=False,
            exclusion_reason="self_reported_outcome",
            session_id=sid,
            revision=review["revision"] if review else None,
            status=review["status"] if review else "not_started",
            total_marks_milli=total,
            maximum_marks_milli=maximum,
            missing=missing,
            percentage=(
                round(total * 100 / maximum, 2) if maximum and not missing else None
            ),
            package_identity=state["package_identity"],
            questions=[
                dict(
                    **q,
                    mapping="unmapped",
                    self_mark=items.get(q["session_question_id"]),
                )
                for q in state["questions"]
            ],
        )

    def authorized_guides(self, sid):
        """Query-only: only guides already deliberately revealed in this attempt."""
        with self.repository.open() as db:
            h, m, questions = self._load(db, sid)
            status, _, _, _ = self._clock(h, m, timestamp(self.now_fn()))
            if m["kind"] != "paper_subjective" or status == "paused":
                return {}
            return {
                q["id"]: dict(
                    solution=q["solution_text"],
                    rubric=parse_rubric(
                        q["rubric_text"], self._authored_rubric_id(m, q), q["max_marks_milli"]
                    ),
                    rubric_sha256=digest(q["rubric_text"]),
                    reviewer_status=("student_self_review_unverified" if self.repository.production else "synthetic_review_only"),
                )
                for q in questions
                if m["paper"].get(q["id"], {}).get("revealed_at")
            }
