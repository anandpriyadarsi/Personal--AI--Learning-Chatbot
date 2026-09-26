from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


NOW = "2026-09-27T00:00:00Z"


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 27, 0, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def _database(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

    path = tmp_path / "learning_assistant.db"
    assert apply_migrations(path) == tuple(range(1, 13))
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            ("course-ma", "MA103N", "Linear Algebra", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, 'not_started', ?, ?)",
            (
                "topic-lu",
                "course-ma",
                "LU Factorization",
                "lu factorization",
                NOW,
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO assessments "
            "(id, course_id, assessment_type, title, due_on, due_time, status, "
            "weight_bps, max_points_milli, earned_points_milli, description, "
            "created_at, updated_at, deleted_at) "
            "VALUES (?, ?, 'quiz', ?, NULL, NULL, 'pending', NULL, 10000, NULL, '', ?, ?, NULL)",
            ("assessment-1", "course-ma", "Timed CBT Test", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO assessment_runtime_specs "
            "(assessment_id, mode, duration_minutes, instructions_text, origin, "
            "package_id, package_revision, created_at, updated_at) "
            "VALUES (?, 'exam', 1, ?, 'external_package', 'phase-c-test', 1, ?, ?)",
            (
                "assessment-1",
                "Attempt all questions.\nUse Mark for Review when needed.",
                NOW,
                NOW,
            ),
        )

        questions = [
            (
                "q-mcq",
                1,
                "Which factor in A=LU is lower triangular?",
                1000,
                "1",
                "A",
                "mcq",
                250,
                "standard",
                "easy",
                '{"correct_option_ids":["B"],"accepted_answers":[]}',
                "SECRET-MCQ-SOLUTION",
                "",
            ),
            (
                "q-msq",
                2,
                "Select all triangular matrices.",
                2000,
                "2",
                "A",
                "msq",
                500,
                "partial",
                "medium",
                '{"correct_option_ids":["A","C"],"accepted_answers":[]}',
                "SECRET-MSQ-SOLUTION",
                "",
            ),
            (
                "q-num",
                3,
                "If rank(A)=4 for a 4x4 matrix, enter the rank.",
                2000,
                "3",
                "B",
                "numerical",
                0,
                "standard",
                "easy",
                '{"correct_option_ids":[],"accepted_answers":["4"]}',
                "SECRET-NUM-SOLUTION",
                "",
            ),
            (
                "q-sub",
                4,
                "Explain how LU factorization solves Ax=b.",
                5000,
                "4",
                "B",
                "long_subjective",
                0,
                "standard",
                "medium",
                '{"correct_option_ids":[],"accepted_answers":[]}',
                "SECRET-SUBJECTIVE-SOLUTION",
                "SECRET-SUBJECTIVE-RUBRIC",
            ),
        ]
        for (
            qid,
            ordinal,
            text,
            marks,
            number,
            section,
            qtype,
            negative,
            scoring,
            difficulty,
            answer_json,
            solution,
            rubric,
        ) in questions:
            connection.execute(
                "INSERT INTO questions "
                "(id, assessment_id, ordinal, question_text, max_marks_milli, status, "
                "user_notes, import_batch_id, created_at, updated_at, deleted_at) "
                "VALUES (?, 'assessment-1', ?, ?, ?, 'not_started', '', NULL, ?, ?, NULL)",
                (qid, ordinal, text, marks, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO assessment_question_specs "
                "(question_id, package_question_id, question_number, section_label, "
                "question_type, negative_marks_milli, scoring_policy, difficulty, "
                "expected_method, estimated_seconds, chapter_label, subtopic_label, "
                "concepts_json, authoring_confidence, solution_text, rubric_text, "
                "answer_json, source_kind, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 120, 'Systems', 'LU', "
                "?, 0.99, ?, ?, ?, 'original', ?, ?)",
                (
                    qid,
                    "pkg-" + qid,
                    number,
                    section,
                    qtype,
                    negative,
                    scoring,
                    difficulty,
                    "Use the intended linear algebra method.",
                    '["factorization"]',
                    solution,
                    rubric,
                    answer_json,
                    NOW,
                    NOW,
                ),
            )
            connection.execute(
                "INSERT INTO question_topic_mappings "
                "(id, question_id, topic_id, score, rank, method, state, reason, "
                "created_at, reviewed_at) "
                "VALUES (?, ?, 'topic-lu', 1.0, 1, 'test', 'confirmed', '', ?, ?)",
                ("map-" + qid, qid, NOW, NOW),
            )

        for option_id, text, correct in [
            ("A", "Upper triangular", 0),
            ("B", "Lower triangular", 1),
            ("C", "Diagonal only", 0),
            ("D", "None", 0),
        ]:
            connection.execute(
                "INSERT INTO question_options "
                "(question_id, option_id, position, option_text, is_correct) "
                "VALUES ('q-mcq', ?, ?, ?, ?)",
                (option_id, ord(option_id) - 64, text, correct),
            )
        for option_id, text, correct in [
            ("A", "Lower triangular", 1),
            ("B", "Dense non-triangular", 0),
            ("C", "Upper triangular", 1),
            ("D", "Rectangular arbitrary", 0),
        ]:
            connection.execute(
                "INSERT INTO question_options "
                "(question_id, option_id, position, option_text, is_correct) "
                "VALUES ('q-msq', ?, ?, ?, ?)",
                (option_id, ord(option_id) - 64, text, correct),
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _service(path, clock):
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService

    return AssessmentRunnerService(path, now_fn=clock)


def test_migration_0011_adds_session_snapshot_response_and_event_tables(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "assessment_test_sessions",
            "assessment_test_session_questions",
            "assessment_test_responses",
            "assessment_test_events",
        }.issubset(tables)
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_start_is_idempotent_and_snapshots_private_keys_without_public_leak(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)

    first = service.start("assessment-1", confirmed=True)
    second = service.start("assessment-1", confirmed=True)
    assert first["created"] is True
    assert second == {"session_id": first["session_id"], "created": False}

    view = service.runner_view(first["session_id"], ordinal=1)
    assert view["terminal"] is False
    assert view["question"]["question_type"] == "mcq"
    assert view["question"]["state"] == "not_answered"
    assert view["remaining_seconds"] == 60

    public = json.dumps(view, ensure_ascii=False, sort_keys=True)
    assert "SECRET-MCQ-SOLUTION" not in public
    assert "SECRET-SUBJECTIVE-RUBRIC" not in public
    assert "correct_option_ids" not in public
    assert "is_correct" not in public

    connection = sqlite3.connect(path)
    try:
        private = connection.execute(
            "SELECT answer_key_json, solution_text FROM assessment_test_session_questions "
            "WHERE session_id=? AND ordinal=1",
            (first["session_id"],),
        ).fetchone()
        assert '"B"' in private[0]
        assert private[1] == "SECRET-MCQ-SOLUTION"
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_test_sessions "
            "WHERE assessment_id='assessment-1' AND status='active'"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_mcq_msq_state_machine_mark_review_clear_and_focus_clamp(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)
    session_id = service.start("assessment-1", confirmed=True)["session_id"]
    view = service.runner_view(session_id, ordinal=1)
    q1 = view["question"]["session_question_id"]

    with pytest.raises(Exception, match="only one"):
        service.save_response(
            session_id,
            q1,
            {"selected_option_ids": ["A", "B"]},
            mark_for_review=False,
        )

    result = service.save_response(
        session_id,
        q1,
        {"selected_option_ids": ["B"]},
        mark_for_review=False,
        focus_seconds_delta=999,
    )
    assert result["state"] == "answered"

    view2 = service.runner_view(session_id, ordinal=2)
    q2 = view2["question"]["session_question_id"]
    result = service.save_response(
        session_id,
        q2,
        {"selected_option_ids": ["A", "C"]},
        mark_for_review=True,
    )
    assert result["state"] == "answered_marked_for_review"

    same = service.save_response(
        session_id,
        q2,
        {"selected_option_ids": ["A", "C"]},
        mark_for_review=None,
    )
    assert same["state"] == "answered_marked_for_review"

    cleared = service.clear_response(session_id, q2)
    assert cleared["state"] == "not_answered"

    with pytest.raises(Exception, match="invalid"):
        service.save_response(
            session_id,
            q2,
            {"selected_option_ids": ["Z"]},
            mark_for_review=False,
        )

    connection = sqlite3.connect(path)
    try:
        focus = connection.execute(
            "SELECT r.focus_seconds FROM assessment_test_responses r "
            "JOIN assessment_test_session_questions q ON q.id=r.session_question_id "
            "WHERE q.session_id=? AND q.ordinal=1",
            (session_id,),
        ).fetchone()[0]
        assert focus == 60
    finally:
        connection.close()


def test_numerical_subjective_autosave_and_resume_persist_responses(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)
    session_id = service.start("assessment-1", confirmed=True)["session_id"]

    q3 = service.runner_view(session_id, ordinal=3)["question"]["session_question_id"]
    service.save_response(
        session_id,
        q3,
        {"value": "4"},
        mark_for_review=False,
        event_type="response_autosaved",
    )
    q4 = service.runner_view(session_id, ordinal=4)["question"]["session_question_id"]
    service.save_response(
        session_id,
        q4,
        {"text": "Factor A=LU, solve Ly=b, then Ux=y."},
        mark_for_review=True,
        event_type="response_autosaved",
    )

    resumed = _service(path, clock).runner_view(session_id, ordinal=4)
    assert resumed["question"]["response"]["text"].startswith("Factor A=LU")
    assert resumed["question"]["state"] == "answered_marked_for_review"

    all_states = {q["ordinal"]: q["state"] for q in resumed["questions"]}
    assert all_states[3] == "answered"
    assert all_states[4] == "answered_marked_for_review"


def test_server_timeout_closes_session_once_blocks_writes_and_allows_new_attempt(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)
    first_id = service.start("assessment-1", confirmed=True)["session_id"]
    q1 = service.runner_view(first_id, ordinal=1)["question"]["session_question_id"]

    clock.advance(61)
    heartbeat = service.heartbeat(
        first_id,
        session_question_id=q1,
        focus_seconds_delta=20,
    )
    assert heartbeat["status"] == "expired"
    assert heartbeat["remaining_seconds"] == 0

    blocked = service.save_response(
        first_id,
        q1,
        {"selected_option_ids": ["B"]},
        mark_for_review=False,
    )
    assert blocked == {"status": "expired", "saved": False}

    service.heartbeat(first_id, session_question_id=q1, focus_seconds_delta=20)

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_test_events "
            "WHERE session_id=? AND event_type='auto_submitted_timeout'",
            (first_id,),
        ).fetchone()[0] == 1
    finally:
        connection.close()

    second = service.start("assessment-1", confirmed=True)
    assert second["created"] is True
    assert second["session_id"] != first_id


def test_manual_submit_is_idempotent_and_does_not_grade_or_mutate_progress(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)
    session_id = service.start("assessment-1", confirmed=True)["session_id"]
    q1 = service.runner_view(session_id, ordinal=1)["question"]["session_question_id"]
    service.save_response(
        session_id,
        q1,
        {"selected_option_ids": ["B"]},
        mark_for_review=False,
    )

    first = service.submit(session_id)
    second = service.submit(session_id)
    assert first["status"] == "submitted"
    assert first["submission_reason"] == "user"
    assert second["status"] == "submitted"

    after = service.save_response(
        session_id,
        q1,
        {"selected_option_ids": ["A"]},
        mark_for_review=False,
    )
    assert after == {"status": "submitted", "saved": False}

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM mistake_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0] == 0
    finally:
        connection.close()


def _app(path, clock):
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "ASSESSMENT_RUNNER_SERVICE_FACTORY": lambda: AssessmentRunnerService(
                path, now_fn=clock
            ),
        }
    )


def test_web_runner_has_clickable_mcq_msq_palette_autosave_and_no_answer_leak(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    app = _app(path, clock)
    client = app.test_client()

    library = client.get("/assessments/tests")
    assert library.status_code == 200
    assert "Timed CBT Test" in library.get_data(as_text=True)

    preflight = client.get("/assessments/tests/assessment-1")
    assert preflight.status_code == 200
    assert "Start test" in preflight.get_data(as_text=True)

    started = client.post(
        "/assessments/tests/assessment-1/start",
        data={"confirmed": "1"},
        follow_redirects=False,
    )
    assert started.status_code == 303
    location = started.headers["Location"]
    assert "/assessments/sessions/" in location
    session_id = location.rstrip("/").split("/")[-1]

    page = client.get(location)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'type="radio"' in html
    assert "Save &amp; Next" in html
    assert "Mark for Review &amp; Next" in html
    assert "Question palette" in html
    assert "SECRET-MCQ-SOLUTION" not in html
    assert "SECRET-SUBJECTIVE-RUBRIC" not in html
    assert "correct_option_ids" not in html
    assert "is_correct" not in html

    connection = sqlite3.connect(path)
    try:
        q1, q2 = connection.execute(
            "SELECT id FROM assessment_test_session_questions "
            "WHERE session_id=? ORDER BY ordinal LIMIT 2",
            (session_id,),
        ).fetchall()
    finally:
        connection.close()
    q1 = q1[0]
    q2 = q2[0]

    auto = client.post(
        f"/assessments/sessions/{session_id}/questions/{q1}/autosave",
        json={"response": {"selected_option_ids": ["B"]}, "focus_seconds_delta": 7},
    )
    assert auto.status_code == 200
    body = auto.get_json()
    assert body["state"] == "answered"
    assert "correct" not in json.dumps(body).lower()

    msq = client.get(f"/assessments/sessions/{session_id}?q=2")
    assert msq.status_code == 200
    msq_html = msq.get_data(as_text=True)
    assert 'type="checkbox"' in msq_html
    assert "SECRET-MSQ-SOLUTION" not in msq_html

    marked = client.post(
        f"/assessments/sessions/{session_id}/questions/{q2}/action",
        data={
            "action": "mark_next",
            "option_ids": ["A", "C"],
            "current_ordinal": "2",
            "next_ordinal": "3",
            "focus_seconds_delta": "4",
        },
        follow_redirects=False,
    )
    assert marked.status_code == 303
    assert "q=3" in marked.headers["Location"]

    submitted = client.post(
        f"/assessments/sessions/{session_id}/submit",
        json={"reason": "user"},
        headers={"Accept": "application/json"},
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["status"] == "submitted"

    summary = client.get(f"/assessments/sessions/{session_id}/summary")
    assert summary.status_code == 200
    summary_html = summary.get_data(as_text=True)
    assert "Test submitted" in summary_html
    assert "SECRET-MCQ-SOLUTION" not in summary_html
    assert "SECRET-SUBJECTIVE-RUBRIC" not in summary_html


def test_start_requires_explicit_instruction_confirmation(tmp_path):
    from personal_learning_assistant.services.assessment_runner_service import (
        AssessmentRunnerService,
        AssessmentRunnerValidationError,
    )

    clock = Clock()
    service = AssessmentRunnerService(_database(tmp_path), now_fn=clock)
    with pytest.raises(AssessmentRunnerValidationError, match="Confirm"):
        service.start("assessment-1", confirmed=False)


def test_phase_c_source_contract_mentions_server_timer_snapshots_and_key_secrecy():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = (root / "ASSESSMENT_STUDIO_PHASE_C.md").read_text(encoding="utf-8")
    assert "server-authoritative" in spec
    assert "immutable session-question snapshots" in spec
    assert "answer keys" in spec
    assert "Save & Next" in spec
    assert "Answered + Marked for Review" in spec
