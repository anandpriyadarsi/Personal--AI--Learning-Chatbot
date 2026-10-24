from __future__ import annotations

import sqlite3

import pytest

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def _service(tmp_path):
    from personal_learning_assistant.repositories.sqlite.daily_agenda_repository import (
        SQLiteDailyAgendaRepository,
    )
    from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
        SQLiteOperationalCalendarRepository,
    )
    from personal_learning_assistant.repositories.sqlite.planner_task_repository import (
        SQLitePlannerTaskRepository,
    )
    from personal_learning_assistant.services.daily_agenda_service import DailyAgendaService
    from personal_learning_assistant.services.operational_calendar_service import (
        OperationalCalendarService,
    )

    path = tmp_path / "daily.db"
    apply_migrations(path)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO planner_tasks "
        "(id,title,description,priority,estimated_minutes,status,rollover_policy,manual_revision,created_at,updated_at) "
        "VALUES ('p0','Important P0','','P0',60,'backlog','carry',0,'x','x')"
    )
    c.execute(
        "INSERT INTO planner_tasks "
        "(id,title,description,priority,estimated_minutes,status,rollover_policy,manual_revision,created_at,updated_at) "
        "VALUES ('p1','Important P1','','P1',45,'backlog','reconsider',0,'x','x')"
    )
    c.execute(
        "INSERT INTO planner_tasks "
        "(id,title,description,priority,estimated_minutes,status,rollover_policy,manual_revision,created_at,updated_at) "
        "VALUES ('p2','Optional P2','','P2',30,'backlog','backlog',0,'x','x')"
    )
    c.execute(
        "INSERT INTO academic_events "
        "(id,event_kind,title,starts_at,ends_at,all_day,status,created_at,updated_at) "
        "VALUES ('class','class','Morning class','2026-10-12T09:00:00','2026-10-12T10:00:00',0,'scheduled','x','x')"
    )
    c.commit()
    c.close()

    agenda = SQLiteDailyAgendaRepository(path)
    tasks = SQLitePlannerTaskRepository(path)
    cal_repo = SQLiteOperationalCalendarRepository(path)
    cal = OperationalCalendarService(cal_repo)
    return DailyAgendaService(agenda, tasks, cal_repo, cal), path


def test_preview_is_side_effect_free(tmp_path):
    service, path = _service(tmp_path)
    preview = service.preview_day("2026-10-12")
    assert preview["date"] == "2026-10-12"
    c = sqlite3.connect(path)
    assert c.execute("SELECT COUNT(*) FROM daily_agendas").fetchone()[0] == 0
    c.close()


def test_generate_approve_complete_and_close_with_bounded_rollover(tmp_path):
    service, path = _service(tmp_path)
    agenda = service.generate_day("2026-10-12")
    assert agenda["status"] == "draft"
    agenda = service.approve_day("2026-10-12")
    assert agenda["status"] == "approved"

    p0_item = next(item for item in agenda["items"] if item.get("source_id") == "p0")
    service.update_item("2026-10-12", p0_item["id"], status="completed", actual_minutes=55)

    result = service.close_day(
        "2026-10-12",
        {
            "learned": "LU verification matters",
            "biggest_confusion": "Pivoting",
            "energy_1_to_5": "4",
            "data_science_ai_assistance_level": "2",
            "tomorrow_first_task": "P1",
            "carry_task_ids": ["p1"],
        },
    )
    assert result["agenda"]["status"] == "closed"
    decisions = {row["task_id"]: row["decision"] for row in result["rollover"]}
    assert "p0" not in decisions
    assert decisions.get("p1") == "carry"
    assert decisions.get("p2") == "backlog"

    c = sqlite3.connect(path)
    assert c.execute("SELECT status FROM planner_tasks WHERE id='p0'").fetchone()[0] == "completed"
    assert c.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 3
    assert c.execute("SELECT COUNT(*) FROM task_rollover_events WHERE decision='carry'").fetchone()[0] <= 1
    c.close()


def test_closed_day_cannot_be_closed_twice(tmp_path):
    from personal_learning_assistant.services.daily_agenda_service import DailyAgendaConflictError

    service, _path = _service(tmp_path)
    service.generate_day("2026-10-12")
    service.approve_day("2026-10-12")
    service.close_day("2026-10-12", {})
    with pytest.raises(DailyAgendaConflictError):
        service.close_day("2026-10-12", {})


def test_explicit_carry_only_respects_backlog_and_preserves_source_ids(tmp_path):
    from personal_learning_assistant.services.daily_agenda_service import DailyAgendaValidationError
    service, path = _service(tmp_path)
    service.generate_day("2026-10-12")
    service.approve_day("2026-10-12")
    with pytest.raises(DailyAgendaValidationError):
        service.close_day("2026-10-12", {"carry_task_ids": ["fake"]})
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM task_rollover_events").fetchone()[0] == 0
    closed = service.close_day("2026-10-12", {"carry_task_ids": ["p1"]})
    decisions = {r["task_id"]: r["decision"] for r in closed["rollover"]}
    assert decisions == {"p0": "backlog", "p1": "carry", "p2": "backlog"}
    tomorrow = closed["tomorrow_draft"]
    assert tomorrow and tomorrow["status"] == "draft"
    tomorrow_ids = {r["source_id"] for r in tomorrow["items"] if r["item_kind"] == "task"}
    assert "p1" in tomorrow_ids and "p0" not in tomorrow_ids and "p2" not in tomorrow_ids
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 3
        assert c.execute("SELECT COUNT(*) FROM task_rollover_events").fetchone()[0] == 3


def test_completed_canonical_study_is_one_self_reported_receipt(tmp_path):
    from personal_learning_assistant.services.daily_agenda_service import DailyAgendaConflictError
    service, path = _service(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute(
            "INSERT INTO study_plans "
            "(id,kind,horizon,starts_on,ends_on,requested_minutes,allocated_minutes,engine_name,engine_version,created_at,updated_at) "
            "VALUES ('study-p','weekly','week','2026-10-12','2026-10-12',40,40,'fixture','1','x','x')"
        )
        c.execute(
            "INSERT INTO study_plan_items "
            "(id,plan_id,plan_date,ordinal,minutes,action) "
            "VALUES ('study-i','study-p','2026-10-12',1,40,'Review source')"
        )
    draft = service.generate_day("2026-10-12")
    study = next(r for r in draft["items"] if r.get("source_id") == "study-i")
    with pytest.raises(DailyAgendaConflictError):
        service.update_item("2026-10-12", study["id"], status="completed", actual_minutes=25)
    service.approve_day("2026-10-12")
    service.update_item("2026-10-12", study["id"], status="completed", actual_minutes=25)
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT status FROM study_plan_items WHERE id='study-i'").fetchone()[0] == "completed"
        session = c.execute(
            "SELECT duration_minutes,plan_item_id,outcome,confidence FROM study_sessions WHERE plan_item_id='study-i'"
        ).fetchone()
        assert session == (25, "study-i", "self_reported_planner_completion", None)
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
    with pytest.raises(DailyAgendaConflictError):
        service.update_item("2026-10-12", study["id"], status="completed", actual_minutes=25)
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM study_sessions WHERE plan_item_id='study-i'").fetchone()[0] == 1
    assert all(r["source_id"] != "study-i" for r in service.preview_day("2026-10-12")["study"])
