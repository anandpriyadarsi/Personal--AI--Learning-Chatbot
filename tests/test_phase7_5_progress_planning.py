from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _course_result():
    return SimpleNamespace(
        courses=(
            SimpleNamespace(id="ma103n", code="MA103N", name="Linear Algebra"),
            SimpleNamespace(id="uc100n", code="UC100N", name="Data Science and AI"),
        )
    )


def _trend(course_id):
    if course_id == "ma103n":
        return {
            "current": {
                "progress_percent": 40,
                "mastered_topics": 4,
                "total_topics": 10,
                "average_confidence": 2.5,
                "weak_topics": ["LU Factorization"],
                "missing_topics": ["Vector Spaces"],
            },
            "previous": {"progress_percent": 30, "mastered_topics": 3},
            "delta_progress": 10,
            "delta_mastered": 1,
        }
    return {
        "current": {
            "progress_percent": 75,
            "mastered_topics": 6,
            "total_topics": 8,
            "average_confidence": 4.0,
            "weak_topics": [],
            "missing_topics": ["Model evaluation"],
        },
        "previous": None,
        "delta_progress": 0,
        "delta_mastered": 0,
    }


def _priorities(course_id, limit=5):
    values = {
        "ma103n": [
            {
                "name": "LU Factorization",
                "status": "weak",
                "confidence": 2,
                "priority_score": 118,
                "priority_reasons": ["marked weak", "low confidence"],
            },
            {
                "name": "Vector Spaces",
                "status": "not_started",
                "confidence": 0,
                "priority_score": 70,
                "priority_reasons": ["unfinished syllabus topic"],
            },
        ],
        "uc100n": [
            {
                "name": "Model evaluation",
                "status": "not_started",
                "confidence": 0,
                "priority_score": 61,
                "priority_reasons": ["unfinished syllabus topic"],
            }
        ],
    }
    return values[course_id][:limit]


def _plans_fixture():
    return {
        "weekly": {
            "created_at": "2026-09-16T20:00:00",
            "start_date": "2026-09-17",
            "course_code": "MA103N",
            "course_name": "Linear Algebra",
            "daily_minutes": 60,
            "study_days": 2,
            "days": [
                {
                    "date": "2026-09-17",
                    "total_minutes": 60,
                    "sessions": [
                        {
                            "topic": "LU Factorization",
                            "status": "weak",
                            "minutes": 60,
                        }
                    ],
                },
                {
                    "date": "2026-09-21",
                    "total_minutes": 60,
                    "sessions": [
                        {
                            "topic": "Vector Spaces",
                            "status": "not_started",
                            "minutes": 60,
                        }
                    ],
                },
            ],
        },
        "multi": {
            "created_at": "2026-09-16T21:00:00",
            "weekly_minutes": 300,
            "study_days": 3,
            "days": [
                {
                    "date": "2026-09-17",
                    "total_minutes": 100,
                    "sessions": [
                        {
                            "course_code": "MA103N",
                            "topic": "Rank",
                            "minutes": 50,
                        },
                        {
                            "course_code": "UC100N",
                            "topic": "Pandas",
                            "minutes": 50,
                        },
                    ],
                }
            ],
        },
        "intelligent": {
            "created_at": "2026-09-16T22:00:00",
            "total_minutes": 180,
            "study_days": 2,
            "days": [
                {
                    "date": "2026-09-18",
                    "sessions": [
                        {
                            "course_code": "MA103N",
                            "topic": "Consistency",
                            "minutes": 90,
                        },
                        {
                            "course_code": "UC100N",
                            "topic": "Data cleaning",
                            "minutes": 90,
                        },
                    ],
                }
            ],
        },
    }


def test_planning_dashboard_builds_progress_summary_and_priorities():
    from personal_learning_assistant.services.planning_dashboard_service import (
        build_planning_dashboard,
    )

    dashboard = build_planning_dashboard(
        _course_result(),
        _trend,
        _priorities,
        {},
    )

    assert dashboard["available"] is True
    assert dashboard["summary"] == {
        "courses": 2,
        "average_progress": 57.5,
        "mastered_topics": 10,
        "weak_topics": 1,
        "missing_topics": 2,
        "saved_plans": 0,
    }
    linear = dashboard["courses"][0]
    assert linear["code"] == "MA103N"
    assert linear["progress_percent"] == 40.0
    assert linear["mastered_topics"] == 4
    assert linear["total_topics"] == 10
    assert linear["average_confidence"] == 2.5
    assert linear["delta_progress"] == 10.0
    assert linear["delta_mastered"] == 1
    assert linear["weak_topics"] == ["LU Factorization"]
    assert linear["missing_topics"] == ["Vector Spaces"]
    assert linear["priorities"][0]["name"] == "LU Factorization"
    assert linear["priorities"][0]["status_label"] == "Weak"
    assert linear["priorities"][0]["reasons"] == ["marked weak", "low confidence"]


def test_planning_dashboard_normalizes_three_saved_plan_types_read_only():
    from personal_learning_assistant.services.planning_dashboard_service import (
        build_planning_dashboard,
    )

    dashboard = build_planning_dashboard(
        _course_result(),
        _trend,
        _priorities,
        _plans_fixture(),
    )

    assert dashboard["summary"]["saved_plans"] == 3
    plans = {item["key"]: item for item in dashboard["plans"]}
    assert set(plans) == {"weekly", "multi", "intelligent"}

    weekly = plans["weekly"]
    assert weekly["exists"] is True
    assert weekly["title"] == "Latest course weekly plan"
    assert weekly["course_label"] == "MA103N · Linear Algebra"
    assert weekly["total_minutes"] == 120
    assert weekly["study_days"] == 2
    assert [item["topic"] for item in weekly["sessions"]] == [
        "LU Factorization",
        "Vector Spaces",
    ]

    multi = plans["multi"]
    assert multi["total_minutes"] == 300
    assert multi["course_label"] == "MA103N + UC100N"
    assert multi["sessions"][0]["date"] == "2026-09-17"

    intelligent = plans["intelligent"]
    assert intelligent["total_minutes"] == 180
    assert intelligent["study_days"] == 2
    assert intelligent["course_label"] == "MA103N + UC100N"


def test_planning_dashboard_represents_missing_plans_without_creating_anything():
    from personal_learning_assistant.services.planning_dashboard_service import (
        build_planning_dashboard,
    )

    dashboard = build_planning_dashboard(
        _course_result(),
        _trend,
        _priorities,
        {"weekly": None, "multi": None, "intelligent": None},
    )

    assert dashboard["summary"]["saved_plans"] == 0
    assert len(dashboard["plans"]) == 3
    assert all(item["exists"] is False for item in dashboard["plans"])
    assert all(item["sessions"] == [] for item in dashboard["plans"])


def test_unavailable_planning_dashboard_has_safe_empty_shape():
    from personal_learning_assistant.services.planning_dashboard_service import (
        unavailable_planning_dashboard,
    )

    dashboard = unavailable_planning_dashboard()
    assert dashboard["available"] is False
    assert dashboard["courses"] == []
    assert dashboard["plans"] == []
    assert dashboard["summary"]["courses"] == 0
    assert dashboard["summary"]["saved_plans"] == 0
    assert "data was not changed" in dashboard["message"].lower()


def test_planning_service_source_contains_no_progress_or_plan_write_calls():
    repo_root = Path(__file__).resolve().parents[1]
    source = (
        repo_root / "personal_learning_assistant/services/planning_dashboard_service.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "record_progress_snapshot(",
        "save_history(",
        "create_weekly_plan(",
        "create_multi_course_plan(",
        "create_intelligent_plan(",
        "save_plan(",
    ):
        assert forbidden not in source


def test_routes_source_declares_get_only_planning_endpoint():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/routes.py").read_text(
        encoding="utf-8"
    )
    assert '@web_blueprint.get("/planning")' in source
    assert 'render_template("planning.html"' in source
    assert "PLANNING_DASHBOARD_PROVIDER" in source
    assert '@web_blueprint.post("/planning")' not in source


def test_base_navigation_exposes_planning_as_real_link():
    repo_root = Path(__file__).resolve().parents[1]
    source = (
        repo_root / "personal_learning_assistant/ui/web/templates/base.html"
    ).read_text(encoding="utf-8")
    assert "url_for('web.planning')" in source
    assert "active_page == 'planning'" in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Planning</span>' not in source


def _dashboard_fixture():
    from personal_learning_assistant.services.planning_dashboard_service import (
        build_planning_dashboard,
    )

    return build_planning_dashboard(
        _course_result(),
        _trend,
        _priorities,
        _plans_fixture(),
    )


def _web_app(provider):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "PLANNING_DASHBOARD_PROVIDER": provider,
        }
    )


def test_planning_page_renders_progress_priorities_and_saved_plans():
    response = _web_app(_dashboard_fixture).test_client().get("/planning")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Progress &amp; planning",
        "57.5%",
        "MA103N",
        "Linear Algebra",
        "40%",
        "LU Factorization",
        "marked weak",
        "Vector Spaces",
        "Latest course weekly plan",
        "Latest multi-course plan",
        "Latest intelligent study plan",
        "120 min",
        "Consistency",
        "Data cleaning",
    ):
        assert expected in text
    assert '<form' not in text.lower()
    assert 'href="/planning"' in text


def test_planning_provider_failure_degrades_without_leaking_exception_content():
    def failing_provider():
        raise RuntimeError("SECRET-PLANNING-STORAGE-DETAIL")

    response = _web_app(failing_provider).test_client().get("/planning")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Progress and planning are temporarily unavailable" in text
    assert "Your academic data was not changed" in text
    assert "SECRET-PLANNING-STORAGE-DETAIL" not in text


def test_planning_empty_dashboard_renders_meaningful_empty_state():
    from personal_learning_assistant.services.planning_dashboard_service import (
        build_planning_dashboard,
    )

    empty = build_planning_dashboard(
        SimpleNamespace(courses=()),
        lambda _course_id: None,
        lambda _course_id, limit=5: [],
        {},
    )
    response = _web_app(lambda: empty).test_client().get("/planning")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No course progress is available yet" in text
    assert "No saved plans yet" in text
    assert "planning data was not changed" in text.lower()


def test_planning_remains_get_only_in_phase755():
    assert _web_app(_dashboard_fixture).test_client().post("/planning").status_code == 405


def test_web_app_creation_keeps_progress_and_planner_engines_lazy(tmp_path):
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "academic_progress",
    "weekly_planner",
    "multi_course_planner",
    "intelligent_study_planner",
    "course_manager",
    "learning_memory",
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
