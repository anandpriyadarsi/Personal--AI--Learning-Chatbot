"""Validated explicit work commands; never grading or inferred learning."""
from datetime import datetime, timezone
from personal_learning_assistant.repositories.sqlite.planner_execution_repository import SQLitePlannerExecutionRepository
from personal_learning_assistant.repositories.sqlite.planner_task_repository import PlannerTaskRepositoryError, PlannerTaskRepositoryConflictError, PlannerTaskRepositoryNotFoundError
from .operational_task_service import OperationalTaskValidationError, OperationalTaskConflictError, OperationalTaskUnavailableError, OperationalTaskNotFoundError


class PlannerExecutionService:
    def __init__(self, database_path, *, now=None):
        self.repository = SQLitePlannerExecutionRepository(database_path)
        self._now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def command(self, task_id, *, expected_revision, command_id, status=None, actual_minutes=None,
                occurred_at=None, agenda_item_id=None, note='', supersedes_id=None):
        try:
            revision = int(expected_revision)
            minutes = None if actual_minutes in (None, '') else int(actual_minutes)
        except (ValueError, TypeError) as error:
            raise OperationalTaskValidationError('Enter a valid revision and whole minutes.') from error
        values = dict(expected_revision=revision, command_id=command_id,
                      occurred_at=occurred_at or self._now(), actual_minutes=minutes,
                      agenda_item_id=agenda_item_id, note=str(note or '').strip())
        try:
            if status is None:
                return self.repository.log_progress(task_id, **values, supersedes_id=supersedes_id)
            return self.repository.transition_task(task_id, target_status=status, **values)
        except PlannerTaskRepositoryConflictError as error:
            raise OperationalTaskConflictError(str(error)) from error
        except PlannerTaskRepositoryNotFoundError as error:
            raise OperationalTaskNotFoundError(str(error)) from error
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError('Activate PAO storage before recording work.') from error
