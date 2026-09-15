"""SQLite-backed legacy-shape compatibility projections for Phase 4.11.

The normalized Phase-3/4 tables remain the structured data model.  These
projections preserve the exact V8-V13 JSON-shaped public API *inside the same
SQLite database* so old compatibility facades can survive the authority switch
without continuing to write JSON files.

Runtime writes are transactional: normalized relational rows and the matching
compatibility projection are committed together.  The migration ledger is read
as historical evidence only and is never rewritten by runtime commands.
"""

from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
)
from personal_learning_assistant.migration.legacy_json_import import stable_target_id


PathLike = Union[str, Path]
PROJECTION_PREFIX = "phase4.compatibility_projection."
PROJECTION_VERSION = 1

STORE_COURSES = "courses"
STORE_ASSESSMENTS = "assessments"
STORE_ASSESSMENT_WORKSPACE = "assessment_workspace"
STORE_LEARNING_MEMORY = "learning_memory"
STORE_PROGRESS_HISTORY = "course_progress_history"
STORE_WEEKLY_PLANS = "weekly_study_plans"
STORE_MULTI_COURSE_PLANS = "multi_course_weekly_plans"
STORE_INTELLIGENT_PLANS = "intelligent_study_plans"
STORE_GRADE_CONFIG = "semester_grade_config"

STORE_NAMES = {
    STORE_COURSES,
    STORE_ASSESSMENTS,
    STORE_ASSESSMENT_WORKSPACE,
    STORE_LEARNING_MEMORY,
    STORE_PROGRESS_HISTORY,
    STORE_WEEKLY_PLANS,
    STORE_MULTI_COURSE_PLANS,
    STORE_INTELLIGENT_PLANS,
    STORE_GRADE_CONFIG,
}

REQUIRED_TABLES = {
    "app_settings",
    "migration_imports",
    "semesters",
    "courses",
    "semester_courses",
    "topics",
    "assessments",
    "assessment_topics",
    "questions",
    "question_sources",
    "question_topic_mappings",
    "question_attempts",
    "mistake_events",
    "topic_progress_events",
    "progress_snapshots",
    "learning_memory_entries",
    "study_plans",
    "study_plan_items",
    "grade_scales",
    "grade_bands",
    "semester_grade_settings",
    "manual_grade_entries",
    "semester_results",
    "academic_events",
}


class SQLiteCompatibilityError(RuntimeError):
    """Base Phase 4.11 compatibility-projection error."""


class SQLiteCompatibilitySchemaError(SQLiteCompatibilityError):
    pass


class SQLiteCompatibilityProjectionMissingError(SQLiteCompatibilityError):
    pass


class SQLiteCompatibilityAuthorityError(SQLiteCompatibilityError):
    pass


class SQLiteCompatibilityDataError(SQLiteCompatibilityError, ValueError):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _clean(value).casefold()).strip("_")


def _milli(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return int((number * Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _bps(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0 or number > 100:
        return None
    return int((number * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _projection_key(store_name: str) -> str:
    if store_name not in STORE_NAMES:
        raise SQLiteCompatibilityDataError("unknown structured store: {}".format(store_name))
    return PROJECTION_PREFIX + store_name


def _course_legacy_key(course: Mapping[str, Any], position: int) -> str:
    raw_id = _clean(course.get("id"))
    code = _clean(course.get("code")).upper()
    if raw_id:
        return "course:id:{}".format(raw_id)
    if code:
        return "course:code:{}".format(code.casefold())
    return "course:index:{}".format(position)


def _topic_legacy_key(course_key: str, topic: Mapping[str, Any], position: int) -> str:
    raw_id = _clean(topic.get("id"))
    name = _clean(topic.get("name"))
    if raw_id:
        suffix = "id:{}".format(raw_id)
    elif name:
        suffix = "name:{}".format(name.casefold())
    else:
        suffix = "index:{}".format(position)
    return "{}/topic:{}".format(course_key, suffix)


def _course_target(course: Mapping[str, Any], position: int) -> str:
    return stable_target_id("data/courses.json", "course", _course_legacy_key(course, position))


def _course_target_from_public(connection: sqlite3.Connection, public_id: Any) -> Optional[str]:
    text = _clean(public_id)
    if not text:
        return None
    lookup = {
        "course:id:{}".format(text).casefold(),
        "course:code:{}".format(text.casefold()).casefold(),
    }
    rows = connection.execute(
        "SELECT legacy_key, target_id FROM migration_imports "
        "WHERE source_path='data/courses.json' AND source_type='legacy_json' "
        "AND target_table='courses'"
    ).fetchall()
    candidates = {str(row[1]) for row in rows if str(row[0]).casefold() in lookup}
    if len(candidates) == 1:
        return next(iter(candidates))
    direct = connection.execute(
        "SELECT id FROM courses WHERE deleted_at IS NULL AND (id=? OR code=? COLLATE NOCASE)",
        (text, text),
    ).fetchall()
    direct_ids = {str(row[0]) for row in direct}
    if len(direct_ids) == 1:
        return next(iter(direct_ids))
    return stable_target_id("data/courses.json", "course", "course:id:{}".format(text))


def _topic_target_from_name(
    connection: sqlite3.Connection,
    course_target: Optional[str],
    topic_name: Any,
) -> Optional[str]:
    if course_target is None:
        return None
    name = _clean(topic_name)
    if not name:
        return None
    rows = connection.execute(
        "SELECT id FROM topics WHERE course_id=? AND normalized_name=? AND deleted_at IS NULL",
        (course_target, name.casefold()),
    ).fetchall()
    ids = {str(row[0]) for row in rows}
    return next(iter(ids)) if len(ids) == 1 else None


def _assessment_key(public_id: Any) -> str:
    return "assessment:id:{}".format(_clean(public_id))


def _assessment_target(public_id: Any) -> str:
    return stable_target_id("data/assessments.json", "assessment", _assessment_key(public_id))


def _question_key(assessment_public_id: Any, question_public_id: Any) -> str:
    return "{}/question:id:{}".format(
        _assessment_key(assessment_public_id), _clean(question_public_id)
    )


def _question_target(assessment_public_id: Any, question_public_id: Any) -> str:
    return stable_target_id(
        "data/assessment_workspace.json",
        "question",
        _question_key(assessment_public_id, question_public_id),
    )


def _safe_date(value: Any, fallback: str) -> str:
    text = str(value or "").strip()[:10]
    try:
        datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return fallback
    return text


class SQLiteCompatibilityProjectionRepository:
    """Exact legacy-shape read model with transactional relational write-through."""

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
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            raise SQLiteCompatibilitySchemaError(
                "Phase 4.11 required tables are missing: {}".format(", ".join(missing))
            )

    def _require_sqlite_authority(self) -> None:
        state = read_authority_control(self.authority_control_path)
        if state.storage_backend != BACKEND_SQLITE or not state.legacy_writes_blocked:
            raise SQLiteCompatibilityAuthorityError(
                "Phase 4.11 runtime compatibility access requires storage_backend=sqlite "
                "and legacy_writes_blocked=true."
            )

    def _read_projection_unchecked(self, store_name: str) -> Optional[Any]:
        row = self.connection.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (_projection_key(store_name),),
        ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise SQLiteCompatibilityDataError(
                "stored compatibility projection is invalid JSON: {}".format(store_name)
            ) from error
        if not isinstance(value, dict):
            raise SQLiteCompatibilityDataError(
                "stored compatibility projection must be a JSON object: {}".format(store_name)
            )
        return value

    def load_projection(self, store_name: str) -> Dict[str, Any]:
        self._require_sqlite_authority()
        before = self.connection.total_changes
        value = self._read_projection_unchecked(store_name)
        if value is None:
            raise SQLiteCompatibilityProjectionMissingError(
                "SQLite authority is active but compatibility projection {!r} is missing; "
                "the final cutover must seed every Phase 4 store before promotion."
                .format(store_name)
            )
        if self.connection.total_changes != before:
            raise SQLiteCompatibilityError("compatibility read unexpectedly mutated SQLite")
        return deepcopy(value)

    def seed_projection(
        self,
        store_name: str,
        payload: Mapping[str, Any],
        *,
        updated_at: str,
        replace: bool = False,
    ) -> None:
        """Seed exact compatibility state before promotion.

        This is a migration/cutover operation, not a runtime writer.  It does not
        alter normalized tables because the final delta import/reconciliation is
        responsible for those rows before this seed runs.
        """
        if not isinstance(payload, Mapping):
            raise SQLiteCompatibilityDataError("projection payload must be a mapping")
        state = read_authority_control(self.authority_control_path)
        if state.storage_backend == BACKEND_SQLITE:
            raise SQLiteCompatibilityAuthorityError(
                "pre-promotion projection seeding is disabled after SQLite authority is active"
            )
        key = _projection_key(store_name)
        existing = self.connection.execute(
            "SELECT 1 FROM app_settings WHERE key=?", (key,)
        ).fetchone()
        if existing is not None and not replace:
            raise SQLiteCompatibilityDataError(
                "compatibility projection already exists: {}".format(store_name)
            )
        if self.connection.in_transaction:
            raise SQLiteCompatibilityError("projection seed refuses nested transactions")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at",
                (key, _json(dict(payload)), str(updated_at)),
            )
        except Exception:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def save_projection(self, store_name: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        self._require_sqlite_authority()
        if not isinstance(payload, Mapping):
            raise SQLiteCompatibilityDataError("projection payload must be a mapping")
        if self.connection.in_transaction:
            raise SQLiteCompatibilityError("compatibility save refuses nested transactions")

        old = self._read_projection_unchecked(store_name) or {}
        new = deepcopy(dict(payload))
        timestamp = _now()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._sync_store(store_name, old, new, timestamp)
            self.connection.execute(
                "INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at",
                (_projection_key(store_name), _json(new), timestamp),
            )
        except Exception:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
        return deepcopy(new)

    def _sync_store(self, store_name: str, old: Mapping[str, Any], new: Mapping[str, Any], now: str) -> None:
        if store_name == STORE_COURSES:
            self._sync_courses(old, new, now)
        elif store_name == STORE_ASSESSMENTS:
            self._sync_assessments(old, new, now)
        elif store_name == STORE_ASSESSMENT_WORKSPACE:
            self._sync_workspace(old, new, now)
        elif store_name == STORE_LEARNING_MEMORY:
            self._sync_learning_memory(new, now)
        elif store_name == STORE_PROGRESS_HISTORY:
            self._sync_progress_history(new, now)
        elif store_name in {STORE_WEEKLY_PLANS, STORE_MULTI_COURSE_PLANS, STORE_INTELLIGENT_PLANS}:
            self._sync_plan_store(store_name, new, now)
        elif store_name == STORE_GRADE_CONFIG:
            self._sync_grade_config(new, now)
        else:
            raise SQLiteCompatibilityDataError("unknown structured store: {}".format(store_name))

    # ------------------------------------------------------------------ courses
    def _sync_courses(self, old: Mapping[str, Any], new: Mapping[str, Any], now: str) -> None:
        raw_courses = new.get("courses", [])
        if not isinstance(raw_courses, list):
            raise SQLiteCompatibilityDataError("courses field must be a list")
        live_course_ids = set()
        live_topic_ids = set()
        public_to_target: Dict[str, str] = {}

        for position, raw in enumerate(raw_courses):
            if not isinstance(raw, Mapping):
                raise SQLiteCompatibilityDataError("course rows must be objects")
            code = _clean(raw.get("code")).upper()
            name = _clean(raw.get("name"))
            if not code or not name:
                raise SQLiteCompatibilityDataError("course code/name must not be empty")
            course_key = _course_legacy_key(raw, position)
            course_id = stable_target_id("data/courses.json", "course", course_key)
            public_id = _clean(raw.get("id")) or code.casefold()
            public_to_target[public_id] = course_id
            live_course_ids.add(course_id)

            semester_label = _clean(raw.get("semester"))
            semester_key = "semester:{}".format(semester_label or "<unspecified>")
            semester_id = stable_target_id(
                "data/courses.json", "semester_placeholder", semester_key
            )
            created_at = str(raw.get("created_at") or now)
            updated_at = str(raw.get("updated_at") or now)
            self.connection.execute(
                "INSERT INTO semesters (id,name,academic_year,starts_on,ends_on,status,created_at,updated_at) "
                "VALUES (?,?,?,NULL,NULL,'planned',?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,updated_at=excluded.updated_at",
                (
                    semester_id,
                    "Legacy Semester {}".format(semester_label) if semester_label else "Legacy Semester (unspecified)",
                    "legacy-unknown",
                    created_at,
                    updated_at,
                ),
            )
            status = _token(raw.get("status")) or "active"
            if status not in {"active", "planned", "completed", "archived"}:
                status = "active"
            self.connection.execute(
                "INSERT INTO courses (id,code,name,status,description,created_at,updated_at,deleted_at) "
                "VALUES (?,?,?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET "
                "code=excluded.code,name=excluded.name,status=excluded.status,updated_at=excluded.updated_at,deleted_at=NULL",
                (course_id, code, name, status, "", created_at, updated_at),
            )
            enrollment = {"planned": "planned", "completed": "completed", "archived": "archived"}.get(status, "enrolled")
            self.connection.execute(
                "INSERT INTO semester_courses (semester_id,course_id,credits_milli,instructor,enrollment_status) "
                "VALUES (?,?,NULL,'',?) ON CONFLICT(semester_id,course_id) DO UPDATE SET "
                "enrollment_status=excluded.enrollment_status",
                (semester_id, course_id, enrollment),
            )

            raw_topics = raw.get("topics", [])
            if not isinstance(raw_topics, list):
                raise SQLiteCompatibilityDataError("course topics must be a list")
            for topic_position, topic_value in enumerate(raw_topics):
                topic = {"name": topic_value} if isinstance(topic_value, str) else topic_value
                if not isinstance(topic, Mapping):
                    raise SQLiteCompatibilityDataError("topic rows must be object/string")
                name_value = _clean(topic.get("name"))
                if not name_value:
                    continue
                topic_key = _topic_legacy_key(course_key, topic, topic_position)
                topic_id = stable_target_id("data/courses.json", "topic", topic_key)
                live_topic_ids.add(topic_id)
                topic_status = _token(topic.get("status")) or "not_started"
                aliases = {"in_progress": "learning", "incomplete": "not_started", "done": "mastered"}
                topic_status = aliases.get(topic_status, topic_status)
                if topic_status not in {"not_started", "learning", "weak", "review", "practiced", "mastered"}:
                    topic_status = "not_started"
                try:
                    confidence = int(topic.get("confidence", 0) or 0)
                except (TypeError, ValueError):
                    confidence = 0
                confidence = max(0, min(5, confidence))
                self.connection.execute(
                    "INSERT INTO topics (id,course_id,name,normalized_name,position,status,confidence,raw_import_status,created_at,updated_at,deleted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET "
                    "course_id=excluded.course_id,name=excluded.name,normalized_name=excluded.normalized_name,"
                    "position=excluded.position,status=excluded.status,confidence=excluded.confidence,"
                    "updated_at=excluded.updated_at,deleted_at=NULL",
                    (
                        topic_id,
                        course_id,
                        name_value,
                        name_value.casefold(),
                        topic_position,
                        topic_status,
                        confidence,
                        _clean(topic.get("status")) or None,
                        created_at,
                        str(topic.get("last_updated") or updated_at),
                    ),
                )

        # Soft-delete only entities that were part of the previous compatibility projection.
        old_courses = old.get("courses", []) if isinstance(old.get("courses", []), list) else []
        for position, raw in enumerate(old_courses):
            if not isinstance(raw, Mapping):
                continue
            old_course_key = _course_legacy_key(raw, position)
            old_course_id = stable_target_id("data/courses.json", "course", old_course_key)
            if old_course_id not in live_course_ids:
                self.connection.execute(
                    "UPDATE courses SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                    (now, now, old_course_id),
                )
            raw_topics = raw.get("topics", []) if isinstance(raw.get("topics", []), list) else []
            for topic_position, topic_value in enumerate(raw_topics):
                topic = {"name": topic_value} if isinstance(topic_value, str) else topic_value
                if not isinstance(topic, Mapping):
                    continue
                tid = stable_target_id(
                    "data/courses.json",
                    "topic",
                    _topic_legacy_key(old_course_key, topic, topic_position),
                )
                if tid not in live_topic_ids:
                    self.connection.execute(
                        "UPDATE topics SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                        (now, now, tid),
                    )

        active_public = _clean(new.get("active_course_id"))
        active_target = public_to_target.get(active_public) or _course_target_from_public(self.connection, active_public)
        if active_target:
            self.connection.execute(
                "INSERT INTO app_settings (key,value_json,updated_at) VALUES ('active_course_id',?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (json.dumps(active_target), now),
            )

    # ------------------------------------------------------------- assessments
    def _sync_assessments(self, old: Mapping[str, Any], new: Mapping[str, Any], now: str) -> None:
        rows = new.get("assessments", [])
        if not isinstance(rows, list):
            raise SQLiteCompatibilityDataError("assessments field must be a list")
        live = set()
        for item in rows:
            if not isinstance(item, Mapping):
                raise SQLiteCompatibilityDataError("assessment rows must be objects")
            public_id = _clean(item.get("id"))
            course_target = _course_target_from_public(self.connection, item.get("course_id"))
            if not public_id or not course_target:
                raise SQLiteCompatibilityDataError("assessment id/course_id must resolve")
            aid = _assessment_target(public_id)
            live.add(aid)
            kind = _token(item.get("type") or item.get("assessment_type")) or "assessment"
            status = _token(item.get("status")) or "pending"
            status = {"done": "completed", "complete": "completed", "open": "pending"}.get(status, status)
            if status not in {"pending", "in_progress", "completed"}:
                status = "pending"
            created_at = str(item.get("created_at") or now)
            updated_at = str(item.get("updated_at") or now)
            due_on = _clean(item.get("due_date") or item.get("due_on")) or None
            due_time = _clean(item.get("due_time")) or None
            self.connection.execute(
                "INSERT INTO assessments (id,course_id,assessment_type,title,due_on,due_time,status,weight_bps,max_points_milli,earned_points_milli,description,created_at,updated_at,deleted_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET "
                "course_id=excluded.course_id,assessment_type=excluded.assessment_type,title=excluded.title,"
                "due_on=excluded.due_on,due_time=excluded.due_time,status=excluded.status,weight_bps=excluded.weight_bps,"
                "max_points_milli=excluded.max_points_milli,earned_points_milli=excluded.earned_points_milli,"
                "description=excluded.description,updated_at=excluded.updated_at,deleted_at=NULL",
                (
                    aid,
                    course_target,
                    kind,
                    _clean(item.get("title")) or "Untitled assessment",
                    due_on,
                    due_time,
                    status,
                    _bps(item.get("weightage_percent") if item.get("weightage_percent") is not None else item.get("weight_percent")),
                    _milli(item.get("total_marks") if item.get("total_marks") is not None else item.get("max_points")),
                    _milli(item.get("obtained_marks") if item.get("obtained_marks") is not None else item.get("earned_points")),
                    str(item.get("description") or ""),
                    created_at,
                    updated_at,
                ),
            )
            self.connection.execute("DELETE FROM assessment_topics WHERE assessment_id=?", (aid,))
            topics = item.get("topics", [])
            if isinstance(topics, list):
                for position, raw_label in enumerate(topics):
                    label = _clean(raw_label)
                    if not label:
                        continue
                    key = "{}/topic:label:{}".format(_assessment_key(public_id), label.casefold())
                    row_id = stable_target_id("data/assessments.json", "assessment_topic", key)
                    topic_id = _topic_target_from_name(self.connection, course_target, label)
                    self.connection.execute(
                        "INSERT INTO assessment_topics (id,assessment_id,topic_id,raw_label,source,confidence,created_at) VALUES (?,?,?,?,?,?,?)",
                        (row_id, aid, topic_id, label, "phase4_compatibility", None, created_at),
                    )
            event_id = stable_target_id(
                "data/assessments.json", "academic_event", _assessment_key(public_id) + "/deadline"
            )
            if due_on:
                starts_at = due_on if not due_time else "{}T{}".format(due_on, due_time)
                self.connection.execute(
                    "INSERT INTO academic_events (id,semester_id,course_id,event_kind,title,starts_at,ends_at,all_day,recurrence_rule,reference_type,reference_id,status,source_entity_type,source_entity_id,created_at,updated_at,deleted_at) "
                    "VALUES (?,NULL,?,'assessment_deadline',?,?,NULL,?,NULL,'assessment',?,?,'assessment',?,?,?,NULL) "
                    "ON CONFLICT(id) DO UPDATE SET course_id=excluded.course_id,title=excluded.title,starts_at=excluded.starts_at,"
                    "all_day=excluded.all_day,status=excluded.status,updated_at=excluded.updated_at,deleted_at=NULL",
                    (
                        event_id,
                        course_target,
                        _clean(item.get("title")) or "Assessment deadline",
                        starts_at,
                        0 if due_time else 1,
                        aid,
                        "completed" if status == "completed" else "scheduled",
                        aid,
                        created_at,
                        updated_at,
                    ),
                )
            else:
                self.connection.execute(
                    "UPDATE academic_events SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                    (now, now, event_id),
                )

        old_rows = old.get("assessments", []) if isinstance(old.get("assessments", []), list) else []
        for item in old_rows:
            if not isinstance(item, Mapping):
                continue
            oid = _assessment_target(item.get("id"))
            if oid not in live:
                self.connection.execute(
                    "UPDATE assessments SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                    (now, now, oid),
                )

    # --------------------------------------------------------------- workspace
    def _sync_workspace(self, old: Mapping[str, Any], new: Mapping[str, Any], now: str) -> None:
        workspaces = new.get("workspaces", {})
        if not isinstance(workspaces, Mapping):
            raise SQLiteCompatibilityDataError("workspace field must be an object")
        live_questions = set()
        for workspace_key, workspace in workspaces.items():
            if not isinstance(workspace, Mapping):
                raise SQLiteCompatibilityDataError("workspace rows must be objects")
            assessment_public = _clean(workspace.get("assessment_id") or workspace_key)
            aid = _assessment_target(assessment_public)
            if self.connection.execute("SELECT 1 FROM assessments WHERE id=? AND deleted_at IS NULL", (aid,)).fetchone() is None:
                raise SQLiteCompatibilityDataError(
                    "workspace assessment is missing from authoritative SQLite: {}".format(assessment_public)
                )
            course_row = self.connection.execute("SELECT course_id FROM assessments WHERE id=?", (aid,)).fetchone()
            course_target = str(course_row[0]) if course_row else None
            questions = workspace.get("questions", [])
            if not isinstance(questions, list):
                raise SQLiteCompatibilityDataError("workspace questions must be a list")
            workspace_created = str(workspace.get("created_at") or now)
            for position, question in enumerate(questions):
                if not isinstance(question, Mapping):
                    raise SQLiteCompatibilityDataError("question rows must be objects")
                public_qid = _clean(question.get("id"))
                if not public_qid:
                    raise SQLiteCompatibilityDataError("question id must not be empty")
                qid = _question_target(assessment_public, public_qid)
                live_questions.add(qid)
                qkey = _question_key(assessment_public, public_qid)
                created_at = str(question.get("created_at") or workspace_created)
                updated_at = str(question.get("updated_at") or created_at)
                status = _token(question.get("status")) or "not_started"
                status = {"pending": "not_started", "in_progress": "attempted", "done": "completed"}.get(status, status)
                if status not in {"not_started", "attempted", "stuck", "completed"}:
                    status = "not_started"
                self.connection.execute(
                    "INSERT INTO questions (id,assessment_id,ordinal,question_text,max_marks_milli,status,user_notes,import_batch_id,created_at,updated_at,deleted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET "
                    "assessment_id=excluded.assessment_id,ordinal=excluded.ordinal,question_text=excluded.question_text,"
                    "max_marks_milli=excluded.max_marks_milli,status=excluded.status,user_notes=excluded.user_notes,"
                    "updated_at=excluded.updated_at,deleted_at=NULL",
                    (
                        qid,
                        aid,
                        position + 1,
                        str(question.get("text") or "").strip(),
                        _milli(question.get("marks")),
                        status,
                        str(question.get("notes") or ""),
                        None,
                        created_at,
                        updated_at,
                    ),
                )
                self.connection.execute("DELETE FROM question_sources WHERE question_id=?", (qid,))
                source_file = question.get("source_file")
                if isinstance(source_file, str) and source_file.strip():
                    source_key = qkey + "/source:legacy"
                    sid = stable_target_id("data/assessment_workspace.json", "question_source", source_key)
                    page = question.get("source_page")
                    try:
                        page = int(page) if page not in (None, "") else None
                    except (TypeError, ValueError):
                        page = None
                    number = _clean(question.get("source_question_number"))
                    locator = "question:{}".format(number) if number else ""
                    self.connection.execute(
                        "INSERT INTO question_sources (id,question_id,document_id,resource_id,note_id,page_number,locator,raw_source_label,created_at) "
                        "VALUES (?,?,NULL,NULL,NULL,?,?,?,?)",
                        (sid, qid, page if page and page > 0 else None, locator, source_file.strip(), created_at),
                    )

                self._replace_question_mappings(qid, course_target, qkey, question, created_at)
                self._replace_question_attempts(qid, qkey, question, created_at)

        old_workspaces = old.get("workspaces", {}) if isinstance(old.get("workspaces", {}), Mapping) else {}
        for workspace_key, workspace in old_workspaces.items():
            if not isinstance(workspace, Mapping):
                continue
            assessment_public = _clean(workspace.get("assessment_id") or workspace_key)
            questions = workspace.get("questions", []) if isinstance(workspace.get("questions", []), list) else []
            for question in questions:
                if not isinstance(question, Mapping):
                    continue
                qid = _question_target(assessment_public, question.get("id"))
                if qid not in live_questions:
                    self.connection.execute(
                        "UPDATE questions SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                        (now, now, qid),
                    )

    def _replace_question_mappings(
        self,
        qid: str,
        course_target: Optional[str],
        qkey: str,
        question: Mapping[str, Any],
        created_at: str,
    ) -> None:
        self.connection.execute("DELETE FROM question_topic_mappings WHERE question_id=?", (qid,))
        mapping = question.get("topic_mapping")
        if not isinstance(mapping, Mapping):
            topic = _clean(question.get("topic"))
            if not topic:
                return
            target = _topic_target_from_name(self.connection, course_target, topic)
            if target is None:
                return
            rows = [(topic, None, 1, "legacy_topic", "accepted", "compatibility topic field", created_at, created_at)]
        else:
            alternatives = mapping.get("alternatives", [])
            rows = []
            if isinstance(alternatives, list):
                for rank, alt in enumerate(alternatives, start=1):
                    if not isinstance(alt, Mapping):
                        continue
                    rows.append(
                        (
                            _clean(alt.get("topic")),
                            _float(alt.get("score")),
                            rank,
                            _clean(mapping.get("method")) or "legacy_mapping",
                            "accepted" if bool(mapping.get("accepted")) and rank == 1 else "proposed",
                            "compatibility projection",
                            str(mapping.get("mapped_at") or created_at),
                            str(mapping.get("mapped_at") or created_at) if bool(mapping.get("accepted")) and rank == 1 else None,
                        )
                    )
            if not rows:
                suggested = _clean(mapping.get("suggested_topic") or question.get("topic"))
                if suggested:
                    rows = [(
                        suggested,
                        _float(mapping.get("score")),
                        1,
                        _clean(mapping.get("method")) or "legacy_mapping",
                        "accepted" if bool(mapping.get("accepted")) else "proposed",
                        "compatibility projection",
                        str(mapping.get("mapped_at") or created_at),
                        str(mapping.get("mapped_at") or created_at) if bool(mapping.get("accepted")) else None,
                    )]
        for topic_name, score, rank, method, state, reason, mapped_at, reviewed_at in rows:
            topic_id = _topic_target_from_name(self.connection, course_target, topic_name)
            if topic_id is None:
                continue
            mid = stable_target_id(
                "runtime/assessment_workspace.json",
                "question_topic_mapping",
                "{}/mapping:{}:{}".format(qkey, rank, topic_name.casefold()),
            )
            self.connection.execute(
                "INSERT INTO question_topic_mappings (id,question_id,topic_id,score,rank,method,state,reason,created_at,reviewed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (mid, qid, topic_id, score, rank, method, state, reason, mapped_at, reviewed_at),
            )

    def _replace_question_attempts(
        self,
        qid: str,
        qkey: str,
        question: Mapping[str, Any],
        created_at: str,
    ) -> None:
        attempt_ids = [str(row[0]) for row in self.connection.execute(
            "SELECT id FROM question_attempts WHERE question_id=?", (qid,)
        ).fetchall()]
        if attempt_ids:
            placeholders = ",".join("?" for _ in attempt_ids)
            self.connection.execute(
                "DELETE FROM mistake_events WHERE attempt_id IN ({})".format(placeholders),
                tuple(attempt_ids),
            )
        self.connection.execute("DELETE FROM question_attempts WHERE question_id=?", (qid,))
        combined = []
        top = question.get("attempts", [])
        if isinstance(top, list):
            combined.extend(top)
        performance = question.get("performance")
        if isinstance(performance, Mapping) and isinstance(performance.get("attempts"), list):
            combined.extend(performance.get("attempts", []))
        for index, raw in enumerate(combined, start=1):
            if not isinstance(raw, Mapping):
                continue
            occurred = str(raw.get("time") or raw.get("occurred_at") or created_at)
            attempt_id = stable_target_id(
                "runtime/assessment_workspace.json",
                "question_attempt",
                "{}/attempt:{}".format(qkey, index),
            )
            response = raw.get("response_ref")
            if response is None and "response" in raw:
                response = _json(raw.get("response"))
            feedback = raw.get("feedback_ref")
            if feedback is None and raw.get("feedback") not in (None, ""):
                feedback = str(raw.get("feedback"))
            self.connection.execute(
                "INSERT INTO question_attempts (id,question_id,attempt_number,outcome,earned_marks_milli,max_marks_milli,response_ref,feedback_ref,occurred_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    qid,
                    index,
                    _clean(raw.get("outcome")) or "unknown",
                    _milli(raw.get("earned_marks")),
                    _milli(raw.get("max_marks")),
                    str(response) if response not in (None, "") else None,
                    str(feedback) if feedback not in (None, "") else None,
                    occurred,
                ),
            )
            mistake = raw.get("mistake")
            if isinstance(mistake, str) and mistake.strip():
                mistake_id = stable_target_id(
                    "runtime/assessment_workspace.json",
                    "mistake_event",
                    "{}/mistake".format(attempt_id),
                )
                self.connection.execute(
                    "INSERT INTO mistake_events (id,attempt_id,category,mistake_text,created_at,resolved_at) VALUES (?,?,?,?,?,NULL)",
                    (mistake_id, attempt_id, "legacy_attempt", mistake.strip(), occurred),
                )

    # ------------------------------------------------------------- memory/progress
    def _sync_learning_memory(self, new: Mapping[str, Any], now: str) -> None:
        current_ids = set()

        def emit_scope(scope_type: str, scope_id: Optional[str], scope: Mapping[str, Any]) -> None:
            public_course = scope_id
            course_target = _course_target_from_public(self.connection, public_course) if public_course else None
            for kind, field in (("weak_topic", "weak_topics"), ("mastered_topic", "mastered_topics")):
                values = scope.get(field, [])
                if not isinstance(values, list):
                    continue
                for index, value in enumerate(values):
                    topic = _clean(value)
                    if not topic:
                        continue
                    key = "{}:{}:{}:{}".format(scope_type, public_course or "global", kind, topic.casefold())
                    entry_id = stable_target_id("runtime/learning_memory.json", "memory_entry", key)
                    current_ids.add(entry_id)
                    topic_id = _topic_target_from_name(self.connection, course_target, topic)
                    self.connection.execute(
                        "INSERT INTO learning_memory_entries (id,scope_type,scope_id,kind,topic_id,raw_topic,memory_text,source_entity_type,source_entity_id,created_at,updated_at,archived_at) "
                        "VALUES (?,?,?,?,?,?,?,'phase4_compatibility',NULL,?,?,NULL) ON CONFLICT(id) DO UPDATE SET "
                        "topic_id=excluded.topic_id,raw_topic=excluded.raw_topic,updated_at=excluded.updated_at,archived_at=NULL",
                        (entry_id, scope_type, course_target if scope_type == "course" else None, kind, topic_id, topic, "", now, now),
                    )
                    if topic_id is not None:
                        event_id = stable_target_id("runtime/learning_memory.json", "topic_progress_event", key)
                        self.connection.execute(
                            "INSERT INTO topic_progress_events (id,topic_id,event_type,previous_status,new_status,confidence,evidence_type,evidence_id,occurred_at,note) "
                            "VALUES (?,?,?,?,?,NULL,'learning_memory',?,?,'compatibility memory state') "
                            "ON CONFLICT(id) DO UPDATE SET topic_id=excluded.topic_id,new_status=excluded.new_status,occurred_at=excluded.occurred_at",
                            (event_id, topic_id, kind, None, "weak" if kind == "weak_topic" else "mastered", entry_id, now),
                        )
            for kind, field in (("note", "notes"), ("activity", "recent_activity")):
                values = scope.get(field, [])
                if not isinstance(values, list):
                    continue
                for index, value in enumerate(values):
                    if kind == "note":
                        if isinstance(value, str):
                            text = value.strip(); created = now; raw_topic = ""
                        elif isinstance(value, Mapping):
                            text = str(value.get("text") or "").strip(); created = str(value.get("created_at") or now); raw_topic = ""
                        else:
                            continue
                    else:
                        if not isinstance(value, Mapping):
                            continue
                        text = str(value.get("question") or "").strip()
                        created = str(value.get("time") or now)
                        raw_topic = str(value.get("topic") or "").strip()
                    if not text:
                        continue
                    key = "{}:{}:{}:{}:{}".format(scope_type, public_course or "global", kind, index, created)
                    entry_id = stable_target_id("runtime/learning_memory.json", "memory_entry", key)
                    current_ids.add(entry_id)
                    self.connection.execute(
                        "INSERT INTO learning_memory_entries (id,scope_type,scope_id,kind,topic_id,raw_topic,memory_text,source_entity_type,source_entity_id,created_at,updated_at,archived_at) "
                        "VALUES (?,?,?,?,NULL,?,?,'phase4_compatibility',NULL,?,?,NULL) ON CONFLICT(id) DO UPDATE SET "
                        "raw_topic=excluded.raw_topic,memory_text=excluded.memory_text,updated_at=excluded.updated_at,archived_at=NULL",
                        (entry_id, scope_type, course_target if scope_type == "course" else None, kind, raw_topic, text, created, now),
                    )

        emit_scope("global", None, new)
        course_memory = new.get("course_memory", {})
        if isinstance(course_memory, Mapping):
            for public_course, scope in course_memory.items():
                if isinstance(scope, Mapping):
                    emit_scope("course", str(public_course), scope)
        rows = self.connection.execute(
            "SELECT id FROM learning_memory_entries WHERE source_entity_type='phase4_compatibility' AND archived_at IS NULL"
        ).fetchall()
        for row in rows:
            if str(row[0]) not in current_ids:
                self.connection.execute(
                    "UPDATE learning_memory_entries SET archived_at=?,updated_at=? WHERE id=?",
                    (now, now, str(row[0])),
                )

    def _sync_progress_history(self, new: Mapping[str, Any], now: str) -> None:
        courses = new.get("courses", {})
        if not isinstance(courses, Mapping):
            raise SQLiteCompatibilityDataError("progress history courses must be an object")
        for public_course, snapshots in courses.items():
            if not isinstance(snapshots, list):
                continue
            course_target = _course_target_from_public(self.connection, public_course)
            if course_target is None:
                continue
            for index, snapshot in enumerate(snapshots):
                if not isinstance(snapshot, Mapping):
                    continue
                captured = str(snapshot.get("captured_at") or now)
                date_text = str(snapshot.get("date") or captured[:10] or now[:10])
                key = "{}:{}:{}".format(public_course, date_text, captured)
                sid = stable_target_id("runtime/course_progress_history.json", "progress_snapshot", key)
                counts = snapshot.get("status_counts", {})
                if not isinstance(counts, Mapping):
                    counts = {}
                score = {
                    k: deepcopy(v)
                    for k, v in snapshot.items()
                    if k not in {"status_counts", "captured_at", "date", "course_id"}
                }
                self.connection.execute(
                    "INSERT INTO progress_snapshots (id,course_id,snapshot_date,counts_json,score_json,engine_version,created_at) "
                    "VALUES (?,?,?,?,?,'V9-compatibility',?) ON CONFLICT(id) DO UPDATE SET "
                    "course_id=excluded.course_id,snapshot_date=excluded.snapshot_date,counts_json=excluded.counts_json,"
                    "score_json=excluded.score_json,created_at=excluded.created_at",
                    (sid, course_target, date_text, _json(dict(counts)), _json(score), captured),
                )

    # ------------------------------------------------------------------- plans
    def _sync_plan_store(self, store_name: str, new: Mapping[str, Any], now: str) -> None:
        config = {
            STORE_WEEKLY_PLANS: ("data/weekly_study_plans.json", "weekly", "week", "weekly_planner", "V9.1"),
            STORE_MULTI_COURSE_PLANS: ("data/multi_course_weekly_plans.json", "multi_course_weekly", "week", "multi_course_planner", "V9.2"),
            STORE_INTELLIGENT_PLANS: ("data/intelligent_study_plans.json", "intelligent", "adaptive", "intelligent_study_planner", "V11"),
        }[store_name]
        source_path, default_kind, default_horizon, engine_name, default_version = config
        plans = new.get("plans", [])
        if not isinstance(plans, list):
            raise SQLiteCompatibilityDataError("study plan store plans must be a list")
        for index, plan in enumerate(plans):
            if not isinstance(plan, Mapping):
                continue
            explicit_id = _clean(plan.get("id"))
            if explicit_id:
                plan_key = "plan:id:{}".format(explicit_id)
            else:
                plan_key = "plan:{}:{}:{}:{}".format(
                    _clean(plan.get("kind")) or default_kind,
                    _clean(plan.get("created_at")),
                    _clean(plan.get("start_date") or plan.get("date") or plan.get("starts_on")),
                    index,
                )
            plan_id = stable_target_id(source_path, "study_plan", plan_key)
            kind = default_kind
            horizon = default_horizon
            raw_kind = _token(plan.get("kind"))
            if store_name == STORE_INTELLIGENT_PLANS:
                if raw_kind == "today": kind, horizon = "intelligent_today", "day"
                elif raw_kind in {"week", "weekly"}: kind, horizon = "intelligent_week", "week"
            start = _clean(plan.get("start_date") or plan.get("date") or plan.get("starts_on")) or now[:10]
            sessions = self._flatten_plan_sessions(plan, start)
            allocated = sum(max(0, int(item.get("minutes") or 0)) for item in sessions)
            requested = plan.get("total_weekly_minutes")
            if requested is None:
                requested = plan.get("available_minutes")
            if requested is None:
                requested = allocated
            try:
                requested = max(0, int(requested))
            except (TypeError, ValueError):
                requested = allocated
            end = max([item["plan_date"] for item in sessions], default=start)
            created_at = str(plan.get("created_at") or now)
            self.connection.execute(
                "INSERT INTO study_plans (id,kind,horizon,starts_on,ends_on,requested_minutes,allocated_minutes,status,engine_name,engine_version,rationale,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,'proposed',?,?,?, ?,?) ON CONFLICT(id) DO UPDATE SET "
                "kind=excluded.kind,horizon=excluded.horizon,starts_on=excluded.starts_on,ends_on=excluded.ends_on,"
                "requested_minutes=excluded.requested_minutes,allocated_minutes=excluded.allocated_minutes,"
                "engine_name=excluded.engine_name,engine_version=excluded.engine_version,updated_at=excluded.updated_at",
                (plan_id, kind, horizon, start, end, requested, allocated, engine_name, _clean(plan.get("engine_version")) or default_version, "compatibility projection", created_at, now),
            )
            self.connection.execute("DELETE FROM study_plan_items WHERE plan_id=?", (plan_id,))
            for ordinal, item in enumerate(sessions, start=1):
                course_target = _course_target_from_public(self.connection, item.get("course_id"))
                topic_target = _topic_target_from_name(self.connection, course_target, item.get("topic"))
                item_id = stable_target_id(
                    source_path, "study_plan_item", "{}/item:{}:{}".format(plan_key, item["plan_date"], ordinal)
                )
                self.connection.execute(
                    "INSERT INTO study_plan_items (id,plan_id,plan_date,ordinal,course_id,topic_id,assessment_id,resource_id,note_id,minutes,action,reason,score,status) "
                    "VALUES (?,?,?,?,?,?,NULL,NULL,NULL,?,?,?,?,?)",
                    (
                        item_id,
                        plan_id,
                        item["plan_date"],
                        ordinal,
                        course_target,
                        topic_target,
                        max(0, int(item.get("minutes") or 0)),
                        item.get("action") or "Study plan item",
                        item.get("reason") or "compatibility projection",
                        _float(item.get("score")),
                        item.get("status") or "planned",
                    ),
                )

    def _flatten_plan_sessions(self, plan: Mapping[str, Any], start: str) -> list:
        result = []
        top_sessions = plan.get("sessions")
        if isinstance(top_sessions, list):
            for raw in top_sessions:
                if isinstance(raw, Mapping):
                    result.append(self._plan_session(raw, _clean(plan.get("date")) or start))
        days = plan.get("days")
        if isinstance(days, list):
            for day in days:
                if not isinstance(day, Mapping):
                    continue
                day_date = _clean(day.get("date")) or start
                sessions = day.get("sessions", [])
                if isinstance(sessions, list):
                    for raw in sessions:
                        if isinstance(raw, Mapping):
                            result.append(self._plan_session(raw, day_date))
        return result

    def _plan_session(self, raw: Mapping[str, Any], plan_date: str) -> dict:
        actions = raw.get("actions", [])
        if isinstance(actions, list):
            action = "; ".join(_clean(item) for item in actions if _clean(item))
        else:
            action = _clean(actions)
        return {
            "plan_date": plan_date,
            "course_id": raw.get("course_id"),
            "topic": raw.get("topic"),
            "minutes": raw.get("minutes", 0),
            "action": action or ("Study {}".format(_clean(raw.get("topic"))) if _clean(raw.get("topic")) else "Study plan item"),
            "reason": ", ".join(str(x) for x in raw.get("reasons", []) if str(x).strip()) if isinstance(raw.get("reasons"), list) else "compatibility projection",
            "score": raw.get("score") if raw.get("score") is not None else raw.get("priority_score"),
            "status": _token(raw.get("status") or raw.get("type")) or "planned",
        }

    # ------------------------------------------------------------------- grades
    def _sync_grade_config(self, new: Mapping[str, Any], now: str) -> None:
        semester_name = _clean(new.get("semester_name")) or "Semester 1"
        semester_id = self._resolve_semester(semester_name, now)
        scale_id = stable_target_id("data/semester_grade_config.json", "grade_scale", "grade_scale:active")
        self.connection.execute(
            "INSERT INTO grade_scales (id,name,source,verified,active_from,active_to,created_at,updated_at) "
            "VALUES (?,?,'legacy planning config',0,NULL,NULL,?,?) ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name,updated_at=excluded.updated_at",
            (scale_id, "Compatibility Grade Scale", now, now),
        )
        self.connection.execute("DELETE FROM grade_bands WHERE scale_id=?", (scale_id,))
        bands = new.get("grade_scale", [])
        if isinstance(bands, list):
            for position, band in enumerate(bands):
                if not isinstance(band, Mapping):
                    continue
                minimum = _bps(band.get("min_score"))
                points = _milli(band.get("grade_point"))
                letter = _clean(band.get("letter"))
                if minimum is None or points is None or not letter:
                    continue
                bid = stable_target_id(
                    "data/semester_grade_config.json", "grade_band", "grade_band:{}:{}".format(position, letter)
                )
                self.connection.execute(
                    "INSERT INTO grade_bands (id,scale_id,minimum_bps,letter_grade,grade_point_milli) VALUES (?,?,?,?,?)",
                    (bid, scale_id, minimum, letter, points),
                )
        target_sgpa = _milli(new.get("target_sgpa"))
        self.connection.execute(
            "INSERT INTO semester_grade_settings (semester_id,scale_id,target_sgpa_milli,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(semester_id) DO UPDATE SET scale_id=excluded.scale_id,target_sgpa_milli=excluded.target_sgpa_milli,updated_at=excluded.updated_at",
            (semester_id, scale_id, target_sgpa, now),
        )
        courses = new.get("courses", [])
        if isinstance(courses, list):
            for position, item in enumerate(courses):
                if not isinstance(item, Mapping):
                    continue
                course_target = _course_target_from_public(self.connection, item.get("course_id"))
                if course_target is None:
                    continue
                credit_milli = _milli(item.get("credits"))
                self.connection.execute(
                    "UPDATE semester_courses SET credits_milli=? WHERE semester_id=? AND course_id=?",
                    (credit_milli, semester_id, course_target),
                )
                gp = _milli(item.get("manual_grade_point"))
                letter = _clean(item.get("manual_letter_grade")) or None
                score = _bps(item.get("manual_score"))
                if gp is None and letter is None and score is None:
                    continue
                entry_id = stable_target_id(
                    "data/semester_grade_config.json", "manual_grade_entry", "manual:{}:{}".format(semester_id, course_target)
                )
                self.connection.execute(
                    "INSERT INTO manual_grade_entries (id,semester_id,course_id,score_bps,letter_grade,grade_point_milli,entry_kind,note,recorded_at) "
                    "VALUES (?,?,?,?,?,?,'compatibility','',?) ON CONFLICT(id) DO UPDATE SET "
                    "score_bps=excluded.score_bps,letter_grade=excluded.letter_grade,grade_point_milli=excluded.grade_point_milli,recorded_at=excluded.recorded_at",
                    (entry_id, semester_id, course_target, score, letter, gp, now),
                )
        result = new.get("semester_result")
        if isinstance(result, Mapping):
            rid = stable_target_id("data/semester_grade_config.json", "semester_result", "semester_result:{}".format(semester_id))
            earned_credits = _milli(result.get("earned_credits")) or 0
            earned_points = _milli(result.get("earned_grade_points")) or 0
            sgpa = _milli(result.get("sgpa")) or 0
            self.connection.execute(
                "INSERT INTO semester_results (id,semester_id,earned_credits_milli,earned_grade_points_milli,sgpa_milli,verified,source,recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET earned_credits_milli=excluded.earned_credits_milli,"
                "earned_grade_points_milli=excluded.earned_grade_points_milli,sgpa_milli=excluded.sgpa_milli,"
                "verified=excluded.verified,source=excluded.source,recorded_at=excluded.recorded_at",
                (rid, semester_id, earned_credits, earned_points, sgpa, 1 if result.get("verified") else 0, str(result.get("source") or ""), str(result.get("recorded_at") or now)),
            )

    def _resolve_semester(self, semester_name: str, now: str) -> str:
        rows = self.connection.execute(
            "SELECT id FROM semesters WHERE name=?", (semester_name,)
        ).fetchall()
        if len(rows) == 1:
            return str(rows[0][0])
        match = re.search(r"(\d+)\s*$", semester_name)
        if match:
            key = "semester:{}".format(match.group(1))
            target = stable_target_id("data/courses.json", "semester_placeholder", key)
            if self.connection.execute("SELECT 1 FROM semesters WHERE id=?", (target,)).fetchone():
                return target
        rows = self.connection.execute("SELECT id FROM semesters ORDER BY created_at,id").fetchall()
        if len(rows) == 1:
            return str(rows[0][0])
        sid = stable_target_id("runtime/semester_grade_config.json", "semester", semester_name.casefold())
        self.connection.execute(
            "INSERT INTO semesters (id,name,academic_year,starts_on,ends_on,status,created_at,updated_at) "
            "VALUES (?,?, 'legacy-unknown',NULL,NULL,'active',?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,updated_at=excluded.updated_at",
            (sid, semester_name, now, now),
        )
        return sid

    def integrity_checks(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        integrity = tuple(str(row[0]) for row in self.connection.execute("PRAGMA integrity_check").fetchall())
        foreign_keys = tuple(tuple(row) for row in self.connection.execute("PRAGMA foreign_key_check").fetchall())
        if self.connection.total_changes != before:
            raise SQLiteCompatibilityError("integrity checks unexpectedly mutated SQLite")
        return {
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "pass": integrity == ("ok",) and not foreign_keys,
        }


__all__ = (
    "PROJECTION_PREFIX",
    "PROJECTION_VERSION",
    "REQUIRED_TABLES",
    "SQLiteCompatibilityAuthorityError",
    "SQLiteCompatibilityDataError",
    "SQLiteCompatibilityError",
    "SQLiteCompatibilityProjectionMissingError",
    "SQLiteCompatibilityProjectionRepository",
    "SQLiteCompatibilitySchemaError",
    "STORE_ASSESSMENTS",
    "STORE_ASSESSMENT_WORKSPACE",
    "STORE_COURSES",
    "STORE_GRADE_CONFIG",
    "STORE_INTELLIGENT_PLANS",
    "STORE_LEARNING_MEMORY",
    "STORE_MULTI_COURSE_PLANS",
    "STORE_PROGRESS_HISTORY",
    "STORE_WEEKLY_PLANS",
)
