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
    assert page.locator('#ls-focus').inner_text() == 'Exit focus'
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
    assert 'view=source' in page.url and page.locator('#source-page-1').count() == 1
    no_overflow(page)
    page.goto(url + '/learning/modules/synthetic/1?view=revision')
    page.emulate_media(media='print')
    assert not page.locator('.topbar').is_visible() and not page.locator('#ls-print').is_visible()
    page.emulate_media(media='screen')
    page.goto(url + '/learning/modules/synthetic/1?view=practice')
    page.check('input[value="0"]'); page.click('.ls-question button')
    page.wait_for_function('document.querySelector(".ls-feedback").textContent.includes("Incorrect")')
    page.check('input[value="1"]'); page.click('.ls-question button')
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
    assert page.locator('#ls-focus').get_attribute('aria-pressed') == 'true'
    page.keyboard.press('Escape'); no_overflow(page); page.close()
