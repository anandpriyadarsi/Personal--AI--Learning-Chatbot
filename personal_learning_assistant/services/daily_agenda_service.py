"""Deterministic daily agenda generation, review, and bounded rollover."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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


def _free_windows(fixed, availability, earliest, buffer):
    """Subtract commitments from explicit availability; unknown occupancy closes the day."""
    occupied = []
    for item in fixed:
        start = _minutes(item.get("start_time"))
        end = _minutes(item.get("end_time"))
        if item.get("all_day") or start is None or end is None or end <= start:
            return []
        occupied.append((max(0, start - buffer), min(1440, end + buffer)))
    windows = []
    for raw_start, raw_end in availability:
        start, end = _minutes(raw_start), _minutes(raw_end)
        if start is None or end is None or end <= start:
            continue
        fragments = [(max(start, earliest, DAY_START_MINUTE), min(end, SHUTDOWN_MINUTE))]
        for a, b in sorted(occupied):
            remaining = []
            for x, y in fragments:
                if b <= x or a >= y:
                    remaining.append((x, y))
                else:
                    remaining.extend([(x, min(y, a)), (max(x, b), y)])
            fragments = [(x, y) for x, y in remaining if x < y]
        windows.extend((x, y) for x, y in fragments if x < y)
    return sorted(windows)


def _preferred_day_allows(task, target):
    preferred = str(task.get("preferred_day") or "").strip()
    if not preferred:
        return True
    try:
        return _parse_date(preferred) <= target
    except DailyAgendaValidationError:
        days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6}
        return days.get(preferred.lower()) == target.weekday()


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
        free_windows=None,
        local_timezone="Asia/Kolkata",
        break_minutes=10,
    ):
        self.agendas = agenda_repository
        self.tasks = task_repository
        self.calendar_repository = calendar_repository
        self.calendar = calendar_service
        self._now = now
        # Date-keyed explicit local wall-clock availability. No defaults are invented.
        self.free_windows = free_windows or {}
        self.local_timezone = timezone.utc if local_timezone == "UTC" else ZoneInfo(local_timezone)
        if not isinstance(break_minutes, int) or not 0 <= break_minutes <= 120:
            raise DailyAgendaValidationError("Break minutes must be between 0 and 120.")
        self.break_minutes = break_minutes

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
            fixed = tuple(item for item in self.calendar.day_items(day)
                          if item.get("source") != "task")
            study = tuple(self.calendar_repository.list_study_items(day))
        except OperationalCalendarError as error:
            raise DailyAgendaUnavailableError("Calendar is temporarily unavailable.") from error
        # The previous day's explicit carry decisions control the NEXT draft only.
        # Backlogged tasks remain in the canonical inbox; do not silently reinsert
        # them into a next-day agenda that the student explicitly reviewed.
        previous = (target - timedelta(days=1)).isoformat()
        decisions = {row["task_id"]: row["decision"] for row in
                     self.agendas.rollover_for_date(previous)}
        tasks = sorted(
            (task for task in self._open_tasks()
             if task["id"] not in decisions or decisions[task["id"]] == "carry"),
            key=lambda item: (0 if decisions.get(item["id"]) == "carry" else 1,
                              self._task_rank(item, day)),
        )
        # Active-flexible ceiling.
        selected = [task for task in tasks if _preferred_day_allows(task, target)][:MAX_FLEXIBLE]
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
                "planned_minutes": row.get("minutes"),
                "status": "planned",
                "reason": row.get("reason") or "Saved study plan item",
                "created_at": now,
                "updated_at": now,
            })

        try:
            clock = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
            if clock.tzinfo is None:
                raise ValueError("Clock must include a timezone")
            clock = clock.astimezone(self.local_timezone)
            earliest = (clock.hour * 60 + clock.minute + bool(clock.second or clock.microsecond)
                        if target == clock.date() else 0 if target > clock.date() else 1440)
        except (TypeError, ValueError):
            earliest = 1440
        midnight = datetime(target.year, target.month, target.day, tzinfo=self.local_timezone)
        if midnight.utcoffset() != (midnight + timedelta(days=1)).utcoffset():
            # Stored agenda slots have no offset/fold field: do not guess through DST.
            earliest = 1440
        windows = _free_windows(fixed, self.free_windows.get(day, ()), earliest, self.break_minutes)
        descriptors = {('planner_task', row['id']): row for row in selected}
        for row in study[:deep_limit]:
            descriptors[('study_plan_item', row['id'])] = {
                'id': row['id'], 'priority': 'P1', 'due_on': day,
                'estimated_minutes': row.get('minutes'),
            }
        for task in selected:
            items.append({
                'id': _id(day, 'task', task['id']), 'item_kind': 'task',
                'source_type': 'planner_task', 'source_id': task['id'],
                'title': task['title'], 'priority': task['priority'],
                'starts_at': None, 'ends_at': None,
                'planned_minutes': task.get('estimated_minutes'), 'status': 'planned',
                'reason': '', 'created_at': now, 'updated_at': now,
            })
        # One priority order, one capacity ledger and one deep-work ceiling.
        # Saved date-specific study is P1 due-today work; P0 tasks rank before it.
        focus = sorted((row for row in items if row['item_kind'] in {'task', 'study'}),
                       key=lambda row: self._task_rank(descriptors[(row['source_type'], row['source_id'])], day))
        used = []
        placed_deep = 0
        for item in focus:
            descriptor = descriptors[(item['source_type'], item['source_id'])]
            try:
                duration = int(descriptor.get('estimated_minutes') or 0)
            except (TypeError, ValueError):
                duration = 0
            duration_known = 0 < duration <= 1440
            item['planned_minutes'] = duration if duration_known else None
            due = str(descriptor.get('due_on') or '')
            deadline_valid = not due or due >= day
            placement = (_place_task(descriptor, windows, used, duration)
                         if duration_known and deadline_valid and placed_deep < deep_limit else None)
            if placement is not None:
                a, b = placement
                item['starts_at'], item['ends_at'] = day + 'T' + _hm(a) + ':00', day + 'T' + _hm(b) + ':00'
                item['reason'] = 'Scheduled within shared explicit availability and capacity'
                used.append((max(0, a - self.break_minutes), b + self.break_minutes))
                placed_deep += 1
            else:
                item['reason'] = (
                    'Unscheduled: deadline has passed; revise the deadline explicitly' if not deadline_valid
                    else 'Unscheduled: a valid duration is required' if not duration_known
                    else 'Unscheduled: no safe explicit availability or capacity'
                )

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

    def day_view(self, agenda_date):
        day = _parse_date(agenda_date).isoformat()
        existing = self.agendas.get_agenda(day)
        if existing is None:
            return self.preview_day(day)
        items = existing["items"]
        return {"available": True, "date": day, "existing": existing,
                "day_mode": existing["day_mode"], "items": items,
                "fixed": tuple(i for i in items if i["item_kind"] in {"fixed", "routine"}),
                "tasks": tuple(i for i in items if i["item_kind"] == "task"),
                "study": tuple(i for i in items if i["item_kind"] == "study"),
                "summary": {"fixed_count": sum(i["item_kind"] in {"fixed", "routine"} for i in items),
                            "task_count": sum(i["item_kind"] == "task" for i in items),
                            "scheduled_focus_minutes": sum(int(i.get("planned_minutes") or 0) for i in items
                                                           if i["item_kind"] in {"task", "study"} and i.get("starts_at")),
                            "p0": sum(i.get("priority") == "P0" for i in items)}}

    def _validate_saved_slots(self, day, agenda):
        target = _parse_date(day)
        tasks = {task["id"]: task for task in self._open_tasks()}
        study = {row["id"]: row for row in self.calendar_repository.list_study_items(day)}
        fixed = tuple(i for i in self.calendar.day_items(day) if i.get("source") != "task")
        windows = _free_windows(fixed, self.free_windows.get(day, ()), 0, self.break_minutes)
        if not self.free_windows.get(day) and any(
            item['item_kind'] in {'task', 'study'} and (item.get('starts_at') or item.get('ends_at'))
            for item in agenda['items']
        ):
            raise DailyAgendaConflictError(
                "Original availability context is unavailable. Preview and save a fresh draft before approval."
            )
        clock = datetime.fromisoformat(str(self._now()).replace("Z", "+00:00"))
        if clock.tzinfo is None:
            raise DailyAgendaConflictError("Approval clock must include a timezone.")
        clock = clock.astimezone(self.local_timezone).replace(tzinfo=None)
        used = []
        for item in agenda["items"]:
            if item["item_kind"] not in {"task", "study"}:
                continue
            if not item.get("starts_at") and not item.get("ends_at"):
                continue  # Legacy unscheduled drafts remain unscheduled.
            try:
                start = datetime.fromisoformat(item["starts_at"])
                end = datetime.fromisoformat(item["ends_at"])
                if start.tzinfo or end.tzinfo or start.date() != target or end.date() != target or start < clock:
                    raise ValueError()
                a, b = start.hour * 60 + start.minute, end.hour * 60 + end.minute
                if start.second or end.second or b <= a or b - a != item["planned_minutes"]:
                    raise ValueError()
                if not any(x <= a and b <= y for x, y in windows):
                    raise ValueError()
                if any(a < y and b > x for x, y in used):
                    raise ValueError()
                if item["item_kind"] == "task":
                    task = tasks[item["source_id"]]
                    left, right = _preferred_window(task)
                    if (int(task.get("estimated_minutes") or 0) != b - a
                            or not _preferred_day_allows(task, target)
                            or (task.get("due_on") and task["due_on"] < day)
                            or a < left or b > right):
                        raise ValueError()
                elif int(study[item['source_id']].get('minutes') or 0) != b - a:
                    raise ValueError()
                used.append((a - self.break_minutes, b + self.break_minutes))
            except (ValueError, TypeError, KeyError):
                raise DailyAgendaConflictError("Saved slots are no longer safe. Preview and save a fresh draft.")

    def generate_day(self, agenda_date, *, expected_fingerprint=None, preview=None):
        preview = preview if preview is not None else self.preview_day(agenda_date)
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
            if expected_fingerprint is None:
                return self.agendas.create_or_replace_draft(agenda, preview["items"])
            return self.agendas.create_or_replace_draft(
                agenda, preview["items"], expected_fingerprint=expected_fingerprint
            )
        except DailyAgendaRepositoryConflictError as error:
            raise DailyAgendaConflictError(str(error)) from error
        except DailyAgendaRepositoryError as error:
            raise DailyAgendaUnavailableError("Daily agenda could not be saved.") from error

    def approve_day(self, agenda_date, *, expected_fingerprint=None):
        day = _parse_date(agenda_date).isoformat()
        now = self._now()
        try:
            fingerprint = self.agendas.planning_fingerprint()
            if expected_fingerprint is not None and fingerprint != expected_fingerprint:
                raise DailyAgendaConflictError("Planner sources changed. Preview again before approval.")
            agenda = self.agendas.get_agenda(day)
            if agenda is None or agenda["status"] != "draft":
                raise DailyAgendaConflictError("Only a draft agenda can be approved.")
            self._validate_saved_slots(day, agenda)
            return self.agendas.approve_agenda(day, approved_at=now, updated_at=now,
                                               expected_fingerprint=fingerprint)
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
        raw_carry = review.get("carry_task_ids", ())
        if not isinstance(raw_carry, (list, tuple, set)):
            raise DailyAgendaValidationError("Choose carry-forward tasks from the daily review.")
        selected_ids = tuple(str(item) for item in raw_carry)
        available_ids = {item["source_id"] for item in incomplete_tasks}
        if (len(selected_ids) != len(set(selected_ids))
                or len(selected_ids) > 2
                or not set(selected_ids) <= available_ids):
            raise DailyAgendaValidationError("Only two existing unfinished tasks may be carried.")
        tomorrow = day + timedelta(days=1)
        rollover = []
        for item in incomplete_tasks:
            carry = item["source_id"] in selected_ids
            decision = "carry" if carry else "backlog"
            rollover.append({
                "id": _id(day.isoformat(), "rollover", item["source_id"], decision),
                "task_id": item["source_id"],
                "from_date": day.isoformat(),
                "to_date": tomorrow.isoformat() if carry else None,
                "decision": decision,
                "reason": ("Student explicitly selected carry-forward"
                           if carry else "Left in task backlog; no automatic rollover"),
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
            if existing_tomorrow is None:
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
