"""Web composition façade for Phase 7.5.13 Operational Planner."""

from __future__ import annotations

from datetime import date

from personal_learning_assistant.services.daily_agenda_service import (
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
            preview = self.daily.preview_day(agenda_date)
            return preview
        except DailyAgendaError as error:
            raise _translate(error)

    def generate_day(self, agenda_date):
        try:
            return self.daily.generate_day(agenda_date)
        except DailyAgendaError as error:
            raise _translate(error)

    def approve_day(self, agenda_date):
        try:
            return self.daily.approve_day(agenda_date)
        except DailyAgendaError as error:
            raise _translate(error)

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
