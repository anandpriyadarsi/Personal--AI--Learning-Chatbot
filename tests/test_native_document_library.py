from io import BytesIO
from zipfile import ZipFile
import sqlite3
import threading
import pytest
from pypdf import PdfWriter

from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary, LibraryError


def pdf_bytes():
    import fitz
    doc = fitz.open()
    for text in ('Chapter 3: Eigenvalues and LU Factorization', 'Eigenvalues: LU,  Factorization again'):
        p = doc.new_page(); p.insert_text((50, 70), text)
    return doc.tobytes()


def pptx_bytes():
    stream = BytesIO()
    with ZipFile(stream, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="r2"/><p:sldId id="257" r:id="r1"/></p:sldIdLst></p:presentation>')
        z.writestr('ppt/_rels/presentation.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>')
        for i, text in ((1, 'Other slide'), (2, 'Eigenvalues and LU Factorization')):
            z.writestr(f'ppt/slides/slide{i}.xml', f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:sld>')
    return stream.getvalue()


@pytest.fixture
def lib(tmp_path):
    return NativeDocumentLibrary(tmp_path/'files', autostart=False)


def upload(lib, name='Linear Algebra.pdf', raw=None, **kwargs):
    return lib.upload(BytesIO(pdf_bytes() if raw is None else raw), name, **kwargs)


@pytest.mark.parametrize('name,raw', [('Linear Algebra.pdf', pdf_bytes()), ('Matrix Methods.pptx', pptx_bytes()), ('Legacy.ppt', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'+b'legacy'*30)])
def test_preserves_original_and_restart(lib, name, raw):
    doc = upload(lib, name, raw)
    assert lib.original(doc['id']).read_bytes() == raw
    assert doc['original_name'] == name
    reopened = NativeDocumentLibrary(lib.root, autostart=False)
    assert reopened.original(doc['id']).read_bytes() == raw
    assert not list(lib.root.rglob('*.txt'))


def test_phrase_case_punctuation_positions_and_scopes(lib):
    folder = lib.create_folder('Semester 1')
    child = lib.create_folder('Lectures', folder['id'])
    pdf = upload(lib, folder_id=child['id'], subject_id='ma103')
    ppt = upload(lib, 'Matrix Methods.pptx', pptx_bytes(), subject_id='ma103')
    lib.run_pending()
    hits = lib.search('"lu FACTORIZATION"')
    assert {(h['id'], h['position']) for h in hits} == {(pdf['id'],1),(pdf['id'],2),(ppt['id'],1)}
    assert all('snippet' in h and h['snippet'] for h in hits)
    assert {h['id'] for h in lib.search('Eigenvalues', folder_id=folder['id'])} == {pdf['id']}
    assert len(lib.search('Eigenvalues', subject_id='ma103')) == 3
    assert len(lib.search('Eigenvalues', document_id=ppt['id'])) == 1
    assert not lib.search('eigen')
    assert not lib.search('Factorization LU')


def test_metadata_move_copy_delete_and_shared_blob(lib):
    doc = upload(lib); lib.run_pending()
    folder = lib.create_folder('Personal')
    lib.update(doc['id'], display_name='My matrices', folder_id=folder['id'], subject_id='ma103', topic='Eigenvalues', tags=['exam'])
    assert lib.search('My matrices')[0]['id'] == doc['id']
    assert lib.search('LU Factorization', folder_id=folder['id'])[0]['display_name'] == 'My matrices'
    copy = lib.copy(doc['id'])
    assert copy['id'] != doc['id'] and lib.original(copy['id']) == lib.original(doc['id'])
    lib.delete(doc['id'])
    assert lib.original(copy['id']).exists()
    assert not lib.search('LU Factorization', document_id=doc['id'])
    lib.delete(copy['id'])
    assert not list((lib.root/'blobs').iterdir())


def test_duplicate_returns_same_record_without_reassigning(lib):
    raw = pdf_bytes()
    first = upload(lib, raw=raw, subject_id='ma103')
    again = upload(lib, raw=raw, subject_id='chem')
    assert first['id'] == again['id']
    assert lib.get(first['id'])['subject_id'] == 'ma103'
    assert len(lib.list_documents()['items']) == 1


def test_disable_removes_index_rebuild_restores(lib):
    d = upload(lib); lib.run_pending()
    lib.set_indexing(d['id'], False)
    assert not lib.search('Eigenvalues')
    assert lib.original(d['id']).exists()
    with sqlite3.connect(lib.database) as con:
        assert con.execute('SELECT count(*) FROM page_fts').fetchone()[0] == 0
    lib.set_indexing(d['id'], True); lib.run_pending()
    assert len(lib.search('Eigenvalues')) == 2
    lib.rebuild(d['id']); lib.run_pending()
    assert len(lib.search('Eigenvalues')) == 2


def test_scan_ppt_encrypted_invalid_and_interrupted(lib):
    writer = PdfWriter(); writer.add_blank_page(width=200, height=200)
    raw = BytesIO(); writer.write(raw)
    d = upload(lib, raw=raw.getvalue()); lib.run_pending()
    assert lib.get(d['id'])['status'] == 'ocr_required'
    legacy = upload(lib, 'Old.ppt', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'+b'x'*100)
    lib.run_pending(); assert lib.get(legacy['id'])['status'] == 'conversion_required'
    with pytest.raises(LibraryError): upload(lib, '../escape.pdf')
    with pytest.raises(LibraryError): upload(lib, 'bad.pdf', b'not a PDF')
    class Interrupted(BytesIO):
        def read(self, size=-1): raise OSError('interrupted')
    with pytest.raises(OSError): lib.upload(Interrupted(b'x'), 'interrupted.pdf')
    assert not list((lib.root/'tmp').iterdir())


def test_folder_cycles_and_nonempty_delete_refused(lib):
    parent = lib.create_folder('A'); child = lib.create_folder('B', parent['id'])
    with pytest.raises(LibraryError): lib.update_folder(parent['id'], 'A', child['id'])
    with pytest.raises(LibraryError): lib.delete_folder(parent['id'])
    lib.update_folder(child['id'], 'C', None)
    lib.delete_folder(parent['id'])


def test_restart_recovers_interrupted_index_and_corrupt_fts(lib):
    d = upload(lib)
    with sqlite3.connect(lib.database) as con: con.execute("UPDATE documents SET status='indexing'")
    reopened = NativeDocumentLibrary(lib.root, autostart=False); reopened.run_pending()
    assert len(reopened.search('Eigenvalues')) == 2
    with sqlite3.connect(lib.database) as con: con.execute('DROP TABLE page_fts')
    reopened.rebuild(); reopened.run_pending()
    assert len(reopened.search('Eigenvalues')) == 2


def test_disable_during_index_prevents_late_publication(lib, monkeypatch):
    d = upload(lib)
    entered = threading.Event(); release = threading.Event()
    original = lib._extract
    def paused(doc):
        entered.set(); release.wait(5)
        return original(doc)
    monkeypatch.setattr(lib, '_extract', paused)
    worker = threading.Thread(target=lib.run_pending); worker.start()
    assert entered.wait(3)
    lib.set_indexing(d['id'], False); release.set(); worker.join(5)
    assert not worker.is_alive() and not lib.search('Eigenvalues')
    assert lib.get(d['id'])['status'] == 'disabled'


def test_integrity_tamper_rejected(lib):
    d = upload(lib); lib.original(d['id']).write_bytes(b'tampered')
    with pytest.raises(LibraryError): lib.original(d['id'])


def test_search_pagination_has_no_missing_content_hits(lib):
    # A metadata match must not displace the final content hit from page one.
    from io import BytesIO
    import fitz
    pdf=fitz.open()
    for _ in range(65):
        p=pdf.new_page();p.insert_text((40,60),'Eigenvalues across many pages')
    d=lib.upload(BytesIO(pdf.tobytes()),'Eigenvalues.pdf');lib.run_pending()
    first=lib.search('Eigenvalues',limit=50)
    second=lib.search('Eigenvalues',offset=50,limit=50)
    assert {h['position'] for h in first+second if h['position']}==set(range(1,66))
    assert len(first+second)==66  # 65 page matches plus the document name.


def test_local_optional_ocr_preserves_original(lib):
    from personal_learning_assistant.services.native_document_extraction import ocr_available
    if not ocr_available(): pytest.skip('Optional local OCR tools are unavailable')
    import fitz
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGB',(1300,350),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',72)
    draw.text((60,100),'Eigenvalues of a matrix',font=font,fill='black')
    png=BytesIO();image.save(png,format='PNG')
    pdf=fitz.open();page=pdf.new_page(width=650,height=175);page.insert_image(page.rect,stream=png.getvalue())
    raw=pdf.tobytes();doc=upload(lib,raw=raw);lib.run_pending()
    assert not lib.search('Eigenvalues') and lib.get(doc['id'])['status']=='ocr_required'
    lib.rebuild(doc['id'],ocr=True);lib.run_pending()
    assert lib.search('Eigenvalues')[0]['position']==1
    assert lib.original(doc['id']).read_bytes()==raw


def test_delete_during_index_has_no_late_rows(lib,monkeypatch):
    d=upload(lib);entered=threading.Event();release=threading.Event();extract=lib._extract
    def paused(doc):
        result=extract(doc);entered.set();release.wait(5);return result
    monkeypatch.setattr(lib,'_extract',paused)
    worker=threading.Thread(target=lib.run_pending);worker.start();assert entered.wait(3)
    lib.delete(d['id']);release.set();worker.join(5)
    assert not lib.search('Eigenvalues')
    with sqlite3.connect(lib.database) as con: assert con.execute('SELECT count(*) FROM pages').fetchone()[0]==0


def test_resource_limit_reports_failed_without_losing_original(lib):
    bad=b'PK\x03\x04'+b'not a complete presentation'
    d=upload(lib,'Bad.pptx',bad);lib.run_pending()
    assert lib.get(d['id'])['status']=='failed'
    assert lib.original(d['id']).read_bytes()==bad


def test_fts_unavailable_keeps_storage_and_exact_search(tmp_path,monkeypatch):
    import personal_learning_assistant.services.native_document_library as module
    monkeypatch.setattr(module,'FTS_SQL','CREATE VIRTUAL TABLE page_fts USING unavailable_fts_module(text)')
    lib=NativeDocumentLibrary(tmp_path/'fallback',autostart=False)
    d=upload(lib);lib.run_pending()
    assert lib.original(d['id']).exists()
    assert len(lib.search('LU Factorization'))==2
    assert not lib.search('eigen')


def test_powerpoint_formatted_runs_preserve_word_boundaries(lib):
    source=BytesIO(pptx_bytes());out=BytesIO()
    with ZipFile(source) as old,ZipFile(out,'w') as new:
        for name in old.namelist():
            raw=old.read(name)
            if name=='ppt/slides/slide2.xml':
                raw=raw.replace(b'<a:t>Eigenvalues and LU Factorization</a:t>',b'<a:t>Eigen</a:t></a:r><a:r><a:t>values and LU Factorization</a:t>')
            new.writestr(name,raw)
    d=upload(lib,'Formatted.pptx',out.getvalue());lib.run_pending()
    assert lib.search('Eigenvalues',document_id=d['id'])[0]['position']==1


def test_disable_purges_live_fts_segments(lib):
    import fitz
    pdf=fitz.open();p=pdf.new_page();p.insert_text((30,60),'confidentialcanaryvalue')
    d=upload(lib,raw=pdf.tobytes());lib.run_pending()
    assert lib.search('confidentialcanaryvalue')
    lib.set_indexing(d['id'],False)
    with sqlite3.connect(lib.database) as con:
        assert not any(b'confidentialcanaryvalue' in bytes(row[0]) for row in con.execute('SELECT block FROM page_fts_data'))


def test_pdf_cumulative_decode_budget_keeps_original(lib,monkeypatch):
    from pypdf.generic import DecodedStreamObject,NameObject
    import personal_learning_assistant.services.native_document_extraction as module
    monkeypatch.setattr(module,'MAX_DECODED_TOTAL',500_000,raising=False)
    writer=PdfWriter()
    for _ in range(3):
        page=writer.add_blank_page(width=200,height=200)
        stream=DecodedStreamObject();stream.set_data(b' '*300_000)
        page[NameObject('/Contents')]=writer._add_object(stream.flate_encode())
    out=BytesIO();writer.write(out);raw=out.getvalue()
    d=upload(lib,'Resource-limited.pdf',raw);lib.run_pending()
    assert lib.get(d['id'])['status']=='failed'
    assert lib.original(d['id']).read_bytes()==raw
