from __future__ import annotations

from types import SimpleNamespace


def _fake_brief():
    assessment = {
        "course_id": "c1",
        "title": "Quiz 1",
        "due_date": "2026-09-18",
    }
    second = {
        "course_id": "c2",
        "title": "Lab report",
        "due_date": "2026-09-19",
    }

    return SimpleNamespace(
        _today=lambda: SimpleNamespace(isoformat=lambda: "2026-09-17"),
        _urgent_assessments=lambda: [assessment, second],
        _today_blocks=lambda: [
            {"assessment": assessment, "minutes": 45, "label": "Quiz preparation"},
            {"assessment": second, "minutes": 30, "label": "Draft report"},
        ],
        _top_risks=lambda limit=3: [
            {
                "course": {"code": "MA103N", "name": "Linear Algebra"},
                "score": 42.5,
                "weak_topics": ["LU Factorization", "Rank"],
                "evidence": [{"topic": "LU Factorization"}],
                "urgent": [assessment],
            },
            {
                "course": {"code": "UC100N", "name": "Data Science and AI"},
                "score": 0,
                "weak_topics": [],
                "evidence": [],
                "urgent": [],
            },
        ],
        _brief_actions=lambda: [
            {
                "course_code": "MA103N",
                "topic": "LU Factorization",
                "score": 88.0,
                "reasons": ["weak topic", "quiz soon", "weak topic"],
                "performance": {"accuracy": 60, "attempts": 5},
            }
        ],
        _course_code=lambda item: "MA103N" if item is assessment else "UC100N",
        _due_label=lambda item: "due tomorrow" if item is assessment else "due in 2 days",
        assessment_weightage_percent=lambda item: 15 if item is assessment else None,
    )


def test_home_dashboard_service_normalizes_existing_daily_brief_read_model():
    from personal_learning_assistant.services.home_dashboard_service import (
        build_home_dashboard_from_brief,
    )

    dashboard = build_home_dashboard_from_brief(_fake_brief())

    assert dashboard["available"] is True
    assert dashboard["date"] == "2026-09-17"
    assert dashboard["summary"] == {
        "urgent_deadlines": 2,
        "scheduled_minutes": 75,
        "priority_topics": 1,
        "risk_courses": 1,
    }
    assert dashboard["deadlines"][0] == {
        "course_code": "MA103N",
        "title": "Quiz 1",
        "due_label": "due tomorrow",
        "weightage_percent": 15.0,
    }
    assert dashboard["study_blocks"][0]["minutes"] == 45
    assert dashboard["priorities"][0]["reasons"] == ["weak topic", "quiz soon"]
    assert dashboard["risks"][0]["course_code"] == "MA103N"
    assert dashboard["best_next_action"]["title"] == "MA103N · LU Factorization"


def test_unavailable_dashboard_has_safe_empty_shape():
    from personal_learning_assistant.services.home_dashboard_service import (
        unavailable_home_dashboard,
    )

    dashboard = unavailable_home_dashboard()

    assert dashboard["available"] is False
    assert dashboard["deadlines"] == []
    assert dashboard["study_blocks"] == []
    assert dashboard["priorities"] == []
    assert dashboard["risks"] == []
    assert dashboard["best_next_action"] is None
    assert "data was not changed" in dashboard["message"].lower()


def _dashboard_fixture():
    from personal_learning_assistant.services.home_dashboard_service import (
        build_home_dashboard_from_brief,
    )

    return build_home_dashboard_from_brief(_fake_brief())


def _web_app(provider):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "HOME_DASHBOARD_PROVIDER": provider,
        }
    )


def test_home_renders_academic_summary_from_injected_read_provider():
    app = _web_app(_dashboard_fixture)
    response = app.test_client().get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Today at a glance",
        "Urgent deadlines",
        "75 min",
        "ANVAYA recommends",
        "MA103N · LU Factorization",
        "Deadline alerts",
        "Quiz 1",
        "Study blocks",
        "Top study priorities",
        "Academic risk",
    ):
        assert expected in text


def test_home_provider_failure_degrades_without_leaking_exception_content():
    def failing_provider():
        raise RuntimeError("SECRET-DATABASE-DETAIL")

    response = _web_app(failing_provider).test_client().get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Academic brief temporarily unavailable" in text
    assert "Your academic data was not changed" in text
    assert "SECRET-DATABASE-DETAIL" not in text


def test_home_with_empty_read_model_renders_meaningful_empty_states():
    from personal_learning_assistant.services.home_dashboard_service import (
        build_home_dashboard_from_brief,
    )

    brief = SimpleNamespace(
        _today=lambda: SimpleNamespace(isoformat=lambda: "2026-09-17"),
        _urgent_assessments=lambda: [],
        _today_blocks=lambda: [],
        _top_risks=lambda limit=3: [],
        _brief_actions=lambda: [],
        _course_code=lambda item: "COURSE",
        _due_label=lambda item: "date unknown",
        assessment_weightage_percent=lambda item: None,
    )
    dashboard = build_home_dashboard_from_brief(brief)
    response = _web_app(lambda: dashboard).test_client().get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No urgent action detected" in text
    assert "No assessment is due within the urgent window" in text
    assert "No deadline-based study block is required today" in text
    assert "No unresolved study priority was found" in text
    assert "No major academic risk signal is active" in text


def test_home_remains_get_only_in_phase752():
    assert _web_app(_dashboard_fixture).test_client().post("/").status_code == 405


def test_web_app_creation_keeps_daily_brief_and_legacy_engines_lazy(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "daily_academic_brief",
    "course_manager",
    "assignment_exam_assistant",
    "academic_intelligence_dashboard",
    "academic_calendar_planner",
    "intelligent_study_planner",
    "rag_answer",
    "semantic_retrieval",
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
