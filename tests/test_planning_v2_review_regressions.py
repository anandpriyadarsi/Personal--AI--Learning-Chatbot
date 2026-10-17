import re
from tests.test_planning_v2_proposals import proposal_app, preview
from tests.test_planning_analysis_v2 import _database, service
from personal_learning_assistant.ui.web import create_app


def test_saved_schedule_shows_times_and_preview_has_no_execution_actions(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    token = preview(client)
    assert client.post('/planning/proposal/2026-10-12',data={'proposal_token':token}).status_code==303
    saved = client.get('/planning/day/2026-10-12').text
    assert '10:10' in saved
    assert 'Unscheduled today' not in saved
    page = client.get('/planning/proposal/2026-10-12?start=15:00&end=18:00').text
    assert '>Complete<' not in page
    assert 'Close day &amp;' not in page


def test_topic_observations_are_reachable(tmp_path):
    path = _database(tmp_path)
    app = create_app({'TESTING':True,'ACADEMIC_OVERVIEW_SERVICE_FACTORY':lambda:service(path)})
    html = app.test_client().get('/analysis').text
    assert 'Topic observations' in html
    assert 'Inspect evidence' in html
    assert 'Candidate for manual review' in html


def test_unavailable_effort_does_not_claim_zero_coverage(tmp_path):
    app = create_app({'TESTING':True,'ACADEMIC_OVERVIEW_SERVICE_FACTORY':lambda:service(tmp_path/'missing.db')})
    html = app.test_client().get('/analysis').text
    assert '0 / 0 items' not in html
    assert 'Effort logging coverage</dt><dd>Unknown' in html


def test_approval_requires_signed_same_origin_intent(proposal_app):
    app, path = proposal_app
    client = app.test_client()
    token = preview(client)
    client.post('/planning/proposal/2026-10-12',data={'proposal_token':token})
    assert client.post('/planning/day/2026-10-12/approve').status_code==400
    page = client.get('/planning/day/2026-10-12').text
    token = re.search(r'name="approval_token" value="([^"]+)"',page).group(1)
    assert client.post('/planning/day/2026-10-12/approve',data={'approval_token':token},headers={'Origin':'https://other.example'}).status_code==400
    assert client.post('/planning/day/2026-10-13/approve',data={'approval_token':token}).status_code==400
    assert client.post('/planning/day/2026-10-12/approve',data={'approval_token':token}).status_code==303


def test_completed_day_displays_recorded_actual_effort(proposal_app):
    app,path=proposal_app
    client=app.test_client()
    client.post('/planning/proposal/2026-10-12',data={'proposal_token':preview(client)})
    import re
    token=re.search(r'name="approval_token" value="([^"]+)"',client.get('/planning/day/2026-10-12').text).group(1)
    client.post('/planning/day/2026-10-12/approve',data={'approval_token':token})
    import sqlite3
    with sqlite3.connect(path) as c:
        ident=c.execute("SELECT id FROM daily_agenda_items WHERE item_kind='task'").fetchone()[0]
    client.post(f'/planning/day/2026-10-12/items/{ident}',data={'status':'completed','actual_minutes':'35'})
    html=client.get('/planning/day/2026-10-12').text
    assert 'recorded 35 min' in html
    assert 'aria-label="Actual minutes for ' in html
