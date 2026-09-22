"""SQLite repository for Phase 6.1 tutor sessions and evidence."""

from __future__ import annotations

import json
import sqlite3
from typing import Iterable, Optional, Sequence

from personal_learning_assistant.domain.tutor_models import (
    TutorEvidence,
    TutorFeedback,
    TutorSession,
    TutorTurn,
)
from personal_learning_assistant.repositories.sqlite.connection import transaction


class TutorRepositoryError(RuntimeError):
    pass


_REQUIRED = {
    "tutor_sessions": {
        "id", "course_id", "topic_id", "assessment_id", "resource_id",
        "mode", "source_policy", "status", "title", "metadata_json",
        "created_at", "updated_at", "completed_at",
    },
    "tutor_turns": {
        "id", "session_id", "ordinal", "role", "content", "support_level",
        "provider_name", "provider_model", "created_at",
    },
    "tutor_evidence_links": {
        "turn_id", "ordinal", "chunk_id", "document_id", "relation_type",
        "retrieval_score", "citation_label", "created_at",
    },
    "tutor_feedback": {
        "id", "turn_id", "rating", "helpful", "feedback_text", "created_at",
    },
}


class SQLiteTutorRepository:
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
            raise TutorRepositoryError(
                "Phase 6.1 tutor tables missing: {}".format(
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
            raise TutorRepositoryError(
                "Phase 6.1 tutor schema incomplete: {}".format("; ".join(issues))
            )

    def resolve_course_id(self, identifier: Optional[str]) -> Optional[str]:
        """Resolve a canonical SQLite course id from id or human course code."""
        if identifier is None:
            return None
        clean = str(identifier or "").strip()
        if not clean:
            return None
        row = self.connection.execute(
            "SELECT id FROM courses "
            "WHERE deleted_at IS NULL "
            "AND (id=? OR lower(code)=lower(?)) "
            "ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END,id LIMIT 1",
            (clean, clean, clean),
        ).fetchone()
        return None if row is None else str(row[0])

    def entity_exists(self, table: str, entity_id: Optional[str]) -> bool:
        if entity_id is None:
            return True
        allowed = {
            "courses", "topics", "assessments", "resources",
            "knowledge_chunks", "knowledge_documents",
        }
        if table not in allowed:
            raise ValueError("unsupported entity table")
        row = self.connection.execute(
            'SELECT 1 FROM "{}" WHERE id=?'.format(table),
            (entity_id,),
        ).fetchone()
        return row is not None

    def topic_course_id(self, topic_id: str) -> Optional[str]:
        row = self.connection.execute(
            "SELECT course_id FROM topics WHERE id=? AND deleted_at IS NULL",
            (topic_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def assessment_course_id(self, assessment_id: str) -> Optional[str]:
        row = self.connection.execute(
            "SELECT course_id FROM assessments WHERE id=? AND deleted_at IS NULL",
            (assessment_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def resource_has_course(self, resource_id: str, course_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM resource_courses WHERE resource_id=? AND course_id=?",
            (resource_id, course_id),
        ).fetchone()
        return row is not None

    def chunk_document_id(self, chunk_id: str) -> Optional[str]:
        row = self.connection.execute(
            "SELECT document_id FROM knowledge_chunks WHERE id=?",
            (chunk_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def create_session(
        self,
        *,
        session_id,
        course_id,
        topic_id,
        assessment_id,
        resource_id,
        mode,
        source_policy,
        title,
        metadata_json,
        created_at,
    ):
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "INSERT INTO tutor_sessions("
                "id,course_id,topic_id,assessment_id,resource_id,mode,"
                "source_policy,status,title,metadata_json,created_at,updated_at,"
                "completed_at) VALUES (?,?,?,?,?,?,?,'active',?,?,?,?,NULL)",
                (
                    session_id,
                    course_id,
                    topic_id,
                    assessment_id,
                    resource_id,
                    mode,
                    source_policy,
                    title,
                    metadata_json,
                    created_at,
                    created_at,
                ),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> TutorSession:
        row = self.connection.execute(
            "SELECT * FROM tutor_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise TutorRepositoryError("tutor session not found: {}".format(session_id))
        try:
            metadata = json.loads(str(row["metadata_json"]))
        except json.JSONDecodeError as error:
            raise TutorRepositoryError("tutor session metadata JSON is invalid") from error
        if not isinstance(metadata, dict):
            raise TutorRepositoryError("tutor session metadata must be a JSON object")
        return TutorSession(
            session_id=str(row["id"]),
            mode=str(row["mode"]),
            source_policy=str(row["source_policy"]),
            status=str(row["status"]),
            course_id=None if row["course_id"] is None else str(row["course_id"]),
            topic_id=None if row["topic_id"] is None else str(row["topic_id"]),
            assessment_id=(
                None if row["assessment_id"] is None else str(row["assessment_id"])
            ),
            resource_id=None if row["resource_id"] is None else str(row["resource_id"]),
            title=str(row["title"]),
            metadata=metadata,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            completed_at=(
                None if row["completed_at"] is None else str(row["completed_at"])
            ),
        )

    def list_sessions(self, limit: int = 20):
        limit = int(limit)
        if limit < 1 or limit > 100:
            raise ValueError("session limit must be between 1 and 100")
        rows = self.connection.execute(
            "SELECT id FROM tutor_sessions "
            "ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return tuple(self.get_session(str(row[0])) for row in rows)

    def _next_ordinal(self, session_id: str) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(ordinal),0)+1 FROM tutor_turns WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return int(row[0])

    def add_turn(
        self,
        *,
        turn_id,
        session_id,
        role,
        content,
        support_level,
        provider_name,
        provider_model,
        created_at,
        evidence: Sequence[TutorEvidence] = (),
    ) -> TutorTurn:
        with transaction(self.connection, immediate=True):
            session = self.connection.execute(
                "SELECT status FROM tutor_sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise TutorRepositoryError("tutor session not found: {}".format(session_id))
            if str(session["status"]) != "active":
                raise TutorRepositoryError("cannot append turn to non-active tutor session")

            ordinal = self._next_ordinal(session_id)
            self.connection.execute(
                "INSERT INTO tutor_turns("
                "id,session_id,ordinal,role,content,support_level,provider_name,"
                "provider_model,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    turn_id,
                    session_id,
                    ordinal,
                    role,
                    content,
                    support_level,
                    provider_name,
                    provider_model,
                    created_at,
                ),
            )

            for item in evidence:
                actual_document_id = self.chunk_document_id(item.chunk_id)
                if actual_document_id is None:
                    raise TutorRepositoryError(
                        "evidence chunk not found: {}".format(item.chunk_id)
                    )
                if actual_document_id != item.document_id:
                    raise TutorRepositoryError(
                        "evidence chunk/document mismatch for {}".format(item.chunk_id)
                    )
                self.connection.execute(
                    "INSERT INTO tutor_evidence_links("
                    "turn_id,ordinal,chunk_id,document_id,relation_type,"
                    "retrieval_score,citation_label,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        turn_id,
                        item.ordinal,
                        item.chunk_id,
                        item.document_id,
                        item.relation_type,
                        item.retrieval_score,
                        item.citation_label,
                        created_at,
                    ),
                )

            self.connection.execute(
                "UPDATE tutor_sessions SET updated_at=? WHERE id=?",
                (created_at, session_id),
            )

        return self.get_turn(turn_id)

    def get_turn(self, turn_id: str) -> TutorTurn:
        row = self.connection.execute(
            "SELECT * FROM tutor_turns WHERE id=?",
            (turn_id,),
        ).fetchone()
        if row is None:
            raise TutorRepositoryError("tutor turn not found: {}".format(turn_id))
        evidence_rows = self.connection.execute(
            "SELECT * FROM tutor_evidence_links WHERE turn_id=? ORDER BY ordinal",
            (turn_id,),
        ).fetchall()
        evidence = tuple(
            TutorEvidence(
                chunk_id=str(item["chunk_id"]),
                document_id=str(item["document_id"]),
                ordinal=int(item["ordinal"]),
                relation_type=str(item["relation_type"]),
                retrieval_score=(
                    None
                    if item["retrieval_score"] is None
                    else float(item["retrieval_score"])
                ),
                citation_label=str(item["citation_label"]),
            )
            for item in evidence_rows
        )
        return TutorTurn(
            turn_id=str(row["id"]),
            session_id=str(row["session_id"]),
            ordinal=int(row["ordinal"]),
            role=str(row["role"]),
            content=str(row["content"]),
            support_level=str(row["support_level"]),
            provider_name=str(row["provider_name"]),
            provider_model=str(row["provider_model"]),
            created_at=str(row["created_at"]),
            evidence=evidence,
        )

    def list_turns(self, session_id: str):
        rows = self.connection.execute(
            "SELECT id FROM tutor_turns WHERE session_id=? ORDER BY ordinal",
            (session_id,),
        ).fetchall()
        return tuple(self.get_turn(str(row[0])) for row in rows)

    def set_session_status(self, session_id: str, status: str, now: str):
        completed_at = None if status == "active" else now
        with transaction(self.connection, immediate=True):
            cursor = self.connection.execute(
                "UPDATE tutor_sessions SET status=?,updated_at=?,completed_at=? "
                "WHERE id=?",
                (status, now, completed_at, session_id),
            )
            if cursor.rowcount != 1:
                raise TutorRepositoryError("tutor session not found: {}".format(session_id))
        return self.get_session(session_id)

    def add_feedback(
        self,
        *,
        feedback_id,
        turn_id,
        rating,
        helpful,
        feedback_text,
        created_at,
    ) -> TutorFeedback:
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "INSERT INTO tutor_feedback("
                "id,turn_id,rating,helpful,feedback_text,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    feedback_id,
                    turn_id,
                    rating,
                    None if helpful is None else int(bool(helpful)),
                    feedback_text,
                    created_at,
                ),
            )
        return TutorFeedback(
            feedback_id=feedback_id,
            turn_id=turn_id,
            rating=rating,
            helpful=helpful,
            feedback_text=feedback_text,
            created_at=created_at,
        )
