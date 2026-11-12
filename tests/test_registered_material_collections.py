"""Regression checks for readable grouped Library and MIT Learning Studio views."""
from io import BytesIO
import sqlite3

import pytest

from test_learning_library_read_model import library_db
from personal_learning_assistant.domain.learning_library_models import LibraryQuery
from personal_learning_assistant.services.learning_library_service import LearningLibraryService
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from personal_learning_assistant.ui.web import create_app


def test_registered_mit_collection_uses_provider_and_title_not_substrings(library_db):
    with sqlite3.connect(library_db) as con:
        con.execute("UPDATE resources SET provider='mit_ocw',title='MIT 18.06 L04 — Factorization' WHERE id='r1'")
        con.execute("UPDATE resources SET provider='Instructor',title='Limits worksheet' WHERE id='r2'")
    service = LearningLibraryService(database_path=library_db)
    page = service.list_items(LibraryQuery(collection="mit"))
    assert [item.key for item in page.items] == ["resource:r1"]
    assert page.items[0].title.startswith("MIT 18.06")
    assert service.list_items(LibraryQuery(collection="mit", search="factor")).total == 1
    assert service.list_items(LibraryQuery(collection="mit", search="limits")).total == 0
    assert [item.key for item in service.list_items(LibraryQuery(collection="unlinked")).items] == ["document:d0"]
    assert service.list_items(LibraryQuery(collection="mit", item_kind="document")).total == 0
    with pytest.raises(ValueError, match="collection"):
        LibraryQuery(collection="unknown")


def test_verified_native_filename_replaces_digest_only_when_id_and_hash_match(library_db, tmp_path):
    native = NativeDocumentLibrary(tmp_path / "native_library", autostart=False)
    try:
        stored = native.upload(BytesIO(b"matrix lecture"), "MIT Matrix Lecture.txt", indexing=False)
        with sqlite3.connect(library_db) as con:
            con.execute(
                "UPDATE knowledge_documents SET kind='txt',mime_type='text/plain',"
                "path_key=?,content_hash=? WHERE id='d0'",
                ("documents/" + stored["sha256"], stored["sha256"]),
            )
        with native.connection(write=True) as con:
            con.execute(
                "INSERT INTO source_links VALUES(?,?,?,?,?,?)",
                (stored["id"], "canonical", "d0", stored["sha256"], "migrated", "test:known"),
            )
        app = create_app({
            "TESTING": True,
            "NATIVE_LIBRARY_SERVICE": native,
            "LEARNING_LIBRARY_DATABASE_PATH": library_db,
        })
        client = app.test_client()
        body = client.get("/library?view=registered").get_data(as_text=True)
        assert "MIT Matrix Lecture.txt" in body
        assert "Unnamed document — rename to identify" not in body

        # The canonical source title is still the expected value for renames.
        token = app.extensions["library_rename_csrf"]
        response = client.post(
            "/library/items/document/d0/rename",
            json={"title": "Eigenvalues tutorial",
                  "expected_title": "Unnamed document — rename to identify"},
            headers={"X-Library-CSRF": token},
        )
        assert response.status_code == 200
        renamed = client.get("/library?view=registered").get_data(as_text=True)
        assert "Eigenvalues tutorial" in renamed
        assert native.get(stored["id"])["display_name"] == "MIT Matrix Lecture.txt"
        assert native.original(stored["id"]).read_bytes() == b"matrix lecture"
    finally:
        native.close()


def test_wrong_content_hash_cannot_replace_unknown_title(library_db, tmp_path):
    native = NativeDocumentLibrary(tmp_path / "native_library", autostart=False)
    try:
        stored = native.upload(BytesIO(b"one"), "Wrong source.txt", indexing=False)
        with sqlite3.connect(library_db) as con:
            con.execute(
                "UPDATE knowledge_documents SET path_key=?,content_hash=? WHERE id='d0'",
                ("documents/" + "b"*64, "b"*64),
            )
        with native.connection(write=True) as con:
            con.execute(
                "INSERT INTO source_links VALUES(?,?,?,?,?,?)",
                (stored["id"], "canonical", "d0", stored["sha256"], "migrated", "test:wrong"),
            )
        app = create_app({
            "TESTING": True,
            "NATIVE_LIBRARY_SERVICE": native,
            "LEARNING_LIBRARY_DATABASE_PATH": library_db,
        })
        html = app.test_client().get("/library?view=registered").get_data(as_text=True)
        assert "Wrong source.txt" not in html
        assert "Unnamed document — rename to identify" in html
    finally:
        native.close()


def test_mit_registered_lectures_appear_inside_learning_studio_folder(library_db, tmp_path):
    with sqlite3.connect(library_db) as con:
        con.execute("UPDATE resources SET provider='mit_ocw',title='MIT 18.06 L03 — Inverse Matrices' WHERE id='r1'")
    native = NativeDocumentLibrary(tmp_path / "native_library", autostart=False)
    try:
        folder = native.create_folder("MIT Course Materials")
        doc = native.upload(BytesIO(b"homework"), "Problem Set.txt", folder_id=folder["id"], indexing=False)
        app = create_app({
            "TESTING": True, "NATIVE_LIBRARY_SERVICE": native,
            "LEARNING_LIBRARY_DATABASE_PATH": library_db,
        })
        c = app.test_client()
        html = c.get("/learning/materials?collection=mit").get_data(as_text=True)
        assert "MIT 18.06 L03" in html and "Problem Set.txt" in html
        assert "/library?view=registered&amp;collection=mit" not in html or "registered" in html
        resource_page = c.get("/library?view=registered&collection=mit")
        assert resource_page.status_code == 200
        assert "MIT 18.06 L03" in resource_page.get_data(as_text=True)
        assert "Unlinked documents" not in resource_page.get_data(as_text=True)
        assert native.get(doc["id"])["folder_id"] == folder["id"]
        assert c.get("/library?view=registered&collection=unknown").status_code == 400
    finally:
        native.close()
