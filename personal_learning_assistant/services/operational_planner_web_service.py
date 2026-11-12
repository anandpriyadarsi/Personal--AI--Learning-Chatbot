"""Web composition façade for Phase 7.5.13 Operational Planner."""

from __future__ import annotations

from datetime import date, datetime, timezone
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
    OperationalTaskConflictError,
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
            OperationalTaskConflictError,
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
            fingerprint=self.daily.agendas.planning_fingerprint(agenda_date)
            day=self.daily.day_view(agenda_date)
            if fingerprint!=self.daily.agendas.planning_fingerprint(agenda_date):
                raise OperationalPlannerWebConflictError("Planner changed during review. Open the day again.")
            return {**day,'planning_fingerprint':fingerprint}
        except DailyAgendaError as error:
            raise _translate(error)
        except DailyAgendaRepositoryError as error:
            raise OperationalPlannerWebUnavailableError("Planner review storage is unavailable.") from error

    def _proposal_daily(self, agenda_date, start, end, *, windows=None, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        try:
            target = datetime.strptime(agenda_date, "%Y-%m-%d").date()
            windows = list(windows) if windows is not None else [(start, end)]
            if not windows or len(windows) > 12:
                raise ValueError('Choose between one and twelve windows')
            parsed = []
            for left_text, right_text in windows:
                left, right = datetime.strptime(left_text, '%H:%M'), datetime.strptime(right_text, '%H:%M')
                if left >= right or left.strftime('%H:%M') != left_text or right.strftime('%H:%M') != right_text:
                    raise ValueError('Invalid availability')
                parsed.append((left_text, right_text))
            parsed.sort()
            if any(a[1] > b[0] for a, b in zip(parsed, parsed[1:])):
                raise ValueError('Overlapping windows')
            daily = DailyAgendaService(
                self.daily.agendas, self.daily.tasks, self.daily.calendar_repository, self.daily.calendar,
                now=now or self.daily._now, free_windows={agenda_date: parsed},
                local_timezone=local_timezone, break_minutes=break_minutes,
            )
            clock = datetime.fromisoformat(str(daily._now()).replace('Z', '+00:00'))
            if clock.tzinfo is None:
                raise ValueError('Clock requires timezone')
            clock = clock.astimezone(daily.local_timezone)
            if target < clock.date() or (target == clock.date() and any(end <= clock.strftime('%H:%M') for _, end in parsed)):
                raise ValueError('Availability has elapsed')
            # Slots have no fold/offset column; reject daylight-saving transitions.
            from datetime import timedelta
            midnight = datetime.combine(target, datetime.min.time(), daily.local_timezone)
            if midnight.utcoffset() != (midnight + timedelta(days=1)).utcoffset():
                raise ValueError('Ambiguous local day')
            return daily
        except (TypeError, ValueError, ZoneInfoNotFoundError, DailyAgendaValidationError) as error:
            raise OperationalPlannerWebValidationError("Enter valid, non-overlapping availability windows that have not elapsed.") from error

    @staticmethod
    def _proposal_hash(preview):
        # Creation timestamps are not scheduling decisions; all other fields bind the preview.
        semantic = {key: value for key, value in preview.items() if key not in {"items", "tasks", "study", "fixed", "review_needed"}}
        semantic["items"] = [
            {key: value for key, value in item.items() if key not in {"created_at", "updated_at"}}
            for item in preview["items"]
        ]
        return hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def preview_proposal(self, agenda_date, start, end, *, windows=None, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        daily = self._proposal_daily(agenda_date, start, end, windows=windows, local_timezone=local_timezone, now=now, break_minutes=break_minutes)
        try:
            fingerprint = daily.agendas.planning_fingerprint(agenda_date)
            preview = daily.preview_day(agenda_date)
            if fingerprint != daily.agendas.planning_fingerprint(agenda_date):
                raise OperationalPlannerWebConflictError("Planner changed during preview. Try again.")
            if preview["existing"] and preview["existing"]["status"] != "draft":
                raise OperationalPlannerWebConflictError("Only an absent or draft agenda can receive a proposal.")
            return {"day": preview, "fingerprint": fingerprint, "semantic_hash": self._proposal_hash(preview)}
        except DailyAgendaError as error:
            raise _translate(error)
        except DailyAgendaRepositoryError as error:
            raise OperationalPlannerWebUnavailableError("Planner preview storage is unavailable.") from error

    def save_proposal(self, agenda_date, start, end, *, fingerprint, semantic_hash, windows=None, proposal_context=None, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        if proposal_context is not None:
            from personal_learning_assistant.repositories.sqlite.planner_proposal_repository import SQLitePlannerProposalRepository
            store = SQLitePlannerProposalRepository(self.daily.agendas.database_path)
            try:
                prior = store.by_command(proposal_context['command_id'])
            except DailyAgendaRepositoryError as error:
                raise OperationalPlannerWebUnavailableError('Proposal persistence requires the PAO migration.') from error
            if prior is not None:
                if prior['date'] != agenda_date or prior['semantic_hash'] != semantic_hash:
                    raise OperationalPlannerWebConflictError('Proposal command conflicts with its saved result.')
                return self.daily.agendas.get_agenda(agenda_date)
        current = self.preview_proposal(agenda_date, start, end, windows=windows, local_timezone=local_timezone, now=now, break_minutes=break_minutes)
        if current["fingerprint"] != fingerprint or current["semantic_hash"] != semantic_hash:
            raise OperationalPlannerWebConflictError("Planner changed since preview. Preview again before saving.")
        daily = self._proposal_daily(agenda_date, start, end, windows=windows, local_timezone=local_timezone, now=now, break_minutes=break_minutes)
        if proposal_context is not None:
            proposal_context = {**proposal_context,
                'policy_version': 'explicit-availability-v1',
                'candidate_refs': [{'kind': row['source_type'], 'id': row['source_id']}
                                   for row in (*current['day']['items'], *current['day'].get('review_needed', ()))],
                'review_needed': list(current['day'].get('review_needed', ())),
                'explanation_codes': {row['source_type'] + ':' + str(row['source_id']): row.get('reason_code', 'fixed_commitment')
                                      for row in (*current['day']['items'], *current['day'].get('review_needed', ()))},
                'source_versions': {'planning_fingerprint': fingerprint},
                'window_instants': [{'start': datetime.fromisoformat(agenda_date + 'T' + left).replace(tzinfo=daily.local_timezone).astimezone(timezone.utc).isoformat(),
                                     'end': datetime.fromisoformat(agenda_date + 'T' + right).replace(tzinfo=daily.local_timezone).astimezone(timezone.utc).isoformat()}
                                    for left, right in daily.free_windows[agenda_date]],
            }
        try:
            return daily.generate_day(agenda_date, expected_fingerprint=fingerprint, preview=current["day"], proposal_context=proposal_context)
        except DailyAgendaError as error:
            raise _translate(error)

    def generate_day(self, agenda_date):
        try:
            return self.daily.generate_day(agenda_date)
        except DailyAgendaError as error:
            raise _translate(error)

    def approve_day(self, agenda_date, *, expected_fingerprint=None, proposal_context=None, local_timezone="Asia/Kolkata", now=None, break_minutes=10):
        try:
            if proposal_context is not None:
                if ((expected_fingerprint is not None and expected_fingerprint != proposal_context.get('saved_fingerprint'))
                        or proposal_context.get('date') != agenda_date
                        or proposal_context.get('timezone') != local_timezone
                        or proposal_context.get('break_minutes') != break_minutes
                        or proposal_context.get('policy') != 'explicit-availability-v1'
                        or proposal_context.get('saved_fingerprint') != self.daily.agendas.planning_fingerprint(agenda_date)):
                    raise OperationalPlannerWebConflictError("Planner or availability context changed. Preview and save a fresh draft.")
                daily = self._proposal_daily(
                    agenda_date, proposal_context['start'], proposal_context['end'], windows=proposal_context.get('windows'),
                    local_timezone=local_timezone, now=now, break_minutes=break_minutes,
                )
                return daily.approve_day(agenda_date, expected_fingerprint=proposal_context['saved_fingerprint'])
            return self.daily.approve_day(agenda_date, expected_fingerprint=expected_fingerprint)
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
