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


@pytest.mark.parametrize('width,height',[(320,568),(390,844),(768,1024),(1366,768),(390,440)])
def test_image_review_to_existing_tutor_exact_citation_and_stale_source(live,width,height,tmp_path):
    from playwright.sync_api import sync_playwright,expect
    base,doc,lib=live
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.getenv('ANVAYA_CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':width,'height':height});page.set_default_timeout(5000);errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/library/files/'+doc['id']+'/open')
        page.get_by_text('Ask about this page/image',exact=True).click()
        page.locator('#mm-method').select_option('review');page.locator('#mm-text').fill('The matrix has two rows and two columns.')
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
