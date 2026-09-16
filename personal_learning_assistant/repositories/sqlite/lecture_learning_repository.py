"""SQLite read/write adapter for Phase 6.4 Lecture Learning Mode.

Writes use only the existing authoritative Resources 2 progress tables and
study_sessions table. No parallel watch-time store is introduced.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
)
from personal_learning_assistant.repositories.sqlite.connection import transaction


class LectureLearningRepositoryError(RuntimeError):
    pass


class LectureLearningAuthorityError(LectureLearningRepositoryError):
    pass


class LectureLearningConflictError(LectureLearningRepositoryError):
    pass


class LectureLearningNotFoundError(LectureLearningRepositoryError):
    pass


_REQUIRED = {
    "courses",
    "topics",
    "resources",
    "resource_courses",
    "resource_topics",
    "resource_progress_events",
    "study_sessions",
    "outbox_events",
    "resource_documents",
    "knowledge_documents",
    "knowledge_chunks",
}


class SQLiteLectureLearningRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        authority_control_path=None,
        validate_schema=True,
    ):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.authority_control_path = (
            None if authority_control_path is None else Path(authority_control_path)
        )
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
        missing = sorted(_REQUIRED - tables)
        if missing:
            raise LectureLearningRepositoryError(
                "Phase 6.4 required tables missing: {}".format(", ".join(missing))
            )

    def require_sqlite_authority(self):
        if self.authority_control_path is None:
            raise LectureLearningAuthorityError(
                "lecture-learning writes require an explicit authority-control path"
            )
        state = read_authority_control(self.authority_control_path)
        if state.storage_backend != BACKEND_SQLITE or not state.legacy_writes_blocked:
            raise LectureLearningAuthorityError(
                "lecture-learning writes require active SQLite authority"
            )

    def resource(self, resource_id: str):
        row = self.connection.execute(
            "SELECT id,resource_type,title,canonical_uri,provider,external_id,"
            "status,completed_at,deleted_at "
            "FROM resources WHERE id=?",
            (str(resource_id),),
        ).fetchone()
        if row is None or row["deleted_at"] is not None:
            raise LectureLearningNotFoundError("lecture resource not found")
        return row

    def course_by_code(self, code: str):
        rows = self.connection.execute(
            "SELECT id,code,name FROM courses "
            "WHERE upper(code)=upper(?) AND deleted_at IS NULL",
            (str(code).strip(),),
        ).fetchall()
        if len(rows) != 1:
            raise LectureLearningNotFoundError(
                "expected exactly one active course for code {}".format(code)
            )
        return rows[0]

    def course_ids(self, resource_id: str):
        return tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT course_id FROM resource_courses "
                "WHERE resource_id=? ORDER BY course_id",
                (resource_id,),
            )
        )

    def topic_ids(self, resource_id: str):
        return tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT topic_id FROM resource_topics "
                "WHERE resource_id=? ORDER BY topic_id",
                (resource_id,),
            )
        )

    def topic_belongs_to_course(self, topic_id: str, course_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM topics WHERE id=? AND course_id=? AND deleted_at IS NULL",
            (topic_id, course_id),
        ).fetchone()
        return row is not None

    def list_lecture_resources(
        self,
        *,
        course_code=None,
        provider=None,
        limit=50,
    ):
        clauses = [
            "r.deleted_at IS NULL",
            "r.archived_at IS NULL",
            "r.resource_type='external_lecture'",
        ]
        args = []
        if course_code:
            clauses.append(
                "EXISTS (SELECT 1 FROM resource_courses rc "
                "JOIN courses c ON c.id=rc.course_id "
                "WHERE rc.resource_id=r.id AND upper(c.code)=upper(?) "
                "AND c.deleted_at IS NULL)"
            )
            args.append(str(course_code))
        if provider:
            clauses.append("lower(r.provider)=lower(?)")
            args.append(str(provider))
        args.append(int(limit))
        return tuple(
            self.connection.execute(
                "SELECT r.id,r.title,r.resource_type,r.provider,r.canonical_uri,"
                "r.external_id,r.status "
                "FROM resources r WHERE {} "
                "ORDER BY r.title COLLATE NOCASE,r.id LIMIT ?".format(
                    " AND ".join(clauses)
                ),
                tuple(args),
            ).fetchall()
        )

    def latest_progress(self, resource_id: str):
        return self.connection.execute(
            "SELECT id,occurred_at,status,value,max_value,unit,position,note "
            "FROM resource_progress_events WHERE resource_id=? "
            "ORDER BY occurred_at DESC,id DESC LIMIT 1",
            (resource_id,),
        ).fetchone()

    def open_segment(self, resource_id: str):
        rows = self.connection.execute(
            "SELECT * FROM study_sessions "
            "WHERE resource_id=? AND ended_at IS NULL "
            "ORDER BY started_at DESC,id DESC",
            (resource_id,),
        ).fetchall()
        if len(rows) > 1:
            raise LectureLearningConflictError(
                "multiple open study sessions exist for this resource"
            )
        return None if not rows else rows[0]

    def segments(self, resource_id: str):
        return tuple(
            self.connection.execute(
                "SELECT * FROM study_sessions WHERE resource_id=? "
                "ORDER BY started_at,id",
                (resource_id,),
            ).fetchall()
        )

    def total_study_minutes(self, resource_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COALESCE(SUM(duration_minutes),0) "
                "FROM study_sessions WHERE resource_id=? AND ended_at IS NOT NULL",
                (resource_id,),
            ).fetchone()[0]
        )

    def current_chunk_count(self, resource_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(DISTINCT c.id) "
                "FROM resource_documents rd "
                "JOIN knowledge_documents d ON d.id=rd.document_id "
                "JOIN knowledge_chunks c ON c.document_id=d.id "
                "AND c.extraction_version=d.extraction_version "
                "WHERE rd.resource_id=? "
                "AND d.extraction_status='completed' "
                "AND d.extraction_version<>'' "
                "AND c.chunk_text IS NOT NULL",
                (resource_id,),
            ).fetchone()[0]
        )

    def _insert_outbox(
        self,
        *,
        event_id,
        event_type,
        resource_id,
        payload,
        created_at,
    ):
        self.connection.execute(
            "INSERT INTO outbox_events("
            "id,event_type,entity_type,entity_id,payload_json,created_at,"
            "processed_at,failed_at,error,attempts) "
            "VALUES (?,?, 'resource', ?, ?, ?, NULL, NULL, NULL, 0)",
            (
                event_id,
                event_type,
                resource_id,
                json.dumps(
                    dict(payload),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                created_at,
            ),
        )

    def _append_progress(
        self,
        *,
        progress_event_id,
        resource_id,
        occurred_at,
        status,
        value,
        max_value,
        unit,
        position,
        note,
        outbox_event_id,
    ):
        self.connection.execute(
            "INSERT INTO resource_progress_events("
            "id,resource_id,occurred_at,status,value,max_value,unit,position,note) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                progress_event_id,
                resource_id,
                occurred_at,
                status,
                value,
                max_value,
                unit,
                position,
                note,
            ),
        )
        latest = self.connection.execute(
            "SELECT status,occurred_at FROM resource_progress_events "
            "WHERE resource_id=? ORDER BY occurred_at DESC,id DESC LIMIT 1",
            (resource_id,),
        ).fetchone()
        latest_status = str(latest["status"])
        completed_at = (
            str(latest["occurred_at"]) if latest_status == "completed" else None
        )
        self.connection.execute(
            "UPDATE resources SET status=?,completed_at=?,updated_at=? WHERE id=?",
            (latest_status, completed_at, occurred_at, resource_id),
        )
        self._insert_outbox(
            event_id=outbox_event_id,
            event_type="resource.progress_recorded",
            resource_id=resource_id,
            payload={
                "status": status,
                "source": "phase6.4_lecture_learning",
                "position": position,
            },
            created_at=occurred_at,
        )

    def start_segment(
        self,
        *,
        segment_id,
        resource_id,
        started_at,
        course_id,
        topic_id,
        note,
        progress_event_id,
        position,
        value,
        max_value,
        unit,
        outbox_event_id,
    ):
        self.require_sqlite_authority()
        self.resource(resource_id)
        with transaction(self.connection, immediate=True):
            if self.open_segment(resource_id) is not None:
                raise LectureLearningConflictError(
                    "an open lecture study session already exists"
                )
            self.connection.execute(
                "INSERT INTO study_sessions("
                "id,started_at,ended_at,duration_minutes,course_id,topic_id,"
                "resource_id,assessment_id,note_id,plan_item_id,outcome,"
                "confidence,note,created_at) "
                "VALUES (?,?,NULL,0,?,?,?,NULL,NULL,NULL,'',NULL,?,?)",
                (
                    segment_id,
                    started_at,
                    course_id,
                    topic_id,
                    resource_id,
                    note,
                    started_at,
                ),
            )
            self._append_progress(
                progress_event_id=progress_event_id,
                resource_id=resource_id,
                occurred_at=started_at,
                status="in_progress",
                value=value,
                max_value=max_value,
                unit=unit,
                position=position,
                note=note,
                outbox_event_id=outbox_event_id,
            )
        return self.connection.execute(
            "SELECT * FROM study_sessions WHERE id=?",
            (segment_id,),
        ).fetchone()

    def checkpoint(
        self,
        *,
        resource_id,
        occurred_at,
        progress_event_id,
        position,
        value,
        max_value,
        unit,
        note,
        outbox_event_id,
    ):
        self.require_sqlite_authority()
        self.resource(resource_id)
        with transaction(self.connection, immediate=True):
            if self.open_segment(resource_id) is None:
                raise LectureLearningConflictError(
                    "checkpoint requires an active lecture study session"
                )
            self._append_progress(
                progress_event_id=progress_event_id,
                resource_id=resource_id,
                occurred_at=occurred_at,
                status="in_progress",
                value=value,
                max_value=max_value,
                unit=unit,
                position=position,
                note=note,
                outbox_event_id=outbox_event_id,
            )

    def close_segment(
        self,
        *,
        resource_id,
        ended_at,
        duration_minutes,
        final_status,
        outcome,
        confidence,
        session_note,
        progress_event_id,
        position,
        value,
        max_value,
        unit,
        progress_note,
        outbox_event_id,
    ):
        self.require_sqlite_authority()
        self.resource(resource_id)
        with transaction(self.connection, immediate=True):
            current = self.open_segment(resource_id)
            if current is None:
                raise LectureLearningConflictError(
                    "no active lecture study session exists"
                )
            self.connection.execute(
                "UPDATE study_sessions SET ended_at=?,duration_minutes=?,"
                "outcome=?,confidence=?,note=? WHERE id=?",
                (
                    ended_at,
                    int(duration_minutes),
                    outcome,
                    confidence,
                    session_note,
                    current["id"],
                ),
            )
            self._append_progress(
                progress_event_id=progress_event_id,
                resource_id=resource_id,
                occurred_at=ended_at,
                status=final_status,
                value=value,
                max_value=max_value,
                unit=unit,
                position=position,
                note=progress_note,
                outbox_event_id=outbox_event_id,
            )
        return str(current["id"])

    def complete_without_open_segment(
        self,
        *,
        resource_id,
        occurred_at,
        progress_event_id,
        position,
        value,
        max_value,
        unit,
        note,
        outbox_event_id,
    ):
        self.require_sqlite_authority()
        self.resource(resource_id)
        with transaction(self.connection, immediate=True):
            if self.open_segment(resource_id) is not None:
                raise LectureLearningConflictError(
                    "active segment must be closed through finish"
                )
            self._append_progress(
                progress_event_id=progress_event_id,
                resource_id=resource_id,
                occurred_at=occurred_at,
                status="completed",
                value=value,
                max_value=max_value,
                unit=unit,
                position=position,
                note=note,
                outbox_event_id=outbox_event_id,
            )
