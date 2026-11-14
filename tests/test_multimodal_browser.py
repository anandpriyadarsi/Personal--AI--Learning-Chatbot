"""Real local Flask/SQLite/Chromium journeys; synthetic providers only."""
from io import BytesIO
from pathlib import Path
from threading import Thread
import os
import pytest
from werkzeug.serving import make_server
from test_multimodal_jobs import owners,image_bytes
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService
from personal_learning_assistant.domain.tutor_models import TutorProviderResponse

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Explicit real-browser gate')


@pytest.fixture
def live(owners):
    lib,db=owners
    class Provider:
        local_only=True;configured=True
        def complete(self,request):return TutorProviderResponse('The supplied transcription says two rows and two columns [S1].','offline-fake','test')
    web=AcademicAgentWebService(database_path=db,index_root=db.parent/'tutor_retrieval',provider_factory=Provider,course_catalogue_loader=lambda:{'courses':[]})
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'ACADEMIC_AGENT_WEB_SERVICE_FACTORY':lambda:web,
                    'NATIVE_LIBRARY_CATALOGUE_FACTORY':lambda:{'available':True,'courses':[]}})
    lib.start_worker();doc=lib.upload(BytesIO(image_bytes()),'Matrix.png')
    server=make_server('127.0.0.1',0,app,threaded=True);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',doc,lib
    finally:server.shutdown();thread.join(5);server.server_close()


@pytest.mark.parametrize('width,height',[(320,568),(360,844),(390,844),(768,1024),(1366,768),(390,440)])
def test_image_review_to_existing_tutor_exact_citation_and_stale_source(live,width,height,tmp_path):
    from playwright.sync_api import sync_playwright,expect
    base,doc,lib=live
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH') or None,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':width,'height':height});page.set_default_timeout(5000);errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/library/files/'+doc['id']+'/open')
        page.get_by_text('Ask about this page/image',exact=True).click()
        page.locator('#mm-method').select_option('review');page.locator('#mm-review-complete').check();page.locator('#mm-text').fill('The matrix has two rows and two columns.')
        page.get_by_role('button',name='Review selected scope',exact=True).click()
        expect(page.locator('#mm-review')).to_contain_text('no cloud transmission')
        page.get_by_role('button',name='Approve reviewed processing',exact=True).click()
        expect(page.locator('#mm-ask')).to_be_visible(timeout=20000)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.locator('#mm-ask').click();page.wait_for_url('**/agent/sessions/*')
        page.locator('#agent-question').fill('What does this show?');page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.agent-turn-assistant')).to_contain_text('two rows',timeout=15000)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        main=page.locator('#main-content').bounding_box();dock=page.locator('#tutor-composer').bounding_box()
        assert main['y']+main['height']<=dock['y']+2
        out=Path(os.getenv('ANVAYA_WEB_ARTIFACTS',str(tmp_path)));out.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(out/f'multimodal-{width}-{height}.png'))
        page.get_by_text('Sources & answer details',exact=True).click()
        citation=page.locator('a[href^="/sources/evidence/"]').first
        citation.click();expect(page.get_by_text('Exact retained source',exact=False)).to_be_visible()
        assert page.locator('img[alt="Exact retained original image"]').evaluate('el=>el.naturalWidth')>0
        lib.update(doc['id'],display_name='Renamed source')
        response=page.reload();assert response.status==410
        expect(page.get_by_role('heading',name='Historical evidence unavailable')).to_be_visible()
        assert not errors
        browser.close()


@pytest.mark.parametrize('width',[390,1366])
def test_crop_scope_edits_invalidate_consent_and_survive_reload(live,width):
    from playwright.sync_api import sync_playwright,expect
    base,doc,lib=live
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH') or None)
        page=browser.new_page(viewport={'width':width,'height':844})
        page.goto(base+'/library/files/'+doc['id']+'/open')
        page.get_by_text('Ask about this page/image',exact=True).click()
        page.locator('#mm-method').select_option('review');page.locator('#mm-review-complete').check();page.locator('#mm-text').fill('Selected crop has two rows.')
        page.locator('#mm-crop-enabled').check();page.get_by_label('Right (%)').fill('60')
        page.locator('#mm-preview').click();expect(page.locator('#mm-approve')).to_be_visible()
        page.get_by_label('Left (%)').fill('10');expect(page.locator('#mm-approve')).to_be_hidden()
        page.locator('#mm-preview').click();page.locator('#mm-approve').click()
        expect(page.locator('#mm-ask')).to_be_visible(timeout=20000)
        page.reload();page.get_by_text('Ask about this page/image',exact=True).click()
        expect(page.get_by_label('Left (%)')).to_have_value('10')
        expect(page.get_by_label('Right (%)')).to_have_value('60')
        expect(page.locator('.mm-crop-overlay')).to_be_visible()
        page.locator('#mm-ask').click();page.wait_for_url('**/agent/sessions/*')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        browser.close()


def test_multiple_named_frames_and_late_start_lecture_navigation(live):
    from playwright.sync_api import sync_playwright,expect
    base,doc,lib=live
    transcript=lib.upload(BytesIO(b'WEBVTT\n\n00:12.500 --> 00:18.000\nSwap the rows.'),'Late lecture.vtt')
    frames=[lib.upload(BytesIO(image_bytes()),f'Board {i}.png',duplicate='copy',indexing=False) for i in range(3)]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH') or None)
        page=browser.new_page(viewport={'width':390,'height':844})
        page.goto(base+'/library/files/'+transcript['id']+'/open')
        page.get_by_text('Ask about this page/image',exact=True).click();page.get_by_text('Link supplied lecture frames',exact=True).click()
        for index,frame in enumerate(frames):
            if index:page.locator('#mm-frame-add').click()
            row=page.locator('.mm-frame-row').nth(index)
            row.locator('select').select_option(frame['id']);row.locator('input').fill(str(13000+index*1000))
        page.locator('#mm-manifest').click();page.get_by_role('link',name='Open lecture evidence',exact=True).click()
        expect(page.get_by_text('Supplied transcript interval 12500–18000 ms',exact=False)).to_be_visible()
        expect(page.locator('figure')).to_have_count(3)
        for img in page.locator('figure img').all():expect(img).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        browser.close()


def test_delayed_preview_cannot_approve_edited_scope(live):
    from playwright.sync_api import sync_playwright,expect
    base,doc,lib=live
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH') or None)
        page=browser.new_page();held=[]
        page.goto(base+'/library/files/'+doc['id']+'/open');page.get_by_text('Ask about this page/image',exact=True).click()
        page.locator('#mm-method').select_option('review');page.locator('#mm-review-complete').check();page.locator('#mm-text').fill('First reading')
        page.route('**/multimodal/preview',lambda route:held.append(route))
        page.locator('#mm-preview').click();page.wait_for_timeout(100)
        page.locator('#mm-text').fill('Edited reading');held[0].continue_()
        expect(page.locator('#mm-status')).to_contain_text('changed')
        expect(page.locator('#mm-approve')).to_be_hidden()
        browser.close()


def test_other_pdf_page_does_not_restore_previously_selected_page(live):
    from playwright.sync_api import sync_playwright,expect
    from test_native_document_library import pdf_bytes
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    base,doc,lib=live;pdf=lib.upload(BytesIO(pdf_bytes()),'Two pages.pdf')
    service=MultimodalEvidenceService(lib);p=service.preview(pdf['id'],{'kind':'pdf_page','page':1},method='review',review_complete=True,text='Page one only')
    service.enqueue(pdf['id'],p['token'])
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH') or None)
        page=browser.new_page();page.goto(base+'/library/files/'+pdf['id']+'/open?position=1')
        page.get_by_text('Ask about this page/image',exact=True).click();expect(page.locator('#mm-ask')).to_be_visible(timeout=20000)
        before=page.locator('#pdf-page').bounding_box()['width'];page.get_by_role('button',name='Zoom +',exact=True).click()
        assert page.locator('#pdf-page').bounding_box()['width']>before*1.2
        page.goto(base+'/library/files/'+pdf['id']+'/open?position=2');page.get_by_text('Ask about this page/image',exact=True).click()
        expect(page.locator('#mm-status')).to_contain_text('another page')
        expect(page.locator('#mm-ask')).to_be_hidden()
        browser.close()


@pytest.mark.parametrize('width',[320,390,768,1366])
def test_rotated_pdf_crop_tutor_citation_and_return(live,width,tmp_path):
    import fitz
    from playwright.sync_api import sync_playwright,expect
    base,_,lib=live
    pdf=fitz.open();p=pdf.new_page(width=400,height=600)
    p.insert_text((40,70),'TOP_LEFT_SECRET');p.insert_text((40,520),'BOTTOM_LEFT_SELECTED');p.set_rotation(90)
    original=pdf.tobytes();pdf.close();doc=lib.upload(BytesIO(original),'Rotated matrix.pdf')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH') or None,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':width,'height':568});page.set_default_timeout(7000)
        page.goto(base+'/library/files/'+doc['id']+'/open?position=1')
        page.get_by_text('Ask about this page/image',exact=True).click()
        page.locator('#mm-crop-enabled').check();page.get_by_label('Right (%)').fill('25');page.get_by_label('Bottom (%)').fill('50')
        page.locator('#mm-preview').focus();page.keyboard.press('Enter')
        expect(page.locator('#mm-approve')).to_be_visible();page.locator('#mm-approve').click()
        expect(page.locator('#mm-ask')).to_be_visible(timeout=20000)
        page.reload();page.get_by_text('Ask about this page/image',exact=True).click()
        expect(page.get_by_label('Right (%)')).to_have_value('25')
        page.locator('#mm-ask').click();page.wait_for_url('**/agent/sessions/*')
        page.locator('#agent-question').fill('What does this show?');page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.agent-turn-assistant')).to_contain_text('two rows',timeout=15000)
        page.get_by_text('Sources & answer details',exact=True).click();page.locator('a[href^="/sources/evidence/"]').first.click()
        image=page.get_by_alt_text('Exact retained PDF page');expect(image).to_be_visible();expect(page.get_by_label('Selected crop boundary')).to_be_visible()
        before=image.bounding_box()['width'];page.get_by_role('button',name='Zoom +',exact=True).click()
        assert image.bounding_box()['width']>before*1.2
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        out=Path(os.getenv('ANVAYA_WEB_ARTIFACTS',str(tmp_path)));out.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(out/f'rotated-pdf-citation-{width}.png'))
        page.get_by_role('link',name='Return to selected page',exact=True).click()
        page.get_by_text('Ask about this page/image',exact=True).click()
        expect(page.get_by_label('Right (%)')).to_have_value('25')
        assert lib.original(doc['id']).read_bytes()==original
        browser.close()


def test_unknown_review_ui_preserves_ambiguity_and_rejects_edits(live,tmp_path):
    from playwright.sync_api import sync_playwright,expect
    base,doc,lib=live
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH') or None)
        page=browser.new_page(viewport={'width':320,'height':568})
        page.goto(base+'/library/files/'+doc['id']+'/open');page.get_by_text('Ask about this page/image',exact=True).click()
        page.locator('#mm-method').select_option('review');page.locator('#mm-review-complete').check();page.locator('#mm-text').fill('Matrix [[1,?],[0,2]]')
        page.locator('#mm-unresolved').fill('Entry (1,2): missing sign')
        page.locator('#mm-review-complete').check();page.locator('#mm-preview').click()
        expect(page.locator('#mm-approve')).to_be_visible();page.locator('#mm-review-complete').uncheck()
        expect(page.locator('#mm-approve')).to_be_hidden();page.locator('#mm-preview').click();page.locator('#mm-approve').click()
        expect(page.locator('#mm-ask')).to_be_visible(timeout=20000);page.locator('#mm-ask').click();page.wait_for_url('**/agent/sessions/*')
        page.locator('#agent-question').fill('Calculate its inverse');page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.agent-turn-assistant')).to_contain_text('unclear',timeout=15000)
        expect(page.locator('.agent-turn-assistant')).to_contain_text('Entry (1,2)')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        out=Path(os.getenv('ANVAYA_WEB_ARTIFACTS',str(tmp_path)));out.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(out/'unclear-matrix-320.png'));browser.close()
