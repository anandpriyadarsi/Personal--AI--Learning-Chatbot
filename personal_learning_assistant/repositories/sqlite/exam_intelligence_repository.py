"""Read-only formal-assessment evidence adapter for Phase 6.6."""

from __future__ import annotations

import sqlite3


class ExamIntelligenceRepositoryError(RuntimeError):
    pass


class ExamIntelligenceNotFoundError(ExamIntelligenceRepositoryError):
    pass


_REQUIRED = {
    "courses",
    "topics",
    "assessments",
    "assessment_topics",
    "questions",
    "question_topic_mappings",
    "question_sources",
    "question_attempts",
    "mistake_events",
}


class SQLiteExamIntelligenceRepository:
    """Read-only queries over formal assessment/PYQ state.

    Generated Phase 6.5 practice tables are deliberately not queried here.
    """

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
            raise ExamIntelligenceRepositoryError(
                "Phase 6.6 required tables missing: {}".format(", ".join(missing))
            )

    def course_by_code(self, code: str):
        rows = self.connection.execute(
            "SELECT id,code,name,status FROM courses "
            "WHERE upper(code)=upper(?) AND deleted_at IS NULL",
            (str(code).strip(),),
        ).fetchall()
        if len(rows) != 1:
            raise ExamIntelligenceNotFoundError(
                "expected exactly one active course for code {}".format(code)
            )
        return rows[0]

    def topics_for_course(self, course_id: str):
        return tuple(
            self.connection.execute(
                "SELECT id,name,position,status,confidence "
                "FROM topics WHERE course_id=? AND deleted_at IS NULL "
                "ORDER BY position,id",
                (course_id,),
            ).fetchall()
        )

    def assessments_for_course(self, course_id: str):
        return tuple(
            self.connection.execute(
                "SELECT id,assessment_type,title,due_on,due_time,status,weight_bps,"
                "max_points_milli,earned_points_milli,description "
                "FROM assessments WHERE course_id=? AND deleted_at IS NULL "
                "ORDER BY CASE WHEN due_on IS NULL THEN 1 ELSE 0 END,due_on,id",
                (course_id,),
            ).fetchall()
        )

    def assessment(self, course_id: str, assessment_id: str):
        row = self.connection.execute(
            "SELECT id,assessment_type,title,due_on,due_time,status,weight_bps,"
            "max_points_milli,earned_points_milli,description "
            "FROM assessments WHERE id=? AND course_id=? AND deleted_at IS NULL",
            (assessment_id, course_id),
        ).fetchone()
        if row is None:
            raise ExamIntelligenceNotFoundError(
                "target assessment is not an active assessment in selected course"
            )
        return row

    def questions_for_course(self, course_id: str):
        return tuple(
            self.connection.execute(
                "SELECT q.id,q.assessment_id,q.ordinal,q.question_text,"
                "q.max_marks_milli,q.status,q.user_notes,"
                "a.title AS assessment_title,a.assessment_type,a.due_on,"
                "a.status AS assessment_status,a.description AS assessment_description "
                "FROM questions q "
                "JOIN assessments a ON a.id=q.assessment_id "
                "WHERE a.course_id=? AND a.deleted_at IS NULL "
                "AND q.deleted_at IS NULL "
                "ORDER BY a.id,q.ordinal,q.id",
                (course_id,),
            ).fetchall()
        )

    def mappings_for_question(self, question_id: str):
        return tuple(
            self.connection.execute(
                "SELECT id,topic_id,score,rank,method,state,reason,created_at,reviewed_at "
                "FROM question_topic_mappings WHERE question_id=? "
                "ORDER BY CASE state WHEN 'accepted' THEN 0 ELSE 1 END,"
                "CASE WHEN rank IS NULL THEN 2147483647 ELSE rank END,id",
                (question_id,),
            ).fetchall()
        )

    def sources_for_question(self, question_id: str):
        return tuple(
            self.connection.execute(
                "SELECT id,document_id,resource_id,note_id,page_number,locator,"
                "raw_source_label,created_at FROM question_sources "
                "WHERE question_id=? ORDER BY id",
                (question_id,),
            ).fetchall()
        )

    def attempts_for_question(self, question_id: str):
        return tuple(
            self.connection.execute(
                "SELECT id,attempt_number,outcome,earned_marks_milli,max_marks_milli,"
                "occurred_at FROM question_attempts WHERE question_id=? "
                "ORDER BY attempt_number,id",
                (question_id,),
            ).fetchall()
        )

    def unresolved_mistake_count(self, question_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM mistake_events m "
                "JOIN question_attempts qa ON qa.id=m.attempt_id "
                "WHERE qa.question_id=? AND m.resolved_at IS NULL",
                (question_id,),
            ).fetchone()[0]
        )

    def target_topic_ids(self, assessment_id: str):
        direct = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT topic_id FROM assessment_topics "
                "WHERE assessment_id=? AND topic_id IS NOT NULL",
                (assessment_id,),
            ).fetchall()
        }
        question_mapped = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT qtm.topic_id "
                "FROM questions q "
                "JOIN question_topic_mappings qtm ON qtm.question_id=q.id "
                "WHERE q.assessment_id=? AND q.deleted_at IS NULL "
                "AND qtm.state='accepted'",
                (assessment_id,),
            ).fetchall()
        }
        return tuple(sorted(direct | question_mapped))
