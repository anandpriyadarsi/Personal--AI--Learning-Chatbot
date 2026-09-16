from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _notes_fixture():
    return SimpleNamespace(
        notes=(
            SimpleNamespace(
                title="LU intuition",
                topic="LU Factorization",
                difficulty="Hard",
                content="Elimination can be recorded as lower-triangular multipliers.",
            ),
            SimpleNamespace(
                title="Pandas cleaning",
                topic="Data Cleaning",
                difficulty="Medium",
                content="Inspect missing values before deciding how to handle them.",
            ),
        )
    )


def _resources_fixture():
    return SimpleNamespace(
        resources=(
            SimpleNamespace(
                position=1,
                title="MIT 18.06",
                resource_type="Course",
                link="https://ocw.mit.edu/",
                status="In Progress",
            ),
            SimpleNamespace(
                position=2,
                title="Local reference",
                resource_type="PDF",
                link="C:/study/reference.pdf",
                status="Not Started",
            ),
            SimpleNamespace(
                position=3,
                title="Finished guide",
                resource_type="Article",
                link="",
                status="Completed",
            ),
        )
    )


def test_notes_dashboard_normalizes_existing_note_service_result():
    from personal_learning_assistant.services.notes_resources_dashboard_service import (
        build_notes_dashboard,
    )

    dashboard = build_notes_dashboard(_notes_fixture())

    assert dashboard["available"] is True
    assert dashboard["summary"] == {
        "total": 2,
        "topics": 2,
        "difficulties": 2,
    }
    assert dashboard["notes"][0] == {
        "title": "LU intuition",
        "topic": "LU Factorization",
        "difficulty": "Hard",
        "content": "Elimination can be recorded as lower-triangular multipliers.",
    }


def test_resources_dashboard_normalizes_status_types_and_safe_links():
    from personal_learning_assistant.services.notes_resources_dashboard_service import (
        build_resources_dashboard,
    )

    dashboard = build_resources_dashboard(_resources_fixture())

    assert dashboard["available"] is True
    assert dashboard["summary"] == {
        "total": 3,
        "types": 3,
        "not_started": 1,
        "in_progress": 1,
        "completed": 1,
    }
    resources = dashboard["resources"]
    assert resources[0]["link_url"] == "https://ocw.mit.edu/"
    assert resources[1]["link_url"] == ""
    assert resources[1]["link"] == "C:/study/reference.pdf"
    assert resources[2]["link"] == ""


def test_resource_dashboard_never_makes_active_javascript_link():
    from personal_learning_assistant.services.notes_resources_dashboard_service import (
        build_resources_dashboard,
    )

    result = SimpleNamespace(
        resources=(
            SimpleNamespace(
                position=1,
                title="Unsafe",
                resource_type="Link",
                link="javascript:alert(1)",
                status="Not Started",
            ),
        )
    )
    dashboard = build_resources_dashboard(result)
    assert dashboard["resources"][0]["link_url"] == ""
    assert dashboard["resources"][0]["link"] == "javascript:alert(1)"


def test_empty_and_unavailable_models_are_safe():
    from personal_learning_assistant.services.notes_resources_dashboard_service import (
        build_notes_dashboard,
        build_resources_dashboard,
        unavailable_notes_dashboard,
        unavailable_resources_dashboard,
    )

    notes = build_notes_dashboard(SimpleNamespace(notes=()))
    resources = build_resources_dashboard(SimpleNamespace(resources=()))
    assert notes["available"] is True and notes["notes"] == []
    assert resources["available"] is True and resources["resources"] == []

    notes_down = unavailable_notes_dashboard()
    resources_down = unavailable_resources_dashboard()
    assert notes_down["available"] is False and notes_down["notes"] == []
    assert resources_down["available"] is False and resources_down["resources"] == []
    assert "data was not changed" in notes_down["message"].lower()
    assert "data was not changed" in resources_down["message"].lower()


def test_dashboard_service_source_uses_list_reads_and_contains_no_write_calls():
    repo_root = Path(__file__).resolve().parents[1]
    source = (
        repo_root
        / "personal_learning_assistant/services/notes_resources_dashboard_service.py"
    ).read_text(encoding="utf-8")

    assert ".list_notes()" in source
    assert ".list_resources()" in source
    for forbidden in (
        ".create_note(",
        ".create_resource(",
        ".update_status(",
        ".append_note(",
        ".append_resource(",
        ".replace_resource(",
        ".save_resources(",
    ):
        assert forbidden not in source


def test_routes_source_declares_get_only_notes_and_resources_endpoints():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/routes.py").read_text(
        encoding="utf-8"
    )
    assert '@web_blueprint.get("/notes")' in source
    assert '@web_blueprint.get("/resources")' in source
    assert 'render_template("notes.html"' in source
    assert 'render_template("resources.html"' in source
    assert "NOTES_DASHBOARD_PROVIDER" in source
    assert "RESOURCES_DASHBOARD_PROVIDER" in source
    assert '@web_blueprint.post("/notes")' not in source
    assert '@web_blueprint.post("/resources")' not in source


def test_base_navigation_exposes_notes_and_resources_as_links():
    repo_root = Path(__file__).resolve().parents[1]
    source = (
        repo_root / "personal_learning_assistant/ui/web/templates/base.html"
    ).read_text(encoding="utf-8")
    assert "url_for('web.notes')" in source
    assert "url_for('web.resources')" in source
    assert "active_page == 'notes'" in source
    assert "active_page == 'resources'" in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Notes</span>' not in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Resources</span>' not in source


def _web_app(notes_provider=None, resources_provider=None):
    from personal_learning_assistant.ui.web import create_app

    config = {"TESTING": True}
    if notes_provider is not None:
        config["NOTES_DASHBOARD_PROVIDER"] = notes_provider
    if resources_provider is not None:
        config["RESOURCES_DASHBOARD_PROVIDER"] = resources_provider
    return create_app(config)


def test_notes_page_renders_existing_notes_without_write_controls():
    from personal_learning_assistant.services.notes_resources_dashboard_service import (
        build_notes_dashboard,
    )

    response = _web_app(
        notes_provider=lambda: build_notes_dashboard(_notes_fixture())
    ).test_client().get("/notes")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Notes",
        "LU intuition",
        "LU Factorization",
        "Hard",
        "lower-triangular multipliers",
        "Pandas cleaning",
    ):
        assert expected in text
    assert '<form' not in text.lower()
    assert 'href="/notes"' in text


def test_resources_page_renders_safe_external_links_and_plain_local_paths():
    from personal_learning_assistant.services.notes_resources_dashboard_service import (
        build_resources_dashboard,
    )

    response = _web_app(
        resources_provider=lambda: build_resources_dashboard(_resources_fixture())
    ).test_client().get("/resources")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MIT 18.06" in text
    assert 'href="https://ocw.mit.edu/"' in text
    assert 'rel="noopener noreferrer"' in text
    assert "C:/study/reference.pdf" in text
    assert 'href="C:/study/reference.pdf"' not in text
    assert "In Progress" in text
    assert "Completed" in text
    assert '<form' not in text.lower()
    assert 'href="/resources"' in text


def test_notes_and_resources_provider_failures_degrade_without_secret_details():
    def failing_notes():
        raise RuntimeError("SECRET-NOTES-STORAGE")

    def failing_resources():
        raise RuntimeError("SECRET-RESOURCES-STORAGE")

    client = _web_app(failing_notes, failing_resources).test_client()
    notes_text = client.get("/notes").get_data(as_text=True)
    resources_text = client.get("/resources").get_data(as_text=True)

    assert "Notes are temporarily unavailable" in notes_text
    assert "SECRET-NOTES-STORAGE" not in notes_text
    assert "Resources are temporarily unavailable" in resources_text
    assert "SECRET-RESOURCES-STORAGE" not in resources_text


def test_notes_and_resources_remain_get_only_in_phase757():
    client = _web_app(
        lambda: {"available": True, "message": "", "summary": {"total": 0, "topics": 0, "difficulties": 0}, "notes": []},
        lambda: {"available": True, "message": "", "summary": {"total": 0, "types": 0, "not_started": 0, "in_progress": 0, "completed": 0}, "resources": []},
    ).test_client()
    assert client.post("/notes").status_code == 405
    assert client.post("/resources").status_code == 405


def test_web_app_creation_keeps_notes_and_resources_subsystems_lazy(tmp_path):
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "notes",
    "resources",
    "personal_learning_assistant.services.notes_service",
    "personal_learning_assistant.services.resource_service",
    "personal_learning_assistant.repositories.json.note_repository",
    "personal_learning_assistant.repositories.json.resource_repository",
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
