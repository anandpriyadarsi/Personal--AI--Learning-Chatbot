"""Real native Chromium vertical slice; all state belongs to disposable owners."""
from contextlib import closing
import hashlib
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
from tests.test_academic_evidence_v23 import NOW, inventory, service
from tests.test_academic_evidence_v23_web import app

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Set ANVAYA_BROWSER_TESTS=1 for native Chromium.')

@pytest.fixture
def journey(uc_owners):
    application=app(uc_owners)
    server=make_server('127.0.0.1',0,application,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(server.server_port),uc_owners
    finally:
        server.shutdown();thread.join(timeout=5);server.server_close()

def shot(page,name):
    folder=os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
    if folder:
        out=Path(folder);out.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(out/name),full_page=True)

def fits(page):
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')

@pytest.mark.parametrize('width',[390,768,1366])
def test_source_practice_evidence_choice_availability_approval_completion(browser,journey,width):
    base,owners=journey;db,studio,lesson=owners
    context=browser.new_context(viewport={'width':width,'height':1000})
    page=context.new_page();errors=[];external=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def local(route):
        if route.request.url.startswith(base+'/'):route.continue_()
        else:external.append(route.request.url);route.abort()
    context.route('**/*',local)
    try:
        # Actual existing owner reader is the visual baseline, with identical
        # source/template to main. The V23 view is an additional scoped preview.
        page.goto(base+'/learning/modules/uc100n-demo/1?view=learn')
        expect(page.locator('#ls-reading-column')).to_contain_text('Cases, variables')
        shot(page,f'original-reader-{width}.png')
        page.goto(base+'/academic-evidence')
        page.locator('.ae-grid').get_by_role('link',name='Open lesson and evidence').click()
        evidence_url=page.url
        expect(page.locator('.ae-metrics')).to_contain_text('Unknown')
        expect(page.locator('.ls-relationship-graph')).to_contain_text('sum 14 then divide by 2')
        expect(page.locator('.ls-trusted-activity')).to_contain_text('Which column answers')
        expect(page.locator('#revision-title')).to_be_visible()
        image=page.locator('.ae-block-image img')
        expect(image).to_be_visible()
        assert image.evaluate('(img)=>img.complete && img.naturalWidth>0')
        assert page.get_by_role('link',name='Original page 2',exact=True).first.get_attribute('href').endswith('/source.pdf#page=2')
        fits(page)
        shot(page,f'v23-lesson-{width}.png')
        page.get_by_role('link',name='Practise the exact question').click()
        expect(page.locator('.ls-question')).to_have_attribute('data-question-id','mean-score')
        page.locator('.ls-question input[value="0"]').check()
        with page.expect_response(lambda response:response.url.endswith('/attempts') and response.request.method=='POST') as attempt:
            page.locator('.ls-question button[type=submit]').click()
        assert attempt.value.status==200 and attempt.value.json()['correct'] is False
        expect(page.locator('.ls-feedback')).to_contain_text('Incorrect')
        page.goto(evidence_url)
        record=page.locator('.ae-record').filter(has_text='Learning Practice')
        expect(record).to_contain_text('study signal')
        expect(record).to_contain_text('incorrect')
        record.get_by_text('Exact evidence identity',exact=True).click()
        expect(record).to_contain_text('mean-score')
        expect(record).to_contain_text('Assistance: unknown')
        with closing(sqlite3.connect(db)) as c:before=list(c.iterdump())
        preview=page.get_by_role('button',name='Preview a manual practice task',exact=True)
        preview.focus();page.keyboard.press('Enter')
        expect(page.get_by_role('button',name='Create my manual practice task')).to_be_visible()
        with closing(sqlite3.connect(db)) as c:assert list(c.iterdump())==before
        assert page.get_by_role('button',name='Complete',exact=True).count()==0
        page.get_by_role('button',name='Create my manual practice task').click()
        expect(page.locator('.planner-task-list')).to_contain_text('Manual practice: UC100N')
        with closing(sqlite3.connect(db)) as c:
            assert c.execute('SELECT course_id,topic_id,status FROM planner_tasks').fetchall()==[('v23-uc100n','v23-data','backlog')]
        page.goto(base+'/planning/day/2026-10-21')
        page.locator('input[name=start]').fill('18:00')
        page.locator('input[name=end]').fill('20:00')
        page.get_by_role('button',name='Preview available time').click()
        assert page.get_by_role('button',name='Complete',exact=True).count()==0
        page.get_by_role('button',name='Save proposal as draft').click()
        expect(page.locator('main')).to_contain_text('18:00–20:00 · UTC')
        page.get_by_role('button',name='Approve day',exact=True).click()
        page.locator('input[name=actual_minutes]').fill('35')
        page.get_by_role('button',name='Complete',exact=True).click()
        expect(page.locator('.planner-agenda-items')).to_contain_text('recorded 35 min')
        with closing(sqlite3.connect(db)) as c:
            assert c.execute('SELECT status FROM planner_tasks').fetchall()==[('completed',)]
            assert c.execute('SELECT COUNT(*) FROM study_sessions').fetchone()[0]==0
            assert c.execute("SELECT earned_points_milli FROM assessments WHERE id='a1'").fetchone()[0] is None
        page.goto(evidence_url)
        expect(page.locator('.ae-record').filter(has_text='Planner Task')).to_contain_text('completion signal')
        expect(page.locator('.ae-record').filter(has_text='Planner Task')).to_contain_text('Recorded actual effort: 35 min')
        expect(page.locator('.ae-metrics')).to_contain_text('Unknown')
        fits(page);assert not errors and not external
        shot(page,f'v23-completed-evidence-{width}.png')
        folder=os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
        if folder:
            (Path(folder)/f'v23-journey-{width}.json').write_text(json.dumps({
                'synthetic_only':True,'width':width,'module_id':'uc100n-demo','revision':1,
                'source_sha256':lesson['source']['sha256'],'question_id':'mean-score','question_revision':1,
                'practice':'incorrect','manual_choice':True,'availability':['18:00','20:00'],
                'approved':True,'completed':True,'actual_minutes':35,'mastery':'unknown',
                'automatic_eligible':False,'external_requests':external,'browser_errors':errors},indent=2),encoding='utf-8')
    finally:context.close()

def test_no_javascript_keyboard_read_preview_and_explicit_consent(browser,journey):
    base,owners=journey
    context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
    page=context.new_page()
    try:
        page.goto(base+'/academic-evidence/learning/uc100n-demo/1')
        expect(page.locator('.ls-relationship-graph')).to_contain_text('measure the score variable')
        expect(page.locator('.ls-trusted-activity')).to_contain_text('Explain why selecting')
        page.get_by_role('button',name='Preview a manual practice task',exact=True).focus()
        page.keyboard.press('Enter')
        button=page.get_by_role('button',name='Create my manual practice task')
        expect(button).to_be_visible()
        with closing(sqlite3.connect(owners[0])) as c:assert c.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==0
        button.focus();page.keyboard.press('Enter')
        expect(page.locator('.planner-task-list')).to_contain_text('Manual practice: UC100N')
        assert page.locator('form[action$="/approve"]').count()==0
        shot(page,'v23-no-javascript-mobile.png')
    finally:context.close()
