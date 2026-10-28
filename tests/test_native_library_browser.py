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
    old=app.config['NATIVE_LIBRARY_SERVICE']; live=NativeDocumentLibrary(old.root)
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
        page.get_by_role('button',name='Upload').click()
        raw=pdf_bytes()
        page.locator('#upload-form input[type=file]').set_input_files({'name':'Linear Algebra Chapter 3.pdf','mimeType':'application/pdf','buffer':raw})
        page.locator('#upload-form select[name=subject_id]').select_option('ma103')
        page.locator('#upload-form input[name=indexing]').check()
        page.get_by_role('button',name='Store document').click()
        expect(page.locator('.file-row')).to_have_count(1)
        expect(page.locator('[data-status]')).to_have_text('Search Ready',timeout=20000)
        page.get_by_role('button',name='Upload').click()
        page.locator('#upload-form input[type=file]').set_input_files({'name':'Matrix Methods Lecture.pptx','mimeType':'application/vnd.openxmlformats-officedocument.presentationml.presentation','buffer':pptx_bytes()})
        page.locator('#upload-form select[name=subject_id]').select_option('ma103')
        page.locator('#upload-form input[name=indexing]').check()
        page.get_by_role('button',name='Store document').click()
        expect(page.locator('.file-row')).to_have_count(2)
        expect(page.locator('[data-status]').first).to_have_text('Search Ready',timeout=20000)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('.files-heading').bounding_box()['height'] < 200
        if theme=='light':
            assert page.locator('.file-row').first.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(255, 255, 255)'
        output=os.environ.get('ANVAYA_NATIVE_LIBRARY_ARTIFACTS')
        if output:
            from pathlib import Path
            Path(output).mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(Path(output)/f'files-{width}-{theme}.png'),full_page=True)
        page.locator('#file-search').fill('Eigenvalues');page.locator('#file-search').press('Enter')
        expect(page.locator('.files-match')).to_have_count(3)
        pdf_match=page.locator('.files-match').filter(has_text='Page 2')
        pdf_match.get_by_role('link',name='Open at Match').click()
        expect(page.locator('.files-heading')).to_contain_text('Page 2')
        expect(page.locator('#pdf-page')).to_be_visible()
        page.wait_for_function('document.getElementById("pdf-page").naturalWidth>0')
        page.locator('#within-search input[name=q]').fill('LU Factorization')
        page.locator('#within-search button').click()
        expect(page.locator('#within-results a')).to_have_count(2)
        page.get_by_role('button',name='Fullscreen',exact=True).click()
        assert page.evaluate('!!document.fullscreenElement || document.querySelector(".reader-focus")!==null')
        page.keyboard.press('Escape')
        page.goto(base+'/library/files')
        row=page.locator('.file-row').filter(has_text='Linear Algebra Chapter 3.pdf')
        row.locator('summary').click();row.get_by_role('button',name='Details / Move folder').click()
        page.locator('#edit-form input[name=display_name]').fill('My Linear Algebra')
        page.locator('#edit-form input[name=topic]').fill('Eigenvalues')
        page.locator('#edit-form input[name=tags]').fill('exam, revision')
        page.locator('#edit-form button[type=submit]').click()
        expect(page.locator('.file-row').filter(has_text='My Linear Algebra')).to_be_visible()
        page.get_by_role('button',name='New folder',exact=True).click()
        page.locator('#folder-form input[name=name]').fill('Semester 1')
        page.get_by_role('button',name='Save folder').click()
        row=page.locator('.file-row').filter(has_text='My Linear Algebra')
        row.locator('summary').click();row.get_by_role('button',name='Details / Move folder').click()
        page.locator('#edit-form select[name=folder_id]').select_option(label='Semester 1')
        page.locator('#edit-form button[type=submit]').click()
        page.locator('.files-folders').get_by_role('link',name='Semester 1').click()
        expect(page.locator('.file-row')).to_have_count(1)
        row=page.locator('.file-row');row.locator('summary').click()
        with page.expect_download() as info: row.get_by_role('link',name='Save / Export',exact=True).click()
        download=info.value
        assert download.suggested_filename=='My Linear Algebra.pdf'
        assert open(download.path(),'rb').read()==raw
        page.on('dialog',lambda dialog:dialog.accept())
        row.get_by_role('button',name='Delete',exact=True).click()
        expect(page.locator('.file-row')).to_have_count(0)
        assert not errors
        context.close();browser.close()


def test_no_horizontal_overflow_with_long_filename_and_menu(server):
    from io import BytesIO
    from playwright.sync_api import sync_playwright
    base,lib=server
    lib.upload(BytesIO(pdf_bytes()),'A'*220+'.pdf')
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport={'width':320,'height':740})
        page.goto(base+'/library/files');page.locator('.file-menu summary').click()
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
        row=page.locator('.file-row');row.locator('summary').click();row.get_by_role('button',name='Move to Course',exact=True).click()
        page.locator('#course-form select[name=subject_id]').select_option('ma103');page.get_by_role('button',name='Save course',exact=True).click()
        expect(page.locator('.file-row')).to_contain_text('MA103N — Linear Algebra')
        assert lib.get(doc['id'])['id']==doc['id'] and lib.get(doc['id'])['status']=='disabled'
        row=page.locator('.file-row');row.locator('summary').click()
        output=os.environ.get('ANVAYA_NATIVE_LIBRARY_ARTIFACTS')
        if output:
            from pathlib import Path
            page.screenshot(path=str(Path(output)/'files-native-actions-390.png'),full_page=True)
        with page.expect_download() as info:row.get_by_role('link',name='Save / Export',exact=True).click()
        assert info.value.suggested_filename=='Renamed visible lecture.pdf'
        assert open(info.value.path(),'rb').read()==raw
        context.close();browser.close()
