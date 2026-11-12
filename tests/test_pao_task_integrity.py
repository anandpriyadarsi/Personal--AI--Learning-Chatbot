import sqlite3
import uuid
import pytest
from tests.test_phase7_5_month_plan_import import _db, FIXTURE
from personal_learning_assistant.services.month_plan_import_service import build_month_plan_import_service
from personal_learning_assistant.repositories.sqlite.daily_agenda_repository import SQLiteDailyAgendaRepository, DailyAgendaRepositoryConflictError


def test_changed_import_preserves_terminal_execution(tmp_path):
    path = _db(tmp_path)
    svc = build_month_plan_import_service(path)
    payload = FIXTURE.read_bytes()
    preview = svc.preview('plan.yaml', payload)
    svc.approve('plan.yaml', payload, preview['source_sha256'])
    with sqlite3.connect(path) as c:
        c.execute("UPDATE planner_tasks SET status='completed',completed_at='2026-10-01T12:00:00Z'")
    changed = payload.replace(b'45', b'46')
    if changed == payload:
        changed = payload + b'\n# refreshed\n'
    svc.approve('plan.yaml', changed, svc.preview('plan.yaml', changed)['source_sha256'])
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT status FROM planner_tasks').fetchone()[0] == 'completed'


def agenda(path, task_id, day, suffix):
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO daily_agendas(id,agenda_date,status,generated_at,created_at,updated_at) VALUES(?,?,'approved','x','x','x')", ('a'+suffix,day))
        c.execute("INSERT INTO daily_agenda_items(id,agenda_id,ordinal,item_kind,source_type,source_id,title,created_at,updated_at) VALUES(?,?,1,'task','planner_task',?,'Read','x','x')", ('i'+suffix,'a'+suffix,task_id))

@pytest.mark.parametrize('terminal', ['archived', 'completed'])
def test_agenda_cannot_complete_terminal_task(tmp_path, terminal):
    path = _db(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_tasks(id,title,status,created_at,updated_at) VALUES('t','Read',?,'x','x')", (terminal,))
    agenda(path, 't', '2026-10-01', '1')
    with pytest.raises(DailyAgendaRepositoryConflictError):
        SQLiteDailyAgendaRepository(path).update_item_status('2026-10-01','i1',status='completed',actual_minutes=10,completed_at='2026-10-01T12:00:00Z',updated_at='2026-10-01T12:00:00Z')
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT status FROM daily_agenda_items WHERE id='i1'").fetchone()[0] != 'completed'


def execution(tmp_path):
    from scripts.pao_migrate import migrate
    from personal_learning_assistant.repositories.sqlite.planner_execution_repository import SQLitePlannerExecutionRepository
    path = _db(tmp_path)
    migrate(path, apply=True)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO planner_tasks(id,title,status,created_at,updated_at) VALUES('t','Read','backlog','x','x')")
    return SQLitePlannerExecutionRepository(path), path


def test_receipt_replay_precedes_revision_check_and_payload_conflicts(tmp_path):
    repo, path = execution(tmp_path)
    cid = str(uuid.uuid4())
    args = dict(expected_revision=0, command_id=cid, target_status='planned', occurred_at='2026-10-01T12:00:00Z')
    first = repo.transition_task('t', **args)
    repo.transition_task('t', expected_revision=1, command_id=str(uuid.uuid4()), target_status='completed', occurred_at='2026-10-01T12:05:00Z')
    assert repo.transition_task('t', **args) == first
    from personal_learning_assistant.repositories.sqlite.planner_task_repository import PlannerTaskRepositoryConflictError
    with pytest.raises(PlannerTaskRepositoryConflictError):
        repo.transition_task('t', **{**args, 'target_status': 'archived'})


def test_partial_logs_and_stale_command_are_atomic(tmp_path):
    repo, path = execution(tmp_path)
    from personal_learning_assistant.repositories.sqlite.planner_task_repository import PlannerTaskRepositoryConflictError
    for revision, minutes in enumerate((10, 15)):
        repo.log_progress('t', expected_revision=revision, command_id=str(uuid.uuid4()), actual_minutes=minutes, occurred_at='2026-10-01T12:00:00Z')
    with pytest.raises(PlannerTaskRepositoryConflictError):
        repo.transition_task('t', expected_revision=0, command_id=str(uuid.uuid4()), target_status='completed', occurred_at='2026-10-01T12:05:00Z')
    repo.transition_task('t', expected_revision=2, command_id=str(uuid.uuid4()), target_status='completed', occurred_at='2026-10-01T12:05:00Z')
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT SUM(actual_minutes) FROM planner_work_logs').fetchone()[0] == 25
        assert c.execute('SELECT COUNT(*) FROM planner_command_receipts').fetchone()[0] == 3


def test_backup_activation_repeat_and_dry_run_do_not_change_database(tmp_path):
    import hashlib
    from scripts.pao_migrate import migrate
    path = _db(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not migrate(path)['ready']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    result = migrate(path, apply=True)
    assert result['applied']
    with sqlite3.connect(result['backup']) as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='planner_command_receipts'").fetchone()
    assert not migrate(path, apply=True)['applied']


def test_history_shows_partial_minutes_and_append_only_correction(tmp_path):
    repo, path = execution(tmp_path)
    first_id = str(uuid.uuid4())
    repo.log_progress('t', expected_revision=0, command_id=first_id, actual_minutes=10, occurred_at='2026-10-01T12:00:00Z')
    repo.log_progress('t', expected_revision=1, command_id=str(uuid.uuid4()), actual_minutes=7, occurred_at='2026-10-01T12:01:00Z', supersedes_id=first_id)
    from personal_learning_assistant.services.operational_task_service import OperationalTaskService
    task = OperationalTaskService(repo).tasks_workspace()['tasks'][0]
    assert task['recorded_minutes'] == 7
    assert len(task['work_logs']) == 2
    assert task['work_logs'][0]['superseded'] is True


def test_migration_failure_rolls_back_all_added_schema(tmp_path, monkeypatch):
    import scripts.pao_migrate as migration
    from pathlib import Path
    path = _db(tmp_path)
    broken = tmp_path / '0018_pao_execution.sql'
    broken.write_text(migration.MIGRATION.read_text() + '\nINVALID SQL;\n')
    broken.with_name('0019_obsidian_source_identity.sql').write_text(migration.MIGRATION.with_name('0019_obsidian_source_identity.sql').read_text())
    monkeypatch.setattr(migration, 'MIGRATION', broken)
    with pytest.raises(sqlite3.Error):
        migration.migrate(path, apply=True)
    with sqlite3.connect(path) as c:
        assert 'revision' not in {r[1] for r in c.execute('PRAGMA table_info(planner_tasks)')}
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='planner_command_receipts'").fetchone()
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_agenda_first_log_preserves_legacy_minutes_and_terminal_correction_time(tmp_path):
    repo, path = execution(tmp_path)
    agenda(path, 't', '2026-10-01', '1')
    with sqlite3.connect(path) as c:
        c.execute("UPDATE daily_agenda_items SET actual_minutes=15,updated_at='2026-10-01T11:00:00Z' WHERE id='i1'")
    cid = str(uuid.uuid4())
    repo.log_progress('t', expected_revision=0, command_id=cid, actual_minutes=10, agenda_item_id='i1', occurred_at='2026-10-01T12:00:00Z')
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT actual_minutes FROM daily_agenda_items WHERE id='i1'").fetchone()[0] == 25
    repo.transition_task('t', expected_revision=1, command_id=str(uuid.uuid4()), target_status='completed', agenda_item_id='i1', occurred_at='2026-10-01T13:00:00Z')
    repo.log_progress('t', expected_revision=2, command_id=str(uuid.uuid4()), actual_minutes=8, agenda_item_id='i1', supersedes_id=cid, occurred_at='2026-10-01T14:00:00Z', note='Corrected entry')
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT actual_minutes,completed_at FROM daily_agenda_items WHERE id='i1'").fetchone() == (23,'2026-10-01T13:00:00Z')
        assert c.execute("SELECT completed_at FROM planner_tasks WHERE id='t'").fetchone()[0] == '2026-10-01T13:00:00Z'
