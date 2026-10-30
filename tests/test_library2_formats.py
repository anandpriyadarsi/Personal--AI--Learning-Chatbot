"""Passive format storage and native resolver contracts, real image/OOXML fixtures."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import hashlib
import pytest
from PIL import Image
from pypdf import PdfWriter
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary,LibraryError,resolve_android_document


def originals():
    writer=PdfWriter();writer.add_blank_page(width=100,height=100);out=BytesIO();writer.write(out)
    result={'pdf':out.getvalue()}
    out=BytesIO()
    with ZipFile(out,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Paragraph fact 47</w:t></w:r></w:p></w:body></w:document>')
    result['docx']=out.getvalue()
    for kind,fmt in [('png','PNG'),('jpg','JPEG'),('jpeg','JPEG'),('webp','WEBP')]:
        out=BytesIO();Image.new('RGB',(8,8),(0,80,120)).save(out,format=fmt);result[kind]=out.getvalue()
    for kind in ['txt','md','csv','py']:result[kind]=b'Safe passive text,47\n'
    return result


EXPECTED={'pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp',
          'txt':'text/plain','md':'text/markdown','csv':'text/csv','py':'text/plain'}


@pytest.mark.parametrize('kind',list(EXPECTED))
def test_actual_original_bytes_mime_and_rename_reach_native_resolver(tmp_path,kind):
    lib=NativeDocumentLibrary(tmp_path/'data/native_library',autostart=False)
    try:
        raw=originals()[kind];doc=lib.upload(BytesIO(raw),'Lecture.'+kind,indexing=False)
        lib.update(doc['id'],display_name='Renamed गणित')
        path,mime,name=resolve_android_document(tmp_path,doc['id'])
        assert mime==EXPECTED[kind] and name=='Renamed गणित.'+kind
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()
    finally:lib.close()


def test_python_file_is_never_executed_and_image_extraction_is_truthful(tmp_path):
    lib=NativeDocumentLibrary(tmp_path/'data/native_library',autostart=False)
    marker=tmp_path/'must-not-exist'
    try:
        raw=('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")').encode()
        code=lib.upload(BytesIO(raw),'lab.py');image=lib.upload(BytesIO(originals()['png']),'diagram.png')
        lib.run_pending()
        assert not marker.exists()
        assert lib.get(code['id'])['status']=='ready'
        assert lib.get(image['id'])['status']=='unavailable' and lib.original(image['id']).exists()
        for name,payload in [('app.apk',b'PK\x03\x04'),('page.html',b'<script>'),('bad.docx',b'PK\x03\x04bad')]:
            with pytest.raises(LibraryError):lib.upload(BytesIO(payload),name)
    finally:lib.close()


def test_failed_fsync_never_loses_an_existing_original(tmp_path,monkeypatch):
    lib=NativeDocumentLibrary(tmp_path/'data/native_library',autostart=False)
    try:
        doc=lib.upload(BytesIO(b'Existing original'),'saved.txt',indexing=False)
        import personal_learning_assistant.services.native_document_library as module
        def full(_):raise OSError('No space left on device')
        monkeypatch.setattr(module.os,'fsync',full)
        with pytest.raises(OSError):lib.upload(BytesIO(b'New original'),'new.txt')
        assert lib.original(doc['id']).read_bytes()==b'Existing original'
        assert lib.list_documents()['total']==1
        assert not list((lib.root/'tmp').iterdir())
    finally:lib.close()
