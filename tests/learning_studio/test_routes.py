import io
import json
import pytest
from .helpers import package, catalogue, source_pdf
from .test_service import publish, event
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app


@pytest.fixture
def client(tmp_path):
    service = LearningStudioService(tmp_path / 'learning_studio.sqlite3',
        source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    app = create_app({'TESTING': True, 'LEARNING_STUDIO_SERVICE_FACTORY': lambda: service})
    return app.test_client(), service, app


def token(app):
    return {'X-Learning-CSRF': app.extensions['learning_studio_csrf']}


def test_landing_and_missing_reads_no_writes(client):
    c, s, app = client
    for path, code in [('/learning', 200), ('/learning/analysis', 200),
                       ('/learning/import', 200), ('/learning/modules/missing/1', 404)]:
        assert c.get(path).status_code == code
    assert not s.store.path.exists()
    assert b'Learning Studio' in c.get('/learning').data


def test_import_preview_publish_and_source(client):
    c, s, app = client
    upload = lambda: {'package': (io.BytesIO(json.dumps(package()).encode()), 'module.json')}
    assert c.post('/learning/import', data=upload()).status_code == 403
    res = c.post('/learning/import', data=upload(), headers=token(app))
    assert res.status_code == 302
    assert b'Staged preview' in c.get(res.location).data
    assert b'Publish this revision' in c.get(res.location).data
    assert c.get('/learning/modules/synthetic/1').status_code == 404
    assert c.post('/learning/modules/synthetic/1/publish', headers=token(app)).status_code == 302
    for view in ('overview', 'learn', 'visualise', 'practice', 'revision', 'weak', 'source'):
        res = c.get(f'/learning/modules/synthetic/1?view={view}')
        assert res.status_code == 200
        assert b'anvaya-mark.png' in res.data
    original = c.get('/learning/modules/synthetic/1/source.pdf')
    assert original.data == source_pdf()
    assert original.headers['X-Content-Type-Options'] == 'nosniff'
    assert c.get('/learning/modules/synthetic/1/assets/foreign.png').status_code == 404


def test_practice_server_grading_and_csrf(client):
    c, s, app = client
    p = publish(s)
    before = s.store.path.read_bytes()
    html = c.get('/learning/modules/synthetic/1?view=practice').data
    assert b'correct_index' not in html and b'Compare the original source.' not in html
    assert s.store.path.read_bytes() == before
    endpoint = '/learning/modules/synthetic/1/attempts'
    assert c.post(endpoint, json=event(p)).status_code == 403
    assert c.post(endpoint, json=event(p), headers={**token(app), 'Origin': 'https://evil.test'}).status_code == 403
    assert c.post(endpoint, json=event(p), headers=token(app)).json['correct'] is False
    assert c.post(endpoint, json=event(p, 'new-event', 1), headers=token(app)).json['correct'] is True
    assert b'recovered' in c.get('/learning/modules/synthetic/1?view=weak').data
    assert c.get('/learning/evidence').json['attempts'] == 2
    assert c.get('/learning/evidence/export').json['events'][0]['correct'] == 0


def test_public_schema_contains_no_keys(client):
    c, s, app = client
    publish(s)
    p = c.get('/learning/modules/synthetic/1/package').json
    assert 'correct_index' not in p['questions'][0]


def test_failed_source_and_oversized_imports_no_state(client):
    c, s, app = client
    res = c.post('/learning/import', data={'package': (io.BytesIO(b'{}'), 'bad.html')}, headers=token(app))
    assert res.status_code == 400
    assert not s.store.path.exists()
    assert c.post('/learning/import', data=b'x' * 26_000_000, headers=token(app)).status_code == 413
