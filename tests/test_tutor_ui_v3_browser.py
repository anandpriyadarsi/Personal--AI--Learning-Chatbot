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
