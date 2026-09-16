from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.domain.resources2_models import (
    CreateResource2Command,
    ResourceAssessmentLink,
    ResourceCourseLink,
    ResourceDocumentLink,
    ResourceNoteLink,
    ResourceProgressCommand,
    ResourceTopicLink,
    UpdateResource2Command,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.resources2_repository import (
    Resources2ConflictError,
    SQLiteResources2Repository,
)
from personal_learning_assistant.services.resource_legacy_reconciliation import (
    reconcile_legacy_resources,
)
from personal_learning_assistant.services.resources2_service import (
    Resources2Service,
    normalize_canonical_uri,
)


NOW = "2026-09-16T13:00:00Z"


def _env(tmp_path: Path):
    db = tmp_path / "resources.db"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (NOW, NOW),
    )
    connection.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,confidence,"
        "raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t1','c1','LU','lu',1,'not_started',NULL,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    connection.execute(
        "INSERT INTO vaults(id,name,root_path,path_key,enabled,last_scanned_at,created_at,updated_at) "
        "VALUES ('v1','Vault','/tmp/vault','vault',1,NULL,?,?)",
        (NOW, NOW),
    )
    connection.execute(
        "INSERT INTO note_metadata(id,vault_id,relative_path,path_key,title,note_type,confidence,"
        "revision_status,pinned_at,archived_at,trashed_at,source_hash,file_mtime_ns,"
        "frontmatter_extra_json,created_at,updated_at) "
        "VALUES ('n1','v1','LU.md','lu.md','LU Notes','concept',NULL,'unreviewed',"
        "NULL,NULL,NULL,'hash-note',1,'{}',?,?)",
        (NOW, NOW),
    )
    connection.execute(
        "INSERT INTO assessments(id,course_id,assessment_type,title,due_on,due_time,status,"
        "weight_bps,max_points_milli,earned_points_milli,description,created_at,updated_at,deleted_at) "
        "VALUES ('a1','c1','quiz','Quiz 1',NULL,NULL,'pending',NULL,NULL,NULL,'',?,?,NULL)",
        (NOW, NOW),
    )
    connection.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,content_hash,"
        "size_bytes,source_timestamp,extraction_status,extraction_version,extraction_error,"
        "created_at,updated_at) "
        "VALUES ('d1','pdf',NULL,'project-documents/lu.pdf','application/pdf','hash-doc',10,NULL,"
        "'pending','',NULL,?,?)",
        (NOW, NOW),
    )
    repo = SQLiteResources2Repository(connection)
    service = Resources2Service(repo, now=lambda: NOW)
    return db, connection, repo, service


def _create(service, **overrides):
    kwargs = dict(
        title="MIT LU Lecture",
        resource_type="youtube_lecture",
        canonical_uri="https://youtu.be/abc123?si=tracking",
        provider="youtube",
        external_id="abc123",
        course_links=(ResourceCourseLink("c1", "supporting"),),
        topic_links=(ResourceTopicLink("t1", "explicit", 0.95),),
        note_links=(ResourceNoteLink("n1", "summary"),),
        assessment_links=(ResourceAssessmentLink("a1", "preparation"),),
        document_links=(ResourceDocumentLink("d1", "transcript"),),
    )
    kwargs.update(overrides)
    return service.create_resource(CreateResource2Command(**kwargs))


def test_canonical_url_removes_tracking_and_normalizes_youtube():
    assert normalize_canonical_uri(
        "https://youtu.be/abc123?si=xyz&utm_source=test"
    ) == "https://www.youtube.com/watch?v=abc123"


def test_create_typed_resource_with_all_relationships(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    details = _create(service)
    assert details.resource.resource_type == "youtube_lecture"
    assert details.resource.canonical_uri == "https://www.youtube.com/watch?v=abc123"
    assert details.resource.status == "not_started"
    assert details.relations.courses[0].course_id == "c1"
    assert details.relations.topics[0].topic_id == "t1"
    assert details.relations.notes[0].note_id == "n1"
    assert details.relations.assessments[0].assessment_id == "a1"
    assert details.relations.documents[0].document_id == "d1"
    assert len(connection.execute("SELECT * FROM outbox_events").fetchall()) == 1
    connection.close()


def test_resource_requires_real_identity(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    with pytest.raises(ValueError, match="requires canonical_uri"):
        service.create_resource(
            CreateResource2Command(title="No Identity", resource_type="other")
        )
    assert repo.list_resources() == ()
    connection.close()


def test_duplicate_provider_external_id_is_reviewed_not_merged(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    first = _create(service)
    with pytest.raises(Resources2ConflictError, match="potential duplicate"):
        _create(service, title="Copy")
    assert len(repo.list_resources()) == 1
    assert repo.list_resources()[0].id == first.resource.id
    connection.close()


def test_same_document_hash_is_duplicate_candidate(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    first = _create(service, provider="", external_id=None, canonical_uri="https://example.edu/a")
    connection.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,content_hash,"
        "size_bytes,source_timestamp,extraction_status,extraction_version,extraction_error,"
        "created_at,updated_at) VALUES ('d2','pdf',NULL,'copy.pdf','application/pdf','hash-doc',10,"
        "NULL,'pending','',NULL,?,?)",
        (NOW, NOW),
    )
    candidates = service.get_duplicate_candidates(
        title="Different",
        canonical_uri="https://example.edu/b",
        provider="",
        external_id=None,
        document_ids=("d2",),
    )
    assert candidates[0].resource_id == first.resource.id
    assert "document_content_hash" in candidates[0].reasons
    connection.close()


def test_allow_duplicate_never_auto_merges_canonical_url(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    _create(service, provider="", external_id=None, document_links=(), canonical_uri="https://example.edu/x")
    second = _create(
        service,
        title="Intentional second entry",
        provider="",
        external_id=None,
        document_links=(),
        canonical_uri="https://example.edu/x",
        allow_duplicate=True,
    )
    assert len(repo.list_resources()) == 2
    assert second.resource.title == "Intentional second entry"
    connection.close()


def test_invalid_relationship_rolls_back_entire_create(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        service.create_resource(
            CreateResource2Command(
                title="Bad link",
                resource_type="pdf",
                canonical_uri="https://example.edu/bad.pdf",
                course_links=(ResourceCourseLink("missing", "supporting"),),
            )
        )
    assert repo.list_resources() == ()
    connection.close()


def test_replace_relationships_is_transactional(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    details = _create(service)
    command = CreateResource2Command(
        title=details.resource.title,
        resource_type=details.resource.resource_type,
        canonical_uri=details.resource.canonical_uri,
        course_links=(ResourceCourseLink("c1", "primary"),),
        topic_links=(),
        note_links=(),
        assessment_links=(),
        document_links=(),
    )
    relations = service.replace_relationships(details.resource.id, command)
    assert relations.courses == (ResourceCourseLink("c1", "primary"),)
    assert relations.topics == ()
    connection.close()


def test_progress_history_is_append_only_and_materialized_status_follows_latest_time(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    details = _create(service)
    rid = details.resource.id
    service.record_progress(
        ResourceProgressCommand(
            rid, "in_progress", "2026-09-16T10:00:00Z",
            value=20, max_value=100, unit="percent", position="20%",
        )
    )
    service.complete_resource(
        rid,
        occurred_at="2026-09-16T12:00:00Z",
        value=100,
        max_value=100,
        unit="percent",
    )
    # Backfilled older event must not replace the current completed state.
    final = service.record_progress(
        ResourceProgressCommand(
            rid, "paused", "2026-09-16T11:00:00Z", note="historical correction"
        )
    )
    assert final.resource.status == "completed"
    assert final.resource.completed_at == "2026-09-16T12:00:00Z"
    assert len(final.history) == 3
    connection.close()


def test_reopen_preserves_history_and_clears_materialized_completion(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    rid = _create(service).resource.id
    service.complete_resource(rid, occurred_at="2026-09-16T12:00:00Z")
    reopened = service.reopen_resource(
        rid, occurred_at="2026-09-16T13:00:00Z", note="review again"
    )
    assert reopened.resource.status == "in_progress"
    assert reopened.resource.completed_at is None
    assert [event.status for event in reopened.history] == ["completed", "in_progress"]
    connection.close()


def test_invalid_progress_value_does_not_write(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    rid = _create(service).resource.id
    before = connection.execute(
        "SELECT COUNT(*) FROM resource_progress_events"
    ).fetchone()[0]
    with pytest.raises(ValueError, match="cannot exceed"):
        service.record_progress(
            ResourceProgressCommand(
                rid, "in_progress", NOW, value=11, max_value=10
            )
        )
    after = connection.execute(
        "SELECT COUNT(*) FROM resource_progress_events"
    ).fetchone()[0]
    assert before == after == 0
    connection.close()


def test_rating_search_archive_trash_restore(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    details = _create(service)
    rid = details.resource.id
    rated = service.set_rating(rid, 5, "Very useful")
    assert rated.resource.rating == 5
    assert service.search_resources("mit")[0].id == rid
    archived = service.archive_resource(rid)
    assert archived.archived_at == NOW
    trashed = service.trash_resource(rid)
    assert trashed.deleted_at == NOW
    restored = service.restore_resource(rid)
    assert restored.deleted_at is None
    assert restored.archived_at is None
    connection.close()


def test_zero_byte_legacy_file_is_preserved_and_reported(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    path = tmp_path / "resources.json"
    path.write_bytes(b"")
    before = path.read_bytes()
    report = reconcile_legacy_resources(path, repo)
    assert report.source_status == "empty_file"
    assert report.source_byte_count == 0
    assert report.validated_legacy_records == 0
    assert path.read_bytes() == before
    connection.close()


def test_invalid_legacy_json_is_not_fabricated_as_empty_list(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    path = tmp_path / "resources.json"
    path.write_text("{bad", encoding="utf-8")
    report = reconcile_legacy_resources(path, repo)
    assert report.source_status == "invalid_json"
    assert report.validated_legacy_records == 0
    connection.close()


def test_valid_legacy_rows_are_previewed_not_auto_imported(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    path = tmp_path / "resources.json"
    path.write_text(
        json.dumps(
            [{"title": "Lecture", "type": "video", "link": "https://example.edu/1",
              "status": "Not Started"}]
        ),
        encoding="utf-8",
    )
    report = reconcile_legacy_resources(path, repo)
    assert report.validated_legacy_records == 1
    assert report.legacy_decisions[0].decision == "create_resource"
    assert repo.list_resources() == ()
    connection.close()


def test_registered_documents_and_notes_are_candidates_not_auto_resources(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    path = tmp_path / "resources.json"
    path.write_bytes(b"")
    report = reconcile_legacy_resources(path, repo)
    assert len(report.document_candidates) == 1
    assert report.document_candidates[0].source_id == "d1"
    assert len(report.note_candidates) == 1
    assert report.note_candidates[0].source_id == "n1"
    assert repo.list_resources() == ()
    connection.close()


def test_integrity_and_foreign_keys_after_resource_commands(tmp_path):
    _db, connection, repo, service = _env(tmp_path)
    _create(service)
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()
