import re
import sqlite3

import pytest

from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
from personal_learning_assistant.ui.web import create_app
from test_phase7_5_daily_agenda import _service


@pytest.fixture
def proposal_app(tmp_path):
    _, path = _service(tmp_path)
    factory = lambda: build_operational_planner_web_service(path)
    app = create_app({'TESTING': True, 'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY': factory,
                      'PLANNING_LOCAL_TIMEZONE': 'UTC', 'PLANNING_NOW': lambda: '2026-10-12T07:00:00Z'})
    from personal_learning_assistant.ui.web.planning_proposals import register_planning_proposals
    if 'planning_proposals' not in app.blueprints:
        register_planning_proposals(app, factory)
    return app, path


def preview(client):
    response = client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00')
    assert response.status_code == 200
    token = re.search(r'name="proposal_token" value="([^"]+)"', response.text).group(1)
    return token


def test_native_preview_save_draft_then_existing_approve(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    token = preview(client)
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM daily_agendas').fetchone()[0] == 0
    saved = client.post('/planning/proposal/2026-10-12', data={'proposal_token': token})
    assert saved.status_code == 303
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT status FROM daily_agendas').fetchone()[0] == 'draft'
        assert conn.execute("SELECT starts_at FROM daily_agenda_items WHERE source_id='p0'").fetchone()[0] == '2026-10-12T10:10:00'
    assert client.post('/planning/proposal/2026-10-12', data={'proposal_token': token}).status_code == 409
    saved_page = client.get('/planning/day/2026-10-12')
    approval_token = re.search(r'name="approval_token" value="([^"]+)"', saved_page.text).group(1)
    assert client.post('/planning/day/2026-10-12/approve', data={'approval_token': approval_token}).status_code == 303
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT status FROM daily_agendas').fetchone()[0] == 'approved'


@pytest.mark.parametrize('sql', ["UPDATE planner_tasks SET estimated_minutes=90 WHERE id='p0'", "UPDATE academic_events SET ends_at='2026-10-12T12:00:00' WHERE id='class'"])
def test_source_changes_reject_stale_preview(proposal_app, sql):
    app, path = proposal_app
    client = app.test_client()
    token = preview(client)
    with sqlite3.connect(path) as conn:
        conn.execute(sql)
    assert client.post('/planning/proposal/2026-10-12', data={'proposal_token': token}).status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM daily_agendas').fetchone()[0] == 0


def test_token_origin_and_date_tampering_rejected(proposal_app):
    app, _ = proposal_app
    client = app.test_client()
    token = preview(client)
    assert client.post('/planning/proposal/2026-10-12', data={}).status_code == 400
    assert client.post('/planning/proposal/2026-10-13', data={'proposal_token': token}).status_code == 400
    assert client.post('/planning/proposal/2026-10-12', data={'proposal_token': token}, headers={'Origin': 'https://evil.example'}).status_code == 403


def test_invalid_availability_fails_closed(proposal_app):
    app, _ = proposal_app
    assert app.test_client().get('/planning/proposal/2026-10-12?start=14:00&end=10:00').status_code == 400


def test_default_proposal_timezone_uses_academic_setting(proposal_app):
    app, _ = proposal_app
    app.config.pop('PLANNING_LOCAL_TIMEZONE', None)
    app.config['ACADEMIC_TIMEZONE'] = 'Asia/Kolkata'
    response = app.test_client().get('/planning/proposal/2026-10-12?start=10:00&end=14:00')
    assert 'Asia/Kolkata' in response.text
    assert '12:30' in response.text


def test_day_view_preserves_saved_slots_and_totals(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    client.post('/planning/proposal/2026-10-12', data={'proposal_token': preview(client)})
    day = build_operational_planner_web_service(path).day_view('2026-10-12')
    assert day['tasks'][0]['starts_at'] == '2026-10-12T10:10:00'
    assert day['summary']['scheduled_focus_minutes'] == 135


@pytest.mark.parametrize('sql', [
    "UPDATE planner_tasks SET estimated_minutes=90 WHERE id='p0'",
    "UPDATE planner_tasks SET preferred_day='2026-10-14' WHERE id='p0'",
    "UPDATE planner_tasks SET due_on='2026-10-11' WHERE id='p0'",
    "UPDATE academic_events SET ends_at='2026-10-12T12:00:00' WHERE id='class'",
])
def test_saved_draft_revalidated_before_approval(proposal_app, sql):
    from personal_learning_assistant.services.operational_planner_web_service import OperationalPlannerWebConflictError
    app, path = proposal_app
    client = app.test_client()
    client.post('/planning/proposal/2026-10-12', data={'proposal_token': preview(client)})
    with sqlite3.connect(path) as conn:
        conn.execute(sql)
    with pytest.raises(OperationalPlannerWebConflictError):
        service = build_operational_planner_web_service(path)
        service.daily._now = lambda: '2026-10-12T00:00:00Z'
        service.approve_day('2026-10-12')
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT status FROM daily_agendas').fetchone()[0] == 'draft'


def test_approval_source_race_is_rejected(proposal_app, monkeypatch):
    from personal_learning_assistant.services.operational_planner_web_service import OperationalPlannerWebConflictError
    app, path = proposal_app
    client = app.test_client()
    client.post('/planning/proposal/2026-10-12', data={'proposal_token': preview(client)})
    service = build_operational_planner_web_service(path)
    service.daily._now = lambda: '2026-10-12T00:00:00Z'
    original = service.daily.agendas.approve_agenda
    def race(*args, **kwargs):
        with sqlite3.connect(path) as conn:
            conn.execute("UPDATE planner_tasks SET estimated_minutes=90 WHERE id='p0'")
        return original(*args, **kwargs)
    monkeypatch.setattr(service.daily.agendas, 'approve_agenda', race)
    with pytest.raises(OperationalPlannerWebConflictError):
        service.approve_day('2026-10-12')


def test_elapsed_saved_slot_cannot_be_approved(proposal_app):
    from personal_learning_assistant.services.operational_planner_web_service import OperationalPlannerWebConflictError
    app, path = proposal_app
    client = app.test_client()
    client.post('/planning/proposal/2026-10-12', data={'proposal_token': preview(client)})
    service = build_operational_planner_web_service(path)
    service.daily._now = lambda: '2026-10-13T00:00:00Z'
    with pytest.raises(OperationalPlannerWebConflictError):
        service.approve_day('2026-10-12')
