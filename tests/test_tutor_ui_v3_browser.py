"""Real HTTP, SQLite and Chromium. Synthetic provider; no live AI certification."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.test_tutor_final_browser import real_tutor
from tests.learning_studio.test_browser import browser

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Requires Chromium')


@pytest.mark.parametrize('width', [360,390,768,1366])
def test_capture_running_tutor(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    sid = service.create_session(course_id=course['id'], mode='doubt', source_policy='source_first', title='Understanding LU, one step at a time')
    service.ask(sid, "I don't understand elimination multipliers in LU factorization.")
    page = browser.new_page(viewport={'width': width, 'height': 844 if width < 768 else 950})
    try:
        folder = os.environ.get('ANVAYA_TUTOR_UI_ARTIFACTS')
        for surface, route in [('home','/agent'),('session','/agent/sessions/'+sid)]:
            page.goto(base + route, wait_until='networkidle')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            if folder:
                Path(folder).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(folder)/f'{surface}-{width}.png'))
                page.screenshot(path=str(Path(folder)/f'{surface}-{width}-full.png'), full_page=True)
    finally:
        page.close()


@pytest.mark.parametrize('width', [320,360,390,430,768,1024,1366])
def test_chat_first_explicit_chips_and_composer_resize(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    sid = service.create_session(course_id=course['id'], mode='doubt', source_policy='source_first')
    page = browser.new_page(viewport={'width': width, 'height': 844})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    try:
        page.goto(base+'/agent/sessions/'+sid)
        transcript = page.locator('#transcript-title').bounding_box()
        assert transcript['y'] < 520
        details = page.locator('#tutor-learning-details')
        expect(details).not_to_have_attribute('open', '')
        composer = page.locator('#agent-question')
        page.get_by_role('button', name='Hint only', exact=True).click()
        assert 'one hint' in composer.input_value()
        assert len(provider.requests) == 0
        composer.fill('A long draft\n' * 30)
        assert composer.evaluate('el => el.offsetHeight') <= 180
        page.set_viewport_size({'width':width,'height':440})
        composer.focus()
        send = page.get_by_role('button', name='Ask tutor', exact=True)
        send.scroll_into_view_if_needed()
        box = send.bounding_box()
        assert box['y'] >= 0 and box['y'] + box['height'] <= 440
        assert composer.input_value().startswith('A long draft')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        assert not errors
    finally:
        page.close()


def test_wide_inline_matrix_is_contained_at_320px(browser, real_tutor):
    base, service, path, course, provider, before = real_tutor
    provider.responses = [r'Inline matrix \(A=\begin{bmatrix}' + '&'.join(['1234567890'] * 12) + r'\end{bmatrix}\) after text.']
    sid = service.create_session(course_id=course['id'], mode='free', source_policy='source_first')
    service.ask(sid, 'Explain this matrix.')
    page = browser.new_page(viewport={'width':320,'height':844})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        expect(page.locator('.assessment-matrix')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        math = page.locator('.tutor-markdown [data-assessment-math]')
        assert math.evaluate('el => el.scrollWidth > el.clientWidth')
    finally:
        page.close()


def test_successful_send_shows_newest_answer_in_long_transcript(browser, real_tutor):
    base, service, path, course, provider, before = real_tutor
    provider.responses = [('Earlier detailed explanation. ' * 20 + '\n\n') * 35,
                          'This is the newly received answer.']
    sid = service.create_session(course_id=course['id'], mode='free', source_policy='source_first')
    service.ask(sid, 'Explain one concept.')
    page = browser.new_page(viewport={'width':390,'height':844})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.locator('#agent-question').fill('Explain the next concept.')
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        latest = page.locator('.agent-turn-assistant').last
        expect(latest).to_contain_text('newly received answer')
        box = latest.bounding_box()
        composer = page.locator('#tutor-composer').bounding_box()
        assert 0 <= box['y'] < composer['y']
        assert len(provider.requests) == 2
    finally:
        page.close()


@pytest.mark.parametrize('width', [320,1366])
def test_sticky_context_stays_below_header_and_link_is_tappable(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    provider.responses = [('A useful earlier explanation. ' * 20 + '\n\n') * 35]
    sid = service.create_session(course_id=course['id'], mode='free', source_policy='source_first')
    service.ask(sid, 'Explain this.')
    page = browser.new_page(viewport={'width':width,'height':844})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.evaluate('scrollTo(0,1000)')
        bar = page.locator('.tutor-context-bar').bounding_box()
        topbar = page.locator('.topbar').bounding_box()
        assert bar['y'] >= topbar['y'] + topbar['height'] - 1
        page.locator('.tutor-context-bar a').click()
        expect(page.locator('#tutor-learning-details')).to_have_attribute('open','')
    finally:
        page.close()


def test_provider_failure_keeps_draft_and_retry_nonce_without_automatic_retry(browser, real_tutor):
    from personal_learning_assistant.tutor.http_provider import TutorProviderRequestError
    base, service, path, course, provider, before = real_tutor
    complete = provider.complete
    failures = []
    def limited(request):
        failures.append(request)
        raise TutorProviderRequestError('429 confidential-provider-detail')
    provider.complete = limited
    sid = service.create_session(course_id=course['id'], mode='free', source_policy='source_first')
    page = browser.new_page(viewport={'width':390,'height':844})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        nonce = page.locator('[name=request_id]').input_value()
        draft = 'Please explain this privately: <img src=x onerror=alert(1)>'
        page.locator('#agent-question').fill(draft)
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.error-panel')).to_contain_text('could not complete')
        expect(page.locator('#agent-question')).to_have_value(draft)
        expect(page.locator('[name=request_id]')).to_have_value(nonce)
        expect(page.locator('#tutor-submit-status')).to_contain_text('could not complete')
        assert 'confidential-provider-detail' not in page.content()
        assert len(failures) == 1 and service.session_view(sid)['turns'] == []
        provider.complete = complete
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.agent-turn-assistant')).to_have_count(1)
        expect(page.locator('#agent-question')).to_have_value('')
        assert len(provider.requests) == 1
    finally:
        page.close()
