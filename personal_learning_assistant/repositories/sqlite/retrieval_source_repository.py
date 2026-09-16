"""Read model over authoritative SQLite knowledge chunks for Phase 5.8."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.ingestion.chunking import decode_chunk_type
from personal_learning_assistant.repositories.sqlite.connection import transaction


class RetrievalSourceRepositoryError(RuntimeError):
    pass


_REQUIRED = {
    "knowledge_documents": {
        "id", "content_hash", "extraction_status", "extraction_version",
    },
    "knowledge_chunks": {
        "id", "document_id", "ordinal", "page_number", "chunk_type",
        "text_hash", "extraction_version", "chunk_text",
    },
    "resource_documents": {"resource_id", "document_id", "role"},
    "resources": {"id", "provider", "external_id", "deleted_at"},
    "resource_courses": {"resource_id", "course_id", "role"},
    "resource_topics": {"resource_id", "topic_id", "relation_source"},
    "index_jobs": {
        "id", "document_id", "content_hash", "index_kind", "model_name",
        "model_version", "index_version", "status", "created_at", "started_at",
        "completed_at", "failed_at", "error",
    },
}


def _canonical(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class SQLiteRetrievalSourceRepository:
    def __init__(self, connection: sqlite3.Connection, *, validate_schema: bool = True):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        if validate_schema:
            self.validate_schema()

    def validate_schema(self):
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing_tables = sorted(set(_REQUIRED) - tables)
        if missing_tables:
            raise RetrievalSourceRepositoryError(
                "Phase 5.8 required tables missing: {}".format(
                    ", ".join(missing_tables)
                )
            )
        issues = []
        for table, required in _REQUIRED.items():
            columns = {
                str(row[1])
                for row in self.connection.execute(
                    'PRAGMA table_info("{}")'.format(table)
                )
            }
            missing = sorted(required - columns)
            if missing:
                issues.append("{}:[{}]".format(table, ",".join(missing)))
        if issues:
            raise RetrievalSourceRepositoryError(
                "Phase 5.8 schema incomplete: {}".format("; ".join(issues))
            )

    def _document_relations(self):
        resource_ids = defaultdict(set)
        course_ids = defaultdict(set)
        topic_ids = defaultdict(set)
        providers = defaultdict(set)

        rows = self.connection.execute(
            "SELECT rd.document_id,r.id AS resource_id,r.provider "
            "FROM resource_documents rd "
            "JOIN resources r ON r.id=rd.resource_id "
            "WHERE r.deleted_at IS NULL"
        ).fetchall()
        for row in rows:
            document_id = str(row["document_id"])
            resource_id = str(row["resource_id"])
            resource_ids[document_id].add(resource_id)
            provider = str(row["provider"] or "").strip()
            if provider:
                providers[document_id].add(provider)

        rows = self.connection.execute(
            "SELECT rd.document_id,rc.course_id "
            "FROM resource_documents rd "
            "JOIN resources r ON r.id=rd.resource_id AND r.deleted_at IS NULL "
            "JOIN resource_courses rc ON rc.resource_id=rd.resource_id"
        ).fetchall()
        for row in rows:
            course_ids[str(row["document_id"])].add(str(row["course_id"]))

        rows = self.connection.execute(
            "SELECT rd.document_id,rt.topic_id "
            "FROM resource_documents rd "
            "JOIN resources r ON r.id=rd.resource_id AND r.deleted_at IS NULL "
            "JOIN resource_topics rt ON rt.resource_id=rd.resource_id"
        ).fetchall()
        for row in rows:
            topic_ids[str(row["document_id"])].add(str(row["topic_id"]))

        return resource_ids, course_ids, topic_ids, providers

    def active_records(self):
        resource_ids, course_ids, topic_ids, providers = self._document_relations()
        rows = self.connection.execute(
            "SELECT c.id AS chunk_id,c.document_id,c.ordinal,c.page_number,"
            "c.chunk_type,c.text_hash,c.extraction_version,c.chunk_text,"
            "d.content_hash "
            "FROM knowledge_chunks c "
            "JOIN knowledge_documents d ON d.id=c.document_id "
            "WHERE d.extraction_status='completed' "
            "AND d.extraction_version<>'' "
            "AND c.extraction_version=d.extraction_version "
            "AND c.chunk_text IS NOT NULL "
            "ORDER BY c.document_id,c.ordinal,c.id"
        ).fetchall()

        records = []
        for row in rows:
            kind, locator = decode_chunk_type(str(row["chunk_type"]))
            document_id = str(row["document_id"])
            local_topics = {
                str(item)
                for item in locator.get("local_topic_ids", [])
                if str(item).strip()
            }
            # Per-chunk local topics are more precise than shared document links.
            effective_topics = local_topics or topic_ids.get(document_id, set())
            records.append(
                {
                    "chunk_id": str(row["chunk_id"]),
                    "document_id": document_id,
                    "ordinal": int(row["ordinal"]),
                    "page_number": (
                        None if row["page_number"] is None else int(row["page_number"])
                    ),
                    "chunk_kind": kind,
                    "locator": dict(locator),
                    "text_hash": str(row["text_hash"]),
                    "content_hash": str(row["content_hash"]),
                    "extraction_version": str(row["extraction_version"]),
                    "text": str(row["chunk_text"]),
                    "resource_ids": tuple(sorted(resource_ids.get(document_id, set()))),
                    "course_ids": tuple(sorted(course_ids.get(document_id, set()))),
                    "topic_ids": tuple(sorted(effective_topics)),
                    "providers": tuple(sorted(providers.get(document_id, set()))),
                }
            )
        return tuple(records)

    def source_fingerprint(self):
        compact = []
        for item in self.active_records():
            compact.append(
                {
                    "chunk_id": item["chunk_id"],
                    "document_id": item["document_id"],
                    "ordinal": item["ordinal"],
                    "text_hash": item["text_hash"],
                    "content_hash": item["content_hash"],
                    "extraction_version": item["extraction_version"],
                    "resource_ids": item["resource_ids"],
                    "course_ids": item["course_ids"],
                    "topic_ids": item["topic_ids"],
                    "providers": item["providers"],
                    "locator": item["locator"],
                }
            )
        raw = _canonical(compact).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def handoff_counts(self):
        counts = {"pending": 0, "completed": 0, "stale": 0, "failed": 0}
        rows = self.connection.execute(
            "SELECT status,COUNT(*) AS n FROM index_jobs "
            "WHERE index_kind='retrieval_handoff' GROUP BY status"
        ).fetchall()
        for row in rows:
            counts[str(row["status"])] = int(row["n"])
        return counts

    def acknowledge_build(
        self,
        *,
        generation_id: str,
        semantic_enabled: bool,
        model_name: str,
        model_version: str,
        now: str,
    ):
        records = self.active_records()
        by_document = {}
        for item in records:
            by_document[item["document_id"]] = item["content_hash"]

        index_kind = "hybrid_retrieval" if semantic_enabled else "lexical_retrieval"
        with transaction(self.connection, immediate=True):
            for document_id, content_hash in sorted(by_document.items()):
                self.connection.execute(
                    "UPDATE index_jobs SET status='stale',error=? "
                    "WHERE document_id=? AND index_kind IN "
                    "('lexical_retrieval','hybrid_retrieval') "
                    "AND index_version<>? "
                    "AND status IN ('pending','running','completed')",
                    (
                        "superseded by Phase 5.8 retrieval generation",
                        document_id,
                        generation_id,
                    ),
                )
                job_id = hashlib.sha256(
                    (
                        "phase5.8|{}|{}|{}|{}|{}|{}".format(
                            document_id,
                            content_hash,
                            index_kind,
                            model_name,
                            model_version,
                            generation_id,
                        )
                    ).encode("utf-8")
                ).hexdigest()
                existing = self.connection.execute(
                    "SELECT id FROM index_jobs "
                    "WHERE document_id=? AND content_hash=? AND index_kind=? "
                    "AND model_name=? AND model_version=? AND index_version=?",
                    (
                        document_id,
                        content_hash,
                        index_kind,
                        model_name,
                        model_version,
                        generation_id,
                    ),
                ).fetchone()
                if existing is None:
                    self.connection.execute(
                        "INSERT INTO index_jobs "
                        "(id,document_id,content_hash,index_kind,model_name,"
                        "model_version,index_version,status,created_at,started_at,"
                        "completed_at,failed_at,error) "
                        "VALUES (?,?,?,?,?,?,?,'completed',?,?,?,NULL,NULL)",
                        (
                            job_id,
                            document_id,
                            content_hash,
                            index_kind,
                            model_name,
                            model_version,
                            generation_id,
                            now,
                            now,
                            now,
                        ),
                    )
                else:
                    self.connection.execute(
                        "UPDATE index_jobs SET status='completed',completed_at=?,"
                        "failed_at=NULL,error=NULL WHERE id=?",
                        (now, str(existing[0])),
                    )
                self.connection.execute(
                    "UPDATE index_jobs SET status='completed',completed_at=?,"
                    "failed_at=NULL,error=NULL "
                    "WHERE document_id=? AND content_hash=? "
                    "AND index_kind='retrieval_handoff' AND status='pending'",
                    (now, document_id, content_hash),
                )
