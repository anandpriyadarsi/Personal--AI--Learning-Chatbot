"""Read-only SQLite evidence adapter for Phase 6.3 Knowledge Navigator."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Optional


class KnowledgeNavigatorRepositoryError(RuntimeError):
    pass


_REQUIRED = {
    "courses",
    "topics",
    "topic_progress_events",
    "learning_memory_entries",
    "assessments",
    "assessment_topics",
    "questions",
    "question_topic_mappings",
    "question_attempts",
    "mistake_events",
    "study_plans",
    "study_plan_items",
    "study_sessions",
    "resources",
    "resource_courses",
    "resource_topics",
    "resource_assessments",
    "resource_progress_events",
    "resource_documents",
    "knowledge_documents",
    "knowledge_chunks",
    "note_metadata",
    "note_courses",
    "note_topics",
}


class SQLiteKnowledgeNavigatorRepository:
    """Read-only evidence queries over already-authoritative academic state."""

    def __init__(self, connection: sqlite3.Connection, *, validate_schema=True):
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
        missing = sorted(_REQUIRED - tables)
        if missing:
            raise KnowledgeNavigatorRepositoryError(
                "Phase 6.3 required tables missing: {}".format(", ".join(missing))
            )

    def course_by_code(self, code: str):
        return self.connection.execute(
            "SELECT id,code,name,status FROM courses "
            "WHERE upper(code)=upper(?) AND deleted_at IS NULL",
            (str(code).strip(),),
        ).fetchone()

    def topic_by_name(self, course_id: str, name: str):
        clean = " ".join(str(name).strip().casefold().split())
        rows = self.connection.execute(
            "SELECT id,name,position,status,confidence,normalized_name "
            "FROM topics WHERE course_id=? AND deleted_at IS NULL "
            "ORDER BY position,id",
            (course_id,),
        ).fetchall()
        exact = []
        for row in rows:
            candidates = {
                " ".join(str(row["name"]).strip().casefold().split()),
                " ".join(str(row["normalized_name"]).strip().casefold().split()),
            }
            if clean in candidates:
                exact.append(row)
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise KnowledgeNavigatorRepositoryError(
                "topic name is ambiguous within selected course"
            )

        alias_rows = self.connection.execute(
            "SELECT t.id,t.name,t.position,t.status,t.confidence,t.normalized_name "
            "FROM topic_aliases a JOIN topics t ON t.id=a.topic_id "
            "WHERE a.course_id=? AND lower(a.normalized_alias)=? "
            "AND t.deleted_at IS NULL",
            (course_id, clean),
        ).fetchall()
        if len(alias_rows) == 1:
            return alias_rows[0]
        if len(alias_rows) > 1:
            raise KnowledgeNavigatorRepositoryError(
                "topic alias is ambiguous within selected course"
            )
        return None

    def topics_for_course(self, course_id: str):
        return tuple(
            self.connection.execute(
                "SELECT id,name,position,status,confidence,normalized_name "
                "FROM topics WHERE course_id=? AND deleted_at IS NULL "
                "ORDER BY position,id",
                (course_id,),
            ).fetchall()
        )

    def latest_progress_event(self, topic_id: str):
        return self.connection.execute(
            "SELECT event_type,previous_status,new_status,confidence,evidence_type,"
            "evidence_id,occurred_at,note FROM topic_progress_events "
            "WHERE topic_id=? ORDER BY occurred_at DESC,id DESC LIMIT 1",
            (topic_id,),
        ).fetchone()

    def active_memory_count(self, topic_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM learning_memory_entries "
                "WHERE topic_id=? AND archived_at IS NULL",
                (topic_id,),
            ).fetchone()[0]
        )

    def assessments_for_topic(self, course_id: str, topic_id: str):
        return tuple(
            self.connection.execute(
                "SELECT DISTINCT a.id,a.title,a.assessment_type,a.due_on,a.due_time,"
                "a.status,a.weight_bps "
                "FROM assessments a "
                "JOIN assessment_topics at ON at.assessment_id=a.id "
                "WHERE a.course_id=? AND at.topic_id=? AND a.deleted_at IS NULL "
                "ORDER BY CASE WHEN a.due_on IS NULL THEN 1 ELSE 0 END,"
                "a.due_on,a.id",
                (course_id, topic_id),
            ).fetchall()
        )

    def unresolved_mistake_count(self, topic_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(DISTINCT m.id) "
                "FROM mistake_events m "
                "JOIN question_attempts qa ON qa.id=m.attempt_id "
                "JOIN questions q ON q.id=qa.question_id AND q.deleted_at IS NULL "
                "JOIN question_topic_mappings qtm ON qtm.question_id=q.id "
                "WHERE qtm.topic_id=? AND qtm.state='accepted' "
                "AND m.resolved_at IS NULL",
                (topic_id,),
            ).fetchone()[0]
        )

    def planned_item_count(self, topic_id: str, as_of: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM study_plan_items spi "
                "JOIN study_plans sp ON sp.id=spi.plan_id "
                "WHERE spi.topic_id=? AND spi.plan_date>=? "
                "AND lower(spi.status) NOT IN ('completed','done','skipped','cancelled') "
                "AND lower(sp.status) NOT IN ('cancelled','archived')",
                (topic_id, as_of),
            ).fetchone()[0]
        )

    def topic_study_minutes(self, topic_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COALESCE(SUM(duration_minutes),0) FROM study_sessions "
                "WHERE topic_id=?",
                (topic_id,),
            ).fetchone()[0]
        )

    def resource_candidates(self, course_id: str, topic_id: str):
        rows = self.connection.execute(
            "SELECT r.id,r.resource_type,r.title,r.provider,r.status,r.rating,"
            "MAX(CASE WHEN rt.topic_id=? THEN 1 ELSE 0 END) AS direct_topic,"
            "MAX(CASE WHEN rc.course_id=? THEN 1 ELSE 0 END) AS direct_course "
            "FROM resources r "
            "LEFT JOIN resource_topics rt ON rt.resource_id=r.id "
            "LEFT JOIN resource_courses rc ON rc.resource_id=r.id "
            "WHERE r.deleted_at IS NULL "
            "AND (rt.topic_id=? OR rc.course_id=?) "
            "GROUP BY r.id,r.resource_type,r.title,r.provider,r.status,r.rating "
            "ORDER BY r.title,r.id",
            (topic_id, course_id, topic_id, course_id),
        ).fetchall()
        return tuple(rows)

    def note_candidates(self, course_id: str, topic_id: str):
        rows = self.connection.execute(
            "SELECT n.id,n.title,n.revision_status,n.pinned_at,"
            "MAX(CASE WHEN nt.topic_id=? THEN 1 ELSE 0 END) AS direct_topic,"
            "MAX(CASE WHEN nc.course_id=? THEN 1 ELSE 0 END) AS direct_course "
            "FROM note_metadata n "
            "LEFT JOIN note_topics nt ON nt.note_id=n.id "
            "LEFT JOIN note_courses nc ON nc.note_id=n.id "
            "WHERE n.trashed_at IS NULL AND n.archived_at IS NULL "
            "AND (nt.topic_id=? OR nc.course_id=?) "
            "GROUP BY n.id,n.title,n.revision_status,n.pinned_at "
            "ORDER BY n.title,n.id",
            (topic_id, course_id, topic_id, course_id),
        ).fetchall()
        return tuple(rows)

    def latest_resource_progress(self, resource_id: str):
        return self.connection.execute(
            "SELECT status,value,max_value,unit,position,occurred_at,note "
            "FROM resource_progress_events WHERE resource_id=? "
            "ORDER BY occurred_at DESC,id DESC LIMIT 1",
            (resource_id,),
        ).fetchone()

    def resource_current_chunk_count(self, resource_id: str) -> int:
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

    def resource_study_minutes(self, resource_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COALESCE(SUM(duration_minutes),0) FROM study_sessions "
                "WHERE resource_id=?",
                (resource_id,),
            ).fetchone()[0]
        )

    def resource_upcoming_assessments(self, resource_id: str, course_id: str):
        return tuple(
            self.connection.execute(
                "SELECT DISTINCT a.id,a.title,a.due_on,a.status "
                "FROM resource_assessments ra "
                "JOIN assessments a ON a.id=ra.assessment_id "
                "WHERE ra.resource_id=? AND a.course_id=? "
                "AND a.deleted_at IS NULL ORDER BY a.due_on,a.id",
                (resource_id, course_id),
            ).fetchall()
        )
