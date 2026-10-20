"""Synthetic result navigation must respect the source that owns the attempt."""
import sqlite3

import pytest

from tests.test_assessment_studio_phase_d import _app, _database, _submitted_session
from tests.test_planning_analysis_v2 import inventory


def test_submitted_subjective_attempt_without_evaluation_links_to_summary(tmp_path):
    from datetime import datetime, timezone
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService

    path = _database(tmp_path)
    sid = _submitted_session(path)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA journal_mode=DELETE')
    before = inventory(tmp_path)
    overview = AcademicOverviewService(path, now=lambda: datetime(2026, 9, 28, tzinfo=timezone.utc)).overview()
    result = next(row for row in overview['assessments'] if row['id'] == sid)
    assert result['category'] == 'pending' and result['earned'] is None
    assert result['url'] == f'/assessments/sessions/{sid}/summary'
    response = _app(path).test_client().get(result['url'])
    assert response.status_code == 200
    assert 'Evaluate / Open Results' in response.text
    assert 'MCQ solution' not in response.text
    assert inventory(tmp_path) == before


@pytest.mark.parametrize('suffix', ['', '/summary', '/evaluation'])
def test_result_reads_hide_permission_details_and_preserve_storage_failure_status(tmp_path, monkeypatch, suffix):
    from personal_learning_assistant.ui.web import routes

    app = _app(_database(tmp_path))
    def denied(session_id):
        raise PermissionError('PRIVATE academic path cannot be opened')
    monkeypatch.setattr(routes, '_is_extended_session', denied)
    response = app.test_client().get('/assessments/sessions/unknown' + suffix)
    assert response.status_code == 503
    assert 'PRIVATE' not in response.text
    assert 'temporarily unavailable' in response.text


def test_completed_paper_direct_result_url_uses_private_self_review(tmp_path):
    from tests.test_planning_analysis_v2 import _submitted_paper

    app, path, sid, studio, clock = _submitted_paper(tmp_path)
    before = inventory(tmp_path)
    client = app.test_client()
    result = client.get(f'/assessments/sessions/{sid}/evaluation')
    assert result.status_code == 303
    assert result.location == f'/assessments/extended/sessions/{sid}'
    assert 'Self-assessed, not independently graded' in client.get(result.location).text
    assert inventory(tmp_path) == before
    denied = client.post(f'/assessments/sessions/{sid}/evaluate')
    assert denied.status_code == 409
    assert inventory(tmp_path) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM assessment_session_evaluations').fetchone()[0] == 0


@pytest.mark.parametrize('failure', ['internal_lookup', 'permission'])
def test_extended_internal_errors_are_unavailable_not_missing_attempts(tmp_path, monkeypatch, failure):
    from tests.test_assessment_production_integration import _production
    from personal_learning_assistant.ui.web import assessment_execution_candidate as routes

    app, path, aid, factory, clock = _production(tmp_path)
    sid = app.test_client().post('/assessments/tests/' + aid + '/start', data={
        'confirmed': '1', 'extended_kind': 'online_timed',
    }).location.rsplit('/', 1)[1]
    def failed(*args, **kwargs):
        if failure == 'internal_lookup':
            raise KeyError('PRIVATE renderer context')
        raise PermissionError('PRIVATE source path')
    monkeypatch.setattr(routes, 'render_template', failed)
    response = app.test_client().get('/assessments/extended/sessions/' + sid)
    assert response.status_code == 503
    assert 'PRIVATE' not in response.text
    assert 'storage unavailable' in response.text


def test_missing_extended_attempt_stays_a_true_404(tmp_path):
    from tests.test_assessment_production_integration import _production
    app, path, aid, factory, clock = _production(tmp_path)
    assert app.test_client().get('/assessments/extended/sessions/missing').status_code == 404
