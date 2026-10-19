from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


NOW = "2026-09-29T00:00:00Z"


@pytest.fixture
def library_db(tmp_path):
    """Real canonical schema; no user files or external services."""
    path = tmp_path / "academic.db"
    apply_migrations(path)
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA foreign_keys=ON")
        for cid, code in (("c1", "MA103N"), ("c2", "UC100N")):
            con.execute("INSERT INTO courses(id,code,name,created_at,updated_at) VALUES (?,?,?,?,?)",
                        (cid, code, "Course " + cid, NOW, NOW))
        con.execute("INSERT INTO topics(id,course_id,name,normalized_name,created_at,updated_at) "
                    "VALUES ('t1','c1','LU factorisation','lu factorisation',?,?)", (NOW, NOW))
        for rid, title, archived, deleted in (
            ("r1", "Lecture collection", None, None),
            ("r2", "Reference text", None, None),
            ("ra", "Archived resource", NOW, None),
            ("rd", "Deleted resource", None, NOW),
        ):
            con.execute("INSERT INTO resources(id,resource_type,title,canonical_uri,provider,status,"
                        "created_at,updated_at,archived_at,deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (rid, "pdf", title, "https://example.org/lecture", "Instructor", "in_progress",
                         NOW, NOW, archived, deleted))
        for did, status, path_key in (
            ("d1", "completed", "lectures/lecture.pdf"),
            ("d2", "pending", "lectures/slides.pptx"),
            ("d0", "failed", "C:\\private\\MA103N-loose.pdf"),
            ("da", "pending", "hidden/archived.pdf"),
            ("dd", "pending", "hidden/deleted.pdf"),
        ):
            con.execute("INSERT INTO knowledge_documents(id,kind,path_key,mime_type,content_hash,"
                        "extraction_status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (did, "pdf", path_key, "application/pdf", "a" * 64, status, NOW, NOW))
        for rid, did in (("r1", "d1"), ("r1", "d2"), ("r2", "d1"), ("ra", "da"), ("rd", "dd")):
            con.execute("INSERT INTO resource_documents VALUES (?,?,'source')", (rid, did))
        for rid, cid in (("r1", "c1"), ("r1", "c2"), ("r2", "c2")):
            con.execute("INSERT INTO resource_courses VALUES (?,?,'supporting')", (rid, cid))
        con.execute("INSERT INTO resource_topics VALUES ('r1','t1','explicit',1.0)")
        con.execute("INSERT INTO vaults(id,name,root_path,path_key,created_at,updated_at) "
                    "VALUES ('v1','Vault','/private/vault','vault',?,?)", (NOW, NOW))
        con.execute("INSERT INTO note_metadata(id,vault_id,relative_path,path_key,title,source_hash,"
                    "file_mtime_ns,created_at,updated_at) VALUES "
                    "('n1','v1','LU.md','lu.md','My LU explanation',?,1,?,?)", ("b" * 64, NOW, NOW))
        con.execute("INSERT INTO resource_notes VALUES ('r1','n1','summary')")
    return path


def service(path):
    from personal_learning_assistant.services.learning_library_service import LearningLibraryService
    return LearningLibraryService(database_path=path)


def query(**kwargs):
    from personal_learning_assistant.domain.learning_library_models import LibraryQuery
    return LibraryQuery(**kwargs)


def fingerprint(path):
    with sqlite3.connect(path) as con:
        return (tuple(con.iterdump()), con.execute("PRAGMA journal_mode").fetchone()[0])


def test_groups_multi_document_resources_and_never_resurrects_hidden_documents(library_db):
    page = service(library_db).list_items(query())
    assert [i.key for i in page.items] == ["resource:r1", "document:d0", "resource:r2"]
    assert page.total == 3
    assert page.items[0].document_count == 2
    assert page.items[0].note_count == 1
    assert page.items[1].title == "MA103N-loose.pdf"
    assert page.items[1].learning_status is None
    assert page.items[1].courses == ()


def test_course_filter_uses_explicit_relationships_not_document_filename(library_db):
    page = service(library_db).list_items(query(course_id="c1"))
    assert [i.key for i in page.items] == ["resource:r1"]
    assert service(library_db).list_items(query(course_id="c1", item_kind="document")).state == "no_matches"
    assert service(library_db).list_items(query(course_id="c1' OR 1=1 --")).total == 0


def test_pagination_is_stable_and_filters_precede_limit(library_db):
    s = service(library_db)
    assert [s.list_items(query(page=n, page_size=1)).items[0].key for n in (1, 2, 3)] == [
        "resource:r1", "document:d0", "resource:r2"]
    assert s.list_items(query(item_kind="resource", page=2, page_size=1)).items[0].key == "resource:r2"
    assert s.list_items(query(page=99)).state == "no_matches"


def test_detail_preserves_shared_documents_and_recorded_relationships(library_db):
    detail = service(library_db).resource_detail("r1")
    assert {d.document_id for d in detail.documents} == {"d1", "d2"}
    assert [c.id for c in detail.courses] == ["c1", "c2"]
    assert [t.id for t in detail.topics] == ["t1"]
    assert [n.label for n in detail.notes] == ["My LU explanation"]
    assert detail.external_url == "https://example.org/lecture"
    assert {d.document_id for d in service(library_db).resource_detail("r2").documents} == {"d1"}
    assert detail.documents[0].open_target == "/knowledge/item/d1"


@pytest.mark.parametrize("rid", ["missing", "ra", "rd"])
def test_hidden_or_unknown_resource_is_not_found(library_db, rid):
    from personal_learning_assistant.services.learning_library_service import LibraryNotFoundError
    with pytest.raises(LibraryNotFoundError):
        service(library_db).resource_detail(rid)


@pytest.mark.parametrize("kwargs", [
    {"page": 0}, {"page": -1}, {"page": True}, {"page": 1.5},
    {"page_size": 0}, {"page_size": 101}, {"item_kind": "notes"},
])
def test_invalid_query_rejected(kwargs):
    with pytest.raises(ValueError):
        query(**kwargs)


def test_models_are_immutable(library_db):
    item = service(library_db).list_items(query()).items[0]
    with pytest.raises(FrozenInstanceError):
        item.title = "Changed"


def test_empty_schema_is_ready_not_unavailable(tmp_path):
    path = tmp_path / "empty.db"
    apply_migrations(path)
    page = service(path).list_items(query())
    assert page.state == "empty"
    assert page.items == ()


@pytest.mark.parametrize("kind", ["missing", "incompatible", "corrupt"])
def test_unavailable_database_is_neither_created_nor_migrated(tmp_path, kind):
    from personal_learning_assistant.services.learning_library_service import LibraryUnavailableError
    path = tmp_path / "absent-parent" / "academic.db"
    if kind != "missing":
        path.parent.mkdir()
        if kind == "corrupt":
            path.write_bytes(b"not sqlite")
        else:
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE resources(id TEXT)")
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(LibraryUnavailableError):
        service(path).list_items(query())
    assert (path.read_bytes() if path.exists() else None) == before
    if kind == "missing":
        assert not path.parent.exists()


def test_reads_preserve_schema_rows_journal_and_unrelated_sources(library_db, tmp_path):
    source = tmp_path / "lecture.pdf"
    source.write_bytes(b"untouched fixture")
    before = fingerprint(library_db)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    service(library_db).list_items(query())
    service(library_db).resource_detail("r1")
    assert fingerprint(library_db) == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,evil", "file:///private/secret", "https://user:secret@example.org/", "https://example.org/?token=secret"])
def test_unsafe_or_credential_bearing_external_links_are_not_activated(library_db, url):
    with sqlite3.connect(library_db) as con:
        con.execute("UPDATE resources SET canonical_uri=? WHERE id='r1'", (url,))
    assert service(library_db).resource_detail("r1").external_url is None


def test_reads_do_not_call_external_or_mutation_boundaries(library_db, monkeypatch):
    import socket
    from personal_learning_assistant.services.resources2_service import Resources2Service
    from personal_learning_assistant.repositories.sqlite import migration_runner
    def forbidden(*args, **kwargs):
        raise AssertionError("Library invoked a forbidden boundary")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(Resources2Service, "create_resource", forbidden)
    monkeypatch.setattr(migration_runner, "apply_migrations", forbidden)
    assert service(library_db).list_items(query()).total == 3
    assert service(library_db).resource_detail("r1").documents


def test_duplicate_relationship_roles_do_not_duplicate_material(library_db):
    with sqlite3.connect(library_db) as con:
        con.execute("INSERT INTO resource_documents VALUES ('r1','d1','supplement')")
        con.execute("INSERT INTO resource_courses VALUES ('r1','c1','primary')")
        con.execute("INSERT INTO resource_notes VALUES ('r1','n1','related')")
    detail = service(library_db).resource_detail('r1')
    assert len(detail.documents) == 2
    assert len(detail.courses) == 2
    assert len(detail.notes) == 1
    assert service(library_db).list_items(query()).items[0].document_count == 2


def test_sort_uses_timestamp_then_case_insensitive_display_title_then_id(library_db):
    with sqlite3.connect(library_db) as con:
        con.execute("UPDATE resources SET title='alpha' WHERE id='r1'")
        con.execute("UPDATE resources SET title='ALPHA' WHERE id='r2'")
        con.execute("UPDATE knowledge_documents SET updated_at='2026-09-30' WHERE id='d0'")
    assert [i.key for i in service(library_db).list_items(query()).items] == [
        'document:d0', 'resource:r1', 'resource:r2']
