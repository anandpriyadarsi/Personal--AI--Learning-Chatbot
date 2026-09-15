"""SQLite knowledge-registry repository for Phase 5.1.

The repository requires an explicit sqlite3.Connection. Importing this module
never opens a database or touches knowledge sources. All mutations are confined
to the already-existing Phase 3 metadata/journal/outbox tables.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.domain.knowledge_registry_models import (
    DocumentRegistrationResult,
    IndexJobRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    OperationJournalRecord,
    OutboxEventRecord,
    RegistryReadiness,
)
from personal_learning_assistant.repositories.sqlite.connection import transaction


class KnowledgeRegistryError(RuntimeError):
    pass


class KnowledgeRegistrySchemaError(KnowledgeRegistryError):
    pass


class KnowledgeRegistryConflictError(KnowledgeRegistryError):
    pass


_REQUIRED_COLUMNS = {
    "knowledge_documents": {
        "id", "kind", "canonical_uri", "path_key", "mime_type", "content_hash",
        "size_bytes", "source_timestamp", "extraction_status", "extraction_version",
        "extraction_error", "created_at", "updated_at",
    },
    "knowledge_chunks": {
        "id", "document_id", "ordinal", "page_number", "char_start", "char_end",
        "chunk_type", "text_hash", "extraction_version", "chunk_text",
    },
    "index_jobs": {
        "id", "document_id", "content_hash", "index_kind", "model_name",
        "model_version", "index_version", "status", "created_at", "started_at",
        "completed_at", "failed_at", "error",
    },
    "operation_journal": {
        "id", "kind", "target_path", "before_hash", "after_hash", "state",
        "error", "created_at", "updated_at",
    },
    "outbox_events": {
        "id", "event_type", "entity_type", "entity_id", "payload_json",
        "created_at", "processed_at", "failed_at", "error", "attempts",
    },
}


def _row_document(row: sqlite3.Row) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        id=str(row["id"]),
        kind=str(row["kind"]),
        canonical_uri=None if row["canonical_uri"] is None else str(row["canonical_uri"]),
        path_key=None if row["path_key"] is None else str(row["path_key"]),
        mime_type=str(row["mime_type"]),
        content_hash=str(row["content_hash"]),
        size_bytes=None if row["size_bytes"] is None else int(row["size_bytes"]),
        source_timestamp=None if row["source_timestamp"] is None else str(row["source_timestamp"]),
        extraction_status=str(row["extraction_status"]),
        extraction_version=str(row["extraction_version"]),
        extraction_error=None if row["extraction_error"] is None else str(row["extraction_error"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_chunk(row: sqlite3.Row) -> KnowledgeChunkRecord:
    return KnowledgeChunkRecord(
        id=str(row["id"]),
        document_id=str(row["document_id"]),
        ordinal=int(row["ordinal"]),
        page_number=None if row["page_number"] is None else int(row["page_number"]),
        char_start=None if row["char_start"] is None else int(row["char_start"]),
        char_end=None if row["char_end"] is None else int(row["char_end"]),
        chunk_type=str(row["chunk_type"]),
        text_hash=str(row["text_hash"]),
        extraction_version=str(row["extraction_version"]),
        chunk_text=None if row["chunk_text"] is None else str(row["chunk_text"]),
    )


def _row_index_job(row: sqlite3.Row) -> IndexJobRecord:
    return IndexJobRecord(
        id=str(row["id"]),
        document_id=str(row["document_id"]),
        content_hash=str(row["content_hash"]),
        index_kind=str(row["index_kind"]),
        model_name=str(row["model_name"]),
        model_version=str(row["model_version"]),
        index_version=str(row["index_version"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        started_at=None if row["started_at"] is None else str(row["started_at"]),
        completed_at=None if row["completed_at"] is None else str(row["completed_at"]),
        failed_at=None if row["failed_at"] is None else str(row["failed_at"]),
        error=None if row["error"] is None else str(row["error"]),
    )


def _row_journal(row: sqlite3.Row) -> OperationJournalRecord:
    return OperationJournalRecord(
        id=str(row["id"]),
        kind=str(row["kind"]),
        target_path=None if row["target_path"] is None else str(row["target_path"]),
        before_hash=None if row["before_hash"] is None else str(row["before_hash"]),
        after_hash=None if row["after_hash"] is None else str(row["after_hash"]),
        state=str(row["state"]),
        error=None if row["error"] is None else str(row["error"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_outbox(row: sqlite3.Row) -> OutboxEventRecord:
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except json.JSONDecodeError as error:
        raise KnowledgeRegistryConflictError(
            "outbox payload_json is corrupt for event {}".format(row["id"])
        ) from error
    if not isinstance(payload, Mapping):
        raise KnowledgeRegistryConflictError(
            "outbox payload_json must decode to an object for event {}".format(row["id"])
        )
    return OutboxEventRecord(
        id=str(row["id"]),
        event_type=str(row["event_type"]),
        entity_type=str(row["entity_type"]),
        entity_id=str(row["entity_id"]),
        payload=dict(payload),
        created_at=str(row["created_at"]),
        processed_at=None if row["processed_at"] is None else str(row["processed_at"]),
        failed_at=None if row["failed_at"] is None else str(row["failed_at"]),
        error=None if row["error"] is None else str(row["error"]),
        attempts=int(row["attempts"]),
    )


class SQLiteKnowledgeRegistryRepository:
    """Metadata registry over the existing Phase 3 knowledge schema."""

    def __init__(self, connection: sqlite3.Connection, *, validate_schema: bool = True):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        if validate_schema:
            self.validate_schema()

    def validate_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        missing_tables = sorted(set(_REQUIRED_COLUMNS) - tables)
        if missing_tables:
            raise KnowledgeRegistrySchemaError(
                "Phase 5.1 required tables are missing: {}".format(
                    ", ".join(missing_tables)
                )
            )
        problems = []
        for table, required in _REQUIRED_COLUMNS.items():
            columns = {
                str(row[1]) for row in self.connection.execute(
                    'PRAGMA table_info("{}")'.format(table)
                ).fetchall()
            }
            missing = sorted(required - columns)
            if missing:
                problems.append("{}:[{}]".format(table, ",".join(missing)))
        if problems:
            raise KnowledgeRegistrySchemaError(
                "Phase 5.1 schema columns are incomplete: {}".format("; ".join(problems))
            )

    def readiness(self) -> RegistryReadiness:
        before = self.connection.total_changes
        self.validate_schema()
        integrity = tuple(
            str(row[0])
            for row in self.connection.execute("PRAGMA integrity_check").fetchall()
        )
        foreign_keys = tuple(
            tuple(row)
            for row in self.connection.execute("PRAGMA foreign_key_check").fetchall()
        )
        after = self.connection.total_changes
        return RegistryReadiness(
            tables=tuple(sorted(_REQUIRED_COLUMNS)),
            integrity_check=integrity,
            foreign_key_violations=foreign_keys,
            total_changes_before=before,
            total_changes_after=after,
        )

    def get_document(self, document_id: str) -> Optional[KnowledgeDocumentRecord]:
        row = self.connection.execute(
            "SELECT * FROM knowledge_documents WHERE id=?", (document_id,)
        ).fetchone()
        return None if row is None else _row_document(row)

    def list_documents(self) -> Tuple[KnowledgeDocumentRecord, ...]:
        rows = self.connection.execute(
            "SELECT * FROM knowledge_documents ORDER BY created_at,id"
        ).fetchall()
        return tuple(_row_document(row) for row in rows)

    def _identity_candidates(
        self, canonical_uri: Optional[str], path_key: Optional[str]
    ) -> Tuple[KnowledgeDocumentRecord, ...]:
        clauses = []
        args = []
        if canonical_uri:
            clauses.append("canonical_uri=?")
            args.append(canonical_uri)
        if path_key:
            clauses.append("path_key=?")
            args.append(path_key)
        if not clauses:
            return ()
        rows = self.connection.execute(
            "SELECT * FROM knowledge_documents WHERE " + " OR ".join(clauses),
            tuple(args),
        ).fetchall()
        records = tuple(_row_document(row) for row in rows)
        ids = {item.id for item in records}
        if len(ids) > 1:
            raise KnowledgeRegistryConflictError(
                "document identity resolves to multiple registry rows"
            )
        return records

    def register_document(
        self,
        *,
        document_id: str,
        kind: str,
        canonical_uri: Optional[str],
        path_key: Optional[str],
        mime_type: str,
        content_hash: str,
        size_bytes: Optional[int],
        source_timestamp: Optional[str],
        now: str,
        outbox_event: Optional[Mapping[str, Any]] = None,
    ) -> DocumentRegistrationResult:
        existing_candidates = self._identity_candidates(canonical_uri, path_key)
        existing = existing_candidates[0] if existing_candidates else None
        if existing is not None and existing.id != document_id:
            raise KnowledgeRegistryConflictError(
                "stable document identity differs from existing registry ID"
            )

        with transaction(self.connection, immediate=True):
            if existing is None:
                self.connection.execute(
                    "INSERT INTO knowledge_documents "
                    "(id,kind,canonical_uri,path_key,mime_type,content_hash,size_bytes,"
                    "source_timestamp,extraction_status,extraction_version,extraction_error,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        document_id, kind, canonical_uri, path_key, mime_type,
                        content_hash, size_bytes, source_timestamp, "pending", "", None,
                        now, now,
                    ),
                )
                action = "created"
            else:
                content_changed = existing.content_hash != content_hash
                action = "updated" if content_changed else "matched"
                if content_changed:
                    extraction_status = "pending"
                    extraction_version = ""
                    extraction_error = None
                else:
                    extraction_status = existing.extraction_status
                    extraction_version = existing.extraction_version
                    extraction_error = existing.extraction_error
                self.connection.execute(
                    "UPDATE knowledge_documents SET kind=?,canonical_uri=?,path_key=?,"
                    "mime_type=?,content_hash=?,size_bytes=?,source_timestamp=?,"
                    "extraction_status=?,extraction_version=?,extraction_error=?,updated_at=? "
                    "WHERE id=?",
                    (
                        kind, canonical_uri, path_key, mime_type, content_hash, size_bytes,
                        source_timestamp, extraction_status, extraction_version,
                        extraction_error, now, document_id,
                    ),
                )
            if outbox_event is not None and action != "matched":
                self._insert_outbox(outbox_event)

        record = self.get_document(document_id)
        if record is None:
            raise KnowledgeRegistryConflictError("document disappeared after registration")
        return DocumentRegistrationResult(document=record, action=action)

    def list_chunks(
        self, document_id: str, extraction_version: Optional[str] = None
    ) -> Tuple[KnowledgeChunkRecord, ...]:
        if extraction_version is None:
            rows = self.connection.execute(
                "SELECT * FROM knowledge_chunks WHERE document_id=? "
                "ORDER BY extraction_version,ordinal,id",
                (document_id,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM knowledge_chunks WHERE document_id=? AND extraction_version=? "
                "ORDER BY ordinal,id",
                (document_id, extraction_version),
            ).fetchall()
        return tuple(_row_chunk(row) for row in rows)

    def replace_chunks(
        self,
        *,
        document_id: str,
        extraction_version: str,
        chunks: Sequence[Mapping[str, Any]],
        now: str,
        outbox_event: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[KnowledgeChunkRecord, ...]:
        if self.get_document(document_id) is None:
            raise KnowledgeRegistryConflictError("cannot attach chunks to an unknown document")
        ordinals = [int(item["ordinal"]) for item in chunks]
        if len(set(ordinals)) != len(ordinals):
            raise KnowledgeRegistryConflictError("chunk ordinals must be unique per extraction")
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "DELETE FROM knowledge_chunks WHERE document_id=? AND extraction_version=?",
                (document_id, extraction_version),
            )
            for item in chunks:
                self.connection.execute(
                    "INSERT INTO knowledge_chunks "
                    "(id,document_id,ordinal,page_number,char_start,char_end,chunk_type,"
                    "text_hash,extraction_version,chunk_text) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(item["id"]), document_id, int(item["ordinal"]),
                        item.get("page_number"), item.get("char_start"), item.get("char_end"),
                        str(item.get("chunk_type") or "text"), str(item["text_hash"]),
                        extraction_version, item.get("chunk_text"),
                    ),
                )
            self.connection.execute(
                "UPDATE knowledge_documents SET extraction_status='completed',"
                "extraction_version=?,extraction_error=NULL,updated_at=? WHERE id=?",
                (extraction_version, now, document_id),
            )
            if outbox_event is not None:
                self._insert_outbox(outbox_event)
        return self.list_chunks(document_id, extraction_version)

    def get_index_job(self, job_id: str) -> Optional[IndexJobRecord]:
        row = self.connection.execute(
            "SELECT * FROM index_jobs WHERE id=?", (job_id,)
        ).fetchone()
        return None if row is None else _row_index_job(row)

    def schedule_index_job(
        self,
        *,
        job_id: str,
        document_id: str,
        content_hash: str,
        index_kind: str,
        model_name: str,
        model_version: str,
        index_version: str,
        now: str,
    ) -> Tuple[IndexJobRecord, str]:
        row = self.connection.execute(
            "SELECT * FROM index_jobs WHERE document_id=? AND content_hash=? "
            "AND index_kind=? AND model_name=? AND model_version=? AND index_version=?",
            (document_id, content_hash, index_kind, model_name, model_version, index_version),
        ).fetchone()
        if row is not None:
            return _row_index_job(row), "matched"
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "INSERT INTO index_jobs "
                "(id,document_id,content_hash,index_kind,model_name,model_version,index_version,"
                "status,created_at,started_at,completed_at,failed_at,error) "
                "VALUES (?,?,?,?,?,?,?,'pending',?,NULL,NULL,NULL,NULL)",
                (
                    job_id, document_id, content_hash, index_kind, model_name,
                    model_version, index_version, now,
                ),
            )
        result = self.get_index_job(job_id)
        if result is None:
            raise KnowledgeRegistryConflictError("index job disappeared after insert")
        return result, "created"

    def transition_index_job(
        self,
        job_id: str,
        *,
        status: str,
        now: str,
        error: Optional[str] = None,
    ) -> IndexJobRecord:
        current = self.get_index_job(job_id)
        if current is None:
            raise KnowledgeRegistryConflictError("unknown index job")
        allowed = {
            "pending": {"running", "failed"},
            "running": {"completed", "failed"},
            "completed": set(),
            "failed": set(),
        }
        if status not in allowed.get(current.status, set()):
            raise KnowledgeRegistryConflictError(
                "invalid index-job transition {} -> {}".format(current.status, status)
            )
        started_at = current.started_at
        completed_at = current.completed_at
        failed_at = current.failed_at
        if status == "running":
            started_at = now
        elif status == "completed":
            completed_at = now
        elif status == "failed":
            failed_at = now
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE index_jobs SET status=?,started_at=?,completed_at=?,failed_at=?,error=? "
                "WHERE id=?",
                (status, started_at, completed_at, failed_at, error, job_id),
            )
        result = self.get_index_job(job_id)
        assert result is not None
        return result

    def create_journal_entry(
        self,
        *,
        operation_id: str,
        kind: str,
        target_path: Optional[str],
        before_hash: Optional[str],
        now: str,
    ) -> OperationJournalRecord:
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "INSERT INTO operation_journal "
                "(id,kind,target_path,before_hash,after_hash,state,error,created_at,updated_at) "
                "VALUES (?,?,?,?,NULL,'planned',NULL,?,?)",
                (operation_id, kind, target_path, before_hash, now, now),
            )
        return self.get_journal_entry(operation_id)

    def get_journal_entry(self, operation_id: str) -> OperationJournalRecord:
        row = self.connection.execute(
            "SELECT * FROM operation_journal WHERE id=?", (operation_id,)
        ).fetchone()
        if row is None:
            raise KnowledgeRegistryConflictError("unknown operation journal entry")
        return _row_journal(row)

    def list_open_journal_entries(self) -> Tuple[OperationJournalRecord, ...]:
        rows = self.connection.execute(
            "SELECT * FROM operation_journal WHERE state NOT IN ('completed','failed') "
            "ORDER BY created_at,id"
        ).fetchall()
        return tuple(_row_journal(row) for row in rows)

    def transition_journal_entry(
        self,
        operation_id: str,
        *,
        state: str,
        now: str,
        after_hash: Optional[str] = None,
        error: Optional[str] = None,
    ) -> OperationJournalRecord:
        current = self.get_journal_entry(operation_id)
        allowed = {
            "planned": {"file_applied", "database_committed", "failed"},
            "file_applied": {"database_committed", "failed"},
            "database_committed": {"completed", "failed"},
            "completed": set(),
            "failed": set(),
        }
        if state not in allowed.get(current.state, set()):
            raise KnowledgeRegistryConflictError(
                "invalid operation-journal transition {} -> {}".format(
                    current.state, state
                )
            )
        next_hash = current.after_hash if after_hash is None else after_hash
        next_error = error if state == "failed" else None
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE operation_journal SET after_hash=?,state=?,error=?,updated_at=? WHERE id=?",
                (next_hash, state, next_error, now, operation_id),
            )
        return self.get_journal_entry(operation_id)

    def _insert_outbox(self, event: Mapping[str, Any]) -> None:
        payload_json = json.dumps(
            dict(event.get("payload") or {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.connection.execute(
            "INSERT INTO outbox_events "
            "(id,event_type,entity_type,entity_id,payload_json,created_at,processed_at,"
            "failed_at,error,attempts) VALUES (?,?,?,?,?,?,NULL,NULL,NULL,0)",
            (
                str(event["id"]), str(event["event_type"]), str(event["entity_type"]),
                str(event["entity_id"]), payload_json, str(event["created_at"]),
            ),
        )

    def enqueue_outbox(self, event: Mapping[str, Any]) -> OutboxEventRecord:
        with transaction(self.connection, immediate=True):
            self._insert_outbox(event)
        return self.get_outbox_event(str(event["id"]))

    def get_outbox_event(self, event_id: str) -> OutboxEventRecord:
        row = self.connection.execute(
            "SELECT * FROM outbox_events WHERE id=?", (event_id,)
        ).fetchone()
        if row is None:
            raise KnowledgeRegistryConflictError("unknown outbox event")
        return _row_outbox(row)

    def list_pending_outbox(self, limit: int = 100) -> Tuple[OutboxEventRecord, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = self.connection.execute(
            "SELECT * FROM outbox_events WHERE processed_at IS NULL AND failed_at IS NULL "
            "ORDER BY created_at,id LIMIT ?",
            (int(limit),),
        ).fetchall()
        return tuple(_row_outbox(row) for row in rows)

    def mark_outbox_processed(self, event_id: str, *, now: str) -> OutboxEventRecord:
        current = self.get_outbox_event(event_id)
        if current.processed_at is not None or current.failed_at is not None:
            raise KnowledgeRegistryConflictError("outbox event is already terminal")
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE outbox_events SET processed_at=?,attempts=attempts+1,error=NULL WHERE id=?",
                (now, event_id),
            )
        return self.get_outbox_event(event_id)

    def mark_outbox_failed(
        self, event_id: str, *, now: str, error: str
    ) -> OutboxEventRecord:
        current = self.get_outbox_event(event_id)
        if current.processed_at is not None or current.failed_at is not None:
            raise KnowledgeRegistryConflictError("outbox event is already terminal")
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE outbox_events SET failed_at=?,attempts=attempts+1,error=? WHERE id=?",
                (now, str(error), event_id),
            )
        return self.get_outbox_event(event_id)
