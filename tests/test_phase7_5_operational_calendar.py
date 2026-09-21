from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def _db(tmp_path):
    path = tmp_path / "calendar.db"
    apply_migrations(path)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO courses "
        "(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c-ma','MA103N','Linear Algebra','active','','x','x',NULL)"
    )
    c.execute(
        "INSERT INTO assessments "
        "(id,course_id,assessment_type,title,due_on,due_time,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('a-mid','c-ma','mid_semester','MA103N Mid-Sem',NULL,NULL,'pending','','x','x',NULL)"
    )
    c.commit()
    c.close()
    return path


def test_supported_recurrence_handles_excluded_and_additional_dates():
    from personal_learning_assistant.services.operational_calendar_service import (
        materialize_occurrences,
    )

    dates = materialize_occurrences(
        recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=FR;UNTIL=20261031",
        first_date="2026-10-02",
        window_start="2026-10-01",
        window_end="2026-10-31",
        excluded_dates=("2026-10-02", "2026-10-09"),
        additional_dates=("2026-10-29",),
    )
    assert date(2026, 10, 2) not in dates
    assert date(2026, 10, 9) not in dates
    assert date(2026, 10, 29) in dates
    assert len(dates) == len(set(dates))


def test_unsupported_rrule_component_is_rejected():
    from personal_learning_assistant.services.operational_calendar_service import (
        OperationalCalendarValidationError,
        materialize_occurrences,
    )

    with pytest.raises(OperationalCalendarValidationError):
        materialize_occurrences(
            recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=MO;BYHOUR=9",
            first_date="2026-10-05",
            window_start="2026-10-01",
            window_end="2026-10-31",
        )


def test_calendar_materializes_event_and_routine_without_row_expansion(tmp_path):
    from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
        SQLiteOperationalCalendarRepository,
    )
    from personal_learning_assistant.services.operational_calendar_service import (
        OperationalCalendarService,
    )

    path = _db(tmp_path)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO academic_events "
        "(id,course_id,event_kind,title,starts_at,all_day,recurrence_rule,status,"
        "source_entity_type,source_entity_id,created_at,updated_at) "
        "VALUES ('e1','c-ma','class','MA103N Class','2026-10-05T09:00:00',0,"
        "'RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20261031','scheduled','test','e1','x','x')"
    )
    c.execute(
        "INSERT INTO routine_templates "
        "(id,title,priority,recurrence_rule,active_from,active_to,start_time,end_time,"
        "status,manual_revision,created_at,updated_at) "
        "VALUES ('r1','Daily Review','P1','RRULE:FREQ=DAILY;COUNT=3','2026-10-01','2026-10-31',"
        "'21:45','21:55','active',0,'x','x')"
    )
    c.commit()
    c.close()

    service = OperationalCalendarService(SQLiteOperationalCalendarRepository(path))
    view = service.view(view="month", anchor_date="2026-10-15")
    assert any(item["title"] == "MA103N Class" for item in view["items"])
    assert sum(1 for item in view["items"] if item["title"] == "Daily Review") == 3

    c = sqlite3.connect(path)
    assert c.execute("SELECT COUNT(*) FROM academic_events").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM routine_templates").fetchone()[0] == 1
    c.close()


def test_confirmed_exam_slot_creates_real_event_and_rejects_overlap(tmp_path):
    from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
        SQLiteOperationalCalendarRepository,
    )
    from personal_learning_assistant.services.operational_calendar_service import (
        OperationalCalendarConflictError,
        OperationalCalendarService,
    )

    path = _db(tmp_path)
    service = OperationalCalendarService(SQLiteOperationalCalendarRepository(path))
    result = service.schedule_assessment(
        "a-mid",
        due_on="2026-10-08",
        start_time="09:00",
        end_time="10:00",
        venue="Room 1",
    )
    assert result["date"] == "2026-10-08"

    c = sqlite3.connect(path)
    assert c.execute("SELECT due_on FROM assessments WHERE id='a-mid'").fetchone()[0] == "2026-10-08"
    assert c.execute("SELECT COUNT(*) FROM academic_events WHERE reference_id='a-mid'").fetchone()[0] == 1
    c.close()

    with pytest.raises(OperationalCalendarConflictError):
        service.schedule_assessment(
            "a-mid",
            due_on="2026-10-08",
            start_time="09:15",
            end_time="09:45",
            venue="Room 2",
        )
