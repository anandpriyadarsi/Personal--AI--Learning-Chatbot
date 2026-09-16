"""SQLite repository for Phase 6.5 source-grounded practice."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
)
from personal_learning_assistant.repositories.sqlite.connection import transaction


class PracticeRepositoryError(RuntimeError):
    pass


class PracticeAuthorityError(PracticeRepositoryError):
    pass


class PracticeConflictError(PracticeRepositoryError):
    pass


class PracticeNotFoundError(PracticeRepositoryError):
    pass


_REQUIRED = {
    "practice_sessions",
    "practice_items",
    "practice_item_sources",
    "practice_attempts",
    "courses",
    "topics",
    "resources",
    "knowledge_documents",
    "knowledge_chunks",
    "outbox_events",
}


class SQLitePracticeRepository:
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
            raise PracticeRepositoryError(
                "Phase 6.5 practice tables missing: {}".format(", ".join(missing))
            )

    def require_sqlite_authority(self):
        if self.authority_control_path is None:
            raise PracticeAuthorityError(
                "practice writes require an explicit authority-control path"
            )
        state = read_authority_control(self.authority_control_path)
        if state.storage_backend != BACKEND_SQLITE or not state.legacy_writes_blocked:
            raise PracticeAuthorityError(
                "practice writes require active SQLite authority"
            )

    def entity_exists(self, table: str, entity_id):
        if entity_id is None:
            return True
        allowed = {"courses", "topics", "resources", "tutor_sessions"}
        if table not in allowed:
            raise ValueError("unsupported entity table")
        row = self.connection.execute(
            'SELECT 1 FROM "{}" WHERE id=?'.format(table),
            (str(entity_id),),
        ).fetchone()
        return row is not None

    def topic_course_id(self, topic_id: str):
        row = self.connection.execute(
            "SELECT course_id FROM topics WHERE id=? AND deleted_at IS NULL",
            (topic_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def resource_has_course(self, resource_id: str, course_id: str):
        row = self.connection.execute(
            "SELECT 1 FROM resource_courses WHERE resource_id=? AND course_id=?",
            (resource_id, course_id),
        ).fetchone()
        return row is not None

    def chunk_document_id(self, chunk_id: str):
        row = self.connection.execute(
            "SELECT document_id FROM knowledge_chunks WHERE id=?",
            (chunk_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def _outbox(self, *, event_id, event_type, entity_id, payload, created_at):
        self.connection.execute(
            "INSERT INTO outbox_events("
            "id,event_type,entity_type,entity_id,payload_json,created_at,"
            "processed_at,failed_at,error,attempts) "
            "VALUES (?,?, 'practice_session', ?, ?, ?, NULL, NULL, NULL, 0)",
            (
                event_id,
                event_type,
                entity_id,
                json.dumps(
                    dict(payload),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                created_at,
            ),
        )

    def create_quiz(
        self,
        *,
        session_id,
        tutor_session_id,
        course_id,
        topic_id,
        resource_id,
        mode,
        difficulty,
        source_query,
        requested_item_count,
        generation_provider,
        generation_model,
        provider_request_id,
        created_at,
        items,
        outbox_event_id,
    ):
        self.require_sqlite_authority()
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "INSERT INTO practice_sessions("
                "id,tutor_session_id,course_id,topic_id,resource_id,mode,difficulty,"
                "status,source_query,source_policy,requested_item_count,"
                "generation_provider,generation_model,provider_request_id,"
                "created_at,completed_at) "
                "VALUES (?,?,?,?,?,?,?,'active',?,'source_only',?,?,?,?,?,NULL)",
                (
                    session_id,
                    tutor_session_id,
                    course_id,
                    topic_id,
                    resource_id,
                    mode,
                    difficulty,
                    source_query,
                    requested_item_count,
                    generation_provider,
                    generation_model,
                    provider_request_id,
                    created_at,
                ),
            )
            for item in items:
                self.connection.execute(
                    "INSERT INTO practice_items("
                    "id,session_id,ordinal,item_type,prompt,options_json,"
                    "answer_key_json,explanation,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        item["id"],
                        session_id,
                        item["ordinal"],
                        item["item_type"],
                        item["prompt"],
                        item["options_json"],
                        item["answer_key_json"],
                        item["explanation"],
                        created_at,
                    ),
                )
                for source in item["sources"]:
                    actual_document = self.chunk_document_id(source["chunk_id"])
                    if actual_document is None:
                        raise PracticeRepositoryError(
                            "practice source chunk does not exist: {}".format(
                                source["chunk_id"]
                            )
                        )
                    if actual_document != source["document_id"]:
                        raise PracticeRepositoryError(
                            "practice source chunk/document mismatch"
                        )
                    self.connection.execute(
                        "INSERT INTO practice_item_sources("
                        "item_id,ordinal,chunk_id,document_id,citation_label,created_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            item["id"],
                            source["ordinal"],
                            source["chunk_id"],
                            source["document_id"],
                            source["citation_label"],
                            created_at,
                        ),
                    )
            self._outbox(
                event_id=outbox_event_id,
                event_type="practice.quiz_generated",
                entity_id=session_id,
                payload={
                    "item_count": len(items),
                    "mode": mode,
                    "difficulty": difficulty,
                    "source": "phase6.5_active_recall",
                },
                created_at=created_at,
            )

    def session(self, session_id: str):
        row = self.connection.execute(
            "SELECT * FROM practice_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise PracticeNotFoundError("practice session not found")
        return row

    def items(self, session_id: str):
        return tuple(
            self.connection.execute(
                "SELECT * FROM practice_items WHERE session_id=? "
                "ORDER BY ordinal,id",
                (session_id,),
            ).fetchall()
        )

    def item_by_ordinal(self, session_id: str, ordinal: int):
        row = self.connection.execute(
            "SELECT * FROM practice_items WHERE session_id=? AND ordinal=?",
            (session_id, int(ordinal)),
        ).fetchone()
        if row is None:
            raise PracticeNotFoundError("practice item not found")
        return row

    def item_sources(self, item_id: str):
        return tuple(
            self.connection.execute(
                "SELECT * FROM practice_item_sources WHERE item_id=? "
                "ORDER BY ordinal",
                (item_id,),
            ).fetchall()
        )

    def attempt_count(self, item_id: str):
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM practice_attempts WHERE item_id=?",
                (item_id,),
            ).fetchone()[0]
        )

    def record_attempt(
        self,
        *,
        attempt_id,
        item_id,
        response_text,
        outcome,
        score_bps,
        grading_mode,
        self_confidence,
        feedback,
        occurred_at,
        outbox_event_id,
    ):
        self.require_sqlite_authority()
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT pi.session_id,ps.status "
                "FROM practice_items pi "
                "JOIN practice_sessions ps ON ps.id=pi.session_id "
                "WHERE pi.id=?",
                (item_id,),
            ).fetchone()
            if row is None:
                raise PracticeNotFoundError("practice item not found")
            if str(row["status"]) != "active":
                raise PracticeConflictError(
                    "cannot submit to a non-active practice session"
                )
            attempt_number = self.attempt_count(item_id) + 1
            self.connection.execute(
                "INSERT INTO practice_attempts("
                "id,item_id,attempt_number,response_text,outcome,score_bps,"
                "grading_mode,self_confidence,feedback,occurred_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    item_id,
                    attempt_number,
                    response_text,
                    outcome,
                    score_bps,
                    grading_mode,
                    self_confidence,
                    feedback,
                    occurred_at,
                ),
            )
            self._outbox(
                event_id=outbox_event_id,
                event_type="practice.attempt_recorded",
                entity_id=str(row["session_id"]),
                payload={
                    "item_id": item_id,
                    "attempt_number": attempt_number,
                    "outcome": outcome,
                    "grading_mode": grading_mode,
                    "source": "phase6.5_active_recall",
                },
                created_at=occurred_at,
            )
        return attempt_number

    def complete_session(self, session_id: str, *, completed_at, outbox_event_id):
        self.require_sqlite_authority()
        with transaction(self.connection, immediate=True):
            session = self.session(session_id)
            if str(session["status"]) == "completed":
                return False
            if str(session["status"]) != "active":
                raise PracticeConflictError(
                    "only active practice sessions can be completed"
                )
            total = int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM practice_items WHERE session_id=?",
                    (session_id,),
                ).fetchone()[0]
            )
            attempted = int(
                self.connection.execute(
                    "SELECT COUNT(DISTINCT pi.id) "
                    "FROM practice_items pi "
                    "JOIN practice_attempts pa ON pa.item_id=pi.id "
                    "WHERE pi.session_id=?",
                    (session_id,),
                ).fetchone()[0]
            )
            if attempted != total:
                raise PracticeConflictError(
                    "all practice items must have at least one attempt before completion"
                )
            self.connection.execute(
                "UPDATE practice_sessions SET status='completed',completed_at=? "
                "WHERE id=?",
                (completed_at, session_id),
            )
            self._outbox(
                event_id=outbox_event_id,
                event_type="practice.session_completed",
                entity_id=session_id,
                payload={
                    "item_count": total,
                    "source": "phase6.5_active_recall",
                },
                created_at=completed_at,
            )
        return True
