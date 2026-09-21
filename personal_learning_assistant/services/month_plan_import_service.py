"""Safe structured monthly-plan import for the Phase 7.5.13 Operational Planner."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import yaml

from personal_learning_assistant.repositories.sqlite.month_plan_import_repository import (
    MonthPlanImportRepositoryError,
    SQLiteMonthPlanImportRepository,
)


SCHEMA_VERSION = "anvaya.external.month_plan/1.0.0"
MAX_YAML_BYTES = 2_000_000
MAX_ITEMS = 1000
MAX_TITLE = 300
_NAMESPACE = uuid.UUID("65fc79ac-c878-5e27-b281-e783f5012e0f")
_SUPPORTED_RRULE = {"FREQ", "BYDAY", "UNTIL", "COUNT"}
_WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


class MonthPlanImportError(RuntimeError):
    """Base safe month-plan import error."""


class MonthPlanImportValidationError(MonthPlanImportError):
    """The uploaded month plan is malformed or violates the supported schema."""


class MonthPlanImportConflictError(MonthPlanImportError):
    """An import would overwrite user-owned operational state."""


class MonthPlanImportUnavailableError(MonthPlanImportError):
    """Planner storage is not currently available."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _date(value, *, field: str, allow_none: bool = False):
    if value in (None, "") and allow_none:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as error:
        raise MonthPlanImportValidationError(
            "{} must be YYYY-MM-DD.".format(field)
        ) from error


def _time(value, *, field: str, allow_none: bool = True):
    if value in (None, "") and allow_none:
        return None
    try:
        return datetime.strptime(str(value), "%H:%M").strftime("%H:%M")
    except (TypeError, ValueError) as error:
        raise MonthPlanImportValidationError(
            "{} must be HH:MM.".format(field)
        ) from error


def _text(value, *, field: str, required: bool = False, limit: int = MAX_TITLE):
    text = str(value or "").strip()
    if required and not text:
        raise MonthPlanImportValidationError("{} is required.".format(field))
    if len(text) > limit:
        raise MonthPlanImportValidationError("{} is too long.".format(field))
    return text


def _int(value, *, field: str, minimum=0, allow_none=True):
    if value in (None, "") and allow_none:
        return None
    if isinstance(value, bool):
        raise MonthPlanImportValidationError("{} must be an integer.".format(field))
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise MonthPlanImportValidationError("{} must be an integer.".format(field)) from error
    if result < minimum:
        raise MonthPlanImportValidationError("{} is outside the accepted range.".format(field))
    return result


def _priority(value, *, field="priority"):
    token = str(value or "P1").strip().upper()
    if token not in {"P0", "P1", "P2"}:
        raise MonthPlanImportValidationError("{} must be P0, P1, or P2.".format(field))
    return token


def _stable_id(plan_id: str, external_id: str, kind: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, "{}\0{}\0{}".format(plan_id, external_id, kind)))


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("Unsupported provenance value: {}".format(type(value).__name__))


def _source_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_rrule(value: str) -> dict[str, Any]:
    raw = _text(value, field="recurrence_rule", required=True, limit=300)
    if raw.startswith("RRULE:"):
        raw = raw[6:]
    parts = {}
    for pair in raw.split(";"):
        if "=" not in pair:
            raise MonthPlanImportValidationError("Recurrence rule is malformed.")
        key, item = pair.split("=", 1)
        key = key.strip().upper()
        if key not in _SUPPORTED_RRULE:
            raise MonthPlanImportValidationError(
                "Unsupported recurrence component: {}".format(key)
            )
        if key in parts:
            raise MonthPlanImportValidationError(
                "Duplicate recurrence component: {}".format(key)
            )
        parts[key] = item.strip().upper()
    if parts.get("FREQ") not in {"DAILY", "WEEKLY"}:
        raise MonthPlanImportValidationError("Only DAILY and WEEKLY recurrence are supported.")
    if parts["FREQ"] == "WEEKLY":
        days = tuple(x for x in parts.get("BYDAY", "").split(",") if x)
        if not days or any(day not in _WEEKDAY for day in days):
            raise MonthPlanImportValidationError("Weekly recurrence requires valid BYDAY values.")
        parts["BYDAY"] = days
    elif "BYDAY" in parts:
        raise MonthPlanImportValidationError("BYDAY is supported only for WEEKLY recurrence.")
    if "UNTIL" in parts:
        try:
            parts["UNTIL"] = datetime.strptime(parts["UNTIL"], "%Y%m%d").date()
        except ValueError as error:
            raise MonthPlanImportValidationError("RRULE UNTIL must be YYYYMMDD.") from error
    if "COUNT" in parts:
        try:
            count = int(parts["COUNT"])
        except ValueError as error:
            raise MonthPlanImportValidationError("RRULE COUNT must be an integer.") from error
        if count < 1 or count > 366:
            raise MonthPlanImportValidationError("RRULE COUNT is outside the accepted range.")
        parts["COUNT"] = count
    return parts


def _first_occurrence(start: date, end: date, rule: dict[str, Any], active_from=None):
    current = max(start, active_from or start)
    count = 0
    while current <= end:
        if rule.get("UNTIL") and current > rule["UNTIL"]:
            break
        matches = rule["FREQ"] == "DAILY" or current.weekday() in {
            _WEEKDAY[d] for d in rule.get("BYDAY", ())
        }
        if matches:
            count += 1
            return current
        current += timedelta(days=1)
    return None


def _within(value: date | None, start: date, end: date, *, field: str):
    if value is not None and not start <= value <= end:
        raise MonthPlanImportValidationError(
            "{} is outside the declared plan range.".format(field)
        )


class MonthPlanImportService:
    def __init__(self, repository, *, now=_utc_now):
        self.repository = repository
        self._now = now

    def _course(self, code, errors):
        if not code:
            return None
        row = self.repository.course_by_code(str(code).strip())
        if row is None:
            errors.append("Unknown exact course code: {}".format(str(code).strip()))
            return None
        return row

    def _normalize(self, document: dict[str, Any], filename: str, source_sha256: str):
        errors, warnings = [], []
        if document.get("schema_version") != SCHEMA_VERSION:
            errors.append("Unsupported schema_version.")
        plan_id = _text(document.get("plan_id"), field="plan_id", required=True)
        date_range = document.get("date_range")
        if not isinstance(date_range, dict):
            raise MonthPlanImportValidationError("date_range must be an object.")
        starts = _date(date_range.get("start"), field="date_range.start")
        ends = _date(date_range.get("end"), field="date_range.end")
        if ends < starts:
            errors.append("date_range.end must be on or after date_range.start.")
        title = _text(
            (document.get("plan_metadata") or {}).get("title"),
            field="plan_metadata.title",
            required=True,
        )
        timezone_name = _text(document.get("timezone"), field="timezone", required=True)
        official_datesheet = bool(
            (document.get("exam_schedule") or {}).get("official_datesheet_received", False)
        )

        normalized = {
            "plan_id": plan_id,
            "schema_version": document.get("schema_version"),
            "source_filename": filename,
            "source_sha256": source_sha256,
            "title": title,
            "starts_on": starts.isoformat(),
            "ends_on": ends.isoformat(),
            "timezone": timezone_name,
            "official_datesheet_received": official_datesheet,
            "assessments": [],
            "events": [],
            "routines": [],
            "tasks": [],
            "weekly_reviews": [],
            "settings": {
                "rollover": document.get("rollover_policy") or {},
                "buffers": document.get("buffer_recovery_rules") or {},
                "daily_review": document.get("daily_review_settings") or {},
            },
        }
        seen = set()

        def unique(external_id):
            if external_id in seen:
                errors.append("Duplicate external id: {}".format(external_id))
                return False
            seen.add(external_id)
            return True

        assessments = document.get("assessments") or []
        if not isinstance(assessments, list):
            errors.append("assessments must be a list.")
            assessments = []
        for raw in assessments[:MAX_ITEMS]:
            if not isinstance(raw, dict):
                errors.append("Assessment entries must be objects.")
                continue
            ext = _text(raw.get("id"), field="assessment.id", required=True)
            if not unique(ext):
                continue
            course = self._course(raw.get("course"), errors)
            due = _date(raw.get("due_on"), field="assessment.due_on", allow_none=True)
            start_time = _time(raw.get("start_time"), field="assessment.start_time")
            end_time = _time(raw.get("end_time"), field="assessment.end_time")
            if not official_datesheet and any((due, start_time, end_time, raw.get("location"))):
                errors.append(
                    "{} supplies a subject exam slot before the official datesheet.".format(ext)
                )
            _within(due, starts, ends, field="assessment.due_on")
            normalized["assessments"].append({
                "external_id": ext,
                "id": _stable_id(plan_id, ext, "assessment"),
                "title": _text(raw.get("title"), field="assessment.title", required=True),
                "description": _text(raw.get("description"), field="assessment.description", limit=4000),
                "course_id": None if course is None else course["id"],
                "course_code": _text(raw.get("course"), field="assessment.course"),
                "assessment_type": "mid_semester" if "mid" in str(raw.get("title","")).lower() else "assessment",
                "due_on": None if due is None else due.isoformat(),
                "due_time": start_time,
                "location": _text(raw.get("location"), field="assessment.location", limit=500),
                "priority": _priority(raw.get("priority")),
                "raw": raw,
            })

        fixed_events = document.get("fixed_events") or []
        if not isinstance(fixed_events, list):
            errors.append("fixed_events must be a list.")
            fixed_events = []
        for raw in fixed_events[:MAX_ITEMS]:
            if not isinstance(raw, dict):
                errors.append("fixed_events entries must be objects.")
                continue
            ext = _text(raw.get("id"), field="fixed_event.id", required=True)
            if not unique(ext):
                continue
            event_date = _date(raw.get("date"), field="fixed_event.date")
            end_date = _date(raw.get("end_date"), field="fixed_event.end_date", allow_none=True)
            _within(event_date, starts, ends, field="fixed_event.date")
            _within(end_date, starts, ends, field="fixed_event.end_date")
            course = self._course(raw.get("course"), errors)
            normalized["events"].append({
                "external_id": ext,
                "id": _stable_id(plan_id, ext, "academic_event"),
                "title": _text(raw.get("title"), field="fixed_event.title", required=True),
                "course_id": None if course is None else course["id"],
                "event_kind": _text(raw.get("type"), field="fixed_event.type", required=True),
                "date": event_date.isoformat(),
                "end_date": None if end_date is None else end_date.isoformat(),
                "start_time": _time(raw.get("start_time"), field="fixed_event.start_time"),
                "end_time": _time(raw.get("end_time"), field="fixed_event.end_time"),
                "recurrence_rule": None,
                "all_day": not bool(raw.get("start_time")),
                "excluded_dates": [],
                "additional_dates": [],
                "raw": raw,
            })

        routines = document.get("recurring_routines") or {}
        class_table = routines.get("class_timetable") if isinstance(routines, dict) else {}
        class_entries = (class_table or {}).get("entries") or []
        personal_entries = (routines or {}).get("personal_routines") or []
        for source_kind, entries in (("class", class_entries), ("routine", personal_entries)):
            if not isinstance(entries, list):
                errors.append("{} recurrence entries must be a list.".format(source_kind))
                continue
            for raw in entries[:MAX_ITEMS]:
                if not isinstance(raw, dict):
                    errors.append("Recurring entries must be objects.")
                    continue
                ext = _text(raw.get("id"), field="routine.id", required=True)
                if not unique(ext):
                    continue
                try:
                    rule = parse_rrule(raw.get("recurrence_rule"))
                except MonthPlanImportValidationError as error:
                    errors.append("{}: {}".format(ext, error))
                    continue
                active_from = _date(raw.get("active_from"), field="routine.active_from", allow_none=True)
                if active_from is None:
                    active_from = starts
                first = _first_occurrence(starts, ends, rule, active_from)
                if first is None:
                    warnings.append("{} has no occurrence inside the plan range.".format(ext))
                    continue
                course = self._course(raw.get("course"), errors)
                base = {
                    "external_id": ext,
                    "id": _stable_id(plan_id, ext, "academic_event" if source_kind == "class" else "routine"),
                    "title": _text(raw.get("title"), field="routine.title", required=True),
                    "course_id": None if course is None else course["id"],
                    "priority": _priority(raw.get("priority")),
                    "recurrence_rule": str(raw.get("recurrence_rule")),
                    "active_from": active_from.isoformat(),
                    "active_to": ends.isoformat(),
                    "start_time": _time(raw.get("start_time"), field="routine.start_time"),
                    "end_time": _time(raw.get("end_time"), field="routine.end_time"),
                    "duration_minutes": _int(
                        raw.get("duration_minutes", raw.get("estimated_minutes")),
                        field="routine.duration_minutes",
                    ),
                    "preferred_window": _text(raw.get("preferred_window"), field="routine.preferred_window", limit=500),
                    "preferred_location": _text(raw.get("preferred_location", raw.get("location")), field="routine.location", limit=500),
                    "condition_text": _text(raw.get("condition", raw.get("skip_rule")), field="routine.condition", limit=1000),
                    "excluded_dates": tuple(str(x) for x in (raw.get("excluded_dates") or [])),
                    "additional_dates": tuple(str(x) for x in (raw.get("additional_dates") or [])),
                    "first_date": first.isoformat(),
                    "raw": raw,
                }
                for label, dates in (("excluded_dates", base["excluded_dates"]), ("additional_dates", base["additional_dates"])):
                    for item in dates:
                        parsed = _date(item, field="routine.{}".format(label))
                        _within(parsed, starts, ends, field="routine.{}".format(label))
                if source_kind == "class":
                    base["event_kind"] = "class"
                    normalized["events"].append(base)
                else:
                    normalized["routines"].append(base)

        task_sources = []
        flex = document.get("flexible_tasks") or {}
        if isinstance(flex, dict):
            task_sources.extend(flex.get("tasks") or [])
        task_sources.extend(document.get("planned_blocks") or [])
        for raw in task_sources[:MAX_ITEMS]:
            if not isinstance(raw, dict):
                errors.append("Task entries must be objects.")
                continue
            ext = _text(raw.get("id"), field="task.id", required=True)
            if not unique(ext):
                continue
            course = self._course(raw.get("course"), errors)
            due = _date(raw.get("due_on"), field="task.due_on", allow_none=True)
            _within(due, starts, ends, field="task.due_on")
            status = str(raw.get("status") or "backlog").strip()
            if status in {"blocked_by_missing_information", "planned"}:
                mapped_status = "planned" if status == "planned" else "backlog"
            else:
                mapped_status = status if status in {"backlog","planned","scheduled"} else "backlog"
            normalized["tasks"].append({
                "external_id": ext,
                "id": _stable_id(plan_id, ext, "task"),
                "title": _text(raw.get("title"), field="task.title", required=True),
                "description": _text(raw.get("description"), field="task.description", limit=4000),
                "priority": _priority(raw.get("priority")),
                "course_id": None if course is None else course["id"],
                "course_code": _text(raw.get("course"), field="task.course"),
                "estimated_minutes": _int(raw.get("estimated_minutes"), field="task.estimated_minutes"),
                "due_on": None if due is None else due.isoformat(),
                "preferred_day": _text(raw.get("preferred_day"), field="task.preferred_day", limit=500),
                "preferred_window": _text(raw.get("preferred_window"), field="task.preferred_window", limit=500),
                "rollover_policy": _text(raw.get("rollover"), field="task.rollover", limit=1000),
                "status": mapped_status,
                "raw": raw,
            })

        reviews = document.get("weekly_reviews") or {}
        for raw_date in (reviews.get("review_dates") if isinstance(reviews, dict) else []) or []:
            d = _date(raw_date, field="weekly_review.date")
            _within(d, starts, ends, field="weekly_review.date")
            normalized["weekly_reviews"].append(d.isoformat())

        if len(seen) > MAX_ITEMS:
            errors.append("The plan contains too many operational items.")
        return normalized, errors, warnings

    def preview(self, filename: str, payload: bytes):
        if not isinstance(payload, (bytes, bytearray)):
            raise MonthPlanImportValidationError("The uploaded plan must be bytes.")
        if len(payload) > MAX_YAML_BYTES:
            raise MonthPlanImportValidationError("The uploaded YAML is too large.")
        try:
            text = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as error:
            raise MonthPlanImportValidationError("The YAML must be UTF-8.") from error
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise MonthPlanImportValidationError("The YAML could not be parsed safely.") from error
        if not isinstance(document, dict):
            raise MonthPlanImportValidationError("The YAML root must be an object.")
        source_sha256 = hashlib.sha256(bytes(payload)).hexdigest()
        normalized, errors, warnings = self._normalize(
            document, _text(filename, field="filename", required=True, limit=255), source_sha256
        )
        existing = None
        active = None
        try:
            existing = self.repository.find_by_hash(source_sha256)
            active = self.repository.active_import(normalized["plan_id"])
        except MonthPlanImportRepositoryError as error:
            raise MonthPlanImportUnavailableError(
                "Operational planner storage is unavailable."
            ) from error
        if existing:
            warnings.append("This exact source hash is already imported; approval will be a no-op.")
        waiting = tuple(
            item["external_id"]
            for item in normalized["assessments"]
            if item["due_on"] is None
        )
        counts = {
            "days": (
                _date(normalized["ends_on"], field="ends_on")
                - _date(normalized["starts_on"], field="starts_on")
            ).days + 1,
            "assessments": len(normalized["assessments"]),
            "fixed_and_class_events": len(normalized["events"]),
            "personal_routines": len(normalized["routines"]),
            "tasks": len(normalized["tasks"]),
            "weekly_reviews": len(normalized["weekly_reviews"]),
        }
        return {
            "valid": not errors,
            "source_sha256": source_sha256,
            "filename": filename,
            "plan": normalized,
            "counts": counts,
            "waiting_exam_slots": waiting,
            "warnings": tuple(warnings),
            "errors": tuple(errors),
            "already_imported": bool(existing),
            "active_import": active,
            "preview_token": source_sha256,
        }

    def approve(self, filename: str, payload: bytes, expected_sha256: str):
        preview = self.preview(filename, payload)
        if not preview["valid"]:
            raise MonthPlanImportValidationError("The month plan preview contains validation errors.")
        if preview["source_sha256"] != str(expected_sha256 or "").strip().lower():
            raise MonthPlanImportConflictError("The uploaded plan changed after preview.")
        if preview["already_imported"]:
            return {
                "created": False,
                "idempotent": True,
                "import": self.repository.find_by_hash(preview["source_sha256"]),
            }
        plan = preview["plan"]
        now = self._now()
        import_id = _stable_id(plan["plan_id"], plan["source_sha256"], "import")
        bundle = {
            "import": {
                "id": import_id,
                "plan_id": plan["plan_id"],
                "schema_version": plan["schema_version"],
                "source_filename": plan["source_filename"],
                "source_sha256": plan["source_sha256"],
                "title": plan["title"],
                "starts_on": plan["starts_on"],
                "ends_on": plan["ends_on"],
                "timezone": plan["timezone"],
                "created_at": now,
                "approved_at": now,
            },
            "assessments": [],
            "events": [],
            "routines": [],
            "tasks": [],
            "ledger": [],
        }
        for item in plan["assessments"]:
            row = dict(item)
            row["source_import_id"] = import_id
            row["created_at"] = now
            row["updated_at"] = now
            bundle["assessments"].append(row)
        for item in plan["events"]:
            row = dict(item)
            row["source_import_id"] = import_id
            row["created_at"] = now
            row["updated_at"] = now
            bundle["events"].append(row)
        for item in plan["routines"]:
            row = dict(item)
            row["source_import_id"] = import_id
            row["created_at"] = now
            row["updated_at"] = now
            bundle["routines"].append(row)
        for item in plan["tasks"]:
            row = dict(item)
            row["source_import_id"] = import_id
            row["created_at"] = now
            row["updated_at"] = now
            bundle["tasks"].append(row)

        for kind in ("assessments", "events", "routines", "tasks"):
            entity_type = {
                "assessments": "assessment",
                "events": "academic_event",
                "routines": "routine",
                "tasks": "task",
            }[kind]
            for row in bundle[kind]:
                details = {
                    "excluded_dates": list(row.get("excluded_dates") or ()),
                    "additional_dates": list(row.get("additional_dates") or ()),
                    "raw": row.get("raw") or {},
                }
                bundle["ledger"].append({
                    "id": _stable_id(plan["plan_id"], row["external_id"], "ledger:" + entity_type),
                    "external_id": row["external_id"],
                    "entity_type": entity_type,
                    "entity_id": row["id"],
                    "source_hash": _source_hash(row.get("raw") or row),
                    "entity_snapshot_hash": "",
                    "details_json": json.dumps(
                        details,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=_json_default,
                    ),
                    "created_at": now,
                    "updated_at": now,
                })
        try:
            saved = self.repository.approve_bundle(bundle)
        except MonthPlanImportRepositoryError as error:
            text = str(error)
            if "manual" in text.lower() or "conflict" in text.lower():
                raise MonthPlanImportConflictError(
                    "The import conflicts with manually changed planner data."
                ) from error
            raise MonthPlanImportUnavailableError(
                "The month plan could not be approved atomically."
            ) from error
        return {"created": True, "idempotent": False, "import": saved}


def build_month_plan_import_service(database_path="data/learning_assistant.db"):
    return MonthPlanImportService(SQLiteMonthPlanImportRepository(database_path))
