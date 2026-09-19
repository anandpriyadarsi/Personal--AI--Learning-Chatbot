from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _notes_fixture():
    return SimpleNamespace(
        notes=(
            SimpleNamespace(position=1,title="LU intuition",topic="LU Factorization",difficulty="Hard",content="Elimination can be recorded as lower-triangular multipliers."),
            SimpleNamespace(position=2,title="Pandas cleaning",topic="Data Cleaning",difficulty="Medium",content="Inspect missing values before deciding how to handle them."),
        )
    )


def _resources_fixture():
    return SimpleNamespace(
        resources=(
            SimpleNamespace(position=1,title="MIT 18.06",resource_type="Course",link="https://ocw.mit.edu/",status="In Progress"),
            SimpleNamespace(position=2,title="Local reference",resource_type="PDF",link="C:/study/reference.pdf",status="Not Started"),
            SimpleNamespace(position=3,title="Finished guide",resource_type="Article",link="",status="Completed"),
        )
    )


def test_notes_dashboard_normalizes_existing_note_service_result():
    from personal_learning_assistant.services.notes_resources_dashboard_service import build_notes_dashboard
    dashboard = build_notes_dashboard(_notes_fixture())
    assert dashboard["available"] is True
    assert dashboard["summary"] == {"total": 2, "topics": 2, "difficulties": 2}
    assert dashboard["notes"][0] == {
        "position": 1,
        "title": "LU intuition",
        "topic": "LU Factorization",
        "difficulty": "Hard",
        "content": "Elimination can be recorded as lower-triangular multipliers.",
    }


def test_resources_dashboard_normalizes_status_types_and_safe_links():
    from personal_learning_assistant.services.notes_resources_dashboard_service import build_resources_dashboard
    dashboard = build_resources_dashboard(_resources_fixture())
    assert dashboard["available"] is True
    assert dashboard["summary"] == {"total":3,"types":3,"not_started":1,"in_progress":1,"completed":1}
    resources = dashboard["resources"]
    assert resources[0]["link_url"] == "https://ocw.mit.edu/"
    assert resources[1]["link_url"] == ""
    assert resources[1]["link"] == "C:/study/reference.pdf"


def test_resource_dashboard_never_makes_active_javascript_link():
    from personal_learning_assistant.services.notes_resources_dashboard_service import build_resources_dashboard
    result = SimpleNamespace(resources=(SimpleNamespace(position=1,title="Unsafe",resource_type="Link",link="javascript:alert(1)",status="Not Started"),))
    dashboard = build_resources_dashboard(result)
    assert dashboard["resources"][0]["link_url"] == ""
    assert dashboard["resources"][0]["link"] == "javascript:alert(1)"


def test_empty_and_unavailable_models_are_safe():
    from personal_learning_assistant.services.notes_resources_dashboard_service import build_notes_dashboard, build_resources_dashboard, unavailable_notes_dashboard, unavailable_resources_dashboard
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


def test_dashboard_adapter_remains_read_only():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/services/notes_resources_dashboard_service.py").read_text(encoding="utf-8")
    for forbidden in (".create_note(", ".update_note(", ".create_resource(", ".update_status(", ".append_note(", ".replace_note(", ".append_resource(", ".replace_resource("):
        assert forbidden not in source


def test_routes_expose_explicit_notes_and_resources_command_endpoints():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/routes.py").read_text(encoding="utf-8")
    for token in (
        '@web_blueprint.get("/notes")', '@web_blueprint.post("/notes")', '@web_blueprint.post("/notes/<int:position>")',
        '@web_blueprint.get("/resources")', '@web_blueprint.post("/resources")', '@web_blueprint.post("/resources/<int:position>/status")',
        "NOTES_RESOURCES_WEB_SERVICE_FACTORY",
    ):
        assert token in source
    assert "repositories.json.note_repository" not in source
    assert "repositories.json.resource_repository" not in source


def test_base_navigation_exposes_notes_and_resources_as_links():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "personal_learning_assistant/ui/web/templates/base.html").read_text(encoding="utf-8")
    assert "url_for('web.notes')" in source
    assert "url_for('web.resources')" in source
    assert "active_page == 'notes'" in source
    assert "active_page == 'resources'" in source


class _ReadFakeWebService:
    def notes_workspace(self, search="", topic="", difficulty=""):
        from personal_learning_assistant.services.notes_resources_dashboard_service import build_notes_dashboard
        dashboard = build_notes_dashboard(_notes_fixture())
        dashboard["query"] = {"search": search, "topic": topic, "difficulty": difficulty}
        dashboard["filter_options"] = {"topics": ["Data Cleaning", "LU Factorization"], "difficulties": ["Hard", "Medium"]}
        return dashboard

    def resources_workspace(self, search="", resource_type="", status=""):
        from personal_learning_assistant.services.notes_resources_dashboard_service import build_resources_dashboard
        dashboard = build_resources_dashboard(_resources_fixture())
        dashboard["query"] = {"search": search, "type": resource_type, "status": status}
        dashboard["filter_options"] = {"types": ["Article", "Course", "PDF"], "statuses": ("Not Started", "In Progress", "Completed")}
        return dashboard


def _web_app(service=None):
    from personal_learning_assistant.ui.web import create_app
    return create_app({"TESTING": True, "NOTES_RESOURCES_WEB_SERVICE_FACTORY": lambda: service or _ReadFakeWebService()})


def test_notes_page_renders_existing_notes_with_operational_forms():
    response = _web_app().test_client().get("/notes")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    for expected in ("Notes", "LU intuition", "LU Factorization", "Hard", "Pandas cleaning", "+ New Note", "Edit note"):
        assert expected in text
    assert '<form' in text.lower()
    assert "Read only" not in text


def test_resources_page_renders_safe_external_links_and_plain_local_paths():
    response = _web_app().test_client().get("/resources")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "MIT 18.06" in text
    assert 'href="https://ocw.mit.edu/"' in text
    assert 'rel="noopener noreferrer"' in text
    assert "C:/study/reference.pdf" in text
    assert 'href="C:/study/reference.pdf"' not in text
    assert "+ Add Resource" in text
    assert '<form' in text.lower()
    assert "Read only" not in text


def test_notes_and_resources_read_failures_degrade_without_secret_details():
    class FailingService:
        def notes_workspace(self, **kwargs):
            raise RuntimeError("SECRET-NOTES-STORAGE")
        def resources_workspace(self, **kwargs):
            raise RuntimeError("SECRET-RESOURCES-STORAGE")
    client = _web_app(FailingService()).test_client()
    notes_text = client.get("/notes").get_data(as_text=True)
    resources_text = client.get("/resources").get_data(as_text=True)
    assert "Notes are temporarily unavailable" in notes_text
    assert "SECRET-NOTES-STORAGE" not in notes_text
    assert "Resources are temporarily unavailable" in resources_text
    assert "SECRET-RESOURCES-STORAGE" not in resources_text


def test_web_app_creation_keeps_notes_and_resources_backends_lazy(tmp_path):
    import os, subprocess, sys
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
    result = subprocess.run([sys.executable,"-c",script],cwd=tmp_path,env={**os.environ,"PYTHONPATH":str(repo_root)},text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
