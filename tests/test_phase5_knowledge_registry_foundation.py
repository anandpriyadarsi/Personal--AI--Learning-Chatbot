from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.domain.knowledge_registry_models import KnowledgeChunkInput
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    KnowledgeRegistryConflictError,
    KnowledgeRegistrySchemaError,
    SQLiteKnowledgeRegistryRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.knowledge_registry_service import KnowledgeRegistryService
from personal_learning_assistant.services.operation_coordination_service import OperationCoordinationService


NOW = "2026-09-15T16:00:00Z"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _repo(tmp_path: Path):
    db = tmp_path / "registry.db"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return db, connection, SQLiteKnowledgeRegistryRepository(connection)


def _service(repo):
    return KnowledgeRegistryService(repo, now=lambda: NOW)


def test_schema_is_already_present_in_phase3_migrations(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    result = repo.readiness()
    assert result.passed is True
    assert result.integrity_check == ("ok",)
    assert result.foreign_key_violations == ()
    connection.close()


def test_incomplete_schema_is_rejected():
    connection = sqlite3.connect(":memory:")
    with pytest.raises(KnowledgeRegistrySchemaError):
        SQLiteKnowledgeRegistryRepository(connection)
    connection.close()


def test_document_registration_is_stable_and_idempotent(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = _service(repo)
    first = service.register_document(
        kind="pdf",
        path_key="knowledge/documents/a.pdf",
        content_hash=_hash("a"),
        mime_type="application/pdf",
        size_bytes=10,
    )
    second = service.register_document(
        kind="pdf",
        path_key="knowledge\\documents\\a.pdf",
        content_hash=_hash("a"),
        mime_type="application/pdf",
        size_bytes=10,
    )
    assert first.action == "created"
    assert second.action == "matched"
    assert first.document.id == second.document.id
    assert len(repo.list_documents()) == 1
    assert len(repo.list_pending_outbox()) == 1
    connection.close()


def test_content_change_preserves_id_and_invalidates_extraction(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = _service(repo)
    first = service.register_document(
        kind="markdown", path_key="vault/a.md", content_hash=_hash("v1")
    )
    service.record_extraction(
        first.document.id,
        extraction_version="extractor-v1",
        chunks=[KnowledgeChunkInput(ordinal=0, text_hash=_hash("chunk"), chunk_text="chunk")],
    )
    changed = service.register_document(
        kind="markdown", path_key="vault/a.md", content_hash=_hash("v2")
    )
    assert changed.document.id == first.document.id
    assert changed.action == "updated"
    assert changed.document.extraction_status == "pending"
    assert changed.document.extraction_version == ""
    connection.close()


def test_source_identity_requires_uri_or_path(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    with pytest.raises(ValueError, match="canonical_uri or path_key"):
        _service(repo).register_document(kind="pdf", content_hash=_hash("x"))
    connection.close()


def test_invalid_content_hash_is_rejected_before_write(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    before = connection.total_changes
    with pytest.raises(ValueError, match="SHA-256"):
        _service(repo).register_document(
            kind="pdf", path_key="a.pdf", content_hash="not-a-hash"
        )
    assert connection.total_changes == before
    connection.close()


def test_chunks_are_deterministic_and_replace_same_extraction_version(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = _service(repo)
    document = service.register_document(
        kind="text", path_key="a.txt", content_hash=_hash("source")
    ).document
    first = service.record_extraction(
        document.id,
        extraction_version="v1",
        chunks=[
            KnowledgeChunkInput(ordinal=0, text_hash=_hash("a"), chunk_text="a"),
            KnowledgeChunkInput(ordinal=1, text_hash=_hash("b"), chunk_text="b"),
        ],
    )
    second = service.record_extraction(
        document.id,
        extraction_version="v1",
        chunks=[KnowledgeChunkInput(ordinal=0, text_hash=_hash("new"), chunk_text="new")],
    )
    assert len(first) == 2
    assert len(second) == 1
    assert second[0].ordinal == 0
    assert second[0].chunk_text == "new"
    connection.close()


def test_duplicate_chunk_ordinals_roll_back(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = _service(repo)
    document = service.register_document(
        kind="text", path_key="a.txt", content_hash=_hash("source")
    ).document
    before = connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
    with pytest.raises(KnowledgeRegistryConflictError, match="ordinals"):
        service.record_extraction(
            document.id,
            extraction_version="v1",
            chunks=[
                KnowledgeChunkInput(ordinal=0, text_hash=_hash("a")),
                KnowledgeChunkInput(ordinal=0, text_hash=_hash("b")),
            ],
        )
    after = connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
    assert before == after == 0
    connection.close()


def test_index_job_schedule_is_idempotent_and_state_machine_is_strict(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = _service(repo)
    document = service.register_document(
        kind="pdf", path_key="a.pdf", content_hash=_hash("pdf")
    ).document
    job1, action1 = service.schedule_index_job(
        document.id, index_kind="fts", index_version="1"
    )
    job2, action2 = service.schedule_index_job(
        document.id, index_kind="fts", index_version="1"
    )
    assert action1 == "created"
    assert action2 == "matched"
    assert job1.id == job2.id
    running = repo.transition_index_job(job1.id, status="running", now=NOW)
    assert running.status == "running"
    completed = repo.transition_index_job(job1.id, status="completed", now=NOW)
    assert completed.status == "completed"
    with pytest.raises(KnowledgeRegistryConflictError):
        repo.transition_index_job(job1.id, status="running", now=NOW)
    connection.close()


def test_operation_journal_supports_file_plus_database_protocol(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = OperationCoordinationService(repo, now=lambda: NOW)
    item = service.begin_operation(kind="note_update", target_path="vault/a.md", before_hash=_hash("old"))
    assert item.state == "planned"
    item = service.mark_file_applied(item.id, after_hash=_hash("new"))
    assert item.state == "file_applied"
    item = service.mark_database_committed(item.id)
    assert item.state == "database_committed"
    item = service.complete_operation(item.id)
    assert item.state == "completed"
    assert repo.list_open_journal_entries() == ()
    connection.close()


def test_operation_journal_rejects_unsafe_skips(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = OperationCoordinationService(repo, now=lambda: NOW)
    item = service.begin_operation(kind="note_update")
    with pytest.raises(KnowledgeRegistryConflictError):
        service.complete_operation(item.id)
    connection.close()


def test_outbox_is_canonical_machine_readable_and_terminal(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = OperationCoordinationService(repo, now=lambda: NOW)
    event = service.enqueue_event(
        event_type="knowledge.changed",
        entity_type="knowledge_document",
        entity_id="doc-1",
        payload={"b": 2, "a": 1},
    )
    assert event.payload == {"a": 1, "b": 2}
    assert len(service.pending_events()) == 1
    done = service.mark_event_processed(event.id)
    assert done.processed_at == NOW
    assert done.attempts == 1
    assert service.pending_events() == ()
    with pytest.raises(KnowledgeRegistryConflictError):
        service.mark_event_failed(event.id, error="late")
    connection.close()


def test_failed_outbox_event_is_terminal(tmp_path):
    _db, connection, repo = _repo(tmp_path)
    service = OperationCoordinationService(repo, now=lambda: NOW)
    event = service.enqueue_event(
        event_type="index.requested",
        entity_type="knowledge_document",
        entity_id="doc-2",
    )
    failed = service.mark_event_failed(event.id, error="boom")
    assert failed.failed_at == NOW
    assert failed.error == "boom"
    assert failed.attempts == 1
    assert service.pending_events() == ()
    connection.close()


def test_registry_readiness_is_read_only(tmp_path):
    db, connection, repo = _repo(tmp_path)
    before_bytes = db.read_bytes()
    before_changes = connection.total_changes
    readiness = repo.readiness()
    assert readiness.passed is True
    assert connection.total_changes == before_changes
    connection.close()
    assert db.read_bytes() == before_bytes
