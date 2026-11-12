"""Regression tests for Library-backed Learning Studio material browsing."""
from io import BytesIO

import pytest

from personal_learning_assistant.repositories.sqlite.learning_library_repository import document_title
from personal_learning_assistant.services.learning_materials_view import (
    browse_materials, is_mit_material,
)
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from personal_learning_assistant.ui.web import create_app


@pytest.fixture
def library(tmp_path):
    lib = NativeDocumentLibrary(tmp_path / "native_library", autostart=False)
    try:
        yield lib
    finally:
        lib.close()


def test_mit_collection_groups_explicit_sources_and_nested_folders_only(library):
    mit = library.create_folder("MIT Course Materials")
    week = library.create_folder("Week 1", parent_id=mit["id"])
    nested = library.upload(BytesIO(b"original A"), "Lecture 01.txt", folder_id=week["id"], indexing=False)
    named = library.upload(BytesIO(b"original B"), "MIT 6.0001 - Problem Set.txt", indexing=False)
    unrelated = library.upload(BytesIO(b"unrelated"), "Limits and continuity.txt", indexing=False)
    untouched = library.upload(BytesIO(b"ordinary"), "Lecture 02.txt", indexing=False)

    assert is_mit_material("MIT Lecture") and is_mit_material("Massachusetts Institute of Technology")
    assert not is_mit_material("limits") and not is_mit_material("submitted")
    before = {d["id"]: (d["folder_id"], d["subject_id"]) for d in (nested, named, unrelated, untouched)}
    result = browse_materials(library, collection="mit")
    assert result["title"] == "MIT Course Materials"
    assert result["total"] == 2
    assert {d["id"] for d in result["documents"]} == {nested["id"], named["id"]}
    assert {d["id"]: (library.get(d["id"])["folder_id"], library.get(d["id"])["subject_id"])
            for d in (nested, named, unrelated, untouched)} == before
    assert library.original(nested["id"]).read_bytes() == b"original A"
    assert browse_materials(library, folder_id=week["id"])["documents"][0]["display_name"] == "Lecture 01.txt"


def test_learning_materials_uses_renamed_original_not_storage_identity(library):
    folder = library.create_folder("Notes")
    doc = library.upload(BytesIO(b"real notes"), "original.txt", folder_id=folder["id"], indexing=False)
    library.update(doc["id"], display_name="Eigenvalues lecture.txt")
    page = browse_materials(library, folder_id=folder["id"])
    assert page["documents"][0]["display_name"] == "Eigenvalues lecture.txt"
    assert "original.txt" == page["documents"][0]["original_name"]
    assert library.original(doc["id"]).read_bytes() == b"real notes"


def test_learning_studio_folder_and_mit_routes_render_original_names(library):
    folder = library.create_folder("MIT Course Materials")
    doc = library.upload(BytesIO(b"module source"), "Source notes.txt", folder_id=folder["id"], indexing=False)
    app = create_app({"TESTING": True, "NATIVE_LIBRARY_SERVICE": library})
    client = app.test_client()
    root = client.get("/learning/materials")
    assert root.status_code == 200
    assert "MIT Course Materials" in root.get_data(as_text=True)
    mit = client.get("/learning/materials?collection=mit")
    assert mit.status_code == 200
    html = mit.get_data(as_text=True)
    assert "Source notes.txt" in html and f"/library/files/{doc['id']}/open" in html
    assert f"/library/files/{doc['id']}/learning" in html
    assert client.get("/learning/materials?folder_id=" + folder["id"]).status_code == 200
    assert client.get("/learning/materials?collection=wrong").status_code == 400
    assert client.get("/learning/materials?page=0").status_code == 400
    assert client.get("/learning/materials?page=1&page=2").status_code == 400


def test_source_titles_never_display_content_hashes():
    digest = "a" * 64
    assert document_title("documents/" + digest + ".pdf") == "Unnamed PDF — rename to identify"
    assert document_title(digest[:32]) == "Unnamed document — rename to identify"
    assert document_title("https://example.com/lecture_03.pdf") == "lecture_03.pdf"


def test_local_browse_links_open_native_folders_without_removing_legacy_projection():
    app = create_app({"TESTING": True, "WEB_ORIGINAL_LIBRARY": True})
    client = app.test_client()
    response = client.get("/library?view=browse")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/library/files")
    # The registered projection remains a separately addressable GET route.
    assert client.get("/library?view=registered").status_code != 302
