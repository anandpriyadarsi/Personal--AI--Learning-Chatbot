from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
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
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            ("course-ma", "MA103N", "Linear Algebra", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, 'not_started', ?, ?)",
            ("topic-lu", "course-ma", "LU Factorization", "lu factorization", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO assessments "
            "(id, course_id, assessment_type, title, due_on, due_time, status, "
            "weight_bps, max_points_milli, earned_points_milli, description, "
            "created_at, updated_at, deleted_at) "
            "VALUES (?, ?, 'quiz', ?, NULL, NULL, 'pending', NULL, 24000, NULL, '', ?, ?, NULL)",
            ("assessment-d", "course-ma", "Phase D Evaluation Test", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO assessment_runtime_specs "
            "(assessment_id, mode, duration_minutes, instructions_text, origin, "
            "package_id, package_revision, created_at, updated_at) "
            "VALUES (?, 'exam', 60, 'Attempt all questions.', 'external_package', "
            "'phase-d-test', 1, ?, ?)",
            ("assessment-d", NOW, NOW),
        )

        questions = [
            ("q1", 1, "Correct MCQ", 4000, "1", "mcq", 1000, "standard",
             '{"correct_option_ids":["B"],"accepted_answers":[]}', "MCQ solution", ""),
            ("q2", 2, "Wrong MCQ with negative marking", 4000, "2", "mcq", 1000, "standard",
             '{"correct_option_ids":["B"],"accepted_answers":[]}', "MCQ solution 2", ""),
            ("q3", 3, "Partial MSQ", 4000, "3", "msq", 2000, "partial",
             '{"correct_option_ids":["A","C","D"],"accepted_answers":[]}', "MSQ solution", ""),
            ("q4", 4, "Numerical normalization", 2000, "4", "numerical", 0, "standard",
             '{"correct_option_ids":[],"accepted_answers":["4"]}', "Numerical solution", ""),
            ("q5", 5, "Fill normalization", 2000, "5", "fill_blank", 0, "standard",
             '{"correct_option_ids":[],"accepted_answers":["linear algebra"]}', "Fill solution", ""),
            ("q6", 6, "True false normalization", 1000, "6", "true_false", 0, "standard",
             '{"correct_option_ids":[],"accepted_answers":["T"]}', "TF solution", ""),
            ("q7", 7, "Explain LU factorization.", 5000, "7", "long_subjective", 0, "standard",
             '{"correct_option_ids":[],"accepted_answers":[]}', "Factor A=LU, solve Ly=b, then Ux=y.",
             "2 marks factorization; 1 forward solve; 2 backward solve."),
            ("q8", 8, "Custom-scored MCQ", 2000, "8", "mcq", 500, "custom",
             '{"correct_option_ids":["A"],"accepted_answers":[]}', "Custom solution", ""),
        ]
        for (
            qid, ordinal, text, marks, number, qtype, negative,
            scoring, answer_json, solution, rubric
        ) in questions:
            connection.execute(
                "INSERT INTO questions "
                "(id, assessment_id, ordinal, question_text, max_marks_milli, "
                "status, user_notes, import_batch_id, created_at, updated_at, deleted_at) "
                "VALUES (?, 'assessment-d', ?, ?, ?, 'not_started', '', NULL, ?, ?, NULL)",
                (qid, ordinal, text, marks, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO assessment_question_specs "
                "(question_id, package_question_id, question_number, section_label, "
                "question_type, negative_marks_milli, scoring_policy, difficulty, "
                "expected_method, estimated_seconds, chapter_label, subtopic_label, "
                "concepts_json, authoring_confidence, solution_text, rubric_text, "
                "answer_json, source_kind, created_at, updated_at) "
                "VALUES (?, ?, ?, 'A', ?, ?, ?, 'medium', ?, 120, 'Systems', "
                "'LU', ?, 0.99, ?, ?, ?, 'original', ?, ?)",
                (
                    qid, "pkg-" + qid, number, qtype, negative, scoring,
                    "Use the intended method.", '["factorization"]',
                    solution, rubric, answer_json, NOW, NOW,
                ),
            )
            connection.execute(
                "INSERT INTO question_topic_mappings "
                "(id, question_id, topic_id, score, rank, method, state, reason, "
                "created_at, reviewed_at) "
                "VALUES (?, ?, 'topic-lu', 1.0, 1, 'reviewed', 'confirmed', '', ?, ?)",
                ("map-" + qid, qid, NOW, NOW),
            )

        options = {
            "q1": [("A", "Upper", 0), ("B", "Lower", 1), ("C", "Diagonal", 0), ("D", "None", 0)],
            "q2": [("A", "Wrong", 0), ("B", "Correct", 1), ("C", "Other", 0), ("D", "Other 2", 0)],
            "q3": [("A", "Correct A", 1), ("B", "Wrong B", 0), ("C", "Correct C", 1), ("D", "Correct D", 1)],
            "q8": [("A", "Correct", 1), ("B", "Wrong", 0)],
        }
        for qid, rows in options.items():
            for position, (option_id, text, correct) in enumerate(rows, start=1):
                connection.execute(
                    "INSERT INTO question_options "
                    "(question_id, option_id, position, option_text, is_correct) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (qid, option_id, position, text, correct),
                )
        connection.commit()
    finally:
        connection.close()
    return path


def _runner(path):
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    return AssessmentRunnerService(
        path,
        now_fn=lambda: datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc),
    )


def _evaluation(path):
    from personal_learning_assistant.services.assessment_evaluation_service import AssessmentEvaluationService
    return AssessmentEvaluationService(path)


def _submitted_session(path):
    runner = _runner(path)
    session_id = runner.start("assessment-d", confirmed=True)["session_id"]

    answers = {
        1: {"selected_option_ids": ["B"]},
        2: {"selected_option_ids": ["A"]},
        3: {"selected_option_ids": ["A", "C"]},
        4: {"value": "4.0"},
        5: {"value": "  Linear   Algebra  "},
        6: {"value": "true"},
        7: {"text": "Use A=LU, forward substitution and backward substitution."},
        8: {"selected_option_ids": ["A"]},
    }
    for ordinal, payload in answers.items():
        view = runner.runner_view(session_id, ordinal=ordinal)
        runner.save_response(
            session_id,
            view["question"]["session_question_id"],
            payload,
            mark_for_review=False,
        )
    runner.submit(session_id)
    return session_id


def test_migration_0012_adds_evaluation_tables_and_signed_attempt_columns(tmp_path):
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
            "assessment_session_evaluations",
            "assessment_response_evaluations",
            "assessment_evaluation_mistakes",
            "assessment_evaluation_events",
        }.issubset(tables)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(question_attempts)")
        }
        assert {"signed_score_milli", "evaluation_ref"}.issubset(columns)
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_deterministic_engine_scores_negative_partial_and_normalized_answers(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    evaluation_id = service.create(session_id)
    assert evaluation_id
    result = service.results(session_id)

    by_number = {q["question_number"]: q for q in result["questions"]}
    assert by_number["1"]["awarded_marks_milli"] == 4000
    assert by_number["1"]["outcome"] == "correct"

    assert by_number["2"]["awarded_marks_milli"] == -1000
    assert by_number["2"]["penalty_marks_milli"] == 1000
    assert by_number["2"]["outcome"] == "incorrect"

    assert by_number["3"]["awarded_marks_milli"] == 2667
    assert by_number["3"]["outcome"] == "partially_correct"
    assert by_number["3"]["details"]["partial_rule"] == "proportional_correct_subset_no_wrong_options"

    assert by_number["4"]["awarded_marks_milli"] == 2000
    assert by_number["5"]["awarded_marks_milli"] == 2000
    assert by_number["6"]["awarded_marks_milli"] == 1000

    assert by_number["7"]["status"] == "awaiting_review"
    assert by_number["7"]["awarded_marks_milli"] is None
    assert by_number["8"]["status"] == "auto_confirmed"
    assert by_number["8"]["outcome"] == "correct"
    assert by_number["8"]["awarded_marks_milli"] == 2000
    assert by_number["8"]["details"]["exact_match_auto_confirmed"] is True

    assert result["confirmed_score_milli"] == 12667
    assert result["awaiting_review_count"] == 1
    assert result["evaluation_status"] == "pending_review"
    assert result["is_final"] is False


def test_exact_custom_msq_is_auto_confirmed_but_non_exact_custom_msq_still_needs_review():
    from personal_learning_assistant.services.assessment_evaluation_service import (
        _deterministic_score,
    )

    base = {
        "question_type": "msq",
        "scoring_policy": "custom",
        "max_marks_milli": 2000,
        "negative_marks_milli": 500,
        "answer_key_json": json.dumps(
            {"correct_option_ids": ["A", "D"], "accepted_answers": []}
        ),
    }

    exact = _deterministic_score({
        **base,
        "response_json": json.dumps({"selected_option_ids": ["D", "A"]}),
    })
    assert exact["status"] == "auto_confirmed"
    assert exact["outcome"] == "correct"
    assert exact["awarded_marks_milli"] == 2000

    non_exact = _deterministic_score({
        **base,
        "response_json": json.dumps({"selected_option_ids": ["A"]}),
    })
    assert non_exact["status"] == "awaiting_review"
    assert non_exact["awarded_marks_milli"] is None
    assert (
        non_exact["details"]["reason"]
        == "custom_scoring_requires_manual_review_for_non_exact_response"
    )


def test_deterministic_evaluation_is_idempotent_and_creates_signed_canonical_attempts(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    first = service.create(session_id)
    second = service.create(session_id)
    assert first == second

    connection = sqlite3.connect(path)
    try:
        attempts = connection.execute(
            "SELECT q.id, a.outcome, a.earned_marks_milli, a.signed_score_milli, "
            "a.evaluation_ref FROM question_attempts a "
            "JOIN questions q ON q.id=a.question_id "
            "ORDER BY q.ordinal"
        ).fetchall()
        assert len(attempts) == 7
        q2 = next(row for row in attempts if row[0] == "q2")
        assert q2[1] == "incorrect"
        assert q2[2] == 0
        assert q2[3] == -1000
        assert q2[4].startswith("assessment_response_evaluation:")

        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_evaluation_events "
            "WHERE session_evaluation_id=? AND event_type='evaluation_created'",
            (first,),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_alex_subjective_grade_is_always_provisional_until_explicit_confirmation(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    service.create(session_id)
    result = service.results(session_id)
    q7 = next(q for q in result["questions"] if q["question_number"] == "7")

    service.save_manual_evaluation(
        q7["evaluation_id"],
        {
            "evaluator_type": "alex_ai",
            "evaluator_model": "GPT-test",
            "awarded_marks": "4",
            "confidence": "0.82",
            "feedback_text": "Good method; expand the triangular solve explanation.",
            "confirm_final": True,
        },
    )
    provisional = service.results(session_id)
    q7p = next(q for q in provisional["questions"] if q["question_number"] == "7")
    assert q7p["status"] == "provisional"
    assert q7p["awarded_marks_milli"] == 4000
    assert provisional["provisional_count"] == 1

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM question_attempts WHERE question_id='q7'"
        ).fetchone()[0] == 0
    finally:
        connection.close()

    service.confirm_provisional(q7["evaluation_id"])
    confirmed = service.results(session_id)
    q7c = next(q for q in confirmed["questions"] if q["question_number"] == "7")
    assert q7c["status"] == "confirmed"

    connection = sqlite3.connect(path)
    try:
        attempt = connection.execute(
            "SELECT earned_marks_milli, signed_score_milli "
            "FROM question_attempts WHERE question_id='q7'"
        ).fetchone()
        assert attempt == (4000, 4000)
    finally:
        connection.close()


def test_manual_subjective_grade_can_finalize_session_and_preserves_no_mastery_mutation(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    service.create(session_id)
    result = service.results(session_id)
    q7 = next(q for q in result["questions"] if q["question_number"] == "7")

    service.save_manual_evaluation(
        q7["evaluation_id"],
        {
            "evaluator_type": "user",
            "evaluator_model": "",
            "awarded_marks": "4",
            "confidence": "1",
            "feedback_text": "Rubric reviewed manually.",
            "confirm_final": True,
        },
    )
    final = service.results(session_id)
    assert final["evaluation_status"] == "confirmed"
    assert final["is_final"] is True
    assert final["final_score"] == "16.667"
    assert final["scored_so_far_milli"] == 16667

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0] == 8
        assert connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0] == 0
        assert connection.execute(
            "SELECT earned_points_milli FROM assessments WHERE id='assessment-d'"
        ).fetchone()[0] is None
    finally:
        connection.close()


def test_manual_score_bounds_are_enforced(tmp_path):
    from personal_learning_assistant.services.assessment_evaluation_service import (
        AssessmentEvaluationValidationError,
    )

    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    service.create(session_id)
    q7 = next(q for q in service.results(session_id)["questions"] if q["question_number"] == "7")

    with pytest.raises(AssessmentEvaluationValidationError, match="between"):
        service.save_manual_evaluation(
            q7["evaluation_id"],
            {
                "evaluator_type": "user",
                "awarded_marks": "6",
                "confidence": "",
                "feedback_text": "",
                "confirm_final": True,
            },
        )


def test_confirmed_mistake_classification_syncs_to_canonical_mistake_event(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    service.create(session_id)
    result = service.results(session_id)
    q2 = next(q for q in result["questions"] if q["question_number"] == "2")

    updated = service.classify_mistake(
        q2["evaluation_id"],
        {
            "category": "careless",
            "note": "Selected the wrong triangular factor.",
            "source_type": "user",
        },
    )
    assert updated["mistakes"][0]["status"] == "confirmed"

    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT m.category, m.mistake_text FROM mistake_events m "
            "JOIN question_attempts a ON a.id=m.attempt_id "
            "WHERE a.question_id='q2'"
        ).fetchone()
        assert row == ("careless", "Selected the wrong triangular factor.")
    finally:
        connection.close()


def test_alex_mistake_classification_stays_provisional_until_confirmed(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    service.create(session_id)
    q2 = next(q for q in service.results(session_id)["questions"] if q["question_number"] == "2")

    updated = service.classify_mistake(
        q2["evaluation_id"],
        {
            "category": "misread",
            "note": "Alex suggests the option wording may have been misread.",
            "source_type": "alex_ai",
        },
    )
    mistake = updated["mistakes"][0]
    assert mistake["status"] == "provisional"

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM mistake_events").fetchone()[0] == 0
    finally:
        connection.close()

    service.confirm_mistake(mistake["id"])
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM mistake_events").fetchone()[0] == 1
    finally:
        connection.close()


def test_active_session_cannot_be_evaluated(tmp_path):
    from personal_learning_assistant.services.assessment_evaluation_service import (
        AssessmentEvaluationConflictError,
    )

    path = _database(tmp_path)
    session_id = _runner(path).start("assessment-d", confirmed=True)["session_id"]
    with pytest.raises(AssessmentEvaluationConflictError, match="Submit"):
        _evaluation(path).create(session_id)


def _app(path):
    from personal_learning_assistant.services.assessment_evaluation_service import AssessmentEvaluationService
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    from personal_learning_assistant.ui.web import create_app

    fixed_now = lambda: datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc)
    return create_app(
        {
            "TESTING": True,
            "ASSESSMENT_RUNNER_SERVICE_FACTORY": lambda: AssessmentRunnerService(
                path, now_fn=fixed_now
            ),
            "ASSESSMENT_EVALUATION_SERVICE_FACTORY": lambda: AssessmentEvaluationService(path),
        }
    )


def test_web_evaluation_flow_shows_results_solution_and_provisional_confirmation(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    client = _app(path).test_client()

    summary = client.get(f"/assessments/sessions/{session_id}/summary")
    assert summary.status_code == 200
    assert "Evaluate / Open Results" in summary.get_data(as_text=True)

    evaluate = client.post(
        f"/assessments/sessions/{session_id}/evaluate",
        follow_redirects=False,
    )
    assert evaluate.status_code == 303
    assert "/evaluation" in evaluate.headers["Location"]

    results = client.get(evaluate.headers["Location"])
    assert results.status_code == 200
    html = results.get_data(as_text=True)
    assert "Evaluation Engine" in html
    assert "MCQ solution" in html
    assert "Correct option" in html
    assert "Grade response" in html
    assert "16.667" not in html

    service = _evaluation(path)
    q7 = next(
        q for q in service.results(session_id)["questions"]
        if q["question_number"] == "7"
    )
    review = client.get(f"/assessments/evaluations/{q7['evaluation_id']}/review")
    assert review.status_code == 200
    assert "Rubric snapshot" in review.get_data(as_text=True)

    saved = client.post(
        f"/assessments/evaluations/{q7['evaluation_id']}/review",
        data={
            "evaluator_type": "alex_ai",
            "evaluator_model": "GPT-test",
            "awarded_marks": "4",
            "confidence": "0.8",
            "feedback_text": "Provisional Alex feedback",
            "confirm_final": "1",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303

    provisional_html = client.get(saved.headers["Location"]).get_data(as_text=True)
    assert "Provisional" in provisional_html
    assert "Confirm provisional grade" in provisional_html


def test_get_results_is_read_only_for_attempt_progress_and_planner_counts(tmp_path):
    path = _database(tmp_path)
    session_id = _submitted_session(path)
    service = _evaluation(path)
    service.create(session_id)

    connection = sqlite3.connect(path)
    try:
        before = {
            "attempts": connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0],
            "mistakes": connection.execute("SELECT COUNT(*) FROM mistake_events").fetchone()[0],
            "progress": connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0],
            "plans": connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0],
        }
    finally:
        connection.close()

    service.results(session_id)
    service.results(session_id)

    connection = sqlite3.connect(path)
    try:
        after = {
            "attempts": connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0],
            "mistakes": connection.execute("SELECT COUNT(*) FROM mistake_events").fetchone()[0],
            "progress": connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0],
            "plans": connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0],
        }
    finally:
        connection.close()
    assert after == before


def test_phase_d_contract_documents_signed_partial_and_human_confirmation():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "ASSESSMENT_STUDIO_PHASE_D.md").read_text(encoding="utf-8")
    assert "signed" in spec.lower()
    assert "proportional" in spec.lower()
    assert "Alex/ChatGPT" in spec
    assert "provisional" in spec
    assert "does not change topic mastery" in spec
