"""Real mobile browser journeys against disposable independent Notes storage."""
import os
from pathlib import Path
from threading import Thread
import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server
from tests.test_ui_v2_protected_browser import protected_browser
from tests.test_notes_media import SAMPLES

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Real Chromium opt-in')

@pytest.fixture
def live(tmp_path):
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepository
    from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService
    from personal_learning_assistant.services.nested_notes_service import NestedNotesService
    from personal_learning_assistant.ui.web import create_app
    repo=AnvayaNotesRepository(notes_path=tmp_path/'notes.json',assets_root=tmp_path/'assets')
    native=AnvayaNotesService(repo);sections=NestedNotesService(repo)
    note=native.create_typed_note({'title':'Day 4 American English','course':'English Communication','body':'# Original practice\nRead clearly.'})['id']
    for title,text in [('Interview Preparation','**Speak clearly** and introduce yourself.'),('Intonation Practice','- [ ] Record a sentence\n- [x] Listen carefully'),('Vocabulary','Distinctive content for search: resilient')]:
        sections.change(note,'add',expected_updated_at=repo.get_note(note)['updated_at'],title=title,body=text)
    app=create_app({'TESTING':True,'PRIVATE_MOBILE_MODE':True,'ANVAYA_NOTES_SERVICE_FACTORY':lambda:native})
    server=make_server('127.0.0.1',0,app,threaded=True);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',repo,note
    finally:server.shutdown();thread.join(5);server.server_close()

@pytest.mark.parametrize('width',[360,390,430])
def test_nested_mobile_accordion_search_edit_attachments_restart(protected_browser,live,width):
    base,repo,note=live
    with protected_browser.new_context(viewport={'width':width,'height':844},reduced_motion='reduce',accept_downloads=True) as context:
        page=context.new_page();errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
        page.goto(f'{base}/notes/view/{note}')
        expect(page.locator('.mini-note')).to_have_count(4)
        assert page.locator('.mini-note[open]').count()==0
        assert not any('/notes/sections/' in u and not u.endswith(note) and '?' not in u for u in requests)
        first=page.locator('.mini-note').nth(1);first.locator('summary').click()
        expect(first.locator('strong')).to_have_text('Speak clearly')
        second=page.locator('.mini-note').nth(2);second.locator('summary').click()
        expect(second.get_by_role('button',name='Edit',exact=True)).to_be_visible()
        assert page.locator('.mini-note[open]').count()==1
        assert second.locator('input[type=checkbox]').count()==2
        second.get_by_role('button',name='Edit',exact=True).click()
        page.locator('#section-title').fill('Intonation Updated');page.locator('#section-body').fill('Revised independent content')
        page.get_by_role('button',name='Save section',exact=True).click()
        expect(page.locator('#section-editor')).to_be_hidden()
        expect(page.locator('.mini-note summary').nth(2)).to_have_text('Intonation Updated')
        page.locator('#section-search').fill('resilient')
        expect(page.locator('.mini-note')).to_have_count(1)
        expect(page.locator('.mini-note summary')).to_have_text('Vocabulary')
        page.locator('#section-search').fill('');expect(page.locator('.mini-note')).to_have_count(4)
        page.get_by_role('button',name='+ Add Section',exact=True).click()
        page.locator('#section-title').fill('Tomorrow’s Practice');page.locator('#section-body').fill('A fresh plan')
        page.get_by_role('button',name='Save section',exact=True).click();expect(page.locator('.mini-note')).to_have_count(5)
        scope=repo.get_note(note)['sections'][0]['id'];page.locator('#media-section').select_option(scope)
        page.locator('#notes-media-files').set_input_files([{'name':'कक्षा Recording.mp3','mimeType':'audio/mpeg','buffer':SAMPLES['mp3']},{'name':'Practice.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4\n%%EOF'}])
        page.get_by_role('button',name='Attach Media',exact=True).click();expect(page.locator('.notes-media-row')).to_have_count(2)
        expect(page.locator('#notes-media-status')).to_contain_text('Media attached')
        assert all(x['section_id']==scope for x in repo.get_note(note)['media'])
        page.reload();expect(page.locator('.mini-note')).to_have_count(5);expect(page.locator('.notes-media-row')).to_have_count(2)
        assert page.locator('audio,video').count()==0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        if width==390:
            folder=Path('docs/mobile/smart-notes/screenshots');folder.mkdir(parents=True,exist_ok=True)
            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(folder/'nested-notes-390.png'))
            page.locator('.mini-note summary').nth(1).click();expect(page.locator('.mini-note-files a')).to_have_count(2)
            page.locator('.mini-note').nth(1).scroll_into_view_if_needed();page.screenshot(path=str(folder/'section-attachments-390.png'))
