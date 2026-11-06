"""Focused thumbnail safety and actual responsive file-manager verification."""
from io import BytesIO
import os
from pathlib import Path

import fitz
import pytest
from PIL import Image

from test_native_document_library import pdf_bytes, pptx_bytes
from test_native_library_routes import app
from test_native_library_browser import server


def test_thumbnail_is_real_first_page_small_private_and_original_unchanged(app, monkeypatch):
    lib = app.config['NATIVE_LIBRARY_SERVICE']
    raw = pdf_bytes()
    doc = lib.upload(BytesIO(raw), 'Lecture.pdf', indexing=False)
    copied = lib.copy(doc['id'])
    renders = []
    render = fitz.Page.get_pixmap

    def counted(page, *args, **kwargs):
        renders.append(page.number)
        return render(page, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, 'get_pixmap', counted)
    client = app.test_client()
    url = f"/library/files/{doc['id']}/thumbnail.png"
    # Folder browsing itself must not render or enqueue conversion work.
    assert client.get('/library/files').status_code == 200
    assert not renders
    response = client.get(url)
    assert response.status_code == 200
    assert response.mimetype == 'image/png'
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    image = Image.open(BytesIO(response.data))
    assert 1 <= max(image.size) <= 241
    assert image.getextrema() != ((255, 255),) * 3  # Real page text, not a blank tile.
    with fitz.open(stream=raw, filetype='pdf') as pdf:
        page = pdf[0]
        scale = min(1.0, 240 / max(page.rect.width, page.rect.height))
        expected = render(page, matrix=fitz.Matrix(scale, scale), alpha=False).tobytes('png')
    assert response.data == expected
    assert client.get(url).data == expected
    assert client.get(f"/library/files/{copied['id']}/thumbnail.png").data == expected
    assert renders == [0]
    assert lib.original(doc['id']).read_bytes() == raw
    assert lib.get(doc['id'])['status'] == 'disabled'
    assert not lib.collection('recent')['items']  # A thumbnail isn't a user open.
    lib.original(doc['id']).unlink()
    assert client.get(url).status_code == 409  # Cached bytes cannot mask loss of original.


def test_thumbnail_fallback_for_slides_encrypted_pdf_and_missing_renderer(app, monkeypatch):
    lib = app.config['NATIVE_LIBRARY_SERVICE']
    slides = lib.upload(BytesIO(pptx_bytes()), 'Slides.pptx', indexing=False)
    client = app.test_client()
    assert client.get(f"/library/files/{slides['id']}/thumbnail.png").status_code == 409
    pdf = fitz.open()
    pdf.new_page()
    raw = pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='user')
    pdf.close()
    encrypted = lib.upload(BytesIO(raw), 'Private.pdf', indexing=False)
    assert client.get(f"/library/files/{encrypted['id']}/thumbnail.png").status_code == 409
    plain = lib.upload(BytesIO(pdf_bytes()), 'Plain.pdf', indexing=False)
    import builtins
    original_import = builtins.__import__

    def without_renderer(name, *args, **kwargs):
        if name == 'fitz':
            raise ImportError('optional renderer unavailable')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', without_renderer)
    assert client.get(f"/library/files/{plain['id']}/thumbnail.png").status_code == 409
    assert client.get('/library/files').status_code == 200


def test_thumbnail_cache_is_bounded_and_does_not_serve_deleted_documents(app):
    lib = app.config['NATIVE_LIBRARY_SERVICE']
    client = app.test_client()
    first = None
    for index in range(65):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 60), f'Lecture {index}')
        doc = lib.upload(BytesIO(pdf.tobytes()), f'Lecture {index}.pdf', indexing=False)
        pdf.close()
        first = first or doc
        assert client.get(f"/library/files/{doc['id']}/thumbnail.png").status_code == 200
    images = app.extensions['native_library_thumbnails']['images']
    assert len(images) == 64 and first['sha256'] not in images
    lib.delete(doc['id'])
    assert client.get(f"/library/files/{doc['id']}/thumbnail.png").status_code == 404


@pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Enable real Chromium with ANVAYA_BROWSER_TESTS=1')
@pytest.mark.parametrize('width', [390, 1366])
def test_refined_library_layout_preview_filters_keyboard_and_views(server, width):
    from playwright.sync_api import sync_playwright, expect
    base, lib = server
    courses = [
        ('CY100N', 'Green Chemistry'), ('UC100N', 'Data Science and AI'),
        ('DE100N', 'Design Thinking and Prototyping'), ('UC103N', 'Indian Knowledge System'),
        ('PL110N', 'Introduction to Physical Activities I'), ('PL120N', 'Introduction to Cultural Activities I'),
        ('PL130N', 'Introduction to Technical Activities I'), ('PL140N', 'Professional Communication I'),
    ]
    lib.bootstrap_academics([{'id':code, 'code':code, 'name':name} for code, name in courses])
    # A synthetic academic page makes the real thumbnail legible in evidence.
    pdf = fitz.open()
    page = pdf.new_page(width=480, height=640)
    page.draw_rect(fitz.Rect(0, 0, 480, 100), color=None, fill=(.08, .18, .23))
    page.insert_text((30, 35), 'UC100N / DATA SCIENCE & AI', fontsize=12, color=(.5, .9, .85))
    page.insert_text((30, 72), 'Data Preprocessing', fontsize=24, color=(1, 1, 1))
    page.insert_textbox(fitz.Rect(30, 125, 450, 600),
        '01  Preparing a dataset\n\nGood analysis starts with reliable data.\nInspect missing values, duplicates and types.\n\n02  Cleaning and transformation\n\n1. Handle missing observations\n2. Remove duplicate rows\n3. Encode categorical features\n4. Scale numerical features\n\n03  Practice\n\nLoad the sample dataset and compare the\nsummary statistics before and after cleaning.',
        fontsize=14, lineheight=1.6, color=(.12, .18, .23))
    doc = lib.upload(BytesIO(pdf.tobytes()), 'Data Preprocessing.pdf', indexing=False)
    pdf.close()
    lib.upload(BytesIO(pptx_bytes()), 'DSAI-Week 6 Lab Assignment-2.pptx', indexing=False)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width':width, 'height':900}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error:errors.append(str(error)))
        assert page.goto(base + '/library/files').status == 200
        preview = page.locator('.file-thumbnail.pdf img')
        expect(preview).to_be_visible()
        assert preview.evaluate('(image)=>image.complete && image.naturalWidth>0')
        assert page.locator('.file-thumbnail.pptx').get_attribute('aria-label').endswith('slide preview unavailable')
        assert page.locator('.file-thumbnail.pptx .file-fallback').is_visible()
        assert page.locator('.academic-files a').evaluate_all('(links)=>links.every(a=>getComputedStyle(a).textDecorationLine==="none")')
        page.locator('.search-filters summary').focus()
        page.keyboard.press('Enter')
        checkbox = page.get_by_role('checkbox', name='Search inside supported files')
        box = checkbox.bounding_box()
        assert 18 <= box['width'] <= 20 and 18 <= box['height'] <= 20
        checkbox.focus()
        page.keyboard.press('Space')
        expect(checkbox).to_be_checked()
        assert checkbox.evaluate('(input)=>getComputedStyle(input).outlineStyle!="none"')
        page.keyboard.press('Space')
        expect(checkbox).not_to_be_checked()
        controls = page.locator('.search-filters select').all()
        assert len({round(c.bounding_box()['height']) for c in controls}) == 1
        assert page.locator('.search-filters').bounding_box()['height'] < (290 if width == 390 else 140)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        # Keyboard toggle and persisted pressed state must agree with the layout.
        toggle = page.locator('[data-action="toggle-view"]')
        toggle.focus()
        page.keyboard.press('Enter')
        expect(page.locator('#file-list')).to_have_class('files-list grid')
        expect(toggle).to_have_attribute('aria-pressed', 'true')
        page.reload()
        expect(toggle).to_have_attribute('aria-pressed', 'true')
        page.locator('.search-filters summary').click()
        expect(preview).to_be_visible()
        out = os.environ.get('ANVAYA_NATIVE_LIBRARY_ARTIFACTS')
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(out) / f'library-refined-files-{width}.png'), full_page=True)
        # Filename/type filtering and original download are still exact.
        page.locator('#file-search').fill('Preprocessing')
        page.locator('select[name=kind]').select_option('pdf')
        page.locator('.files-search>button').click()
        expect(page.locator('.file-row')).to_have_count(1)
        assert 'kind=pdf' in page.url
        assert page.request.get(f"{base}/library/files/{doc['id']}/original").body() == lib.original(doc['id']).read_bytes()
        page.goto(base + '/library/files')
        page.locator('.files-folders a').filter(has_text='Semester 1').click()
        expect(page.locator('.files-folders a')).to_have_count(9)
        assert page.locator('.folder-code').count() == 9
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        heights = [a.bounding_box()['height'] for a in page.locator('.folder-card').all()]
        assert max(heights) < 200
        if out:
            page.screenshot(path=str(Path(out) / f'library-refined-subjects-{width}.png'), full_page=True)
        page.locator('.folder-card').filter(has_text='DE100N').click()
        expect(page.locator('.files-breadcrumbs')).to_contain_text('Design Thinking and Prototyping')
        assert not errors
        browser.close()


@pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Enable real Chromium with ANVAYA_BROWSER_TESTS=1')
def test_thumbnails_load_near_viewport_and_fail_to_clear_file_icon(server):
    from playwright.sync_api import sync_playwright, expect
    base, lib = server
    for index in range(12):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 60), f'Lesson {index}')
        lib.upload(BytesIO(pdf.tobytes()), f'Lesson {index}.pdf', indexing=False)
        pdf.close()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width':390, 'height':844})
        requested = []
        def unavailable(route):
            requested.append(route.request.url)
            route.abort()
        page.route('**/thumbnail.png', unavailable)
        page.goto(base + '/library/files')
        fallback = page.locator('.file-thumbnail').first
        expect(fallback).to_have_attribute('aria-label', 'PDF file icon; first-page preview unavailable')
        assert 0 < len(requested) < 12  # Ordinary browsing defers off-screen rendering.
        assert fallback.locator('.file-fallback').is_visible()
        assert fallback.locator('img').count() == 0
        last = page.locator('.file-thumbnail').last
        last.scroll_into_view_if_needed()
        expect(last).to_have_attribute('aria-label', 'PDF file icon; first-page preview unavailable')
        assert last.locator('.file-fallback').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.close()
