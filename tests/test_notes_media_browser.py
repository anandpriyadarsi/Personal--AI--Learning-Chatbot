"""Real browser media management, lazy bytes, and responsive controls."""
import os
from pathlib import Path
from threading import Thread
import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server
from tests.test_notes_media import SAMPLES
from tests.test_ui_v2_protected_browser import protected_browser

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Real Chromium opt-in')

@pytest.fixture
def live_media(tmp_path):
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepository
    from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService
    from personal_learning_assistant.ui.web import create_app
    repo=AnvayaNotesRepository(notes_path=tmp_path/'notes.json',assets_root=tmp_path/'assets')
    service=AnvayaNotesService(repo)
    note=service.create_handwritten_note({'title':'Spectroscopy','course':'CY100N'},[('page.pdf',b'%PDF-1.4\n%%EOF')])['id']
    app=create_app({'TESTING':True,'PRIVATE_MOBILE_MODE':True,'ANVAYA_NOTES_SERVICE_FACTORY':lambda:service})
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}',note,repo
    finally: server.shutdown();thread.join(5);server.server_close()

@pytest.mark.parametrize('width',[360,390,1366])
def test_real_upload_reopen_rename_delete_no_preload(protected_browser,live_media,width):
    base,note,repo=live_media
    with protected_browser.new_context(viewport={'width':width,'height':844},accept_downloads=True) as context:
        page=context.new_page();errors=[];files=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:files.append(request.url) if '/notes/media/' in request.url and request.url.endswith(('/file','/open','/share')) else None)
        page.goto(f'{base}/notes/view/{note}')
        expect(page.get_by_role('heading',name='Attached Media')).to_be_visible()
        expect(page.locator('#notes-media-status')).to_contain_text('No media attached')
        page.locator('#notes-media-management>summary').click()
        page.locator('#notes-media-files').set_input_files([
            {'name':'Spectroscopy Lecture.mp4','mimeType':'video/mp4','buffer':SAMPLES['mp4']},
            {'name':'Teacher Explanation.mp3','mimeType':'audio/mpeg','buffer':SAMPLES['mp3']}])
        page.get_by_role('button',name='Attach Media',exact=True).click()
        expect(page.locator('.notes-media-row')).to_have_count(2)
        expect(page.locator('#notes-media-status')).to_contain_text('Media attached')
        page.reload()
        expect(page.locator('.notes-media-row')).to_have_count(2)
        assert files==[]
        assert page.locator('audio,video').count()==0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        first=page.locator('.notes-media-row').first
        first.get_by_text('Attachment options',exact=True).click()
        first.get_by_label('Attachment name').fill('Revised Lecture.mp4')
        first.get_by_role('button',name='Rename',exact=True).click()
        expect(page.locator('.notes-media-open').first).to_have_text('Revised Lecture.mp4')
        with page.expect_download() as event:
            page.locator('.notes-media-open').first.click()
        assert event.value.suggested_filename=='Revised Lecture.mp4'
        assert Path(event.value.path()).read_bytes()==SAMPLES['mp4']
        # Download leaves the same notes page intact for browser users.
        expect(page.get_by_role('heading',name='Spectroscopy',exact=True)).to_be_visible()
        first=page.locator('.notes-media-row').first
        first.get_by_text('Attachment options',exact=True).click()
        page.once('dialog',lambda dialog:dialog.accept())
        first.get_by_role('button',name='Delete attachment',exact=True).click()
        expect(page.locator('.notes-media-row')).to_have_count(1)
        page.reload();expect(page.locator('.notes-media-row')).to_have_count(1)
        assert len(repo.get_note(note)['assets'])==1
        assert not errors,errors


def test_failed_upload_keeps_selection_for_retry(protected_browser,live_media):
    base,note,_=live_media
    with protected_browser.new_context(viewport={'width':390,'height':844}) as context:
        page=context.new_page();page.goto(f'{base}/notes/view/{note}')
        page.locator('#notes-media-management>summary').click()
        picker=page.locator('#notes-media-files')
        picker.set_input_files({'name':'not-valid.mp3','mimeType':'audio/mpeg','buffer':b'<html>not media</html>'})
        page.get_by_role('button',name='Attach Media',exact=True).click()
        expect(page.locator('#notes-media-status')).to_contain_text('Choose a valid')
        assert picker.evaluate('(input)=>input.files.length')==1
        assert not page.get_by_role('button',name='Attach Media',exact=True).is_disabled()
