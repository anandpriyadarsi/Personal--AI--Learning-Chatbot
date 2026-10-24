"""HTTP regression for private Tutor presentation and recoverable submissions."""
from html import unescape
import re
import pytest
from personal_learning_assistant.ui.web import create_app
from tests.test_phase7_5_academic_agent_web import build_test_web_service


@pytest.fixture
def ui(tmp_path):
    service, path, course, provider, retrieval = build_test_web_service(tmp_path)
    app = create_app({'TESTING': True, 'PRIVATE_MOBILE_MODE': True,
                      'ANDROID_LOCAL_RUNTIME': True,
                      'ACADEMIC_AGENT_WEB_SERVICE_FACTORY': lambda: service})
    return app, service, course


def test_android_home_discloses_unavailable_ai_and_prioritizes_start(ui):
    app, service, course = ui
    html = app.test_client().get('/agent').text
    assert 'ANVAYA Tutor' in html
    assert 'Online AI unavailable in this Android build' in html
    assert html.index('id="tutor-start"') < html.index('id="tutor-mentor"')
    assert 'Native secure key storage' in html
    assert 'name="api_key"' not in html


def test_session_conversation_precedes_secondary_learning_details(ui):
    app, service, course = ui
    sid = service.create_session(course_id=course['id'], mode='concept', source_policy='source_only')
    html = app.test_client().get('/agent/sessions/' + sid).text
    assert html.index('id="transcript-title"') < html.index('id="tutor-learning-details"')
    assert 'id="tutor-composer"' in html
    assert 'id="tutor-submit-status"' in html
    assert 'id="tutor-provider-state"' in html


def test_failed_provider_submission_preserves_escaped_draft_and_request_id(ui):
    app, service, course = ui
    sid = service.create_session(course_id=course['id'], mode='concept', source_policy='source_first')
    client = app.test_client()
    client.get('/agent/sessions/' + sid)
    draft = 'Why does </textarea><script>alert(1)</script> fail in LU?'
    response = client.post('/agent/sessions/' + sid + '/ask', data={
        'csrf_token': app.extensions['tutor_action_csrf'], 'request_id': 'recover-same-request',
        'question': draft})
    assert response.status_code == 503
    value = re.search(r'<textarea[^>]*id="agent-question"[^>]*>(.*?)</textarea>', response.text, re.S).group(1)
    assert unescape(value) == draft
    assert '<script>alert(1)</script>' not in response.text
    assert 'value="recover-same-request"' in response.text
    assert service.session_view(sid)['turns'] == []


def test_invalid_csrf_does_not_echo_submitted_payload(ui):
    app, service, course = ui
    sid = service.create_session(course_id=course['id'], mode='concept', source_policy='source_first')
    response = app.test_client().post('/agent/sessions/' + sid + '/ask', data={
        'csrf_token': 'bad', 'question': 'do-not-echo-cross-site', 'request_id': 'untrusted-id'})
    assert response.status_code == 403
    assert 'do-not-echo-cross-site' not in response.text
    assert 'untrusted-id' not in response.text


def test_requested_mentor_advice_remains_expanded(ui):
    app, service, course = ui
    response = app.test_client().get('/agent?course=' + course['code'])
    assert response.status_code == 200
    assert re.search(r'<details[^>]*id="tutor-mentor"[^>]*\bopen\b', response.text)
