"""SQLite repository for Phase 5.5 Resources 2 Core.

Requires an explicit sqlite3.Connection and operates only on the existing
Phase 3 Resources 2 tables. Source/PDF/Markdown bytes never enter SQLite here.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.domain.resources2_models import (
    DuplicateCandidate,
    ResourceAssessmentLink,
    ResourceCourseLink,
    ResourceDocumentLink,
    ResourceNoteLink,
    ResourceProgressEvent,
    ResourceRecord,
    ResourceRelations,
    ResourceTopicLink,
)
from personal_learning_assistant.repositories.sqlite.connection import transaction


class Resources2RepositoryError(RuntimeError):
    pass


class Resources2SchemaError(Resources2RepositoryError):
    pass


class Resources2ConflictError(Resources2RepositoryError):
    pass


class Resources2NotFoundError(Resources2RepositoryError):
    pass


_REQUIRED_COLUMNS = {
    "resources": {
        "id", "resource_type", "title", "canonical_uri", "provider",
        "external_id", "status", "rating", "quality_note", "created_at",
        "updated_at", "completed_at", "archived_at", "deleted_at",
    },
    "resource_courses": {"resource_id", "course_id", "role"},
    "resource_topics": {
        "resource_id", "topic_id", "relation_source", "confidence",
    },
    "resource_notes": {"resource_id", "note_id", "role"},
    "resource_assessments": {"resource_id", "assessment_id", "role"},
    "resource_documents": {"resource_id", "document_id", "role"},
    "resource_progress_events": {
        "id", "resource_id", "occurred_at", "status", "value", "max_value",
        "unit", "position", "note",
    },
    "knowledge_documents": {"id", "content_hash", "path_key", "canonical_uri", "kind"},
    "note_metadata": {"id", "title", "path_key", "note_type"},
    "courses": {"id"},
    "topics": {"id", "course_id"},
    "assessments": {"id"},
    "outbox_events": {
        "id", "event_type", "entity_type", "entity_id", "payload_json",
        "created_at", "processed_at", "failed_at", "error", "attempts",
    },
}


def _resource(row: sqlite3.Row) -> ResourceRecord:
    return ResourceRecord(
        id=str(row["id"]),
        resource_type=str(row["resource_type"]),
        title=str(row["title"]),
        canonical_uri=None if row["canonical_uri"] is None else str(row["canonical_uri"]),
        provider=str(row["provider"]),
        external_id=None if row["external_id"] is None else str(row["external_id"]),
        status=str(row["status"]),
        rating=None if row["rating"] is None else int(row["rating"]),
        quality_note=str(row["quality_note"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        completed_at=None if row["completed_at"] is None else str(row["completed_at"]),
        archived_at=None if row["archived_at"] is None else str(row["archived_at"]),
        deleted_at=None if row["deleted_at"] is None else str(row["deleted_at"]),
    )


def _progress(row: sqlite3.Row) -> ResourceProgressEvent:
    return ResourceProgressEvent(
        id=str(row["id"]),
        resource_id=str(row["resource_id"]),
        occurred_at=str(row["occurred_at"]),
        status=str(row["status"]),
        value=None if row["value"] is None else float(row["value"]),
        max_value=None if row["max_value"] is None else float(row["max_value"]),
        unit=str(row["unit"]),
        position=str(row["position"]),
        note=str(row["note"]),
    )


class SQLiteResources2Repository:
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
            raise Resources2SchemaError(
                "Phase 5.5 required tables are missing: {}".format(
                    ", ".join(missing_tables)
                )
            )
        problems = []
        for table, required in _REQUIRED_COLUMNS.items():
            columns = {
                str(row[1])
                for row in self.connection.execute(
                    'PRAGMA table_info("{}")'.format(table)
                ).fetchall()
            }
            missing = sorted(required - columns)
            if missing:
                problems.append("{}:[{}]".format(table, ",".join(missing)))
        if problems:
            raise Resources2SchemaError(
                "Phase 5.5 schema columns are incomplete: {}".format(
                    "; ".join(problems)
                )
            )

    def get_resource(self, resource_id: str) -> ResourceRecord:
        row = self.connection.execute(
            "SELECT * FROM resources WHERE id=?", (str(resource_id),)
        ).fetchone()
        if row is None:
            raise Resources2NotFoundError("unknown resource")
        return _resource(row)

    def list_resources(
        self,
        *,
        include_archived: bool = False,
        include_deleted: bool = False,
        resource_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[ResourceRecord, ...]:
        clauses = []
        args = []
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if resource_type is not None:
            clauses.append("resource_type=?")
            args.append(str(resource_type))
        if status is not None:
            clauses.append("status=?")
            args.append(str(status))
        sql = "SELECT * FROM resources"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC,title COLLATE NOCASE,id"
        rows = self.connection.execute(sql, tuple(args)).fetchall()
        return tuple(_resource(row) for row in rows)

    def search_resources(self, text: str) -> Tuple[ResourceRecord, ...]:
        pattern = "%" + str(text or "").casefold() + "%"
        rows = self.connection.execute(
            "SELECT * FROM resources "
            "WHERE deleted_at IS NULL AND ("
            "lower(title) LIKE ? OR lower(provider) LIKE ? "
            "OR lower(COALESCE(canonical_uri,'')) LIKE ? "
            "OR lower(COALESCE(external_id,'')) LIKE ?) "
            "ORDER BY updated_at DESC,title COLLATE NOCASE,id",
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        return tuple(_resource(row) for row in rows)

    def create_resource(
        self,
        *,
        resource_id: str,
        resource_type: str,
        title: str,
        canonical_uri: Optional[str],
        provider: str,
        external_id: Optional[str],
        status: str,
        rating: Optional[int],
        quality_note: str,
        now: str,
        course_links: Sequence[ResourceCourseLink],
        topic_links: Sequence[ResourceTopicLink],
        note_links: Sequence[ResourceNoteLink],
        assessment_links: Sequence[ResourceAssessmentLink],
        document_links: Sequence[ResourceDocumentLink],
        outbox_event: Optional[Mapping[str, object]] = None,
    ) -> ResourceRecord:
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "INSERT INTO resources "
                "(id,resource_type,title,canonical_uri,provider,external_id,status,"
                "rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                (
                    resource_id, resource_type, title, canonical_uri, provider,
                    external_id, status, rating, quality_note, now, now,
                ),
            )
            self._replace_relationships(
                resource_id=resource_id,
                course_links=course_links,
                topic_links=topic_links,
                note_links=note_links,
                assessment_links=assessment_links,
                document_links=document_links,
                replace_existing=False,
            )
            if outbox_event is not None:
                self._insert_outbox(outbox_event)
        return self.get_resource(resource_id)

    def update_resource(
        self,
        *,
        resource_id: str,
        resource_type: str,
        title: str,
        canonical_uri: Optional[str],
        provider: str,
        external_id: Optional[str],
        rating: Optional[int],
        quality_note: str,
        now: str,
        outbox_event: Optional[Mapping[str, object]] = None,
    ) -> ResourceRecord:
        self.get_resource(resource_id)
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE resources SET resource_type=?,title=?,canonical_uri=?,provider=?,"
                "external_id=?,rating=?,quality_note=?,updated_at=? WHERE id=?",
                (
                    resource_type, title, canonical_uri, provider, external_id,
                    rating, quality_note, now, resource_id,
                ),
            )
            if outbox_event is not None:
                self._insert_outbox(outbox_event)
        return self.get_resource(resource_id)

    def set_relationships(
        self,
        *,
        resource_id: str,
        course_links: Sequence[ResourceCourseLink],
        topic_links: Sequence[ResourceTopicLink],
        note_links: Sequence[ResourceNoteLink],
        assessment_links: Sequence[ResourceAssessmentLink],
        document_links: Sequence[ResourceDocumentLink],
        now: str,
        outbox_event: Optional[Mapping[str, object]] = None,
    ) -> ResourceRelations:
        self.get_resource(resource_id)
        with transaction(self.connection, immediate=True):
            self._replace_relationships(
                resource_id=resource_id,
                course_links=course_links,
                topic_links=topic_links,
                note_links=note_links,
                assessment_links=assessment_links,
                document_links=document_links,
                replace_existing=True,
            )
            self.connection.execute(
                "UPDATE resources SET updated_at=? WHERE id=?", (now, resource_id)
            )
            if outbox_event is not None:
                self._insert_outbox(outbox_event)
        return self.get_relations(resource_id)

    def _replace_relationships(
        self,
        *,
        resource_id: str,
        course_links: Sequence[ResourceCourseLink],
        topic_links: Sequence[ResourceTopicLink],
        note_links: Sequence[ResourceNoteLink],
        assessment_links: Sequence[ResourceAssessmentLink],
        document_links: Sequence[ResourceDocumentLink],
        replace_existing: bool,
    ) -> None:
        if replace_existing:
            for table in (
                "resource_courses",
                "resource_topics",
                "resource_notes",
                "resource_assessments",
                "resource_documents",
            ):
                self.connection.execute(
                    "DELETE FROM {} WHERE resource_id=?".format(table),
                    (resource_id,),
                )
        for item in course_links:
            self.connection.execute(
                "INSERT INTO resource_courses(resource_id,course_id,role) VALUES (?,?,?)",
                (resource_id, item.course_id, item.role),
            )
        for item in topic_links:
            self.connection.execute(
                "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
                "VALUES (?,?,?,?)",
                (resource_id, item.topic_id, item.relation_source, item.confidence),
            )
        for item in note_links:
            self.connection.execute(
                "INSERT INTO resource_notes(resource_id,note_id,role) VALUES (?,?,?)",
                (resource_id, item.note_id, item.role),
            )
        for item in assessment_links:
            self.connection.execute(
                "INSERT INTO resource_assessments(resource_id,assessment_id,role) "
                "VALUES (?,?,?)",
                (resource_id, item.assessment_id, item.role),
            )
        for item in document_links:
            self.connection.execute(
                "INSERT INTO resource_documents(resource_id,document_id,role) VALUES (?,?,?)",
                (resource_id, item.document_id, item.role),
            )

    def get_relations(self, resource_id: str) -> ResourceRelations:
        self.get_resource(resource_id)
        courses = tuple(
            ResourceCourseLink(str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT course_id,role FROM resource_courses WHERE resource_id=? "
                "ORDER BY role,course_id",
                (resource_id,),
            )
        )
        topics = tuple(
            ResourceTopicLink(
                str(row[0]),
                str(row[1]),
                None if row[2] is None else float(row[2]),
            )
            for row in self.connection.execute(
                "SELECT topic_id,relation_source,confidence FROM resource_topics "
                "WHERE resource_id=? ORDER BY relation_source,topic_id",
                (resource_id,),
            )
        )
        notes = tuple(
            ResourceNoteLink(str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT note_id,role FROM resource_notes WHERE resource_id=? "
                "ORDER BY role,note_id",
                (resource_id,),
            )
        )
        assessments = tuple(
            ResourceAssessmentLink(str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT assessment_id,role FROM resource_assessments WHERE resource_id=? "
                "ORDER BY role,assessment_id",
                (resource_id,),
            )
        )
        documents = tuple(
            ResourceDocumentLink(str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT document_id,role FROM resource_documents WHERE resource_id=? "
                "ORDER BY role,document_id",
                (resource_id,),
            )
        )
        return ResourceRelations(
            courses=courses,
            topics=topics,
            notes=notes,
            assessments=assessments,
            documents=documents,
        )

    def append_progress(
        self,
        *,
        event: ResourceProgressEvent,
        now: str,
        outbox_event: Optional[Mapping[str, object]] = None,
    ) -> ResourceRecord:
        self.get_resource(event.resource_id)
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "INSERT INTO resource_progress_events "
                "(id,resource_id,occurred_at,status,value,max_value,unit,position,note) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    event.id, event.resource_id, event.occurred_at, event.status,
                    event.value, event.max_value, event.unit, event.position, event.note,
                ),
            )
            latest = self.connection.execute(
                "SELECT status,occurred_at FROM resource_progress_events "
                "WHERE resource_id=? ORDER BY occurred_at DESC,id DESC LIMIT 1",
                (event.resource_id,),
            ).fetchone()
            status = str(latest[0])
            completed_at = str(latest[1]) if status == "completed" else None
            self.connection.execute(
                "UPDATE resources SET status=?,completed_at=?,updated_at=? WHERE id=?",
                (status, completed_at, now, event.resource_id),
            )
            if outbox_event is not None:
                self._insert_outbox(outbox_event)
        return self.get_resource(event.resource_id)

    def get_history(self, resource_id: str) -> Tuple[ResourceProgressEvent, ...]:
        self.get_resource(resource_id)
        rows = self.connection.execute(
            "SELECT * FROM resource_progress_events WHERE resource_id=? "
            "ORDER BY occurred_at,id",
            (resource_id,),
        ).fetchall()
        return tuple(_progress(row) for row in rows)

    def set_lifecycle(
        self,
        resource_id: str,
        *,
        status: str,
        archived_at: Optional[str],
        deleted_at: Optional[str],
        now: str,
        outbox_event: Optional[Mapping[str, object]] = None,
    ) -> ResourceRecord:
        self.get_resource(resource_id)
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE resources SET status=?,archived_at=?,deleted_at=?,updated_at=? "
                "WHERE id=?",
                (status, archived_at, deleted_at, now, resource_id),
            )
            if outbox_event is not None:
                self._insert_outbox(outbox_event)
        return self.get_resource(resource_id)

    def duplicate_candidates(
        self,
        *,
        canonical_uri: Optional[str],
        provider: str,
        external_id: Optional[str],
        document_ids: Sequence[str] = (),
        normalized_title: str = "",
    ) -> Tuple[DuplicateCandidate, ...]:
        reasons: Dict[str, set] = defaultdict(set)

        if provider and external_id:
            rows = self.connection.execute(
                "SELECT id FROM resources WHERE lower(provider)=lower(?) "
                "AND external_id=? AND deleted_at IS NULL",
                (provider, external_id),
            ).fetchall()
            for row in rows:
                reasons[str(row[0])].add("provider_external_id")

        if canonical_uri:
            rows = self.connection.execute(
                "SELECT id FROM resources WHERE canonical_uri=? AND deleted_at IS NULL",
                (canonical_uri,),
            ).fetchall()
            for row in rows:
                reasons[str(row[0])].add("canonical_uri")

        if normalized_title:
            rows = self.connection.execute(
                "SELECT id FROM resources WHERE lower(trim(title))=? "
                "AND lower(trim(provider))=? AND deleted_at IS NULL",
                (normalized_title, provider.casefold().strip()),
            ).fetchall()
            for row in rows:
                reasons[str(row[0])].add("title_provider")

        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            doc_hashes = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT content_hash FROM knowledge_documents WHERE id IN ({})".format(
                        placeholders
                    ),
                    tuple(document_ids),
                ).fetchall()
            }
            if doc_hashes:
                hash_placeholders = ",".join("?" for _ in doc_hashes)
                rows = self.connection.execute(
                    "SELECT DISTINCT rd.resource_id "
                    "FROM resource_documents rd "
                    "JOIN knowledge_documents kd ON kd.id=rd.document_id "
                    "JOIN resources r ON r.id=rd.resource_id "
                    "WHERE kd.content_hash IN ({}) AND r.deleted_at IS NULL".format(
                        hash_placeholders
                    ),
                    tuple(sorted(doc_hashes)),
                ).fetchall()
                for row in rows:
                    reasons[str(row[0])].add("document_content_hash")

        return tuple(
            DuplicateCandidate(resource_id=resource_id, reasons=tuple(sorted(values)))
            for resource_id, values in sorted(reasons.items())
        )

    def unlinked_documents(self):
        return self.connection.execute(
            "SELECT kd.id,kd.kind,kd.canonical_uri,kd.path_key,kd.content_hash "
            "FROM knowledge_documents kd "
            "LEFT JOIN resource_documents rd ON rd.document_id=kd.id "
            "WHERE rd.resource_id IS NULL ORDER BY kd.path_key,kd.id"
        ).fetchall()

    def unlinked_notes(self):
        return self.connection.execute(
            "SELECT n.id,n.title,n.path_key,n.note_type "
            "FROM note_metadata n "
            "LEFT JOIN resource_notes rn ON rn.note_id=n.id "
            "WHERE rn.resource_id IS NULL AND n.trashed_at IS NULL "
            "ORDER BY n.path_key,n.id"
        ).fetchall()

    def _insert_outbox(self, event: Mapping[str, object]) -> None:
        payload_json = json.dumps(
            dict(event.get("payload") or {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.connection.execute(
            "INSERT INTO outbox_events "
            "(id,event_type,entity_type,entity_id,payload_json,created_at,"
            "processed_at,failed_at,error,attempts) "
            "VALUES (?,?,?,?,?,?,NULL,NULL,NULL,0)",
            (
                str(event["id"]),
                str(event["event_type"]),
                str(event["entity_type"]),
                str(event["entity_id"]),
                payload_json,
                str(event["created_at"]),
            ),
        )
