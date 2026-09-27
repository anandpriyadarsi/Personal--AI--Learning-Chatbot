from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


NOW = "2026-09-27T00:00:00Z"


def _database(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

    path = tmp_path / "learning_assistant.db"
    assert apply_migrations(path) == tuple(range(1, 15))
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at) "
            "VALUES ('course-ma', 'MA103N', 'Linear Algebra', 'active', '', ?, ?)",
            (NOW, NOW),
        )
        for topic_id, name, position in [
            ("topic-lu", "LU Factorization", 1),
            ("topic-rank", "Matrix Rank", 2),
        ]:
            connection.execute(
                "INSERT INTO topics "
                "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
                "VALUES (?, 'course-ma', ?, ?, ?, 'not_started', ?, ?)",
                (topic_id, name, name.lower(), position, NOW, NOW),
            )
        connection.execute(
            "INSERT INTO assessments "
            "(id, course_id, assessment_type, title, due_on, due_time, status, "
            "weight_bps, max_points_milli, earned_points_milli, description, "
            "created_at, updated_at, deleted_at) "
            "VALUES ('a1', 'course-ma', 'quiz', 'Recovery Source Test', NULL, NULL, "
            "'pending', NULL, 8000, NULL, '', ?, ?, NULL)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO assessment_test_sessions "
            "(id, assessment_id, status, mode, title_snapshot, "
            "course_code_snapshot, course_name_snapshot, instructions_snapshot, "
            "duration_seconds, question_count, max_marks_milli, started_at, "
            "expires_at, submitted_at, submission_reason, current_ordinal, "
            "revision, created_at, updated_at) "
            "VALUES ('s1', 'a1', 'submitted', 'exam', 'Recovery Source Test', "
            "'MA103N', 'Linear Algebra', '', 1800, 4, 8000, ?, ?, ?, 'user', "
            "1, 1, ?, ?)",
            (
                "2026-09-26T10:00:00Z",
                "2026-09-26T10:30:00Z",
                "2026-09-26T10:30:00Z",
                NOW,
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO assessment_session_evaluations "
            "(id, session_id, status, engine_version, created_at, updated_at, confirmed_at) "
            "VALUES ('se1', 's1', 'confirmed', 'assessment-evaluation-v1', ?, ?, ?)",
            (NOW, NOW, NOW),
        )

        rows = [
            ("q1", "sq1", 1, "topic-lu", 0, "incorrect", 220, "medium"),
            ("q2", "sq2", 2, "topic-lu", 500, "partially_correct", 260, "medium"),
            ("q3", "sq3", 3, "topic-rank", 2000, "correct", 80, "easy"),
            ("q4", "sq4", 4, "topic-rank", 2000, "correct", 90, "easy"),
        ]
        for qid, sqid, ordinal, topic_id, score, outcome, focus, difficulty in rows:
            connection.execute(
                "INSERT INTO questions "
                "(id, assessment_id, ordinal, question_text, max_marks_milli, "
                "status, user_notes, import_batch_id, created_at, updated_at, deleted_at) "
                "VALUES (?, 'a1', ?, ?, 2000, 'not_started', '', NULL, ?, ?, NULL)",
                (qid, ordinal, "Question " + qid, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO assessment_test_session_questions "
                "(id, session_id, question_id, ordinal, question_number, "
                "section_label, question_type, question_text, max_marks_milli, "
                "negative_marks_milli, scoring_policy, topic_id, chapter_label, "
                "subtopic_label, concepts_json, difficulty, expected_method, "
                "options_json, answer_key_json, solution_text, rubric_text, created_at) "
                "VALUES (?, 's1', ?, ?, ?, 'A', 'mcq', ?, 2000, 500, 'standard', "
                "?, 'Systems', ?, '[]', ?, '', '[]', '{}', '', '', ?)",
                (
                    sqid,
                    qid,
                    ordinal,
                    str(ordinal),
                    "Snapshot " + qid,
                    topic_id,
                    "LU" if topic_id == "topic-lu" else "Rank",
                    difficulty,
                    NOW,
                ),
            )
            response_id = "r-" + sqid
            connection.execute(
                "INSERT INTO assessment_test_responses "
                "(id, session_question_id, state, response_json, focus_seconds, "
                "visited_at, answered_at, saved_at, revision, updated_at) "
                "VALUES (?, ?, 'answered', '{}', ?, ?, ?, ?, 1, ?)",
                (response_id, sqid, focus, NOW, NOW, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO assessment_response_evaluations "
                "(id, session_evaluation_id, session_question_id, question_id, "
                "response_id, evaluator_type, evaluator_model, status, outcome, "
                "awarded_marks_milli, max_marks_milli, penalty_marks_milli, "
                "scoring_policy, rubric_version, confidence, feedback_text, "
                "details_json, question_attempt_id, created_at, updated_at, confirmed_at) "
                "VALUES (?, 'se1', ?, ?, ?, 'deterministic', '', 'auto_confirmed', "
                "?, ?, 2000, ?, 'standard', '', 1.0, '', '{}', NULL, ?, ?, ?)",
                (
                    "ev-" + sqid,
                    sqid,
                    qid,
                    response_id,
                    outcome,
                    score,
                    max(0, -score),
                    NOW,
                    NOW,
                    NOW,
                ),
            )

        for mid, evid, category in [
            ("m1", "ev-sq1", "concept_gap"),
            ("m2", "ev-sq2", "concept_gap"),
        ]:
            connection.execute(
                "INSERT INTO assessment_evaluation_mistakes "
                "(id, response_evaluation_id, category, note, source_type, status, "
                "mistake_event_id, created_at, confirmed_at) "
                "VALUES (?, ?, ?, '', 'user', 'confirmed', NULL, ?, ?)",
                (mid, evid, category, NOW, NOW),
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _service(path, task_service=None):
    from personal_learning_assistant.services.adaptive_academic_loop_service import (
        AdaptiveAcademicLoopService,
    )
    return AdaptiveAcademicLoopService(path, task_service=task_service)


def test_migration_0013_adds_recommendation_ledger_and_recovery_task_unique_index(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "assessment_recovery_recommendations",
            "assessment_recovery_recommendation_events",
        }.issubset(tables)
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(planner_tasks)")
        }
        assert "planner_tasks_assessment_recovery_external_uq" in indexes
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_preview_is_read_only_and_maps_concept_gap_to_concept_rebuild(tmp_path):
    path = _database(tmp_path)
    preview = _service(path).preview()

    assert preview["has_evidence"] is True
    lu = next(item for item in preview["candidates"] if item["topic_id"] == "topic-lu")
    assert lu["action_family"] == "concept_rebuild"
    assert lu["suggested_priority"] == "P0"
    assert lu["suggested_minutes"] == 60
    assert "LU Factorization" in lu["alex_prompt"]
    assert any(step["kind"] == "retest" for step in lu["action_plan"])

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_recovery_recommendations"
        ).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 0
    finally:
        connection.close()


def test_generate_selected_is_idempotent_and_does_not_touch_planner(tmp_path):
    path = _database(tmp_path)
    service = _service(path)
    preview = service.preview()
    lu = next(item for item in preview["candidates"] if item["topic_id"] == "topic-lu")

    first = service.generate([lu["evidence_fingerprint"]])
    second = service.generate([lu["evidence_fingerprint"]])
    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["existing_count"] == 1

    workspace = service.workspace()
    assert len(workspace["pending"]) == 1
    assert workspace["pending"][0]["topic_id"] == "topic-lu"

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 0
    finally:
        connection.close()


def test_changed_evidence_supersedes_old_pending_recommendation(tmp_path):
    path = _database(tmp_path)
    service = _service(path)
    lu = next(item for item in service.preview()["candidates"] if item["topic_id"] == "topic-lu")
    service.generate([lu["evidence_fingerprint"]])

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE assessment_response_evaluations "
            "SET awarded_marks_milli=1000, outcome='partially_correct' "
            "WHERE id='ev-sq1'"
        )
        connection.commit()
    finally:
        connection.close()

    changed = next(
        item for item in service.preview()["candidates"]
        if item["topic_id"] == "topic-lu"
    )
    assert changed["evidence_fingerprint"] != lu["evidence_fingerprint"]
    service.generate([changed["evidence_fingerprint"]])

    workspace = service.workspace()
    assert len(workspace["pending"]) == 1
    assert len(workspace["superseded"]) == 1


def test_apply_creates_one_linked_planner_backlog_task_and_retry_is_idempotent(tmp_path):
    path = _database(tmp_path)
    service = _service(path)
    lu = next(item for item in service.preview()["candidates"] if item["topic_id"] == "topic-lu")
    service.generate([lu["evidence_fingerprint"]])
    recommendation = service.workspace()["pending"][0]

    applied = service.apply(
        recommendation["id"],
        {
            "revision": recommendation["revision"],
            "title": "Recover LU before next quiz",
            "description": "Use the ANVAYA recovery sequence.",
            "priority": "P1",
            "estimated_minutes": "50",
            "due_on": "2026-10-03",
        },
    )
    assert applied["status"] == "applied"

    again = service.apply(applied["id"], {"revision": applied["revision"]})
    assert again["status"] == "applied"

    connection = sqlite3.connect(path)
    try:
        tasks = connection.execute(
            "SELECT external_id, title, priority, estimated_minutes, due_on, "
            "course_id, topic_id, status FROM planner_tasks"
        ).fetchall()
        assert tasks == [
            (
                "assessment-recovery:" + recommendation["id"],
                "Recover LU before next quiz",
                "P1",
                50,
                "2026-10-03",
                "course-ma",
                "topic-lu",
                "backlog",
            )
        ]
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_recovery_recommendation_events "
            "WHERE recommendation_id=? AND event_type='applied_to_planner'",
            (recommendation["id"],),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_reject_creates_no_planner_task(tmp_path):
    path = _database(tmp_path)
    service = _service(path)
    rank = next(item for item in service.preview()["candidates"] if item["topic_id"] == "topic-rank")
    service.generate([rank["evidence_fingerprint"]])
    recommendation = service.workspace()["pending"][0]

    result = service.reject(
        recommendation["id"],
        revision=recommendation["revision"],
        reason="No recovery needed now.",
    )
    assert result["status"] == "rejected"

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 0
    finally:
        connection.close()


def test_interrupted_apply_remains_accepted_and_retry_resumes_without_duplicate(tmp_path):
    from personal_learning_assistant.services.operational_task_service import (
        OperationalTaskUnavailableError,
    )

    class FailingTasks:
        def create_assessment_recovery_task(self, *args, **kwargs):
            raise OperationalTaskUnavailableError("simulated planner outage")

    path = _database(tmp_path)
    failing = _service(path, task_service=FailingTasks())
    lu = next(item for item in failing.preview()["candidates"] if item["topic_id"] == "topic-lu")
    failing.generate([lu["evidence_fingerprint"]])
    recommendation = failing.workspace()["pending"][0]

    with pytest.raises(Exception, match="application is pending"):
        failing.apply(
            recommendation["id"],
            {
                "revision": recommendation["revision"],
                "title": "LU recovery",
                "priority": "P1",
                "estimated_minutes": "45",
            },
        )

    accepted = failing.recommendation(recommendation["id"])
    assert accepted["status"] == "accepted"

    recovered = _service(path).apply(
        accepted["id"],
        {"revision": accepted["revision"]},
    )
    assert recovered["status"] == "applied"

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 1
    finally:
        connection.close()


def test_apply_does_not_mutate_mastery_progress_or_daily_schedule(tmp_path):
    path = _database(tmp_path)
    service = _service(path)
    lu = next(item for item in service.preview()["candidates"] if item["topic_id"] == "topic-lu")
    service.generate([lu["evidence_fingerprint"]])
    recommendation = service.workspace()["pending"][0]
    service.apply(
        recommendation["id"],
        {
            "revision": recommendation["revision"],
            "title": recommendation["suggested_title"],
            "priority": "P0",
            "estimated_minutes": "60",
        },
    )

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM daily_agendas").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM daily_agenda_items").fetchone()[0] == 0
        assert connection.execute(
            "SELECT status FROM topics WHERE id='topic-lu'"
        ).fetchone()[0] == "not_started"
    finally:
        connection.close()


def _app(path):
    from personal_learning_assistant.services.adaptive_academic_loop_service import (
        AdaptiveAcademicLoopService,
    )
    from personal_learning_assistant.ui.web import create_app
    return create_app(
        {
            "TESTING": True,
            "ADAPTIVE_ACADEMIC_LOOP_SERVICE_FACTORY": lambda: AdaptiveAcademicLoopService(path),
        }
    )


def test_web_adaptive_loop_get_is_read_only_and_posts_use_prg(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()

    page = client.get("/assessments/adaptive")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Adaptive Academic Loop" in html
    assert "Generate selected recommendations" in html

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_recovery_recommendations"
        ).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 0
    finally:
        connection.close()

    service = _service(path)
    lu = next(item for item in service.preview()["candidates"] if item["topic_id"] == "topic-lu")
    generated = client.post(
        "/assessments/adaptive/generate",
        data={"evidence_fingerprint": lu["evidence_fingerprint"]},
        follow_redirects=False,
    )
    assert generated.status_code == 303

    recommendation = service.workspace()["pending"][0]
    applied = client.post(
        f"/assessments/adaptive/{recommendation['id']}/apply",
        data={
            "revision": str(recommendation["revision"]),
            "title": "Web LU recovery",
            "priority": "P1",
            "estimated_minutes": "45",
        },
        follow_redirects=False,
    )
    assert applied.status_code == 303


def test_phase_f_contract_keeps_human_approval_and_no_silent_mastery():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "ASSESSMENT_STUDIO_PHASE_F.md").read_text(encoding="utf-8")
    assert "pending → accepted → applied" in spec
    assert "explicit Apply" in spec
    assert "does not write" in spec
    assert "topic status" in spec
    assert "assessment-recovery:<recommendation_id>" in spec
