import json
import sqlite3
from datetime import timedelta
import pytest
from test_assessment_studio_phase_c import _database, Clock, _service


def candidate(tmp_path, paper=False, mode="practice"):
    from personal_learning_assistant.services.assessment_execution_service import (
        AssessmentExecutionService,
    )

    path = _database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE assessment_runtime_specs SET mode=?", (mode,))
        if paper:
            db.execute(
                "UPDATE assessment_question_specs SET question_type='long_subjective',rubric_text='Reviewed method marks; use any valid derivation.',solution_text='Reviewed worked solution'"
            )
    clock = Clock()
    sid = _service(path, clock).start("assessment-1", confirmed=True)["session_id"]
    with sqlite3.connect(path) as db:
        from pathlib import Path

        db.executescript(
            (
                Path(__file__).resolve().parents[1]
                / "scripts/fixtures/assessment_execution_candidate.sql"
            ).read_text()
        )
    service = AssessmentExecutionService(path, now_fn=clock)
    service.adopt(
        sid,
        kind="paper_subjective" if paper else "online_timed",
        reviewed_fixture=paper,
    )
    return service, sid, path, clock


def command(service, sid, kind, **data):
    import uuid

    return service.command(
        sid,
        kind,
        dict(
            request_id=str(uuid.uuid4()),
            expected_revision=service.state(sid)["revision"],
            **data,
        ),
    )


def question(service, sid):
    return service.state(sid)["questions"][0]


def test_pause_freezes_active_time_after_restart(tmp_path):
    s, sid, path, clock = candidate(tmp_path)
    clock.advance(12)
    q = question(s, sid)
    command(
        s,
        sid,
        "pause",
        question_id=q["session_question_id"],
        expected_response_revision=q["response_revision"],
        response={"selected_option_ids": ["B"]},
        marked=True,
    )
    state = s.state(sid)
    assert state["status"] == "paused" and state["remaining_ms"] == 48000
    clock.advance(36000)
    from personal_learning_assistant.services.assessment_execution_service import (
        AssessmentExecutionService,
    )

    restarted = AssessmentExecutionService(path, now_fn=clock)
    assert restarted.state(sid)["remaining_ms"] == 48000
    command(restarted, sid, "resume")
    assert restarted.state(sid)["remaining_ms"] == 48000
    q = question(restarted, sid)
    assert q["response"] == {"selected_option_ids": ["B"]} and q["marked"]


def test_pause_at_exact_deadline_expires(tmp_path):
    s, sid, _, clock = candidate(tmp_path)
    clock.advance(60)
    result = command(s, sid, "pause")
    assert result["state"]["status"] == "expired" and result["error"] == "expired"


def test_exam_pause_disabled_even_with_forged_payload(tmp_path):
    s, sid, _, _ = candidate(tmp_path, mode="exam")
    for payload in ({}, {"pause_allowed": True}, {"mode": "practice"}):
        with pytest.raises(ValueError):
            command(s, sid, "pause", **payload)
    assert s.state(sid)["status"] == "active"


def test_receipt_replay_cannot_restore_old_active_header(tmp_path):
    s, sid, _, _ = candidate(tmp_path)
    payload = dict(request_id="request-resume-001", expected_revision=2)
    command(s, sid, "pause")
    s.command(sid, "resume", payload)
    command(s, sid, "pause")
    result = s.command(sid, "resume", payload)
    assert result["replayed"] and result["state"]["status"] == "paused"
    with pytest.raises(ValueError):
        s.command(sid, "pause", payload)


def test_multiple_devices_conflict_and_stale_autosave_after_resume(tmp_path):
    s, sid, _, _ = candidate(tmp_path)
    q = question(s, sid)
    payload = dict(
        request_id="request-old-save",
        expected_revision=1,
        question_id=q["session_question_id"],
        expected_response_revision=1,
        response={"selected_option_ids": ["A"]},
    )
    command(s, sid, "pause")
    command(s, sid, "resume")
    with pytest.raises(ValueError):
        s.command(sid, "save", payload)
    assert question(s, sid)["response"] == {}


def test_get_paused_state_has_no_logical_write(tmp_path):
    s, sid, path, clock = candidate(tmp_path)
    command(s, sid, "pause")
    with sqlite3.connect(path) as db:
        before = list(db.iterdump())
    clock.advance(10000)
    s.state(sid)
    s.state(sid)
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before


def test_clock_rollback_clamps_and_naive_rejected(tmp_path):
    s, sid, _, clock = candidate(tmp_path)
    clock.advance(10)
    command(s, sid, "heartbeat")
    clock.advance(-20)
    result = command(s, sid, "pause")["state"]
    assert result["remaining_ms"] == 50000 and result["clock_anomaly"]
    clock.value = clock.value.replace(tzinfo=None)
    with pytest.raises(ValueError):
        s.state(sid)


def test_final_pause_payload_saves_atomically(tmp_path):
    s, sid, path, clock = candidate(tmp_path)
    q = question(s, sid)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER fail_receipt BEFORE INSERT ON assessment_candidate_receipts BEGIN SELECT RAISE(ABORT,'fixture failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        command(
            s,
            sid,
            "pause",
            question_id=q["session_question_id"],
            expected_response_revision=1,
            response={"selected_option_ids": ["B"]},
        )
    assert s.state(sid)["status"] == "active" and question(s, sid)["response"] == {}


def test_paused_submit_idempotent(tmp_path):
    s, sid, _, clock = candidate(tmp_path)
    command(s, sid, "pause")
    clock.advance(900)
    payload = dict(
        request_id="request-submit-001", expected_revision=s.state(sid)["revision"]
    )
    first = s.command(sid, "submit", payload)
    second = s.command(sid, "submit", payload)
    assert first["state"]["status"] == "submitted" and second["replayed"]


def test_paper_admission_and_reveal_policy(tmp_path):
    s, sid, _, _ = candidate(tmp_path)
    with pytest.raises(ValueError):
        command(s, sid, "reveal", question_id=question(s, sid)["session_question_id"])


def test_incomplete_draft_reload_not_zero(tmp_path):
    s, sid, _, _ = candidate(tmp_path, paper=True)
    command(s, sid, "finish_solving")
    state = s.state(sid)
    assert state["review"]["items"] == {}
    with pytest.raises(ValueError):
        command(s, sid, "self_submit", confirmed=True)
    assert s.state(sid)["review"]["status"] == "draft"


def test_self_submit_amend_preserves_previous_revision(tmp_path):
    s, sid, path, _ = candidate(tmp_path, paper=True)
    command(s, sid, "finish_solving")
    for q in s.state(sid)["questions"]:
        command(s, sid, "reveal", question_id=q["session_question_id"])
        command(
            s,
            sid,
            "self_save",
            question_id=q["session_question_id"],
            marks="0.5",
            reason="Calculation error",
        )
    command(s, sid, "self_submit", confirmed=True)
    original = s.state(sid)["review"]
    assert original["status"] == "submitted"
    command(s, sid, "amend", reason="Checked working again")
    q = question(s, sid)
    command(s, sid, "self_save", question_id=q["session_question_id"], marks="1")
    assert s.state(sid)["review"]["supersedes"] == original["revision"]
    assert s.review_history(sid)[0] == original
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM question_attempts").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM assessment_session_evaluations"
            ).fetchone()[0]
            == 0
        )
    summary = s.review_summary(sid)
    assert (
        summary["provenance"] == "self_assessed"
        and summary["independence"] == "assisted_or_unknown"
    )
    assert summary["eligible_for_recovery"] is False and all(
        q["mapping"] == "unmapped" for q in summary["questions"]
    )


def test_rubric_revision_does_not_rebind_attempt(tmp_path):
    s, sid, path, _ = candidate(tmp_path, paper=True)
    command(s, sid, "finish_solving")
    q = question(s, sid)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE assessment_question_specs SET rubric_text='Later rubric'")
    result = command(s, sid, "reveal", question_id=q["session_question_id"])
    assert result["guide"]["rubric"]["text"].startswith("Reviewed method")
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE assessment_test_session_questions SET rubric_text='Tampered' WHERE id=?",
            (q["session_question_id"],),
        )
    with pytest.raises(ValueError):
        command(s, sid, "reveal", question_id=q["session_question_id"])


def test_reveal_requires_acknowledged_attempt_and_denies_paused(tmp_path):
    s, sid, _, _ = candidate(tmp_path, paper=True)
    q = question(s, sid)
    with pytest.raises(ValueError):
        command(s, sid, "reveal", question_id=q["session_question_id"])
    command(s, sid, "attempt", question_id=q["session_question_id"], attempted=True)
    command(s, sid, "pause")
    with pytest.raises(ValueError):
        command(s, sid, "reveal", question_id=q["session_question_id"])
    command(s, sid, "resume")
    with pytest.raises(ValueError, match="Finish solving"):
        command(s, sid, "reveal", question_id=q["session_question_id"])
    command(s, sid, "finish_solving")
    assert (
        command(s, sid, "reveal", question_id=q["session_question_id"])["guide"][
            "solution"
        ]
        == "Reviewed worked solution"
    )


def test_legacy_writers_and_helper_cannot_mutate_extended_attempt(tmp_path):
    s, sid, path, clock = candidate(tmp_path)
    command(s, sid, "pause")
    old = _service(path, clock)
    for call in (
        lambda: old.runner_view(sid),
        lambda: old.submit(sid),
        lambda: old.heartbeat(sid, session_question_id=None),
        lambda: old.coding_context(sid, question(s, sid)["session_question_id"]),
    ):
        with pytest.raises(Exception, match="candidate workspace"):
            call()
    clock.advance(1000)
    with pytest.raises(Exception, match="candidate workspace"):
        old.start("assessment-1", confirmed=True)
    assert s.state(sid)["status"] == "paused"


def test_paper_cannot_enter_ordinary_evaluator(tmp_path):
    s, sid, path, clock = candidate(tmp_path, paper=True)
    command(s, sid, "finish_solving")
    from personal_learning_assistant.services.assessment_evaluation_service import (
        AssessmentEvaluationService,
    )

    with pytest.raises(Exception, match="candidate workspace"):
        AssessmentEvaluationService(path).create(sid)


def test_receipts_do_not_store_or_replay_private_guides(tmp_path):
    s, sid, path, clock = candidate(tmp_path, paper=True)
    command(s, sid, "finish_solving")
    q = question(s, sid)
    payload = dict(
        request_id="request-reveal-001",
        expected_revision=s.state(sid)["revision"],
        question_id=q["session_question_id"],
    )
    s.command(sid, "reveal", payload)
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT result_json FROM assessment_candidate_receipts WHERE request_id=?",
            (payload["request_id"],),
        ).fetchone()
        assert "Reviewed worked solution" not in row[0]
    replay = s.command(sid, "reveal", payload)
    assert "Reviewed worked solution" not in json.dumps(replay)


@pytest.mark.parametrize(
    "table,event",
    [
        ("assessment_test_responses", "UPDATE"),
        ("assessment_candidate_execution", "UPDATE"),
        ("assessment_test_events", "INSERT"),
        ("assessment_candidate_receipts", "INSERT"),
    ],
)
def test_nth_write_failure_rolls_back_all_state(tmp_path, table, event):
    s, sid, path, clock = candidate(tmp_path)
    q = question(s, sid)
    with sqlite3.connect(path) as db:
        db.execute(
            f"CREATE TRIGGER fixture_failure BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT,'injected failure'); END"
        )
        before = list(db.iterdump())
    with pytest.raises(sqlite3.IntegrityError):
        command(
            s,
            sid,
            "pause",
            question_id=q["session_question_id"],
            expected_response_revision=1,
            response={"selected_option_ids": ["B"]},
        )
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before


def test_competing_commands_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    s, sid, path, clock = candidate(tmp_path)

    def attempt(kind):
        from personal_learning_assistant.services.assessment_execution_service import (
            AssessmentExecutionService,
        )

        other = AssessmentExecutionService(path, now_fn=clock)
        try:
            return other.command(
                sid,
                kind,
                dict(request_id="request-" + kind + "-race", expected_revision=1),
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["pause", "submit"]))
    assert sum(result is not None for result in results) == 1
    assert s.state(sid)["status"] in {"paused", "submitted"}


def test_paper_exam_denied_before_source_reveal(tmp_path):
    with pytest.raises(ValueError, match="all-subjective practice"):
        candidate(tmp_path, paper=True, mode="exam")


def test_source_only_repository_never_initializes_missing_schema(tmp_path):
    from personal_learning_assistant.services.assessment_execution_service import (
        AssessmentExecutionService,
    )

    path = _database(tmp_path)
    with sqlite3.connect(path) as db:
        before = list(db.iterdump())
    with pytest.raises(sqlite3.OperationalError):
        AssessmentExecutionService(path).state("missing")
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before


def test_lock_wait_clock_sampled_after_acquiring_write_transaction(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import time
    from personal_learning_assistant.services.assessment_execution_service import (
        AssessmentExecutionService,
    )

    s, sid, path, clock = candidate(tmp_path)
    clock.advance(59)
    started = Event()

    def pause():
        started.set()
        return AssessmentExecutionService(path, now_fn=clock).command(
            sid, "pause", dict(request_id="request-lock-clock", expected_revision=1)
        )

    db = sqlite3.connect(path, isolation_level=None)
    db.execute("BEGIN IMMEDIATE")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(pause)
            assert started.wait(timeout=5)
            # Worker cannot acquire the write lock until the controlling transaction releases.
            time.sleep(0.1)
            clock.advance(2)
            db.rollback()
            result = future.result(timeout=5)
        assert result["state"]["status"] == "expired" and result["error"] == "expired"
    finally:
        db.close()


def test_self_success_cannot_mutate_grades_or_suppress_recovery(tmp_path):
    s, sid, path, clock = candidate(tmp_path, paper=True)

    def protected_snapshot():
        with sqlite3.connect(path) as db:
            tables = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                if not row[0].startswith("assessment_candidate_")
                and row[0] not in {"assessment_test_sessions", "assessment_test_events"}
            ]
            return {
                name: db.execute('SELECT * FROM "' + name + '"').fetchall()
                for name in tables
            }

    before = protected_snapshot()
    command(s, sid, "finish_solving")
    for q in s.state(sid)["questions"]:
        command(s, sid, "reveal", question_id=q["session_question_id"])
        command(
            s,
            sid,
            "self_save",
            question_id=q["session_question_id"],
            marks=str(q["max_marks_milli"] / 1000),
        )
    command(s, sid, "self_submit", confirmed=True)
    assert s.review_summary(sid)["percentage"] == 100
    assert s.review_summary(sid)["eligible_for_recovery"] is False
    assert protected_snapshot() == before


def test_submitted_review_and_receipts_are_sql_immutable(tmp_path):
    s, sid, path, clock = candidate(tmp_path, paper=True)
    command(s, sid, "finish_solving")
    for q in s.state(sid)["questions"]:
        command(
            s, sid, "self_save", question_id=q["session_question_id"], unattempted=True
        )
    command(s, sid, "self_submit", confirmed=True)
    with sqlite3.connect(path) as db:
        for sql in (
            "UPDATE assessment_candidate_self_reviews SET snapshot_json='{}'",
            "DELETE FROM assessment_candidate_self_reviews",
            "UPDATE assessment_candidate_receipts SET result_json='{}'",
            "DELETE FROM assessment_candidate_receipts",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(sql)
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_step_error_reasons_are_bounded_and_preserved(tmp_path):
    from scripts.assessment_execution_fixture import create_fixture

    s, ids, key = create_fixture(tmp_path / "fixture")
    sid = ids["paper"]
    command(s, sid, "finish_solving")
    q = s.state(sid)["questions"][0]
    command(s, sid, "reveal", question_id=q["session_question_id"])
    command(
        s,
        sid,
        "self_save",
        question_id=q["session_question_id"],
        steps={"factor": "1", "forward": "0.5", "back": "0.5"},
        step_reasons={
            "forward": "Arithmetic slip",
            "back": "Used earlier incorrect value",
        },
    )
    item = s.state(sid)["review"]["items"][q["session_question_id"]]
    assert (
        item["step_reasons"]["forward"] == "Arithmetic slip"
        and item["marking_mode"] == "per_step"
    )
    with pytest.raises(ValueError):
        command(
            s,
            sid,
            "self_save",
            question_id=q["session_question_id"],
            steps={"factor": "1", "forward": "1", "back": "1"},
            step_reasons={"unknown": "Forged step"},
        )


def test_structured_imported_paper_uses_original_author_id_across_self_review(tmp_path):
    """Reviewed package IDs are fixed before approval; canonical IDs are generated
    later and must not silently replace the rubric's authored identity.
    """
    from pathlib import Path
    from personal_learning_assistant.services.assessment_execution_service import AssessmentExecutionService
    path = _database(tmp_path)
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT q.id,q.max_marks_milli FROM questions q ORDER BY ordinal"
        ).fetchall()
        for index, (canonical, maximum) in enumerate(rows):
            authored = "package-" + canonical
            rubric = "Reviewer method and intermediate-work criteria."
            if index == 0:
                rubric = json.dumps({
                    "schema": "anvaya.subjective-rubric", "version": 1,
                    "question_id": authored, "total_marks_milli": maximum,
                    "grading_increment_milli": 500,
                    "steps": [{
                        "id": "method", "label": "Method",
                        "expected_work": "Use the correct lower triangular factor",
                        "max_marks_milli": maximum, "prerequisites": [],
                        "award_when": ["Correct method"],
                        "do_not_award_when": ["Incorrect method"],
                        "allowed_awards_milli": [0, maximum],
                        "alternative_group": None
                    }],
                    "common_mistakes": ["Confusing L and U"],
                    "review_required": False
                })
            db.execute(
                "UPDATE assessment_question_specs SET question_type='long_subjective', "
                "package_question_id=?,solution_text='Reviewed method',rubric_text=? "
                "WHERE question_id=?", (authored, rubric, canonical)
            )
        db.execute("UPDATE assessment_runtime_specs SET mode='practice'")
    clock = Clock()
    sid = _service(path, clock).start("assessment-1", confirmed=True)["session_id"]
    with sqlite3.connect(path) as db:
        db.executescript(
            (Path(__file__).resolve().parents[1] / "scripts/fixtures/assessment_execution_candidate.sql").read_text()
        )
    service = AssessmentExecutionService(path, now_fn=clock)
    service.adopt(sid, kind="paper_subjective", reviewed_fixture=True)
    command(service, sid, "finish_solving")
    q = question(service, sid)
    guide = command(service, sid, "reveal", question_id=q["session_question_id"])["guide"]
    assert guide["rubric"]["question_id"] == "package-" + q["question_id"]
    result = command(
        service, sid, "self_save",
        question_id=q["session_question_id"],
        steps={"method": "1.0"}
    )
    assert result["state"]["review"]["items"][q["session_question_id"]]["awarded_marks_milli"] == 1000
    assert service.authorized_guides(sid)[q["session_question_id"]]["rubric"]["question_id"] == "package-" + q["question_id"]
