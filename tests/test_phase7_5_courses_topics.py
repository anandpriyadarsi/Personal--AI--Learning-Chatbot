from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _topic(name, status, confidence, last_updated=None):
    return SimpleNamespace(
        name=name,
        status=status,
        confidence=confidence,
        last_updated=last_updated,
    )


def _course(course_id, code, name, semester, status, topics):
    return SimpleNamespace(
        id=course_id,
        code=code,
        name=name,
        semester=semester,
        status=status,
        topics=tuple(topics),
        created_at=None,
        updated_at=None,
    )


def _result_fixture():
    return SimpleNamespace(
        active_course_id="ma103n",
        courses=(
            _course(
                "ma103n",
                "MA103N",
                "Linear Algebra",
                "Semester 1",
                "active",
                (
                    _topic("LU Factorization", "weak", 2, "2026-09-16"),
                    _topic("Rank of Matrix", "mastered", 5, "2026-09-15"),
                    _topic("Vector Spaces", "learning", 3),
                ),
            ),
            _course(
                "uc100n",
                "UC100N",
                "Data Science and AI",
                "Semester 1",
                "active",
                (_topic("Pandas", "practiced", 4),),
            ),
        ),
    )


def test_course_catalogue_service_normalizes_courses_topics_and_summary():
    from personal_learning_assistant.services.course_dashboard_service import (
        build_course_catalogue_from_result,
    )

    catalogue = build_course_catalogue_from_result(_result_fixture())

    assert catalogue["available"] is True
    assert catalogue["active_course_id"] == "ma103n"
    assert catalogue["summary"] == {
        "courses": 2,
        "topics": 4,
        "mastered_topics": 1,
        "weak_topics": 1,
    }
    first = catalogue["courses"][0]
    assert first["code"] == "MA103N"
    assert first["is_active"] is True
    assert first["topic_count"] == 3
    assert first["mastered_count"] == 1
    assert first["progress_percent"] == 33
    assert first["topics"][0] == {
        "name": "LU Factorization",
        "status": "weak",
        "status_label": "Weak",
        "confidence": 2,
        "last_updated": "2026-09-16",
    }


def test_course_catalogue_service_clamps_confidence_and_handles_empty_topics():
    from personal_learning_assistant.services.course_dashboard_service import (
        build_course_catalogue_from_result,
    )

    result = SimpleNamespace(
        active_course_id=None,
        courses=(
            _course(
                "empty",
                "CY100N",
                "Engineering Chemistry",
                "Semester 1",
                "planned",
                (),
            ),
            _course(
                "bounded",
                "DE100N",
                "Design Thinking",
                "Semester 1",
                "active",
                (
                    _topic("Prototype", "review", 99),
                    _topic("Ideation", "not_started", -3),
                ),
            ),
        ),
    )

    catalogue = build_course_catalogue_from_result(result)

    assert catalogue["courses"][0]["progress_percent"] == 0
    assert catalogue["courses"][1]["topics"][0]["confidence"] == 5
    assert catalogue["courses"][1]["topics"][1]["confidence"] == 0
    assert catalogue["courses"][1]["topics"][1]["status_label"] == "Not started"


def test_unavailable_course_catalogue_has_safe_empty_shape():
    from personal_learning_assistant.services.course_dashboard_service import (
        unavailable_course_catalogue,
    )

    catalogue = unavailable_course_catalogue()

    assert catalogue["available"] is False
    assert catalogue["courses"] == []
    assert catalogue["active_course_id"] is None
    assert catalogue["summary"] == {
        "courses": 0,
        "topics": 0,
        "mastered_topics": 0,
        "weak_topics": 0,
    }
    assert "data was not changed" in catalogue["message"].lower()


def test_routes_source_declares_get_only_courses_endpoint():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/routes.py").read_text(
        encoding="utf-8"
    )

    assert '@web_blueprint.get("/courses")' in source
    assert 'render_template("courses.html"' in source
    assert "COURSE_CATALOGUE_PROVIDER" in source
    assert '@web_blueprint.post("/courses")' not in source


def test_base_navigation_exposes_courses_as_real_link():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/templates/base.html").read_text(
        encoding="utf-8"
    )

    assert "url_for('web.courses')" in source
    assert "active_page == 'courses'" in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Courses</span>' not in source


def _catalogue_fixture():
    from personal_learning_assistant.services.course_dashboard_service import (
        build_course_catalogue_from_result,
    )

    return build_course_catalogue_from_result(_result_fixture())


def _web_app(provider):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "COURSE_CATALOGUE_PROVIDER": provider,
        }
    )


def test_courses_page_renders_active_course_topics_status_and_confidence():
    response = _web_app(_catalogue_fixture).test_client().get("/courses")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Courses & topics",
        "2 courses",
        "4 topics",
        "MA103N",
        "Linear Algebra",
        "Active course",
        "LU Factorization",
        "Weak",
        "Confidence 2/5",
        "Rank of Matrix",
        "Mastered",
        "33% mastered",
        "UC100N",
        "Data Science and AI",
    ):
        assert expected in text
    assert 'href="/courses"' in text


def test_courses_provider_failure_degrades_without_leaking_exception_content():
    def failing_provider():
        raise RuntimeError("SECRET-COURSE-STORAGE-DETAIL")

    response = _web_app(failing_provider).test_client().get("/courses")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Courses are temporarily unavailable" in text
    assert "Your academic data was not changed" in text
    assert "SECRET-COURSE-STORAGE-DETAIL" not in text


def test_courses_empty_catalogue_renders_meaningful_empty_state():
    from personal_learning_assistant.services.course_dashboard_service import (
        build_course_catalogue_from_result,
    )

    empty = build_course_catalogue_from_result(
        SimpleNamespace(active_course_id=None, courses=())
    )
    response = _web_app(lambda: empty).test_client().get("/courses")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No courses are available yet" in text
    assert "course data was not changed" in text.lower()


def test_courses_remains_get_only_in_phase753():
    assert _web_app(_catalogue_fixture).test_client().post("/courses").status_code == 405


def test_web_app_creation_keeps_course_engines_lazy(tmp_path):
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "course_manager",
    "personal_learning_assistant.services.course_service",
    "personal_learning_assistant.repositories.routed_course_repository",
    "personal_learning_assistant.repositories.structured_authority_router",
    "personal_learning_assistant.repositories.sqlite.course_repository",
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
