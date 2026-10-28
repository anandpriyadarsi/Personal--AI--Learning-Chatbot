"""Genuine Chromium mobile viewports, not Android hardware certification."""
import json
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.test_ui_v2_protected_browser import protected_live, protected_browser
from tests.test_learning_library_read_model import library_db

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1',
    reason='Set ANVAYA_BROWSER_TESTS=1 for real Chromium mobile acceptance')


@pytest.fixture
def mobile_live(protected_live, library_db):
    from personal_learning_assistant.services.learning_library_service import LearningLibraryService
    from personal_learning_assistant.services.knowledge_reader_service import KnowledgeReaderService
    a = protected_live['app']
    a.config.update(PRIVATE_MOBILE_MODE=True, TRUSTED_HOSTS=['127.0.0.1'],
        LEARNING_LIBRARY_SERVICE_FACTORY=lambda: LearningLibraryService(database_path=library_db),
        KNOWLEDGE_READER_SERVICE_FACTORY=lambda: KnowledgeReaderService(database_path=library_db))
    return protected_live


def capture(page, name):
    folder = os.environ.get('ANVAYA_MOBILE_ARTIFACTS')
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / (name + '.png')), full_page=True)
        page.screenshot(path=str(Path(folder) / (name + '-viewport.png')), full_page=False)


@pytest.mark.parametrize('width,height', [(320,700),(360,800),(390,844),(412,915),(430,932),(844,390),(768,1024),(1366,900)])
def test_actual_academic_surfaces_and_touch_navigation(protected_browser, mobile_live, width, height):
    live = mobile_live
    with protected_browser.new_context(viewport={'width':width,'height':height}, has_touch=True,
                                       reduced_motion='reduce') as ctx:
        page = ctx.new_page(); errors=[]; outbound=[]
        page.on('pageerror', lambda e: errors.append(str(e)))
        ctx.route('**/*', lambda r: r.continue_() if r.request.url.startswith(live['base']+'/')
                  else (outbound.append(r.request.url), r.abort())[-1])
        paths={'today':'/',**live['routes'],'library':'/library',
               'library-detail':'/library/resources/r1','notes':'/notes','settings':'/mobile/settings'}
        for surface,path in paths.items():
            r=page.goto(live['base']+path,wait_until='networkidle')
            assert r.status==200,(surface,r.status)
            assert r.headers['cache-control']=='no-store'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(surface,width)
            assert page.locator('main').is_visible()
            if surface=='learning-reader':
                expect(page.locator('#ls-reading-column')).to_contain_text('Learn this concept')
                assert page.locator('.ls-source-chips a').count()>0
            if surface=='assessment-runner':
                assert page.get_by_role('button',name='Save & Next',exact=True).is_visible()
                assert page.locator('.mobile-dock').count()==0
            if width==390 or (width==1366 and surface=='today'):
                capture(page,f'mobile-{surface}-{width}')
        if width<=860:
            dock=page.get_by_role('navigation',name='Mobile study navigation')
            dock.get_by_role('link',name='Learn workspace',exact=True).tap()
            expect(page).to_have_url(live['base']+'/learning')
            expect(dock.get_by_role('link',name='Learn workspace',exact=True)).to_have_attribute('aria-current','page')
            dock.get_by_role('link',name='Tutor workspace',exact=True).tap()
            expect(page).to_have_url(live['base']+'/agent')
        assert not errors and not outbound,(errors,outbound)


def test_themes_installability_and_no_sensitive_cache(protected_browser,mobile_live):
    base=mobile_live['base']
    with protected_browser.new_context(viewport={'width':390,'height':844}) as ctx:
        page=ctx.new_page();page.goto(base+'/mobile/settings',wait_until='networkidle')
        page.locator('#mobile-theme').select_option('light')
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        capture(page,'mobile-settings-light-390')
        page.reload();expect(page.locator('#mobile-theme')).to_have_value('light')
        for key in ['learning','assessment-runner','tutor','analysis']:
            page.goto(base+mobile_live['routes'][key],wait_until='networkidle')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            capture(page,f'mobile-{key}-light-390')
        page.goto(base+'/mobile/settings',wait_until='networkidle')
        page.evaluate('navigator.serviceWorker.ready.then(() => true)')
        page.reload();assert page.evaluate('navigator.serviceWorker.controller !== null')
        page.goto(base+'/library',wait_until='networkidle')
        keys=page.evaluate('caches.keys().then(async names => (await Promise.all(names.map(async n => (await (await caches.open(n)).keys()).map(r=>new URL(r.url).pathname)))).flat())')
        assert set(keys)=={'/mobile/offline','/static/css/mobile_v1.css','/static/js/mobile_v1.js',
                          '/static/brand/anvaya-mobile-192.png','/static/brand/anvaya-mobile-512.png'}
        cdp=ctx.new_cdp_session(page)
        cdp.send('Page.enable')
        manifest=cdp.send('Page.getAppManifest')
        assert manifest['url'].endswith('/manifest.webmanifest')
        assert not manifest['errors'],manifest
        install=cdp.send('Page.getInstallabilityErrors')
        assert not install['installabilityErrors'],install
        folder=os.environ.get('ANVAYA_MOBILE_ARTIFACTS')
        if folder:
            (Path(folder)/'installability-cache.json').write_text(json.dumps({'chromium_installability':install,
                'cached_paths':keys,'real_android_device':False},indent=2))


def test_offline_fallback_failed_post_and_reconnection(protected_browser,mobile_live):
    # Stop the actual HTTP host. Chromium 134's worker-target fetches are not
    # reliably affected by Playwright context.set_offline on loopback.
    from threading import Thread
    from werkzeug.serving import make_server
    server=make_server('127.0.0.1',0,mobile_live['app'],threaded=True)
    port=server.server_port
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{port}'
    try:
        with protected_browser.new_context(viewport={'width':390,'height':844}) as ctx:
            page=ctx.new_page();page.goto(base+'/mobile/settings')
            page.evaluate('navigator.serviceWorker.ready.then(() => true)')
            page.reload();assert page.evaluate('navigator.serviceWorker.controller !== null')
            server.shutdown();thread.join(timeout=5);server.server_close()
            page.goto(base+'/library')
            expect(page.get_by_role('heading',name='Your workspace needs its host.')).to_be_visible()
            assert 'Lecture collection' not in page.locator('main').inner_text()
            capture(page,'mobile-offline-390')
            result=page.evaluate("fetch('/agent/sessions',{method:'POST',body:'title=offline'}).then(r=>({failed:!r.ok})).catch(()=>({failed:true}))")
            assert result['failed'] is True
            server=make_server('127.0.0.1',port,mobile_live['app'],threaded=True)
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            page.get_by_role('link',name='Try your workspace again').click()
            expect(page.locator('.ws-home-grid')).to_be_visible()
            assert mobile_live['tutor'].created==[]
            page.wait_for_load_state('networkidle')
            expect(page.locator('#mobile-connection')).to_be_hidden()
    finally:
        if thread.is_alive():server.shutdown();thread.join(timeout=5)
        server.server_close()


def test_library_search_and_source_identity(protected_browser,mobile_live):
    base=mobile_live['base']
    page=protected_browser.new_page(viewport={'width':360,'height':800})
    try:
        page.goto(base+'/library');page.locator('main input[name="q"]').fill('LECTURE')
        page.locator('main input[name="q"]').press('Enter')
        expect(page.locator('article.library-card')).to_have_count(1)
        page.get_by_role('link',name='View resource').click()
        expect(page.locator('main')).to_contain_text('Lecture collection')
        page.get_by_role('link',name='View source').first.click()
        assert '/knowledge/item/d1' in page.url
    finally:page.close()


def test_update_waits_without_reloading_active_page(protected_browser,mobile_live):
    from flask import Response
    a=mobile_live['app'];version={'value':'1'}
    def versioned_worker():
        import re
        source=(Path(a.static_folder)/'js/mobile-sw.js').read_text()
        source=re.sub(r"const CACHE = '[^']+';",
            "const CACHE = 'anvaya-mobile-update-test-"+version['value']+"';",source)
        return Response(source,
                        mimetype='application/javascript',headers={'Cache-Control':'no-store','Service-Worker-Allowed':'/'})
    a.view_functions['mobile.worker']=versioned_worker
    with protected_browser.new_context(viewport={'width':390,'height':844}) as ctx:
        page=ctx.new_page();page.goto(mobile_live['base']+'/mobile/settings')
        page.evaluate('navigator.serviceWorker.ready.then(()=>true)');page.reload()
        assert page.evaluate('navigator.serviceWorker.controller !== null')
        page.evaluate('window.mobileUpdateSentinel = "unsaved work remains"')
        version['value']='2'
        page.evaluate('navigator.serviceWorker.getRegistration().then(r=>{window.mobileRegistration=r;return r.update()})')
        page.evaluate("""async () => {
            const r = window.mobileRegistration;
            if (r.waiting) return;
            const worker = r.installing;
            if (!worker) throw new Error('Update was not discovered');
            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('Update did not wait')), 10000);
                worker.addEventListener('statechange', () => {
                    if (worker.state === 'installed') { clearTimeout(timeout); resolve(); }
                    if (worker.state === 'redundant') { clearTimeout(timeout); reject(new Error('Update failed')); }
                });
            });
        }""")
        assert page.evaluate('window.mobileUpdateSentinel')=='unsaved work remains'
        assert page.evaluate('navigator.serviceWorker.getRegistration().then(r => r.active.state === "activated" && r.waiting.state === "installed" && r.active !== r.waiting)')
        expect(page.locator('#mobile-update-status')).to_contain_text('Update ready')


def test_real_tutor_repository_conversation_resume(protected_browser,mobile_live):
    from tests.test_phase7_5_academic_agent_web import build_test_web_service,FakeProvider,first_retrieval_hit,open_database
    import sqlite3
    root=mobile_live['root']/'mobile-tutor';root.mkdir()
    service,path,course,provider,retrieval=build_test_web_service(root,provider=FakeProvider(configured=True))
    db=open_database(path)
    try:retrieval.hits=(first_retrieval_hit(db),)
    finally:db.close()
    mobile_live['app'].config['ACADEMIC_AGENT_WEB_SERVICE_FACTORY']=lambda:service
    with protected_browser.new_context(viewport={'width':390,'height':844}) as ctx:
        page=ctx.new_page();page.goto(mobile_live['base']+'/agent')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/agent/sessions')) as response:
            page.get_by_role('button',name='Create tutor session',exact=True).click()
        assert response.value.status==303,response.value.request.all_headers()
        page.wait_for_url('**/agent/sessions/*')
        session_url=page.url
        page.locator('#agent-question').fill('Explain the retrieved source simply.')
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.agent-turn-assistant')).to_contain_text('retrieved source supports')
        assert provider.calls==1  # Explicitly deterministic provider, never a cloud model.
        page.reload()
        expect(page.locator('.agent-turn-user')).to_contain_text('Explain the retrieved source simply.')
        expect(page.locator('.agent-turn-assistant')).to_contain_text('[S1]')
        sid=session_url.rsplit('/',1)[-1]
        with sqlite3.connect(path) as con:
            assert con.execute('SELECT count(*) FROM tutor_turns WHERE session_id=?',(sid,)).fetchone()[0]==2
        page.close();page=ctx.new_page();page.goto(session_url)
        expect(page.locator('.agent-turn-assistant')).to_contain_text('retrieved source supports')
        assert provider.calls==1
        assert page.locator('#transcript-title').bounding_box()['y']<550, 'Tutor conversation is pushed below mobile metadata'
        capture(page,'mobile-tutor-persisted-390')


def test_light_learning_text_remains_readable(protected_browser,mobile_live):
    with protected_browser.new_context(viewport={'width':390,'height':844}) as ctx:
        page=ctx.new_page();page.goto(mobile_live['base']+'/mobile/settings')
        page.locator('#mobile-theme').select_option('light')
        page.goto(mobile_live['base']+'/learning',wait_until='networkidle')
        for selector in ['.ls-subject-card h4','.ls-subject-summary','.ls-subject-footer strong','.ls-workspace-hero h1']:
            channels=page.locator(selector).first.evaluate('e=>getComputedStyle(e).color.match(/[0-9.]+/g).slice(0,3).map(Number)')
            assert max(channels)<130,(selector,channels)
        bg=page.locator('.ls-workspace-hero').evaluate('e=>getComputedStyle(e).backgroundColor.match(/[0-9.]+/g).slice(0,3).map(Number)')
        assert min(bg)>200,bg
        capture(page,'mobile-learning-light-fixed-390')
        page.goto(mobile_live['base']+mobile_live['routes']['learning-reader'],wait_until='networkidle')
        for selector in ['.ls-lesson>h2','.ls-block strong','.ls-v24-checkpoint p']:
            channels=page.locator(selector).first.evaluate('e=>getComputedStyle(e).color.match(/[0-9.]+/g).slice(0,3).map(Number)')
            assert max(channels)<130,(selector,channels)
        capture(page,'mobile-reader-light-fixed-390')


def test_composer_focus_and_short_viewport_preserve_input(protected_browser,mobile_live):
    with protected_browser.new_context(viewport={'width':390,'height':844}) as ctx:
        page=ctx.new_page();page.goto(mobile_live['base']+'/agent/sessions/session-1')
        composer=page.locator('#agent-question')
        composer.fill('A synthetic question awaiting my explicit submission.')
        expect(page.locator('.mobile-dock')).to_be_hidden()
        page.set_viewport_size({'width':390,'height':420})
        expect(composer).to_have_value('A synthetic question awaiting my explicit submission.')
        composer.scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert mobile_live['tutor'].llm_calls==0
        # This simulates reduced space; it is not an Android keyboard certificate.


@pytest.mark.parametrize('width',[320,390,430,844])
@pytest.mark.parametrize('kind',['online','paper'])
def test_production_assessment_pause_resume_and_paper_review(protected_browser,mobile_live,width,kind):
    from scripts.assessment_execution_fixture import create_fixture
    from tests.test_assessment_studio_phase_c import Clock
    from personal_learning_assistant.ui.web.assessment_execution_candidate import create_production_blueprint
    clock=Clock();service,ids,key=create_fixture(mobile_live['root']/'mobile-extended',now_fn=clock)
    a=mobile_live['app'];a.config['ASSESSMENT_EXTENDED_ENABLED']=True
    a.config['ASSESSMENT_EXTENDED_SERVICE_FACTORY']=lambda:service
    a.register_blueprint(create_production_blueprint(lambda:service,secret_key=key))
    with protected_browser.new_context(viewport={'width':width,'height':844}) as ctx:
        page=ctx.new_page();page.on('dialog',lambda d:d.accept())
        url=mobile_live['base']+'/assessments/extended/sessions/'+ids[kind]
        page.goto(url,wait_until='networkidle')
        assert page.locator('link[rel=manifest]').count()==1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if kind=='online':page.locator('input[value="B"]').check()
        page.get_by_role('button',name='Pause Test',exact=True).click()
        expect(page.locator('#state-banner')).to_contain_text('Test Paused')
        assert service.state(ids[kind])['status']=='paused'
        clock.advance(36000);page.reload()
        expect(page.locator('#timer')).to_contain_text('30:00')
        page.get_by_role('button',name='Resume Test',exact=True).click()
        expect(page.locator('#state-banner')).to_contain_text('Solving in progress')
        if kind=='online':expect(page.locator('input[value="B"]')).to_be_checked()
        else:
            page.get_by_role('button',name='Finish Solving',exact=True).click()
            expect(page.locator('#state-banner')).to_contain_text('Self-check workspace')
            page.get_by_role('button',name='Reveal solution and marking guide').first.click()
            expect(page.locator('.guide')).to_contain_text('Solve Ly = b')
            for select in page.locator('select[name^="step_"]').all():select.select_option('1.0')
            page.get_by_role('button',name='Save Self-Check').first.click()
            expect(page.locator('.mark-state').first).to_contain_text('3.0 marks')
        if width==390:capture(page,f'mobile-production-assessment-{kind}-390')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_private_note_editor_formatting_templates_media_and_save(protected_browser,mobile_live):
    from io import BytesIO
    from PIL import Image
    with protected_browser.new_context(viewport={'width':390,'height':844}) as ctx:
        page=ctx.new_page();page.goto(mobile_live['base']+'/notes/create/typed',wait_until='networkidle')
        tab=page.locator('[data-card-family-tab="square"]');tab.click()
        expect(tab).to_have_attribute('aria-selected','true')
        body=page.locator('#anvaya-note-body');body.fill('Synthetic explanation')
        body.evaluate('(e)=>e.setSelectionRange(0,e.value.length)')
        page.get_by_role('button',name='Bold',exact=True).click()
        expect(body).to_have_value('**Synthetic explanation**')
        image=BytesIO();Image.new('RGB',(8,8),'#55c2b8').save(image,format='PNG')
        page.locator('#anvaya-note-files').set_input_files({'name':'synthetic.png','mimeType':'image/png','buffer':image.getvalue()})
        preview=page.locator('#anvaya-selected-media img')
        expect(preview).to_be_visible()
        assert preview.evaluate('(e)=>e.complete && e.naturalWidth>0')
        page.get_by_role('button',name='Insert at cursor',exact=True).click()
        assert 'anvaya-upload:0' in body.input_value()
        page.locator('input[name=title]').fill('Synthetic mobile note')
        page.get_by_role('button',name='Create note',exact=True).click()
        expect(page.locator('main')).to_contain_text('Synthetic mobile note')
        page.reload()
        section=page.locator('#mini-original-content')
        expect(section).to_have_attribute('open','')
        expect(section).to_contain_text('Synthetic explanation')
        expect(section.locator('img')).to_have_count(1)
        expect(section.locator('img')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        evidence=Path(__file__).resolve().parents[1]/'docs/mobile/smart-notes/screenshots';evidence.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(evidence/'keep-editor-saved-390.png'))


def test_health_check_supports_webviews_without_abortsignal_timeout(protected_browser, mobile_live):
    with protected_browser.new_context(viewport={'width':390,'height':844}) as context:
        page=context.new_page()
        page.add_init_script("Object.defineProperty(AbortSignal,'timeout',{value:undefined,configurable:true})")
        page.goto(mobile_live['base']+'/mobile/settings',wait_until='networkidle')
        expect(page.locator('#mobile-connection')).to_be_hidden()
