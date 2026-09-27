"""Read-only, content-free projection of the assessment lifecycle.

Deliberately select metadata, never question bodies or hidden package/snapshot JSON.
The owning service supplies a read-only SQLite connection.
"""
from __future__ import annotations

import sqlite3


class SQLiteAssessmentWorkspaceRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def courses(self):
        return tuple(dict(row) for row in self.connection.execute(
            "SELECT id, code, name FROM courses WHERE deleted_at IS NULL ORDER BY code COLLATE NOCASE, id"
        ))

    def rows(self):
        # One canonical assessment, with an active attempt preferred to a terminal
        # attempt. Stable IDs break timestamp ties (imports may share a second).
        canonical = self.connection.execute("""
            SELECT a.id, a.course_id, a.title, a.assessment_type, c.code AS course_code,
                   c.name AS course_name, r.mode, r.duration_minutes,
                   a.max_points_milli AS max_marks_milli, r.package_revision,
                   COALESCE(b.workspace_kind, '') AS workspace_kind,
                   COALESCE(s.started_at, a.created_at) AS updated_at,
                   'assessment' AS entry_type, a.id AS assessment_id,
                   (SELECT COUNT(*) FROM questions q WHERE q.assessment_id=a.id
                      AND q.deleted_at IS NULL) AS question_count,
                   (SELECT COUNT(*) FROM assessment_test_sessions h
                      WHERE h.assessment_id=a.id) AS attempt_count,
                   s.id AS session_id, s.status AS session_status, s.expires_at,
                   e.status AS evaluation_status
            FROM assessments a
            JOIN courses c ON c.id=a.course_id
            JOIN assessment_runtime_specs r ON r.assessment_id=a.id
            LEFT JOIN assessment_import_batches b ON b.id=(
                SELECT bi.id FROM assessment_import_batches bi
                WHERE bi.assessment_id=a.id AND bi.status='approved'
                ORDER BY bi.package_revision DESC, bi.id DESC LIMIT 1)
            LEFT JOIN assessment_test_sessions s ON s.id=(
                SELECT si.id FROM assessment_test_sessions si WHERE si.assessment_id=a.id
                ORDER BY (si.status='active') DESC, si.started_at DESC, si.id DESC LIMIT 1)
            LEFT JOIN assessment_session_evaluations e ON e.session_id=s.id
            WHERE a.deleted_at IS NULL AND c.deleted_at IS NULL
        """).fetchall()
        # Prior revisions are kept in the authoring history; only the current
        # package family belongs in the action queue. Approved rows live above.
        batches = self.connection.execute("""
            SELECT b.id, b.course_id, b.title, b.assessment_type,
                   c.code AS course_code, c.name AS course_name, b.mode,
                   b.duration_minutes, b.total_marks_milli AS max_marks_milli,
                   b.package_revision, b.workspace_kind, b.updated_at, b.status,
                   'package' AS entry_type, NULL AS assessment_id,
                   (SELECT COUNT(*) FROM assessment_import_questions q
                      WHERE q.batch_id=b.id) AS question_count,
                   0 AS attempt_count, NULL AS session_id, NULL AS session_status,
                   NULL AS expires_at, NULL AS evaluation_status
            FROM assessment_import_batches b JOIN courses c ON c.id=b.course_id
            WHERE b.status!='approved' AND c.deleted_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM assessment_import_batches newer
                  WHERE newer.package_id=b.package_id
                    AND newer.package_revision>b.package_revision)
        """).fetchall()
        return tuple(dict(row) for row in (*canonical, *batches))

    def history(self, assessment_id: str):
        # Header-only history remains safe even for an active attempt.
        return tuple(dict(row) for row in self.connection.execute("""
            SELECT s.id, s.id AS session_id, s.assessment_id, a.course_id,
                   s.title_snapshot AS title, s.course_code_snapshot AS course_code,
                   s.course_name_snapshot AS course_name, a.assessment_type,
                   s.mode, s.duration_seconds / 60 AS duration_minutes,
                   s.max_marks_milli, s.question_count, s.started_at AS updated_at,
                   s.status AS session_status, s.expires_at, e.status AS evaluation_status,
                   'attempt' AS entry_type
            FROM assessment_test_sessions s JOIN assessments a ON a.id=s.assessment_id
            LEFT JOIN assessment_session_evaluations e ON e.session_id=s.id
            WHERE s.assessment_id=? ORDER BY s.started_at DESC, s.id DESC
        """, (str(assessment_id),)))
