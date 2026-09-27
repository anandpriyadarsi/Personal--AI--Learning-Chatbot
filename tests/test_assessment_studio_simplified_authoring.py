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
        connection.executemany(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            [
                ("course-ma", "MA103N", "Linear Algebra", NOW, NOW),
                ("course-cy", "CY100N", "Engineering Chemistry", NOW, NOW),
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


def test_subject_picker_reuses_notes_studio_card_style(monkeypatch, tmp_path):
    from personal_learning_assistant.ui.web import routes

    class FakeNotes:
        def library(self):
            return {
                "cards": [
                    {
                        "course": "MA103N · Linear Algebra",
                        "card_style": "iris-violet",
                    }
                ]
            }

    monkeypatch.setattr(routes, "build_anvaya_notes_service", lambda: FakeNotes())

    client = _app(_database(tmp_path)).test_client()
    page = client.get("/assessments/import?kind=quiz")
    assert page.status_code == 200
    html = page.get_data(as_text=True)

    assert "assessment-subject-picker" in html
    assert "anvaya-note-template--iris-violet" in html
    assert "MA103N" in html
    assert "Linear Algebra" in html


def test_kind_selection_uses_dialog_instead_of_inline_subject_grid(tmp_path):
    client = _app(_database(tmp_path)).test_client()

    home = client.get("/assessments/import")
    home_html = home.get_data(as_text=True)
    assert "assessment-kind-grid-simple" in home_html
    assert "assessment-subject-dialog-grid" not in home_html
    assert "assessment-course-grid" not in home_html

    quiz = client.get("/assessments/import?kind=quiz")
    quiz_html = quiz.get_data(as_text=True)
    assert "<dialog" in quiz_html
    assert 'id="assessment-subject-picker"' in quiz_html
    assert "data-auto-open-subject-picker" in quiz_html
    assert "assessment-course-grid" not in quiz_html


def test_focused_workspace_is_single_subject_and_keeps_alex_tools_floating(tmp_path):
    client = _app(_database(tmp_path)).test_client()
    page = client.get("/assessments/import?kind=quiz&course_id=course-ma")
    assert page.status_code == 200
    html = page.get_data(as_text=True)

    assert "Quiz · MA103N" in html
    assert "Linear Algebra" in html
    assert "Engineering Chemistry" not in html
    assert 'id="assessment-alex-tools-launcher"' in html
    assert 'data-position-key="anvaya.assessment.alexTools.position"' in html
    assert 'id="assessment-alex-tools-drawer"' in html
    assert "Copy personalized prompt" in html
    assert "Open Alex / ChatGPT" in html
    assert "Preview prompt" in html
    assert "Edit master prompt" in html


def test_rejected_package_can_be_deleted_from_history(tmp_path):
    path = _database(tmp_path)
    service = _service(path)
    staged = service.stage_upload(
        "ma103n-delete.anvaya-assessment.json",
        _example_bytes(),
        workspace_kind="quiz",
        selected_course_id="course-ma",
    )
    service.reject(staged["id"])

    client = _app(path).test_client()
    history = client.get("/assessments/import?kind=quiz&course_id=course-ma")
    html = history.get_data(as_text=True)
    assert "Rejected" in html
    assert "Delete" in html
    assert f'/assessments/import/{staged["id"]}/delete' in html

    deleted = client.post(
        f'/assessments/import/{staged["id"]}/delete',
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert "deleted=1" in deleted.headers["Location"]

    workspace = service.workspace(workspace_kind="quiz", course_id="course-ma")
    assert workspace["batches"] == ()


def test_non_rejected_package_cannot_be_deleted(tmp_path):
    path = _database(tmp_path)
    service = _service(path)
    staged = service.stage_upload(
        "ma103n-review.anvaya-assessment.json",
        _example_bytes(),
        workspace_kind="quiz",
        selected_course_id="course-ma",
    )

    client = _app(path).test_client()
    response = client.post(f'/assessments/import/{staged["id"]}/delete')
    assert response.status_code == 409

    workspace = service.workspace(workspace_kind="quiz", course_id="course-ma")
    assert len(workspace["batches"]) == 1


def test_history_card_uses_stretched_link_and_delete_sits_above_it():
    root = Path(__file__).resolve().parents[1]
    template = (
        root / "personal_learning_assistant/ui/web/templates/assessment_import.html"
    ).read_text(encoding="utf-8")
    css = (
        root / "personal_learning_assistant/ui/web/static/css/app.css"
    ).read_text(encoding="utf-8")

    assert 'class="assessment-history-card-link"' in template
    assert ".assessment-history-card-link" in css
    assert "position: absolute;" in css
    assert "inset: 0;" in css
    assert ".assessment-history-delete" in css
    assert "z-index: 3;" in css


def test_alex_tools_javascript_preserves_drag_position_and_subject_auto_open():
    root = Path(__file__).resolve().parents[1]
    script = (
        root / "personal_learning_assistant/ui/web/static/js/assessment_authoring.js"
    ).read_text(encoding="utf-8")

    assert "anvaya.assessment.alexTools.position" in script
    assert "pointerdown" in script
    assert "pointermove" in script
    assert "localStorage.setItem" in script
    assert "data-auto-open-subject-picker" in script
    assert "data-confirm-delete" in script
