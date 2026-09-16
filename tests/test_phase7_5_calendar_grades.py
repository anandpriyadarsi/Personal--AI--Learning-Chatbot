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


def _grade_config():
    return {
        "semester_name": "Semester 1",
        "target_sgpa": 9.0,
        "grade_scale_source": "student planning config",
        "grade_scale_verified": False,
        "grade_scale": [
            {"letter": "A+", "min_score": 90, "grade_point": 10},
            {"letter": "A", "min_score": 80, "grade_point": 9},
        ],
        "courses": [
            {
                "course_id": "ma103n",
                "credits": 4,
                "manual_score": 84,
                "manual_letter_grade": "A",
                "manual_grade_point": 9,
            },
            {
                "course_id": "uc100n",
                "credits": 3,
                "manual_score": None,
                "manual_letter_grade": None,
                "manual_grade_point": None,
            },
        ],
        "semester_result": {
            "earned_credits": 7,
            "earned_grade_points": 63,
            "sgpa": 9.0,
            "verified": True,
            "source": "official result sheet",
        },
    }


def _assessment_state():
    return {
        "assessments": [
            {
                "id": "1",
                "course_id": "ma103n",
                "title": "Quiz 1",
                "type": "quiz",
                "status": "pending",
                "due_date": "2026-09-15",
                "weightage_percent": 10,
            },
            {
                "id": "2",
                "course_id": "uc100n",
                "title": "Lab submission",
                "type": "lab",
                "status": "in_progress",
                "due_date": "2026-09-20",
                "weightage_percent": 15,
            },
            {
                "id": "3",
                "course_id": "ma103n",
                "title": "End semester exam",
                "type": "endsem",
                "status": "pending",
                "due_date": "2026-11-10",
                "weightage_percent": 50,
            },
            {
                "id": "4",
                "course_id": "ma103n",
                "title": "Assignment 1",
                "type": "assignment",
                "status": "completed",
                "due_date": "2026-09-10",
                "weightage_percent": 5,
            },
        ]
    }


def _dashboard_fixture():
    from personal_learning_assistant.services.calendar_grades_dashboard_service import (
        build_calendar_grades_dashboard,
    )
    return build_calendar_grades_dashboard(
        _grade_config(),
        _assessment_state(),
        _course_result(),
        today=date(2026, 9, 17),
        grade_source_present=True,
    )


def test_calendar_grades_builds_only_recorded_grade_evidence():
    dashboard = _dashboard_fixture()

    assert dashboard["available"] is True
    grades = dashboard["grades"]
    assert grades["semester_name"] == "Semester 1"
    assert grades["target_sgpa"] == 9.0
    assert grades["scale"]["source"] == "student planning config"
    assert grades["scale"]["verified"] is False
    assert grades["scale"]["bands"][0]["letter"] == "A+"

    courses = {item["code"]: item for item in grades["courses"]}
    linear = courses["MA103N"]
    assert linear["name"] == "Linear Algebra"
    assert linear["credits"] == 4.0
    assert linear["score"] == 84.0
    assert linear["letter_grade"] == "A"
    assert linear["grade_point"] == 9.0
    assert linear["has_recorded_grade"] is True

    data_science = courses["UC100N"]
    assert data_science["has_recorded_grade"] is False
    assert data_science["letter_grade"] is None
    assert data_science["grade_point"] is None

    result = grades["semester_result"]
    assert result["sgpa"] == 9.0
    assert result["verified"] is True
    assert result["source"] == "official result sheet"


def test_calendar_grades_groups_deadlines_without_changing_them():
    dashboard = _dashboard_fixture()
    groups = dashboard["calendar"]["groups"]

    assert [item["title"] for item in groups["overdue"]] == ["Quiz 1"]
    assert [item["title"] for item in groups["upcoming"]] == ["Lab submission"]
    assert [item["title"] for item in groups["later"]] == ["End semester exam"]
    assert [item["title"] for item in groups["completed"]] == ["Assignment 1"]

    upcoming = groups["upcoming"][0]
    assert upcoming["course_code"] == "UC100N"
    assert upcoming["due_date"] == "2026-09-20"
    assert upcoming["days_until"] == 3
    assert upcoming["status_label"] == "In progress"
    assert upcoming["weightage_percent"] == 15.0

    summary = dashboard["summary"]
    assert summary["calendar_events"] == 4
    assert summary["overdue"] == 1
    assert summary["upcoming"] == 1
    assert summary["recorded_grades"] == 1


def test_calendar_grades_hides_grade_configuration_when_source_is_absent():
    from personal_learning_assistant.services.calendar_grades_dashboard_service import (
        build_calendar_grades_dashboard,
    )

    dashboard = build_calendar_grades_dashboard(
        _grade_config(),
        {"assessments": []},
        _course_result(),
        today=date(2026, 9, 17),
        grade_source_present=False,
    )

    assert dashboard["grades"]["source_present"] is False
    assert dashboard["grades"]["courses"] == []
    assert dashboard["grades"]["scale"]["bands"] == []
    assert dashboard["grades"]["semester_result"] is None
    assert dashboard["summary"]["grade_courses"] == 0


def test_unavailable_calendar_grades_dashboard_has_safe_empty_shape():
    from personal_learning_assistant.services.calendar_grades_dashboard_service import (
        unavailable_calendar_grades_dashboard,
    )

    dashboard = unavailable_calendar_grades_dashboard()
    assert dashboard["available"] is False
    assert dashboard["grades"]["courses"] == []
    assert dashboard["calendar"]["groups"]["upcoming"] == []
    assert dashboard["summary"]["calendar_events"] == 0
    assert "data was not changed" in dashboard["message"].lower()


def test_calendar_grades_service_source_contains_no_write_calls():
    repo_root = Path(__file__).resolve().parents[1]
    source = (
        repo_root
        / "personal_learning_assistant/services/calendar_grades_dashboard_service.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "maybe_save_sqlite_structured_store(",
        "save_grade_config(",
        "save_store(",
        "record_progress_snapshot(",
        "write_text(",
        "unlink(",
        "remove(",
    ):
        assert forbidden not in source


def test_routes_source_declares_get_only_calendar_endpoint():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/routes.py").read_text(
        encoding="utf-8"
    )
    assert '@web_blueprint.get("/calendar")' in source
    assert 'render_template("calendar.html"' in source
    assert "CALENDAR_GRADES_PROVIDER" in source
    assert '@web_blueprint.post("/calendar")' not in source


def test_base_navigation_exposes_calendar_as_real_link():
    repo_root = Path(__file__).resolve().parents[1]
    source = (
        repo_root / "personal_learning_assistant/ui/web/templates/base.html"
    ).read_text(encoding="utf-8")
    assert "url_for('web.calendar')" in source
    assert "active_page == 'calendar'" in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Calendar</span>' not in source


def _web_app(provider):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "CALENDAR_GRADES_PROVIDER": provider,
        }
    )


def test_calendar_page_renders_calendar_and_recorded_grades():
    response = _web_app(_dashboard_fixture).test_client().get("/calendar")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Calendar &amp; grades",
        "Semester 1",
        "Target SGPA",
        "9",
        "MA103N",
        "Linear Algebra",
        "84%",
        "official result sheet",
        "Quiz 1",
        "Overdue",
        "Lab submission",
        "End semester exam",
        "Completed",
    ):
        assert expected in text
    assert "<form" not in text.lower()
    assert 'href="/calendar"' in text


def test_calendar_provider_failure_degrades_without_leaking_exception_content():
    def failing_provider():
        raise RuntimeError("SECRET-GRADE-CALENDAR-STORAGE-DETAIL")

    response = _web_app(failing_provider).test_client().get("/calendar")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Calendar and grades are temporarily unavailable" in text
    assert "Your academic data was not changed" in text
    assert "SECRET-GRADE-CALENDAR-STORAGE-DETAIL" not in text


def test_calendar_empty_dashboard_renders_meaningful_empty_states():
    from personal_learning_assistant.services.calendar_grades_dashboard_service import (
        build_calendar_grades_dashboard,
    )

    empty = build_calendar_grades_dashboard(
        {"semester_name": "Semester 1", "courses": [], "grade_scale": []},
        {"assessments": []},
        SimpleNamespace(courses=()),
        today=date(2026, 9, 17),
        grade_source_present=True,
    )
    response = _web_app(lambda: empty).test_client().get("/calendar")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No academic deadlines are stored yet" in text
    assert "No semester course grades are recorded yet" in text
    assert "No explicit semester result is stored yet" in text


def test_calendar_remains_get_only_in_phase756():
    assert _web_app(_dashboard_fixture).test_client().post("/calendar").status_code == 405


def test_web_app_creation_keeps_grade_calendar_engines_lazy(tmp_path):
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "semester_grade_intelligence",
    "academic_calendar_planner",
    "assignment_exam_assistant",
    "personal_learning_assistant.repositories.json.grade_calendar_repository",
    "personal_learning_assistant.repositories.sqlite.grade_calendar_repository",
    "personal_learning_assistant.repositories.grade_calendar_backend",
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
