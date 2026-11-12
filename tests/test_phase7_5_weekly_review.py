from __future__ import annotations

import sqlite3

import pytest

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def _service(tmp_path):
    from personal_learning_assistant.repositories.sqlite.weekly_review_repository import (
        SQLiteWeeklyReviewRepository,
    )
    from personal_learning_assistant.services.weekly_review_service import WeeklyReviewService

    path = tmp_path / "weekly.db"
    apply_migrations(path)
    from pathlib import Path
    c = sqlite3.connect(path)
    c.executescript(Path('personal_learning_assistant/repositories/sqlite/optional_migrations/0018_pao_execution.sql').read_text())
    c.execute(
        "INSERT INTO daily_agendas "
        "(id,agenda_date,day_mode,status,generated_at,created_at,updated_at) "
        "VALUES ('d1','2026-10-12','normal','closed','x','x','x')"
    )
    c.execute(
        "INSERT INTO daily_agenda_items "
        "(id,agenda_id,ordinal,item_kind,source_type,title,priority,planned_minutes,actual_minutes,status,created_at,updated_at) "
        "VALUES ('i1','d1',1,'task','planner_task','Task','P0',60,50,'completed','x','x')"
    )
    c.execute("UPDATE daily_agendas SET approved_at='2026-10-11T12:00:00Z'")
    c.execute("UPDATE daily_agenda_items SET starts_at='2026-10-12T09:00:00Z',ends_at='2026-10-12T10:00:00Z'")
    c.commit()
    c.close()
    return WeeklyReviewService(SQLiteWeeklyReviewRepository(path)), path


def test_weekly_review_aggregates_and_closes(tmp_path):
    service, _path = _service(tmp_path)
    workspace = service.workspace("2026-10-18")
    assert workspace["evidence"]["planned_items"] == 1
    assert workspace["evidence"]["completed_items"] == 1
    assert workspace["evidence"]["planned_focus_minutes"] == 60
    assert workspace["evidence"]["actual_focus_minutes"] == 50

    review = service.save(
        "2026-10-18",
        {
            "what_worked": "Library",
            "what_failed": "Too much optional work",
            "next_priority_1": "Academics",
            "next_priority_2": "Coding",
            "next_priority_3": "Sleep",
        },
        close=True,
    )
    assert review["closed_at"]


def test_closed_week_rejects_second_write(tmp_path):
    from personal_learning_assistant.services.weekly_review_service import WeeklyReviewConflictError

    service, _path = _service(tmp_path)
    service.save("2026-10-18", {}, close=True)
    with pytest.raises(WeeklyReviewConflictError):
        service.save("2026-10-18", {"what_worked": "changed"}, close=False)
