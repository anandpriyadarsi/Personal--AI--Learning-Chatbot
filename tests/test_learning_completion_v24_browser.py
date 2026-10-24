"""Actual no-JS practice, approved metadata and separate reviewed publication."""
from contextlib import closing,contextmanager
from threading import Thread
from copy import deepcopy
import os
import sqlite3
import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server
from tests.learning_studio.test_browser import browser
from tests.academic_evidence_v23_fixtures import uc_owners
from tests.test_academic_evidence_v23_web import app
from tests.test_academic_evidence_v23 import NOW
from tests.test_academic_evidence_v23_browser import fits,shot

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Set ANVAYA_BROWSER_TESTS=1 for native Chromium.')

@pytest.fixture
def completion_live(uc_owners):
    from personal_learning_assistant.services.knowledge_reader_service import KnowledgeReaderService
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    @contextmanager
    def owner():
        with closing(sqlite3.connect(uc_owners[0],isolation_level=None)) as con:
            yield TutorSessionService(SQLiteTutorRepository(con),now=lambda:NOW.isoformat())
    with closing(sqlite3.connect(uc_owners[0])) as con,con:
        con.execute('INSERT INTO knowledge_documents(id,kind,path_key,mime_type,content_hash,extraction_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
            ('synthetic-uc100n-source','pdf','synthetic/source.pdf','application/pdf',uc_owners[2]['source']['sha256'],'completed',NOW.isoformat(),NOW.isoformat()))
    application=app(uc_owners,ACADEMIC_DATABASE_PATH=uc_owners[0],LEARNING_LIBRARY_DATABASE_PATH=uc_owners[0],
        LEARNING_TUTOR_V24_OWNER_FACTORY=owner,
        KNOWLEDGE_READER_SERVICE_FACTORY=lambda:KnowledgeReaderService(database_path=uc_owners[0]))
    server=make_server('127.0.0.1',0,application,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(server.server_port),uc_owners
    finally:server.shutdown();thread.join(timeout=5);server.server_close()

@pytest.mark.parametrize('width',[390,768,1366])
def test_native_practice_metadata_review_stage_publish_and_discovery(browser,completion_live,width):
    base,owners=completion_live;studio=owners[1]
    context=browser.new_context(java_script_enabled=False,viewport={'width':width,'height':1000})
    page=context.new_page();external=[]
    def local(route):
        if route.request.url.startswith(base+'/'):route.continue_()
        else:external.append(route.request.url);route.abort()
    context.route('**/*',local)
    lesson=base+'/learning/modules/uc100n-demo/1';evidence=base+'/academic-evidence/learning/uc100n-demo/1'
    original=studio.source('uc100n-demo',1)
    try:
        page.goto(lesson+'?view=practice&question=mean-score')
        expect(page.locator('#ls-pause')).not_to_be_visible()
        expect(page.locator('.ls-reading-controls')).not_to_be_visible()
        page.locator('.ls-question input[type=radio][value="0"]').check()
        page.locator('.ls-question button[type=submit]').focus();page.keyboard.press('Enter')
        expect(page.locator('.ls-feedback')).to_contain_text('Incorrect')
        page.wait_for_load_state('load')
        fits(page);shot(page,f'v24-native-practice-{width}.png')
        page.goto(evidence);page.get_by_role('button',name='Get a source-grounded hint').click()
        page.get_by_role('link',name='Review saving this help session').click()
        expect(page.get_by_role('heading',name='Review this help before saving')).to_be_visible()
        with closing(sqlite3.connect(owners[0])) as con:assert con.execute('SELECT COUNT(*) FROM tutor_sessions').fetchone()[0]==0
        page.locator('input[name=confirm_save]').check();page.get_by_role('button',name='Save approved metadata').click()
        expect(page.locator('#tutor-session-history')).to_contain_text('Hint help view')
        fits(page);shot(page,f'v24-consented-tutor-{width}.png')
        with closing(sqlite3.connect(owners[0])) as con:
            assert con.execute('SELECT COUNT(*) FROM tutor_sessions').fetchone()[0]==1
            assert con.execute('SELECT COUNT(*) FROM tutor_turns').fetchone()[0]==0
        page.goto(lesson+'?view=practice&question=mean-score')
        page.locator('.ls-question input[type=radio][value="1"]').check();page.locator('.ls-question button[type=submit]').click()
        expect(page.locator('.ls-feedback')).to_contain_text('Correct')
        page.goto(evidence);page.get_by_role('link',name='Edit and review notes for a staged revision').click()
        page.get_by_role('button',name='Extract a temporary review draft').click()
        for n in (1,2,3):
            page.locator('#review-note-'+str(n)).fill('Human reviewed note for original page '+str(n)+'.')
            page.locator('input[name=reviewed_pages][value="'+str(n)+'"]').check()
        page.locator('input[name=approve]').check();fits(page);shot(page,f'v24-conversion-edit-{width}.png')
        page.get_by_role('button',name='Stage reviewed notes for separate publication review').click()
        expect(page.get_by_role('heading',name='Staged preview',exact=True)).to_be_visible()
        with studio.store.connection() as con:assert con.execute('SELECT revision FROM active_modules').fetchone()[0]==1
        page.get_by_role('button',name='Publish this revision',exact=True).click()
        assert studio.source('uc100n-demo',1)==studio.source('uc100n-demo',2)==original
        assert studio.module('uc100n-demo',1)['questions']==studio.module('uc100n-demo',2)['questions']
        page.goto(base+'/knowledge/item/synthetic-uc100n-source');page.get_by_role('link',name='Find source-linked lessons').click()
        expect(page.get_by_role('link',name='Open lesson',exact=True)).to_have_attribute('href','/learning/modules/uc100n-demo/2?view=learn')
        fits(page);shot(page,f'v24-source-discovery-{width}.png')
        page.get_by_role('link',name='Review evidence',exact=True).click();expect(page.locator('.ae-metrics')).to_contain_text('Unknown')
        assert not external
    finally:context.close()


def test_long_math_reader_and_help_keyboard_containment(browser,completion_live):
    base,owners=completion_live;studio=owners[1];p=deepcopy(owners[2]);p['module_revision']=2
    p['sections'][0]['blocks'].append({'kind':'definition','text':'Long authored expression: \\('+'+'.join(['x']*80)+'\\).','pages':[2]})
    studio.stage(p,{'assets/cases.png':studio.asset('uc100n-demo',1,'assets/cases.png')});studio.publish('uc100n-demo',2)
    studio.attempt('uc100n-demo',{'event_id':'long-math-mistake','module_revision':2,'source_sha256':p['source']['sha256'],'question_id':'mean-score','question_revision':1,'selection':0})
    context=browser.new_context(viewport={'width':390,'height':1000});page=context.new_page()
    try:
        page.goto(base+'/learning/modules/uc100n-demo/2?view=learn')
        math=page.locator('math').first;expect(math).to_have_attribute('tabindex','0');math.focus();expect(math).to_be_focused();fits(page);shot(page,'v24-long-math-reader-390.png')
        page.goto(base+'/academic-evidence/learning/uc100n-demo/2');page.get_by_role('button',name='Get a source-grounded hint').click();page.get_by_role('button',name='Concept',exact=True).click()
        math=page.locator('math').first;math.focus();expect(math).to_be_focused();fits(page);shot(page,'v24-long-math-help-390.png')
    finally:context.close()
