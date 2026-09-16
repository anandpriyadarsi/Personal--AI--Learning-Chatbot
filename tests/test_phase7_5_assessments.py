from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace


def _course_result():
    return SimpleNamespace(
        courses=(
            SimpleNamespace(id="ma103n", code="MA103N", name="Linear Algebra"),
            SimpleNamespace(id="uc100n", code="UC100N", name="Data Science and AI"),
        )
    )


def _state_fixture():
    return {
        "version": 2,
        "assessments": [
            {
                "id": "1",
                "course_id": "ma103n",
                "type": "quiz",
                "title": "Quiz 1",
                "status": "pending",
                "due_date": "2026-09-16",
                "due_time": "10:00",
                "weightage_percent": 10,
                "topics": ["LU Factorization", "Rank"],
            },
            {
                "id": "2",
                "course_id": "uc100n",
                "type": "lab",
                "title": "Pandas lab",
                "status": "in_progress",
                "due_date": "2026-09-17",
                "weightage_percent": 5,
                "topics": ["Pandas"],
            },
            {
                "id": "3",
                "course_id": "ma103n",
                "type": "midsem",
                "title": "Midsem",
                "status": "pending",
                "due_date": "2026-09-25",
                "weightage_percent": 25,
                "topics": ["Matrices", "Vector Spaces"],
            },
            {
                "id": "4",
                "course_id": "uc100n",
                "type": "assignment",
                "title": "Cleaning exercise",
                "status": "completed",
                "due_date": "2026-09-14",
                "obtained_marks": 18,
                "total_marks": 20,
                "topics": [],
            },
        ],
    }


def test_assessment_catalogue_normalizes_groups_summary_and_course_identity():
    from personal_learning_assistant.services.assessment_dashboard_service import (
        build_assessment_catalogue,
    )

    catalogue = build_assessment_catalogue(
        _state_fixture(),
        _course_result(),
        today=date(2026, 9, 17),
    )

    assert catalogue["available"] is True
    assert catalogue["summary"] == {
        "total": 4,
        "active": 3,
        "overdue": 1,
        "completed": 1,
    }
    assert [item["id"] for item in catalogue["groups"]["overdue"]] == ["1"]
    assert [item["id"] for item in catalogue["groups"]["upcoming"]] == ["2", "3"]
    assert [item["id"] for item in catalogue["groups"]["completed"]] == ["4"]

    overdue = catalogue["groups"]["overdue"][0]
    assert overdue["course_code"] == "MA103N"
    assert overdue["course_name"] == "Linear Algebra"
    assert overdue["type_label"] == "Quiz"
    assert overdue["status_label"] == "Pending"
    assert overdue["due_label"] == "Overdue by 1 day"
    assert overdue["weightage_percent"] == 10.0
    assert overdue["topics"] == ["LU Factorization", "Rank"]

    today_item = catalogue["groups"]["upcoming"][0]
    assert today_item["due_label"] == "Due today"
    assert today_item["status_label"] == "In progress"


def test_assessment_catalogue_supports_legacy_aliases_unknown_course_and_missing_date():
    from personal_learning_assistant.services.assessment_dashboard_service import (
        build_assessment_catalogue,
    )

    state = {
        "assessments": [
            {
                "id": 9,
                "course_id": "missing",
                "assessment_type": "project",
                "title": "Portfolio",
                "status": "pending",
                "due_on": "",
                "weight": "12.5",
                "topics": "not-a-list",
            }
        ]
    }
    catalogue = build_assessment_catalogue(
        state,
        SimpleNamespace(courses=()),
        today=date(2026, 9, 17),
    )

    item = catalogue["groups"]["upcoming"][0]
    assert item["id"] == "9"
    assert item["course_code"] == "UNKNOWN"
    assert item["type_label"] == "Project"
    assert item["due_label"] == "Date not set"
    assert item["weightage_percent"] == 12.5
    assert item["topics"] == []


def test_completed_assessment_is_not_classified_overdue_even_when_due_date_is_past():
    from personal_learning_assistant.services.assessment_dashboard_service import (
        build_assessment_catalogue,
    )

    state = {
        "assessments": [
            {
                "id": "done",
                "course_id": "ma103n",
                "type": "quiz",
                "title": "Old quiz",
                "status": "completed",
                "due_date": "2026-09-01",
                "topics": [],
            }
        ]
    }
    catalogue = build_assessment_catalogue(
        state,
        _course_result(),
        today=date(2026, 9, 17),
    )

    assert catalogue["summary"]["overdue"] == 0
    assert catalogue["groups"]["overdue"] == []
    assert catalogue["groups"]["completed"][0]["id"] == "done"


def test_unavailable_assessment_catalogue_has_safe_empty_shape():
    from personal_learning_assistant.services.assessment_dashboard_service import (
        unavailable_assessment_catalogue,
    )

    catalogue = unavailable_assessment_catalogue()
    assert catalogue["available"] is False
    assert catalogue["groups"] == {"overdue": [], "upcoming": [], "completed": []}
    assert catalogue["summary"] == {
        "total": 0,
        "active": 0,
        "overdue": 0,
        "completed": 0,
    }
    assert "data was not changed" in catalogue["message"].lower()


def test_routes_source_declares_get_only_assessments_endpoint():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/routes.py").read_text(
        encoding="utf-8"
    )
    assert '@web_blueprint.get("/assessments")' in source
    assert 'render_template("assessments.html"' in source
    assert "ASSESSMENT_CATALOGUE_PROVIDER" in source
    assert '@web_blueprint.post("/assessments")' not in source


def test_base_navigation_exposes_assessments_as_real_link():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/templates/base.html").read_text(
        encoding="utf-8"
    )
    assert "url_for('web.assessments')" in source
    assert "active_page == 'assessments'" in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Assessments</span>' not in source


def _catalogue_fixture():
    from personal_learning_assistant.services.assessment_dashboard_service import (
        build_assessment_catalogue,
    )

    return build_assessment_catalogue(
        _state_fixture(),
        _course_result(),
        today=date(2026, 9, 17),
    )


def _web_app(provider):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "ASSESSMENT_CATALOGUE_PROVIDER": provider,
        }
    )


def test_assessments_page_renders_groups_course_type_due_weightage_status_and_topics():
    response = _web_app(_catalogue_fixture).test_client().get("/assessments")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Assessments",
        "Assessment timeline",
        "4 total",
        "1 overdue",
        "Overdue",
        "Upcoming &amp; active",
        "Completed",
        "MA103N",
        "Quiz 1",
        "Quiz",
        "Pending",
        "Overdue by 1 day",
        "10% weightage",
        "LU Factorization",
        "UC100N",
        "Pandas lab",
        "Due today",
    ):
        assert expected in text
    assert '<form' not in text.lower()
    assert 'href="/assessments"' in text


def test_assessments_provider_failure_degrades_without_leaking_exception_content():
    def failing_provider():
        raise RuntimeError("SECRET-ASSESSMENT-STORAGE-DETAIL")

    response = _web_app(failing_provider).test_client().get("/assessments")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Assessments are temporarily unavailable" in text
    assert "Your academic data was not changed" in text
    assert "SECRET-ASSESSMENT-STORAGE-DETAIL" not in text


def test_assessments_empty_catalogue_renders_meaningful_empty_state():
    from personal_learning_assistant.services.assessment_dashboard_service import (
        build_assessment_catalogue,
    )

    empty = build_assessment_catalogue(
        {"assessments": []},
        SimpleNamespace(courses=()),
        today=date(2026, 9, 17),
    )
    response = _web_app(lambda: empty).test_client().get("/assessments")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No assessments are available yet" in text
    assert "assessment data was not changed" in text.lower()


def test_assessments_remains_get_only_in_phase754():
    assert _web_app(_catalogue_fixture).test_client().post("/assessments").status_code == 405


def test_web_app_creation_keeps_assessment_storage_and_legacy_engines_lazy(tmp_path):
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "assignment_exam_assistant",
    "personal_learning_assistant.repositories.json.assessment_repository",
    "personal_learning_assistant.repositories.structured_authority_router",
    "personal_learning_assistant.repositories.sqlite.assessment_repository",
    "personal_learning_assistant.repositories.sqlite.compatibility_repository",
    "personal_learning_assistant.services.course_service",
    "personal_learning_assistant.repositories.routed_course_repository",
):
    assert name not in sys.modules, name
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
