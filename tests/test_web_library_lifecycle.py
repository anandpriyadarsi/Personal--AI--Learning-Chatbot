"""Explicit web startup, read-only migration boundary and streamed recovery."""
from io import BytesIO
from pathlib import Path
import sqlite3
import pytest
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.ui.web.native_library import initialize_library
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def test_generic_factory_and_get_never_create_or_migrate_storage(tmp_path):
    root=tmp_path/'untouched'
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_ROOT':root})
    response=app.test_client().get('/library/files')
    assert response.status_code==503
    assert not root.exists()


def test_explicit_startup_projects_real_terms_and_get_is_idempotent(tmp_path):
    db=tmp_path/'data/learning_assistant.db';db.parent.mkdir();apply_migrations(db)
    cat={'courses':[{'id':'actual-course','code':'UC100N','name':'Data Science and AI','semester':'Semester 1','academic_year':'2026–27'}]}
    app=create_app({'TESTING':True,'ACADEMIC_DATABASE_PATH':db,'NATIVE_LIBRARY_ROOT':db.parent/'native_library','NATIVE_LIBRARY_CATALOGUE_FACTORY':lambda:cat})
    lib=initialize_library(app)
    try:
        with lib.connection() as con:
            before=[tuple(r) for r in con.execute('SELECT * FROM folders ORDER BY id')]
            ledger=[tuple(r) for r in con.execute('SELECT * FROM migration_ledger ORDER BY operation_id')]
        for _ in range(3):assert app.test_client().get('/library/files').status_code==200
        with lib.connection() as con:
            assert [tuple(r) for r in con.execute('SELECT * FROM folders ORDER BY id')]==before
            assert [tuple(r) for r in con.execute('SELECT * FROM migration_ledger ORDER BY operation_id')]==ledger
        assert lib.semesters()[0]['year']=='2026–27'
        assert len(before)==2
    finally:lib.close()


def test_same_course_in_two_configured_years_has_distinct_enrollment_roots(tmp_path):
    lib=NativeDocumentLibrary(tmp_path/'library',autostart=False)
    try:
        course=[{'id':'same-id','code':'UC100N','name':'Data Science and AI'}]
        a=lib.bootstrap_academics(course,number=1,year='2026–27')
        b=lib.bootstrap_academics(course,number=1,year='2027–28')
        assert a['semester']['id']!=b['semester']['id']
        assert a['subjects'][0]['folder_id']!=b['subjects'][0]['folder_id']
        assert len(lib.semesters())==2
    finally:lib.close()


def test_visual_image_and_inert_code_reader_preserve_originals(tmp_path):
    from PIL import Image
    lib=NativeDocumentLibrary(tmp_path/'library',autostart=False)
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib})
    c=app.test_client()
    try:
        image=BytesIO();Image.new('RGB',(10,10),'red').save(image,format='PNG')
        d=lib.upload(BytesIO(image.getvalue()),'image.png',indexing=False)
        page=c.get('/library/files/'+d['id']+'/open').text
        assert 'class="original-image"' in page and '/original?' in page
        assert c.get('/library/files/'+d['id']+'/original').data==image.getvalue()
        code=b'print("<script>not executed</script>")'
        d=lib.upload(BytesIO(code),'program.py',indexing=False)
        page=c.get('/library/files/'+d['id']+'/open').text
        assert '<script>not executed</script>' not in page and '&lt;script&gt;' in page
        assert c.get('/library/files/'+d['id']+'/original').data==code
    finally:lib.close()


def test_web_backup_stream_and_staged_restore_reject_invalid_without_mutation(tmp_path):
    from personal_learning_assistant.android_backup import apply_pending_restore
    lib=NativeDocumentLibrary(tmp_path/'data/native_library',autostart=False)
    doc=lib.upload(BytesIO(b'Irreplaceable notes'),'notes.txt',indexing=False)
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'LOCAL_DATA_ROOT':tmp_path})
    c=app.test_client();csrf=app.extensions['native_library_csrf']
    try:
        response=c.get('/library/backup/export')
        assert response.status_code==200 and response.is_streamed
        raw=response.data;response.close()
        assert c.post('/library/backup/restore',data={'backup':(BytesIO(raw),'backup.zip')}).status_code==403
        assert c.post('/library/backup/restore',data={'csrf_token':csrf,'backup':(BytesIO(b'bad'),'bad.zip')}).status_code==400
        assert lib.original(doc['id']).read_bytes()==b'Irreplaceable notes'
        response=c.post('/library/backup/restore',data={'csrf_token':csrf,'backup':(BytesIO(raw),'backup.zip')})
        assert response.status_code==200 and 'staged' in response.text
        assert lib.original(doc['id']).read_bytes()==b'Irreplaceable notes'
    finally:lib.close()
    assert apply_pending_restore(tmp_path)
    restored=NativeDocumentLibrary(tmp_path/'data/native_library',autostart=False)
    try:assert restored.original(doc['id']).read_bytes()==b'Irreplaceable notes'
    finally:restored.close()


def test_explicit_web_library_mode_uses_one_primary_entry_and_legacy_upload_adapter(tmp_path):
    lib=NativeDocumentLibrary(tmp_path/'library',autostart=False)
    try:
        app=create_app({'TESTING':True,'WEB_ORIGINAL_LIBRARY':True,'NATIVE_LIBRARY_SERVICE':lib})
        c=app.test_client()
        assert c.get('/library').location.endswith('/library/files')
        assert c.get('/library/upload').location.endswith('/library/files')
        assert c.get('/library',follow_redirects=True).status_code==200
    finally:lib.close()


def test_legacy_knowledge_opens_exact_registered_original_without_raw_text(tmp_path):
    import hashlib
    from personal_learning_assistant.services.knowledge_registry_service import KnowledgeRegistryService
    from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
    from personal_learning_assistant.services.knowledge_reader_service import KnowledgeReaderService
    from tests.learning_studio.test_multilecture_web import source_pdf
    db=tmp_path/'data/learning_assistant.db';db.parent.mkdir();apply_migrations(db)
    raw=source_pdf('Private synthetic fact must not leak in the Library reader.')
    digest=hashlib.sha256(raw).hexdigest();directory=db.parent/'documents';directory.mkdir();path=directory/(digest+'.pdf');path.write_bytes(raw)
    with sqlite3.connect(db) as con:
        con.row_factory=sqlite3.Row
        owner=KnowledgeRegistryService(SQLiteKnowledgeRegistryRepository(con))
        owner.register_document(kind='document',path_key='documents/'+path.name,content_hash=digest,mime_type='application/pdf',size_bytes=len(raw))
        source_id=con.execute('SELECT id FROM knowledge_documents').fetchone()[0]
    lib=NativeDocumentLibrary(db.parent/'native_library',autostart=False)
    try:
        reader=KnowledgeReaderService(database_path=db)
        app=create_app({'TESTING':True,'WEB_ORIGINAL_LIBRARY':True,'NATIVE_LIBRARY_SERVICE':lib,
            'KNOWLEDGE_READER_SERVICE_FACTORY':lambda:reader,'LEARNING_STUDIO_SOURCE_DATABASE':db,
            'LEARNING_STUDIO_SOURCE_ROOTS':{'documents':directory}})
        c=app.test_client();page=c.get('/knowledge/item/'+source_id)
        assert page.status_code==200
        assert 'knowledge-reader-chunk' not in page.text
        assert 'Open registered original' in page.text
        assert c.get('/library/registered/'+source_id+'/original').data==raw
        path.unlink()
        assert c.get('/library/registered/'+source_id+'/original').status_code==409
        with sqlite3.connect(db) as con:assert con.execute('SELECT content_hash FROM knowledge_documents WHERE id=?',(source_id,)).fetchone()[0]==digest
    finally:lib.close()


def test_failed_metadata_commit_cannot_report_upload_success_or_lose_original(tmp_path,monkeypatch):
    lib=NativeDocumentLibrary(tmp_path/'library',autostart=False)
    old=lib.upload(BytesIO(b'Keep this original'),'old.txt',indexing=False)
    try:
        def no_space(*args):raise sqlite3.OperationalError('database or disk is full')
        monkeypatch.setattr(lib,'_enqueue_publication',no_space)
        with pytest.raises(sqlite3.OperationalError):lib.upload(BytesIO(b'Interrupted new original'),'new.txt',indexing=False)
        assert lib.original(old['id']).read_bytes()==b'Keep this original'
        assert [d['id'] for d in lib.list_documents()['items']]==[old['id']]
    finally:lib.close()


def test_enospc_during_backup_keeps_previous_verified_export(tmp_path,monkeypatch):
    from personal_learning_assistant import android_backup as backup
    import errno
    data=tmp_path/'data';data.mkdir();(data/'notes.txt').write_text('Keep all academic records')
    target=tmp_path/'last-good.zip';backup.export_backup_file(tmp_path,destination=target);previous=target.read_bytes()
    def no_space(*args,**kwargs):raise OSError(errno.ENOSPC,'No space left on device')
    monkeypatch.setattr(backup,'_copy',no_space)
    with pytest.raises(OSError):backup.export_backup_file(tmp_path,destination=target)
    assert target.read_bytes()==previous
    assert (data/'notes.txt').read_text()=='Keep all academic records'
