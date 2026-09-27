from __future__ import annotations

import io
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
        courses = [
            ("course-ma", "MA103N", "Linear Algebra"),
            ("course-cy", "CY100N", "Engineering Chemistry"),
        ]
        connection.executemany(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            [(cid, code, name, NOW, NOW) for cid, code, name in courses],
        )
        connection.executemany(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, 'course-ma', ?, ?, ?, 'not_started', ?, ?)",
            [
                ("topic-inverse", "Matrix Inverse", "matrix inverse", 1, NOW, NOW),
                ("topic-lu", "LU Factorization", "lu factorization", 2, NOW, NOW),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _example_bytes():
    root = Path(__file__).resolve().parents[1]
    return (root / "examples/anvaya_assessment_package_v1.example.json").read_bytes()


def _service(path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
    )

    return AssessmentPackageService(path)


def _app(path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
    )
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "ASSESSMENT_PACKAGE_SERVICE_FACTORY": lambda: AssessmentPackageService(path),
        }
    )


def test_migration_0014_adds_authoring_preferences_and_workspace_kind(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "assessment_authoring_preferences" in tables
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(assessment_import_batches)"
            )
        }
        assert "workspace_kind" in columns
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_workspace_exposes_three_kinds_live_courses_and_personalized_master_prompt(tmp_path):
    workspace = _service(_database(tmp_path)).workspace(
        workspace_kind="quiz",
        course_id="course-ma",
    )

    assert [item["id"] for item in workspace["workspace_kinds"]] == [
        "quiz",
        "exam",
        "test",
    ]
    assert [item["code"] for item in workspace["courses"]] == ["CY100N", "MA103N"]
    assert workspace["selected_course"]["code"] == "MA103N"
    assert workspace["selected_kind"] == "quiz"
    assert "**Workspace kind:** Quiz" in workspace["resolved_prompt"]
    assert "**ANVAYA course code:** MA103N" in workspace["resolved_prompt"]
    assert "{{COURSE_CODE}}" in workspace["master_prompt"]
    assert "{{COURSE_CODE}}" not in workspace["resolved_prompt"]


def test_master_prompt_edit_persists_and_reset_restores_repository_default(tmp_path):
    path = _database(tmp_path)
    service = _service(path)

    service.save_master_prompt(
        "CUSTOM {{ASSESSMENT_KIND}} {{COURSE_CODE}} {{COURSE_NAME}}"
    )
    custom = service.workspace(workspace_kind="exam", course_id="course-ma")
    assert custom["prompt_is_custom"] is True
    assert custom["resolved_prompt"] == "CUSTOM Exam MA103N Linear Algebra"
    assert custom["prompt_revision"] == 1

    service.save_master_prompt(
        "CUSTOM V2 {{ASSESSMENT_KIND}} {{COURSE_CODE}}"
    )
    updated = service.workspace(workspace_kind="test", course_id="course-ma")
    assert updated["prompt_revision"] == 2
    assert updated["resolved_prompt"] == "CUSTOM V2 Test MA103N"

    service.reset_master_prompt()
    reset = service.workspace(workspace_kind="quiz", course_id="course-ma")
    assert reset["prompt_is_custom"] is False
    assert "ANVAYA Assessment Package" in reset["master_prompt"]
    assert "MA103N" in reset["resolved_prompt"]


def test_stage_upload_persists_user_kind_and_rejects_wrong_selected_subject(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageValidationError,
    )

    path = _database(tmp_path)
    service = _service(path)

    staged = service.stage_upload(
        "ma103n.anvaya-assessment.json",
        _example_bytes(),
        workspace_kind="quiz",
        selected_course_id="course-ma",
    )
    assert staged["workspace_kind"] == "quiz"

    workspace = service.workspace(workspace_kind="quiz", course_id="course-ma")
    assert len(workspace["batches"]) == 1
    assert workspace["batches"][0]["workspace_kind_label"] == "Quiz"
    assert workspace["batches"][0]["course_code"] == "MA103N"

    other_path = tmp_path / "other"
    other_path.mkdir()
    mismatch_db = _database(other_path)
    mismatch = _service(mismatch_db)
    with pytest.raises(AssessmentPackageValidationError, match="does not match package course code"):
        mismatch.stage_upload(
            "ma103n.anvaya-assessment.json",
            _example_bytes(),
            workspace_kind="exam",
            selected_course_id="course-cy",
        )


def test_authoring_page_is_alex_first_compact_and_notes_style_card_driven(tmp_path):
    client = _app(_database(tmp_path)).test_client()
    response = client.get("/assessments/import?kind=quiz&course_id=course-ma")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Create assessments with Alex" in html
    assert 'href="https://chatgpt.com/"' in html
    assert "Open Alex / ChatGPT" in html
    assert "Master Prompt" in html
    assert "Copy prompt" in html
    assert "Edit prompt" in html
    assert "Quiz" in html and "Exam" in html and "Test" in html
    assert "MA103N" in html
    assert "Linear Algebra" in html
    assert "Engineering Chemistry" in html
    assert "Validate &amp; open review" in html
    assert 'name="workspace_kind"' in html
    assert 'name="course_id"' in html
    assert "assessment-prompt-dialog" in html
    assert "assessment-kind-card" in html
    assert "assessment-course-card" in html


def test_web_upload_saves_kind_subject_and_history_automatically(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()

    response = client.post(
        "/assessments/import",
        data={
            "workspace_kind": "quiz",
            "course_id": "course-ma",
            "package": (
                io.BytesIO(_example_bytes()),
                "MA103N_quiz.anvaya-assessment.json",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/review" in response.headers["Location"]

    history = client.get("/assessments/import?kind=quiz&course_id=course-ma")
    assert history.status_code == 200
    html = history.get_data(as_text=True)
    assert "Quiz · MA103N history" in html
    assert "Linear Algebra Practice Quiz" in html
    assert "MA103N_quiz.anvaya-assessment.json" in html
    assert "Review" in html


def test_prompt_save_route_is_prg_and_get_page_remains_read_only(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()

    saved = client.post(
        "/assessments/import/prompt",
        data={
            "workspace_kind": "test",
            "course_id": "course-ma",
            "master_prompt": "MY PROMPT {{COURSE_CODE}} {{ASSESSMENT_KIND}}",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert "prompt_saved=1" in saved.headers["Location"]

    page = client.get(saved.headers["Location"])
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "MY PROMPT MA103N Test" in html

    connection = sqlite3.connect(path)
    try:
        before = connection.execute(
            "SELECT revision FROM assessment_authoring_preferences WHERE id='default'"
        ).fetchone()[0]
        batch_count = connection.execute(
            "SELECT COUNT(*) FROM assessment_import_batches"
        ).fetchone()[0]
    finally:
        connection.close()

    client.get("/assessments/import?kind=test&course_id=course-ma")
    client.get("/assessments/import?kind=test&course_id=course-ma")

    connection = sqlite3.connect(path)
    try:
        after = connection.execute(
            "SELECT revision FROM assessment_authoring_preferences WHERE id='default'"
        ).fetchone()[0]
        after_batches = connection.execute(
            "SELECT COUNT(*) FROM assessment_import_batches"
        ).fetchone()[0]
    finally:
        connection.close()

    assert after == before
    assert after_batches == batch_count == 0


def test_master_prompt_contract_contains_context_and_strict_package_requirements():
    root = Path(__file__).resolve().parents[1]
    prompt = (root / "ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md").read_text(
        encoding="utf-8"
    )

    assert "{{ASSESSMENT_KIND}}" in prompt
    assert "{{COURSE_CODE}}" in prompt
    assert "{{COURSE_NAME}}" in prompt
    assert "anvaya.assessment-package" in prompt
    assert "mcq" in prompt
    assert "msq" in prompt
    assert "review_required" in prompt
    assert "Do not globally assume JEE Advanced" in prompt or "Do not assume one global JEE Advanced" in prompt
