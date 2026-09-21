"""Deterministic daily agenda generation, review, and bounded rollover."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from personal_learning_assistant.repositories.sqlite.daily_agenda_repository import (
    DailyAgendaRepositoryConflictError,
    DailyAgendaRepositoryError,
    DailyAgendaRepositoryNotFoundError,
    SQLiteDailyAgendaRepository,
)
from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
    SQLiteOperationalCalendarRepository,
)
from personal_learning_assistant.repositories.sqlite.planner_task_repository import (
    SQLitePlannerTaskRepository,
)
from personal_learning_assistant.services.operational_calendar_service import (
    OperationalCalendarService,
    OperationalCalendarError,
)


_NAMESPACE = uuid.UUID("828cd60d-9810-5d21-8af3-34b590088ba2")
_OPEN_TASK_STATUSES = ("backlog", "planned", "scheduled", "in_progress", "skipped")
SHUTDOWN_MINUTE = 22 * 60 + 10
DAY_START_MINUTE = 6 * 60
MAX_FLEXIBLE = 5


class DailyAgendaError(RuntimeError):
    """Base safe daily-agenda error."""


class DailyAgendaValidationError(DailyAgendaError):
    """A daily-agenda command is invalid."""


class DailyAgendaConflictError(DailyAgendaError):
    """A daily-agenda transition conflicts with current state."""


class DailyAgendaNotFoundError(DailyAgendaError):
    """The requested agenda/item does not exist."""


class DailyAgendaUnavailableError(DailyAgendaError):
    """Daily planner persistence is unavailable."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as error:
        raise DailyAgendaValidationError("Date must be YYYY-MM-DD.") from error


def _minutes(hm):
    if not hm:
        return None
    try:
        t = datetime.strptime(str(hm), "%H:%M").time()
    except ValueError:
        return None
    return t.hour * 60 + t.minute


def _hm(total):
    total = max(0, min(int(total), 24 * 60 - 1))
    return "{:02d}:{:02d}".format(total // 60, total % 60)


def _id(day, kind, source_id, suffix=""):
    material = "{}\0{}\0{}\0{}".format(day, kind, source_id or "", suffix)
    return str(uuid.uuid5(_NAMESPACE, material))


def _preferred_window(task):
    text = (str(task.get("preferred_window") or "") + " " + str(task.get("preferred_day") or "")).lower()
    if "morning" in text:
        return 6 * 60, 12 * 60
    if "afternoon" in text or "daytime" in text or "library" in text:
        return 12 * 60, 18 * 60
    if "evening" in text or "after dinner" in text:
        return 18 * 60, SHUTDOWN_MINUTE
    return DAY_START_MINUTE, SHUTDOWN_MINUTE


def _free_windows(fixed):
    occupied = []
    for item in fixed:
        if item.get("all_day"):
            continue
        start = _minutes(item.get("start_time"))
        end = _minutes(item.get("end_time"))
        if start is not None and end is not None and end > start:
            occupied.append((start, end))
    occupied.sort()
    merged = []
    for start, end in occupied:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    windows = []
    cursor = DAY_START_MINUTE
    for start, end in merged:
        if cursor < start:
            windows.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < SHUTDOWN_MINUTE:
        windows.append((cursor, SHUTDOWN_MINUTE))
    return windows


def _place_task(task, windows, used, duration):
    pref_start, pref_end = _preferred_window(task)
    for index, (start, end) in enumerate(windows):
        start = max(start, pref_start)
        end = min(end, pref_end)
        cursor = start
        for a, b in sorted(used):
            if b <= cursor or a >= end:
                continue
            if cursor + duration <= a:
                break
            cursor = max(cursor, b)
        if cursor + duration <= end:
            return cursor, cursor + duration
    return None


class DailyAgendaService:
    def __init__(
        self,
        agenda_repository,
        task_repository,
        calendar_repository,
        calendar_service,
        *,
        now=_now,
    ):
        self.agendas = agenda_repository
        self.tasks = task_repository
        self.calendar_repository = calendar_repository
        self.calendar = calendar_service
        self._now = now

    def _open_tasks(self):
        try:
            return self.tasks.list_tasks(statuses=_OPEN_TASK_STATUSES)
        except Exception as error:
            raise DailyAgendaUnavailableError("Planner tasks are temporarily unavailable.") from error

    @staticmethod
    def _task_rank(task, target):
        due = str(task.get("due_on") or "")
        overdue = bool(due and due < target)
        due_today = due == target
        priority = {"P0": 0, "P1": 1, "P2": 2}.get(task.get("priority"), 3)
        return (
            priority,
            0 if overdue else 1 if due_today else 2,
            due or "9999-12-31",
            str(task.get("created_at") or ""),
            str(task.get("id") or ""),
        )

    def preview_day(self, agenda_date):
        target = _parse_date(agenda_date)
        day = target.isoformat()
        existing = self.agendas.get_agenda(day)
        try:
            fixed = tuple(self.calendar.day_items(day))
            study = tuple(self.calendar_repository.list_study_items(day))
        except OperationalCalendarError as error:
            raise DailyAgendaUnavailableError("Calendar is temporarily unavailable.") from error
        tasks = sorted(self._open_tasks(), key=lambda item: self._task_rank(item, day))
        # Active-flexible ceiling.
        selected = list(tasks[:MAX_FLEXIBLE])
        fixed_count = sum(1 for item in fixed if item.get("start_time"))
        deep_limit = 1 if fixed_count >= 4 else 3

        items = []
        now = self._now()
        for item in fixed:
            items.append({
                "id": _id(day, "fixed" if item["source"] == "academic_event" else "routine", item["id"], item.get("start_time","")),
                "item_kind": "fixed" if item["source"] == "academic_event" else "routine",
                "source_type": item["source"],
                "source_id": item["id"],
                "title": item["title"],
                "priority": item.get("priority"),
                "starts_at": (
                    None if not item.get("start_time")
                    else day + "T" + item["start_time"] + ":00"
                ),
                "ends_at": (
                    None if not item.get("end_time")
                    else day + "T" + item["end_time"] + ":00"
                ),
                "planned_minutes": item.get("duration_minutes"),
                "status": "planned",
                "reason": "Fixed commitment" if item["source"] == "academic_event" else "Recurring routine",
                "created_at": now,
                "updated_at": now,
            })

        for row in study[:deep_limit]:
            items.append({
                "id": _id(day, "study", row["id"]),
                "item_kind": "study",
                "source_type": "study_plan_item",
                "source_id": row["id"],
                "title": "{}{}".format(
                    (str(row.get("course_code")) + " · ") if row.get("course_code") else "",
                    row.get("action") or "Study block",
                ),
                "priority": "P1",
                "starts_at": None,
                "ends_at": None,
                "planned_minutes": int(row.get("minutes") or 0),
                "status": "planned",
                "reason": row.get("reason") or "Saved study plan item",
                "created_at": now,
                "updated_at": now,
            })

        windows = _free_windows(fixed)
        used = []
        placed_deep = 0
        for task in selected:
            duration = int(task.get("estimated_minutes") or 30)
            duration = max(10, min(duration, 180))
            placement = None
            if placed_deep < deep_limit:
                placement = _place_task(task, windows, used, duration)
            starts_at = ends_at = None
            reason = "Important task selected for today"
            if placement is not None:
                a, b = placement
                starts_at = day + "T" + _hm(a) + ":00"
                ends_at = day + "T" + _hm(b) + ":00"
                used.append((a, b))
                placed_deep += 1
                reason = "Scheduled into a free window without crossing shutdown"
            else:
                reason = "Selected for today but left unscheduled because no safe free window was available"
            items.append({
                "id": _id(day, "task", task["id"]),
                "item_kind": "task",
                "source_type": "planner_task",
                "source_id": task["id"],
                "title": task["title"],
                "priority": task["priority"],
                "starts_at": starts_at,
                "ends_at": ends_at,
                "planned_minutes": duration,
                "status": "planned",
                "reason": reason,
                "created_at": now,
                "updated_at": now,
            })

        day_mode = "minimum_viable" if fixed_count >= 6 else "normal"
        return {
            "available": True,
            "date": day,
            "existing": existing,
            "day_mode": day_mode,
            "items": tuple(items),
            "fixed": tuple(item for item in items if item["item_kind"] in {"fixed","routine"}),
            "tasks": tuple(item for item in items if item["item_kind"] == "task"),
            "study": tuple(item for item in items if item["item_kind"] == "study"),
            "summary": {
                "fixed_count": sum(1 for item in items if item["item_kind"] in {"fixed","routine"}),
                "task_count": sum(1 for item in items if item["item_kind"] == "task"),
                "scheduled_focus_minutes": sum(
                    int(item.get("planned_minutes") or 0)
                    for item in items
                    if item["item_kind"] in {"task","study"} and item.get("starts_at")
                ),
                "p0": sum(1 for item in items if item.get("priority") == "P0"),
            },
        }

    def generate_day(self, agenda_date):
        preview = self.preview_day(agenda_date)
        if preview["existing"] and preview["existing"]["status"] != "draft":
            raise DailyAgendaConflictError("Only a draft agenda can be regenerated.")
        now = self._now()
        agenda = {
            "id": str(uuid.uuid5(_NAMESPACE, "agenda:" + preview["date"])),
            "agenda_date": preview["date"],
            "day_mode": preview["day_mode"],
            "generated_at": now,
            "created_at": now,
            "updated_at": now,
        }
        try:
            return self.agendas.create_or_replace_draft(agenda, preview["items"])
        except DailyAgendaRepositoryConflictError as error:
            raise DailyAgendaConflictError(str(error)) from error
        except DailyAgendaRepositoryError as error:
            raise DailyAgendaUnavailableError("Daily agenda could not be saved.") from error

    def approve_day(self, agenda_date):
        day = _parse_date(agenda_date).isoformat()
        now = self._now()
        try:
            return self.agendas.approve_agenda(day, approved_at=now, updated_at=now)
        except DailyAgendaRepositoryConflictError as error:
            raise DailyAgendaConflictError(str(error)) from error
        except DailyAgendaRepositoryError as error:
            raise DailyAgendaUnavailableError("Daily agenda could not be approved.") from error

    def update_item(self, agenda_date, item_id, *, status, actual_minutes=None):
        if status not in {"planned","in_progress","completed","skipped","moved"}:
            raise DailyAgendaValidationError("Invalid agenda item status.")
        actual = None
        if actual_minutes not in (None, ""):
            try:
                actual = int(actual_minutes)
            except (TypeError, ValueError) as error:
                raise DailyAgendaValidationError("Actual minutes must be an integer.") from error
            if actual < 0 or actual > 1440:
                raise DailyAgendaValidationError("Actual minutes are outside the accepted range.")
        now = self._now()
        try:
            return self.agendas.update_item_status(
                _parse_date(agenda_date).isoformat(),
                item_id,
                status=status,
                actual_minutes=actual,
                completed_at=now if status == "completed" else None,
                updated_at=now,
            )
        except DailyAgendaRepositoryNotFoundError as error:
            raise DailyAgendaNotFoundError(str(error)) from error
        except DailyAgendaRepositoryConflictError as error:
            raise DailyAgendaConflictError(str(error)) from error
        except DailyAgendaRepositoryError as error:
            raise DailyAgendaUnavailableError("Agenda item could not be updated.") from error

    def close_day(self, agenda_date, review):
        day = _parse_date(agenda_date)
        current = self.agendas.get_agenda(day.isoformat())
        if current is None:
            raise DailyAgendaNotFoundError("Daily agenda was not found.")
        if current["status"] == "closed":
            raise DailyAgendaConflictError("Daily agenda is already closed.")

        def optional_int(name, minimum, maximum):
            value = review.get(name)
            if value in (None, ""):
                return None
            try:
                value = int(value)
            except (TypeError, ValueError) as error:
                raise DailyAgendaValidationError("{} must be an integer.".format(name)) from error
            if not minimum <= value <= maximum:
                raise DailyAgendaValidationError("{} is outside the accepted range.".format(name))
            return value

        payload = {
            "learned": str(review.get("learned") or "").strip()[:4000],
            "biggest_confusion": str(review.get("biggest_confusion") or "").strip()[:4000],
            "coding_completed": bool(review.get("coding_completed")),
            "coding_independent": bool(review.get("coding_independent")),
            "data_science_ai_assistance_level": optional_int(
                "data_science_ai_assistance_level", 0, 7
            ),
            "energy_1_to_5": optional_int("energy_1_to_5", 1, 5),
            "sleep_target": str(review.get("sleep_target") or "").strip()[:100],
            "tomorrow_first_task": str(review.get("tomorrow_first_task") or "").strip()[:500],
        }
        now = self._now()
        payload["created_at"] = now
        payload["updated_at"] = now

        incomplete_tasks = [
            item for item in current["items"]
            if item["item_kind"] == "task"
            and item["status"] not in {"completed", "moved"}
            and item.get("source_id")
        ]
        p0 = [item for item in incomplete_tasks if item.get("priority") == "P0"][:1]
        p1 = [item for item in incomplete_tasks if item.get("priority") == "P1"][:1]
        selected = p0 + p1
        tomorrow = day + timedelta(days=1)
        rollover = []
        for item in incomplete_tasks:
            carry = item in selected
            decision = "carry" if carry else ("backlog" if item.get("priority") == "P1" else "drop")
            if item.get("priority") == "P2":
                decision = "backlog"
            rollover.append({
                "id": _id(day.isoformat(), "rollover", item["source_id"], decision),
                "task_id": item["source_id"],
                "from_date": day.isoformat(),
                "to_date": tomorrow.isoformat() if carry else None,
                "decision": decision,
                "reason": (
                    "Bounded daily carry-forward" if carry
                    else "Returned to backlog under the rollover policy"
                ),
                "created_at": now,
            })
        try:
            closed = self.agendas.close_agenda(
                day.isoformat(),
                review=payload,
                rollover_rows=tuple(rollover),
                closed_at=now,
                updated_at=now,
            )
        except DailyAgendaRepositoryConflictError as error:
            raise DailyAgendaConflictError(str(error)) from error
        except DailyAgendaRepositoryError as error:
            raise DailyAgendaUnavailableError("Daily agenda could not be closed.") from error

        tomorrow_draft = None
        try:
            existing_tomorrow = self.agendas.get_agenda(tomorrow.isoformat())
            if existing_tomorrow is None or existing_tomorrow["status"] == "draft":
                tomorrow_draft = self.generate_day(tomorrow.isoformat())
        except DailyAgendaError:
            tomorrow_draft = None
        return {"agenda": closed, "tomorrow_draft": tomorrow_draft, "rollover": tuple(rollover)}


def build_daily_agenda_service(database_path="data/learning_assistant.db"):
    agenda_repo = SQLiteDailyAgendaRepository(database_path)
    task_repo = SQLitePlannerTaskRepository(database_path)
    calendar_repo = SQLiteOperationalCalendarRepository(database_path)
    calendar_service = OperationalCalendarService(calendar_repo)
    return DailyAgendaService(agenda_repo, task_repo, calendar_repo, calendar_service)
