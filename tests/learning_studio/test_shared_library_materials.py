"""Shared original files: no duplicate source authority or inferred MIT placement."""
from io import BytesIO

import pytest

from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.repositories.sqlite.learning_library_repository import document_title
from personal_learning_assistant.services.learning_library_service import LearningLibraryService
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.ui.web.learning_materials import canonical_document_titles

from .helpers import catalogue, source_pdf


@pytest.fixture
def workspace(tmp_path):
    library = NativeDocumentLibrary(tmp_path / "native_library", autostart=False)
    course_catalogue = catalogue()
    studio = LearningStudioService(
        tmp_path / "learning_studio.sqlite3",
        source_loader=lambda _source: source_pdf(),
        catalogue_loader=lambda: course_catalogue,
    )
    app = create_app({
        "TESTING": True,
        "NATIVE_LIBRARY_SERVICE": library,
        "LEARNING_STUDIO_SERVICE_FACTORY": lambda: studio,
    })
    yield library, app, app.test_client()
    library.close()


def test_file_browser_uses_existing_folder_ids_and_original_display_names(workspace):
    library, _, client = workspace
    root = library.bootstrap_academics([
        {"id": "math-real-id", "code": "MA103N", "name": "Linear Algebra"}
    ])
    subject = root["subjects"][0]
    doc = library.upload(BytesIO(b"Eigenvectors and bases."),
                         "original-lecture.txt", folder_id=subject["folder_id"])
    library.update(doc["id"], display_name="Eigenvectors Lecture 04")
    home = client.get("/learning")
    assert home.status_code == 200
    assert b"Original study materials" in home.data
    assert b"Semester 1" in home.data
    semester = client.get("/learning/materials?folder_id=" + root["semester"]["folder_id"])
    assert b"Linear Algebra" in semester.data
    subject_page = client.get("/learning/materials?folder_id=" + subject["folder_id"])
    assert subject_page.status_code == 200
    assert b"Eigenvectors Lecture 04" in subject_page.data
    assert ("/library/files/" + doc["id"] + "/open").encode() in subject_page.data
    assert library.get(doc["id"])["folder_id"] == subject["folder_id"]


def test_mit_folder_action_is_explicit_csrf_guarded_and_idempotent(workspace):
    library, app, client = workspace
    assert not any(f["name"] == "MIT Course Materials" for f in library.children()["items"])
    assert client.post("/learning/materials/mit-folder").status_code == 403
    assert library.children()["total"] == 0
    token = app.extensions["learning_studio_csrf"]
    created = client.post("/learning/materials/mit-folder",
                          data={"csrf_token": token})
    assert created.status_code == 303
    created_again = client.post("/learning/materials/mit-folder",
                                data={"csrf_token": token})
    assert created_again.status_code == 303
    assert library.children()["total"] == 1
    mit = library.children()["items"][0]
    assert mit["name"] == "MIT Course Materials"
    assert created.location.endswith("folder_id=" + mit["id"])
    document = library.upload(BytesIO(b"Course materials"),
                              "MIT Lecture 01.txt", folder_id=mit["id"])
    assert b"MIT Lecture 01.txt" in client.get(created.location).data
    library.update(document["id"], display_name="Lecture 1 - Introduction")
    assert b"Lecture 1 - Introduction" in client.get(created.location).data


def test_unavailable_store_does_not_initialize_or_mutate_it(tmp_path):
    app = create_app({"TESTING": True})
    before = set(tmp_path.iterdir())
    result = app.test_client().get("/learning/materials")
    assert result.status_code == 200
    assert b"original-file Library is unavailable" in result.data or b"Original-file Library is unavailable" in result.data
    assert set(tmp_path.iterdir()) == before


def test_browse_invalid_folder_and_page_never_move_or_remove_files(workspace):
    library, _, client = workspace
    saved = library.upload(BytesIO(b"Preserve me"), "saved.txt")
    assert client.get("/learning/materials?folder_id=does-not-exist").status_code == 404
    assert client.get("/learning/materials?page=0").status_code == 400
    assert client.get("/learning/materials?page=not-a-number").status_code == 400
    assert client.get("/learning/materials?folder_id=a&folder_id=b").status_code == 400
    assert library.original(saved["id"]).read_bytes() == b"Preserve me"
    library.trash(saved["id"])
    assert b"saved.txt" not in client.get("/learning/materials").data


def test_content_addressed_names_are_not_exposed_and_manual_names_win():
    digest = "a" * 64
    assert document_title("documents/" + digest + ".pdf") == "Unnamed PDF document"
    assert document_title("documents/" + digest[:32]) == "Unnamed document"
    assert document_title("lectures/LU-Decomposition.pdf") == "LU-Decomposition.pdf"
    names = lambda pairs: {("doc", digest): "Actual Lecture.pdf"}
    service = LearningLibraryService(native_title_lookup=names)
    opaque = {"id": "doc", "path_key": "documents/" + digest + ".pdf",
              "content_hash": digest, "title": "Unnamed PDF document"}
    assert service._linked_names([opaque])[("doc", digest)] == "Actual Lecture.pdf"
    assert not service._linked_names([{**opaque, "title": "My custom title"}])


def test_source_id_and_hash_both_required_to_recover_native_name(workspace):
    library, _, _ = workspace
    saved = library.upload(BytesIO(b"Exact academic source"), "Verified Lecture.txt")
    with library.connection(write=True) as con:
        con.execute("INSERT INTO source_links VALUES (?,?,?,?,?,?)",
                    (saved["id"], "canonical", "academic-doc-id", saved["sha256"],
                     "migrated", "test:verified"))
    with create_app({"TESTING": True}).app_context():
        assert canonical_document_titles(library, [
            ("academic-doc-id", saved["sha256"])
        ]) == {("academic-doc-id", saved["sha256"]): "Verified Lecture.txt"}
        assert canonical_document_titles(library, [
            ("other-document", saved["sha256"]),
            ("academic-doc-id", "b" * 64),
        ]) == {}
