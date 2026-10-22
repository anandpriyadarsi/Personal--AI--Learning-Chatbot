"""Private-mobile HTTP contracts. No installed academic store is opened."""
import pytest
from personal_learning_assistant.ui.web import create_app


def app(**extra):
    return create_app({'TESTING': True, 'PRIVATE_MOBILE_MODE': True, **extra})


def test_manifest_and_reviewed_assets_are_locally_available():
    c = app().test_client()
    r = c.get('/manifest.webmanifest')
    assert r.status_code == 200
    assert r.mimetype == 'application/manifest+json'
    data = r.json
    assert data['display'] == 'standalone' and data['start_url'] == '/'
    assert data['scope'] == '/' and data['id'] == '/'
    for icon in data['icons']:
        assert c.get(icon['src']).status_code == 200
    assert {i['sizes'] for i in data['icons']} >= {'192x192', '512x512'}


@pytest.mark.parametrize('path', ['/healthz', '/mobile/settings', '/missing-private-page'])
def test_private_responses_are_no_store_and_same_origin(path):
    r = app().test_client().get(path)
    assert r.headers['Cache-Control'] == 'no-store'
    assert r.headers['Referrer-Policy'] == 'same-origin'
    assert "connect-src 'self'" in r.headers['Content-Security-Policy']
    assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']


def test_private_mode_rejects_remote_and_cross_site_requests():
    c = app().test_client()
    assert c.get('/healthz', environ_base={'REMOTE_ADDR': '192.168.1.15'}).status_code == 403
    assert c.get('/healthz', headers={'Host': 'attacker.invalid'}).status_code == 400
    assert c.post('/agent/sessions', headers={'Origin': 'https://attacker.invalid'}).status_code == 403


def test_cloud_provider_is_denied_even_with_keys(monkeypatch):
    from personal_learning_assistant.tutor.http_provider import OpenAICompatibleTutorProvider
    from personal_learning_assistant.tutor.provider import TutorProviderUnavailableError
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, 'requests', SimpleNamespace(
        post=lambda *a, **k: pytest.fail('Outbound AI call')))
    p = OpenAICompatibleTutorProvider(api_url='https://provider.invalid', api_key='synthetic', model='synthetic')
    with app().app_context():
        assert p.configured is False
        with pytest.raises(TutorProviderUnavailableError):
            p.complete(None)
    with app(MOBILE_ALLOW_CLOUD_AI=True).app_context():
        assert p.configured is False  # Missing data acknowledgement.
    with app(MOBILE_ALLOW_CLOUD_AI=True,
             MOBILE_AI_DATA_ACK='questions-sources-history-leave-device').app_context():
        assert p.configured is True
    with create_app({'TESTING': True}).app_context():
        assert p.configured is True  # Existing desktop policy preserved.


def test_worker_has_root_scope_and_no_cacheable_errors():
    c = app().test_client()
    r = c.get('/mobile-sw.js')
    assert r.status_code == 200 and r.mimetype == 'application/javascript'
    assert r.headers['Cache-Control'] == 'no-store'
    assert r.headers['Service-Worker-Allowed'] == '/'
    fallback = c.get('/mobile/offline')
    assert fallback.status_code == 200
    assert b'Python host' in fallback.data and b'not saved' in fallback.data
    assert b'localStorage' not in fallback.data


def test_private_mode_is_environment_selectable(monkeypatch):
    monkeypatch.setenv('ANVAYA_PRIVATE_MOBILE', 'true')
    assert create_app({'TESTING': True}).config['PRIVATE_MOBILE_MODE'] is True
