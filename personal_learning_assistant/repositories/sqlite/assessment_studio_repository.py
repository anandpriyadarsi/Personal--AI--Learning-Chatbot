"""SQLite repository for Assessment Studio Phase A template configuration."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

from personal_learning_assistant.repositories.sqlite.connection import transaction


_REQUIRED_TABLES = {
    "courses",
    "topics",
    "assessment_templates",
    "assessment_template_topics",
    "assessment_template_patterns",
}


class AssessmentStudioRepositoryError(RuntimeError):
    """Base error for Assessment Studio persistence."""


class AssessmentStudioRepositorySchemaError(AssessmentStudioRepositoryError):
    """Raised when migration 0009 has not been applied."""


class AssessmentStudioRepositoryNotFoundError(AssessmentStudioRepositoryError):
    """Raised when a requested template does not exist."""


class AssessmentStudioRepositoryConflictError(AssessmentStudioRepositoryError):
    """Raised for duplicate names or stale optimistic revisions."""


class AssessmentStudioRepositoryDataError(AssessmentStudioRepositoryError):
    """Raised when a foreign-key/domain relationship is invalid."""


class SQLiteAssessmentStudioRepository:
    """Normalized repository for reusable assessment templates."""

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
            raise AssessmentStudioRepositorySchemaError(
                "Assessment Studio schema is unavailable; missing: {}".format(
                    ", ".join(missing)
                )
            )

    def list_courses(self):
        rows = self.connection.execute(
            "SELECT id, code, name FROM courses "
            "WHERE deleted_at IS NULL ORDER BY code COLLATE NOCASE, name"
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_course(self, course_id: str):
        row = self.connection.execute(
            "SELECT id, code, name FROM courses "
            "WHERE id=? AND deleted_at IS NULL",
            (str(course_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_topics(self, course_id: str | None = None):
        if course_id:
            rows = self.connection.execute(
                "SELECT id, course_id, name, position FROM topics "
                "WHERE course_id=? AND deleted_at IS NULL "
                "ORDER BY position, name COLLATE NOCASE",
                (str(course_id),),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT id, course_id, name, position FROM topics "
                "WHERE deleted_at IS NULL "
                "ORDER BY course_id, position, name COLLATE NOCASE"
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def list_templates(
        self,
        *,
        course_id: str | None = None,
        include_inactive: bool = True,
    ):
        where = ["c.deleted_at IS NULL"]
        params: list[Any] = []
        if course_id:
            where.append("t.course_id=?")
            params.append(str(course_id))
        if not include_inactive:
            where.append("t.is_active=1")
        rows = self.connection.execute(
            "SELECT t.id, t.course_id, c.code AS course_code, c.name AS course_name, "
            "t.name, t.assessment_type, t.mode, t.description, t.instructions, "
            "t.duration_minutes, t.total_marks_milli, t.is_active, t.revision, "
            "t.provenance, t.created_at, t.updated_at, t.deactivated_at, "
            "(SELECT COUNT(*) FROM assessment_template_topics x "
            " WHERE x.template_id=t.id) AS topic_count, "
            "(SELECT COALESCE(SUM(p.question_count),0) "
            " FROM assessment_template_patterns p "
            " WHERE p.template_id=t.id) AS question_count "
            "FROM assessment_templates t "
            "JOIN courses c ON c.id=t.course_id "
            "WHERE {} "
            "ORDER BY t.is_active DESC, c.code COLLATE NOCASE, t.name COLLATE NOCASE"
            .format(" AND ".join(where)),
            tuple(params),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_template(self, template_id: str):
        row = self.connection.execute(
            "SELECT t.*, c.code AS course_code, c.name AS course_name "
            "FROM assessment_templates t "
            "JOIN courses c ON c.id=t.course_id "
            "WHERE t.id=? AND c.deleted_at IS NULL",
            (str(template_id),),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["topics"] = tuple(
            dict(item)
            for item in self.connection.execute(
                "SELECT tp.id, tp.name, tt.position "
                "FROM assessment_template_topics tt "
                "JOIN topics tp ON tp.id=tt.topic_id "
                "WHERE tt.template_id=? AND tp.deleted_at IS NULL "
                "ORDER BY tt.position, tp.name COLLATE NOCASE",
                (str(template_id),),
            ).fetchall()
        )
        result["patterns"] = tuple(
            dict(item)
            for item in self.connection.execute(
                "SELECT id, position, question_type, question_count, "
                "marks_each_milli, negative_marks_milli, scoring_policy "
                "FROM assessment_template_patterns "
                "WHERE template_id=? ORDER BY position",
                (str(template_id),),
            ).fetchall()
        )
        return result

    def _validate_scope(self, course_id: str, topic_ids: Sequence[str]) -> None:
        if self.get_course(course_id) is None:
            raise AssessmentStudioRepositoryDataError("course does not exist")
        for topic_id in topic_ids:
            row = self.connection.execute(
                "SELECT 1 FROM topics "
                "WHERE id=? AND course_id=? AND deleted_at IS NULL",
                (str(topic_id), str(course_id)),
            ).fetchone()
            if row is None:
                raise AssessmentStudioRepositoryDataError(
                    "template topic does not belong to the selected course"
                )

    @staticmethod
    def _insert_topics(connection, template_id: str, topic_ids: Sequence[str]) -> None:
        for position, topic_id in enumerate(topic_ids, start=1):
            connection.execute(
                "INSERT INTO assessment_template_topics "
                "(template_id, topic_id, position) VALUES (?, ?, ?)",
                (template_id, topic_id, position),
            )

    @staticmethod
    def _insert_patterns(
        connection,
        template_id: str,
        patterns: Sequence[Mapping[str, Any]],
        now: str,
    ) -> None:
        for position, pattern in enumerate(patterns, start=1):
            connection.execute(
                "INSERT INTO assessment_template_patterns "
                "(id, template_id, position, question_type, question_count, "
                "marks_each_milli, negative_marks_milli, scoring_policy, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(pattern["id"]),
                    template_id,
                    position,
                    str(pattern["question_type"]),
                    int(pattern["question_count"]),
                    int(pattern["marks_each_milli"]),
                    int(pattern["negative_marks_milli"]),
                    str(pattern["scoring_policy"]),
                    now,
                    now,
                ),
            )

    def create_template(
        self,
        record: Mapping[str, Any],
        *,
        topic_ids: Sequence[str],
        patterns: Sequence[Mapping[str, Any]],
    ):
        template_id = str(record["id"])
        course_id = str(record["course_id"])
        self._validate_scope(course_id, topic_ids)
        try:
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    "INSERT INTO assessment_templates "
                    "(id, course_id, name, assessment_type, mode, description, "
                    "instructions, duration_minutes, total_marks_milli, is_active, "
                    "revision, provenance, created_at, updated_at, deactivated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, NULL)",
                    (
                        template_id,
                        course_id,
                        str(record["name"]),
                        str(record["assessment_type"]),
                        str(record["mode"]),
                        str(record.get("description") or ""),
                        str(record.get("instructions") or ""),
                        int(record["duration_minutes"]),
                        record.get("total_marks_milli"),
                        str(record.get("provenance") or "user"),
                        str(record["created_at"]),
                        str(record["updated_at"]),
                    ),
                )
                self._insert_topics(self.connection, template_id, topic_ids)
                self._insert_patterns(
                    self.connection, template_id, patterns, str(record["updated_at"])
                )
        except sqlite3.IntegrityError as error:
            if "assessment_templates.course_id, assessment_templates.name" in str(error):
                raise AssessmentStudioRepositoryConflictError(
                    "A template with this name already exists for the course."
                ) from error
            raise
        return self.get_template(template_id)

    def update_template(
        self,
        template_id: str,
        *,
        expected_revision: int,
        record: Mapping[str, Any],
        topic_ids: Sequence[str],
        patterns: Sequence[Mapping[str, Any]],
    ):
        template_id = str(template_id)
        course_id = str(record["course_id"])
        self._validate_scope(course_id, topic_ids)
        try:
            with transaction(self.connection, immediate=True):
                cursor = self.connection.execute(
                    "UPDATE assessment_templates SET "
                    "course_id=?, name=?, assessment_type=?, mode=?, description=?, "
                    "instructions=?, duration_minutes=?, total_marks_milli=?, "
                    "provenance=?, updated_at=?, revision=revision+1 "
                    "WHERE id=? AND revision=?",
                    (
                        course_id,
                        str(record["name"]),
                        str(record["assessment_type"]),
                        str(record["mode"]),
                        str(record.get("description") or ""),
                        str(record.get("instructions") or ""),
                        int(record["duration_minutes"]),
                        record.get("total_marks_milli"),
                        str(record.get("provenance") or "user"),
                        str(record["updated_at"]),
                        template_id,
                        int(expected_revision),
                    ),
                )
                if cursor.rowcount != 1:
                    exists = self.connection.execute(
                        "SELECT 1 FROM assessment_templates WHERE id=?",
                        (template_id,),
                    ).fetchone()
                    if exists is None:
                        raise AssessmentStudioRepositoryNotFoundError("Template not found.")
                    raise AssessmentStudioRepositoryConflictError(
                        "Template changed since this form was opened."
                    )
                self.connection.execute(
                    "DELETE FROM assessment_template_topics WHERE template_id=?",
                    (template_id,),
                )
                self.connection.execute(
                    "DELETE FROM assessment_template_patterns WHERE template_id=?",
                    (template_id,),
                )
                self._insert_topics(self.connection, template_id, topic_ids)
                self._insert_patterns(
                    self.connection, template_id, patterns, str(record["updated_at"])
                )
        except sqlite3.IntegrityError as error:
            if "assessment_templates.course_id, assessment_templates.name" in str(error):
                raise AssessmentStudioRepositoryConflictError(
                    "A template with this name already exists for the course."
                ) from error
            raise
        return self.get_template(template_id)

    def set_active(
        self,
        template_id: str,
        *,
        expected_revision: int,
        active: bool,
        now: str,
    ):
        template_id = str(template_id)
        with transaction(self.connection, immediate=True):
            cursor = self.connection.execute(
                "UPDATE assessment_templates SET is_active=?, deactivated_at=?, "
                "updated_at=?, revision=revision+1 WHERE id=? AND revision=?",
                (
                    1 if active else 0,
                    None if active else now,
                    now,
                    template_id,
                    int(expected_revision),
                ),
            )
            if cursor.rowcount != 1:
                exists = self.connection.execute(
                    "SELECT 1 FROM assessment_templates WHERE id=?",
                    (template_id,),
                ).fetchone()
                if exists is None:
                    raise AssessmentStudioRepositoryNotFoundError("Template not found.")
                raise AssessmentStudioRepositoryConflictError(
                    "Template changed since this action was prepared."
                )
        return self.get_template(template_id)
