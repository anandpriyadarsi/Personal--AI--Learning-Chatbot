from __future__ import annotations

import sqlite3
from pathlib import Path


NOW = "2026-09-27T00:00:00Z"


def _database(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

    path = tmp_path / "learning_assistant.db"
    assert apply_migrations(path) == tuple(range(1, 13))
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

        assessments = [
            ("a1", "Previous Paper 1", "previous_paper", "p1", "reproduced_paper"),
            ("a2", "Generated Practice", "quiz", "p2", "generated_practice"),
            ("a3", "Provisional Subjective", "quiz", "p3", "generated_practice"),
        ]
        for assessment_id, title, assessment_type, package_id, purpose in assessments:
            connection.execute(
                "INSERT INTO assessments "
                "(id, course_id, assessment_type, title, due_on, due_time, status, "
                "weight_bps, max_points_milli, earned_points_milli, description, "
                "created_at, updated_at, deleted_at) "
                "VALUES (?, 'course-ma', ?, ?, NULL, NULL, 'pending', NULL, "
                "4000, NULL, '', ?, ?, NULL)",
                (assessment_id, assessment_type, title, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO assessment_runtime_specs "
                "(assessment_id, mode, duration_minutes, instructions_text, origin, "
                "package_id, package_revision, created_at, updated_at) "
                "VALUES (?, 'exam', 30, '', 'external_package', ?, 1, ?, ?)",
                (assessment_id, package_id, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO assessment_import_batches "
                "(id, package_id, package_revision, package_schema, package_version, "
                "source_filename, source_sha256, course_id, title, assessment_type, "
                "mode, duration_minutes, total_marks_milli, instructions_text, "
                "authoring_engine, authoring_model, authoring_purpose, status, "
                "package_json, validation_notes_json, revision, assessment_id, "
                "created_at, updated_at, approved_at, rejected_at) "
                "VALUES (?, ?, 1, 'anvaya.assessment-package', 1, '', ?, 'course-ma', "
                "?, ?, 'exam', 30, 4000, '', 'ChatGPT/Alex', 'test', ?, "
                "'approved', '{}', '[]', 1, ?, ?, ?, ?, NULL)",
                (
                    "batch-" + assessment_id,
                    package_id,
                    "a" * 64,
                    title,
                    assessment_type,
                    purpose,
                    assessment_id,
                    NOW,
                    NOW,
                    NOW,
                ),
            )

        questions = [
            ("q1", "a1", 1, "Historical LU", 2000),
            ("q2", "a1", 2, "Historical Rank", 2000),
            ("q3", "a2", 1, "Practice LU", 2000),
            ("q4", "a2", 2, "Practice Rank", 2000),
            ("q5", "a3", 1, "Provisional LU", 2000),
        ]
        for qid, aid, ordinal, text, marks in questions:
            connection.execute(
                "INSERT INTO questions "
                "(id, assessment_id, ordinal, question_text, max_marks_milli, "
                "status, user_notes, import_batch_id, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, 'not_started', '', NULL, ?, ?, NULL)",
                (qid, aid, ordinal, text, marks, NOW, NOW),
            )

        sessions = [
            ("s1", "a1", "Previous Paper 1", 2, 4000, "2026-09-20T10:00:00Z", "2026-09-20T10:30:00Z"),
            ("s2", "a2", "Generated Practice", 2, 4000, "2026-09-24T10:00:00Z", "2026-09-24T10:30:00Z"),
            ("s3", "a3", "Provisional Subjective", 1, 2000, "2026-09-26T10:00:00Z", "2026-09-26T10:30:00Z"),
        ]
        for sid, aid, title, count, max_marks, started, submitted in sessions:
            connection.execute(
                "INSERT INTO assessment_test_sessions "
                "(id, assessment_id, status, mode, title_snapshot, "
                "course_code_snapshot, course_name_snapshot, instructions_snapshot, "
                "duration_seconds, question_count, max_marks_milli, started_at, "
                "expires_at, submitted_at, submission_reason, current_ordinal, "
                "revision, created_at, updated_at) "
                "VALUES (?, ?, 'submitted', 'exam', ?, 'MA103N', 'Linear Algebra', '', "
                "1800, ?, ?, ?, ?, ?, 'user', 1, 1, ?, ?)",
                (
                    sid,
                    aid,
                    title,
                    count,
                    max_marks,
                    started,
                    submitted,
                    submitted,
                    started,
                    submitted,
                ),
            )

        snapshots = [
            ("sq1", "s1", "q1", 1, "1", "mcq", 2000, "topic-lu", "Systems", "Factorization", "medium", 180, 1000, "partially_correct", "confirmed", 1.0),
            ("sq2", "s1", "q2", 2, "2", "mcq", 2000, "topic-rank", "Systems", "Rank classification", "hard", 60, 2000, "correct", "auto_confirmed", 1.0),
            ("sq3", "s2", "q3", 1, "1", "mcq", 2000, "topic-lu", "Systems", "Factorization", "medium", 240, -500, "incorrect", "auto_confirmed", 1.0),
            ("sq4", "s2", "q4", 2, "2", "long_subjective", 2000, "topic-rank", "Systems", "Rank classification", "hard", 120, 1000, "partially_correct", "confirmed", 0.8),
            ("sq5", "s3", "q5", 1, "1", "long_subjective", 2000, "topic-lu", "Systems", "Factorization", "hard", 300, 1500, "partially_correct", "provisional", 0.7),
        ]

        for (
            sqid, sid, qid, ordinal, number, qtype, marks, topic_id,
            chapter, subtopic, difficulty, focus, awarded, outcome, eval_status, confidence
        ) in snapshots:
            connection.execute(
                "INSERT INTO assessment_test_session_questions "
                "(id, session_id, question_id, ordinal, question_number, "
                "section_label, question_type, question_text, max_marks_milli, "
                "negative_marks_milli, scoring_policy, topic_id, chapter_label, "
                "subtopic_label, concepts_json, difficulty, expected_method, "
                "options_json, answer_key_json, solution_text, rubric_text, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'A', ?, ?, ?, 500, 'standard', ?, ?, ?, "
                "'["linear algebra"]', ?, 'Use intended method', '[]', '{}', '', '', ?)",
                (
                    sqid,
                    sid,
                    qid,
                    ordinal,
                    number,
                    qtype,
                    "Snapshot " + qid,
                    marks,
                    topic_id,
                    chapter,
                    subtopic,
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

        for sid, status in [("s1", "confirmed"), ("s2", "confirmed"), ("s3", "provisional")]:
            connection.execute(
                "INSERT INTO assessment_session_evaluations "
                "(id, session_id, status, engine_version, created_at, updated_at, confirmed_at) "
                "VALUES (?, ?, ?, 'assessment-evaluation-v1', ?, ?, ?)",
                (
                    "se-" + sid,
                    sid,
                    status,
                    NOW,
                    NOW,
                    NOW if status == "confirmed" else None,
                ),
            )

        for (
            sqid, sid, qid, marks, awarded, outcome, eval_status, confidence
        ) in [
            ("sq1", "s1", "q1", 2000, 1000, "partially_correct", "confirmed", 1.0),
            ("sq2", "s1", "q2", 2000, 2000, "correct", "auto_confirmed", 1.0),
            ("sq3", "s2", "q3", 2000, -500, "incorrect", "auto_confirmed", 1.0),
            ("sq4", "s2", "q4", 2000, 1000, "partially_correct", "confirmed", 0.8),
            ("sq5", "s3", "q5", 2000, 1500, "partially_correct", "provisional", 0.7),
        ]:
            connection.execute(
                "INSERT INTO assessment_response_evaluations "
                "(id, session_evaluation_id, session_question_id, question_id, "
                "response_id, evaluator_type, evaluator_model, status, outcome, "
                "awarded_marks_milli, max_marks_milli, penalty_marks_milli, "
                "scoring_policy, rubric_version, confidence, feedback_text, "
                "details_json, question_attempt_id, created_at, updated_at, confirmed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, 'standard', '', ?, '', "
                "'{}', NULL, ?, ?, ?)",
                (
                    "ev-" + sqid,
                    "se-" + sid,
                    sqid,
                    qid,
                    "r-" + sqid,
                    "alex_ai" if eval_status == "provisional" else "deterministic",
                    eval_status,
                    outcome,
                    awarded,
                    marks,
                    max(0, -awarded),
                    confidence,
                    NOW,
                    NOW,
                    NOW if eval_status in {"confirmed", "auto_confirmed"} else None,
                ),
            )

        for mid, evid, category, note in [
            ("m1", "ev-sq1", "concept_gap", "LU setup misunderstanding."),
            ("m2", "ev-sq3", "careless", "Incorrect option selected."),
        ]:
            connection.execute(
                "INSERT INTO assessment_evaluation_mistakes "
                "(id, response_evaluation_id, category, note, source_type, status, "
                "mistake_event_id, created_at, confirmed_at) "
                "VALUES (?, ?, ?, ?, 'user', 'confirmed', NULL, ?, ?)",
                (mid, evid, category, note, NOW, NOW),
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _service(path):
    from personal_learning_assistant.services.assessment_intelligence_service import (
        AssessmentIntelligenceService,
    )
    return AssessmentIntelligenceService(path)


def test_phase_e_uses_no_new_migration_and_existing_schema_remains_0012(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        versions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        assert versions == tuple(range(1, 13))
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_overview_uses_confirmed_sessions_only_and_confidence_weighting(tmp_path):
    report = _service(_database(tmp_path)).overview()

    assert report["confirmed_session_count"] == 2
    assert report["course_count"] == 1
    assert report["overall"]["question_count"] == 4
    assert report["overall"]["signed_score_milli"] == 3500
    assert report["overall"]["performance_percent"] == 43.8
    assert report["overall"]["weighted_performance_percent"] == 43.4
    assert report["overall"]["full_accuracy_percent"] == 25.0
    assert report["overall"]["focus_seconds"] == 600

    assert len(report["recent_trend"]) == 2
    assert report["recent_trend"][0]["title"] == "Generated Practice"
    assert report["recent_trend"][0]["performance_percent"] == 12.5
    assert report["recent_trend"][1]["performance_percent"] == 75.0


def test_course_topic_heatmap_time_and_recovery_order_are_transparent(tmp_path):
    report = _service(_database(tmp_path)).course_report("course-ma")
    by_topic = {item["label"]: item for item in report["topics"]}

    lu = by_topic["LU Factorization"]
    rank = by_topic["Matrix Rank"]

    assert lu["question_count"] == 2
    assert lu["weighted_performance_percent"] == 12.5
    assert lu["time_per_available_mark_seconds"] == 105.0
    assert lu["mistake_count"] == 2
    assert lu["band"] == "needs_review"

    assert rank["weighted_performance_percent"] == 77.8
    assert rank["time_per_available_mark_seconds"] == 45.0
    assert report["median_time_per_mark_seconds"] == 75.0

    assert report["recovery_topics"][0]["label"] == "LU Factorization"
    assert report["recovery_topics"][0]["recovery_order"] == 1
    assert "repeated confirmed mistake classifications" in report["recovery_topics"][0]["recovery_signals"]
    assert report["recovery_topics"][0]["slower_than_course_median"] is True

    assert {item["chapter"] for item in report["heatmap"]} == {"Systems"}
    assert len(report["heatmap"]) == 2


def test_difficulty_question_type_and_mistake_patterns_are_confirmed_evidence(tmp_path):
    report = _service(_database(tmp_path)).course_report("course-ma")

    difficulties = {item["label"]: item for item in report["difficulties"]}
    assert difficulties["Medium"]["question_count"] == 2
    assert difficulties["Hard"]["question_count"] == 2

    qtypes = {item["label"]: item for item in report["question_types"]}
    assert qtypes["Mcq"]["question_count"] == 3
    assert qtypes["Long Subjective"]["question_count"] == 1

    patterns = {item["category"]: item for item in report["mistake_patterns"]}
    assert patterns["concept_gap"]["count"] == 1
    assert patterns["careless"]["count"] == 1


def test_historical_previous_paper_statistics_are_descriptive_not_predictive(tmp_path):
    report = _service(_database(tmp_path)).course_report("course-ma")
    historical = report["historical"]

    assert historical["session_count"] == 1
    assert historical["question_count"] == 2
    shares = {item["label"]: item["share_percent"] for item in historical["topics"]}
    assert shares == {"LU Factorization": 50.0, "Matrix Rank": 50.0}
    assert "not a forecast" in historical["note"]


def test_session_analysis_can_show_preliminary_but_cross_test_excludes_it(tmp_path):
    path = _database(tmp_path)
    service = _service(path)

    provisional = service.session_analysis("s3")
    assert provisional["is_final"] is False
    assert provisional["confirmed_question_count"] == 0
    assert provisional["provisional_count"] == 1
    assert provisional["overall"]["question_count"] == 0

    course = service.course_report("course-ma")
    assert len(course["trend"]) == 2
    assert all(item["session_id"] != "s3" for item in course["trend"])


def test_weak_topics_order_is_observed_evidence_not_mastery(tmp_path):
    report = _service(_database(tmp_path)).weak_topics()

    assert report["has_evidence"] is True
    assert report["topics"][0]["label"] == "LU Factorization"
    assert report["topics"][0]["course_code"] == "MA103N"
    assert report["topics"][0]["recovery_order"] == 1
    assert report["topics"][0]["mistake_count"] == 2
    assert "not a mastery score" in report["note"]


def _app(path):
    from personal_learning_assistant.services.assessment_intelligence_service import (
        AssessmentIntelligenceService,
    )
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "ASSESSMENT_INTELLIGENCE_SERVICE_FACTORY": lambda: AssessmentIntelligenceService(path),
        }
    )


def test_web_reports_activate_visuals_heatmap_tables_and_session_links(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()

    overview = client.get("/assessments/reports")
    assert overview.status_code == 200
    html = overview.get_data(as_text=True)
    assert "Assessment Intelligence" in html
    assert "Performance by course" in html
    assert "Accessible evidence table" in html
    assert "Historical coverage only" in html

    course = client.get("/assessments/reports/courses/course-ma")
    assert course.status_code == 200
    course_html = course.get_data(as_text=True)
    assert "Performance heatmap" in course_html
    assert "Heatmap data table" in course_html
    assert "Difficulty vs performance" in course_html
    assert "Topic time-per-mark" in course_html
    assert "Observed reproduced-paper coverage" in course_html

    session = client.get("/assessments/sessions/s1/analysis")
    assert session.status_code == 200
    session_html = session.get_data(as_text=True)
    assert "Session" in session_html
    assert "Question evidence" in session_html
    assert "LU Factorization" in session_html

    weak = client.get("/assessments/weak-topics")
    assert weak.status_code == 200
    weak_html = weak.get_data(as_text=True)
    assert "Topics to inspect first" in weak_html
    assert "Recovery evidence table" in weak_html


def test_phase_e_get_routes_are_nonmutating(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()

    connection = sqlite3.connect(path)
    try:
        before = {
            "progress": connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0],
            "plans": connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0],
            "attempts": connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0],
            "mistakes": connection.execute("SELECT COUNT(*) FROM mistake_events").fetchone()[0],
            "eval_events": connection.execute("SELECT COUNT(*) FROM assessment_evaluation_events").fetchone()[0],
        }
    finally:
        connection.close()

    for url in [
        "/assessments/reports",
        "/assessments/reports/courses/course-ma",
        "/assessments/sessions/s1/analysis",
        "/assessments/weak-topics",
    ]:
        assert client.get(url).status_code == 200
        assert client.get(url).status_code == 200

    connection = sqlite3.connect(path)
    try:
        after = {
            "progress": connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0],
            "plans": connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0],
            "attempts": connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0],
            "mistakes": connection.execute("SELECT COUNT(*) FROM mistake_events").fetchone()[0],
            "eval_events": connection.execute("SELECT COUNT(*) FROM assessment_evaluation_events").fetchone()[0],
        }
    finally:
        connection.close()

    assert after == before


def test_phase_e_contract_documents_confirmed_only_accessibility_and_no_prediction():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "ASSESSMENT_STUDIO_PHASE_E.md").read_text(encoding="utf-8")

    assert "confirmed" in spec.lower()
    assert "table equivalent" in spec.lower()
    assert "not a forecast" in spec.lower()
    assert "does not change topic mastery" in spec.lower()
    assert "confidence-weighted" in spec.lower()
