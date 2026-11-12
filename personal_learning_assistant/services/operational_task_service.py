"""Task lifecycle and validation for the Phase 7.5.13 Operational Planner."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from personal_learning_assistant.repositories.sqlite.planner_task_repository import (
    PlannerTaskRepositoryError,
    PlannerTaskRepositoryConflictError,
    PlannerTaskRepositoryNotFoundError,
    SQLitePlannerTaskRepository,
)


MAX_TITLE = 300
MAX_DESCRIPTION = 4000
MAX_EXTERNAL_ID = 240
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


class OperationalTaskConflictError(OperationalTaskError):
    """Manual study context conflicts with current identity or a prior receipt."""


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


_WEEKDAYS = ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')


def _preferred_day(value):
    text = str(value or '').strip()
    if not text or text.lower() == 'none':
        return None
    if text.title() in _WEEKDAYS:
        return text.title()
    try:
        if len(text) != 10:
            raise ValueError()
        return datetime.strptime(text, '%Y-%m-%d').date().isoformat()
    except ValueError as error:
        raise OperationalTaskValidationError('Preferred day must be a date (YYYY-MM-DD), weekday, or none.') from error


class OperationalTaskService:
    def __init__(self, repository, *, now=_now, id_factory=uuid.uuid4):
        self.repository = repository
        self._now = now
        self._id_factory = id_factory

    def tasks_workspace(self, *, status="", priority="", course_id=""):
        if status not in {'', 'all', *_ALLOWED}:
            raise OperationalTaskValidationError('Choose a valid task status.')
        statuses = None if status == 'all' else ((status,) if status else
            ('backlog', 'planned', 'scheduled', 'in_progress', 'skipped'))
        try:
            tasks = self.repository.list_tasks(statuses=statuses, priority=priority or None,
                                               course_id=course_id or None)
            catalogue = self.repository.capture_catalogue()
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError('Tasks are temporarily unavailable.') from error
        labels = {c['id']: c['code'] + ' · ' + c['name'] for c in catalogue['courses']}
        tasks = tuple(dict(task) for task in tasks)
        for task in tasks:
            from urllib.parse import quote
            task['source_links'] = [dict(url='/academic-evidence/learning/'+quote(ref['identifier'],safe='')+'/'+quote(ref['revision_key'],safe=''),label='Open linked learning source') for ref in task.get('sources',()) if ref['owner']=='learning' and ref['kind']=='module' and ref['revision_key'].isdigit()]
            task['source_links'] += [dict(url='/planning/source/obsidian/'+quote(ref['identifier'],safe='')+'?sha256='+quote(ref.get('sha256') or '',safe=''),label='Open linked Markdown version') for ref in task.get('sources',()) if ref['owner']=='obsidian' and ref['kind']=='markdown']
            task['allowed_transitions'] = tuple(sorted(_ALLOWED.get(task['status'], ())))
            task['course_label'] = labels.get(task.get('course_id'), 'Course unavailable' if task.get('course_id') else 'No course linked')
            try:
                _preferred_day(task.get('preferred_day'))
                task['timing_needs_review'] = False
            except OperationalTaskValidationError:
                task['timing_needs_review'] = True
        return {
            "available": True,
            "catalogue": catalogue,
            "tasks": tasks,
            "filters": {"status": status, "priority": priority, "course_id": course_id},
            "summary": {
                "open": sum(t["status"] not in {"completed", "archived"} for t in tasks),
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
        external_id=None,
        _study_context=None,
        _intent_id=None,
        _source_refs=(),
    ):
        title = str(title or "").strip()
        if not title or len(title) > MAX_TITLE:
            raise OperationalTaskValidationError("Enter a valid task title.")
        description = str(description or "").strip()
        if len(description) > MAX_DESCRIPTION:
            raise OperationalTaskValidationError("Task description is too long.")
        external_id = str(external_id or "").strip() or None
        if external_id is not None:
            if len(external_id) > MAX_EXTERNAL_ID or not external_id.startswith(
                "assessment-recovery:"
            ):
                raise OperationalTaskValidationError(
                    "Task external ID is not an accepted internal recovery reference."
                )
        for reference in (course_id, topic_id, assessment_id):
            if reference not in (None, '') and (not isinstance(reference, str) or
                    not 1 <= len(reference) <= 120 or reference != reference.strip()):
                raise OperationalTaskValidationError('Choose exact course, topic, and assessment IDs from the catalogue.')
        now = self._now()
        row = {
            "id": (str(uuid.uuid5(uuid.NAMESPACE_URL, "anvaya:manual-study:"+_intent_id))
                   if _intent_id is not None else str(self._id_factory())),
            "source_import_id": None,
            "external_id": external_id,
            "title": title,
            "description": description,
            "priority": _priority(priority),
            "course_id": course_id or None,
            "topic_id": topic_id or None,
            "assessment_id": assessment_id or None,
            "estimated_minutes": _minutes(estimated_minutes),
            "due_on": _date(due_on),
            "preferred_day": _preferred_day(preferred_day),
            "preferred_window": str(preferred_window or "").strip() or None,
            "rollover_policy": str(rollover_policy or "").strip(),
            "status": "backlog",
            "created_at": now,
            "updated_at": now,
        }
        try:
            return (self.repository.create_task(row, study_context=_study_context, source_refs=_source_refs)
                    if _study_context is not None or _source_refs else self.repository.create_task(row))
        except PlannerTaskRepositoryConflictError as error:
            raise OperationalTaskConflictError(str(error)) from error
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("The task could not be saved.") from error

    def create_manual_study_task(self, *, intent_id, title, description, course_id,
                                 topic_id, topic_name=None, estimated_minutes=30, due_on=None, source_refs=()):
        """One explicit user intent, one owner receipt; never recovery eligibility."""
        try:
            parsed=uuid.UUID(str(intent_id))
        except (ValueError,TypeError,AttributeError) as error:
            raise OperationalTaskValidationError('A canonical study intent UUID is required.') from error
        if str(parsed)!=intent_id:
            raise OperationalTaskValidationError('A canonical study intent UUID is required.')
        if (type(estimated_minutes) is not int or not 1<=estimated_minutes<=180 or
                not isinstance(course_id,str) or not 1<=len(course_id)<=120 or
                not isinstance(topic_id,str) or not 1<=len(topic_id)<=120):
            raise OperationalTaskValidationError('Choose exact course/topic and 1–180 practice minutes.')
        return self.create_task(title=title,description=description,priority='P2',
            course_id=course_id,topic_id=topic_id,estimated_minutes=estimated_minutes,due_on=due_on,
            _study_context={'course_id':course_id,'topic_id':topic_id,'topic_name':topic_name},
            _intent_id=intent_id, _source_refs=source_refs)

    def create_assessment_recovery_task(
        self,
        recommendation_id,
        *,
        title,
        description="",
        priority="P1",
        estimated_minutes=None,
        due_on=None,
        course_id=None,
        topic_id=None,
        assessment_id=None,
    ):
        external_id = "assessment-recovery:{}".format(str(recommendation_id))
        try:
            return self.repository.get_task_by_external_id(external_id)
        except PlannerTaskRepositoryNotFoundError:
            pass
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError(
                "Recovery task lookup is temporarily unavailable."
            ) from error

        try:
            return self.create_task(
                title=title,
                description=description,
                priority=priority,
                estimated_minutes=estimated_minutes,
                due_on=due_on,
                course_id=course_id,
                topic_id=topic_id,
                assessment_id=assessment_id,
                external_id=external_id,
            )
        except OperationalTaskUnavailableError as error:
            # If a concurrent/retried Apply already created the unique task,
            # return it instead of duplicating planner work.
            try:
                return self.repository.get_task_by_external_id(external_id)
            except PlannerTaskRepositoryError:
                raise error

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
            return self.repository.update_task(task_id, fields, mark_manual=True, expected=current)
        except PlannerTaskRepositoryNotFoundError as error:
            raise OperationalTaskNotFoundError("Task was not found.") from error
        except PlannerTaskRepositoryConflictError as error:
            raise OperationalTaskConflictError(str(error)) from error
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("Task could not be updated.") from error

    def update_task(self, task_id, expected_revision=None, **changes):
        try:
            current = self.repository.get_task(task_id)
        except PlannerTaskRepositoryNotFoundError as error:
            raise OperationalTaskNotFoundError("Task was not found.") from error
        if str(current["status"]) == "archived":
            raise OperationalTaskValidationError("Archived tasks cannot be edited.")
        if expected_revision is not None:
            try:
                if int(expected_revision) != current.get('revision', current['manual_revision']):
                    raise OperationalTaskConflictError('Task changed. Refresh before editing.')
            except (ValueError, TypeError) as error:
                raise OperationalTaskValidationError('A valid task revision is required.') from error
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
                fields[field] = _preferred_day(changes[field]) if field == "preferred_day" else str(changes[field] or "").strip() or None
        fields["updated_at"] = self._now()
        try:
            return self.repository.update_task(task_id, fields, mark_manual=True, expected=current)
        except PlannerTaskRepositoryConflictError as error:
            raise OperationalTaskConflictError(str(error)) from error
        except PlannerTaskRepositoryError as error:
            raise OperationalTaskUnavailableError("Task could not be updated.") from error


def build_operational_task_service(database_path="data/learning_assistant.db"):
    return OperationalTaskService(SQLitePlannerTaskRepository(database_path))
