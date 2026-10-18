from datetime import date
from types import SimpleNamespace

import pytest

from personal_learning_assistant.services.daily_agenda_service import DailyAgendaService
from personal_learning_assistant.services.operational_calendar_service import materialize_occurrences


def task(**changes):
    return dict(dict(id='task', title='Study', priority='P1', estimated_minutes=60), **changes)


def service(tasks=None, fixed=(), **kwargs):
    kwargs.setdefault("local_timezone", "UTC")
    return DailyAgendaService(
        SimpleNamespace(get_agenda=lambda day: None, rollover_for_date=lambda day: ()),
        SimpleNamespace(list_tasks=lambda **kw: tasks or [task()]),
        SimpleNamespace(list_study_items=lambda day: ()),
        SimpleNamespace(day_items=lambda day: fixed),
        now=lambda: '2026-10-16T08:00:01Z', **kwargs,
    )


def test_default_does_not_invent_availability():
    assert service().preview_day('2026-10-16')['tasks'][0]['starts_at'] is None


def test_future_preferred_date_not_selected():
    assert service([task(preferred_day='2026-10-19')]).preview_day('2026-10-16')['tasks'] == ()


@pytest.mark.parametrize('changes', [{'due_on': '2026-10-15'}, {'estimated_minutes': None}, {'estimated_minutes': 0}])
def test_impossible_or_unknown_duration_unscheduled(changes):
    item = service([task(**changes)], free_windows={'2026-10-16': [('06:00', '20:00')]}).preview_day('2026-10-16')['tasks'][0]
    assert item['starts_at'] is None


def test_clock_and_break_buffer():
    items = service([task(), task(id='two')], free_windows={'2026-10-16': [('06:00', '12:00')]}).preview_day('2026-10-16')['tasks']
    assert items[0]['starts_at'] == '2026-10-16T08:01:00'
    assert items[1]['starts_at'] == '2026-10-16T09:11:00'


@pytest.mark.parametrize('fixed', [dict(all_day=True), dict(start_time='09:00', end_time=''), dict(start_time='09:00', end_time='10:00')])
def test_fixed_commitments_block_capacity(fixed):
    event = dict(id='event', source='academic_event', title='Class', **fixed)
    item = service(fixed=[event], free_windows={'2026-10-16': [('09:00', '10:00')]}).preview_day('2026-10-16')['tasks'][0]
    assert item['starts_at'] is None


def test_past_day_has_no_slots():
    assert service(free_windows={'2026-10-15': [('09:00', '12:00')]}).preview_day('2026-10-15')['tasks'][0]['starts_at'] is None


def test_count_is_anchored_before_query_window():
    assert materialize_occurrences(recurrence_rule='FREQ=DAILY;COUNT=2', first_date='2026-10-01', window_start='2026-10-16', window_end='2026-10-17') == ()


def test_weekly_count_exclusions_do_not_reset_sequence():
    assert materialize_occurrences(recurrence_rule='FREQ=WEEKLY;BYDAY=MO,FR;COUNT=3', first_date='2026-10-02', window_start='2026-10-09', window_end='2026-10-16', excluded_dates=['2026-10-05']) == (date(2026, 10, 9),)


def test_recurring_event_retained_after_original_end(tmp_path):
    import sqlite3
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import SQLiteOperationalCalendarRepository
    from personal_learning_assistant.services.operational_calendar_service import OperationalCalendarService
    path = tmp_path / 'calendar.db'
    apply_migrations(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO academic_events (id,event_kind,title,starts_at,ends_at,all_day,recurrence_rule,status,created_at,updated_at) VALUES ('r','class','Class','2026-10-02T09:00:00','2026-10-02T10:00:00',0,'FREQ=WEEKLY;BYDAY=FR','scheduled','x','x')")
    items = OperationalCalendarService(SQLiteOperationalCalendarRepository(path)).day_items('2026-10-16')
    assert any(item['id'] == 'r' for item in items)


def test_multiday_commitment_remains_busy_on_middle_day():
    from personal_learning_assistant.services.operational_calendar_service import OperationalCalendarService
    row = dict(id='trip', title='Trip', event_kind='other', starts_at='2026-10-15T18:00:00', ends_at='2026-10-17T10:00:00', all_day=False)
    calendar = OperationalCalendarService(SimpleNamespace(list_academic_events=lambda *args: [row], list_routines=lambda: [], list_planner_tasks=lambda *args: [], list_assessments=lambda: []))
    items = calendar.day_items('2026-10-16')
    assert len(items) == 1
    assert items[0]['all_day'] is True


def test_local_clock_and_overlapping_windows_do_not_duplicate_slots():
    items = service([task(), task(id='two')], local_timezone='Asia/Kolkata', free_windows={'2026-10-16': [('12:00', '16:00'), ('13:00', '17:00')]}).preview_day('2026-10-16')['tasks']
    assert items[0]['starts_at'] == '2026-10-16T13:31:00'
    assert items[1]['starts_at'] == '2026-10-16T14:41:00'


def test_calendar_deadline_marker_is_not_a_fixed_commitment():
    marker = dict(id='task', source='task', title='Study', all_day=True)
    preview = service(fixed=[marker], free_windows={'2026-10-16': [('09:00', '12:00')]}).preview_day('2026-10-16')
    assert preview['fixed'] == ()
    assert preview['tasks'][0]['starts_at'] == '2026-10-16T09:00:00'


def test_dst_transition_day_requires_explicit_review():
    planner = service(local_timezone='America/New_York', free_windows={'2026-11-01': [('06:00', '12:00')]})
    assert planner.preview_day('2026-11-01')['tasks'][0]['starts_at'] is None


def test_recurring_multiday_spillover_blocks_next_day():
    from personal_learning_assistant.services.operational_calendar_service import OperationalCalendarService
    row = dict(id='trip', title='Trip', event_kind='other', starts_at='2026-10-15T18:00:00', ends_at='2026-10-17T10:00:00', all_day=False, recurrence_rule='FREQ=WEEKLY;BYDAY=TH')
    calendar = OperationalCalendarService(SimpleNamespace(list_academic_events=lambda *args: [row], list_routines=lambda: [], list_planner_tasks=lambda *args: [], list_assessments=lambda: []))
    for day in ('2026-10-16', '2026-10-23'):
        assert calendar.day_items(day)[0]['all_day'] is True


def test_offset_commitments_fail_closed_on_adjacent_local_day(tmp_path):
    from test_phase7_5_daily_agenda import _service
    import sqlite3
    planner, path = _service(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE academic_events SET starts_at='2026-10-15T23:30:00Z', ends_at='2026-10-16T00:30:00Z'")
    assert planner.calendar.day_items('2026-10-16')[0]['all_day'] is True
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE academic_events SET starts_at='2026-10-15T23:30:00Z', ends_at='2026-10-15T23:45:00Z'")
    assert planner.calendar.day_items('2026-10-16')[0]['all_day'] is True


def test_saved_study_and_tasks_share_capacity_and_deep_limit():
    planner = service([task(estimated_minutes=60)], free_windows={'2026-10-16': [('09:00','11:00')]})
    planner.calendar_repository.list_study_items = lambda day: [dict(id='s1',minutes=90,action='Revision')]
    preview = planner.preview_day('2026-10-16')
    assert preview['study'][0]['starts_at'] == '2026-10-16T09:00:00'
    assert preview['tasks'][0]['starts_at'] is None
    assert preview['summary']['scheduled_focus_minutes'] == 90
    planner.free_windows = {'2026-10-16': [('09:00','22:00')]}
    planner.calendar_repository.list_study_items = lambda day: [dict(id=f's{i}',minutes=60,action='Revision') for i in range(3)]
    preview = planner.preview_day('2026-10-16')
    assert len([r for r in preview['items'] if r.get('starts_at')]) == 3
    assert preview['tasks'][0]['starts_at'] is None


def test_due_p0_task_gets_capacity_before_saved_p1_study():
    planner = service([task(priority='P0',due_on='2026-10-16')], free_windows={'2026-10-16': [('09:00','12:30')]})
    planner.calendar_repository.list_study_items = lambda day: [dict(id=f's{i}',minutes=60,action='Revision') for i in range(3)]
    preview = planner.preview_day('2026-10-16')
    assert preview['tasks'][0]['starts_at'] == '2026-10-16T09:00:00'
    assert len([r for r in preview['study'] if r['starts_at']]) == 2
    assert preview['summary']['scheduled_focus_minutes'] == 180
