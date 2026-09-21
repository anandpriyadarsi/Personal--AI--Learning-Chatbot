from __future__ import annotations

import sqlite3

import pytest

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def _service(tmp_path):
    from personal_learning_assistant.services.operational_task_service import (
        OperationalTaskService,
    )
    from personal_learning_assistant.repositories.sqlite.planner_task_repository import (
        SQLitePlannerTaskRepository,
    )

    path = tmp_path / "tasks.db"
    apply_migrations(path)
    return OperationalTaskService(SQLitePlannerTaskRepository(path)), path


def test_task_create_complete_and_archive(tmp_path):
    service, _path = _service(tmp_path)
    task = service.create_task(
        title="Solve LU set",
        priority="P0",
        estimated_minutes="45",
        due_on="2026-10-05",
    )
    assert task["status"] == "backlog"
    completed = service.transition(task["id"], "completed")
    assert completed["status"] == "completed"
    assert completed["completed_at"]
    archived = service.transition(task["id"], "archived")
    assert archived["status"] == "archived"


def test_task_validation_rejects_bad_priority_and_negative_duration(tmp_path):
    from personal_learning_assistant.services.operational_task_service import (
        OperationalTaskValidationError,
    )

    service, _path = _service(tmp_path)
    with pytest.raises(OperationalTaskValidationError):
        service.create_task(title="x", priority="P9")
    with pytest.raises(OperationalTaskValidationError):
        service.create_task(title="x", estimated_minutes="-1")


def test_task_transition_rejects_archived_mutation(tmp_path):
    from personal_learning_assistant.services.operational_task_service import (
        OperationalTaskValidationError,
    )

    service, _path = _service(tmp_path)
    task = service.create_task(title="x")
    service.transition(task["id"], "archived")
    with pytest.raises(OperationalTaskValidationError):
        service.update_task(task["id"], title="changed")
