"""Reviewable long-term memory candidates for ANVAYA Tutor 2.2.3."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Mapping

from personal_learning_assistant.repositories.sqlite.connection import transaction


class TutorMemoryCandidateError(RuntimeError):
    pass


_KIND_MAP = {
    "misconception": "misconception",
    "doubt": "recurring_doubt",
    "hint_requested": "scaffolding_need",
    "answer_incorrect": "practice_need",
    "answer_partial": "practice_need",
    "answer_unclear": "clarification_need",
    "answer_correct": "demonstrated_strength",
    "math_verified": "verified_calculation_strength",
    "math_repaired": "calculation_review_need",
    "math_blocked": "calculation_risk",
}


def _clean(value, limit=400):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def _candidate_id(signal):
    payload = "|".join(
        (
            _clean(signal.get("course_id"), 120),
            _clean(signal.get("topic_id"), 120),
            _clean(signal.get("kind"), 60),
            _clean(signal.get("text"), 300).casefold(),
            _clean(signal.get("first_observed_at"), 80),
            _clean(signal.get("last_observed_at"), 80),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return "tutor-memory-candidate-" + digest


def _memory_entry_id(candidate_id):
    digest = hashlib.sha256(
        ("accepted|" + str(candidate_id)).encode("utf-8")
    ).hexdigest()[:24]
    return "tutor-memory-" + digest


def _topic_name(connection, topic_id):
    if not topic_id:
        return ""
    row = connection.execute(
        "SELECT name FROM topics WHERE id=? AND deleted_at IS NULL",
        (str(topic_id),),
    ).fetchone()
    return "" if row is None else str(row[0])


def _candidate_text(signal, topic_name=""):
    kind = _clean(signal.get("kind"), 60).casefold()
    text = _clean(signal.get("text"), 300)
    topic = _clean(topic_name, 120) or "this topic"

    if kind == "misconception":
        return "Recurring misconception: {}".format(
            text or "A repeated conceptual misconception was observed."
        )
    if kind == "doubt":
        return "Recurring doubt: {}".format(
            text or "The same doubt recurred across Tutor sessions."
        )
    if kind == "hint_requested":
        return "Often needs hints while studying {}.".format(topic)
    if kind == "answer_incorrect":
        return "Repeated incorrect-answer signal observed in {}.".format(topic)
    if kind == "answer_partial":
        return "Repeated partial-answer signal observed in {}.".format(topic)
    if kind == "answer_unclear":
        return "Repeated unclear-answer signal observed in {}.".format(topic)
    if kind == "answer_correct":
        return "Repeated correct-answer signal observed in {}.".format(topic)
    if kind == "math_verified":
        return "Repeated verified calculations observed in {}.".format(topic)
    if kind == "math_repaired":
        return "Calculations repeatedly needed correction in {}.".format(topic)
    if kind == "math_blocked":
        return "Repeated calculation verification failures observed in {}.".format(
            topic
        )
    raise TutorMemoryCandidateError("unsupported stable Tutor signal")


def _confidence(signal):
    sessions = max(0, int(signal.get("session_count") or 0))
    events = max(0, int(signal.get("event_count") or 0))
    value = 1 + sessions + (1 if events >= 4 else 0)
    return max(1, min(5, value))


def _row_dict(row):
    if row is None:
        return None
    keys = tuple(row.keys()) if hasattr(row, "keys") else ()
    result = {key: row[key] for key in keys}
    try:
        provenance = json.loads(str(result.get("provenance_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        provenance = []
    result["provenance"] = tuple(
        str(item) for item in provenance if str(item).strip()
    )
    return result


def propose_memory_candidate(connection, signal, *, now):
    if not isinstance(connection, sqlite3.Connection):
        raise TypeError("connection must be an explicit sqlite3.Connection")
    if not isinstance(signal, Mapping):
        raise TutorMemoryCandidateError("stable signal is invalid")

    session_count = int(signal.get("session_count") or 0)
    evidence_count = int(signal.get("event_count") or 0)
    if session_count < 2 or evidence_count < 2:
        raise TutorMemoryCandidateError(
            "memory candidates require evidence from at least two sessions"
        )

    course_id = _clean(signal.get("course_id"), 120)
    topic_id = _clean(signal.get("topic_id"), 120) or None
    signal_kind = _clean(signal.get("kind"), 60).casefold()
    candidate_kind = _KIND_MAP.get(signal_kind)
    if not course_id or candidate_kind is None:
        raise TutorMemoryCandidateError("stable signal scope or kind is invalid")

    if connection.execute(
        "SELECT 1 FROM courses WHERE id=? AND deleted_at IS NULL",
        (course_id,),
    ).fetchone() is None:
        raise TutorMemoryCandidateError("candidate course does not exist")

    if topic_id and connection.execute(
        "SELECT 1 FROM topics "
        "WHERE id=? AND course_id=? AND deleted_at IS NULL",
        (topic_id, course_id),
    ).fetchone() is None:
        raise TutorMemoryCandidateError("candidate topic does not match course")

    first_seen = _clean(signal.get("first_observed_at"), 80)
    last_seen = _clean(signal.get("last_observed_at"), 80)
    if not first_seen or not last_seen:
        raise TutorMemoryCandidateError("stable signal timestamps are required")

    provenance = tuple(
        _clean(item, 180)
        for item in tuple(signal.get("provenance") or ())
        if _clean(item, 180)
    )
    if len(provenance) < 2:
        raise TutorMemoryCandidateError(
            "memory candidate provenance must include at least two observations"
        )

    candidate_text = _candidate_text(
        signal,
        topic_name=_topic_name(connection, topic_id),
    )
    candidate_id = _candidate_id(signal)

    existing = connection.execute(
        "SELECT * FROM tutor_memory_candidates WHERE id=?",
        (candidate_id,),
    ).fetchone()
    if existing is not None:
        return _row_dict(existing)

    with transaction(connection, immediate=True):
        prior = connection.execute(
            "SELECT id FROM tutor_memory_candidates "
            "WHERE course_id=? "
            "AND COALESCE(topic_id,'')=COALESCE(?, '') "
            "AND signal_kind=? AND candidate_text=? "
            "AND status='proposed' "
            "ORDER BY last_observed_at DESC,created_at DESC,id DESC LIMIT 1",
            (course_id, topic_id, signal_kind, candidate_text),
        ).fetchone()
        supersedes = None
        if prior is not None:
            supersedes = str(prior["id"])
            connection.execute(
                "UPDATE tutor_memory_candidates "
                "SET status='superseded',updated_at=?,reviewed_at=?,review_note=? "
                "WHERE id=? AND status='proposed'",
                (
                    str(now),
                    str(now),
                    "Superseded by a newer evidence window.",
                    supersedes,
                ),
            )

        connection.execute(
            "INSERT INTO tutor_memory_candidates("
            "id,course_id,topic_id,signal_kind,candidate_kind,candidate_text,"
            "confidence,evidence_count,session_count,first_observed_at,"
            "last_observed_at,provenance_json,status,supersedes_candidate_id,"
            "accepted_memory_entry_id,review_note,created_at,updated_at,reviewed_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'proposed',?,NULL,'',?,?,NULL)",
            (
                candidate_id,
                course_id,
                topic_id,
                signal_kind,
                candidate_kind,
                candidate_text,
                _confidence(signal),
                evidence_count,
                session_count,
                first_seen,
                last_seen,
                json.dumps(list(provenance), ensure_ascii=False),
                supersedes,
                str(now),
                str(now),
            ),
        )

    return _row_dict(
        connection.execute(
            "SELECT * FROM tutor_memory_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
    )


def list_memory_candidates(
    connection,
    *,
    course_id,
    topic_id=None,
    include_reviewed=True,
    limit=30,
):
    if not isinstance(connection, sqlite3.Connection):
        raise TypeError("connection must be an explicit sqlite3.Connection")
    clean_course = _clean(course_id, 120)
    clean_topic = _clean(topic_id, 120) or None
    if not clean_course:
        return ()

    params = [clean_course]
    where = ["course_id=?"]
    if clean_topic:
        where.append("topic_id=?")
        params.append(clean_topic)
    if not include_reviewed:
        where.append("status='proposed'")

    params.append(max(1, min(100, int(limit))))
    rows = connection.execute(
        "SELECT * FROM tutor_memory_candidates WHERE "
        + " AND ".join(where)
        + " ORDER BY CASE status WHEN 'proposed' THEN 0 ELSE 1 END,"
        "last_observed_at DESC,created_at DESC,id DESC LIMIT ?",
        tuple(params),
    ).fetchall()
    return tuple(_row_dict(row) for row in rows)


def review_memory_candidate(
    connection,
    candidate_id,
    *,
    action,
    now,
    review_note="",
):
    if not isinstance(connection, sqlite3.Connection):
        raise TypeError("connection must be an explicit sqlite3.Connection")
    clean_id = _clean(candidate_id, 160)
    clean_action = _clean(action, 40).casefold()
    if clean_action not in {"accept", "reject"}:
        raise TutorMemoryCandidateError("candidate review action is invalid")

    with transaction(connection, immediate=True):
        row = connection.execute(
            "SELECT * FROM tutor_memory_candidates WHERE id=?",
            (clean_id,),
        ).fetchone()
        if row is None:
            raise TutorMemoryCandidateError("memory candidate was not found")
        if str(row["status"]) != "proposed":
            raise TutorMemoryCandidateError(
                "memory candidate has already been reviewed"
            )

        accepted_memory_id = None
        if clean_action == "accept":
            accepted_memory_id = _memory_entry_id(clean_id)
            existing_memory = connection.execute(
                "SELECT id FROM learning_memory_entries "
                "WHERE source_entity_type='tutor_memory_candidate' "
                "AND source_entity_id=? AND archived_at IS NULL "
                "ORDER BY updated_at DESC,id DESC LIMIT 1",
                (clean_id,),
            ).fetchone()
            if existing_memory is not None:
                accepted_memory_id = str(existing_memory["id"])
            else:
                topic_id = (
                    None if row["topic_id"] is None else str(row["topic_id"])
                )
                connection.execute(
                    "INSERT INTO learning_memory_entries("
                    "id,scope_type,scope_id,kind,topic_id,raw_topic,memory_text,"
                    "source_entity_type,source_entity_id,created_at,updated_at,"
                    "archived_at"
                    ") VALUES (?,'course',?,?,?,?,?,'tutor_memory_candidate',"
                    "?,?,?,NULL)",
                    (
                        accepted_memory_id,
                        str(row["course_id"]),
                        str(row["candidate_kind"]),
                        topic_id,
                        _topic_name(connection, topic_id),
                        str(row["candidate_text"]),
                        clean_id,
                        str(now),
                        str(now),
                    ),
                )

            connection.execute(
                "UPDATE tutor_memory_candidates "
                "SET status='accepted',accepted_memory_entry_id=?,review_note=?,"
                "updated_at=?,reviewed_at=? WHERE id=?",
                (
                    accepted_memory_id,
                    _clean(review_note, 500),
                    str(now),
                    str(now),
                    clean_id,
                ),
            )
        else:
            connection.execute(
                "UPDATE tutor_memory_candidates "
                "SET status='rejected',review_note=?,updated_at=?,reviewed_at=? "
                "WHERE id=?",
                (
                    _clean(review_note, 500),
                    str(now),
                    str(now),
                    clean_id,
                ),
            )

    return _row_dict(
        connection.execute(
            "SELECT * FROM tutor_memory_candidates WHERE id=?",
            (clean_id,),
        ).fetchone()
    )
