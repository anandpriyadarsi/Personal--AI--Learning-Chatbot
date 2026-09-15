"""Legacy-authoritative Phase 4.7 Study Plans SQLite dual-read backend.

The existing V9.1/V9.2/V11 planner modules remain unchanged.  This module
observes their persisted JSON stores, compares them with the Phase 3 SQLite
shadow, records structured diagnostics, and always returns the legacy result.
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.json.study_plan_repository import (
    LegacyJsonStudyPlanRepository,
)
from personal_learning_assistant.repositories.sqlite.study_plan_repository import (
    INTELLIGENT_SOURCE_PATH,
    MULTI_SOURCE_PATH,
    WEEKLY_SOURCE_PATH,
    SQLiteStudyPlanRepository,
)


_SOURCE_TO_STATE_KEY = {
    WEEKLY_SOURCE_PATH: "weekly",
    MULTI_SOURCE_PATH: "multi_course",
    INTELLIGENT_SOURCE_PATH: "intelligent",
}
_SOURCE_CONFIG = {
    WEEKLY_SOURCE_PATH: ("weekly", "week", "weekly_planner", "V9.1"),
    MULTI_SOURCE_PATH: ("multi_course_weekly", "week", "multi_course_planner", "V9.2"),
    INTELLIGENT_SOURCE_PATH: ("intelligent", "adaptive", "intelligent_study_planner", "V11"),
}


@dataclass(frozen=True)
class StudyPlanBackendConfig:
    mode: str = "legacy"

    def __post_init__(self) -> None:
        normalized = str(self.mode or "").strip().lower().replace("-", "_")
        if normalized not in {"legacy", "dual_read"}:
            raise ValueError("Phase 4.7 study-plan backend must be 'legacy' or 'dual_read'.")
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class StudyPlanParityDiagnostic:
    domain: str
    status: str
    key: str
    severity: str
    legacy_value: Any
    sqlite_value: Any
    message: str
    source_path: str = ""
    entity_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "status": self.status,
            "key": self.key,
            "severity": self.severity,
            "legacy_value": deepcopy(self.legacy_value),
            "sqlite_value": deepcopy(self.sqlite_value),
            "message": self.message,
            "source_path": self.source_path,
            "entity_type": self.entity_type,
        }


@dataclass(frozen=True)
class StudyPlanParityReport:
    operation: str
    diagnostics: Tuple[StudyPlanParityDiagnostic, ...]

    @property
    def mismatch_count(self) -> int:
        return sum(item.status in {"mismatch", "error"} for item in self.diagnostics)

    @property
    def deferred_count(self) -> int:
        return sum(item.status == "deferred" for item in self.diagnostics)

    @property
    def is_semantically_equal(self) -> bool:
        return self.mismatch_count == 0

    @property
    def status(self) -> str:
        if self.mismatch_count:
            return "mismatch"
        if self.deferred_count:
            return "pass_with_deferred"
        return "pass"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "is_semantically_equal": self.is_semantically_equal,
            "mismatch_count": self.mismatch_count,
            "deferred_count": self.deferred_count,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


DiagnosticSink = Callable[[StudyPlanParityReport], None]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_token(value: Any) -> str:
    import re

    text = _clean_text(value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _non_negative_int(value: Any, default: int = 0) -> int:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite():
            return default
        parsed = int(number.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _score(value: Any) -> Optional[float]:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return float(number) if number.is_finite() else None


def _status(value: Any, default: str = "planned") -> str:
    raw = _normalized_token(value)
    allowed = {
        "planned", "proposed", "active", "completed", "done", "skipped",
        "cancelled", "buffer", "study", "weekly_review", "short_review",
    }
    if raw == "done":
        return "completed"
    return raw if raw in allowed else default


def _date_text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()[:10]
        try:
            date.fromisoformat(text)
            return text
        except ValueError:
            pass
    return fallback


def _date_from_timestamp(value: Any, fallback: str = "1970-01-01") -> str:
    text = str(value or "").strip()
    if len(text) >= 10:
        return _date_text(text[:10], fallback)
    return fallback


def _date_add(start: str, offset: int) -> str:
    try:
        return (date.fromisoformat(start) + timedelta(days=offset)).isoformat()
    except ValueError:
        return start


def _max_date(values: Iterable[str], fallback: str) -> str:
    valid = []
    for value in values:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            continue
        valid.append(value)
    return max(valid) if valid else fallback


def _timestamp(value: Any, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _action_from_session(session: Mapping[str, Any], topic: str, fallback: str) -> str:
    raw_actions = session.get("actions")
    actions: List[str] = []
    if isinstance(raw_actions, list):
        actions.extend(_clean_text(item) for item in raw_actions if _clean_text(item))
    elif raw_actions:
        text = _clean_text(raw_actions)
        if text:
            actions.append(text)
    if actions:
        return "; ".join(actions[:4])[:1000]
    if topic:
        return "Study {}".format(topic)
    return fallback


def _plan_key(plan: Mapping[str, Any], source_path: str, index: int, fallback_kind: str) -> str:
    explicit = _clean_text(plan.get("id"))
    if explicit:
        return "plan:id:{}".format(explicit)
    created_at = _clean_text(plan.get("created_at"))
    start = _clean_text(plan.get("start_date") or plan.get("date") or plan.get("starts_on"))
    kind = _clean_text(plan.get("kind")) or fallback_kind
    if created_at or start:
        return "plan:{}:{}:{}:{}".format(kind, created_at, start, index)
    return "plan:{}:{}:{}".format(source_path, fallback_kind, index)


def _plan_kind(source_path: str, plan: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    kind, horizon, engine_name, default_version = _SOURCE_CONFIG[source_path]
    engine_version = _clean_text(plan.get("engine_version")) or default_version
    if source_path == INTELLIGENT_SOURCE_PATH:
        raw = _normalized_token(plan.get("kind")) or "intelligent"
        if raw == "today":
            return "intelligent_today", "day", engine_name, engine_version
        if raw in {"week", "weekly"}:
            return "intelligent_week", "week", engine_name, engine_version
        return "intelligent", "adaptive", engine_name, engine_version
    return kind, horizon, engine_name, engine_version


def _extract_items(
    source_path: str,
    plan: Mapping[str, Any],
    plan_key: str,
    starts_on: str,
) -> Tuple[Dict[str, Any], ...]:
    items: List[Dict[str, Any]] = []
    ordinal = 1

    def append_item(
        *,
        raw: Mapping[str, Any],
        local_key: str,
        plan_date: str,
        raw_course_id: Any = "",
        raw_topic: Any = "",
        minutes: Any = 0,
        action: str = "Study plan item",
        reason: str = "legacy study-plan item",
        score_value: Any = None,
        status_value: Any = "planned",
    ) -> None:
        nonlocal ordinal
        status = _status(status_value, default="planned")
        if status in {"study", "weekly_review", "short_review"}:
            status = "planned"
        items.append(
            {
                "legacy_key": "{}/item:{}".format(plan_key, local_key),
                "plan_legacy_key": plan_key,
                "plan_date": plan_date,
                "ordinal": ordinal,
                "raw_course_id": _clean_text(raw_course_id),
                "raw_topic": _clean_text(raw_topic),
                "minutes": _non_negative_int(minutes, 0),
                "action": _clean_text(action) or "Study plan item",
                "reason": reason,
                "score": _score(score_value),
                "status": status,
                "raw": deepcopy(dict(raw)),
            }
        )
        ordinal += 1

    days = plan.get("days")
    if isinstance(days, list):
        for day_index, raw_day in enumerate(days):
            if not isinstance(raw_day, Mapping):
                continue
            plan_date = _date_text(raw_day.get("date"), _date_add(starts_on, day_index))
            day_minutes = raw_day.get(
                "total_minutes", raw_day.get("available_minutes", raw_day.get("minutes", 0))
            )
            sessions = raw_day.get("sessions")
            if isinstance(sessions, list) and sessions:
                for session_index, raw_session in enumerate(sessions):
                    if not isinstance(raw_session, Mapping):
                        continue
                    topic = raw_session.get("topic")
                    append_item(
                        raw=raw_session,
                        local_key="day:{}:session:{}".format(day_index, session_index),
                        plan_date=plan_date,
                        raw_course_id=raw_session.get("course_id", plan.get("course_id", "")),
                        raw_topic=topic,
                        minutes=raw_session.get("minutes", day_minutes),
                        action=_action_from_session(raw_session, _clean_text(topic), "Study session"),
                        reason="imported from legacy day/session plan",
                        score_value=raw_session.get("score", raw_session.get("priority_score")),
                        status_value=raw_session.get("status", raw_day.get("kind", "planned")),
                    )
            else:
                tasks = raw_day.get("tasks")
                if isinstance(tasks, list) and tasks:
                    total = _non_negative_int(day_minutes, 0)
                    per_task = total // len(tasks)
                    remainder = total % len(tasks)
                    for task_index, task in enumerate(tasks):
                        text = _clean_text(task)
                        append_item(
                            raw={"task": task, "day": deepcopy(dict(raw_day))},
                            local_key="day:{}:task:{}".format(day_index, task_index),
                            plan_date=plan_date,
                            raw_course_id=plan.get("course_id", ""),
                            raw_topic=text,
                            minutes=per_task + (1 if task_index < remainder else 0),
                            action="Study {}".format(text or "planned task"),
                            reason="imported from legacy task-list day",
                        )

    raw_items = plan.get("items")
    if isinstance(raw_items, list) and raw_items:
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, Mapping):
                continue
            topic = raw_item.get("topic", raw_item.get("task", raw_item.get("title", "")))
            append_item(
                raw=raw_item,
                local_key="item:{}".format(index),
                plan_date=_date_text(raw_item.get("date"), starts_on),
                raw_course_id=raw_item.get("course_id", plan.get("course_id", "")),
                raw_topic=topic,
                minutes=raw_item.get("minutes", raw_item.get("allocated_minutes", 0)),
                action=_clean_text(raw_item.get("action")) or "Study {}".format(_clean_text(topic) or "allocated course work"),
                reason="imported from legacy plan item",
                score_value=raw_item.get("score", raw_item.get("priority_score")),
                status_value=raw_item.get("status", "planned"),
            )

    sessions = plan.get("sessions")
    if isinstance(sessions, list) and sessions:
        plan_date = _date_text(plan.get("date"), starts_on)
        for index, raw_session in enumerate(sessions):
            if not isinstance(raw_session, Mapping):
                continue
            topic = raw_session.get("topic")
            append_item(
                raw=raw_session,
                local_key="session:{}".format(index),
                plan_date=plan_date,
                raw_course_id=raw_session.get("course_id", plan.get("course_id", "")),
                raw_topic=topic,
                minutes=raw_session.get("minutes", 0),
                action=_action_from_session(raw_session, _clean_text(topic), "Study session"),
                reason="imported from legacy intelligent daily session",
                score_value=raw_session.get("score", raw_session.get("priority_score")),
                status_value=raw_session.get("status", "planned"),
            )

    return tuple(items)


def _requested_minutes(source_path: str, plan: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> int:
    for field in (
        "requested_minutes", "total_weekly_minutes", "total_minutes",
        "available_minutes", "stored_minutes",
    ):
        if field in plan and plan.get(field) not in (None, ""):
            return _non_negative_int(plan.get(field), sum(int(item["minutes"]) for item in items))
    if "daily_minutes" in plan and "study_days" in plan:
        return _non_negative_int(plan.get("daily_minutes")) * _non_negative_int(plan.get("study_days"))
    if source_path == INTELLIGENT_SOURCE_PATH and "minutes_per_day" in plan and "study_days" in plan:
        return _non_negative_int(plan.get("minutes_per_day")) * _non_negative_int(plan.get("study_days"))
    return sum(int(item["minutes"]) for item in items)


def _source_path_for_repository(repository: Any, source_path: str) -> Path:
    attribute = {
        WEEKLY_SOURCE_PATH: "weekly_path",
        MULTI_SOURCE_PATH: "multi_course_path",
        INTELLIGENT_SOURCE_PATH: "intelligent_path",
    }[source_path]
    return Path(getattr(repository, attribute))


def _source_hash(repository: Any, source_path: str, store: Optional[Mapping[str, Any]]) -> Optional[str]:
    path = _source_path_for_repository(repository, source_path)
    if store is None and not path.exists():
        return None
    if not path.exists():
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_source_projection(
    repository: Any,
    source_path: str,
    store: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    if store is None:
        return {
            "present": False,
            "source_hash": None,
            "source_version": None,
            "raw_plan_evidence": (),
            "plan_rows": (),
            "item_rows": (),
        }
    plans = store.get("plans", []) if isinstance(store, Mapping) else []
    if not isinstance(plans, list):
        plans = []
    fallback_kind = _SOURCE_CONFIG[source_path][0]
    projected_plans: List[Dict[str, Any]] = []
    projected_items: List[Dict[str, Any]] = []
    raw_evidence: List[Dict[str, Any]] = []

    for index, raw_plan in enumerate(plans):
        if not isinstance(raw_plan, Mapping):
            continue
        plan = dict(raw_plan)
        key = _plan_key(plan, source_path, index, fallback_kind)
        kind, horizon, engine_name, engine_version = _plan_kind(source_path, plan)
        created_at = _timestamp(plan.get("created_at"), "1970-01-01T00:00:00")
        starts_on = _date_text(
            plan.get("start_date", plan.get("date", plan.get("starts_on"))),
            _date_from_timestamp(created_at),
        )
        items = _extract_items(source_path, plan, key, starts_on)
        dates = [str(item["plan_date"]) for item in items]
        if horizon == "day":
            ends_on = starts_on
        else:
            ends_on = _date_text(plan.get("end_date", plan.get("ends_on")), "")
            if not ends_on:
                ends_on = _max_date(
                    dates,
                    _date_add(starts_on, 6 if horizon in {"week", "adaptive"} else 0),
                )
        allocated = sum(int(item["minutes"]) for item in items)
        requested = _requested_minutes(source_path, plan, items)
        rationale = _clean_text(
            plan.get("rationale")
            or plan.get("message")
            or plan.get("planner_principle")
            or "legacy study-plan import"
        )
        projected_plans.append(
            {
                "legacy_key": key,
                "kind": kind,
                "horizon": horizon,
                "starts_on": starts_on,
                "ends_on": ends_on,
                "requested_minutes": requested,
                "allocated_minutes": allocated,
                "status": _status(plan.get("status"), default="proposed"),
                "engine_name": engine_name,
                "engine_version": engine_version,
                "rationale": rationale,
                "created_at": created_at,
                "updated_at": _timestamp(plan.get("updated_at"), created_at),
            }
        )
        projected_items.extend(items)
        raw_evidence.append({"legacy_key": key, "raw": deepcopy(plan)})

    return {
        "present": True,
        "source_hash": _source_hash(repository, source_path, store),
        "source_version": store.get("version", 1) if isinstance(store, Mapping) else 1,
        "raw_plan_evidence": tuple(raw_evidence),
        "plan_rows": tuple(projected_plans),
        "item_rows": tuple(projected_items),
    }


def _sqlite_plan_projection(source: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    fields = (
        "legacy_key", "kind", "horizon", "starts_on", "ends_on",
        "requested_minutes", "allocated_minutes", "status", "engine_name",
        "engine_version", "rationale", "created_at", "updated_at",
    )
    return tuple({field: deepcopy(row.get(field)) for field in fields} for row in source.get("plan_rows", ()))


def _sqlite_item_projection(source: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    fields = (
        "legacy_key", "plan_legacy_key", "plan_date", "ordinal",
        "raw_course_id", "raw_topic", "minutes", "action", "reason", "score", "status", "raw",
    )
    return tuple({field: deepcopy(row.get(field)) for field in fields} for row in source.get("item_rows", ()))


def _diagnostic(
    domain: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    source_path: str = "",
    entity_type: str = "",
    key: str = "",
    message: Optional[str] = None,
) -> StudyPlanParityDiagnostic:
    equal = legacy_value == sqlite_value
    return StudyPlanParityDiagnostic(
        domain=domain,
        status="matched" if equal else "mismatch",
        key=key,
        severity="info" if equal else "error",
        legacy_value=deepcopy(legacy_value),
        sqlite_value=deepcopy(sqlite_value),
        message=message or (
            "Legacy and SQLite study-plan semantics match."
            if equal
            else "Legacy and SQLite study-plan semantics differ; the mismatch was not normalized away."
        ),
        source_path=source_path,
        entity_type=entity_type,
    )


def compare_study_plan_parity(
    legacy_repository: Any,
    legacy_state: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_state",
) -> StudyPlanParityReport:
    diagnostics: List[StudyPlanParityDiagnostic] = []
    sqlite_sources = sqlite_snapshot.get("sources", {})

    for source_path, state_key in _SOURCE_TO_STATE_KEY.items():
        legacy_source = _legacy_source_projection(
            legacy_repository,
            source_path,
            legacy_state.get(state_key),
        )
        sqlite_source = sqlite_sources.get(source_path, {})
        diagnostics.extend(
            (
                _diagnostic(
                    "source_presence",
                    legacy_source["present"],
                    sqlite_source.get("present", False),
                    source_path=source_path,
                    entity_type="study_plan_source",
                ),
                _diagnostic(
                    "source_hash",
                    legacy_source["source_hash"],
                    sqlite_source.get("source_hash"),
                    source_path=source_path,
                    entity_type="study_plan_source",
                ),
                _diagnostic(
                    "source_version",
                    legacy_source["source_version"],
                    sqlite_source.get("source_version"),
                    source_path=source_path,
                    entity_type="study_plan_source",
                ),
                _diagnostic(
                    "raw_plan_evidence",
                    legacy_source["raw_plan_evidence"],
                    tuple(sqlite_source.get("raw_plan_evidence", ())),
                    source_path=source_path,
                    entity_type="study_plan",
                    message="Exact stored plan JSON is compared through migration-ledger raw evidence without regenerating a plan.",
                ),
                _diagnostic(
                    "plan_semantics",
                    legacy_source["plan_rows"],
                    _sqlite_plan_projection(sqlite_source),
                    source_path=source_path,
                    entity_type="study_plan",
                    message="Plan kind/horizon/dates/minutes/status/engine/rationale/timestamps are compared against persisted SQLite rows.",
                ),
                _diagnostic(
                    "plan_item_semantics",
                    legacy_source["item_rows"],
                    _sqlite_item_projection(sqlite_source),
                    source_path=source_path,
                    entity_type="study_plan_item",
                    message="Plan item order/date/course/topic raw identity/minutes/action/reason/score/status are compared without rerunning planner engines.",
                ),
            )
        )

        anomalies = tuple(sqlite_source.get("anomalies", ()))
        diagnostics.append(
            StudyPlanParityDiagnostic(
                domain="sqlite_structure",
                status="matched" if not anomalies else "mismatch",
                key="",
                severity="info" if not anomalies else "error",
                legacy_value=(),
                sqlite_value=anomalies,
                message=(
                    "Study-plan/item ownership and course/topic relationships are structurally valid."
                    if not anomalies
                    else "SQLite study-plan structural anomalies were detected explicitly."
                ),
                source_path=source_path,
                entity_type="study_plan_structure",
            )
        )

        historical = tuple(sqlite_source.get("historical_plan_rows", ())) + tuple(
            sqlite_source.get("historical_item_rows", ())
        )
        if historical:
            diagnostics.append(
                StudyPlanParityDiagnostic(
                    domain="historical_rows",
                    status="deferred",
                    key="",
                    severity="info",
                    legacy_value="current legacy snapshot is not deletion authority",
                    sqlite_value=historical,
                    message="Rows evidenced only by older source hashes are retained as historical plan evidence rather than promoted to current authority.",
                    source_path=source_path,
                    entity_type="study_plan_history",
                )
            )

    global_anomalies = tuple(sqlite_snapshot.get("global_anomalies", ()))
    diagnostics.append(
        StudyPlanParityDiagnostic(
            domain="sqlite_global_structure",
            status="matched" if not global_anomalies else "mismatch",
            key="",
            severity="info" if not global_anomalies else "error",
            legacy_value=(),
            sqlite_value=global_anomalies,
            message=(
                "All live study plans/items are backed by supported migration evidence."
                if not global_anomalies
                else "Unledgered live study-plan rows were detected."
            ),
            entity_type="study_plan_structure",
        )
    )

    return StudyPlanParityReport(operation=operation, diagnostics=tuple(diagnostics))


class DualReadStudyPlanRepository:
    """Return exact legacy state while independently observing SQLite parity."""

    def __init__(
        self,
        legacy_repository: Any,
        sqlite_repository: SQLiteStudyPlanRepository,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ) -> None:
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._diagnostic_sink = diagnostic_sink
        self._reports: List[StudyPlanParityReport] = []

    @property
    def last_report(self) -> Optional[StudyPlanParityReport]:
        return self._reports[-1] if self._reports else None

    @property
    def reports(self) -> Tuple[StudyPlanParityReport, ...]:
        return tuple(self._reports)

    def _record(self, report: StudyPlanParityReport) -> None:
        self._reports.append(report)
        if self._diagnostic_sink is not None:
            try:
                self._diagnostic_sink(report)
            except Exception:
                # Diagnostics are observational and must not break legacy reads.
                pass

    def load_state(self):
        legacy_state = self.legacy_repository.load_state()
        try:
            snapshot = self.sqlite_repository.parity_snapshot()
            report = compare_study_plan_parity(
                self.legacy_repository,
                legacy_state,
                snapshot,
                operation="load_state",
            )
            self._record(report)
        except Exception as error:
            self._record(
                StudyPlanParityReport(
                    operation="load_state",
                    diagnostics=(
                        StudyPlanParityDiagnostic(
                            domain="sqlite_read",
                            status="error",
                            key="",
                            severity="error",
                            legacy_value="authoritative legacy result returned",
                            sqlite_value=type(error).__name__,
                            message="SQLite study-plan shadow read failed: {}".format(error),
                            entity_type="study_plan_shadow",
                        ),
                    ),
                )
            )
        return deepcopy(legacy_state)

    def load_weekly_store(self):
        return deepcopy(self.load_state()["weekly"])

    def load_multi_course_store(self):
        return deepcopy(self.load_state()["multi_course"])

    def load_intelligent_store(self):
        return deepcopy(self.load_state()["intelligent"])

    def save_state(self, state):
        return self.legacy_repository.save_state(state)

    def save_weekly_store(self, value):
        return self.legacy_repository.save_weekly_store(value)

    def save_multi_course_store(self, value):
        return self.legacy_repository.save_multi_course_store(value)

    def save_intelligent_store(self, value):
        return self.legacy_repository.save_intelligent_store(value)


def build_study_plan_repository(
    config: Union[StudyPlanBackendConfig, str] = StudyPlanBackendConfig(),
    *,
    legacy_repository: Optional[Any] = None,
    weekly_path: Optional[Union[str, Path]] = None,
    multi_course_path: Optional[Union[str, Path]] = None,
    intelligent_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteStudyPlanRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    selected = config if isinstance(config, StudyPlanBackendConfig) else StudyPlanBackendConfig(config)
    if legacy_repository is None:
        kwargs: Dict[str, Any] = {}
        if weekly_path is not None:
            kwargs["weekly_path"] = weekly_path
        if multi_course_path is not None:
            kwargs["multi_course_path"] = multi_course_path
        if intelligent_path is not None:
            kwargs["intelligent_path"] = intelligent_path
        legacy_repository = LegacyJsonStudyPlanRepository(**kwargs)
    if selected.mode == "legacy":
        return legacy_repository
    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteStudyPlanRepository(sqlite_connection)
    return DualReadStudyPlanRepository(
        legacy_repository,
        shadow,
        diagnostic_sink=diagnostic_sink,
    )


create_study_plan_repository = build_study_plan_repository


__all__ = (
    "DualReadStudyPlanRepository",
    "StudyPlanBackendConfig",
    "StudyPlanParityDiagnostic",
    "StudyPlanParityReport",
    "build_study_plan_repository",
    "compare_study_plan_parity",
    "create_study_plan_repository",
)
