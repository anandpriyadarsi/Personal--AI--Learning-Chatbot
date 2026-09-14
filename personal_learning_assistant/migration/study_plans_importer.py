"""Idempotent Phase 3 importer for legacy study-plan stores.

This is a shadow migration adapter only. It imports verified weekly,
multi-course weekly, and intelligent study-plan JSON snapshots into an explicit
temporary SQLite database while JSON remains authoritative until the Phase 4
cutover gate is approved.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.repositories.sqlite.connection import transaction

from .import_ledger import MigrationImportLedger, build_import_identity
from .legacy_json_import import (
    ImportIssue,
    ImportTally,
    LegacyImportDataError,
    LegacyImportError,
    add_tally,
    ensure_tables,
    freeze_tally,
    load_verified_json,
    source_sha256,
    stable_target_id,
)
from .legacy_source_scanner import LegacySourceSnapshot, STATUS_MISSING, STATUS_VALID_JSON


WEEKLY_SOURCE_PATH = "data/weekly_study_plans.json"
MULTI_SOURCE_PATH = "data/multi_course_weekly_plans.json"
INTELLIGENT_SOURCE_PATH = "data/intelligent_study_plans.json"
COURSE_SOURCE_PATH = "data/courses.json"

SUPPORTED_SOURCE_PATHS = (
    WEEKLY_SOURCE_PATH,
    MULTI_SOURCE_PATH,
    INTELLIGENT_SOURCE_PATH,
)

OPTIONAL_SOURCE_PATHS = {INTELLIGENT_SOURCE_PATH}

REQUIRED_TABLES = (
    "migration_imports",
    "courses",
    "topics",
    "study_plans",
    "study_plan_items",
)

PLAN_SOURCE_CONFIG = {
    WEEKLY_SOURCE_PATH: {
        "kind": "weekly",
        "horizon": "week",
        "engine_name": "weekly_planner",
        "engine_version": "V9.1",
    },
    MULTI_SOURCE_PATH: {
        "kind": "multi_course_weekly",
        "horizon": "week",
        "engine_name": "multi_course_planner",
        "engine_version": "V9.2",
    },
    INTELLIGENT_SOURCE_PATH: {
        "kind": "intelligent",
        "horizon": "adaptive",
        "engine_name": "intelligent_study_planner",
        "engine_version": "V11",
    },
}


@dataclass(frozen=True)
class StudyPlanReviewItem:
    source_path: str
    plan_legacy_key: str
    item_legacy_key: str
    raw_course_id: str
    raw_topic: str
    reason: str


@dataclass(frozen=True)
class StudyPlanImportResult:
    sources_scanned: int
    imported_sources: Tuple[str, ...]
    optional_sources_absent: Tuple[str, ...]
    study_plans: ImportTally
    study_plan_items: ImportTally
    total_plan_items: int
    unresolved_course_refs: int
    unresolved_topic_refs: int
    review_items: Tuple[StudyPlanReviewItem, ...]
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        return (
            self.study_plans.created
            + self.study_plans.updated
            + self.study_plan_items.created
            + self.study_plan_items.updated
        )

    @property
    def review_required_items(self) -> int:
        return len(self.review_items)


# Compatibility aliases for callers using the feature title.
StudyPlansImportResult = StudyPlanImportResult
PlanningImportResult = StudyPlanImportResult


@dataclass(frozen=True)
class _PreparedPlanItem:
    legacy_key: str
    target_id: str
    plan_date: str
    ordinal: int
    raw_course_id: str
    raw_topic: str
    course_id: Optional[str]
    topic_id: Optional[str]
    minutes: int
    action: str
    reason: str
    score: Optional[float]
    status: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedPlan:
    source_path: str
    source_hash: str
    source_version: str
    source_type: str
    legacy_key: str
    target_id: str
    kind: str
    horizon: str
    starts_on: str
    ends_on: str
    requested_minutes: int
    allocated_minutes: int
    status: str
    engine_name: str
    engine_version: str
    rationale: str
    created_at: str
    updated_at: str
    items: Tuple[_PreparedPlanItem, ...]
    raw: Mapping[str, Any]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_label(value: Any) -> str:
    return _clean_text(value).casefold()


def _normalized_token(value: Any) -> str:
    text = _clean_text(value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _timestamp(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _date_text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()[:10]
        try:
            date.fromisoformat(text)
            return text
        except ValueError:
            return fallback
    return fallback


def _date_from_timestamp(value: str, fallback: str = "1970-01-01") -> str:
    text = str(value or "").strip()
    if len(text) >= 10:
        return _date_text(text[:10], fallback)
    return fallback


def _date_add(start_date: str, offset_days: int) -> str:
    try:
        base = date.fromisoformat(start_date)
    except ValueError:
        return start_date
    return (base + timedelta(days=offset_days)).isoformat()


def _max_date(values: Sequence[str], fallback: str) -> str:
    valid = []
    for value in values:
        try:
            date.fromisoformat(value)
        except ValueError:
            continue
        valid.append(value)
    return max(valid) if valid else fallback


def _non_negative_int(
    value: Any,
    *,
    field: str,
    legacy_key: str,
    issues: List[ImportIssue],
    default: int = 0,
) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        parsed = None
    else:
        try:
            number = Decimal(str(value).strip())
            if not number.is_finite():
                parsed = None
            else:
                parsed = int(number.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError):
            parsed = None
    if parsed is None or parsed < 0:
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_study_plan_minutes",
                message=(
                    "Study-plan field '{}' value {!r} is not a non-negative "
                    "number; imported as {} while the raw value remains in the ledger."
                ).format(field, value, default),
                legacy_key=legacy_key,
            )
        )
        return default
    return parsed


def _score(value: Any, *, legacy_key: str, issues: List[ImportIssue]) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        parsed = None
    else:
        try:
            decimal_value = Decimal(str(value).strip())
            parsed = float(decimal_value) if decimal_value.is_finite() else None
        except (InvalidOperation, ValueError):
            parsed = None
    if parsed is None:
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_study_plan_score",
                message=(
                    "Study-plan priority/score value {!r} is not finite; "
                    "imported as NULL while raw data remains in the ledger."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
    return parsed


def _status(value: Any, *, default: str = "planned") -> str:
    raw = _normalized_token(value)
    allowed = {
        "planned",
        "proposed",
        "active",
        "completed",
        "done",
        "skipped",
        "cancelled",
        "buffer",
        "study",
        "weekly_review",
        "short_review",
    }
    if raw == "done":
        return "completed"
    return raw if raw in allowed else default


def _action_from_session(session: Mapping[str, Any], topic: str, fallback: str) -> str:
    raw_actions = session.get("actions")
    actions = []
    if isinstance(raw_actions, list):
        for item in raw_actions:
            text = _clean_text(item)
            if text:
                actions.append(text)
    elif raw_actions:
        text = _clean_text(raw_actions)
        if text:
            actions.append(text)
    if actions:
        joined = "; ".join(actions[:4])
        return joined[:1000]
    if topic:
        return "Study {}".format(topic)
    return fallback


def _plan_key(plan: Mapping[str, Any], source_path: str, index: int, fallback_kind: str) -> str:
    explicit_id = _clean_text(plan.get("id"))
    if explicit_id:
        return "plan:id:{}".format(explicit_id)
    created_at = _clean_text(plan.get("created_at"))
    start = _clean_text(
        plan.get("start_date")
        or plan.get("date")
        or plan.get("starts_on")
    )
    kind = _clean_text(plan.get("kind")) or fallback_kind
    if created_at or start:
        return "plan:{}:{}:{}:{}".format(kind, created_at, start, index)
    return "plan:{}:{}:{}".format(source_path, fallback_kind, index)


def _course_candidates(connection: sqlite3.Connection, legacy_course_id: str) -> Tuple[str, ...]:
    lookup_keys = (
        "course:id:{}".format(legacy_course_id),
        "course:code:{}".format(legacy_course_id.casefold()),
    )
    rows = connection.execute(
        "SELECT mi.legacy_key, mi.target_id "
        "FROM migration_imports AS mi "
        "JOIN courses AS c ON c.id = mi.target_id "
        "WHERE mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'courses' "
        "AND c.deleted_at IS NULL",
        (COURSE_SOURCE_PATH,),
    ).fetchall()
    matches = set()
    folded = {item.casefold() for item in lookup_keys}
    for row in rows:
        if str(row[0]).casefold() in folded:
            matches.add(str(row[1]))
    return tuple(sorted(matches))


def _resolve_course_target(
    connection: sqlite3.Connection,
    raw_course_id: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
    review_items: List[StudyPlanReviewItem],
    raw_topic: str = "",
) -> Optional[str]:
    text = _clean_text(raw_course_id)
    if not text:
        return None
    candidates = _course_candidates(connection, text)
    if len(candidates) == 1:
        return candidates[0]
    reason = "unresolved_course_reference" if not candidates else "ambiguous_course_reference"
    issues.append(
        ImportIssue(
            severity="warning",
            code=reason,
            message=(
                "Study-plan course reference {!r} could not be resolved exactly "
                "against imported courses."
            ).format(text),
            legacy_key=legacy_key,
        )
    )
    review_items.append(
        StudyPlanReviewItem(
            source_path="",
            plan_legacy_key="",
            item_legacy_key=legacy_key,
            raw_course_id=text,
            raw_topic=raw_topic,
            reason=reason,
        )
    )
    return None


def _resolve_topic_target(
    connection: sqlite3.Connection,
    course_id: Optional[str],
    raw_topic: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
    review_items: List[StudyPlanReviewItem],
    raw_course_id: str,
) -> Optional[str]:
    label = _clean_text(raw_topic)
    if not label or course_id is None:
        return None
    normalized = label.casefold()
    rows = connection.execute(
        "SELECT DISTINCT t.id "
        "FROM topics AS t "
        "JOIN migration_imports AS mi ON mi.target_id = t.id "
        "WHERE t.course_id = ? "
        "AND t.normalized_name = ? "
        "AND t.deleted_at IS NULL "
        "AND mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'topics'",
        (course_id, normalized, COURSE_SOURCE_PATH),
    ).fetchall()
    candidates = tuple(sorted({str(row[0]) for row in rows}))
    if len(candidates) == 1:
        return candidates[0]
    reason = "unresolved_topic_reference" if not candidates else "ambiguous_topic_reference"
    issues.append(
        ImportIssue(
            severity="warning",
            code=reason,
            message=(
                "Study-plan topic reference {!r} could not be resolved exactly "
                "inside its imported course."
            ).format(label),
            legacy_key=legacy_key,
        )
    )
    review_items.append(
        StudyPlanReviewItem(
            source_path="",
            plan_legacy_key="",
            item_legacy_key=legacy_key,
            raw_course_id=raw_course_id,
            raw_topic=label,
            reason=reason,
        )
    )
    return None


def _source_config(source_path: str) -> Mapping[str, str]:
    return PLAN_SOURCE_CONFIG[source_path]


def _plan_source_kind(source_path: str, plan: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    config = _source_config(source_path)
    engine_name = config["engine_name"]
    engine_version = _clean_text(plan.get("engine_version")) or config["engine_version"]
    if source_path == INTELLIGENT_SOURCE_PATH:
        raw_kind = _normalized_token(plan.get("kind")) or "intelligent"
        if raw_kind == "today":
            return "intelligent_today", "day", engine_name, engine_version
        if raw_kind in {"week", "weekly"}:
            return "intelligent_week", "week", engine_name, engine_version
        return "intelligent", "adaptive", engine_name, engine_version
    return config["kind"], config["horizon"], engine_name, engine_version


def _extract_plan_items(
    connection: sqlite3.Connection,
    source_path: str,
    plan: Mapping[str, Any],
    plan_key: str,
    plan_id: str,
    starts_on: str,
    imported_at: str,
    issues: List[ImportIssue],
    review_items: List[StudyPlanReviewItem],
) -> Tuple[_PreparedPlanItem, ...]:
    items: List[_PreparedPlanItem] = []

    def append_item(
        *,
        raw_item: Mapping[str, Any],
        local_key: str,
        plan_date: str,
        ordinal: int,
        raw_course_id: Any = "",
        raw_topic: Any = "",
        minutes: Any = 0,
        action: str = "Study plan item",
        reason: str = "legacy study-plan item",
        score_value: Any = None,
        status_value: Any = "planned",
    ) -> None:
        item_key = "{}/item:{}".format(plan_key, local_key)
        raw_course_text = _clean_text(raw_course_id)
        raw_topic_text = _clean_text(raw_topic)
        course_id = _resolve_course_target(
            connection,
            raw_course_text,
            issues=issues,
            legacy_key=item_key,
            review_items=review_items,
            raw_topic=raw_topic_text,
        )
        topic_id = _resolve_topic_target(
            connection,
            course_id,
            raw_topic_text,
            issues=issues,
            legacy_key=item_key,
            review_items=review_items,
            raw_course_id=raw_course_text,
        )
        minute_count = _non_negative_int(
            minutes,
            field="minutes",
            legacy_key=item_key,
            issues=issues,
            default=0,
        )
        status = _status(status_value, default="planned")
        if status in {"study", "weekly_review", "short_review"}:
            status = "planned"
        item = _PreparedPlanItem(
            legacy_key=item_key,
            target_id=stable_target_id(source_path, "study_plan_item", item_key),
            plan_date=plan_date,
            ordinal=ordinal,
            raw_course_id=raw_course_text,
            raw_topic=raw_topic_text,
            course_id=course_id,
            topic_id=topic_id,
            minutes=minute_count,
            action=_clean_text(action) or "Study plan item",
            reason=reason,
            score=_score(score_value, legacy_key=item_key, issues=issues),
            status=status,
            raw=dict(raw_item),
        )
        items.append(item)

    ordinal = 1
    days = plan.get("days")
    if isinstance(days, list):
        for day_index, raw_day in enumerate(days):
            if not isinstance(raw_day, dict):
                raise LegacyImportDataError(
                    "study-plan day at index {} must be an object".format(day_index)
                )
            plan_date = _date_text(raw_day.get("date"), _date_add(starts_on, day_index))
            day_minutes = raw_day.get("total_minutes", raw_day.get("available_minutes", raw_day.get("minutes", 0)))
            sessions = raw_day.get("sessions")
            if isinstance(sessions, list) and sessions:
                for session_index, raw_session in enumerate(sessions):
                    if not isinstance(raw_session, dict):
                        raise LegacyImportDataError(
                            "study-plan session at day {} index {} must be an object".format(day_index, session_index)
                        )
                    topic = raw_session.get("topic")
                    append_item(
                        raw_item=raw_session,
                        local_key="day:{}:session:{}".format(day_index, session_index),
                        plan_date=plan_date,
                        ordinal=ordinal,
                        raw_course_id=raw_session.get("course_id", plan.get("course_id", "")),
                        raw_topic=topic,
                        minutes=raw_session.get("minutes", day_minutes),
                        action=_action_from_session(raw_session, _clean_text(topic), "Study session"),
                        reason="imported from legacy day/session plan",
                        score_value=raw_session.get("score", raw_session.get("priority_score")),
                        status_value=raw_session.get("status", raw_day.get("kind", "planned")),
                    )
                    ordinal += 1
            else:
                tasks = raw_day.get("tasks")
                if isinstance(tasks, list) and tasks:
                    task_minutes = _non_negative_int(
                        day_minutes,
                        field="day minutes",
                        legacy_key=plan_key,
                        issues=issues,
                        default=0,
                    )
                    per_task = task_minutes // len(tasks) if tasks else 0
                    remainder = task_minutes % len(tasks) if tasks else 0
                    for task_index, task in enumerate(tasks):
                        text = _clean_text(task)
                        append_item(
                            raw_item={"task": task, "day": dict(raw_day)},
                            local_key="day:{}:task:{}".format(day_index, task_index),
                            plan_date=plan_date,
                            ordinal=ordinal,
                            raw_course_id=plan.get("course_id", ""),
                            raw_topic=text,
                            minutes=per_task + (1 if task_index < remainder else 0),
                            action="Study {}".format(text or "planned task"),
                            reason="imported from legacy task-list day",
                            score_value=None,
                            status_value="planned",
                        )
                        ordinal += 1

    plan_items = plan.get("items")
    if isinstance(plan_items, list) and plan_items:
        for item_index, raw_item in enumerate(plan_items):
            if not isinstance(raw_item, dict):
                raise LegacyImportDataError(
                    "study-plan item at index {} must be an object".format(item_index)
                )
            raw_topic = raw_item.get("topic", raw_item.get("task", raw_item.get("title", "")))
            append_item(
                raw_item=raw_item,
                local_key="item:{}".format(item_index),
                plan_date=_date_text(raw_item.get("date"), starts_on),
                ordinal=ordinal,
                raw_course_id=raw_item.get("course_id", plan.get("course_id", "")),
                raw_topic=raw_topic,
                minutes=raw_item.get("minutes", raw_item.get("allocated_minutes", 0)),
                action=_clean_text(raw_item.get("action")) or "Study {}".format(_clean_text(raw_topic) or "allocated course work"),
                reason="imported from legacy plan item",
                score_value=raw_item.get("score", raw_item.get("priority_score")),
                status_value=raw_item.get("status", "planned"),
            )
            ordinal += 1

    sessions = plan.get("sessions")
    if isinstance(sessions, list) and sessions:
        plan_date = _date_text(plan.get("date"), starts_on)
        for session_index, raw_session in enumerate(sessions):
            if not isinstance(raw_session, dict):
                raise LegacyImportDataError(
                    "study-plan session at index {} must be an object".format(session_index)
                )
            topic = raw_session.get("topic")
            append_item(
                raw_item=raw_session,
                local_key="session:{}".format(session_index),
                plan_date=plan_date,
                ordinal=ordinal,
                raw_course_id=raw_session.get("course_id", plan.get("course_id", "")),
                raw_topic=topic,
                minutes=raw_session.get("minutes", 0),
                action=_action_from_session(raw_session, _clean_text(topic), "Study session"),
                reason="imported from legacy intelligent daily session",
                score_value=raw_session.get("score", raw_session.get("priority_score")),
                status_value=raw_session.get("status", "planned"),
            )
            ordinal += 1

    if not items:
        issues.append(
            ImportIssue(
                severity="info",
                code="study_plan_without_items",
                message="Study plan contains no importable item/session rows.",
                legacy_key=plan_key,
            )
        )

    return tuple(items)


def _requested_minutes(
    source_path: str,
    plan: Mapping[str, Any],
    items: Tuple[_PreparedPlanItem, ...],
    plan_key: str,
    issues: List[ImportIssue],
) -> int:
    candidates = (
        "requested_minutes",
        "total_weekly_minutes",
        "total_minutes",
        "available_minutes",
        "stored_minutes",
    )
    for field in candidates:
        if field in plan and plan.get(field) not in (None, ""):
            return _non_negative_int(
                plan.get(field),
                field=field,
                legacy_key=plan_key,
                issues=issues,
                default=sum(item.minutes for item in items),
            )
    if "daily_minutes" in plan and "study_days" in plan:
        daily = _non_negative_int(plan.get("daily_minutes"), field="daily_minutes", legacy_key=plan_key, issues=issues, default=0)
        days = _non_negative_int(plan.get("study_days"), field="study_days", legacy_key=plan_key, issues=issues, default=0)
        return daily * days
    if source_path == INTELLIGENT_SOURCE_PATH and "minutes_per_day" in plan and "study_days" in plan:
        daily = _non_negative_int(plan.get("minutes_per_day"), field="minutes_per_day", legacy_key=plan_key, issues=issues, default=0)
        days = _non_negative_int(plan.get("study_days"), field="study_days", legacy_key=plan_key, issues=issues, default=0)
        return daily * days
    return sum(item.minutes for item in items)


def _prepare_source_plans(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    imported_at: str,
    issues: List[ImportIssue],
    review_items: List[StudyPlanReviewItem],
) -> Tuple[_PreparedPlan, ...]:
    if snapshot.canonical_path not in SUPPORTED_SOURCE_PATHS:
        raise LegacyImportDataError(
            "study-plan importer does not support {}".format(snapshot.canonical_path)
        )
    data = load_verified_json(snapshot, expected_kind="object")
    raw_plans = data.get("plans", [])
    if raw_plans is None:
        raw_plans = []
    if not isinstance(raw_plans, list):
        raise LegacyImportDataError(
            "{} field 'plans' must be an array".format(snapshot.canonical_path)
        )

    version = data.get("version")
    if version not in (None, 1, 2, "1", "2"):
        issues.append(
            ImportIssue(
                severity="warning",
                code="unexpected_study_plan_store_version",
                message=(
                    "{} version {!r} was imported without rewriting the source."
                ).format(snapshot.canonical_path, version),
            )
        )

    prepared: List[_PreparedPlan] = []
    seen_keys = set()
    for index, raw_plan in enumerate(raw_plans):
        if not isinstance(raw_plan, dict):
            raise LegacyImportDataError(
                "study plan at index {} in {} must be an object".format(
                    index,
                    snapshot.canonical_path,
                )
            )
        fallback = _source_config(snapshot.canonical_path)["kind"]
        plan_key = _plan_key(raw_plan, snapshot.canonical_path, index, fallback)
        if plan_key in seen_keys:
            raise LegacyImportDataError(
                "duplicate legacy study-plan identity: {}".format(plan_key)
            )
        seen_keys.add(plan_key)
        target_id = stable_target_id(snapshot.canonical_path, "study_plan", plan_key)
        kind, horizon, engine_name, engine_version = _plan_source_kind(
            snapshot.canonical_path,
            raw_plan,
        )
        created_at = _timestamp(raw_plan.get("created_at"), imported_at)
        starts_on = _date_text(
            raw_plan.get("start_date", raw_plan.get("date", raw_plan.get("starts_on"))),
            _date_from_timestamp(created_at, _date_from_timestamp(imported_at)),
        )
        items = _extract_plan_items(
            connection,
            snapshot.canonical_path,
            raw_plan,
            plan_key,
            target_id,
            starts_on,
            imported_at,
            issues,
            review_items,
        )
        item_dates = [item.plan_date for item in items]
        if horizon == "day":
            ends_on = starts_on
        else:
            ends_on = _date_text(raw_plan.get("end_date", raw_plan.get("ends_on")), "")
            if not ends_on:
                ends_on = _max_date(item_dates, _date_add(starts_on, 6 if horizon in {"week", "adaptive"} else 0))
        allocated = sum(item.minutes for item in items)
        requested = _requested_minutes(snapshot.canonical_path, raw_plan, items, plan_key, issues)
        status = _status(raw_plan.get("status"), default="proposed")
        rationale = _clean_text(
            raw_plan.get("rationale")
            or raw_plan.get("message")
            or raw_plan.get("planner_principle")
            or "legacy study-plan import"
        )
        prepared.append(
            _PreparedPlan(
                source_path=snapshot.canonical_path,
                source_hash=snapshot.source_hash,
                source_version=snapshot.source_version,
                source_type=snapshot.source_type,
                legacy_key=plan_key,
                target_id=target_id,
                kind=kind,
                horizon=horizon,
                starts_on=starts_on,
                ends_on=ends_on,
                requested_minutes=requested,
                allocated_minutes=allocated,
                status=status,
                engine_name=engine_name,
                engine_version=engine_version,
                rationale=rationale,
                created_at=created_at,
                updated_at=_timestamp(raw_plan.get("updated_at"), created_at),
                items=items,
                raw=dict(raw_plan),
            )
        )
    return tuple(prepared)


def _ledger_disposition(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot: LegacySourceSnapshot,
    *,
    legacy_key: str,
    target_table: str,
    target_id: str,
    existence_sql: str,
    existence_params: Tuple[Any, ...],
) -> str:
    identity = build_import_identity(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        source_type=snapshot.source_type,
        source_version=snapshot.source_version,
        legacy_key=legacy_key,
        target_table=target_table,
    )
    existing = ledger.find(identity)
    if existing is not None:
        if existing.target_id != target_id:
            ledger.record_snapshot_import(
                snapshot,
                legacy_key=legacy_key,
                target_table=target_table,
                target_id=target_id,
            )
        target_exists = connection.execute(existence_sql, existence_params).fetchone()
        if target_exists is None:
            raise LegacyImportError(
                "migration ledger points to a missing {} target: {}".format(
                    target_table,
                    target_id,
                )
            )
        return "matched"

    target_exists = connection.execute(existence_sql, existence_params).fetchone()
    return "updated" if target_exists is not None else "created"


def _stage_owned_plan_items(
    connection: sqlite3.Connection,
    source_path: str,
    plan_id: str,
) -> None:
    rows = connection.execute(
        "SELECT spi.id, spi.plan_date, spi.ordinal "
        "FROM study_plan_items AS spi "
        "JOIN migration_imports AS mi ON mi.target_id = spi.id "
        "WHERE spi.plan_id = ? "
        "AND mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'study_plan_items' "
        "ORDER BY spi.plan_date, spi.ordinal, spi.id",
        (plan_id, source_path),
    ).fetchall()
    if not rows:
        return
    maximum = connection.execute(
        "SELECT COALESCE(MAX(ordinal), 0) FROM study_plan_items WHERE plan_id = ?",
        (plan_id,),
    ).fetchone()[0]
    stage_base = int(maximum) + len(rows) + 1000
    for offset, row in enumerate(rows, start=1):
        connection.execute(
            "UPDATE study_plan_items SET ordinal = ?, status = 'superseded' WHERE id = ?",
            (stage_base + offset, str(row[0])),
        )


def _snapshot_by_path(
    snapshots: Iterable[LegacySourceSnapshot],
) -> Dict[str, LegacySourceSnapshot]:
    mapping = {}
    for snapshot in snapshots:
        mapping[snapshot.canonical_path] = snapshot
    return mapping


def import_study_plans(
    connection: sqlite3.Connection,
    snapshots: Iterable[LegacySourceSnapshot],
    *,
    imported_at: str,
) -> StudyPlanImportResult:
    """Import verified weekly/multi-course/intelligent plan snapshots.

    Missing optional ``intelligent_study_plans.json`` is recorded as absence.
    Missing required weekly or multi-course stores fail before any write.
    """
    ensure_tables(connection, REQUIRED_TABLES)
    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")

    by_path = _snapshot_by_path(snapshots)
    missing_required = [
        path for path in (WEEKLY_SOURCE_PATH, MULTI_SOURCE_PATH)
        if path not in by_path or by_path[path].status != STATUS_VALID_JSON
    ]
    if missing_required:
        raise LegacyImportDataError(
            "required study-plan sources are missing or not valid_json: {}".format(
                ", ".join(missing_required)
            )
        )

    optional_absent: List[str] = []
    prepared_by_snapshot: List[Tuple[LegacySourceSnapshot, Tuple[_PreparedPlan, ...]]] = []
    issues: List[ImportIssue] = []
    review_items: List[StudyPlanReviewItem] = []

    for path in SUPPORTED_SOURCE_PATHS:
        snapshot = by_path.get(path)
        if snapshot is None:
            if path in OPTIONAL_SOURCE_PATHS:
                optional_absent.append(path)
                continue
            raise LegacyImportDataError("required study-plan source missing: {}".format(path))
        if snapshot.status == STATUS_MISSING and path in OPTIONAL_SOURCE_PATHS:
            optional_absent.append(path)
            continue
        if snapshot.status != STATUS_VALID_JSON:
            raise LegacyImportDataError(
                "study-plan source {} is not importable: {}".format(path, snapshot.status)
            )
        prepared = _prepare_source_plans(
            connection,
            snapshot,
            imported_at,
            issues,
            review_items,
        )
        prepared_by_snapshot.append((snapshot, prepared))

    counters: Dict[str, Dict[str, int]] = {
        "study_plans": {},
        "study_plan_items": {},
    }
    ledger = MigrationImportLedger(connection)

    with transaction(connection, immediate=True):
        for snapshot, plans in prepared_by_snapshot:
            for plan in plans:
                disposition = _ledger_disposition(
                    connection,
                    ledger,
                    snapshot,
                    legacy_key=plan.legacy_key,
                    target_table="study_plans",
                    target_id=plan.target_id,
                    existence_sql="SELECT 1 FROM study_plans WHERE id = ?",
                    existence_params=(plan.target_id,),
                )
                plan_changed = disposition != "matched"
                if plan_changed:
                    connection.execute(
                        "INSERT INTO study_plans "
                        "(id, kind, horizon, starts_on, ends_on, requested_minutes, "
                        "allocated_minutes, status, engine_name, engine_version, "
                        "rationale, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "kind = excluded.kind, horizon = excluded.horizon, "
                        "starts_on = excluded.starts_on, ends_on = excluded.ends_on, "
                        "requested_minutes = excluded.requested_minutes, "
                        "allocated_minutes = excluded.allocated_minutes, "
                        "status = excluded.status, engine_name = excluded.engine_name, "
                        "engine_version = excluded.engine_version, "
                        "rationale = excluded.rationale, updated_at = excluded.updated_at",
                        (
                            plan.target_id,
                            plan.kind,
                            plan.horizon,
                            plan.starts_on,
                            plan.ends_on,
                            plan.requested_minutes,
                            plan.allocated_minutes,
                            plan.status,
                            plan.engine_name,
                            plan.engine_version,
                            plan.rationale,
                            plan.created_at,
                            plan.updated_at,
                        ),
                    )
                    ledger.record_snapshot_import(
                        snapshot,
                        legacy_key=plan.legacy_key,
                        target_table="study_plans",
                        target_id=plan.target_id,
                        details={
                            "kind": "study_plan",
                            "engine_name": plan.engine_name,
                            "engine_version": plan.engine_version,
                            "legacy_kind": plan.kind,
                            "raw": dict(plan.raw),
                        },
                        imported_at=imported_at,
                    )
                    _stage_owned_plan_items(connection, snapshot.canonical_path, plan.target_id)
                add_tally(counters["study_plans"], disposition)

                for item in plan.items:
                    item_disposition = _ledger_disposition(
                        connection,
                        ledger,
                        snapshot,
                        legacy_key=item.legacy_key,
                        target_table="study_plan_items",
                        target_id=item.target_id,
                        existence_sql="SELECT 1 FROM study_plan_items WHERE id = ?",
                        existence_params=(item.target_id,),
                    )
                    if item_disposition != "matched" or plan_changed:
                        connection.execute(
                            "INSERT INTO study_plan_items "
                            "(id, plan_id, plan_date, ordinal, course_id, topic_id, "
                            "assessment_id, resource_id, note_id, minutes, action, "
                            "reason, score, status) "
                            "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(id) DO UPDATE SET "
                            "plan_id = excluded.plan_id, plan_date = excluded.plan_date, "
                            "ordinal = excluded.ordinal, course_id = excluded.course_id, "
                            "topic_id = excluded.topic_id, minutes = excluded.minutes, "
                            "action = excluded.action, reason = excluded.reason, "
                            "score = excluded.score, status = excluded.status",
                            (
                                item.target_id,
                                plan.target_id,
                                item.plan_date,
                                item.ordinal,
                                item.course_id,
                                item.topic_id,
                                item.minutes,
                                item.action,
                                item.reason,
                                item.score,
                                item.status,
                            ),
                        )
                    if item_disposition != "matched":
                        ledger.record_snapshot_import(
                            snapshot,
                            legacy_key=item.legacy_key,
                            target_table="study_plan_items",
                            target_id=item.target_id,
                            details={
                                "kind": "study_plan_item",
                                "plan_legacy_key": plan.legacy_key,
                                "raw_course_id": item.raw_course_id,
                                "raw_topic": item.raw_topic,
                                "target_course_id": item.course_id,
                                "target_topic_id": item.topic_id,
                                "raw": dict(item.raw),
                            },
                            imported_at=imported_at,
                        )
                    add_tally(counters["study_plan_items"], item_disposition)

            # TOCTOU guard: a source change during the transaction aborts everything.
            source_sha256(snapshot)

    enriched_review_items = []
    for item in review_items:
        source_path = item.source_path
        plan_key = item.plan_legacy_key
        if not source_path or not plan_key:
            # Earlier resolution helpers run before the plan object exists; keep
            # the item portable but do not expose physical paths.
            source_path = "legacy study-plan source"
            plan_key = "legacy study-plan"
        enriched_review_items.append(
            StudyPlanReviewItem(
                source_path=source_path,
                plan_legacy_key=plan_key,
                item_legacy_key=item.item_legacy_key,
                raw_course_id=item.raw_course_id,
                raw_topic=item.raw_topic,
                reason=item.reason,
            )
        )

    unresolved_course_refs = sum(
        1 for item in enriched_review_items if "course" in item.reason
    )
    unresolved_topic_refs = sum(
        1 for item in enriched_review_items if "topic" in item.reason
    )

    return StudyPlanImportResult(
        sources_scanned=len(by_path),
        imported_sources=tuple(snapshot.canonical_path for snapshot, _ in prepared_by_snapshot),
        optional_sources_absent=tuple(optional_absent),
        study_plans=freeze_tally(counters["study_plans"]),
        study_plan_items=freeze_tally(counters["study_plan_items"]),
        total_plan_items=sum(len(plans_items.items) for _, plans in prepared_by_snapshot for plans_items in plans),
        unresolved_course_refs=unresolved_course_refs,
        unresolved_topic_refs=unresolved_topic_refs,
        review_items=tuple(enriched_review_items),
        issues=tuple(issues),
    )


def import_weekly_multi_intelligent_study_plans(
    connection: sqlite3.Connection,
    snapshots: Iterable[LegacySourceSnapshot],
    *,
    imported_at: str,
) -> StudyPlanImportResult:
    """Compatibility alias for :func:`import_study_plans`."""
    return import_study_plans(connection, snapshots, imported_at=imported_at)


def _markdown_cell(value: Any) -> str:
    return (
        str(value)
        .replace("|", "\\|")
        .replace("\r", "")
        .replace("\n", "<br>")
    )


def render_study_plan_import_review_markdown(result: StudyPlanImportResult) -> str:
    """Render a portable plan-import review report without writing a file."""
    lines = [
        "# Study Plan Import Review",
        "",
        "- Imported sources: {}".format(", ".join(result.imported_sources) or "none"),
        "- Optional sources absent: {}".format(", ".join(result.optional_sources_absent) or "none"),
        "- Plans: created {}, updated {}, matched {}".format(
            result.study_plans.created,
            result.study_plans.updated,
            result.study_plans.matched,
        ),
        "- Plan items: created {}, updated {}, matched {}".format(
            result.study_plan_items.created,
            result.study_plan_items.updated,
            result.study_plan_items.matched,
        ),
        "- Review-required items: {}".format(result.review_required_items),
        "",
    ]
    if not result.review_items:
        lines.append("No study-plan course/topic references require review.")
        return "\n".join(lines) + "\n"

    lines.extend(
        (
            "| Source | Plan | Item | Raw course | Raw topic/task | Reason |",
            "|---|---|---|---|---|---|",
        )
    )
    for item in result.review_items:
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                _markdown_cell(item.source_path),
                _markdown_cell(item.plan_legacy_key),
                _markdown_cell(item.item_legacy_key),
                _markdown_cell(item.raw_course_id or "n/a"),
                _markdown_cell(item.raw_topic or "n/a"),
                _markdown_cell(item.reason),
            )
        )
    return "\n".join(lines) + "\n"


__all__ = (
    "PlanningImportResult",
    "StudyPlanImportResult",
    "StudyPlanReviewItem",
    "StudyPlansImportResult",
    "import_study_plans",
    "import_weekly_multi_intelligent_study_plans",
    "render_study_plan_import_review_markdown",
)
