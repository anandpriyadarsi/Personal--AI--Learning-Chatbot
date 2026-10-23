"""Opt-in real Chromium journeys against disposable synthetic Flask stores.

Run: ANVAYA_BROWSER_TESTS=1 python -m pytest -q tests/test_ui_v2_browser.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.ui_v2_fixtures import fingerprint, live_ui

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Set ANVAYA_BROWSER_TESTS=1 for real Chromium acceptance')
VIEWPORTS = [(320, 700), (360, 800), (390, 844), (768, 1024), (1024, 768), (1366, 768), (1536, 864), (1920, 1080)]
PAGES = ['home', 'vault', 'obsidian-reader', 'notes', 'notes-reader', 'knowledge', 'knowledge-reader', 'courses', 'resources']


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture(scope='module')
def ui(tmp_path_factory):
    with live_ui(tmp_path_factory.mktemp('ui-v2')) as fixture:
        yield fixture


@pytest.fixture
def context(browser, ui):
    context = browser.new_context(reduced_motion='reduce')
    context.set_default_timeout(5000)
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(ui['base']) else route.abort())
    yield context
    context.close()


@pytest.mark.parametrize('width,height', VIEWPORTS)
@pytest.mark.parametrize('surface', PAGES)
def test_responsive_surfaces_have_one_main_no_overflow_or_js_errors(context, ui, width, height, surface):
    page = context.new_page()
    page.set_viewport_size({'width': width, 'height': height})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    # Static layout is ready at load; tracking heartbeats do not define page readiness.
    response = page.goto(ui['base'] + ui['routes'][surface], wait_until='load')
    assert response.status == 200
    assert page.locator('main').count() == 1
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'{surface} overflows at {width}px'
    assert not errors
    assert page.evaluate('window.__unsafeMarkdown !== true')
    output = os.environ.get('ANVAYA_UI_V2_ARTIFACTS')
    # Broad viewport evidence without hundreds of duplicate images.
    if output and (width in (390, 1366) or PAGES.index(surface) == VIEWPORTS.index((width, height))):
        Path(output).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(output) / f'{surface}-{width}.png'), full_page=True)


def test_home_primary_action_and_mobile_navigation(context, ui):
    page = context.new_page()
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(ui['base'])
    toggle = page.locator('#nav-toggle')
    toggle.click()
    assert toggle.get_attribute('aria-expanded') == 'true'
    page.keyboard.press('Escape')
    assert toggle.get_attribute('aria-expanded') == 'false'
    toggle.click()
    page.locator('#nav-backdrop').click(position={'x': 380, 'y': 100}, force=True)
    assert toggle.get_attribute('aria-expanded') == 'false'
    page.locator('main a[href="/obsidian"]').first.click()
    assert page.url.endswith('/obsidian')
    assert page.locator('.nav-item[aria-current="page"]').count() == 1


def test_vault_search_link_back_and_source_immutability(context, ui):
    page = context.new_page()
    before = fingerprint(ui['note_path'])
    page.goto(ui['base'] + '/obsidian')
    search = page.locator('main input[name="q"]')
    search.fill('LU')
    search.press('Enter')
    page.locator('main a[href*="/obsidian/note?"]').filter(has_text='LU').first.click()
    assert 'path=Math' in page.url
    assert page.locator('.obsidian-reading-view').inner_text().find('Worked example') >= 0
    linked = page.locator('main a[href*="Rank.md"]').first
    linked.click()
    assert 'Rank.md' in page.url
    page.go_back()
    assert 'LU.md' in page.url
    assert fingerprint(ui['note_path']) == before


def test_companion_keyboard_save_persists_without_changing_vault(context, ui):
    page = context.new_page()
    before = fingerprint(ui['note_path'])
    page.goto(ui['base'] + ui['routes']['obsidian-reader'])
    launcher = page.locator('#notes-study-tools-launcher')
    launcher.click()
    saved = page.locator('[data-study-tab="saved"]')
    saved.focus()
    page.keyboard.press('ArrowRight')
    doubt = page.locator('[data-study-tab="doubts"]')
    assert doubt.get_attribute('aria-selected') == 'true'
    assert doubt.evaluate('element => element === document.activeElement')
    page.locator('[data-study-panel="doubts"] textarea[name="entry_text"]').fill('Synthetic question: why use a pivot?')
    page.locator('[data-study-panel="doubts"] button[type="submit"]').last.click()
    page.reload()
    assert 'Synthetic question: why use a pivot?' in page.locator('[data-study-panel="doubts"]').inner_text()
    assert fingerprint(ui['note_path']) == before
    page.keyboard.press('Escape')
    assert launcher.get_attribute('aria-expanded') == 'false'


@pytest.mark.parametrize('surface', ['obsidian-reader', 'notes-reader'])
def test_focus_reading_is_reversible_and_keyboard_operable(context, ui, surface):
    page = context.new_page()
    page.goto(ui['base'] + ui['routes'][surface])
    focus = page.locator('[data-workspace-focus]')
    focus.focus()
    page.keyboard.press('Enter')
    assert focus.get_attribute('aria-pressed') == 'true'
    page.keyboard.press('Escape')
    assert focus.get_attribute('aria-pressed') == 'false'


def test_personal_note_filter_reader_editor_preserves_identity(context, ui):
    page = context.new_page()
    page.goto(ui['base'] + '/notes')
    page.locator('main input[name="q"]').fill('Elimination')
    page.locator('main input[name="q"]').press('Enter')
    assert page.locator('.anvaya-note-card-link').count() == 1
    page.locator('.anvaya-note-card-link').click()
    assert ui['note_id'] in page.url
    page.get_by_role('link', name='Edit note', exact=True).click()
    assert page.locator('input[name="title"]').input_value() == 'Elimination practice'
    assert 'Worked example' in page.locator('textarea[name="body"]').input_value()
    assert ui['notes_repository'].get_note(ui['note_id'])['title'] == 'Elimination practice'


def test_no_js_search_readers_and_gets_are_read_only(browser, ui):
    paths = [ui[name] for name in ('note_path', 'database_path', 'resources_path')] + [ui['notes_repository'].notes_path]
    before = [fingerprint(path) for path in paths]
    with browser.new_context(java_script_enabled=False, viewport={'width': 390, 'height': 844}) as context:
        page = context.new_page()
        page.goto(ui['base'])
        search = page.locator('#global-study-search')
        search.fill('LU')
        search.press('Enter')
        assert '/library?view=search&q=LU' in page.url
        page.get_by_role('link', name='MIT 18.06 Lecture 4', exact=True).click()
        assert page.url.endswith('/knowledge/item/d-lu')
        original = page.get_by_role('link', name='Open original', exact=False)
        assert original.get_attribute('href') == 'https://example.com/lu'
        for surface in ('notes-reader', 'obsidian-reader', 'resources'):
            assert page.goto(ui['base'] + ui['routes'][surface]).status == 200
    assert [fingerprint(path) for path in paths] == before


def test_resources_add_and_status_use_disposable_store(context, ui):
    page = context.new_page()
    page.goto(ui['base'] + '/resources')
    page.locator('#new-resource summary').click()
    form = page.locator('#new-resource form')
    form.locator('[name="title"]').fill('Synthetic revision resource')
    form.locator('[name="resource_type"]').fill('Article')
    form.locator('[name="link"]').fill('https://example.com/revision')
    form.get_by_role('button', name='Add resource', exact=True).click()
    row = page.locator('li[id^="resource-"]').filter(has_text='Synthetic revision resource')
    row.locator('select[name="status"]').select_option('Completed')
    row.get_by_role('button', name='Update', exact=True).click()
    page.reload()
    row = page.locator('li[id^="resource-"]').filter(has_text='Synthetic revision resource')
    assert row.locator('select[name="status"]').input_value() == 'Completed'
    import json
    saved = json.loads(ui['resources_path'].read_text(encoding='utf-8'))
    assert any(item['title'] == 'Synthetic revision resource' and item['status'] == 'Completed' for item in saved)


@pytest.mark.parametrize('state', ['disconnected', 'empty', 'unavailable'])
def test_vault_empty_disconnected_unavailable_states(context, ui, tmp_path, state):
    from copy import deepcopy
    saved = deepcopy(ui['config'].config)
    try:
        if state == 'disconnected':
            ui['config'].config['enabled'] = False
        elif state == 'empty':
            (tmp_path / '.obsidian').mkdir()
            ui['config'].config['vault_path'] = str(tmp_path)
        else:
            ui['config'].config['vault_path'] = str(tmp_path / 'missing')
        page = context.new_page()
        page.set_viewport_size({'width': 320, 'height': 700})
        response = page.goto(ui['base'] + '/obsidian')
        assert response.status == 200
        assert page.locator('main').count() == 1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not page.locator('main a[href*="/obsidian/note?"]').count()
        assert str(tmp_path) not in page.locator('main').inner_text()
    finally:
        ui['config'].config = saved


def test_personal_drawer_initial_tab_is_keyboard_reachable(context, ui):
    page = context.new_page()
    page.goto(ui['base'] + ui['routes']['notes-reader'])
    page.locator('#notes-study-tools-launcher').click()
    saved = page.locator('[data-study-tab="saved"]')
    # Opening transfers focus on the next animation frame; require the real
    # focused state before sending keyboard input, including on busy CI runners.
    from playwright.sync_api import expect
    expect(saved).to_have_attribute('tabindex', '0')
    expect(saved).to_be_focused()
    page.keyboard.press('ArrowRight')
    assert page.locator('[data-study-tab="doubts"]').get_attribute('aria-selected') == 'true'
    assert page.locator('[data-study-panel="doubts"] textarea').is_visible()


def test_focus_resize_restores_operable_sidebar(context, ui):
    page = context.new_page()
    page.set_viewport_size({'width':390,'height':844})
    page.goto(ui['base'] + ui['routes']['obsidian-reader'])
    page.locator('[data-workspace-focus]').click()
    page.set_viewport_size({'width':1366,'height':768})
    page.locator('[data-workspace-focus]').click()
    assert page.locator('#app-sidebar').evaluate('el => !el.inert')
    link = page.locator('#app-sidebar a[href="/notes"]')
    link.focus()
    assert link.evaluate('el => el === document.activeElement')


def test_mobile_notes_show_first_card_without_filter_wall(context, ui):
    page = context.new_page()
    page.set_viewport_size({'width':390,'height':844})
    page.goto(ui['base'] + '/notes')
    assert page.locator('.anvaya-note-card-link').first.bounding_box()['y'] < 750


@pytest.mark.parametrize('surface', ['obsidian-reader', 'notes-reader'])
def test_study_tools_launcher_does_not_cover_reading_column(context, ui, surface):
    page = context.new_page(); page.set_viewport_size({'width':390,'height':844})
    page.goto(ui['base'] + ui['routes'][surface])
    launcher = page.locator('#notes-study-tools-launcher').bounding_box()
    article = page.locator('main article').first.bounding_box()
    assert launcher['y'] + launcher['height'] <= article['y']


def test_mobile_no_javascript_navigation_is_native(browser, ui):
    with browser.new_context(java_script_enabled=False, viewport={'width':390,'height':844}) as context:
        page = context.new_page()
        page.goto(ui['base'])
        page.locator('.ws-fallback-nav summary').click()
        page.locator('.ws-fallback-nav a[href="/obsidian"]').click()
        assert page.url.endswith('/obsidian')
        assert page.locator('#obsidian-query').is_visible()


@pytest.mark.parametrize('width', [390,1366])
def test_focus_navigation_reopens_sidebar(context, ui, width):
    page=context.new_page();page.set_viewport_size({'width':width,'height':844})
    page.goto(ui['base']+ui['routes']['obsidian-reader'])
    page.locator('[data-workspace-focus]').click()
    page.locator('#nav-toggle').click()
    assert not page.locator('body').evaluate("el=>el.classList.contains('workspace-focus')")
    assert page.locator('#nav-toggle').get_attribute('aria-expanded') == 'true'
    assert page.locator('#app-sidebar').evaluate('el=>!el.inert')


def test_animated_drawer_open_moves_keyboard_focus(context, ui):
    from playwright.sync_api import expect
    page=context.new_page();page.emulate_media(reduced_motion='no-preference')
    page.goto(ui['base']+ui['routes']['notes-reader'])
    page.locator('#notes-study-tools-launcher').focus();page.keyboard.press('Enter')
    expect(page.locator('[data-study-tab="saved"]')).to_be_focused(timeout=2000)
    page.keyboard.press('ArrowRight')
    expect(page.locator('[data-study-tab="doubts"]')).to_be_focused()
