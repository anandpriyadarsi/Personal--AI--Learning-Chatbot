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
        page.get_by_role('button', name='+ Tools', exact=True).click()
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


@pytest.mark.parametrize('width', [320, 1366])
def test_no_redundant_context_bar_but_learning_details_remain_accessible(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    provider.responses = [('A useful earlier explanation. ' * 20 + '\\n\\n') * 35]
    sid = service.create_session(course_id=course['id'], mode='free', source_policy='source_first')
    service.ask(sid, 'Explain this.')
    page = browser.new_page(viewport={'width':width,'height':844})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        assert page.locator('.tutor-context-bar').count() == 0
        assert page.get_by_text('Learning details ↓').count() == 0
        details = page.locator('#tutor-learning-details')
        expect(details).not_to_have_attribute('open','')
        details.locator('summary').first.click()
        expect(details).to_have_attribute('open','')
        expect(details).to_contain_text('Source policy')
    finally:
        page.close()


@pytest.mark.parametrize('width', [1024, 1366, 1745])
def test_sidebar_collapse_fills_tutor_viewport_without_outer_scroll(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    provider.responses = [('Long LU factorization explanation. ' * 30 + '\\n\\n') * 24]
    sid = service.create_session(course_id=course['id'], mode='concept', source_policy='source_first')
    service.ask(sid, 'Explain LU factorization.')
    page = browser.new_page(viewport={'width':width, 'height':760})
    try:
        page.goto(base + '/agent/sessions/' + sid)
        reader = page.locator('#main-content')
        composer = page.locator('#tutor-composer')
        assert reader.evaluate('(el) => el.scrollHeight > el.clientHeight')
        expanded_width = reader.bounding_box()['width']
        page.locator('#agent-question').fill('Preserve my draft when I hide navigation')
        page.locator('#nav-toggle').click()
        page.wait_for_function("document.body.classList.contains('sidebar-collapsed')")
        # Wait for the shell's 180ms width transition to reach its final size.
        page.wait_for_function("""() => {
          const shell = document.querySelector('.app-shell');
          const sidebar = document.querySelector('.app-sidebar');
          const main = document.querySelector('.app-main');
          const viewport = document.documentElement.clientWidth;
          return Math.abs(main.getBoundingClientRect().width - viewport) <= 3 &&
                 sidebar.getBoundingClientRect().right <= 3 &&
                 shell.getBoundingClientRect().width >= viewport - 2;
        }""")
        content = reader.bounding_box()
        dock = composer.bounding_box()
        assert content['x'] <= 40
        assert content['x'] + content['width'] >= width - 45
        assert content['width'] > expanded_width + 100
        assert dock['y'] >= content['y'] + content['height'] - 2
        assert page.locator('#agent-question').input_value() == 'Preserve my draft when I hide navigation'
        assert page.evaluate('document.scrollingElement.scrollHeight <= innerHeight + 2')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        reader.evaluate('(el) => el.scrollTop = el.scrollHeight')
        assert page.evaluate('document.scrollingElement.scrollHeight <= innerHeight + 2')
        page.locator('#nav-toggle').click()
        page.wait_for_function("!document.body.classList.contains('sidebar-collapsed')")
        assert page.locator('#agent-question').input_value() == 'Preserve my draft when I hide navigation'
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


def test_phone_composer_keeps_full_readable_input_width(browser, real_tutor):
    base, service, path, course, provider, before = real_tutor
    sid = service.create_session(course_id=course['id'], mode='free', source_policy='source_first')
    page = browser.new_page(viewport={'width':390,'height':844})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        width = page.locator('#agent-question').bounding_box()['width']
        available = page.locator('#tutor-ask-form').bounding_box()['width']
        assert width >= .55 * available  # Compact Tools and Send share one row.
        assert width >= 150
    finally:
        page.close()


@pytest.mark.parametrize('width', [390,1366])
def test_light_tutor_uses_saved_app_theme_and_stays_readable(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    sid = service.create_session(course_id=course['id'], mode='free', source_policy='source_first')
    service.ask(sid, 'Explain this concept simply.')
    page = browser.new_page(viewport={'width':width,'height':844})
    try:
        page.goto(base+'/mobile/settings')
        page.locator('#mobile-theme').select_option('light')
        page.goto(base+'/agent/sessions/'+sid)
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        assert page.locator('#agent-question').evaluate('el => getComputedStyle(el).color !== getComputedStyle(el).backgroundColor')
        folder = os.environ.get('ANVAYA_TUTOR_UI_ARTIFACTS')
        if folder:
            Path(folder).mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(Path(folder)/f'session-light-{width}.png'))
    finally:
        page.close()


@pytest.mark.parametrize('width,height', [
    (320, 700), (360, 740), (390, 844), (768, 900), (1366, 900),
])
def test_compact_dock_does_not_overlap_answers_and_tools_expand(browser, real_tutor, width, height):
    base, service, path, course, provider, before = real_tutor
    provider.responses = [('The first explanation contains useful mathematics. ' * 20 + '\\n\\n') * 20]
    sid = service.create_session(course_id=course['id'], mode='concept', source_policy='source_first')
    service.ask(sid, 'Explain LU factorization.')
    page = browser.new_page(viewport={'width': width, 'height': height})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(base + '/agent/sessions/' + sid)
        reader = page.locator('#main-content')
        dock = page.locator('#tutor-composer')
        assert dock.evaluate('(element) => getComputedStyle(element).position') != 'fixed'
        assert reader.evaluate('(element) => getComputedStyle(element).overflowY') == 'auto'
        assert reader.evaluate('(element) => element.scrollHeight > element.clientHeight')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')

        def separate():
            reading = reader.bounding_box()
            composer = dock.bounding_box()
            assert reading['y'] + reading['height'] <= composer['y'] + 2
            assert composer['y'] + composer['height'] <= height + 1

        separate()
        reader.evaluate('(element) => element.scrollTop = element.scrollHeight')
        separate()
        reader.evaluate('(element) => element.scrollTop = 0')
        separate()

        tools = page.get_by_role('button', name='+ Tools', exact=True)
        shortcuts = page.locator('#tutor-quick-prompts')
        expect(shortcuts).to_be_hidden()
        expect(tools).to_have_attribute('aria-expanded', 'false')
        tools.click()
        expect(shortcuts).to_be_visible()
        expect(tools).to_have_attribute('aria-expanded', 'true')
        separate()
        page.get_by_role('button', name='Worked example').click()
        expect(shortcuts).to_be_hidden()
        expect(tools).to_have_attribute('aria-expanded', 'false')
        expect(page.locator('#agent-question')).to_have_value('Show one worked example and verify the calculation.')
        assert len(provider.requests) == 1  # No automatic send from Tools.

        tools.click()
        page.keyboard.press('Escape')
        expect(shortcuts).to_be_hidden()
        separate()
        assert not errors, errors
    finally:
        page.close()


@pytest.mark.parametrize('width', [360, 390, 1366])
def test_compact_bar_remains_separate_at_short_viewport(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    sid = service.create_session(course_id=course['id'], source_policy='source_first')
    page = browser.new_page(viewport={'width': width, 'height': 440})
    try:
        page.goto(base + '/agent/sessions/' + sid)
        page.locator('#agent-question').fill('A multi-line question ' * 35)
        reading = page.locator('#main-content').bounding_box()
        dock = page.locator('#tutor-composer').bounding_box()
        assert reading['y'] + reading['height'] <= dock['y'] + 2
        assert dock['y'] + dock['height'] <= 441
        assert page.locator('#agent-question').bounding_box()['width'] >= 150
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    finally:
        page.close()


@pytest.mark.parametrize('width', [390, 1024, 1366, 1745])
def test_tutor_home_uses_screen_and_chat_rename_is_accessible(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    sid = service.create_session(course_id=course['id'], title='My original chat',
                                 mode='concept', source_policy='source_first')
    page = browser.new_page(viewport={'width': width, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(base + '/agent', wait_until='networkidle')
        page.locator('#nav-toggle').click() if width >= 1024 else None
        if width >= 1024:
            page.wait_for_function("document.body.classList.contains('sidebar-collapsed')")
            page.wait_for_function("""() => {
                const content = document.getElementById('main-content').getBoundingClientRect();
                return content.left <= 2 && content.right >= document.documentElement.clientWidth - 2;
            }""")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        home = page.locator('.tutor-home-grid')
        assert home.is_visible()
        start = page.locator('#tutor-start').bounding_box()
        history = page.locator('#tutor-history').bounding_box()
        if width >= 1366:
            assert history['x'] > start['x'] + start['width'] - 3
            assert abs(history['y'] - start['y']) <= 5
        else:
            assert history['y'] >= start['y'] + start['height'] - 3
        chat_link = page.locator('.tutor-history-link', has_text='My original chat')
        assert chat_link.count() == 1
        assert chat_link.evaluate('(el) => getComputedStyle(el).textDecorationLine') == 'none'
        page.get_by_label('Rename My original chat').click()
        rename = page.get_by_label('Rename chat')
        expect(rename).to_have_value('My original chat')
        rename.fill('Renamed LU study chat')
        page.get_by_role('button', name='Save name').click()
        expect(page.locator('.tutor-history-link', has_text='Renamed LU study chat')).to_have_count(1)
        assert service.session_view(sid)['title'] == 'Renamed LU study chat'
        assert len(provider.requests) == 0
        assert not errors
    finally:
        page.close()
