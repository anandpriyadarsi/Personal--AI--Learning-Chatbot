"""Real Chromium mobile file-manager journeys, synthetic originals only."""
import os
from threading import Thread
import pytest
from werkzeug.serving import make_server
from test_native_document_library import pdf_bytes, pptx_bytes
from test_native_library_routes import app

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1', reason='Enable real Chromium tests with ANVAYA_BROWSER_TESTS=1')


@pytest.fixture
def server(app):
    # Exercise the actual async worker, not synchronous test-only route parsing.
    from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
    old=app.config['NATIVE_LIBRARY_SERVICE']
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    directory=old.root.parent/'data';directory.mkdir(exist_ok=True)
    apply_migrations(directory/'learning_assistant.db')
    live=NativeDocumentLibrary(directory/'native_library',autostart=False)
    live.configure_tutor(directory/'learning_assistant.db',directory/'tutor_retrieval')
    live.start_worker()
    app.config['NATIVE_LIBRARY_SERVICE']=live
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}',live
    finally: server.shutdown();thread.join(5);server.server_close();live.close()


@pytest.mark.parametrize('width,theme',[(360,'dark'),(390,'light'),(1366,'dark')])
def test_upload_search_read_rename_move_download_and_delete(server,width,theme,tmp_path):
    from playwright.sync_api import sync_playwright, expect
    base,lib=server
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        context=browser.new_context(viewport={'width':width,'height':840},color_scheme=theme,accept_downloads=True)
        context.add_init_script("localStorage.setItem('anvaya.mobile.theme',"+__import__('json').dumps(theme)+");")
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        assert page.goto(base+'/library/files').status==200
        page.wait_for_function('(theme)=>document.documentElement.dataset.theme===theme',arg=theme)
        page.get_by_label('Add files or folder').click()
        page.get_by_role('button',name='Import files',exact=True).first.click()
        raw=pdf_bytes()
        page.locator('#import-form input[type=file]').set_input_files([
            {'name':'Linear Algebra Chapter 3.pdf','mimeType':'application/pdf','buffer':raw},
            {'name':'Matrix Methods Lecture.pptx','mimeType':'application/vnd.openxmlformats-officedocument.presentationml.presentation','buffer':pptx_bytes()}])
        page.locator('#import-form button[type=submit]').click()
        expect(page.locator('#import-results')).to_contain_text('Linear Algebra Chapter 3.pdf · Saved')
        expect(page.locator('#import-results')).to_contain_text('Matrix Methods Lecture.pptx · Saved')
        page.get_by_role('button',name='Done · Show saved files').click()
        expect(page.locator('.file-row')).to_have_count(2)
        expect(page.locator('[data-status]').first).to_have_text('Ready for Tutor',timeout=20000)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('.files-heading').bounding_box()['height'] < 200
        if theme=='light':
            assert page.locator('.file-row').first.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(255, 255, 255)'
        output=os.environ.get('ANVAYA_NATIVE_LIBRARY_ARTIFACTS')
        if output:
            from pathlib import Path
            Path(output).mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(Path(output)/f'files-{width}-{theme}.png'),full_page=True)
        page.locator('#file-search').fill('linear alg');page.locator('#file-search').press('Enter')
        expect(page.locator('.file-row')).to_have_count(1)
        row=page.locator('.file-row');row.locator('summary').click()
        row.get_by_role('button',name='Rename',exact=True).click()
        page.locator('#rename-form input[name=display_name]').fill('My Linear Algebra')
        page.get_by_role('button',name='Save name').click()
        expect(page.locator('.file-main h2')).to_have_text('My Linear Algebra')
        page.goto(base+'/library/files')
        row=page.locator('.file-row').filter(has_text='My Linear Algebra')
        expect(row).to_be_visible()
        row.locator('summary').click()
        with page.expect_download() as info:row.get_by_role('link',name='Export original',exact=True).click()
        download=info.value
        assert download.suggested_filename=='My Linear Algebra.pdf'
        assert open(download.path(),'rb').read()==raw
        # Trash is recoverable and preserves exact original bytes.
        row.get_by_role('button',name='Move to Trash',exact=True).click()
        expect(page.locator('.file-row')).to_have_count(1)
        page.goto(base+'/library/files?collection=trash')
        row=page.locator('.file-row');expect(row).to_contain_text('My Linear Algebra')
        row.locator('summary').click();row.get_by_role('button',name='Restore',exact=True).click()
        expect(page.locator('.file-row')).to_have_count(0)
        page.goto(base+'/library/files')
        expect(page.locator('.file-row')).to_have_count(2)
        page.get_by_role('link',name='Semester 1',exact=False).click()
        expect(page.locator('.files-folders')).to_contain_text('MA103N')
        page.locator('.files-folders a').first.click()
        page.on('dialog',lambda dialog:dialog.accept())
        page.get_by_role('button',name='Folder template',exact=True).click()
        expect(page.locator('.files-folders')).to_contain_text('Practice Problems')

        assert not errors
        context.close();browser.close()


def test_no_horizontal_overflow_with_long_filename_and_menu(server):
    from io import BytesIO
    from playwright.sync_api import sync_playwright
    base,lib=server
    lib.upload(BytesIO(pdf_bytes()),'A'*220+'.pdf')
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport={'width':320,'height':740})
        page.goto(base+'/library/files');page.locator('.file-row .file-menu summary').click()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.close()


def test_inside_document_search_has_more_matches(server):
    from io import BytesIO
    import fitz
    from playwright.sync_api import sync_playwright,expect
    base,lib=server;pdf=fitz.open()
    for _ in range(55):
        p=pdf.new_page();p.insert_text((40,60),'Eigenvalues in this long document')
    d=lib.upload(BytesIO(pdf.tobytes()),'Long.pdf')
    lib.run_pending()
    # The production async worker may have claimed it before this thread.
    import time
    deadline=time.monotonic()+10
    while lib.get(d['id'])['status'] not in ('ready','failed') and time.monotonic()<deadline:time.sleep(.05)
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport={'width':390,'height':844})
        page.goto(base+f"/library/files/{d['id']}/open")
        page.locator('#within-search input[name=q]').fill('Eigenvalues')
        page.locator('#within-search button').click()
        expect(page.locator('#within-results a')).to_have_count(50)
        expect(page.locator('#within-results').get_by_role('button',name='More matches')).to_have_count(1)
        page.locator('#within-results').get_by_role('button',name='More matches').click()
        expect(page.locator('#within-results a')).to_have_count(55)
        expect(page.locator('#within-results')).to_contain_text('Page 55')
        browser.close()


def test_default_open_and_distinct_rename_course_actions_keep_original(server):
    from io import BytesIO
    from playwright.sync_api import sync_playwright,expect
    base,lib=server;raw=pdf_bytes()
    doc=lib.upload(BytesIO(raw),'Imported PDF.pdf',indexing=False)
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(viewport={'width':390,'height':844},accept_downloads=True)
        page=context.new_page();page.goto(base+'/library/files');row=page.locator('.file-row')
        assert row.locator('.file-main h2 a').get_attribute('href')==f"/library/files/{doc['id']}/original?native_action=view"
        with page.expect_response(lambda response:response.url.endswith('/original?native_action=view')) as opened:
            row.locator('.file-main h2 a').click()
        assert opened.value.headers['content-type']=='application/pdf'
        assert lib.get(doc['id'])['status']=='disabled'
        page.goto(base+'/library/files');row=page.locator('.file-row');row.locator('summary').click()
        assert row.get_by_role('link',name='Open with…',exact=True).get_attribute('href').endswith('native_action=open_with')
        row.get_by_role('button',name='Rename',exact=True).click()
        expect(page.locator('#rename-dialog')).to_be_visible()
        page.locator('#rename-form input[name=display_name]').fill('Renamed visible lecture')
        page.get_by_role('button',name='Save name',exact=True).click()
        expect(page.locator('.file-main h2')).to_have_text('Renamed visible lecture')
        row=page.locator('.file-row');row.locator('summary').click();row.get_by_role('button',name='Move',exact=True).click()
        page.locator('#destination-children').get_by_role('button',name='Semester 1',exact=True).click()
        page.locator('#destination-children').get_by_role('button',name='MA103N — Linear Algebra',exact=True).click()
        page.on('dialog',lambda dialog:dialog.accept())
        page.get_by_role('button',name='Use this folder',exact=True).click()
        expect(page.locator('.file-row')).to_have_count(0)
        page.goto(base+'/library/files?folder_id='+lib.get(doc['id'])['folder_id'])
        expect(page.locator('.files-breadcrumbs')).to_contain_text('MA103N — Linear Algebra')
        assert lib.get(doc['id'])['id']==doc['id'] and lib.get(doc['id'])['status']=='disabled'
        row=page.locator('.file-row');row.locator('summary').click()
        output=os.environ.get('ANVAYA_NATIVE_LIBRARY_ARTIFACTS')
        if output:
            from pathlib import Path
            page.screenshot(path=str(Path(output)/'files-native-actions-390.png'),full_page=True)
        with page.expect_download() as info:row.get_by_role('link',name='Export original',exact=True).click()
        assert info.value.suggested_filename=='Renamed visible lecture.pdf'
        assert open(info.value.path(),'rb').read()==raw
        context.close();browser.close()
