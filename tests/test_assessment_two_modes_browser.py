"""Real browser, imported packages and production services; no personal records."""
import os
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from test_assessment_production_integration import _production
from test_assessment_studio_phase_b import _package, _raw
from personal_learning_assistant.services.assessment_package_service import AssessmentPackageService


@pytest.fixture(scope='module')
def mode_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def mode_live(tmp_path):
    app, path, paper, service, clock = _production(tmp_path, paper=True)
    package = _package(package_id='two-mode-cbt')
    package['assessment']['mode'] = 'practice'
    importer = AssessmentPackageService(path)
    batch = importer.stage_upload('cbt.json', _raw(package))
    cbt = importer.approve(batch['id'])
    app.config['ANDROID_LOCAL_RUNTIME'] = True
    server = make_server('127.0.0.1',0,app,threaded=True)
    thread = Thread(target=server.serve_forever,daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', {'cbt':cbt,'handwritten':paper}, service, clock, app
    server.shutdown();thread.join(timeout=5);server.server_close()


def capture(page,name):
    folder = os.environ.get('ANVAYA_ASSESSMENT_ARTIFACTS')
    if folder:
        path = Path(folder);path.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(path/(name+'.png')),full_page=False)


@pytest.mark.parametrize('width,height',[(320,740),(360,800),(390,844),(430,932),(768,1024),(1366,900),(844,390)])
@pytest.mark.parametrize('theme',['dark','light'])
@pytest.mark.parametrize('mode',['cbt','handwritten'])
def test_imported_modes_pause_restart_and_closed_book_review(mode_browser,mode_live,width,height,theme,mode):
    base, ids, service, clock, _ = mode_live
    with mode_browser.new_context(viewport={'width':width,'height':height}, reduced_motion='reduce') as ctx:
        ctx.add_init_script("localStorage.setItem('anvaya.mobile.theme', '"+theme+"')")
        page = ctx.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept())
        page.goto(base+'/assessments',wait_until='networkidle')
        expect(page.locator('.assessment-mode-card')).to_have_count(2)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        capture(page,f'home-{theme}-{width}')
        page.get_by_role('link',name='Open CBT Tests →' if mode=='cbt' else 'Open Handwritten Tests →',exact=True).click()
        expect(page).to_have_url(base+'/assessments/tests?assessment_mode='+mode)
        page.locator('a[href="/assessments/tests/'+ids[mode]+'?assessment_mode='+mode+'"]').first.click()
        assert page.locator('form[action$="/start"]').count()==1
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.locator('input[name=confirmed]').check()
        if mode=='handwritten':page.locator('input[name=self_review_acknowledged]').check()
        page.get_by_role('button',name='Start CBT Test' if mode=='cbt' else 'Start Handwritten Test',exact=True).click()
        expect(page.locator('#workspace')).to_have_attribute('data-status','active')
        sid = page.url.rsplit('/',1)[1]
        assert page.locator('html').get_attribute('data-native-runtime')=='true'
        expect(page.locator('html')).to_have_attribute('data-theme',theme)
        if mode=='cbt':
            page.locator('input[value="B"]').check()
            page.get_by_role('button',name='Save & Next',exact=True).click()
            expect(page.locator('.question-head')).to_contain_text('QUESTION 2')
            page.locator('[name="answer"]').fill('2')
        else:
            page.get_by_role('button',name='Attempted on paper',exact=True).click()
            expect(page.get_by_role('button',name='Undo attempted',exact=True)).to_be_visible()
            # The persisted-page label can paint before deferred handlers finish
            # their mobile palette layout. Interact with the completed reload.
            page.wait_for_load_state('load')
            assert page.get_by_role('button',name='Reveal solution and marking guide').count()==0
            if not page.locator('.palette-disclosure').evaluate('e=>e.open'):
                page.locator('.palette-disclosure summary').click()
            page.get_by_role('button',name='Question 2',exact=True).click()
            expect(page.locator('.question-head')).to_contain_text('QUESTION 2')
        page.evaluate('scrollTo(0,0)')
        # Compact palette and question fit within one portrait screen at 390 px.
        if width==390:
            assert page.locator('.question-text').bounding_box()['y'] < height
        capture(page,f'{mode}-solving-{theme}-{width}')
        pause = page.get_by_role('navigation',name='Question palette').get_by_role('button',name='Pause Test',exact=True)
        assert pause.bounding_box()['height'] >= 44
        pause.click()
        expect(page.locator('#workspace')).to_have_attribute('data-status','paused')
        frozen = service().state(sid)['remaining_ms']
        capture(page,f'{mode}-paused-{theme}-{width}')
        page.close();clock.advance(86400)
        page=ctx.new_page();page.on('dialog',lambda d:d.accept())
        page.goto(base+'/assessments',wait_until='networkidle')
        expect(page.get_by_role('heading',name='Continue Paused Tests')).to_be_visible()
        assert service().state(sid)['remaining_ms']==frozen
        page.get_by_role('button',name='Resume Test →',exact=True).click()
        expect(page.locator('#workspace')).to_have_attribute('data-status','active')
        assert service().state(sid)['current_ordinal']==2
        if mode=='cbt':
            expect(page.locator('[name="answer"]')).to_have_value('2')
            page.get_by_role('button',name='Clear Response',exact=True).click()
            expect(page.locator('[name="answer"]')).to_have_value('')
        else:
            page.get_by_role('button',name='Finish Solving',exact=True).click()
            expect(page.locator('#state-banner')).to_contain_text('Self-check workspace')
            page.get_by_role('button',name='Reveal solution and marking guide').first.click()
            expect(page.locator('.guide')).to_contain_text('Factorization followed')
            assert 'Synthetic fixture review only' not in page.locator('body').inner_text()
            page.locator('input[name=marks]').first.fill('1.5')
            page.get_by_role('button',name='Save Self-Check',exact=True).first.click()
            expect(page.locator('.mark-state').first).to_contain_text('1.5 marks')
            capture(page,f'handwritten-review-{theme}-{width}')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors


def test_extended_cbt_helper_uses_its_own_form_and_preserves_answers(mode_browser,mode_live):
    import sqlite3
    from types import SimpleNamespace
    base,ids,service,clock,app=mode_live
    with sqlite3.connect(service().repository.path) as db:db.execute("UPDATE courses SET code='UC100N'")
    calls=[]
    class Provider:
        def complete(self,request):
            calls.append(request)
            return SimpleNamespace(content='Use a Boolean mask. Try it yourself.')
    app.config['CODING_HELPER_PROVIDER_FACTORY']=Provider
    client=app.test_client()
    result=client.post('/assessments/tests/'+ids['cbt']+'/start',data={'confirmed':'1','assessment_mode':'cbt'})
    sid=result.location.rsplit('/',1)[1]
    with mode_browser.new_context(viewport={'width':390,'height':844}) as ctx:
        page=ctx.new_page();page.goto(base+'/assessments/extended/sessions/'+sid)
        page.locator('input[value="B"]').check()
        page.locator('.practice-tools summary').click()
        page.get_by_role('button',name='Coding Helper',exact=True).click()
        page.locator('#coding-helper-action').select_option('concept')
        page.locator('#coding-helper-form input[name=topic]').fill('Pandas')
        page.get_by_role('button',name='Get help',exact=True).click()
        expect(page.locator('#coding-helper-answer')).to_contain_text('Boolean mask')
        assert len(calls)==1
        assert service().state(sid)['revision']==1
        page.get_by_role('button',name='Close Coding Helper',exact=True).click()
        expect(page.locator('input[value="B"]')).to_be_checked()
        assert page.locator('#save-status').inner_text()==''
