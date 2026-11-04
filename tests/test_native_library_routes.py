from io import BytesIO
import pytest
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from test_native_document_library import pdf_bytes, pptx_bytes


@pytest.fixture
def app(tmp_path):
    lib = NativeDocumentLibrary(tmp_path/'library', autostart=False)
    return create_app({'TESTING':True, 'NATIVE_LIBRARY_SERVICE':lib,
        'NATIVE_LIBRARY_CATALOGUE_FACTORY':lambda:{'available':True,'courses':[{'id':'ma103','code':'MA103N','name':'Linear Algebra','semester':'Semester 1','topics':[{'name':'Eigenvalues'}]}]}})


def token(app):
    return {'X-Library-CSRF':app.extensions['native_library_csrf'], 'Origin':'http://localhost'}


def test_original_upload_search_open_rename_move_and_download(app):
    c=app.test_client(); raw=pdf_bytes()
    response=c.post('/library/files/upload',data={'file':(BytesIO(raw),'Lecture.pdf'),'subject_id':'ma103','indexing':'true'},headers=token(app))
    assert response.status_code==201
    doc=response.json['document']; lib=app.config['NATIVE_LIBRARY_SERVICE']; lib.run_pending()
    results=c.get('/library/files/search?q=Eigenvalues&subject_id=ma103').json['matches']
    assert sorted(h['position'] for h in results)==[1,2]
    assert c.get(results[1]['open_url']).status_code==200
    original=c.get(f"/library/files/{doc['id']}/original?download=1")
    assert original.data==raw and 'attachment;' in original.headers['Content-Disposition']
    assert original.headers['Cache-Control']=='no-store'
    assert c.patch(f"/library/files/{doc['id']}",json={'display_name':'My matrices'},headers=token(app)).status_code==200
    folder=c.post('/library/files/folders',json={'name':'Semester 1'},headers=token(app)).json
    assert c.patch(f"/library/files/{doc['id']}",json={'folder_id':folder['id']},headers=token(app)).status_code==200
    assert c.get('/library/files?folder_id='+folder['id']).status_code==200
    assert c.get(f"/library/files/{doc['id']}/original").data==raw
    assert not list(lib.root.rglob('*.txt'))


def test_actions_require_same_origin_token_and_delete_confirmation(app):
    c=app.test_client(); lib=app.config['NATIVE_LIBRARY_SERVICE']
    d=lib.upload(BytesIO(pdf_bytes()),'Doc.pdf')
    for headers in ({},{**token(app),'Origin':'https://evil.test'},{**token(app),'Sec-Fetch-Site':'cross-site'}):
        assert c.delete('/library/files/'+d['id'],json={'confirm':True},headers=headers).status_code==403
    assert c.delete('/library/files/'+d['id'],json={},headers=token(app)).status_code==400
    assert c.delete('/library/files/'+d['id'],json={'confirm':True},headers=token(app)).status_code==200
    assert c.get('/library/files/'+d['id']+'/original').status_code==404


def test_disabled_searchable_status_and_metadata_only_search(app):
    c=app.test_client(); lib=app.config['NATIVE_LIBRARY_SERVICE']
    d=lib.upload(BytesIO(pdf_bytes()),'Matrices.pdf'); lib.run_pending()
    assert c.post('/library/files/'+d['id']+'/index',json={'enabled':False},headers=token(app)).status_code==200
    assert not c.get('/library/files/search?q=Eigenvalues').json['matches']
    assert c.get('/library/files/search?q=Matrices').json['matches'][0]['id']==d['id']
    page=c.get('/library/files').get_data(as_text=True)
    assert 'Matrices.pdf' in page and 'Tutor processing off' in page


def test_hostile_names_unknown_subject_and_bad_queries(app):
    c=app.test_client(); lib=app.config['NATIVE_LIBRARY_SERVICE']
    lib.upload(BytesIO(pdf_bytes()),'<script>.pdf')
    text=c.get('/library/files').get_data(as_text=True)
    assert '<script>.pdf' not in text and '&lt;script&gt;.pdf' in text
    assert c.get('/library/files?page=bad').status_code==400
    assert c.get('/library/files/search?q='+('a'*501)).status_code==400
    response=c.post('/library/files/upload',data={'file':(BytesIO(pdf_bytes()),'X.pdf'),'subject_id':'unknown'},headers=token(app))
    assert response.status_code==400


def test_powerpoint_viewer_truthful_and_studio_handoff_explicit(app):
    c=app.test_client(); lib=app.config['NATIVE_LIBRARY_SERVICE']
    d=lib.upload(BytesIO(pptx_bytes()),'Slides.pptx'); lib.run_pending()
    text=c.get(f"/library/files/{d['id']}/open?position=1").get_data(as_text=True)
    assert 'Slide 1' in text and 'external' in text.lower()
    text=c.get(f"/library/files/{d['id']}/learning").get_data(as_text=True)
    assert 'authored' in text.lower() and '/learning/import' in text
    assert lib.original(d['id']).exists()


def test_browse_and_status_complete_while_indexer_is_busy(app,monkeypatch):
    from threading import Event,Thread
    lib=app.config['NATIVE_LIBRARY_SERVICE'];doc=lib.upload(BytesIO(pdf_bytes()),'Async.pdf')
    entered=Event();release=Event();extract=lib._extract
    def blocked(d):
        entered.set();release.wait(5);return extract(d)
    monkeypatch.setattr(lib,'_extract',blocked)
    worker=Thread(target=lib.run_pending);worker.start();assert entered.wait(2)
    try:
        c=app.test_client()
        assert c.get('/library/files').status_code==200
        assert c.get('/library/files/status?ids='+doc['id']).json['documents'][0]['status']=='indexing'
        assert c.get('/library/files/'+doc['id']+'/original').data.startswith(b'%PDF')
    finally:release.set();worker.join(5)
    assert not worker.is_alive()


def test_default_open_and_separate_menu_actions_preserve_bytes_and_current_name(app):
    c=app.test_client();lib=app.config['NATIVE_LIBRARY_SERVICE']
    raw=pdf_bytes();doc=lib.upload(BytesIO(raw),'Original.pdf',indexing=False)
    identity=doc['id'];base=f'/library/files/{identity}'
    assert c.patch(base,json={'display_name':'My lecture'},headers=token(app)).status_code==200
    metadata=c.get(base).json['document']
    assert metadata['open_url']==base+'/original?native_action=view'
    assert metadata['open_with_url']==base+'/original?native_action=open_with'
    assert metadata['filename']=='My lecture.pdf'
    html=c.get('/library/files').get_data(as_text=True)
    assert f'<a href="/library/files/{identity}/open?position=1">My lecture</a>' in html
    for name in ['Open with…','Rename','Move','Favorite','Details','Export original','Copy','Move to Trash']:
        assert f'>{name}</' in html
    assert 'Prepare supported content for Tutor on this device' in html
    assert 'no cloud service' in html
    response=c.get(base+'/original?native_action=view')
    assert response.data==raw and 'My lecture.pdf' in response.headers['Content-Disposition']
    assert lib.get(identity)['status']=='disabled'


def test_upload_requires_explicit_content_indexing(app):
    c=app.test_client()
    doc=c.post('/library/files/upload',data={'file':(BytesIO(pdf_bytes()),'Plain.pdf')},headers=token(app)).json['document']
    assert doc['indexing_enabled']==0 and doc['status']=='disabled'


def test_future_configured_terms_and_type_filtered_search_use_actual_courses(app):
    app.config['NATIVE_LIBRARY_CATALOGUE_FACTORY']=lambda:{'courses':[
        {'id':'actual-term2-course','code':'CS201','name':'Algorithms','semester':'Semester 2 First Year'}]}
    from personal_learning_assistant.ui.web.native_library import synchronize_academic_folders
    synchronize_academic_folders(app.config['NATIVE_LIBRARY_SERVICE'],app.config['NATIVE_LIBRARY_CATALOGUE_FACTORY']()['courses'])
    client=app.test_client();body=client.get('/library/files').get_data(as_text=True)
    assert 'Semester 2' in body and '>Semester 1<' not in body
    lib=app.config['NATIVE_LIBRARY_SERVICE']
    lib.upload(BytesIO(b'lesson content'),'lesson.txt',indexing=False)
    lib.upload(BytesIO(pdf_bytes()),'lesson.pdf',indexing=False)
    body=client.get('/library/files?q=lesson&kind=txt').get_data(as_text=True)
    assert 'lesson.txt' in body and 'lesson.pdf' not in body


def test_canonical_writer_contention_does_not_block_web_library_navigation(tmp_path,monkeypatch):
    import sqlite3
    from threading import Event,Thread
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    directory=tmp_path/'data';directory.mkdir()
    database=directory/'learning_assistant.db';apply_migrations(database)
    lib=NativeDocumentLibrary(directory/'native_library',autostart=False)
    lib.configure_tutor(database,directory/'retrieval')
    doc=lib.upload(BytesIO(b'Unique local evidence remains available.'),'fact.txt')
    web=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,
                    'NATIVE_LIBRARY_CATALOGUE_FACTORY':lambda:{'courses':[]}})
    entered=Event();read_done=Event();errors=[]
    publish=lib._publish_native
    def publishing(record,pages):
        entered.set()
        return publish(record,pages)
    monkeypatch.setattr(lib,'_publish_native',publishing)
    held=sqlite3.connect(database,isolation_level=None);held.execute('BEGIN IMMEDIATE')
    worker=Thread(target=lib.run_pending)
    reader=None
    try:
        worker.start();assert entered.wait(3)
        def navigate():
            try:
                client=web.test_client()
                assert client.get('/library/files').status_code==200
                assert client.get('/library/files/'+doc['id']+'/original').data==b'Unique local evidence remains available.'
            except Exception as error:errors.append(str(error))
            finally:read_done.set()
        reader=Thread(target=navigate);reader.start()
        assert read_done.wait(2),'Canonical writer contention blocked unrelated Library navigation'
        assert not errors
    finally:
        held.rollback();held.close();worker.join(8)
        if reader is not None:reader.join(8)
        lib.close()
    assert not worker.is_alive()
    assert lib.get(doc['id'])['tutor_state']=='ready'


def test_disable_after_canonical_write_cannot_publish_late_native_generation(tmp_path,monkeypatch):
    import sqlite3
    from threading import Event,Thread
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
    directory=tmp_path/'data';directory.mkdir()
    database=directory/'learning_assistant.db';apply_migrations(database)
    lib=NativeDocumentLibrary(directory/'native_library',autostart=False)
    lib.configure_tutor(database,directory/'retrieval')
    doc=lib.upload(BytesIO(b'Only the old generation contains Zirconium47.'),'fact.txt')
    committed=Event();release=Event();publish=lib._publish_native;first=[True]
    def pause_after_commit(record,pages):
        source=publish(record,pages)
        if first[0]:
            first[0]=False;committed.set();assert release.wait(8)
        return source
    monkeypatch.setattr(lib,'_publish_native',pause_after_commit)
    worker=Thread(target=lib.run_pending);worker.start()
    try:
        assert committed.wait(3)
        lib.set_indexing(doc['id'],False)
        with sqlite3.connect(database) as con:
            assert not SQLiteRetrievalSourceRepository(con).active_records()
    finally:
        release.set();worker.join(8);lib.close()
    assert not worker.is_alive()
    with sqlite3.connect(database) as con:
        assert not SQLiteRetrievalSourceRepository(con).active_records()
    assert lib.get(doc['id'])['tutor_state']=='disabled'
    assert lib.original(doc['id']).read_bytes()==b'Only the old generation contains Zirconium47.'
