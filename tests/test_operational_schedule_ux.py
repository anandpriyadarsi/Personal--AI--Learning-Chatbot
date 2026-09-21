from __future__ import annotations

import sqlite3

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def _db(tmp_path):
    path = tmp_path / "operational-ux.db"
    apply_migrations(path)
    return path


def test_user_can_create_edit_and_pause_recurring_schedule(tmp_path):
    from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
        SQLiteOperationalCalendarRepository,
    )
    from personal_learning_assistant.services.operational_calendar_service import (
        OperationalCalendarService,
    )

    path = _db(tmp_path)
    service = OperationalCalendarService(SQLiteOperationalCalendarRepository(path))

    created = service.create_routine(
        title="Swimming",
        category="health",
        priority="P1",
        frequency="weekly",
        weekdays=("TU", "TH", "SA"),
        active_from="2026-10-01",
        active_to="2026-10-31",
        start_time="17:30",
        end_time="18:30",
        duration_minutes="60",
        preferred_window="evening",
        preferred_location="NITK pool",
        condition_text="Skip on exam day",
    )

    assert created["status"] == "active"
    assert created["manual_revision"] == 1
    assert "FREQ=WEEKLY" in created["recurrence_rule"]
    assert "BYDAY=TU,TH,SA" in created["recurrence_rule"]

    updated = service.update_routine(
        created["id"],
        title="Swimming practice",
        category="health",
        priority="P1",
        frequency="weekly",
        weekdays=("TU", "TH"),
        active_from="2026-10-01",
        active_to="2026-10-31",
        start_time="18:00",
        end_time="19:00",
        duration_minutes="60",
        preferred_window="evening",
        preferred_location="NITK pool",
        condition_text="Skip on exam day",
    )
    assert updated["title"] == "Swimming practice"
    assert updated["manual_revision"] == 2

    paused = service.set_routine_status(created["id"], "paused")
    assert paused["status"] == "paused"

    workspace = service.routines_workspace()
    assert workspace["summary"]["paused"] == 1


def test_generated_daily_agenda_study_block_is_visible_on_calendar(tmp_path):
    from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
        SQLiteOperationalCalendarRepository,
    )
    from personal_learning_assistant.services.operational_calendar_service import (
        OperationalCalendarService,
    )

    path = _db(tmp_path)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO daily_agendas "
        "(id,agenda_date,day_mode,status,generated_at,approved_at,closed_at,created_at,updated_at) "
        "VALUES ('agenda-1','2026-10-05','normal','approved','x','x',NULL,'x','x')"
    )
    c.execute(
        "INSERT INTO daily_agenda_items "
        "(id,agenda_id,ordinal,item_kind,source_type,source_id,title,priority,"
        "starts_at,ends_at,planned_minutes,actual_minutes,status,reason,created_at,updated_at,completed_at) "
        "VALUES ('item-1','agenda-1',1,'study','study_plan_item','sp-1',"
        "'MA103N · LU practice','P1','2026-10-05T19:00:00','2026-10-05T19:45:00',"
        "45,NULL,'planned','','x','x',NULL)"
    )
    c.commit()
    c.close()

    service = OperationalCalendarService(SQLiteOperationalCalendarRepository(path))
    view = service.view(view="month", anchor_date="2026-10-15")

    matches = [
        item for item in view["items"]
        if item["source"] == "daily_agenda" and item["title"] == "MA103N · LU practice"
    ]
    assert len(matches) == 1
    assert matches[0]["start_time"] == "19:00"
    assert matches[0]["planned_minutes"] == 45
    assert matches[0]["agenda_status"] == "approved"


def test_recurring_schedule_routes_use_planner_service_boundary():
    from personal_learning_assistant.ui.web import create_app

    calls = []

    class FakePlanner:
        def routines_workspace(self):
            return {
                "available": True,
                "routines": (),
                "summary": {"active": 0, "paused": 0},
            }

        def create_routine(self, **payload):
            calls.append(("create", payload))
            return {"id": "r1"}

        def update_routine(self, routine_id, **payload):
            calls.append(("update", routine_id, payload))
            return {"id": routine_id}

        def set_routine_status(self, routine_id, status):
            calls.append(("status", routine_id, status))
            return {"id": routine_id, "status": status}

    app = create_app(
        {
            "TESTING": True,
            "OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY": lambda: FakePlanner(),
        }
    )
    client = app.test_client()

    assert client.get("/planning/routines").status_code == 200

    response = client.post(
        "/planning/routines",
        data={
            "title": "Swimming",
            "category": "health",
            "priority": "P1",
            "frequency": "weekly",
            "weekdays": ["TU", "TH"],
            "active_from": "2026-10-01",
            "active_to": "2026-10-31",
            "start_time": "18:00",
            "end_time": "19:00",
            "duration_minutes": "60",
        },
    )
    assert response.status_code == 303
    assert calls[0][0] == "create"
    assert calls[0][1]["weekdays"] == ("TU", "TH")

    response = client.post(
        "/planning/routines/r1/status",
        data={"status": "paused"},
    )
    assert response.status_code == 303
    assert calls[-1] == ("status", "r1", "paused")
