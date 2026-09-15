"""Phase 4.10 writable SQLite command repositories.

These repositories are deliberately separate from the Phase 4.1-4.8 shadow
read repositories.  A command repository can mutate SQLite only when an
explicit Phase 4 authority-control file already says ``storage_backend=sqlite``
and legacy writes are blocked in the same atomic state.

The classes accept relational SQLite identifiers.  They do not guess legacy
IDs, rewrite migration evidence, open a production database implicitly, or
perform the final authority promotion.  Application compatibility/routing is a
later step; this module establishes the transaction-safe relational command
surface that routing can target.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
)


PathLike = Union[str, Path]


class SQLiteAuthorityCommandError(RuntimeError):
    """Base error for Phase 4.10 authoritative SQLite commands."""


class SQLiteAuthorityNotActiveError(SQLiteAuthorityCommandError):
    """Raised when a command is attempted before the atomic authority switch."""


class SQLiteAuthoritySchemaError(SQLiteAuthorityCommandError):
    """Raised when required relational tables are unavailable."""


class SQLiteAuthorityDataError(SQLiteAuthorityCommandError, ValueError):
    """Raised when command input cannot satisfy the relational contract."""


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SQLiteAuthorityDataError("{} must not be empty".format(field))
    return text


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _integer(value: Any, field: str, *, minimum: Optional[int] = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise SQLiteAuthorityDataError("{} must be an integer".format(field)) from error
    if minimum is not None and result < minimum:
        raise SQLiteAuthorityDataError(
            "{} must be at least {}".format(field, minimum)
        )
    return result


def _optional_integer(
    value: Any,
    field: str,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> Optional[int]:
    if value is None or value == "":
        return None
    result = _integer(value, field, minimum=minimum)
    if maximum is not None and result > maximum:
        raise SQLiteAuthorityDataError(
            "{} must be at most {}".format(field, maximum)
        )
    return result


def _optional_float(value: Any, field: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise SQLiteAuthorityDataError("{} must be numeric".format(field)) from error


def _bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def _json_text(value: Any, field: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise SQLiteAuthorityDataError("{} must be JSON serializable".format(field)) from error


def _json_object_text(value: Any, field: str) -> str:
    if not isinstance(value, Mapping):
        raise SQLiteAuthorityDataError("{} must be a mapping, not pre-encoded JSON".format(field))
    return _json_text(dict(value), field)


@contextmanager
def _transaction(connection: sqlite3.Connection):
    if connection.in_transaction:
        raise SQLiteAuthorityCommandError(
            "Phase 4.10 command repository refuses nested transactions"
        )
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


class _SQLiteCommandBase:
    REQUIRED_TABLES: Tuple[str, ...] = ()

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        authority_control_path: PathLike,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an open sqlite3.Connection")
        self.connection = connection
        self.authority_control_path = Path(authority_control_path)
        self._validate_schema()

    def _validate_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = sorted(set(self.REQUIRED_TABLES) - tables)
        if missing:
            raise SQLiteAuthoritySchemaError(
                "required SQLite command tables are missing: {}".format(
                    ", ".join(missing)
                )
            )

    def _require_authority(self) -> None:
        state = read_authority_control(self.authority_control_path)
        if state.storage_backend != BACKEND_SQLITE or not state.legacy_writes_blocked:
            raise SQLiteAuthorityNotActiveError(
                "SQLite command writes require the atomic Phase 4 authority state; "
                "shadow/legacy databases remain read-only candidates."
            )

    def _write(self, callback):
        self._require_authority()
        with _transaction(self.connection):
            return callback()

    def _exists(self, table: str, entity_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM {} WHERE id = ?".format(table),
            (entity_id,),
        ).fetchone()
        return row is not None

    def _require_row(self, table: str, entity_id: Any, field: str) -> str:
        value = _required_text(entity_id, field)
        if not self._exists(table, value):
            raise SQLiteAuthorityDataError(
                "{} does not reference an existing {} row: {}".format(
                    field, table, value
                )
            )
        return value


class SQLiteCourseCommandRepository(_SQLiteCommandBase):
    """Transactional commands for semesters, courses, topics and active course."""

    REQUIRED_TABLES = (
        "app_settings",
        "semesters",
        "courses",
        "semester_courses",
        "topics",
    )

    def upsert_semester(self, record: Mapping[str, Any]) -> str:
        semester_id = _required_text(record.get("id"), "semester.id")
        name = _required_text(record.get("name"), "semester.name")
        academic_year = _required_text(record.get("academic_year"), "semester.academic_year")
        created_at = _required_text(record.get("created_at"), "semester.created_at")
        updated_at = _required_text(record.get("updated_at"), "semester.updated_at")

        def command():
            self.connection.execute(
                "INSERT INTO semesters "
                "(id, name, academic_year, starts_on, ends_on, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, academic_year=excluded.academic_year, "
                "starts_on=excluded.starts_on, ends_on=excluded.ends_on, "
                "status=excluded.status, updated_at=excluded.updated_at",
                (
                    semester_id,
                    name,
                    academic_year,
                    _optional_text(record.get("starts_on")),
                    _optional_text(record.get("ends_on")),
                    str(record.get("status") or "planned"),
                    created_at,
                    updated_at,
                ),
            )
            return semester_id

        return self._write(command)

    def upsert_course(self, record: Mapping[str, Any]) -> str:
        course_id = _required_text(record.get("id"), "course.id")
        code = _required_text(record.get("code"), "course.code").upper()
        name = _required_text(record.get("name"), "course.name")
        created_at = _required_text(record.get("created_at"), "course.created_at")
        updated_at = _required_text(record.get("updated_at"), "course.updated_at")

        def command():
            self.connection.execute(
                "INSERT INTO courses "
                "(id, code, name, status, description, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "code=excluded.code, name=excluded.name, status=excluded.status, "
                "description=excluded.description, updated_at=excluded.updated_at, "
                "deleted_at=excluded.deleted_at",
                (
                    course_id,
                    code,
                    name,
                    str(record.get("status") or "active"),
                    str(record.get("description") or ""),
                    created_at,
                    updated_at,
                    _optional_text(record.get("deleted_at")),
                ),
            )
            return course_id

        return self._write(command)

    def upsert_semester_course(self, record: Mapping[str, Any]) -> Tuple[str, str]:
        semester_id = _required_text(record.get("semester_id"), "semester_course.semester_id")
        course_id = _required_text(record.get("course_id"), "semester_course.course_id")
        credits = _optional_integer(record.get("credits_milli"), "credits_milli", minimum=0)

        def command():
            if not self._exists("semesters", semester_id):
                raise SQLiteAuthorityDataError("semester_course semester does not exist")
            if not self._exists("courses", course_id):
                raise SQLiteAuthorityDataError("semester_course course does not exist")
            self.connection.execute(
                "INSERT INTO semester_courses "
                "(semester_id, course_id, credits_milli, instructor, enrollment_status) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(semester_id, course_id) DO UPDATE SET "
                "credits_milli=excluded.credits_milli, instructor=excluded.instructor, "
                "enrollment_status=excluded.enrollment_status",
                (
                    semester_id,
                    course_id,
                    credits,
                    str(record.get("instructor") or ""),
                    str(record.get("enrollment_status") or "enrolled"),
                ),
            )
            return (semester_id, course_id)

        return self._write(command)

    def upsert_topic(self, record: Mapping[str, Any]) -> str:
        topic_id = _required_text(record.get("id"), "topic.id")
        course_id = _required_text(record.get("course_id"), "topic.course_id")
        name = _required_text(record.get("name"), "topic.name")
        normalized_name = str(record.get("normalized_name") or name.casefold()).strip()
        created_at = _required_text(record.get("created_at"), "topic.created_at")
        updated_at = _required_text(record.get("updated_at"), "topic.updated_at")
        position = _integer(record.get("position", 0), "topic.position", minimum=0)
        confidence = _optional_integer(
            record.get("confidence"), "topic.confidence", minimum=0, maximum=5
        )

        def command():
            if not self._exists("courses", course_id):
                raise SQLiteAuthorityDataError("topic course does not exist")
            self.connection.execute(
                "INSERT INTO topics "
                "(id, course_id, name, normalized_name, position, status, confidence, "
                "raw_import_status, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "course_id=excluded.course_id, name=excluded.name, "
                "normalized_name=excluded.normalized_name, position=excluded.position, "
                "status=excluded.status, confidence=excluded.confidence, "
                "raw_import_status=excluded.raw_import_status, "
                "updated_at=excluded.updated_at, deleted_at=excluded.deleted_at",
                (
                    topic_id,
                    course_id,
                    name,
                    normalized_name,
                    position,
                    str(record.get("status") or "not_started"),
                    confidence,
                    _optional_text(record.get("raw_import_status")),
                    created_at,
                    updated_at,
                    _optional_text(record.get("deleted_at")),
                ),
            )
            return topic_id

        return self._write(command)

    def set_active_course(self, course_id: str, *, updated_at: str) -> str:
        course_id = _required_text(course_id, "active_course_id")
        updated_at = _required_text(updated_at, "updated_at")

        def command():
            if not self._exists("courses", course_id):
                raise SQLiteAuthorityDataError("active course does not exist")
            self.connection.execute(
                "INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at",
                ("active_course_id", json.dumps(course_id), updated_at),
            )
            return course_id

        return self._write(command)

    def soft_delete_course(self, course_id: str, *, deleted_at: str) -> None:
        course_id = _required_text(course_id, "course_id")
        deleted_at = _required_text(deleted_at, "deleted_at")

        def command():
            cursor = self.connection.execute(
                "UPDATE courses SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
                (deleted_at, deleted_at, course_id),
            )
            if cursor.rowcount != 1:
                raise SQLiteAuthorityDataError("live course row was not found")

        self._write(command)

    def soft_delete_topic(self, topic_id: str, *, deleted_at: str) -> None:
        topic_id = _required_text(topic_id, "topic_id")
        deleted_at = _required_text(deleted_at, "deleted_at")

        def command():
            cursor = self.connection.execute(
                "UPDATE topics SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
                (deleted_at, deleted_at, topic_id),
            )
            if cursor.rowcount != 1:
                raise SQLiteAuthorityDataError("live topic row was not found")

        self._write(command)


class SQLiteAssessmentCommandRepository(_SQLiteCommandBase):
    """Transactional assessment and assessment-topic commands."""

    REQUIRED_TABLES = ("courses", "topics", "assessments", "assessment_topics")

    def upsert_assessment(self, record: Mapping[str, Any]) -> str:
        assessment_id = _required_text(record.get("id"), "assessment.id")
        course_id = _required_text(record.get("course_id"), "assessment.course_id")
        assessment_type = _required_text(record.get("assessment_type"), "assessment.assessment_type")
        title = _required_text(record.get("title"), "assessment.title")
        created_at = _required_text(record.get("created_at"), "assessment.created_at")
        updated_at = _required_text(record.get("updated_at"), "assessment.updated_at")

        def command():
            if not self._exists("courses", course_id):
                raise SQLiteAuthorityDataError("assessment course does not exist")
            self.connection.execute(
                "INSERT INTO assessments "
                "(id, course_id, assessment_type, title, due_on, due_time, status, "
                "weight_bps, max_points_milli, earned_points_milli, description, "
                "created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "course_id=excluded.course_id, assessment_type=excluded.assessment_type, "
                "title=excluded.title, due_on=excluded.due_on, due_time=excluded.due_time, "
                "status=excluded.status, weight_bps=excluded.weight_bps, "
                "max_points_milli=excluded.max_points_milli, "
                "earned_points_milli=excluded.earned_points_milli, "
                "description=excluded.description, updated_at=excluded.updated_at, "
                "deleted_at=excluded.deleted_at",
                (
                    assessment_id,
                    course_id,
                    assessment_type,
                    title,
                    _optional_text(record.get("due_on")),
                    _optional_text(record.get("due_time")),
                    str(record.get("status") or "pending"),
                    _optional_integer(record.get("weight_bps"), "weight_bps", minimum=0, maximum=10000),
                    _optional_integer(record.get("max_points_milli"), "max_points_milli", minimum=0),
                    _optional_integer(record.get("earned_points_milli"), "earned_points_milli", minimum=0),
                    str(record.get("description") or ""),
                    created_at,
                    updated_at,
                    _optional_text(record.get("deleted_at")),
                ),
            )
            return assessment_id

        return self._write(command)

    def replace_topics(
        self,
        assessment_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> Tuple[str, ...]:
        assessment_id = _required_text(assessment_id, "assessment_id")
        prepared = []
        for raw in rows:
            row_id = _required_text(raw.get("id"), "assessment_topic.id")
            topic_id = _optional_text(raw.get("topic_id"))
            raw_label = str(raw.get("raw_label") or "")
            if topic_id is None and not raw_label:
                raise SQLiteAuthorityDataError(
                    "assessment topic needs topic_id or raw_label"
                )
            prepared.append(
                (
                    row_id,
                    topic_id,
                    raw_label,
                    str(raw.get("source") or ""),
                    _optional_float(raw.get("confidence"), "assessment_topic.confidence"),
                    _required_text(raw.get("created_at"), "assessment_topic.created_at"),
                )
            )

        def command():
            if not self._exists("assessments", assessment_id):
                raise SQLiteAuthorityDataError("assessment does not exist")
            for _, topic_id, _, _, _, _ in prepared:
                if topic_id is not None and not self._exists("topics", topic_id):
                    raise SQLiteAuthorityDataError("assessment topic target does not exist")
            self.connection.execute(
                "DELETE FROM assessment_topics WHERE assessment_id = ?", (assessment_id,)
            )
            for row_id, topic_id, raw_label, source, confidence, created_at in prepared:
                self.connection.execute(
                    "INSERT INTO assessment_topics "
                    "(id, assessment_id, topic_id, raw_label, source, confidence, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (row_id, assessment_id, topic_id, raw_label, source, confidence, created_at),
                )
            return tuple(item[0] for item in prepared)

        return self._write(command)

    def soft_delete_assessment(self, assessment_id: str, *, deleted_at: str) -> None:
        assessment_id = _required_text(assessment_id, "assessment_id")
        deleted_at = _required_text(deleted_at, "deleted_at")

        def command():
            cursor = self.connection.execute(
                "UPDATE assessments SET deleted_at=?, updated_at=? "
                "WHERE id=? AND deleted_at IS NULL",
                (deleted_at, deleted_at, assessment_id),
            )
            if cursor.rowcount != 1:
                raise SQLiteAuthorityDataError("live assessment row was not found")

        self._write(command)


class SQLiteQuestionCommandRepository(_SQLiteCommandBase):
    """Question, source, mapping, attempt and mistake commands."""

    REQUIRED_TABLES = (
        "assessments",
        "topics",
        "questions",
        "question_sources",
        "question_topic_mappings",
        "question_attempts",
        "mistake_events",
    )

    def upsert_question(self, record: Mapping[str, Any]) -> str:
        question_id = _required_text(record.get("id"), "question.id")
        assessment_id = _required_text(record.get("assessment_id"), "question.assessment_id")
        ordinal = _integer(record.get("ordinal"), "question.ordinal", minimum=1)
        question_text = _required_text(record.get("question_text"), "question.question_text")
        created_at = _required_text(record.get("created_at"), "question.created_at")
        updated_at = _required_text(record.get("updated_at"), "question.updated_at")

        def command():
            if not self._exists("assessments", assessment_id):
                raise SQLiteAuthorityDataError("question assessment does not exist")
            self.connection.execute(
                "INSERT INTO questions "
                "(id, assessment_id, ordinal, question_text, max_marks_milli, status, "
                "user_notes, import_batch_id, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "assessment_id=excluded.assessment_id, ordinal=excluded.ordinal, "
                "question_text=excluded.question_text, max_marks_milli=excluded.max_marks_milli, "
                "status=excluded.status, user_notes=excluded.user_notes, "
                "import_batch_id=excluded.import_batch_id, updated_at=excluded.updated_at, "
                "deleted_at=excluded.deleted_at",
                (
                    question_id,
                    assessment_id,
                    ordinal,
                    question_text,
                    _optional_integer(record.get("max_marks_milli"), "max_marks_milli", minimum=0),
                    str(record.get("status") or "not_started"),
                    str(record.get("user_notes") or ""),
                    _optional_text(record.get("import_batch_id")),
                    created_at,
                    updated_at,
                    _optional_text(record.get("deleted_at")),
                ),
            )
            return question_id

        return self._write(command)

    def replace_sources(
        self,
        question_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> Tuple[str, ...]:
        question_id = _required_text(question_id, "question_id")
        prepared = []
        for raw in rows:
            row_id = _required_text(raw.get("id"), "question_source.id")
            document_id = _optional_text(raw.get("document_id"))
            resource_id = _optional_text(raw.get("resource_id"))
            note_id = _optional_text(raw.get("note_id"))
            raw_label = str(raw.get("raw_source_label") or "")
            if not any((document_id, resource_id, note_id, raw_label)):
                raise SQLiteAuthorityDataError(
                    "question source requires document/resource/note/raw label evidence"
                )
            prepared.append(
                (
                    row_id,
                    document_id,
                    resource_id,
                    note_id,
                    _optional_integer(raw.get("page_number"), "page_number", minimum=1),
                    str(raw.get("locator") or ""),
                    raw_label,
                    _required_text(raw.get("created_at"), "question_source.created_at"),
                )
            )

        def command():
            if not self._exists("questions", question_id):
                raise SQLiteAuthorityDataError("question does not exist")
            self.connection.execute("DELETE FROM question_sources WHERE question_id = ?", (question_id,))
            for row in prepared:
                self.connection.execute(
                    "INSERT INTO question_sources "
                    "(id, question_id, document_id, resource_id, note_id, page_number, "
                    "locator, raw_source_label, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row[0], question_id, *row[1:]),
                )
            return tuple(item[0] for item in prepared)

        return self._write(command)

    def replace_topic_mappings(
        self,
        question_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> Tuple[str, ...]:
        question_id = _required_text(question_id, "question_id")
        prepared = []
        for raw in rows:
            prepared.append(
                (
                    _required_text(raw.get("id"), "question_topic_mapping.id"),
                    _required_text(raw.get("topic_id"), "question_topic_mapping.topic_id"),
                    _optional_float(raw.get("score"), "question_topic_mapping.score"),
                    _optional_integer(raw.get("rank"), "question_topic_mapping.rank", minimum=1),
                    _required_text(raw.get("method"), "question_topic_mapping.method"),
                    str(raw.get("state") or "proposed"),
                    str(raw.get("reason") or ""),
                    _required_text(raw.get("created_at"), "question_topic_mapping.created_at"),
                    _optional_text(raw.get("reviewed_at")),
                )
            )

        def command():
            if not self._exists("questions", question_id):
                raise SQLiteAuthorityDataError("question does not exist")
            for row in prepared:
                if not self._exists("topics", row[1]):
                    raise SQLiteAuthorityDataError("question mapping topic does not exist")
            self.connection.execute(
                "DELETE FROM question_topic_mappings WHERE question_id = ?", (question_id,)
            )
            for row in prepared:
                self.connection.execute(
                    "INSERT INTO question_topic_mappings "
                    "(id, question_id, topic_id, score, rank, method, state, reason, created_at, reviewed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row[0], question_id, *row[1:]),
                )
            return tuple(item[0] for item in prepared)

        return self._write(command)

    def upsert_attempt(self, record: Mapping[str, Any]) -> str:
        attempt_id = _required_text(record.get("id"), "attempt.id")
        question_id = _required_text(record.get("question_id"), "attempt.question_id")
        attempt_number = _integer(record.get("attempt_number"), "attempt.attempt_number", minimum=1)
        occurred_at = _required_text(record.get("occurred_at"), "attempt.occurred_at")

        def command():
            if not self._exists("questions", question_id):
                raise SQLiteAuthorityDataError("attempt question does not exist")
            self.connection.execute(
                "INSERT INTO question_attempts "
                "(id, question_id, attempt_number, outcome, earned_marks_milli, max_marks_milli, "
                "response_ref, feedback_ref, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "question_id=excluded.question_id, attempt_number=excluded.attempt_number, "
                "outcome=excluded.outcome, earned_marks_milli=excluded.earned_marks_milli, "
                "max_marks_milli=excluded.max_marks_milli, response_ref=excluded.response_ref, "
                "feedback_ref=excluded.feedback_ref, occurred_at=excluded.occurred_at",
                (
                    attempt_id,
                    question_id,
                    attempt_number,
                    _required_text(record.get("outcome"), "attempt.outcome"),
                    _optional_integer(record.get("earned_marks_milli"), "earned_marks_milli", minimum=0),
                    _optional_integer(record.get("max_marks_milli"), "max_marks_milli", minimum=0),
                    _optional_text(record.get("response_ref")),
                    _optional_text(record.get("feedback_ref")),
                    occurred_at,
                ),
            )
            return attempt_id

        return self._write(command)

    def upsert_mistake(self, record: Mapping[str, Any]) -> str:
        mistake_id = _required_text(record.get("id"), "mistake.id")
        attempt_id = _required_text(record.get("attempt_id"), "mistake.attempt_id")
        created_at = _required_text(record.get("created_at"), "mistake.created_at")

        def command():
            if not self._exists("question_attempts", attempt_id):
                raise SQLiteAuthorityDataError("mistake attempt does not exist")
            self.connection.execute(
                "INSERT INTO mistake_events "
                "(id, attempt_id, category, mistake_text, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET attempt_id=excluded.attempt_id, "
                "category=excluded.category, mistake_text=excluded.mistake_text, "
                "resolved_at=excluded.resolved_at",
                (
                    mistake_id,
                    attempt_id,
                    _required_text(record.get("category"), "mistake.category"),
                    str(record.get("mistake_text") or ""),
                    created_at,
                    _optional_text(record.get("resolved_at")),
                ),
            )
            return mistake_id

        return self._write(command)

    def soft_delete_question(self, question_id: str, *, deleted_at: str) -> None:
        question_id = _required_text(question_id, "question_id")
        deleted_at = _required_text(deleted_at, "deleted_at")

        def command():
            cursor = self.connection.execute(
                "UPDATE questions SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
                (deleted_at, deleted_at, question_id),
            )
            if cursor.rowcount != 1:
                raise SQLiteAuthorityDataError("live question row was not found")

        self._write(command)


class SQLiteLearningProgressCommandRepository(_SQLiteCommandBase):
    """Commands for memory entries, topic progress events and snapshots."""

    REQUIRED_TABLES = (
        "courses",
        "topics",
        "learning_memory_entries",
        "topic_progress_events",
        "progress_snapshots",
    )

    def upsert_memory_entry(self, record: Mapping[str, Any]) -> str:
        entry_id = _required_text(record.get("id"), "memory.id")
        created_at = _required_text(record.get("created_at"), "memory.created_at")
        updated_at = _required_text(record.get("updated_at"), "memory.updated_at")
        topic_id = _optional_text(record.get("topic_id"))

        def command():
            if topic_id is not None and not self._exists("topics", topic_id):
                raise SQLiteAuthorityDataError("memory topic does not exist")
            self.connection.execute(
                "INSERT INTO learning_memory_entries "
                "(id, scope_type, scope_id, kind, topic_id, raw_topic, memory_text, "
                "source_entity_type, source_entity_id, created_at, updated_at, archived_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "scope_type=excluded.scope_type, scope_id=excluded.scope_id, kind=excluded.kind, "
                "topic_id=excluded.topic_id, raw_topic=excluded.raw_topic, "
                "memory_text=excluded.memory_text, source_entity_type=excluded.source_entity_type, "
                "source_entity_id=excluded.source_entity_id, updated_at=excluded.updated_at, "
                "archived_at=excluded.archived_at",
                (
                    entry_id,
                    _required_text(record.get("scope_type"), "memory.scope_type"),
                    _optional_text(record.get("scope_id")),
                    _required_text(record.get("kind"), "memory.kind"),
                    topic_id,
                    str(record.get("raw_topic") or ""),
                    str(record.get("memory_text") or ""),
                    _optional_text(record.get("source_entity_type")),
                    _optional_text(record.get("source_entity_id")),
                    created_at,
                    updated_at,
                    _optional_text(record.get("archived_at")),
                ),
            )
            return entry_id

        return self._write(command)

    def upsert_topic_progress_event(self, record: Mapping[str, Any]) -> str:
        event_id = _required_text(record.get("id"), "topic_progress_event.id")
        topic_id = _required_text(record.get("topic_id"), "topic_progress_event.topic_id")
        occurred_at = _required_text(record.get("occurred_at"), "topic_progress_event.occurred_at")

        def command():
            if not self._exists("topics", topic_id):
                raise SQLiteAuthorityDataError("topic progress target does not exist")
            self.connection.execute(
                "INSERT INTO topic_progress_events "
                "(id, topic_id, event_type, previous_status, new_status, confidence, "
                "evidence_type, evidence_id, occurred_at, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET topic_id=excluded.topic_id, "
                "event_type=excluded.event_type, previous_status=excluded.previous_status, "
                "new_status=excluded.new_status, confidence=excluded.confidence, "
                "evidence_type=excluded.evidence_type, evidence_id=excluded.evidence_id, "
                "occurred_at=excluded.occurred_at, note=excluded.note",
                (
                    event_id,
                    topic_id,
                    _required_text(record.get("event_type"), "topic_progress_event.event_type"),
                    _optional_text(record.get("previous_status")),
                    _optional_text(record.get("new_status")),
                    _optional_integer(record.get("confidence"), "confidence", minimum=0, maximum=5),
                    _optional_text(record.get("evidence_type")),
                    _optional_text(record.get("evidence_id")),
                    occurred_at,
                    str(record.get("note") or ""),
                ),
            )
            return event_id

        return self._write(command)

    def upsert_progress_snapshot(self, record: Mapping[str, Any]) -> str:
        snapshot_id = _required_text(record.get("id"), "progress_snapshot.id")
        course_id = _required_text(record.get("course_id"), "progress_snapshot.course_id")

        def command():
            if not self._exists("courses", course_id):
                raise SQLiteAuthorityDataError("progress snapshot course does not exist")
            self.connection.execute(
                "INSERT INTO progress_snapshots "
                "(id, course_id, snapshot_date, counts_json, score_json, engine_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET course_id=excluded.course_id, "
                "snapshot_date=excluded.snapshot_date, counts_json=excluded.counts_json, "
                "score_json=excluded.score_json, engine_version=excluded.engine_version, "
                "created_at=excluded.created_at",
                (
                    snapshot_id,
                    course_id,
                    _required_text(record.get("snapshot_date"), "progress_snapshot.snapshot_date"),
                    _json_object_text(record.get("counts", {}), "counts"),
                    _json_object_text(record.get("score", {}), "score"),
                    _required_text(record.get("engine_version"), "progress_snapshot.engine_version"),
                    _required_text(record.get("created_at"), "progress_snapshot.created_at"),
                ),
            )
            return snapshot_id

        return self._write(command)


class SQLiteStudyPlanCommandRepository(_SQLiteCommandBase):
    """Transactional plan header and ordered-item commands."""

    REQUIRED_TABLES = (
        "courses",
        "topics",
        "assessments",
        "study_plans",
        "study_plan_items",
    )

    def upsert_plan(self, record: Mapping[str, Any]) -> str:
        plan_id = _required_text(record.get("id"), "study_plan.id")

        def command():
            self.connection.execute(
                "INSERT INTO study_plans "
                "(id, kind, horizon, starts_on, ends_on, requested_minutes, allocated_minutes, "
                "status, engine_name, engine_version, rationale, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, horizon=excluded.horizon, "
                "starts_on=excluded.starts_on, ends_on=excluded.ends_on, "
                "requested_minutes=excluded.requested_minutes, allocated_minutes=excluded.allocated_minutes, "
                "status=excluded.status, engine_name=excluded.engine_name, "
                "engine_version=excluded.engine_version, rationale=excluded.rationale, "
                "updated_at=excluded.updated_at",
                (
                    plan_id,
                    _required_text(record.get("kind"), "study_plan.kind"),
                    _required_text(record.get("horizon"), "study_plan.horizon"),
                    _required_text(record.get("starts_on"), "study_plan.starts_on"),
                    _required_text(record.get("ends_on"), "study_plan.ends_on"),
                    _integer(record.get("requested_minutes"), "requested_minutes", minimum=0),
                    _integer(record.get("allocated_minutes"), "allocated_minutes", minimum=0),
                    str(record.get("status") or "proposed"),
                    _required_text(record.get("engine_name"), "study_plan.engine_name"),
                    _required_text(record.get("engine_version"), "study_plan.engine_version"),
                    str(record.get("rationale") or ""),
                    _required_text(record.get("created_at"), "study_plan.created_at"),
                    _required_text(record.get("updated_at"), "study_plan.updated_at"),
                ),
            )
            return plan_id

        return self._write(command)

    def replace_plan_items(
        self,
        plan_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> Tuple[str, ...]:
        plan_id = _required_text(plan_id, "plan_id")
        prepared = []
        for raw in rows:
            prepared.append(
                (
                    _required_text(raw.get("id"), "study_plan_item.id"),
                    _required_text(raw.get("plan_date"), "study_plan_item.plan_date"),
                    _integer(raw.get("ordinal"), "study_plan_item.ordinal", minimum=1),
                    _optional_text(raw.get("course_id")),
                    _optional_text(raw.get("topic_id")),
                    _optional_text(raw.get("assessment_id")),
                    _optional_text(raw.get("resource_id")),
                    _optional_text(raw.get("note_id")),
                    _integer(raw.get("minutes"), "study_plan_item.minutes", minimum=0),
                    _required_text(raw.get("action"), "study_plan_item.action"),
                    str(raw.get("reason") or ""),
                    _optional_float(raw.get("score"), "study_plan_item.score"),
                    str(raw.get("status") or "planned"),
                )
            )

        def command():
            if not self._exists("study_plans", plan_id):
                raise SQLiteAuthorityDataError("study plan does not exist")
            self.connection.execute("DELETE FROM study_plan_items WHERE plan_id = ?", (plan_id,))
            for row in prepared:
                self.connection.execute(
                    "INSERT INTO study_plan_items "
                    "(id, plan_id, plan_date, ordinal, course_id, topic_id, assessment_id, "
                    "resource_id, note_id, minutes, action, reason, score, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row[0], plan_id, *row[1:]),
                )
            return tuple(item[0] for item in prepared)

        return self._write(command)


class SQLiteGradeCalendarCommandRepository(_SQLiteCommandBase):
    """Commands for grade configuration/results, credits and academic events."""

    REQUIRED_TABLES = (
        "semesters",
        "courses",
        "semester_courses",
        "grade_scales",
        "grade_bands",
        "semester_grade_settings",
        "manual_grade_entries",
        "semester_results",
        "academic_events",
    )

    def upsert_grade_scale(self, record: Mapping[str, Any]) -> str:
        scale_id = _required_text(record.get("id"), "grade_scale.id")

        def command():
            self.connection.execute(
                "INSERT INTO grade_scales "
                "(id, name, source, verified, active_from, active_to, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, source=excluded.source, "
                "verified=excluded.verified, active_from=excluded.active_from, "
                "active_to=excluded.active_to, updated_at=excluded.updated_at",
                (
                    scale_id,
                    _required_text(record.get("name"), "grade_scale.name"),
                    str(record.get("source") or ""),
                    _bool_int(record.get("verified", False)),
                    _optional_text(record.get("active_from")),
                    _optional_text(record.get("active_to")),
                    _required_text(record.get("created_at"), "grade_scale.created_at"),
                    _required_text(record.get("updated_at"), "grade_scale.updated_at"),
                ),
            )
            return scale_id

        return self._write(command)

    def replace_grade_bands(
        self,
        scale_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> Tuple[str, ...]:
        scale_id = _required_text(scale_id, "scale_id")
        prepared = []
        for raw in rows:
            prepared.append(
                (
                    _required_text(raw.get("id"), "grade_band.id"),
                    _integer(raw.get("minimum_bps"), "grade_band.minimum_bps", minimum=0),
                    _required_text(raw.get("letter_grade"), "grade_band.letter_grade"),
                    _integer(raw.get("grade_point_milli"), "grade_band.grade_point_milli", minimum=0),
                )
            )
            if prepared[-1][1] > 10000:
                raise SQLiteAuthorityDataError("grade_band.minimum_bps must be <= 10000")

        def command():
            if not self._exists("grade_scales", scale_id):
                raise SQLiteAuthorityDataError("grade scale does not exist")
            self.connection.execute("DELETE FROM grade_bands WHERE scale_id = ?", (scale_id,))
            for band_id, minimum_bps, letter, points in prepared:
                self.connection.execute(
                    "INSERT INTO grade_bands "
                    "(id, scale_id, minimum_bps, letter_grade, grade_point_milli) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (band_id, scale_id, minimum_bps, letter, points),
                )
            return tuple(item[0] for item in prepared)

        return self._write(command)

    def set_semester_course_credits(
        self,
        semester_id: str,
        course_id: str,
        credits_milli: Optional[int],
    ) -> None:
        semester_id = _required_text(semester_id, "semester_id")
        course_id = _required_text(course_id, "course_id")
        credits = _optional_integer(credits_milli, "credits_milli", minimum=0)

        def command():
            cursor = self.connection.execute(
                "UPDATE semester_courses SET credits_milli=? "
                "WHERE semester_id=? AND course_id=?",
                (credits, semester_id, course_id),
            )
            if cursor.rowcount != 1:
                raise SQLiteAuthorityDataError("semester course relationship does not exist")

        self._write(command)

    def upsert_semester_grade_settings(self, record: Mapping[str, Any]) -> str:
        semester_id = _required_text(record.get("semester_id"), "semester_grade_settings.semester_id")
        scale_id = _required_text(record.get("scale_id"), "semester_grade_settings.scale_id")

        def command():
            if not self._exists("semesters", semester_id):
                raise SQLiteAuthorityDataError("semester does not exist")
            if not self._exists("grade_scales", scale_id):
                raise SQLiteAuthorityDataError("grade scale does not exist")
            self.connection.execute(
                "INSERT INTO semester_grade_settings "
                "(semester_id, scale_id, target_sgpa_milli, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(semester_id) DO UPDATE SET scale_id=excluded.scale_id, "
                "target_sgpa_milli=excluded.target_sgpa_milli, updated_at=excluded.updated_at",
                (
                    semester_id,
                    scale_id,
                    _optional_integer(record.get("target_sgpa_milli"), "target_sgpa_milli", minimum=0),
                    _required_text(record.get("updated_at"), "semester_grade_settings.updated_at"),
                ),
            )
            return semester_id

        return self._write(command)

    def upsert_manual_grade_entry(self, record: Mapping[str, Any]) -> str:
        entry_id = _required_text(record.get("id"), "manual_grade.id")

        def command():
            self.connection.execute(
                "INSERT INTO manual_grade_entries "
                "(id, semester_id, course_id, score_bps, letter_grade, grade_point_milli, "
                "entry_kind, note, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET score_bps=excluded.score_bps, "
                "letter_grade=excluded.letter_grade, grade_point_milli=excluded.grade_point_milli, "
                "entry_kind=excluded.entry_kind, note=excluded.note, recorded_at=excluded.recorded_at",
                (
                    entry_id,
                    _required_text(record.get("semester_id"), "manual_grade.semester_id"),
                    _required_text(record.get("course_id"), "manual_grade.course_id"),
                    _optional_integer(record.get("score_bps"), "manual_grade.score_bps", minimum=0, maximum=10000),
                    _optional_text(record.get("letter_grade")),
                    _optional_integer(record.get("grade_point_milli"), "manual_grade.grade_point_milli", minimum=0),
                    _required_text(record.get("entry_kind"), "manual_grade.entry_kind"),
                    str(record.get("note") or ""),
                    _required_text(record.get("recorded_at"), "manual_grade.recorded_at"),
                ),
            )
            return entry_id

        return self._write(command)

    def upsert_semester_result(self, record: Mapping[str, Any]) -> str:
        result_id = _required_text(record.get("id"), "semester_result.id")

        def command():
            self.connection.execute(
                "INSERT INTO semester_results "
                "(id, semester_id, earned_credits_milli, earned_grade_points_milli, sgpa_milli, "
                "verified, source, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET semester_id=excluded.semester_id, "
                "earned_credits_milli=excluded.earned_credits_milli, "
                "earned_grade_points_milli=excluded.earned_grade_points_milli, "
                "sgpa_milli=excluded.sgpa_milli, verified=excluded.verified, "
                "source=excluded.source, recorded_at=excluded.recorded_at",
                (
                    result_id,
                    _required_text(record.get("semester_id"), "semester_result.semester_id"),
                    _integer(record.get("earned_credits_milli"), "earned_credits_milli", minimum=0),
                    _integer(record.get("earned_grade_points_milli"), "earned_grade_points_milli", minimum=0),
                    _integer(record.get("sgpa_milli"), "sgpa_milli", minimum=0),
                    _bool_int(record.get("verified", False)),
                    str(record.get("source") or ""),
                    _required_text(record.get("recorded_at"), "semester_result.recorded_at"),
                ),
            )
            return result_id

        return self._write(command)

    def upsert_academic_event(self, record: Mapping[str, Any]) -> str:
        event_id = _required_text(record.get("id"), "academic_event.id")

        def command():
            self.connection.execute(
                "INSERT INTO academic_events "
                "(id, semester_id, course_id, event_kind, title, starts_at, ends_at, all_day, "
                "recurrence_rule, reference_type, reference_id, status, source_entity_type, "
                "source_entity_id, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET semester_id=excluded.semester_id, "
                "course_id=excluded.course_id, event_kind=excluded.event_kind, title=excluded.title, "
                "starts_at=excluded.starts_at, ends_at=excluded.ends_at, all_day=excluded.all_day, "
                "recurrence_rule=excluded.recurrence_rule, reference_type=excluded.reference_type, "
                "reference_id=excluded.reference_id, status=excluded.status, "
                "source_entity_type=excluded.source_entity_type, source_entity_id=excluded.source_entity_id, "
                "updated_at=excluded.updated_at, deleted_at=excluded.deleted_at",
                (
                    event_id,
                    _optional_text(record.get("semester_id")),
                    _optional_text(record.get("course_id")),
                    _required_text(record.get("event_kind"), "academic_event.event_kind"),
                    _required_text(record.get("title"), "academic_event.title"),
                    _required_text(record.get("starts_at"), "academic_event.starts_at"),
                    _optional_text(record.get("ends_at")),
                    _bool_int(record.get("all_day", False)),
                    _optional_text(record.get("recurrence_rule")),
                    _optional_text(record.get("reference_type")),
                    _optional_text(record.get("reference_id")),
                    str(record.get("status") or "scheduled"),
                    _optional_text(record.get("source_entity_type")),
                    _optional_text(record.get("source_entity_id")),
                    _required_text(record.get("created_at"), "academic_event.created_at"),
                    _required_text(record.get("updated_at"), "academic_event.updated_at"),
                    _optional_text(record.get("deleted_at")),
                ),
            )
            return event_id

        return self._write(command)


__all__ = (
    "SQLiteAssessmentCommandRepository",
    "SQLiteAuthorityCommandError",
    "SQLiteAuthorityDataError",
    "SQLiteAuthorityNotActiveError",
    "SQLiteAuthoritySchemaError",
    "SQLiteCourseCommandRepository",
    "SQLiteGradeCalendarCommandRepository",
    "SQLiteLearningProgressCommandRepository",
    "SQLiteQuestionCommandRepository",
    "SQLiteStudyPlanCommandRepository",
)
