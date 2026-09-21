"""Task lifecycle and validation for the Phase 7.5.13 Operational Planner."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from personal_learning_assistant.repositories.sqlite.planner_task_repository import (
    PlannerTaskRepositoryError,
    PlannerTaskRepositoryNotFoundError,
    SQLitePlannerTaskRepository,
)


MAX_TITLE = 300
MAX_DESCRIPTION = 4000
_ALLOWED = {
    "backlog": {"planned", "scheduled", "skipped", "archived", "completed"},
    "planned": {"backlog", "scheduled", "in_progress", "skipped", "archived", "completed"},
    "scheduled": {"planned", "in_progress", "skipped", "archived", "completed"},
    "in_progress": {"planned", "scheduled", "skipped", "archived", "completed"},
    "skipped": {"backlog", "planned", "archived"},
    "completed": {"archived"},
    "archived": set(),
}


class OperationalTaskError(RuntimeError):
    """Base safe task-layer error."""


class OperationalTaskValidationError(OperationalTaskError):
    """Task input or transition is invalid."""


class OperationalTaskNotFoundError(OperationalTaskError):
    """Task does not exist."""


class OperationalTaskUnavailableError(OperationalTaskError):
    """Task persistence is unavailable."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _priority(value):
    token = str(value or "P1").strip().upper()
    if token not in {"P0", "P1", "P2"}:
        raise OperationalTaskValidationError("Priority must be P0, P1, or P2.")
    return token


def _minutes(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise OperationalTaskValidationError("Estimated minutes must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise OperationalTaskValidationError("Estimated minutes must be an integer.") from error
    if number < 0 or number > 1440:
        raise OperationalTaskValidationError("Estimated minutes are outside the accepted range.")
    return number


def _date(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise OperationalTaskValidationError("Due date must be YYYY-MM-DD.") from error


class OperationalTaskService:
    def __init__(self, repository, *, now=_now, id_factory=uuid.uuid4):
        self.repository = repository
        self._now = now
        self._id_factory = id_factory

    def tasks_workspace(self, *, status="", priority="", course_id=""):
        statuses = None
        if status:
            statuses = (status,)
        else:
            statuses = ("backlog", "planned", "scheduled", "in_progress", "skipped")
        try:
            tasks = self.repository.list_tasks(
                statuses=statuses,
                priority=priority or None,
                course_id=course_id or None,
            )
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("Tasks are temporarily unavailable.") from error
        return {
            "available": True,
            "tasks": tasks,
            "filters": {"status": status, "priority": priority, "course_id": course_id},
            "summary": {
                "open": len(tasks),
                "p0": sum(1 for task in tasks if task["priority"] == "P0"),
                "p1": sum(1 for task in tasks if task["priority"] == "P1"),
                "p2": sum(1 for task in tasks if task["priority"] == "P2"),
            },
        }

    def create_task(
        self,
        *,
        title,
        description="",
        priority="P1",
        estimated_minutes=None,
        due_on=None,
        preferred_day="",
        preferred_window="",
        rollover_policy="",
        course_id=None,
        topic_id=None,
        assessment_id=None,
    ):
        title = str(title or "").strip()
        if not title or len(title) > MAX_TITLE:
            raise OperationalTaskValidationError("Enter a valid task title.")
        description = str(description or "").strip()
        if len(description) > MAX_DESCRIPTION:
            raise OperationalTaskValidationError("Task description is too long.")
        now = self._now()
        row = {
            "id": str(self._id_factory()),
            "source_import_id": None,
            "external_id": None,
            "title": title,
            "description": description,
            "priority": _priority(priority),
            "course_id": course_id or None,
            "topic_id": topic_id or None,
            "assessment_id": assessment_id or None,
            "estimated_minutes": _minutes(estimated_minutes),
            "due_on": _date(due_on),
            "preferred_day": str(preferred_day or "").strip() or None,
            "preferred_window": str(preferred_window or "").strip() or None,
            "rollover_policy": str(rollover_policy or "").strip(),
            "status": "backlog",
            "created_at": now,
            "updated_at": now,
        }
        try:
            return self.repository.create_task(row)
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("The task could not be saved.") from error

    def transition(self, task_id, status, *, actual_minutes=None):
        status = str(status or "").strip()
        try:
            current = self.repository.get_task(task_id)
        except PlannerTaskRepositoryNotFoundError as error:
            raise OperationalTaskNotFoundError("Task was not found.") from error
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("Task is temporarily unavailable.") from error
        if status not in _ALLOWED:
            raise OperationalTaskValidationError("Unknown task status.")
        if status not in _ALLOWED.get(str(current["status"]), set()):
            raise OperationalTaskValidationError(
                "Task cannot move from {} to {}.".format(current["status"], status)
            )
        now = self._now()
        fields = {"status": status, "updated_at": now}
        if status == "completed":
            fields["completed_at"] = now
        if status == "archived":
            fields["archived_at"] = now
        try:
            return self.repository.update_task(task_id, fields, mark_manual=True)
        except PlannerTaskRepositoryNotFoundError as error:
            raise OperationalTaskNotFoundError("Task was not found.") from error
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("Task could not be updated.") from error

    def update_task(self, task_id, **changes):
        try:
            current = self.repository.get_task(task_id)
        except PlannerTaskRepositoryNotFoundError as error:
            raise OperationalTaskNotFoundError("Task was not found.") from error
        if str(current["status"]) == "archived":
            raise OperationalTaskValidationError("Archived tasks cannot be edited.")
        fields = {}
        if "title" in changes:
            title = str(changes["title"] or "").strip()
            if not title or len(title) > MAX_TITLE:
                raise OperationalTaskValidationError("Enter a valid task title.")
            fields["title"] = title
        if "description" in changes:
            description = str(changes["description"] or "").strip()
            if len(description) > MAX_DESCRIPTION:
                raise OperationalTaskValidationError("Task description is too long.")
            fields["description"] = description
        if "priority" in changes:
            fields["priority"] = _priority(changes["priority"])
        if "estimated_minutes" in changes:
            fields["estimated_minutes"] = _minutes(changes["estimated_minutes"])
        if "due_on" in changes:
            fields["due_on"] = _date(changes["due_on"])
        for field in ("preferred_day", "preferred_window", "rollover_policy"):
            if field in changes:
                fields[field] = str(changes[field] or "").strip() or None
        fields["updated_at"] = self._now()
        try:
            return self.repository.update_task(task_id, fields, mark_manual=True)
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("Task could not be updated.") from error


def build_operational_task_service(database_path="data/learning_assistant.db"):
    return OperationalTaskService(SQLitePlannerTaskRepository(database_path))
