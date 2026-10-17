"""Real SSR dashboards on loopback using disposable canonical SQLite fixtures."""
import os
import sqlite3
from pathlib import Path
from threading import Thread
import pytest
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from tests.test_planning_analysis_v2 import _database, service, NOW
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.services.home_dashboard_service import unavailable_home_dashboard
from personal_learning_assistant.services.planning_dashboard_service import unavailable_planning_dashboard
from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service

@pytest.fixture(scope='module')
def chromium():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()

@pytest.fixture(params=['populated', 'empty'])
def live_hub(tmp_path, monkeypatch, request):
    monkeypatch.chdir(tmp_path)
    path = _database(tmp_path)
    with sqlite3.connect(path) as con:
        if request.param == 'empty':
            con.execute('DELETE FROM assessment_response_evaluations')
            con.execute('DELETE FROM assessment_session_evaluations')
            con.execute('DELETE FROM assessment_test_sessions')
        else:
            con.execute("INSERT INTO planner_tasks(id,title,priority,course_id,estimated_minutes,due_on,preferred_day,created_at,updated_at) VALUES('browser-task','Review matrix factorization and prepare questions for the next class','P1','course-ma',40,'2026-09-28','2026-09-28','2026-09-27','2026-09-27')")
            con.execute("INSERT INTO academic_events(id,course_id,event_kind,title,starts_at,ends_at,created_at,updated_at) VALUES('browser-event','course-ma','class','Linear algebra class','2026-09-28T10:00:00','2026-09-28T11:00:00','2026-09-27','2026-09-27')")
    app = create_app({'TESTING':True, 'PLANNING_NOW': lambda: NOW.isoformat(),
        'ACADEMIC_OVERVIEW_SERVICE_FACTORY':lambda: service(path),
        'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY':lambda: build_operational_planner_web_service(path),
        'HOME_DASHBOARD_PROVIDER':unavailable_home_dashboard,
        'PLANNING_DASHBOARD_PROVIDER':unavailable_planning_dashboard,
        'LEARNING_STUDIO_DATABASE':str(tmp_path/'absent_learning.db'),
        'LEARNING_STUDIO_SOURCE_DATABASE':str(path)})
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', request.param
    server.shutdown(); thread.join(); server.server_close()

@pytest.mark.parametrize('width', [360,390,768,1024,1366,1536,1920])
@pytest.mark.parametrize('route', ['/analysis','/planning'])
def test_hubs_responsive_and_native_filters(chromium, live_hub, width, route):
    base, state = live_hub
    context = chromium.new_context(viewport={'width':width,'height':1000}, java_script_enabled=False)
    page = context.new_page()
    response = page.goto(base+route+'?view=week&date=2026-09-28')
    assert response.status == 200
    expect(page.locator('.pa-hero')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.pa-panel,.pa-metrics,.pa-filters').evaluate_all('(els) => els.every(e => e.getBoundingClientRect().right <= innerWidth + 1 && e.getBoundingClientRect().left >= 0)')
    if state == 'populated':
        if route == '/analysis':
            expect(page.locator('.pa-table')).to_contain_text('3 / 4')
        else:
            expect(page.locator('.pa-timeline')).to_contain_text('Linear algebra class')
            expect(page.locator('.pa-task-list')).to_contain_text('Review matrix factorization')
    else:
        expect(page.locator('.pa-empty').first).to_be_visible()
    page.locator('select[name=course]').select_option('MA103N')
    if route == '/analysis':
        page.locator('select[name=days]').select_option('7')
        page.locator('select[name=evidence]').select_option('evaluated')
    page.get_by_role('button', name='Apply filters').click()
    expect(page.locator('select[name=course]')).to_have_value('MA103N')
    if route == '/analysis':
        expect(page.locator('select[name=days]')).to_have_value('7')
        expect(page.locator('select[name=evidence]')).to_have_value('evaluated')
    else:
        assert page.locator('select[name=days],select[name=evidence]').count() == 0
    if route == '/planning':
        assert 'view=week' in page.url and 'date=2026-09-28' in page.url
    page.locator('select[name=course]').focus(); page.keyboard.press('Tab')
    focus_target = page.locator('select[name=days]') if route == '/analysis' else page.get_by_role('button', name='Apply filters')
    expect(focus_target).to_be_focused()
    assert focus_target.evaluate('e => getComputedStyle(e).outlineStyle') != 'none'
    page.locator('.pa-disclosure').first.locator('summary').click()
    assert page.locator('.pa-disclosure').first.get_attribute('open') is not None
    assert all('None' not in text for text in page.locator('.pa-metrics').all_inner_texts())
    folder = os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
    if folder:
        target=Path(folder); target.mkdir(parents=True,exist_ok=True)
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(target/f'hub-{route[1:]}-{state}-{width}.png'),full_page=True)
    context.close()

@pytest.mark.parametrize('width', [390,1366])
def test_analysis_to_saved_approved_completed_day_and_review(chromium, live_hub, width):
    base, state = live_hub
    context = chromium.new_context(viewport={'width':width,'height':1000},java_script_enabled=False)
    page = context.new_page()
    page.goto(base+'/analysis')
    page.get_by_role('link',name='Plan your next session').click()
    page.get_by_role('link',name='Review agenda',exact=False).click()
    page.locator('input[name=start]').fill('18:00')
    page.locator('input[name=end]').fill('20:00')
    page.get_by_role('button',name='Preview available time').click()
    expect(page.get_by_role('button',name='Save proposal as draft')).to_be_visible()
    assert page.get_by_role('button',name='Complete',exact=True).count()==0
    page.get_by_role('button',name='Save proposal as draft').click()
    expect(page.get_by_role('button',name='Approve day')).to_be_visible()
    if state=='populated':
        expect(page.locator('.planner-agenda-items')).to_contain_text('18:00')
    page.get_by_role('button',name='Approve day').click()
    if state=='populated':
        page.locator('input[name=actual_minutes]').fill('35')
        page.get_by_role('button',name='Complete',exact=True).click()
        expect(page.locator('.planner-agenda-items')).to_contain_text('Completed')
    page.goto(base+'/planning/review/week/2026-09-28')
    assert page.locator('main').count()==1
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    expect(page.locator('textarea[name=what_worked]')).to_be_visible()
    page.locator('textarea[name=what_worked]').fill('A clear study window helped.')
    page.get_by_role('button',name='Save review',exact=True).click()
    expect(page.locator('textarea[name=what_worked]')).to_have_value('A clear study window helped.')
    context.close()
