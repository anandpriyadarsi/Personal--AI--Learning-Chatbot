"""Durable explicit capacity and useful feasible selection regressions."""
import re
import sqlite3

import pytest

from test_phase7_5_daily_agenda import _service
from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
from personal_learning_assistant.ui.web import create_app


@pytest.fixture
def proposal_store(tmp_path):
    _, path = _service(tmp_path)
    from scripts.pao_migrate import migrate
    migrate(path, apply=True, backup_path=tmp_path / 'before-pao.db')
    return path


def app_for(path):
    return create_app({'TESTING': True, 'PAO_V3_ENABLED': True, 'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY': lambda: build_operational_planner_web_service(path),
                      'PLANNING_LOCAL_TIMEZONE': 'UTC', 'PLANNING_NOW': lambda: '2026-10-12T07:00:00Z'})


def fields(response):
    return dict(re.findall(r'name="([^"]+)" value="([^"]*)"', response.text))


def test_save_restart_reopen_approves_with_fresh_token_and_retains_windows(proposal_store):
    app = app_for(proposal_store)
    client = app.test_client()
    page = client.get('/planning/proposal/2026-10-12?start=10:00&end=12:00&start=18:00&end=20:00')
    assert page.status_code == 200
    with sqlite3.connect(proposal_store) as c:
        assert c.execute('SELECT COUNT(*) FROM planner_proposals').fetchone()[0] == 0
    form = fields(page)
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 303
    restarted = app_for(proposal_store).test_client()
    page = restarted.get('/planning/day/2026-10-12')
    assert '18:00' in page.text
    assert 'approval_token' in fields(page)
    assert restarted.post('/planning/day/2026-10-12/approve', data=fields(page)).status_code == 303
    with sqlite3.connect(proposal_store) as c:
        assert c.execute('SELECT status FROM daily_agendas').fetchone()[0] == 'approved'
        assert c.execute('SELECT COUNT(*) FROM planner_proposals').fetchone()[0] == 1


def test_duplicate_save_is_idempotent(proposal_store):
    client = app_for(proposal_store).test_client()
    form = fields(client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00'))
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 303
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 303
    with sqlite3.connect(proposal_store) as c:
        assert c.execute('SELECT COUNT(*) FROM planner_proposals').fetchone()[0] == 1


@pytest.mark.parametrize('query', ['start=10:00&end=12:00&start=11:00&end=13:00', 'start=06:00&end=07:00'])
def test_overlapping_or_elapsed_windows_rejected(proposal_store, query):
    assert app_for(proposal_store).test_client().get('/planning/proposal/2026-10-12?' + query).status_code == 400


def test_sixth_feasible_candidate_is_selected_before_cap(tmp_path):
    service, path = _service(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute('DELETE FROM planner_tasks')
        for i in range(6):
            c.execute("INSERT INTO planner_tasks (id,title,description,priority,estimated_minutes,status,rollover_policy,manual_revision,created_at,updated_at,due_on) VALUES (?,?, '', 'P0',30,'backlog','carry',0,'x','x',?)", (str(i), 'Task '+str(i), '2026-10-11' if i < 5 else None))
    service.free_windows = {'2026-10-12': [('10:00','14:00')]}
    service._now = lambda: '2026-10-12T07:00:00Z'
    service.local_timezone = __import__('datetime').timezone.utc
    preview = service.preview_day('2026-10-12')
    assert any(x['source_id'] == '5' and x['starts_at'] for x in preview['tasks'])
    assert len(preview['tasks']) <= 5
    assert any(x['source_id'] == '4' for x in preview['review_needed'])


def test_unrelated_history_does_not_invalidate_but_relevant_task_change_does(proposal_store):
    client = app_for(proposal_store).test_client()
    page = client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00')
    form = fields(page)
    with sqlite3.connect(proposal_store) as c:
        c.execute("INSERT INTO academic_events (id,event_kind,title,starts_at,ends_at,all_day,status,created_at,updated_at) VALUES ('future','class','Next month','2026-11-12T09:00:00','2026-11-12T10:00:00',0,'scheduled','x','x')")
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 303
    page = client.get('/planning/day/2026-10-12')
    with sqlite3.connect(proposal_store) as c:
        c.execute("UPDATE planner_tasks SET estimated_minutes=90 WHERE id='p0'")
    assert client.post('/planning/day/2026-10-12/approve', data=fields(page)).status_code == 409
    with sqlite3.connect(proposal_store) as c:
        assert c.execute('SELECT status FROM daily_agendas').fetchone()[0] == 'draft'


def test_approval_duplicate_never_records_another_transition(proposal_store):
    client = app_for(proposal_store).test_client()
    form = fields(client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00'))
    client.post('/planning/proposal/2026-10-12', data=form)
    approval = fields(client.get('/planning/day/2026-10-12'))
    assert client.post('/planning/day/2026-10-12/approve', data=approval).status_code == 303
    with sqlite3.connect(proposal_store) as c:
        before = tuple(c.iterdump())
    assert client.post('/planning/day/2026-10-12/approve', data=approval).status_code == 409
    with sqlite3.connect(proposal_store) as c:
        assert tuple(c.iterdump()) == before


def test_small_candidate_behind_large_one_fits_and_unknown_occupancy_blocks(proposal_store):
    with sqlite3.connect(proposal_store) as c:
        c.execute("UPDATE planner_tasks SET estimated_minutes=300 WHERE id='p0'")
    service = build_operational_planner_web_service(proposal_store)
    config = {'local_timezone': 'UTC', 'now': lambda: '2026-10-12T07:00:00Z'}
    preview = service.preview_proposal('2026-10-12', '10:00', '11:00', **config)['day']
    assert next(x for x in preview['tasks'] if x['source_id'] == 'p1')['starts_at']
    with sqlite3.connect(proposal_store) as c:
        c.execute("UPDATE academic_events SET ends_at=NULL WHERE id='class'")
    preview = service.preview_proposal('2026-10-12', '10:00', '14:00', **config)['day']
    assert all(not x['starts_at'] for x in preview['tasks'])


def test_failed_proposal_persistence_rolls_back_draft(proposal_store):
    client = app_for(proposal_store).test_client()
    form = fields(client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00'))
    with sqlite3.connect(proposal_store) as c:
        c.execute("CREATE TRIGGER reject_proposal BEFORE INSERT ON planner_proposals BEGIN SELECT RAISE(ABORT,'storage failure'); END")
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 503
    with sqlite3.connect(proposal_store) as c:
        assert c.execute('SELECT COUNT(*) FROM daily_agendas').fetchone()[0] == 0


def test_saved_review_queue_and_reason_codes_survive_reopen(proposal_store):
    with sqlite3.connect(proposal_store) as c:
        for i in range(6):
            c.execute("INSERT INTO planner_tasks (id,title,description,priority,estimated_minutes,status,rollover_policy,manual_revision,created_at,updated_at,due_on) VALUES (?,?, '', 'P0',30,'backlog','carry',0,'x','x','2026-10-11')", ('late'+str(i), 'Overdue review '+str(i)))
    client = app_for(proposal_store).test_client()
    form = fields(client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00'))
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 303
    page = app_for(proposal_store).test_client().get('/planning/day/2026-10-12')
    assert 'Needs planning review' in page.text
    assert 'Overdue review 5' in page.text
    import json
    with sqlite3.connect(proposal_store) as c:
        context = json.loads(c.execute('SELECT context_json FROM planner_proposals').fetchone()[0])
    assert context['explanation_codes']['planner_task:late5'] == 'deadline_review_required'
    assert context['window_instants'][0]['start'].endswith('+00:00')


def test_feature_off_legacy_save_does_not_require_or_create_durable_storage(tmp_path):
    _, path = _service(tmp_path)
    app = app_for(path)
    app.config['PAO_V3_ENABLED'] = False
    client = app.test_client()
    form = fields(client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00'))
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 303
    page = client.get('/planning/day/2026-10-12')
    assert 'app session' in page.text
    assert 'approval_token' in fields(page)
    with sqlite3.connect(path) as c:
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='planner_proposals'").fetchone()


def test_feature_on_without_activation_fails_save_without_source_changes(tmp_path):
    _, path = _service(tmp_path)
    client = app_for(path).test_client()
    form = fields(client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00'))
    with sqlite3.connect(path) as c:
        before = tuple(c.iterdump())
    assert client.post('/planning/proposal/2026-10-12', data=form).status_code == 503
    with sqlite3.connect(path) as c:
        assert tuple(c.iterdump()) == before
