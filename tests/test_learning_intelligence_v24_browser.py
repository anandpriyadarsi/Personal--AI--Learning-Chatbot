"""Native Chromium V2.4 source/help/planner loop; synthetic disposable owners."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from threading import Thread
import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server
from tests.learning_studio.test_browser import browser
from tests.academic_evidence_v23_fixtures import uc_owners
from tests.test_academic_evidence_v23 import NOW
from tests.test_academic_evidence_v23_web import app
from tests.test_academic_evidence_v23_browser import fits, shot

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Set ANVAYA_BROWSER_TESTS=1 for native Chromium.')

@pytest.fixture
def live_v24(uc_owners):
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    application=app(uc_owners,ACADEMIC_DATABASE_PATH=uc_owners[0],
        ACADEMIC_OVERVIEW_SERVICE_FACTORY=lambda:AcademicOverviewService(uc_owners[0],now=lambda:NOW,local_timezone='UTC'))
    server=make_server('127.0.0.1',0,application,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(server.server_port),uc_owners
    finally:server.shutdown();thread.join(timeout=5);server.server_close()


@pytest.mark.parametrize('width',[390,768,1366])
def test_complete_learning_help_and_effort_journey(browser,live_v24,width):
    base,owners=live_v24
    context=browser.new_context(viewport={'width':width,'height':1000})
    page=context.new_page();errors=[];external=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def local(route):
        if route.request.url.startswith(base+'/'):route.continue_()
        else:external.append(route.request.url);route.abort()
    context.route('**/*',local)
    lesson=base+'/learning/modules/uc100n-demo/1'
    evidence=base+'/academic-evidence/learning/uc100n-demo/1'
    try:
        page.goto(lesson+'?view=learn');page.wait_for_load_state('networkidle')
        expect(page.get_by_text('On this lesson',exact=True)).to_be_visible()
        expect(page.locator('.ls-v24-checkpoint')).to_contain_text('Check your understanding')
        fits(page);shot(page,f'v24-reader-{width}.png')
        page.goto(lesson+'?view=practice&question=mean-score')
        page.locator('.ls-question input[type=radio][value="0"]').check()
        with page.expect_response(lambda r:r.url.endswith('/attempts') and r.request.method=='POST') as response:
            page.locator('.ls-question button[type=submit]').click()
        assert response.value.json()['correct'] is False
        expect(page.locator('.ls-feedback')).to_contain_text('Incorrect')
        page.wait_for_load_state('networkidle')
        page.goto(evidence)
        shot(page,f'v24-mistake-evidence-{width}.png')
        hint=page.get_by_role('button',name='Get a source-grounded hint')
        hint.focus();page.keyboard.press('Enter')
        expect(page.get_by_role('heading',name='Offline help',exact=True)).to_be_visible()
        expect(page.locator('#help-level')).to_have_text('Hint')
        expect(page.locator('main')).to_contain_text('No provider was called')
        assert page.get_by_role('link',name='Original page 2',exact=True).first.get_attribute('href').endswith('source.pdf#page=2')
        page.get_by_role('button',name='Concept',exact=True).click()
        expect(page.locator('#help-level')).to_have_text('Concept')
        page.get_by_role('button',name='Example',exact=True).click()
        expect(page.locator('.ae-block-example')).to_contain_text('Divide by 2 observations')
        fits(page);shot(page,f'v24-offline-help-{width}.png')
        page.get_by_role('button',name='Self Check',exact=True).click()
        expect(page.locator('#help-level')).to_have_text('Self Check')
        page.get_by_role('link',name='Try the exact self-check').click()
        page.locator('.ls-question input[type=radio][value="1"]').check()
        with page.expect_response(lambda r:r.url.endswith('/attempts') and r.request.method=='POST') as response:
            page.locator('.ls-question button[type=submit]').click()
        assert response.value.json()['correct'] is True
        page.wait_for_load_state('networkidle')
        page.goto(evidence)
        expect(page.locator('.ae-metrics')).to_contain_text('Unknown')
        page.get_by_role('button',name='Review PDF extraction draft').click()
        expect(page.get_by_role('heading',name='Review extracted draft',exact=True)).to_be_visible()
        expect(page.locator('#draft-page-2')).to_contain_text('Mean score')
        fits(page);shot(page,f'v24-draft-review-{width}.png')
        page.goto(evidence)
        page.get_by_role('button',name='Preview a manual practice task',exact=True).click()
        with closing(sqlite3.connect(owners[0])) as db:assert db.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==0
        page.get_by_role('button',name='Create my manual practice task').click()
        expect(page.locator('.planner-task-list')).to_contain_text('Manual practice: UC100N')
        page.goto(base+'/planning/day/2026-10-21')
        page.locator('input[name=start]').fill('18:00');page.locator('input[name=end]').fill('20:00')
        page.get_by_role('button',name='Preview available time').click()
        shot(page,f'v24-planning-preview-{width}.png')
        page.get_by_role('button',name='Save proposal as draft').click()
        page.get_by_role('button',name='Approve day',exact=True).click()
        page.locator('input[name=actual_minutes]').fill('35')
        page.get_by_role('button',name='Complete',exact=True).click()
        expect(page.locator('.planner-agenda-items')).to_contain_text('recorded 35 min')
        shot(page,f'v24-planning-complete-{width}.png')
        page.goto(evidence)
        expect(page.locator('.ae-record').filter(has_text='Planner Task')).to_contain_text('Recorded actual effort: 35 min')
        expect(page.locator('.ae-metrics')).to_contain_text('Unknown')
        shot(page,f'v24-topic-complete-{width}.png')
        page.goto(base+'/analysis')
        expect(page.locator('#effort-title')).to_be_visible()
        expect(page.locator('main')).to_contain_text('35 min')
        fits(page);shot(page,f'v24-analysis-{width}.png')
        page.goto(base+'/assessments');shot(page,f'v24-assessments-{width}.png')
        assert not errors and not external
        with closing(sqlite3.connect(owners[0])) as db:
            assert db.execute('SELECT status FROM planner_tasks').fetchall()==[('completed',)]
            assert db.execute('SELECT COUNT(*) FROM study_sessions').fetchone()[0]==0
            assert db.execute("SELECT earned_points_milli FROM assessments WHERE id='a1'").fetchone()[0] is None
        folder=os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
        if folder:
            (Path(folder)/f'v24-journey-{width}.json').write_text(json.dumps({'synthetic_only':True,'width':width,
                'question_id':'mean-score','source_sha256':owners[2]['source']['sha256'],
                'help_levels':['hint','concept','example','self_check'],'help_persisted':False,
                'practice':['incorrect','correct'],'mastery':'unknown','actual_minutes':35,
                'errors':errors,'external':external},indent=2),encoding='utf-8')
    finally:context.close()


def test_offline_ladder_and_draft_work_without_javascript(browser,live_v24):
    from tests.test_tutor_grounding_v24 import mistake
    base,owners=live_v24;mistake(owners)
    context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
    page=context.new_page()
    try:
        evidence=base+'/academic-evidence/learning/uc100n-demo/1'
        page.goto(evidence)
        button=page.get_by_role('button',name='Get a source-grounded hint')
        button.focus();page.keyboard.press('Enter')
        expect(page.locator('#help-level')).to_have_text('Hint')
        page.get_by_role('button',name='Example',exact=True).focus();page.keyboard.press('Enter')
        expect(page.locator('.ae-block-example')).to_contain_text('Divide by 2 observations')
        fits(page);shot(page,'v24-no-js-help-390.png')
        page.goto(evidence);page.get_by_role('button',name='Review PDF extraction draft').click()
        expect(page.locator('#draft-page-2')).to_contain_text('Mean score')
        shot(page,'v24-no-js-draft-390.png')
        with closing(sqlite3.connect(owners[0])) as db:assert db.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==0
    finally:context.close()


def test_text_size_focus_and_cross_owner_navigation(browser,live_v24):
    base,_=live_v24
    context=browser.new_context(viewport={'width':1366,'height':1000})
    page=context.new_page()
    try:
        page.goto(base+'/learning/modules/uc100n-demo/1?view=learn')
        page.wait_for_load_state('networkidle')
        prose=page.locator('.ls-block-definition p').last
        before=prose.evaluate('(p)=>parseFloat(getComputedStyle(p).fontSize)')
        page.locator('#ls-text-size').select_option('24')
        expect(prose).to_have_css('font-size','24px')
        assert prose.evaluate('(p)=>parseFloat(getComputedStyle(p).fontSize)')>before
        page.get_by_role('button',name='Focus Reading',exact=True).click()
        page.locator('.ls-v24-outline > summary').click()
        link=page.locator('.ls-v24-journey').get_by_role('link',name='03 Review evidence and choose a next step')
        href=link.get_attribute('href')
        assert 'focus=' not in href and 'nav=' not in href
        with page.expect_response(lambda r:'/academic-evidence/learning/' in r.url and r.request.is_navigation_request()) as response:
            link.click()
        assert response.value.status==200
        expect(page.locator('#signals-title')).to_be_visible()
    finally:context.close()


def test_cross_owner_navigation_waits_for_pending_reading_write(browser, live_v24):
    """A slow text-size save must finish before strict evidence snapshot capture."""
    base, _ = live_v24
    context = browser.new_context(viewport={'width': 1366, 'height': 1000})
    page = context.new_page()
    held = []
    try:
        page.goto(base+'/learning/modules/uc100n-demo/1?view=learn')
        page.wait_for_load_state('networkidle')
        page.route('**/progress', lambda route: held.append(route)
                   if route.request.method == 'POST' else route.continue_())
        page.locator('#ls-text-size').select_option('24')
        page.locator('.ls-v24-outline > summary').click()
        assert held
        link = page.locator('.ls-v24-journey').get_by_role('link', name='03 Review evidence and choose a next step')
        from playwright.sync_api import TimeoutError as BrowserTimeout
        with pytest.raises(BrowserTimeout):
            with page.expect_request(lambda r: r.is_navigation_request() and '/academic-evidence/' in r.url, timeout=300):
                link.click(no_wait_after=True)
        assert '/learning/modules/' in page.url
        with page.expect_response(lambda r: r.url.endswith('/progress') and r.request.method == 'POST'):
            held.pop().continue_()
        page.wait_for_url('**/academic-evidence/learning/uc100n-demo/1#signals-title')
        expect(page.locator('#signals-title')).to_be_visible()
    finally:
        for route in held: route.abort()
        context.close()


def test_overview_can_leave_learning_owner_without_a_bookmark_write(browser, live_v24):
    base,_=live_v24
    page=browser.new_page(viewport={'width':390,'height':844})
    try:
        page.goto(base+'/learning/modules/uc100n-demo/1')
        page.wait_for_load_state('networkidle')
        page.get_by_role('link',name='Learn workspace',exact=True).click(no_wait_after=True)
        page.wait_for_url(base+'/learning',timeout=3000)
    finally:page.close()
