from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.json.note_repository import LegacyJsonNoteRepository
from personal_learning_assistant.repositories.json.resource_repository import LegacyJsonResourceRepository
from personal_learning_assistant.services.notes_service import NotesService
from personal_learning_assistant.services.resource_service import ResourceService
from personal_learning_assistant.services.notes_resources_web_service import (
    NotesResourcesWebNotFoundError,
    NotesResourcesWebService,
    NotesResourcesWebUnavailableError,
    NotesResourcesWebValidationError,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_notes(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {"title": "Duplicate", "topic": "Linear Algebra", "difficulty": "Hard", "content": "LU body"},
                {"title": "Duplicate", "topic": "Linear Algebra", "difficulty": "Medium", "content": "Rank body"},
                {"title": "Atoms", "topic": "Chemistry", "difficulty": "Easy", "content": "Chemistry body"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


def _seed_resources(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {"title": "MIT 18.06", "type": "Course", "link": "https://ocw.mit.edu/", "status": "In Progress"},
                {"title": "Local PDF", "type": "PDF", "link": "C:/study/reference.pdf", "status": "Not Started"},
                {"title": "Unsafe", "type": "Website", "link": "javascript:alert(1)", "status": "Not Started"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


def _service(tmp_path):
    notes_path = tmp_path / "notes.json"
    resources_path = tmp_path / "resources.json"
    _seed_notes(notes_path)
    _seed_resources(resources_path)
    return (
        NotesResourcesWebService(
            NotesService(LegacyJsonNoteRepository(notes_path)),
            ResourceService(LegacyJsonResourceRepository(resources_path)),
        ),
        notes_path,
        resources_path,
    )


def test_notes_workspace_preserves_positions_through_search_and_filters(tmp_path):
    service, _, _ = _service(tmp_path)
    workspace = service.notes_workspace(search="rank", topic="Linear Algebra", difficulty="")
    assert workspace["query"] == {"search": "rank", "topic": "Linear Algebra", "difficulty": ""}
    assert [(item["position"], item["title"]) for item in workspace["notes"]] == [(2, "Duplicate")]


def test_blank_notes_search_lists_filtered_notes_instead_of_legacy_empty_search(tmp_path):
    service, _, _ = _service(tmp_path)
    workspace = service.notes_workspace(search="", topic="Linear Algebra", difficulty="")
    assert [item["position"] for item in workspace["notes"]] == [1, 2]


def test_resources_workspace_keeps_only_http_links_active(tmp_path):
    service, _, _ = _service(tmp_path)
    workspace = service.resources_workspace()
    by_title = {item["title"]: item for item in workspace["resources"]}
    assert by_title["MIT 18.06"]["link_url"] == "https://ocw.mit.edu/"
    assert by_title["Local PDF"]["link_url"] == ""
    assert by_title["Unsafe"]["link_url"] == ""


def test_duplicate_note_titles_are_updated_by_position_not_title(tmp_path):
    service, notes_path, _ = _service(tmp_path)
    service.update_note(2, "Duplicate", "Linear Algebra", "Medium", "Updated second note")
    stored = json.loads(notes_path.read_text(encoding="utf-8"))
    assert stored[0]["content"] == "LU body"
    assert stored[1]["content"] == "Updated second note"
    assert set(stored[1]) == {"title", "topic", "difficulty", "content"}


def test_invalid_positions_and_validation_leave_stores_unchanged(tmp_path):
    service, notes_path, resources_path = _service(tmp_path)
    notes_before = _hash(notes_path)
    resources_before = _hash(resources_path)
    with pytest.raises(NotesResourcesWebValidationError):
        service.create_note("   ", "Math", "Hard", "body")
    with pytest.raises(NotesResourcesWebNotFoundError):
        service.update_note(99, "Missing", "Math", "Hard", "body")
    with pytest.raises(NotesResourcesWebValidationError):
        service.update_resource_status(1, "Paused")
    with pytest.raises(NotesResourcesWebNotFoundError):
        service.update_resource_status(99, "Completed")
    assert _hash(notes_path) == notes_before
    assert _hash(resources_path) == resources_before


def test_explicit_create_can_initialize_zero_byte_stores(tmp_path):
    notes_path = tmp_path / "notes.json"
    resources_path = tmp_path / "resources.json"
    notes_path.write_bytes(b"")
    resources_path.write_bytes(b"")
    service = NotesResourcesWebService(
        NotesService(LegacyJsonNoteRepository(notes_path)),
        ResourceService(LegacyJsonResourceRepository(resources_path)),
    )
    service.create_note("First", "", "", "")
    service.create_resource("First resource", "", "")
    assert json.loads(notes_path.read_text(encoding="utf-8"))[0]["title"] == "First"
    assert json.loads(resources_path.read_text(encoding="utf-8"))[0]["title"] == "First resource"


def test_unexpected_storage_errors_are_mapped_to_safe_messages():
    class BrokenNotes:
        def list_notes(self, *args, **kwargs):
            raise RuntimeError("C:/SECRET/notes.json")
    class BrokenResources:
        def list_resources(self, *args, **kwargs):
            raise RuntimeError("C:/SECRET/resources.json")
    service = NotesResourcesWebService(BrokenNotes(), BrokenResources())
    with pytest.raises(NotesResourcesWebUnavailableError) as notes_error:
        service.notes_workspace()
    with pytest.raises(NotesResourcesWebUnavailableError) as resources_error:
        service.resources_workspace()
    assert "SECRET" not in str(notes_error.value)
    assert "SECRET" not in str(resources_error.value)


def _app_with_service(service):
    from personal_learning_assistant.ui.web import create_app
    return create_app({"TESTING": True, "NOTES_RESOURCES_WEB_SERVICE_FACTORY": lambda: service})


def test_notes_get_search_and_post_prg_routes(tmp_path):
    service, notes_path, _ = _service(tmp_path)
    client = _app_with_service(service).test_client()
    before = _hash(notes_path)
    response = client.get("/notes?q=rank&topic=Linear+Algebra")
    assert response.status_code == 200
    assert "Rank body" in response.get_data(as_text=True)
    assert _hash(notes_path) == before
    response = client.post("/notes", data={"title": "New note", "topic": "Math", "difficulty": "Easy", "content": "body"})
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/notes?created=1")
    response = client.post("/notes/2", data={"title": "Updated", "topic": "Math", "difficulty": "Medium", "content": "changed"})
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/notes?updated=1")


def test_notes_route_errors_are_safe(tmp_path):
    service, _, _ = _service(tmp_path)
    client = _app_with_service(service).test_client()
    response = client.post("/notes", data={"title": "   "})
    assert response.status_code == 400
    assert "Enter a title" in response.get_data(as_text=True)
    response = client.post("/notes/999", data={"title": "x"})
    assert response.status_code == 404
    assert "no longer exists" in response.get_data(as_text=True)


def test_resources_get_create_status_and_safe_links(tmp_path):
    service, _, resources_path = _service(tmp_path)
    client = _app_with_service(service).test_client()
    before = _hash(resources_path)
    response = client.get("/resources?q=MIT&type=Course")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="https://ocw.mit.edu/"' in text
    assert 'href="javascript:alert(1)"' not in text
    assert _hash(resources_path) == before
    response = client.post("/resources", data={"title": "Docs", "resource_type": "Website", "link": "https://example.test/"})
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/resources?created=1")
    response = client.post("/resources/1/status", data={"status": "Completed"})
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/resources?updated=1")


def test_routes_do_not_import_legacy_repositories_directly():
    source = (Path(__file__).resolve().parents[1] / "personal_learning_assistant/ui/web/routes.py").read_text(encoding="utf-8")
    assert "repositories.json.note_repository" not in source
    assert "repositories.json.resource_repository" not in source
    assert "main.py" not in source
    assert "input(" not in source
