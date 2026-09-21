"""Month/week/day operational calendar and supported recurrence materialization."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
    OperationalCalendarRepositoryError,
    OperationalCalendarRepositoryNotFoundError,
    SQLiteOperationalCalendarRepository,
)
from personal_learning_assistant.services.month_plan_import_service import (
    MonthPlanImportValidationError,
    parse_rrule,
)


_WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


class OperationalCalendarError(RuntimeError):
    """Base safe operational-calendar error."""


class OperationalCalendarValidationError(OperationalCalendarError):
    """Calendar request is invalid."""


class OperationalCalendarConflictError(OperationalCalendarError):
    """Calendar write conflicts with an existing fixed commitment."""


class OperationalCalendarNotFoundError(OperationalCalendarError):
    """Calendar/assessment item was not found."""


class OperationalCalendarUnavailableError(OperationalCalendarError):
    """Calendar persistence is unavailable."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as error:
        raise OperationalCalendarValidationError("Date must be YYYY-MM-DD.") from error


def _iso_dt(d: date, hm: str | None):
    return d.isoformat() + "T" + (str(hm or "00:00")) + ":00"


def _time_minutes(value):
    if not value:
        return None
    try:
        parsed = datetime.strptime(str(value), "%H:%M").time()
    except ValueError:
        try:
            parsed = datetime.fromisoformat(str(value)).time()
        except ValueError:
            return None
    return parsed.hour * 60 + parsed.minute


def _event_time_parts(item):
    raw = str(item.get("starts_at") or "")
    try:
        parsed = datetime.fromisoformat(raw)
        start = parsed.strftime("%H:%M")
    except ValueError:
        start = ""
    raw_end = str(item.get("ends_at") or "")
    try:
        parsed_end = datetime.fromisoformat(raw_end)
        end = parsed_end.strftime("%H:%M")
    except ValueError:
        end = ""
    return start, end


def _decode_dates(raw):
    if isinstance(raw, (tuple, list)):
        return {str(x) for x in raw}
    try:
        value = json.loads(str(raw or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    return {str(x) for x in value if isinstance(x, str)}


def _optional_date(value):
    text = str(value or "").strip()
    return None if not text else _parse_date(text).isoformat()


def _clean_time(value, *, label):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError as error:
        raise OperationalCalendarValidationError(
            "{} must be HH:MM.".format(label)
        ) from error
    return text


def _duration(value):
    if value in (None, ""):
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError) as error:
        raise OperationalCalendarValidationError(
            "Duration must be an integer number of minutes."
        ) from error
    if minutes < 0 or minutes > 1440:
        raise OperationalCalendarValidationError(
            "Duration is outside the accepted range."
        )
    return minutes


def _routine_rule(frequency, weekdays, active_to):
    token = str(frequency or "weekly").strip().lower()
    if token not in {"daily", "weekly"}:
        raise OperationalCalendarValidationError(
            "Routine frequency must be daily or weekly."
        )
    parts = ["RRULE:FREQ={}".format(token.upper())]
    if token == "weekly":
        days = tuple(
            dict.fromkeys(
                str(day or "").strip().upper()
                for day in tuple(weekdays or ())
                if str(day or "").strip()
            )
        )
        if not days or any(day not in _WEEKDAY for day in days):
            raise OperationalCalendarValidationError(
                "Choose at least one valid weekday for a weekly routine."
            )
        parts.append("BYDAY=" + ",".join(days))
    if active_to:
        end = _parse_date(active_to)
        parts.append("UNTIL=" + end.strftime("%Y%m%d"))
    rule = ";".join(parts)
    try:
        parse_rrule(rule)
    except MonthPlanImportValidationError as error:
        raise OperationalCalendarValidationError(str(error)) from error
    return rule


def materialize_occurrences(
    *,
    recurrence_rule,
    first_date,
    window_start,
    window_end,
    active_from=None,
    active_to=None,
    excluded_dates=(),
    additional_dates=(),
):
    start = max(_parse_date(first_date), _parse_date(window_start))
    end = _parse_date(window_end)
    if active_from:
        start = max(start, _parse_date(active_from))
    if active_to:
        end = min(end, _parse_date(active_to))
    if end < start:
        return ()
    try:
        rule = parse_rrule(recurrence_rule)
    except MonthPlanImportValidationError as error:
        raise OperationalCalendarValidationError(str(error)) from error
    excluded = {str(x) for x in excluded_dates}
    additional = {
        _parse_date(x)
        for x in additional_dates
        if window_start <= str(x) <= window_end
    }
    result = []
    seen_count = 0
    current = start
    while current <= end:
        if rule.get("UNTIL") and current > rule["UNTIL"]:
            break
        match = (
            rule["FREQ"] == "DAILY"
            or current.weekday() in {_WEEKDAY[x] for x in rule.get("BYDAY", ())}
        )
        if match:
            seen_count += 1
            if rule.get("COUNT") and seen_count > rule["COUNT"]:
                break
            if current.isoformat() not in excluded:
                result.append(current)
        current += timedelta(days=1)
    result.extend(additional)
    return tuple(sorted(set(result)))


class OperationalCalendarService:
    def __init__(self, repository, *, now=_now, id_factory=uuid.uuid4):
        self.repository = repository
        self._now = now
        self._id_factory = id_factory

    def _event_occurrences(self, start: date, end: date):
        try:
            rows = self.repository.list_academic_events(start.isoformat(), end.isoformat())
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "Operational calendar is temporarily unavailable."
            ) from error
        items = []
        for row in rows:
            start_day = str(row["starts_at"])[:10]
            details = row.get("import_details") or {}
            if row.get("recurrence_rule"):
                dates = materialize_occurrences(
                    recurrence_rule=row["recurrence_rule"],
                    first_date=start_day,
                    window_start=start.isoformat(),
                    window_end=end.isoformat(),
                    active_from=start_day,
                    excluded_dates=details.get("excluded_dates") or (),
                    additional_dates=details.get("additional_dates") or (),
                )
            else:
                d = _parse_date(start_day)
                dates = (d,) if start <= d <= end else ()
            for d in dates:
                start_time, end_time = _event_time_parts(row)
                items.append({
                    "id": row["id"],
                    "source": "academic_event",
                    "date": d.isoformat(),
                    "title": row["title"],
                    "kind": row["event_kind"],
                    "course_id": row.get("course_id"),
                    "priority": "P0" if row["event_kind"] in {"class","lab","assessment","official_holiday"} else None,
                    "start_time": "" if int(row.get("all_day") or 0) else start_time,
                    "end_time": "" if int(row.get("all_day") or 0) else end_time,
                    "all_day": bool(row.get("all_day")),
                })
        return items

    def _task_occurrences(self, start: date, end: date):
        try:
            rows = self.repository.list_planner_tasks(
                start.isoformat(), end.isoformat()
            )
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "Operational calendar is temporarily unavailable."
            ) from error
        items = []
        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "source": "task",
                    "date": str(row["due_on"]),
                    "title": row["title"],
                    "kind": "task",
                    "priority": row.get("priority"),
                    "start_time": "",
                    "end_time": "",
                    "preferred_window": row.get("preferred_window") or "",
                    "all_day": True,
                }
            )
        return items

    def _routine_occurrences(self, start: date, end: date):
        try:
            routines = self.repository.list_routines()
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "Operational calendar is temporarily unavailable."
            ) from error
        items = []
        for row in routines:
            first = row.get("active_from") or start.isoformat()
            dates = materialize_occurrences(
                recurrence_rule=row["recurrence_rule"],
                first_date=first,
                window_start=start.isoformat(),
                window_end=end.isoformat(),
                active_from=row.get("active_from"),
                active_to=row.get("active_to"),
                excluded_dates=_decode_dates(row.get("excluded_dates_json")),
                additional_dates=_decode_dates(row.get("additional_dates_json")),
            )
            for d in dates:
                items.append({
                    "id": row["id"],
                    "source": "routine",
                    "date": d.isoformat(),
                    "title": row["title"],
                    "kind": row.get("category") or "routine",
                    "priority": row.get("priority"),
                    "start_time": row.get("start_time") or "",
                    "end_time": row.get("end_time") or "",
                    "duration_minutes": row.get("duration_minutes"),
                    "preferred_window": row.get("preferred_window") or "",
                    "condition_text": row.get("condition_text") or "",
                    "all_day": False,
                })
        return items

    def _agenda_occurrences(self, start: date, end: date):
        try:
            rows = self.repository.list_daily_agenda_items(
                start.isoformat(), end.isoformat()
            )
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "Operational calendar is temporarily unavailable."
            ) from error
        items = []
        for row in rows:
            start_time, end_time = _event_time_parts(row)
            items.append(
                {
                    "id": row["id"],
                    "source": "daily_agenda",
                    "date": str(row["agenda_date"]),
                    "title": row["title"],
                    "kind": "agenda_" + str(row.get("item_kind") or "item"),
                    "priority": row.get("priority"),
                    "start_time": start_time,
                    "end_time": end_time,
                    "planned_minutes": row.get("planned_minutes"),
                    "agenda_status": row.get("agenda_status"),
                    "item_status": row.get("item_status"),
                    "all_day": not bool(start_time),
                }
            )
        return items

    def _range(self, anchor: date, view: str):
        if view == "day":
            return anchor, anchor
        if view == "week":
            start = anchor - timedelta(days=anchor.weekday())
            return start, start + timedelta(days=6)
        if view == "month":
            start = anchor.replace(day=1)
            if start.month == 12:
                next_month = start.replace(year=start.year + 1, month=1)
            else:
                next_month = start.replace(month=start.month + 1)
            return start, next_month - timedelta(days=1)
        raise OperationalCalendarValidationError("Calendar view must be month, week, or day.")

    @staticmethod
    def _navigation(anchor: date, view: str):
        if view == "day":
            return anchor - timedelta(days=1), anchor + timedelta(days=1)
        if view == "week":
            return anchor - timedelta(days=7), anchor + timedelta(days=7)
        if view == "month":
            current = anchor.replace(day=1)
            previous = (
                current.replace(year=current.year - 1, month=12)
                if current.month == 1
                else current.replace(month=current.month - 1)
            )
            following = (
                current.replace(year=current.year + 1, month=1)
                if current.month == 12
                else current.replace(month=current.month + 1)
            )
            return previous, following
        raise OperationalCalendarValidationError(
            "Calendar view must be month, week, or day."
        )

    def view(self, *, view="month", anchor_date=None):
        anchor = _parse_date(anchor_date or date.today().isoformat())
        start, end = self._range(anchor, view)
        items = (
            self._event_occurrences(start, end)
            + self._routine_occurrences(start, end)
            + self._task_occurrences(start, end)
            + self._agenda_occurrences(start, end)
        )
        items.sort(key=lambda item: (item["date"], item.get("start_time") or "", item["title"]))
        grouped = {}
        for item in items:
            grouped.setdefault(item["date"], []).append(item)
        try:
            assessments = self.repository.list_assessments()
        except OperationalCalendarRepositoryError:
            assessments = ()
        waiting = tuple(
            {
                "id": a["id"],
                "course_code": a["course_code"],
                "title": a["title"],
            }
            for a in assessments
            if a.get("due_on") in (None, "")
            and "mid" in str(a.get("assessment_type") or a.get("title") or "").lower()
        )
        previous_anchor, next_anchor = self._navigation(anchor, view)
        return {
            "available": True,
            "view": view,
            "anchor_date": anchor.isoformat(),
            "starts_on": start.isoformat(),
            "ends_on": end.isoformat(),
            "previous_anchor": previous_anchor.isoformat(),
            "next_anchor": next_anchor.isoformat(),
            "today": date.today().isoformat(),
            "items": tuple(items),
            "days": grouped,
            "waiting_exam_slots": waiting,
        }

    def routines_workspace(self):
        try:
            rows = self.repository.list_routine_templates()
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "Schedules are temporarily unavailable."
            ) from error
        return {
            "available": True,
            "routines": rows,
            "summary": {
                "active": sum(1 for row in rows if row.get("status") == "active"),
                "paused": sum(1 for row in rows if row.get("status") == "paused"),
            },
        }

    def _routine_fields(
        self,
        *,
        title,
        category="routine",
        priority="P1",
        frequency="weekly",
        weekdays=(),
        active_from="",
        active_to="",
        start_time="",
        end_time="",
        duration_minutes=None,
        preferred_window="",
        preferred_location="",
        condition_text="",
    ):
        clean_title = " ".join(str(title or "").strip().split())
        if not clean_title or len(clean_title) > 300:
            raise OperationalCalendarValidationError(
                "Enter a valid schedule title."
            )
        clean_priority = str(priority or "P1").strip().upper()
        if clean_priority not in {"P0", "P1", "P2"}:
            raise OperationalCalendarValidationError(
                "Priority must be P0, P1, or P2."
            )
        start_date = _optional_date(active_from)
        end_date = _optional_date(active_to)
        if start_date and end_date and end_date < start_date:
            raise OperationalCalendarValidationError(
                "Schedule end date cannot be before its start date."
            )
        start_clock = _clean_time(start_time, label="Start time")
        end_clock = _clean_time(end_time, label="End time")
        if start_clock and end_clock:
            if _time_minutes(end_clock) <= _time_minutes(start_clock):
                raise OperationalCalendarValidationError(
                    "End time must be after start time."
                )
        return {
            "title": clean_title,
            "category": " ".join(str(category or "routine").strip().split())[:80] or "routine",
            "priority": clean_priority,
            "recurrence_rule": _routine_rule(frequency, weekdays, end_date),
            "active_from": start_date,
            "active_to": end_date,
            "start_time": start_clock or None,
            "end_time": end_clock or None,
            "duration_minutes": _duration(duration_minutes),
            "preferred_window": " ".join(str(preferred_window or "").strip().split())[:200] or None,
            "preferred_location": " ".join(str(preferred_location or "").strip().split())[:300] or None,
            "condition_text": str(condition_text or "").strip()[:1000],
        }

    def create_routine(self, **payload):
        fields = self._routine_fields(**payload)
        now = self._now()
        row = {
            "id": str(self._id_factory()),
            **fields,
            "created_at": now,
            "updated_at": now,
        }
        try:
            created = self.repository.create_manual_routine(row)
            self.repository.mark_future_agendas_stale(
                fields.get("active_from") or date.today().isoformat()
            )
            return created
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "The schedule could not be saved."
            ) from error

    def update_routine(self, routine_id, **payload):
        fields = self._routine_fields(**payload)
        fields["updated_at"] = self._now()
        try:
            updated = self.repository.update_manual_routine(routine_id, fields)
            self.repository.mark_future_agendas_stale(
                fields.get("active_from") or date.today().isoformat()
            )
            return updated
        except OperationalCalendarRepositoryNotFoundError as error:
            raise OperationalCalendarNotFoundError(
                "Schedule was not found."
            ) from error
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "The schedule could not be updated."
            ) from error

    def set_routine_status(self, routine_id, status):
        token = str(status or "").strip().lower()
        if token not in {"active", "paused", "archived"}:
            raise OperationalCalendarValidationError(
                "Schedule status must be active, paused, or archived."
            )
        try:
            current = self.repository.get_routine(routine_id)
            updated = self.repository.update_manual_routine(
                routine_id,
                {"status": token, "updated_at": self._now()},
            )
            self.repository.mark_future_agendas_stale(
                current.get("active_from") or date.today().isoformat()
            )
            return updated
        except OperationalCalendarRepositoryNotFoundError as error:
            raise OperationalCalendarNotFoundError(
                "Schedule was not found."
            ) from error
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "The schedule status could not be changed."
            ) from error

    def day_items(self, agenda_date):
        return tuple(self.view(view="day", anchor_date=agenda_date)["items"])

    def schedule_assessment(self, assessment_id, *, due_on, start_time, end_time="", venue=""):
        d = _parse_date(due_on)
        try:
            start = datetime.strptime(str(start_time), "%H:%M")
        except ValueError as error:
            raise OperationalCalendarValidationError("Start time must be HH:MM.") from error
        end = None
        if end_time:
            try:
                end = datetime.strptime(str(end_time), "%H:%M")
            except ValueError as error:
                raise OperationalCalendarValidationError("End time must be HH:MM.") from error
            if (end.hour, end.minute) <= (start.hour, start.minute):
                raise OperationalCalendarValidationError("End time must be after start time.")
        day = self.view(view="day", anchor_date=d.isoformat())
        start_min = start.hour * 60 + start.minute
        end_min = (end.hour * 60 + end.minute) if end else start_min + 60
        conflicts = []
        for item in day["items"]:
            if item.get("all_day"):
                continue
            a = _time_minutes(item.get("start_time"))
            b = _time_minutes(item.get("end_time"))
            if a is not None and b is not None and max(a, start_min) < min(b, end_min):
                conflicts.append(item)
        if conflicts:
            raise OperationalCalendarConflictError(
                "The confirmed assessment overlaps an existing fixed commitment."
            )
        now = self._now()
        event_id = str(uuid.uuid5(
            uuid.UUID("e6b68031-93a1-58e3-bb9a-a312948d14f2"),
            "assessment:" + str(assessment_id),
        ))
        event = {
            "id": event_id,
            "starts_at": _iso_dt(d, start.strftime("%H:%M")),
            "ends_at": None if end is None else _iso_dt(d, end.strftime("%H:%M")),
            "created_at": now,
            "updated_at": now,
        }
        try:
            self.repository.schedule_assessment(
                assessment_id,
                due_on=d.isoformat(),
                due_time=start.strftime("%H:%M"),
                venue_note=str(venue or "").strip(),
                event_row=event,
            )
            self.repository.mark_future_agendas_stale(d.isoformat())
        except OperationalCalendarRepositoryNotFoundError as error:
            raise OperationalCalendarNotFoundError("Assessment was not found.") from error
        except OperationalCalendarRepositoryError as error:
            raise OperationalCalendarUnavailableError(
                "The assessment schedule could not be saved."
            ) from error
        return {"assessment_id": assessment_id, "date": d.isoformat(), "time": start.strftime("%H:%M")}


def build_operational_calendar_service(database_path="data/learning_assistant.db"):
    return OperationalCalendarService(SQLiteOperationalCalendarRepository(database_path))
