#!/usr/bin/env python3
"""Characterize pinned planner defects using only TemporaryDirectory databases.

Usage: python reproduce_planning.py --repo /path/to/audit
No existing database is read or modified. Migrations apply only to new temp DBs.
Assertions distinguish repaired desired behavior from remaining defect witnesses.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--repo", type=Path, default=os.environ.get('REPO_ROOT'), help='Pinned source checkout (or REPO_ROOT env)')
p.add_argument("--output", type=Path, help='Optional JSON results file; otherwise stdout')
args = p.parse_args()
if not args.repo:
    p.error('--repo or REPO_ROOT is required')
repo = args.repo.resolve()
sys.path.insert(0, str(repo))
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.daily_agenda_service import build_daily_agenda_service
from personal_learning_assistant.services.operational_calendar_service import build_operational_calendar_service
from personal_learning_assistant.services.month_plan_import_service import build_month_plan_import_service
from personal_learning_assistant.repositories.sqlite.weekly_review_repository import SQLiteWeeklyReviewRepository

def dump(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as c, c:
        return '\n'.join(c.iterdump())

def task(c, ident, *, preferred=None, due=None, priority='P1', minutes=60):
    c.execute("INSERT INTO planner_tasks (id,title,priority,estimated_minutes,status,preferred_day,due_on,created_at,updated_at) VALUES (?,?,?,?,'backlog',?,?, '2026-09-30T00:00:00Z','2026-09-30T00:00:00Z')", (ident, ident, priority, minutes, preferred, due))

results = {}
with tempfile.TemporaryDirectory(prefix='anvaya-planning-audit-') as temp:
    root = Path(temp)
    db = root / 'scenario_b.db'
    apply_migrations(db)
    with closing(sqlite3.connect(db)) as c, c:
        task(c, 'future', preferred='2026-10-30')
    service = build_daily_agenda_service(db)
    service._now = lambda: '2026-09-30T00:00:00Z'
    service.free_windows = {'2026-10-01': [('06:00', '22:00')]}
    before = dump(db)
    preview = service.preview_day('2026-10-01')
    assert not any(r['source_id'] == 'future' for r in preview['tasks'])
    assert dump(db) == before
    with closing(sqlite3.connect(db)) as c, c:
        task(c, 'today', minutes=60)
    service.generate_day('2026-10-01')
    service.approve_day('2026-10-01')
    with closing(sqlite3.connect(db)) as c, c:
        c.execute("UPDATE planner_tasks SET title='changed after approval', estimated_minutes=90 WHERE id='today'")
    current = service.day_view('2026-10-01')
    saved_item = next(r for r in current['existing']['items'] if r['source_id']=='today')
    shown_item = next(r for r in current['tasks'] if r['source_id']=='today')
    assert saved_item['title'] == shown_item['title'] == 'today'
    assert saved_item['starts_at'] == shown_item['starts_at']
    results['scenario_B'] = {'preferred_day':'2026-10-30', 'preview_on':'2026-10-01',
        'actual_placement': None, 'future_task_excluded':True, 'read_logical_dump_unchanged': True,
        'approved_title':saved_item['title'], 'above_saved_preview_title':shown_item['title']}

    # B2 replaces the inverted C witness with desired no-initialization reads.
    import course_manager
    import learning_memory
    legacy = root / 'legacy' / 'data'
    course_manager.DATA_DIR = str(legacy)
    course_manager.COURSES_FILE = str(legacy / 'courses.json')
    learning_memory.DATA_DIR = str(legacy)
    learning_memory.MEMORY_FILE = str(legacy / 'learning_memory.json')
    assert not legacy.exists()
    course_manager.load_course_data()
    learning_memory.load_memory()
    assert not legacy.exists()
    results['scenario_C'] = {'created_by_read': False, 'missing_files_remain_missing': True}

    # Due marker is included as a fixed routine and then as a timed flexible task.
    db = root / 'due_and_rollover.db'
    apply_migrations(db)
    with closing(sqlite3.connect(db)) as c, c:
        task(c, 'due', due='2026-10-12', priority='P0')
        task(c, 'p0-two', priority='P0')
        task(c, 'p0-three', priority='P0')
    daily = build_daily_agenda_service(db)
    daily._now = lambda: '2026-09-30T00:00:00Z'
    daily.free_windows = {'2026-10-12': [('06:00', '22:00')]}
    preview = daily.preview_day('2026-10-12')
    duplicates = [r for r in preview['items'] if r['source_id']=='due']
    assert len(duplicates) == 1
    assert {(r['source_type'],r['item_kind']) for r in duplicates} == {('planner_task','task')}
    daily.generate_day('2026-10-12')
    daily.approve_day('2026-10-12')
    closed = daily.close_day('2026-10-12', {})
    tomorrow = closed['tomorrow_draft']
    dropped = [r['task_id'] for r in closed['rollover'] if r['decision']=='drop']
    assert dropped
    tomorrow_sources = {r['source_id'] for r in tomorrow['items'] if r['item_kind']=='task'}
    assert set(dropped) <= tomorrow_sources
    results['due_marker_duplicate'] = [{k:r[k] for k in ('item_kind','source_type','source_id','starts_at','reason')} for r in duplicates]
    results['rollover_policy_not_consumed'] = {'ledger':list(closed['rollover']), 'tomorrow_task_sources':sorted(tomorrow_sources), 'dropped_reappeared':dropped}

    # COUNT is global to recurrence, but current implementation restarts on each window.
    db = root / 'calendar.db'
    apply_migrations(db)
    with closing(sqlite3.connect(db)) as c, c:
        c.execute("INSERT INTO routine_templates (id,title,recurrence_rule,active_from,active_to,start_time,end_time,created_at,updated_at) VALUES ('count','COUNT three','RRULE:FREQ=DAILY;COUNT=3','2026-10-01','2026-10-31','21:45','21:55','x','x')")
        c.execute("INSERT INTO academic_events (id,event_kind,title,starts_at,ends_at,all_day,recurrence_rule,status,created_at,updated_at) VALUES ('recurring','class','Weekly class','2026-10-05T09:00:00','2026-10-05T10:00:00',0,'RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20261031','scheduled','x','x')")
    calendar = build_operational_calendar_service(db)
    month = calendar.view(view='month',anchor_date='2026-10-12')
    day = calendar.view(view='day',anchor_date='2026-10-12')
    assert len([r for r in month['items'] if r['id']=='count']) == 3
    assert not any(r['id']=='count' for r in day['items'])
    assert any(r['id']=='recurring' and r['date']=='2026-10-12' for r in month['items'])
    assert any(r['id']=='recurring' for r in day['items'])
    results['calendar_window_inconsistency'] = {'month_count_dates':[r['date'] for r in month['items'] if r['id']=='count'], 'day_count_dates':[r['date'] for r in day['items'] if r['id']=='count'], 'month_class_on_oct12':True, 'day_class_on_oct12':True}

    db = root / 'study_capacity.db'
    apply_migrations(db)
    with closing(sqlite3.connect(db)) as c, c:
        c.execute("INSERT INTO study_plans (id,kind,horizon,starts_on,ends_on,requested_minutes,allocated_minutes,engine_name,engine_version,created_at,updated_at) VALUES ('plan','weekly','week','2026-10-12','2026-10-12',540,540,'fixture','1','x','x')")
        for n in range(1,4):
            c.execute("INSERT INTO study_plan_items (id,plan_id,plan_date,ordinal,minutes,action) VALUES (?,'plan','2026-10-12',?,180,'Legacy study')",('s'+str(n),n))
            task(c,'t'+str(n),minutes=180)
    daily = build_daily_agenda_service(db)
    daily._now = lambda: '2026-09-30T00:00:00Z'
    daily.free_windows = {'2026-10-12': [('06:00', '22:00')]}
    preview = daily.preview_day('2026-10-12')
    assert len(preview['study'])==3 and not any(r['starts_at'] for r in preview['tasks'])
    assert len([r for r in preview['study'] if r['starts_at']])==3
    assert sum(r['planned_minutes'] for r in preview['study'])==540
    assert preview['summary']['scheduled_focus_minutes']==540
    saved = daily.generate_day('2026-10-12')
    daily.approve_day('2026-10-12')
    study_item = next(r for r in saved['items'] if r['source_id']=='s1')
    daily.update_item('2026-10-12',study_item['id'],status='completed',actual_minutes=180)
    with closing(sqlite3.connect(db)) as c, c:
        source_status = c.execute("SELECT status FROM study_plan_items WHERE id='s1'").fetchone()[0]
        engagement_count = c.execute('SELECT COUNT(*) FROM study_sessions').fetchone()[0]
    assert source_status=='planned' and engagement_count==0
    assert any(r['source_id']=='s1' for r in daily.preview_day('2026-10-12')['study'])
    results['study_capacity_and_completion'] = {'study_count':3,'timed_task_count':0,'timed_study_minutes':540,'summary_focus_minutes':540,'total_scheduled_focus_minutes':540,'completed_agenda_source_status':source_status,'engagement_rows':engagement_count,'completed_source_reappears_in_preview':True}

    # Changed revision repeats same ledger PK per plan/external ID (not per import).
    db = root / 'month_revision.db'
    apply_migrations(db)
    with closing(sqlite3.connect(db)) as c, c:
        c.execute("INSERT INTO courses(id,code,name,status,created_at,updated_at) VALUES('c-ma','MA103N','Linear Algebra','active','x','x')")
    monthly = build_month_plan_import_service(db)
    payload = (repo / 'tests/fixtures/phase7_5/month_plan_minimal.yaml').read_bytes()
    preview = monthly.preview('original.yaml',payload)
    assert preview['valid']
    monthly.approve('original.yaml',payload,preview['source_sha256'])
    with closing(sqlite3.connect(db)) as c, c:
        results['month_settings_projection_gap'] = {'preview_weekly_review_dates':preview['plan']['weekly_reviews'], 'persisted_weekly_review_rows':c.execute('SELECT COUNT(*) FROM weekly_reviews').fetchone()[0], 'preview_settings':preview['plan']['settings']}
    changed = payload.replace(b'Solve and explain one LU set.',b'Solve two LU sets independently.')
    assert changed != payload
    preview = monthly.preview('revision.yaml',changed)
    before = dump(db)
    try:
        monthly.approve('revision.yaml',changed,preview['source_sha256'])
    except Exception as error:
        results['month_revision_failure'] = {'error_type':type(error).__name__, 'safe_error':str(error), 'cause_type':type(error.__cause__).__name__, 'root_cause':str(error.__cause__.__cause__), 'rollback_logical_dump_unchanged':dump(db)==before}
        assert 'UNIQUE constraint failed: month_plan_import_items.id' in str(error.__cause__.__cause__)
        assert dump(db)==before
    else:
        raise AssertionError('Expected existing changed-revision ledger defect')

serialized = json.dumps(results, indent=2, default=str) + '\n'
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding='utf-8')
else:
    print(serialized, end='')
