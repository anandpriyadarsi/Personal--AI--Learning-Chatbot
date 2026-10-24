"""Opt-in deterministic browser gate; CI enables it on Ubuntu and Windows."""
import os
import threading
import pytest
from werkzeug.serving import make_server
from .helpers import package, source_pdf, catalogue
from .test_service import publish
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Set ANVAYA_BROWSER_TESTS=1 to execute the browser gate.')


@pytest.fixture
def live(tmp_path):
    service = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    p = package(); p['title'] = 'Long source heading ' * 14
    publish(service, p)
    app = create_app({'TESTING': True, 'LEARNING_STUDIO_SERVICE_FACTORY': lambda: service})
    server = make_server('127.0.0.1', 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', service
    server.shutdown(); thread.join(timeout=10); server.server_close()


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get('ANVAYA_BROWSER_EXECUTABLE') or None)
        yield browser
        browser.close()


def screenshot(page, name):
    folder = os.environ.get('ANVAYA_BROWSER_ARTIFACTS')
    if folder:
        from pathlib import Path
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / name), full_page=True)


def no_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')


def assert_focus(page, enabled):
    from playwright.sync_api import expect
    page.wait_for_load_state('domcontentloaded')
    expect(page.locator('#ls-focus')).to_have_text('Exit focus' if enabled else 'Focus Reading')
    expect(page.locator('#ls-focus')).to_have_attribute('aria-pressed', str(enabled).lower())


def test_desktop_width_focus_escape_logo_and_contents(browser, live):
    url, service = live
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url + '/learning/modules/synthetic/1?view=learn')
    page.wait_for_function('document.querySelector("#nav-toggle").getAttribute("aria-expanded") === "true"')
    before = page.locator('#ls-reading-column').bounding_box()['width']
    page.click('#nav-toggle')
    page.wait_for_function('(before) => document.querySelector("#ls-reading-column").getBoundingClientRect().width > before + 150', arg=before)
    after = page.locator('#ls-reading-column').bounding_box()['width']
    assert after - before > 150
    page.click('#nav-toggle')
    page.wait_for_function('(before) => Math.abs(document.querySelector("#ls-reading-column").getBoundingClientRect().width - before) < 2', arg=before)
    page.click('#ls-focus')
    assert not page.locator('.topbar').is_visible() and not page.locator('#app-sidebar').is_visible()
    assert page.locator('#ls-reading-column').bounding_box()['width'] > before + 150
    assert page.locator('.ls-reading-controls img').evaluate('(img) => img.complete && img.naturalWidth > 0')
    page.click('#ls-contents')
    assert page.locator('#ls-contents-dialog').evaluate('(d) => d.open')
    page.keyboard.press('Escape')
    assert not page.locator('#ls-contents-dialog').evaluate('(d) => d.open')
    assert_focus(page, True)
    screenshot(page, 'desktop-focus.png')
    page.keyboard.press('Escape')
    assert page.locator('.topbar').is_visible() and page.locator('#app-sidebar').is_visible()
    page.evaluate('() => { document.documentElement.requestFullscreen = () => Promise.reject(new Error("denied")); }')
    page.click('#ls-fullscreen')
    page.wait_for_function('document.querySelector("#ls-control-status").textContent.includes("unavailable")')
    page.click('#ls-focus')
    no_overflow(page)
    assert page.locator('.ls-diagram').count() > 0 and not errors
    page.close()


def test_mobile_navigation_source_revision_and_practice(browser, live):
    url, service = live
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    page.goto(url + '/learning/modules/synthetic/1?view=learn')
    no_overflow(page)
    page.click('#nav-toggle')
    assert page.locator('#nav-toggle').get_attribute('aria-expanded') == 'true'
    page.keyboard.press('Escape')
    assert page.locator('#nav-toggle').get_attribute('aria-expanded') == 'false'
    page.click('#ls-focus'); page.click('#ls-contents')
    assert page.locator('#ls-contents-dialog').bounding_box()['width'] < 390
    page.click('#ls-close-contents'); page.keyboard.press('Escape')
    screenshot(page, 'mobile-learn.png')
    page.locator('.ls-source-chips a').first.click()
    page.wait_for_load_state('load')
    assert 'view=source' in page.url and page.locator('#source-page-1').count() == 1
    no_overflow(page)
    page.goto(url + '/learning/modules/synthetic/1?view=revision')
    page.emulate_media(media='print')
    assert not page.locator('.topbar').is_visible() and not page.locator('#ls-print').is_visible()
    page.emulate_media(media='screen')
    page.goto(url + '/learning/modules/synthetic/1?view=practice')
    page.check('input[type=radio][value="0"]'); page.click('.ls-question button')
    page.wait_for_function('document.querySelector(".ls-feedback").textContent.includes("Incorrect")')
    page.check('input[type=radio][value="1"]'); page.click('.ls-question button')
    page.wait_for_function('document.querySelector(".ls-feedback").textContent.includes("Correct")')
    page.goto(url + '/learning/modules/synthetic/1?view=weak')
    assert 'recovered' in page.locator('#ls-reading-column').inner_text()
    assert service.evidence()['ever_missed'] == 1
    no_overflow(page); page.close()


def test_browser_storage_failure_keyboard_access(browser, live):
    url, service = live
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.add_init_script('Object.defineProperty(window, "localStorage", {get() {throw new Error("denied");}})')
    page.goto(url + '/learning/modules/synthetic/1?view=learn')
    page.locator('#ls-contents').focus(); page.keyboard.press('Enter')
    assert page.locator('#ls-contents-dialog').evaluate('(d) => d.open')
    page.keyboard.press('Escape')
    assert page.locator('#ls-contents').evaluate('(b) => b === document.activeElement')
    page.locator('#ls-focus').focus(); page.keyboard.press('Enter')
    assert_focus(page, True)
    page.keyboard.press('Escape'); no_overflow(page); page.close()


@pytest.mark.parametrize('width',[360,390,768,1024,1366,1920])
def test_focused_view_contents_navigation_and_exit(browser,live,width):
    url,_=live
    page=browser.new_page(viewport={'width':width,'height':950})
    page.goto(url+'/learning/modules/synthetic/1?view=learn')
    page.click('#ls-focus')
    page.click('#ls-contents')
    page.locator('.ls-dialog-views a').filter(has_text='Visualise').click()
    # Tabs hide in Focus Reading; navigate through actual source/page links instead
    # after asserting a stored internal URL and then using it.
    assert_focus(page, True)
    page.click('#ls-contents')
    page.locator('#ls-contents-dialog a').first.click()
    assert_focus(page, True)
    assert not page.locator('.topbar').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.keyboard.press('Escape')
    assert_focus(page, False)
    page.reload()
    assert page.locator('.topbar').is_visible()
    page.close()


@pytest.fixture
def real_live(recovered_pilot):
    service,p,source,assets=recovered_pilot
    from pathlib import Path
    from personal_learning_assistant.learning_studio.pilot_quality import normalize_pilot
    improved,_,improved_assets=normalize_pilot(Path(os.environ['ANVAYA_TEST_RECOVERED_PILOT_ZIP']).read_bytes(),source_id=service.module(p['module_id'],1)['source']['source_id'])
    service.stage(improved,improved_assets);service.publish(improved['module_id'],2)
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:service})
    server=make_server('127.0.0.1',0,app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',p,source
    server.shutdown();thread.join(timeout=10);server.server_close()


def test_external_recovered_pilot_real_browser(browser,real_live):
    url,p,source=real_live
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    base=url+f'/learning/modules/{p["module_id"]}/1'
    page.goto(base+'?view=source')
    assert page.locator('.ls-source-page').count()==1
    for number in range(1,21):
        page.goto(base+'?view=source&page='+str(number))
        assert page.locator('.ls-source-page').count()==1
        image=page.locator('.ls-source-page img')
        image.scroll_into_view_if_needed()
        image.evaluate('(i) => i.loading = "eager"')
        page.wait_for_function('(src) => {const i=Array.from(document.images).find(i=>i.src===src);return i.complete&&i.naturalWidth>0}',arg=image.get_attribute('src') if image.get_attribute('src').startswith('http') else url+image.get_attribute('src'))
    assert page.request.get(base+'/source.pdf').body()==source
    page.goto(base+'?view=learn')
    assert page.locator('.ls-lesson').count()==1
    assert page.locator('.ls-block-source').count()==1
    page.goto(base+'?view=learn&all=1')
    assert page.locator('.ls-lesson').count()==20
    page.goto(base+'?view=learn')
    page.click('#ls-focus');screenshot(page,'v11-real-pilot-desktop-focus.png')
    page.click('#ls-contents');page.locator('.ls-dialog-views').get_by_role('link',name='Practice',exact=True).click()
    assert page.locator('.ls-question').count()==1
    assert 'Question 1 of 31' in page.locator('#ls-reading-column').inner_text()
    assert_focus(page, True)
    q=p['questions'][0];form=page.locator('.ls-question').first
    wrong=(q['correct_index']+1)%len(q['options'])
    form.locator(f'input[value="{wrong}"]').check();form.locator('button').click()
    page.wait_for_function('document.querySelector(".ls-feedback").textContent.includes("Incorrect")')
    form.locator(f'input[value="{q["correct_index"]}"]').check();form.locator('button').click()
    page.wait_for_function('document.querySelector(".ls-feedback").textContent.includes("Correct")')
    page.click('#ls-contents');page.locator('.ls-dialog-views a').filter(has_text='My Weak Questions').click()
    assert 'recovered needs recheck' in page.locator('#ls-reading-column').inner_text()
    page.locator('.ls-related-lesson').first.click()
    assert '#lesson-' in page.url
    assert_focus(page, True)
    page.set_viewport_size({'width':390,'height':844})
    no_overflow(page);screenshot(page,'v11-real-pilot-mobile.png')
    page.click('#ls-contents');page.locator('.ls-dialog-views a').filter(has_text='Day-before-exam Revision').click()
    page.emulate_media(media='print');assert not page.locator('.ls-reading-controls').is_visible()
    page.emulate_media(media='screen')
    improved=base.rsplit('/',1)[0]+'/2'
    page.goto(improved+'?view=revision')
    assert page.locator('.ls-block-recall').count()==12
    page.locator('.ls-remembered').first.click()
    page.wait_for_function('Array.from(document.querySelectorAll(".ls-engagement-status")).some(e=>e.textContent.includes("Self-report saved"))')
    page.goto(improved+'?view=learn&section=lesson-06')
    activity=page.locator('.ls-trusted-activity')
    activity.locator('summary').click();assert not activity.locator('details').evaluate('(e)=>e.open')
    activity.locator('select').select_option('jainism');activity.locator('textarea').fill('Jiva contrasts with anatta; Vedanta has different positions.')
    activity.locator('summary').click();assert activity.locator('details').evaluate('(e)=>e.open')
    page.locator('.ls-save-engagement').click()
    page.wait_for_function('document.querySelector(".ls-engagement-status").textContent.includes("Self-report saved")')
    page.reload()
    from playwright.sync_api import expect
    expect(page.locator('.ls-trusted-activity textarea')).to_have_value('Jiva contrasts with anatta; Vedanta has different positions.')
    no_overflow(page);screenshot(page,'v12-real-activity-mobile.png')
    page.goto(improved+'?view=learn&section=lesson-07')
    no_overflow(page);screenshot(page,'v12-real-graph-mobile.png')
    requests=[];page.on('request',lambda r:requests.append(r.url))
    page.goto(improved+'?view=source&page=12')
    page.locator('.ls-source-page img').evaluate('(i)=>i.loading="eager"')
    expect(page.locator('.ls-source-page img')).to_be_visible()
    assert len([u for u in requests if '/assets/' in u])==1
    assert not errors
    page.close()


def test_focus_url_fallback_without_storage(browser,live):
    url,_=live
    page=browser.new_page(viewport={'width':1440,'height':900})
    page.add_init_script('for (const key of ["localStorage","sessionStorage"]) Object.defineProperty(window,key,{get(){throw new Error("denied")}})')
    page.goto(url+'/learning/modules/synthetic/1?view=learn')
    page.click('#ls-focus');page.click('#ls-contents')
    page.locator('.ls-dialog-views a').filter(has_text='Visualise').click()
    assert_focus(page, True)
    page.keyboard.press('Escape');page.reload()
    assert_focus(page, False)
    no_overflow(page);page.close()


def test_explicit_focus_exit_survives_browser_history(browser,live):
    url,_=live
    page=browser.new_page(viewport={'width':1440,'height':900})
    page.goto(url+'/learning/modules/synthetic/1?view=learn')
    page.click('#ls-focus');page.click('#ls-contents')
    page.locator('.ls-dialog-views a').filter(has_text='Visualise').click()
    page.click('#ls-focus')
    page.go_back()
    assert_focus(page, False)
    assert page.locator('.topbar').is_visible()
    page.close()


def test_focus_exit_reload_preserves_saved_collapsed_navigation(browser,live):
    url,_=live
    page=browser.new_page(viewport={'width':1440,'height':900})
    page.goto(url+'/learning/modules/synthetic/1?view=learn')
    page.click('#nav-toggle');page.click('#ls-focus');page.click('#ls-focus');page.reload()
    assert page.locator('body').evaluate('(b)=>b.classList.contains("sidebar-collapsed")')
    assert page.locator('#nav-toggle').get_attribute('aria-expanded')=='false'
    page.click('#nav-toggle')
    assert page.locator('#nav-toggle').get_attribute('aria-expanded')=='true'
    assert page.locator('#app-sidebar').evaluate('(s)=>!s.inert')
    page.close()


def test_focus_restoration_after_deferred_reader_initialization(browser, live):
    from pathlib import Path
    url, _ = live
    page = browser.new_page(viewport={'width': 1024, 'height': 950})
    page.goto(url + '/learning/modules/synthetic/1?view=learn')
    page.click('#ls-focus')
    script = Path('personal_learning_assistant/ui/web/static/js/learning_studio.js').read_text()
    # Separate navigation commit/static DOM from the deferred reader initializer.
    page.route('**/static/js/learning_studio.js', lambda route: route.fulfill(
        content_type='application/javascript', body='window.resumeReader = () => {' + script + '};'))
    page.click('#ls-contents')
    page.locator('.ls-dialog-views').get_by_role('link', name='Visualise', exact=True).click()
    page.wait_for_load_state('load')
    assert page.locator('#ls-focus').inner_text() == 'Focus Reading'
    assert page.evaluate('JSON.parse(sessionStorage.getItem("anvaya.learning.focus.v1")).enabled') is True
    assert 'focus=1' in page.url
    page.evaluate('setTimeout(window.resumeReader, 150)')
    assert_focus(page, True)
    assert not page.locator('.topbar').is_visible()
    page.close()
