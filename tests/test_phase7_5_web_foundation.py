from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _app():
    from personal_learning_assistant.ui.web import create_app

    return create_app({"TESTING": True})


def test_app_factory_creates_testing_app():
    app = _app()
    assert app.testing is True
    assert app.name == "personal_learning_assistant.ui.web"


def test_home_route_renders_local_navigation_shell():
    client = _app().test_client()
    response = client.get("/")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Personal AI Learning Assistant" in text
    for label in (
        "Home",
        "Courses",
        "Assessments",
        "Planning",
        "Calendar",
        "Notes",
        "Resources",
        "Knowledge",
        "Academic Agent",
    ):
        assert label in text
    assert "https://" not in text
    assert "http://" not in text


def test_health_route_is_read_only_and_machine_readable():
    client = _app().test_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {
        "phase": "7.5.1",
        "service": "personal-learning-assistant-web",
        "status": "ok",
    }
    assert client.post("/healthz").status_code == 405


def test_home_is_get_only():
    client = _app().test_client()
    assert client.post("/").status_code == 405


def test_static_css_is_served_locally():
    client = _app().test_client()
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
    assert "--surface" in response.get_data(as_text=True)


def test_unknown_route_uses_project_404_page():
    client = _app().test_client()
    response = client.get("/this-route-does-not-exist")
    text = response.get_data(as_text=True)
    assert response.status_code == 404
    assert "Page not found" in text
    assert "Return home" in text


def test_unhandled_error_uses_project_500_page():
    app = _app()
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/_phase751_test_error")
    def _phase751_test_error():
        raise RuntimeError("test-only")

    response = app.test_client().get("/_phase751_test_error")
    text = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "Something went wrong" in text
    assert "Return home" in text


def test_web_startup_does_not_import_optional_ai_or_legacy_cli_modules(tmp_path):
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "main",
    "rag_answer",
    "semantic_retrieval",
    "hybrid_retrieval",
    "vision_math_reader",
    "youtube_ingestion",
    "youtube_analysis",
    "course_manager",
    "notes",
    "resources",
):
    assert name not in sys.modules, name
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_runtime_dependency_declares_flask():
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "Flask==3.1.2" in requirements.splitlines()
