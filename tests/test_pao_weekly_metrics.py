import sqlite3
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.weekly_review_repository import SQLiteWeeklyReviewRepository


def database(tmp_path):
    path = tmp_path / 'evidence.db'
    apply_migrations(path)
    return path


def test_deadlines_without_agendas_use_review_clock(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_tasks(id,title,due_on,created_at,updated_at) VALUES ('t','Due','2026-10-13','x','x')")
    evidence = SQLiteWeeklyReviewRepository(path).aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-15T12:00:00Z')
    assert evidence['missed_deadline_count'] == 1
    assert evidence['actual_focus_minutes'] is None


def test_closed_draft_and_unallocated_items_excluded(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO daily_agendas(id,agenda_date,status,generated_at,created_at,updated_at) VALUES ('a','2026-10-12','closed','x','x','x')")
        c.execute("INSERT INTO daily_agenda_items(id,agenda_id,ordinal,item_kind,title,planned_minutes,created_at,updated_at) VALUES ('i','a',1,'task','Draft',60,'x','x')")
    evidence = SQLiteWeeklyReviewRepository(path).aggregate_period('2026-10-12','2026-10-18')
    assert evidence['planned_focus_minutes'] == 0
    assert evidence['planned_items'] == 0


def test_null_zero_approval_allocation_and_log_dedup(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO daily_agendas(id,agenda_date,status,approved_at,generated_at,created_at,updated_at) VALUES ('a','2026-10-12','approved','2026-10-11T12:00:00Z','x','x','x')")
        c.execute("INSERT INTO daily_agenda_items(id,agenda_id,ordinal,item_kind,title,planned_minutes,starts_at,ends_at,actual_minutes,created_at,updated_at) VALUES ('i','a',1,'manual','Study',60,'2026-10-12T09:00:00Z','2026-10-12T10:00:00Z',0,'x','x')")
        c.execute("CREATE TABLE IF NOT EXISTS planner_work_logs(id TEXT PRIMARY KEY, task_id TEXT, agenda_item_id TEXT, actual_minutes INTEGER, occurred_at TEXT, note TEXT, supersedes_id TEXT)")
    repo = SQLiteWeeklyReviewRepository(path)
    result = repo.aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-20T12:00:00Z')
    assert result['actual_focus_minutes'] == 0
    assert result['recorded_items'] == 1
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_work_logs VALUES ('l',NULL,'i',15,'2026-10-12T10:00:00Z','',NULL)")
        c.execute("INSERT INTO planner_work_logs VALUES ('c',NULL,'i',20,'2026-10-12T10:00:00Z','','l')")
    result = repo.aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-20T12:00:00Z')
    assert result['actual_focus_minutes'] == 20
    assert result['recorded_items'] == 1
    with sqlite3.connect(path) as c:
        c.execute("UPDATE planner_work_logs SET occurred_at='2026-10-16T10:00:00Z' WHERE id='c'")
        c.execute("UPDATE daily_agenda_items SET actual_minutes=20 WHERE id='i'")
    historical = repo.aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-14T12:00:00Z')
    assert historical['actual_focus_minutes'] == 15
    assert 'work_log:c' not in historical['metrics']['actual_minutes']['source_refs']


def test_historical_deadlines_compare_first_completion_to_as_of(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_tasks(id,title,due_on,status,completed_at,created_at,updated_at) VALUES ('t','Due','2026-10-13','completed','2026-10-15T01:00:00Z','x','x')")
    repo = SQLiteWeeklyReviewRepository(path)
    later = repo.aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-16T12:00:00Z')
    assert later['deadline_outcomes']['late'] == 1
    earlier = repo.aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-14T12:00:00Z')
    assert earlier['deadline_outcomes']['unresolved'] == 1


def test_closed_snapshot_stays_frozen_after_owner_edits(tmp_path):
    from pathlib import Path
    from personal_learning_assistant.services.weekly_review_service import WeeklyReviewService
    path = database(tmp_path)
    with sqlite3.connect(path) as c:
        c.executescript(Path('personal_learning_assistant/repositories/sqlite/optional_migrations/0018_pao_execution.sql').read_text())
    service = WeeklyReviewService(SQLiteWeeklyReviewRepository(path),now=lambda:'2026-10-20T12:00:00Z')
    service.save('2026-10-18',{},close=True)
    frozen = service.workspace('2026-10-18')['evidence']
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_tasks(id,title,due_on,created_at,updated_at) VALUES ('later','Due','2026-10-13','x','x')")
    assert service.workspace('2026-10-18')['evidence'] == frozen
    assert SQLiteWeeklyReviewRepository(path).aggregate_period('2026-10-12','2026-10-18')['missed_deadline_count'] == 1


def test_stale_displayed_evidence_or_review_revision_cannot_close(tmp_path):
    from pathlib import Path
    import pytest
    from personal_learning_assistant.services.weekly_review_service import WeeklyReviewService, WeeklyReviewConflictError
    path = database(tmp_path)
    with sqlite3.connect(path) as c:
        c.executescript(Path('personal_learning_assistant/repositories/sqlite/optional_migrations/0018_pao_execution.sql').read_text())
    service = WeeklyReviewService(SQLiteWeeklyReviewRepository(path),now=lambda:'2026-10-20T12:00:00Z')
    workspace = service.workspace('2026-10-18')
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_tasks(id,title,due_on,created_at,updated_at) VALUES ('later','Due','2026-10-13','x','x')")
    with pytest.raises(WeeklyReviewConflictError):
        service.save('2026-10-18',dict(evidence_fingerprint=workspace['evidence_fingerprint']),close=True)
    service.save('2026-10-18',dict(expected_revision='0'))
    with pytest.raises(WeeklyReviewConflictError):
        service.save('2026-10-18',dict(expected_revision='0'),close=True)


def test_overview_task_totals_are_not_priority_page_counts(tmp_path):
    from datetime import datetime, timezone
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    path = database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute('PRAGMA journal_mode=DELETE')
        c.executemany("INSERT INTO planner_tasks(id,title,priority,due_on,created_at,updated_at) VALUES (?,?,'P0','2026-10-30','x','x')",[(str(i),'Future') for i in range(110)])
        c.execute("INSERT INTO planner_tasks(id,title,priority,due_on,created_at,updated_at) VALUES ('overdue','Due','P2','2026-10-13','x','x')")
    view = AcademicOverviewService(path,now=lambda:datetime(2026,10,20,tzinfo=timezone.utc)).overview()
    assert len(view['tasks']) == 100
    assert view['summary']['open_tasks'] == 111
    assert view['summary']['overdue_tasks'] == 1


def test_mixed_assessment_population_explicitly_labels_sampling(tmp_path):
    from tests.test_planning_analysis_v2 import _database, service
    path = _database(tmp_path)
    with sqlite3.connect(path) as c:
        columns = [r[1] for r in c.execute('PRAGMA table_info(assessment_test_sessions)')]
        original = dict(zip(columns,c.execute("SELECT * FROM assessment_test_sessions WHERE id='s3'").fetchone()))
        for index in range(105):
            row = {**original,'id':'sample-'+str(index)}
            c.execute('INSERT INTO assessment_test_sessions ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row[k] for k in columns))
    view = service(path).overview()
    assert len(view['assessments']) == 100
    assert 'Sample' in view['assessment_scope'] and 'counts describe displayed sample' in view['assessment_scope']
    assert sum(view['summary'][kind+'_sessions'] for kind in ('evaluated','self_reported','pending')) == 100


def test_explicit_source_study_queue_is_not_inferred_from_reading(tmp_path):
    from scripts.pao_migrate import migrate
    path=database(tmp_path);migrate(path,apply=True)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_tasks(id,title,due_on,created_at,updated_at) VALUES('revision','Review linked source','2026-10-16','x','x')")
        c.execute("INSERT INTO planner_task_sources(task_id,owner,kind,identifier,revision_key,mapping_status) VALUES('revision','learning','module','lesson','2','confirmed')")
    value=SQLiteWeeklyReviewRepository(path).aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-18T12:00:00Z')
    assert value['revision_queue'][0]['next_review_on'] == '2026-10-16'
    assert value['metrics']['revision_queue']['value'] == 1


def test_week_comparison_requires_matching_snapshot_and_recording_coverage(tmp_path):
    import json
    from scripts.pao_migrate import migrate
    from personal_learning_assistant.domain.weekly_evidence import POLICY_VERSION
    path=database(tmp_path);migrate(path,apply=True)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO daily_agendas(id,agenda_date,status,approved_at,generated_at,created_at,updated_at) VALUES('a','2026-10-12','approved','2026-10-11T12:00:00Z','x','x','x')")
        c.execute("INSERT INTO daily_agenda_items(id,agenda_id,ordinal,item_kind,title,planned_minutes,actual_minutes,starts_at,ends_at,created_at,updated_at) VALUES('i','a',1,'manual','Study',30,20,'2026-10-12T09:00:00Z','2026-10-12T09:30:00Z','x','2026-10-12T10:00:00Z')")
        prior={'policy_version':POLICY_VERSION,'scope':{'start':'2026-10-05','end':'2026-10-11','course_id':'','timezone':'Asia/Kolkata'},'planned_items':1,'recorded_items':1,'planned_focus_minutes':40,'actual_focus_minutes':25}
        c.execute("INSERT INTO weekly_reviews(id,week_start,week_end,created_at,updated_at,closed_at,evidence_json) VALUES('prior','2026-10-05','2026-10-11','x','x','2026-10-12T00:00:00Z',?)",(json.dumps(prior),))
    result=SQLiteWeeklyReviewRepository(path).aggregate_period('2026-10-12','2026-10-18',as_of='2026-10-20T12:00:00Z')
    assert result['metrics']['weekly_comparison']['value']['actual_minutes_delta'] == -5


def test_review_clock_never_predates_immediately_preceding_completion():
    from datetime import datetime,timezone
    from personal_learning_assistant.services.weekly_review_service import _now
    before=datetime.now(timezone.utc)
    observed=datetime.fromisoformat(_now().replace('Z','+00:00'))
    assert observed >= before
