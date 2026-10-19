"""Web composition façade for Phase 7.5.13 Operational Planner."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from zoneinfo import ZoneInfoNotFoundError

from personal_learning_assistant.repositories.sqlite.daily_agenda_repository import DailyAgendaRepositoryError

from personal_learning_assistant.services.daily_agenda_service import (
    DailyAgendaService,
    DailyAgendaConflictError,
    DailyAgendaError,
    DailyAgendaNotFoundError,
    DailyAgendaValidationError,
    build_daily_agenda_service,
)
from personal_learning_assistant.services.month_plan_import_service import (
    MonthPlanImportConflictError,
    MonthPlanImportError,
    MonthPlanImportValidationError,
    build_month_plan_import_service,
)
from personal_learning_assistant.services.operational_calendar_service import (
    OperationalCalendarConflictError,
    OperationalCalendarError,
    OperationalCalendarNotFoundError,
    OperationalCalendarValidationError,
    build_operational_calendar_service,
)
from personal_learning_assistant.services.operational_task_service import (
    OperationalTaskError,
    OperationalTaskNotFoundError,
    OperationalTaskValidationError,
    build_operational_task_service,
)
from personal_learning_assistant.services.weekly_review_service import (
    WeeklyReviewConflictError,
    WeeklyReviewError,
    WeeklyReviewValidationError,
    build_weekly_review_service,
)


class OperationalPlannerWebError(RuntimeError):
    """Base safe web-facade error."""


class OperationalPlannerWebValidationError(OperationalPlannerWebError):
    """Web command input is invalid."""


class OperationalPlannerWebNotFoundError(OperationalPlannerWebError):
    """Web command target does not exist."""


class OperationalPlannerWebConflictError(OperationalPlannerWebError):
    """Web command conflicts with current state."""


class OperationalPlannerWebUnavailableError(OperationalPlannerWebError):
    """Operational planner is temporarily unavailable."""


def _translate(error):
    if isinstance(
        error,
        (
            MonthPlanImportValidationError,
            OperationalCalendarValidationError,
            OperationalTaskValidationError,
            DailyAgendaValidationError,
            WeeklyReviewValidationError,
        ),
    ):
        return OperationalPlannerWebValidationError(str(error))
    if isinstance(
        error,
        (OperationalCalendarNotFoundError, OperationalTaskNotFoundError, DailyAgendaNotFoundError),
    ):
        return OperationalPlannerWebNotFoundError(str(error))
    if isinstance(
        error,
        (
            MonthPlanImportConflictError,
            OperationalCalendarConflictError,
            DailyAgendaConflictError,
            WeeklyReviewConflictError,
        ),
    ):
        return OperationalPlannerWebConflictError(str(error))
    return OperationalPlannerWebUnavailableError(
        "Operational planner is temporarily unavailable."
    )


class OperationalPlannerWebService:
    def __init__(self, month_import, tasks, calendar, daily, weekly):
        self.month_import = month_import
        self.tasks = tasks
        self.calendar = calendar
        self.daily = daily
        self.weekly = weekly

    def planning_home(self, *, today=None):
        today = today or date.today().isoformat()
        try:
            task_view = self.tasks.tasks_workspace()
            day_preview = self.daily.preview_day(today)
            agenda = day_preview.get("existing")
            return {
                "available": True,
                "today": today,
                "task_summary": task_view["summary"],
                "agenda": agenda,
                "today_preview": day_preview,
                "daily_review_status": (
                    "closed" if agenda and agenda.get("status") == "closed"
                    else "open" if agenda else "not_generated"
                ),
            }
        except (OperationalTaskError, DailyAgendaError) as error:
            raise _translate(error)

    def tasks_workspace(self, **filters):
        try:
            return self.tasks.tasks_workspace(**filters)
        except OperationalTaskError as error:
            raise _translate(error)

    def create_task(self, **payload):
        try:
            return self.tasks.create_task(**payload)
        except OperationalTaskError as error:
            raise _translate(error)

    def update_task(self, task_id, **payload):
        try:
            return self.tasks.update_task(task_id, **payload)
        except OperationalTaskError as error:
            raise _translate(error)

    def transition_task(self, task_id, status):
        try:
            return self.tasks.transition(task_id, status)
        except OperationalTaskError as error:
            raise _translate(error)

    def preview_month_plan(self, filename, payload):
        try:
            return self.month_import.preview(filename, payload)
        except MonthPlanImportError as error:
            raise _translate(error)

    def approve_month_plan(self, filename, payload, expected_sha256):
        try:
            return self.month_import.approve(filename, payload, expected_sha256)
        except MonthPlanImportError as error:
            raise _translate(error)

    def calendar_view(self, *, view="month", anchor_date=None):
        try:
            return self.calendar.view(view=view, anchor_date=anchor_date)
        except OperationalCalendarError as error:
            raise _translate(error)

    def schedule_assessment(self, assessment_id, **payload):
        try:
            return self.calendar.schedule_assessment(assessment_id, **payload)
        except OperationalCalendarError as error:
            raise _translate(error)

    def day_view(self, agenda_date):
        try:
            return self.daily.day_view(agenda_date)
        except DailyAgendaError as error:
            raise _translate(error)

    def _proposal_daily(self, agenda_date, start, end, *, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        try:
            datetime.strptime(agenda_date, "%Y-%m-%d")
            left = datetime.strptime(start, "%H:%M")
            right = datetime.strptime(end, "%H:%M")
            if left >= right or left.strftime("%H:%M") != start or right.strftime("%H:%M") != end:
                raise ValueError("Invalid availability")
            return DailyAgendaService(
                self.daily.agendas, self.daily.tasks, self.daily.calendar_repository, self.daily.calendar,
                now=now or self.daily._now, free_windows={agenda_date: [(start, end)]},
                local_timezone=local_timezone, break_minutes=break_minutes,
            )
        except (TypeError, ValueError, ZoneInfoNotFoundError, DailyAgendaValidationError) as error:
            raise OperationalPlannerWebValidationError("Enter a valid date and availability window (start before end).") from error

    @staticmethod
    def _proposal_hash(preview):
        # Creation timestamps are not scheduling decisions; all other fields bind the preview.
        semantic = {key: value for key, value in preview.items() if key not in {"items", "tasks", "study", "fixed"}}
        semantic["items"] = [
            {key: value for key, value in item.items() if key not in {"created_at", "updated_at"}}
            for item in preview["items"]
        ]
        return hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def preview_proposal(self, agenda_date, start, end, *, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        daily = self._proposal_daily(agenda_date, start, end, local_timezone=local_timezone, now=now, break_minutes=break_minutes)
        try:
            fingerprint = daily.agendas.planning_fingerprint()
            preview = daily.preview_day(agenda_date)
            if fingerprint != daily.agendas.planning_fingerprint():
                raise OperationalPlannerWebConflictError("Planner changed during preview. Try again.")
            if preview["existing"] and preview["existing"]["status"] != "draft":
                raise OperationalPlannerWebConflictError("Only an absent or draft agenda can receive a proposal.")
            return {"day": preview, "fingerprint": fingerprint, "semantic_hash": self._proposal_hash(preview)}
        except DailyAgendaError as error:
            raise _translate(error)
        except DailyAgendaRepositoryError as error:
            raise OperationalPlannerWebUnavailableError("Planner preview storage is unavailable.") from error

    def save_proposal(self, agenda_date, start, end, *, fingerprint, semantic_hash, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        current = self.preview_proposal(agenda_date, start, end, local_timezone=local_timezone, now=now, break_minutes=break_minutes)
        if current["fingerprint"] != fingerprint or current["semantic_hash"] != semantic_hash:
            raise OperationalPlannerWebConflictError("Planner changed since preview. Preview again before saving.")
        daily = self._proposal_daily(agenda_date, start, end, local_timezone=local_timezone, now=now, break_minutes=break_minutes)
        try:
            return daily.generate_day(agenda_date, expected_fingerprint=fingerprint, preview=current["day"])
        except DailyAgendaError as error:
            raise _translate(error)

    def generate_day(self, agenda_date):
        try:
            return self.daily.generate_day(agenda_date)
        except DailyAgendaError as error:
            raise _translate(error)

    def approve_day(self, agenda_date, *, proposal_context=None, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        try:
            if proposal_context is not None:
                if (proposal_context.get('date') != agenda_date
                        or proposal_context.get('timezone') != local_timezone
                        or proposal_context.get('break_minutes') != break_minutes
                        or proposal_context.get('policy') != 'explicit-availability-v1'
                        or proposal_context.get('saved_fingerprint') != self.daily.agendas.planning_fingerprint()):
                    raise OperationalPlannerWebConflictError("Planner or availability context changed. Preview and save a fresh draft.")
                daily = self._proposal_daily(
                    agenda_date, proposal_context['start'], proposal_context['end'],
                    local_timezone=local_timezone, now=now, break_minutes=break_minutes,
                )
                return daily.approve_day(agenda_date, expected_fingerprint=proposal_context['saved_fingerprint'])
            return self.daily.approve_day(agenda_date)
        except DailyAgendaError as error:
            raise _translate(error)
        except DailyAgendaRepositoryError as error:
            raise OperationalPlannerWebUnavailableError("Planner approval storage is unavailable.") from error

    def update_day_item(self, agenda_date, item_id, *, status, actual_minutes=None):
        try:
            return self.daily.update_item(
                agenda_date, item_id, status=status, actual_minutes=actual_minutes
            )
        except DailyAgendaError as error:
            raise _translate(error)

    def close_day(self, agenda_date, review):
        try:
            return self.daily.close_day(agenda_date, review)
        except DailyAgendaError as error:
            raise _translate(error)

    def weekly_review(self, anchor_date):
        try:
            return self.weekly.workspace(anchor_date)
        except WeeklyReviewError as error:
            raise _translate(error)

    def save_weekly_review(self, anchor_date, payload, *, close=False):
        try:
            return self.weekly.save(anchor_date, payload, close=close)
        except WeeklyReviewError as error:
            raise _translate(error)


def build_operational_planner_web_service(database_path="data/learning_assistant.db"):
    return OperationalPlannerWebService(
        build_month_plan_import_service(database_path),
        build_operational_task_service(database_path),
        build_operational_calendar_service(database_path),
        build_daily_agenda_service(database_path),
        build_weekly_review_service(database_path),
    )
