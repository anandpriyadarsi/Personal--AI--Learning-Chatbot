from io import BytesIO
import sqlite3
import pytest
from test_multimodal_jobs import owners,image_bytes
from personal_learning_assistant.ui.web import create_app


@pytest.fixture
def app(owners):
    lib,db=owners
    return create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,
                      'NATIVE_LIBRARY_CATALOGUE_FACTORY':lambda:{'available':True,'courses':[]}})


def headers(app):return {'X-Library-CSRF':app.extensions['native_library_csrf'],'Origin':'http://localhost'}


def test_protected_review_queue_status_and_tutor_handoff(app,owners):
    lib,db=owners;doc=lib.upload(BytesIO(image_bytes()),'Matrix.png');c=app.test_client()
    base='/library/files/'+doc['id']+'/multimodal'
    assert c.post(base+'/preview',json={'locator':{'kind':'image'},'method':'review','text':'Two rows'}).status_code==403
    preview=c.post(base+'/preview',json={'locator':{'kind':'image'},'method':'review','text':'Two rows'},headers=headers(app))
    assert preview.status_code==200
    assert c.post(base+'/jobs',json={'token':preview.json['token']},headers=headers(app)).status_code==202
    lib.run_pending()
    assert c.get(base+'/status').json['state']=='ready'
    handoff=c.post(base+'/ask',json={'locator':{'kind':'image'}},headers=headers(app))
    assert handoff.status_code==201 and handoff.json['url'].startswith('/agent/sessions/')
    view=c.get('/library/files/'+doc['id']+'/open').get_data(as_text=True)
    assert 'Ask about this page/image' in view


def test_lecture_route_preserves_exact_cue_and_safe_frame(app,owners):
    lib,db=owners;c=app.test_client()
    transcript=lib.upload(BytesIO(b'WEBVTT\n\n00:01.000 --> 00:04.500\nSwap rows.'),'a.vtt')
    frame=lib.upload(BytesIO(image_bytes()),'frame.png',indexing=False)
    created=c.post('/library/lecture-manifests',json={'transcript_id':transcript['id'],'frames':[{'document_id':frame['id'],'timestamp_ms':2000}],'reference':''},headers=headers(app))
    assert created.status_code==201
    page=c.get(created.json['url']+'?timestamp_ms=2000')
    assert page.status_code==200 and b'1000' in page.data and b'4500' in page.data
