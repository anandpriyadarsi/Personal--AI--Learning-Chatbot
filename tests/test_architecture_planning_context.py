"""No scheduled draft may outlive its explicit availability context silently."""
import re
import sqlite3

import pytest

from tests.test_planning_v2_proposals import proposal_app, preview


def logical_state(path):
    with sqlite3.connect(path) as db:
        return tuple(db.iterdump())


def save(client):
    response = client.post('/planning/proposal/2026-10-12', data={'proposal_token': preview(client)})
    assert response.status_code == 303
    return re.search(r'name="approval_token" value="([^"]+)"', client.get(response.location).text).group(1)


def test_preview_and_approval_share_the_configured_timezone_and_clock(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    app.config['PLANNING_NOW'] = lambda: '2026-10-12T10:00:00Z'
    response = client.get('/planning/proposal/2026-10-12?start=10:00&end=14:00')
    token = re.search(r'name="proposal_token" value="([^"]+)"', response.text).group(1)
    assert client.post('/planning/proposal/2026-10-12', data={'proposal_token': token}).status_code == 303
    approval = re.search(r'name="approval_token" value="([^"]+)"', client.get('/planning/day/2026-10-12').text).group(1)
    assert client.post('/planning/day/2026-10-12/approve', data={'approval_token': approval}).status_code == 303
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM daily_agendas').fetchone() == ('approved',)


@pytest.mark.parametrize('change', ['timezone', 'break_policy', 'context_missing', 'source', 'overlap'])
def test_saved_schedule_requires_original_context_and_current_sources(proposal_app, change):
    app, path = proposal_app
    client = app.test_client()
    approval = save(client)
    if change == 'timezone':
        app.config['PLANNING_LOCAL_TIMEZONE'] = 'Pacific/Honolulu'
    elif change == 'break_policy':
        app.config['PLANNING_BREAK_MINUTES'] = 30
    elif change == 'context_missing':
        app.extensions['planning_proposal_contexts'].clear()
    else:
        with sqlite3.connect(path) as db:
            if change == 'source':
                db.execute("UPDATE planner_tasks SET estimated_minutes=90 WHERE id='p0'")
            else:
                db.execute("UPDATE academic_events SET ends_at='2026-10-12T12:00:00' WHERE id='class'")
    before = logical_state(path)
    result = client.post('/planning/day/2026-10-12/approve', data={'approval_token': approval})
    assert result.status_code == 409
    assert logical_state(path) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM daily_agendas').fetchone() == ('draft',)


def test_lost_original_context_is_visible_when_saved_day_reopens(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    save(client)
    app.extensions['planning_proposal_contexts'].clear()
    before = logical_state(path)
    page = client.get('/planning/day/2026-10-12')
    assert page.status_code == 200
    assert 'Original availability context is unavailable' in page.text
    assert '>Approve day<' not in page.text
    assert logical_state(path) == before


def test_service_does_not_invent_an_approval_window_for_a_scheduled_draft(proposal_app):
    from personal_learning_assistant.services.operational_planner_web_service import (
        build_operational_planner_web_service, OperationalPlannerWebConflictError,
    )
    app, path = proposal_app
    save(app.test_client())
    service = build_operational_planner_web_service(path)
    service.daily._now = lambda: '2026-10-12T07:00:00Z'
    before = logical_state(path)
    with pytest.raises(OperationalPlannerWebConflictError, match='availability context'):
        service.approve_day('2026-10-12')
    assert logical_state(path) == before


def test_an_approval_token_cannot_approve_a_replacement_draft(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    old_approval = save(client)
    response = client.get('/planning/proposal/2026-10-12?start=16:00&end=19:00')
    token = re.search(r'name="proposal_token" value="([^"]+)"', response.text).group(1)
    assert client.post('/planning/proposal/2026-10-12', data={'proposal_token': token}).status_code == 303
    before = logical_state(path)
    response = client.post('/planning/day/2026-10-12/approve', data={'approval_token': old_approval})
    assert response.status_code == 409
    assert logical_state(path) == before


def test_source_race_between_context_check_and_approval_is_rejected(proposal_app, monkeypatch):
    from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
    app, path = proposal_app
    client = app.test_client()
    approval = save(client)
    service = build_operational_planner_web_service(path)
    original = service.daily.agendas.planning_fingerprint
    calls = 0
    def raced():
        nonlocal calls
        calls += 1
        if calls == 2:
            with sqlite3.connect(path) as db:
                db.execute("UPDATE planner_tasks SET description='Changed while approving' WHERE id='p2'")
        return original()
    monkeypatch.setattr(service.daily.agendas, 'planning_fingerprint', raced)
    app.config['OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY'] = lambda: service
    response = client.post('/planning/day/2026-10-12/approve', data={'approval_token': approval})
    assert response.status_code == 409
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM daily_agendas').fetchone() == ('draft',)


def test_commit_to_context_publication_cannot_bless_a_changed_source(proposal_app, monkeypatch):
    from personal_learning_assistant.repositories.sqlite.daily_agenda_repository import SQLiteDailyAgendaRepository
    app, path = proposal_app
    original = SQLiteDailyAgendaRepository.create_or_replace_draft
    def raced(repository, *args, **kwargs):
        result = original(repository, *args, **kwargs)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE planner_tasks SET description='Source changed after draft commit' WHERE id='p2'")
        return result
    monkeypatch.setattr(SQLiteDailyAgendaRepository, 'create_or_replace_draft', raced)
    client = app.test_client()
    approval = save(client)
    before = logical_state(path)
    assert client.post('/planning/day/2026-10-12/approve', data={'approval_token': approval}).status_code == 409
    assert logical_state(path) == before


def test_identical_replacement_still_requires_its_own_review(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    old_approval = save(client)
    first = logical_state(path)
    new_approval = save(client)
    assert logical_state(path) == first
    assert old_approval != new_approval
    assert client.post('/planning/day/2026-10-12/approve', data={'approval_token': old_approval}).status_code == 409
    assert logical_state(path) == first
    assert client.post('/planning/day/2026-10-12/approve', data={'approval_token': new_approval}).status_code == 303


def test_replacement_waits_for_inflight_approval_context(proposal_app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from personal_learning_assistant.services.operational_planner_web_service import OperationalPlannerWebService
    app, path = proposal_app
    client = app.test_client()
    approval = save(client)
    replacement = preview(client)
    entered, release, save_entered = Event(), Event(), Event()
    original_approve = OperationalPlannerWebService.approve_day
    original_save = OperationalPlannerWebService.save_proposal
    def blocked_approval(service, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_approve(service, *args, **kwargs)
    def observed_save(service, *args, **kwargs):
        save_entered.set()
        return original_save(service, *args, **kwargs)
    monkeypatch.setattr(OperationalPlannerWebService, 'approve_day', blocked_approval)
    monkeypatch.setattr(OperationalPlannerWebService, 'save_proposal', observed_save)
    def approve():
        return app.test_client().post('/planning/day/2026-10-12/approve', data={'approval_token': approval})
    def replace():
        return app.test_client().post('/planning/proposal/2026-10-12', data={'proposal_token': replacement})
    with ThreadPoolExecutor(max_workers=2) as pool:
        approval_result = pool.submit(approve)
        assert entered.wait(5)
        replacement_result = pool.submit(replace)
        try:
            assert not save_entered.wait(.2), 'Replacement passed the availability-context lock during approval'
        finally:
            release.set()
        assert approval_result.result(timeout=5).status_code == 303
        assert replacement_result.result(timeout=5).status_code == 409


def test_owner_wal_snapshot_freshness_boundary_preserves_pending_result_link(tmp_path):
    from datetime import timedelta
    from tests.test_planning_v21_wal_snapshot import _wal, _overview
    from tests.test_planning_analysis_v2 import NOW, inventory
    from personal_learning_assistant.services.academic_wal_snapshot import AcademicSnapshotFeed
    path, writer = _wal(tmp_path)
    try:
        writer.execute("UPDATE assessment_test_sessions SET status='submitted' WHERE id='s3'")
        writer.commit()
        feed = AcademicSnapshotFeed(path)
        feed.publish(writer, at=NOW)
        before = inventory(tmp_path)
        current = _overview(path, feed.latest, at=NOW + timedelta(seconds=120))
        assert current['available']
        row = next(row for row in current['assessments'] if row['id'] == 's3')
        assert row['category'] == 'pending' and row['earned'] is None
        assert row['url'] == '/assessments/sessions/s3/evaluation'
        assert not _overview(path, feed.latest, at=NOW + timedelta(seconds=121))['available']
        assert inventory(tmp_path) == before
    finally:
        writer.close()
