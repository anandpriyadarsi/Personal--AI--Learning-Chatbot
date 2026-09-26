from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


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
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            ("course-ma", "MA103N", "Linear Algebra", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            ("course-ds", "UC100N", "Data Science and AI", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, 'not_started', ?, ?)",
            ("topic-lu", "course-ma", "LU Factorization", "lu factorization", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, 'not_started', ?, ?)",
            ("topic-pandas", "course-ds", "Pandas", "pandas", NOW, NOW),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _payload(**overrides):
    payload = {
        "course_id": "course-ma",
        "name": "Mid-Sem Practice",
        "assessment_type": "midsem",
        "mode": "exam",
        "duration_minutes": "60",
        "total_marks": "30",
        "description": "Practice under exam conditions.",
        "instructions": "No hints during the attempt.",
        "topic_ids": ["topic-lu"],
        "pattern_types": ["mcq", "msq", "long_subjective"],
        "pattern_counts": ["4", "2", "2"],
        "pattern_marks": ["1", "2", "11"],
        "pattern_negative_marks": ["0.25", "0.5", "0"],
        "pattern_scoring_policies": ["standard", "partial", "standard"],
    }
    payload.update(overrides)
    return payload


def test_migration_0009_adds_normalized_template_schema_with_integrity(tmp_path):
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
            "assessment_templates",
            "assessment_template_topics",
            "assessment_template_patterns",
        }.issubset(tables)
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_create_read_update_and_lifecycle_are_normalized_and_revision_safe(tmp_path):
    from personal_learning_assistant.services.assessment_studio_service import (
        AssessmentStudioConflictError,
        AssessmentStudioService,
    )

    service = AssessmentStudioService(_database(tmp_path))
    created = service.create_template(_payload())
    assert created["course_code"] == "MA103N"
    assert created["name"] == "Mid-Sem Practice"
    assert created["revision"] == 1
    assert created["active"] is True
    assert [item["name"] for item in created["topics"]] == ["LU Factorization"]
    assert [item["question_type"] for item in created["patterns"]] == [
        "mcq",
        "msq",
        "long_subjective",
    ]

    changed = service.update_template(
        created["id"],
        _payload(name="Mid-Sem Practice v2", revision="1", duration_minutes="75"),
    )
    assert changed["revision"] == 2
    assert changed["duration_minutes"] == 75

    with pytest.raises(AssessmentStudioConflictError):
        service.update_template(created["id"], _payload(revision="1"))

    inactive = service.set_active(
        created["id"], revision=changed["revision"], active=False
    )
    assert inactive["active"] is False
    assert inactive["revision"] == 3

    active = service.set_active(
        created["id"], revision=inactive["revision"], active=True
    )
    assert active["active"] is True
    assert active["revision"] == 4


def test_cross_course_topic_and_duplicate_name_are_rejected_atomically(tmp_path):
    from personal_learning_assistant.services.assessment_studio_service import (
        AssessmentStudioConflictError,
        AssessmentStudioService,
        AssessmentStudioValidationError,
    )

    path = _database(tmp_path)
    service = AssessmentStudioService(path)

    with pytest.raises(AssessmentStudioValidationError):
        service.create_template(_payload(topic_ids=["topic-pandas"]))

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_templates"
        ).fetchone()[0] == 0
    finally:
        connection.close()

    service.create_template(_payload())
    with pytest.raises(AssessmentStudioConflictError):
        service.create_template(_payload(name="mid-sem practice"))


def test_invalid_duration_negative_marks_and_empty_patterns_are_rejected(tmp_path):
    from personal_learning_assistant.services.assessment_studio_service import (
        AssessmentStudioService,
        AssessmentStudioValidationError,
    )

    service = AssessmentStudioService(_database(tmp_path))
    with pytest.raises(AssessmentStudioValidationError):
        service.create_template(_payload(duration_minutes="0"))
    with pytest.raises(AssessmentStudioValidationError):
        service.create_template(
            _payload(
                pattern_marks=["1"],
                pattern_negative_marks=["2"],
                pattern_counts=["1"],
                pattern_types=["mcq"],
                pattern_scoring_policies=["standard"],
            )
        )
    with pytest.raises(AssessmentStudioValidationError):
        service.create_template(
            _payload(
                pattern_marks=[],
                pattern_negative_marks=[],
                pattern_counts=[],
                pattern_types=[],
                pattern_scoring_policies=[],
            )
        )


def test_get_read_models_do_not_mutate_database(tmp_path):
    from personal_learning_assistant.services.assessment_studio_service import (
        AssessmentStudioService,
    )

    path = _database(tmp_path)
    service = AssessmentStudioService(path)
    created = service.create_template(_payload())

    connection = sqlite3.connect(path)
    try:
        counts_before = {
            table: connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in (
                "assessment_templates",
                "assessment_template_topics",
                "assessment_template_patterns",
                "question_attempts",
                "topic_progress_events",
                "study_plan_items",
            )
        }
    finally:
        connection.close()

    service.overview()
    service.list_templates()
    service.course_workspace("course-ma")
    service.template_detail(created["id"])
    service.form_context(course_id="course-ma", preset="quiz")

    connection = sqlite3.connect(path)
    try:
        counts_after = {
            table: connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in counts_before
        }
    finally:
        connection.close()
    assert counts_after == counts_before


def test_read_service_never_creates_missing_database(tmp_path):
    from personal_learning_assistant.services.assessment_studio_service import (
        AssessmentStudioService,
        AssessmentStudioUnavailableError,
    )

    path = tmp_path / "missing.db"
    with pytest.raises(AssessmentStudioUnavailableError):
        AssessmentStudioService(path).overview()
    assert not path.exists()


def _empty_catalogue():
    return {
        "available": True,
        "message": "",
        "date": "2026-09-27",
        "summary": {"total": 0, "active": 0, "overdue": 0, "completed": 0},
        "groups": {"overdue": [], "upcoming": [], "completed": []},
    }


def _app(path):
    from personal_learning_assistant.services.assessment_studio_service import (
        AssessmentStudioService,
    )
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "ASSESSMENT_CATALOGUE_PROVIDER": _empty_catalogue,
            "ASSESSMENT_STUDIO_SERVICE_FACTORY": lambda: AssessmentStudioService(path),
        }
    )


def test_web_overview_templates_course_and_prg_commands(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()

    overview = client.get("/assessments")
    assert overview.status_code == 200
    text = overview.get_data(as_text=True)
    assert "Assessment Studio" in text
    assert "Assessment timeline" in text
    assert "<form" not in text.lower()
    assert client.post("/assessments").status_code == 405

    course = client.get("/assessments/courses/course-ma")
    assert course.status_code == 200
    assert "Quiz Practice" in course.get_data(as_text=True)

    new_form = client.get(
        "/assessments/templates/new?course_id=course-ma&preset=midsem"
    )
    assert new_form.status_code == 200
    assert "Mid-Sem Practice" in new_form.get_data(as_text=True)

    response = client.post(
        "/assessments/templates",
        data={
            "course_id": "course-ma",
            "name": "Quiz Pattern",
            "assessment_type": "quiz",
            "mode": "exam",
            "duration_minutes": "30",
            "total_marks": "10",
            "description": "",
            "instructions": "",
            "topic_ids": ["topic-lu"],
            "pattern_type": ["mcq", "mcq", "mcq", "mcq"],
            "pattern_count": ["10", "", "", ""],
            "pattern_marks": ["1", "", "", ""],
            "pattern_negative_marks": ["0.25", "0", "0", "0"],
            "pattern_scoring_policy": ["standard", "standard", "standard", "standard"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/assessments/templates/" in response.headers["Location"]

    detail = client.get(response.headers["Location"])
    assert detail.status_code == 200
    detail_text = detail.get_data(as_text=True)
    assert "Quiz Pattern" in detail_text
    assert "MCQ" in detail_text


def test_web_invalid_template_returns_400_without_partial_write(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()
    response = client.post(
        "/assessments/templates",
        data={
            "course_id": "course-ma",
            "name": "Broken",
            "assessment_type": "quiz",
            "mode": "exam",
            "duration_minutes": "0",
            "pattern_type": ["mcq"],
            "pattern_count": ["1"],
            "pattern_marks": ["1"],
            "pattern_negative_marks": ["0"],
            "pattern_scoring_policy": ["standard"],
        },
    )
    assert response.status_code == 400
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_templates"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_phase_a_source_reserves_alex_package_and_jee_style_future_contract():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "ASSESSMENT_STUDIO_PHASE_A.md").read_text(encoding="utf-8")
    assert "*.anvaya-assessment.json" in spec
    assert "Alex/ChatGPT" in spec
    assert "single-select radio" in spec
    assert "multi-select checkbox" in spec
    assert "Marked for Review" in spec
    assert "Exam mode and practice mode" in spec
