"""Read-only SQLite queries for Assessment Studio Phase E intelligence."""

from __future__ import annotations

import sqlite3


_REQUIRED_TABLES = {
    "courses",
    "topics",
    "assessments",
    "assessment_runtime_specs",
    "assessment_test_sessions",
    "assessment_test_session_questions",
    "assessment_test_responses",
    "assessment_session_evaluations",
    "assessment_response_evaluations",
    "assessment_evaluation_mistakes",
}


class AssessmentIntelligenceRepositoryError(RuntimeError):
    pass


class AssessmentIntelligenceRepositorySchemaError(AssessmentIntelligenceRepositoryError):
    pass


class AssessmentIntelligenceRepositoryNotFoundError(AssessmentIntelligenceRepositoryError):
    pass


class SQLiteAssessmentIntelligenceRepository:
    """Read-only query boundary for assessment analytics."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("explicit sqlite3.Connection required")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self._validate_schema()

    def _validate_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise AssessmentIntelligenceRepositorySchemaError(
                "Assessment Intelligence schema is unavailable; missing: {}".format(
                    ", ".join(missing)
                )
            )

    @staticmethod
    def _dict(row):
        return dict(row) if row is not None else None

    def get_course(self, course_id: str):
        row = self.connection.execute(
            "SELECT id, code, name FROM courses "
            "WHERE id=? AND deleted_at IS NULL",
            (str(course_id),),
        ).fetchone()
        return self._dict(row)

    def list_courses_with_confirmed_sessions(self):
        rows = self.connection.execute(
            "SELECT c.id, c.code, c.name, "
            "COUNT(DISTINCT s.id) AS confirmed_session_count, "
            "COUNT(DISTINCT q.id) AS evaluated_question_count "
            "FROM courses c "
            "JOIN assessments a ON a.course_id=c.id AND a.deleted_at IS NULL "
            "JOIN assessment_test_sessions s ON s.assessment_id=a.id "
            "JOIN assessment_session_evaluations se "
            "ON se.session_id=s.id AND se.status='confirmed' "
            "JOIN assessment_test_session_questions q ON q.session_id=s.id "
            "WHERE c.deleted_at IS NULL "
            "GROUP BY c.id, c.code, c.name "
            "ORDER BY c.code COLLATE NOCASE, c.name COLLATE NOCASE"
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def list_confirmed_sessions(self, *, course_id: str | None = None, limit: int = 300):
        where = ""
        params = []
        if course_id is not None:
            where = "AND c.id=?"
            params.append(str(course_id))
        params.append(max(1, min(int(limit), 1000)))
        rows = self.connection.execute(
            "SELECT s.id AS session_id, s.assessment_id, s.title_snapshot, "
            "s.course_code_snapshot, s.course_name_snapshot, s.mode, "
            "s.question_count, s.max_marks_milli, s.started_at, s.submitted_at, "
            "s.submission_reason, a.assessment_type, c.id AS course_id, "
            "r.origin, r.package_id, r.package_revision, "
            "se.id AS session_evaluation_id, se.status AS evaluation_status, "
            "se.confirmed_at AS evaluation_confirmed_at, "
            "COALESCE((SELECT SUM(tr.focus_seconds) "
            " FROM assessment_test_responses tr "
            " JOIN assessment_test_session_questions tq "
            " ON tq.id=tr.session_question_id "
            " WHERE tq.session_id=s.id), 0) AS focus_seconds "
            "FROM assessment_test_sessions s "
            "JOIN assessments a ON a.id=s.assessment_id "
            "JOIN courses c ON c.id=a.course_id "
            "JOIN assessment_runtime_specs r ON r.assessment_id=a.id "
            "JOIN assessment_session_evaluations se "
            "ON se.session_id=s.id AND se.status='confirmed' "
            "WHERE s.status IN ('submitted','expired') "
            "AND a.deleted_at IS NULL AND c.deleted_at IS NULL "
            "{} "
            "ORDER BY COALESCE(s.submitted_at, s.expires_at, s.started_at) DESC, s.id DESC "
            "LIMIT ?".format(where),
            tuple(params),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_session_header(self, session_id: str):
        row = self.connection.execute(
            "SELECT s.id AS session_id, s.assessment_id, s.status AS session_status, "
            "s.mode, s.title_snapshot, s.course_code_snapshot, "
            "s.course_name_snapshot, s.question_count, s.max_marks_milli, "
            "s.started_at, s.expires_at, s.submitted_at, s.submission_reason, "
            "a.assessment_type, c.id AS course_id, "
            "r.origin, r.package_id, r.package_revision, "
            "se.id AS session_evaluation_id, se.status AS evaluation_status, "
            "se.engine_version, se.created_at AS evaluation_created_at, "
            "se.updated_at AS evaluation_updated_at, "
            "se.confirmed_at AS evaluation_confirmed_at "
            "FROM assessment_test_sessions s "
            "JOIN assessments a ON a.id=s.assessment_id "
            "JOIN courses c ON c.id=a.course_id "
            "JOIN assessment_runtime_specs r ON r.assessment_id=a.id "
            "LEFT JOIN assessment_session_evaluations se ON se.session_id=s.id "
            "WHERE s.id=? AND a.deleted_at IS NULL AND c.deleted_at IS NULL",
            (str(session_id),),
        ).fetchone()
        return self._dict(row)

    def list_session_question_evidence(self, session_id: str):
        rows = self.connection.execute(
            "SELECT q.id AS session_question_id, q.question_id, q.ordinal, "
            "q.question_number, q.section_label, q.question_type, "
            "q.max_marks_milli, q.negative_marks_milli, q.scoring_policy, "
            "q.topic_id, t.name AS topic_name, q.chapter_label, "
            "q.subtopic_label, q.concepts_json, q.difficulty, "
            "q.estimated_seconds, tr.focus_seconds, tr.state AS response_state, "
            "ev.id AS response_evaluation_id, ev.evaluator_type, "
            "ev.evaluator_model, ev.status AS evaluation_status, ev.outcome, "
            "ev.awarded_marks_milli, ev.penalty_marks_milli, ev.confidence, "
            "ev.feedback_text "
            "FROM assessment_test_session_questions q "
            "JOIN assessment_test_responses tr ON tr.session_question_id=q.id "
            "LEFT JOIN topics t ON t.id=q.topic_id "
            "LEFT JOIN assessment_response_evaluations ev "
            "ON ev.session_question_id=q.id "
            "WHERE q.session_id=? "
            "ORDER BY q.ordinal",
            (str(session_id),),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def list_confirmed_question_evidence(self, *, course_id: str | None = None):
        where = ""
        params = []
        if course_id is not None:
            where = "AND c.id=?"
            params.append(str(course_id))
        rows = self.connection.execute(
            "SELECT s.id AS session_id, s.assessment_id, s.title_snapshot, "
            "s.course_code_snapshot, s.mode, "
            "COALESCE(s.submitted_at, s.expires_at, s.started_at) AS occurred_at, "
            "a.assessment_type, c.id AS course_id, c.code AS course_code, "
            "c.name AS course_name, q.id AS session_question_id, q.question_id, "
            "q.ordinal, q.question_number, q.question_type, "
            "q.max_marks_milli, q.negative_marks_milli, q.scoring_policy, "
            "q.topic_id, t.name AS topic_name, q.chapter_label, q.subtopic_label, "
            "q.concepts_json, q.difficulty, q.estimated_seconds, "
            "tr.focus_seconds, ev.id AS response_evaluation_id, "
            "ev.evaluator_type, ev.status AS evaluation_status, ev.outcome, "
            "ev.awarded_marks_milli, ev.penalty_marks_milli, ev.confidence "
            "FROM assessment_test_sessions s "
            "JOIN assessments a ON a.id=s.assessment_id "
            "JOIN courses c ON c.id=a.course_id "
            "JOIN assessment_session_evaluations se "
            "ON se.session_id=s.id AND se.status='confirmed' "
            "JOIN assessment_test_session_questions q ON q.session_id=s.id "
            "JOIN assessment_test_responses tr ON tr.session_question_id=q.id "
            "JOIN assessment_response_evaluations ev "
            "ON ev.session_question_id=q.id "
            "LEFT JOIN topics t ON t.id=q.topic_id "
            "WHERE s.status IN ('submitted','expired') "
            "AND ev.status IN ('auto_confirmed','confirmed') "
            "AND ev.awarded_marks_milli IS NOT NULL "
            "AND a.deleted_at IS NULL AND c.deleted_at IS NULL "
            "{} "
            "ORDER BY occurred_at, s.id, q.ordinal".format(where),
            tuple(params),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def list_confirmed_mistakes(self, *, course_id: str | None = None):
        where = ""
        params = []
        if course_id is not None:
            where = "AND c.id=?"
            params.append(str(course_id))
        rows = self.connection.execute(
            "SELECT m.id, m.category, m.note, m.source_type, "
            "m.response_evaluation_id, s.id AS session_id, "
            "COALESCE(s.submitted_at, s.expires_at, s.started_at) AS occurred_at, "
            "c.id AS course_id, c.code AS course_code, c.name AS course_name, "
            "q.topic_id, t.name AS topic_name, q.chapter_label, "
            "q.subtopic_label, q.question_type, q.difficulty "
            "FROM assessment_evaluation_mistakes m "
            "JOIN assessment_response_evaluations ev "
            "ON ev.id=m.response_evaluation_id "
            "JOIN assessment_session_evaluations se "
            "ON se.id=ev.session_evaluation_id AND se.status='confirmed' "
            "JOIN assessment_test_session_questions q "
            "ON q.id=ev.session_question_id "
            "JOIN assessment_test_sessions s ON s.id=q.session_id "
            "JOIN assessments a ON a.id=s.assessment_id "
            "JOIN courses c ON c.id=a.course_id "
            "LEFT JOIN topics t ON t.id=q.topic_id "
            "WHERE m.status='confirmed' "
            "AND ev.status IN ('auto_confirmed','confirmed') "
            "AND a.deleted_at IS NULL AND c.deleted_at IS NULL "
            "{} "
            "ORDER BY occurred_at, m.created_at, m.id".format(where),
            tuple(params),
        ).fetchall()
        return tuple(dict(row) for row in rows)
