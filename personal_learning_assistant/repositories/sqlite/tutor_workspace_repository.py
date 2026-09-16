"""Read-only Phase 6.9 Tutor Workspace repository."""

from __future__ import annotations

import json
import sqlite3

from personal_learning_assistant.domain.tutor_workspace_models import (
    WorkspaceActivity,
    WorkspaceCounts,
)


class TutorWorkspaceRepositoryError(RuntimeError):
    pass


class SQLiteTutorWorkspaceRepository:
    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def table_names(self):
        return {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }

    def schema_versions(self):
        if "schema_migrations" not in self.table_names():
            return ()
        return tuple(
            int(row[0])
            for row in self.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        )

    def course_by_code(self, course_code: str):
        rows = self.connection.execute(
            "SELECT id,code,name,status FROM courses "
            "WHERE upper(code)=upper(?) AND deleted_at IS NULL",
            (str(course_code).strip(),),
        ).fetchall()
        if len(rows) != 1:
            raise TutorWorkspaceRepositoryError(
                "expected exactly one active course for code {}".format(course_code)
            )
        return rows[0]

    def _count(self, sql, params=()):
        return int(self.connection.execute(sql, params).fetchone()[0])

    def counts(self, course_id: str):
        tables = self.table_names()
        practice_ready = {
            "practice_sessions",
            "practice_items",
            "practice_attempts",
        }.issubset(tables)
        return WorkspaceCounts(
            topic_count=self._count(
                "SELECT COUNT(*) FROM topics "
                "WHERE course_id=? AND deleted_at IS NULL",
                (course_id,),
            ),
            resource_count=self._count(
                "SELECT COUNT(DISTINCT r.id) FROM resources r "
                "JOIN resource_courses rc ON rc.resource_id=r.id "
                "WHERE rc.course_id=? AND r.deleted_at IS NULL "
                "AND r.archived_at IS NULL",
                (course_id,),
            ),
            assessment_count=self._count(
                "SELECT COUNT(*) FROM assessments "
                "WHERE course_id=? AND deleted_at IS NULL",
                (course_id,),
            ),
            tutor_session_count=self._count(
                "SELECT COUNT(*) FROM tutor_sessions WHERE course_id=?",
                (course_id,),
            ),
            active_tutor_session_count=self._count(
                "SELECT COUNT(*) FROM tutor_sessions "
                "WHERE course_id=? AND status='active'",
                (course_id,),
            ),
            practice_session_count=(
                self._count(
                    "SELECT COUNT(*) FROM practice_sessions WHERE course_id=?",
                    (course_id,),
                )
                if practice_ready
                else 0
            ),
            active_practice_session_count=(
                self._count(
                    "SELECT COUNT(*) FROM practice_sessions "
                    "WHERE course_id=? AND status='active'",
                    (course_id,),
                )
                if practice_ready
                else 0
            ),
            deterministic_practice_attempt_count=(
                self._count(
                    "SELECT COUNT(*) FROM practice_attempts pa "
                    "JOIN practice_items pi ON pi.id=pa.item_id "
                    "JOIN practice_sessions ps ON ps.id=pi.session_id "
                    "WHERE ps.course_id=? AND pa.grading_mode='deterministic'",
                    (course_id,),
                )
                if practice_ready
                else 0
            ),
            active_lecture_segment_count=self._count(
                "SELECT COUNT(*) FROM study_sessions ss "
                "JOIN resources r ON r.id=ss.resource_id "
                "WHERE ss.course_id=? AND ss.ended_at IS NULL "
                "AND r.resource_type='external_lecture'",
                (course_id,),
            ),
            completed_agent_action_count=self._count(
                "SELECT COUNT(*) FROM operation_journal "
                "WHERE kind='academic_agent_action' AND state='completed'"
            ),
            planned_agent_action_count=self._count(
                "SELECT COUNT(*) FROM operation_journal "
                "WHERE kind='academic_agent_action' AND state='planned'"
            ),
        )

    def recent_activity(self, course_id: str, *, limit=12):
        limit = max(1, int(limit))
        rows = []

        for row in self.connection.execute(
            "SELECT id,title,status,mode,topic_id,resource_id,assessment_id,updated_at "
            "FROM tutor_sessions WHERE course_id=? "
            "ORDER BY updated_at DESC,id DESC LIMIT ?",
            (course_id, limit),
        ).fetchall():
            rows.append(
                WorkspaceActivity(
                    activity_type="tutor_session",
                    entity_id=str(row["id"]),
                    title=str(row["title"] or "Tutor session"),
                    status=str(row["status"]),
                    mode=str(row["mode"]),
                    topic_id=(
                        None if row["topic_id"] is None else str(row["topic_id"])
                    ),
                    resource_id=(
                        None
                        if row["resource_id"] is None
                        else str(row["resource_id"])
                    ),
                    assessment_id=(
                        None
                        if row["assessment_id"] is None
                        else str(row["assessment_id"])
                    ),
                    occurred_at=str(row["updated_at"]),
                )
            )

        tables = self.table_names()
        if {"practice_sessions", "practice_items", "practice_attempts"}.issubset(
            tables
        ):
            for row in self.connection.execute(
                "SELECT id,status,mode,difficulty,topic_id,resource_id,created_at "
                "FROM practice_sessions WHERE course_id=? "
                "ORDER BY created_at DESC,id DESC LIMIT ?",
                (course_id, limit),
            ).fetchall():
                rows.append(
                    WorkspaceActivity(
                        activity_type="practice_session",
                        entity_id=str(row["id"]),
                        title="{} practice ({})".format(
                            str(row["mode"]),
                            str(row["difficulty"]),
                        ),
                        status=str(row["status"]),
                        mode=str(row["mode"]),
                        topic_id=(
                            None
                            if row["topic_id"] is None
                            else str(row["topic_id"])
                        ),
                        resource_id=(
                            None
                            if row["resource_id"] is None
                            else str(row["resource_id"])
                        ),
                        assessment_id=None,
                        occurred_at=str(row["created_at"]),
                    )
                )

        for row in self.connection.execute(
            "SELECT ss.id,ss.started_at,ss.ended_at,ss.topic_id,ss.resource_id,"
            "r.title FROM study_sessions ss "
            "JOIN resources r ON r.id=ss.resource_id "
            "WHERE ss.course_id=? AND r.resource_type='external_lecture' "
            "ORDER BY ss.started_at DESC,ss.id DESC LIMIT ?",
            (course_id, limit),
        ).fetchall():
            rows.append(
                WorkspaceActivity(
                    activity_type="lecture_segment",
                    entity_id=str(row["id"]),
                    title=str(row["title"]),
                    status=(
                        "active" if row["ended_at"] is None else "completed"
                    ),
                    mode="lecture",
                    topic_id=(
                        None if row["topic_id"] is None else str(row["topic_id"])
                    ),
                    resource_id=str(row["resource_id"]),
                    assessment_id=None,
                    occurred_at=str(row["started_at"]),
                )
            )

        rows.sort(
            key=lambda item: (
                item.occurred_at,
                item.activity_type,
                item.entity_id,
            ),
            reverse=True,
        )
        return tuple(rows[:limit])

    def recent_agent_events(self, *, limit=10):
        result = []
        for row in self.connection.execute(
            "SELECT entity_id,payload_json,created_at FROM outbox_events "
            "WHERE event_type='academic_agent.action_executed' "
            "AND entity_type='agent_action' "
            "ORDER BY created_at DESC,id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall():
            try:
                payload = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError:
                payload = {}
            result.append(
                {
                    "fingerprint": str(row["entity_id"]),
                    "created_at": str(row["created_at"]),
                    "action_type": str(payload.get("action_type", "")),
                    "route": str(payload.get("route", "")),
                    "result_type": str(payload.get("result_type", "")),
                    "result_id": payload.get("result_id"),
                }
            )
        return tuple(result)
