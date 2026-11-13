from contextlib import closing
from io import BytesIO
import hashlib
import sqlite3
import pytest
from PIL import Image
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.multimodal_schema import activate
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository


def image_bytes():
    stream=BytesIO();Image.new('RGB',(120,80),'white').save(stream,format='PNG');return stream.getvalue()


@pytest.fixture
def owners(tmp_path,monkeypatch):
    monkeypatch.setenv('ANVAYA_MULTIMODAL_ENABLED','true')
    db=tmp_path/'data/learning_assistant.db';db.parent.mkdir();apply_migrations(db)
    lib=NativeDocumentLibrary(db.parent/'native_library',autostart=False)
    lib.configure_tutor(db,db.parent/'tutor_retrieval');activate(db,lib.root,apply=True)
    yield lib,db
    lib.close()


def records(db):
    with closing(sqlite3.connect(db)) as con:return SQLiteRetrievalSourceRepository(con).active_records()


def test_image_review_queue_exact_locator_original_unchanged(owners):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    lib,db=owners;raw=image_bytes();doc=lib.upload(BytesIO(raw),'matrix.png',subject_id='math')
    svc=MultimodalEvidenceService(lib)
    review=svc.preview(doc['id'],{'kind':'image'},method='review',text='Matrix [[1,-1],[0,2]]')
    svc.enqueue(doc['id'],review['token']);lib.run_pending()
    found=records(db);assert len(found)==1
    assert found[0]['locator']['mm_locator']['kind']=='image'
    assert found[0]['locator']['mm_kind']=='user_transcription'
    assert lib.original(doc['id']).read_bytes()==raw
    assert svc.status(doc['id'])['state']=='ready'
    # Changed source invalidates review token, even if bytes are shared.
    review=svc.preview(doc['id'],{'kind':'image'},method='review',text='a')
    lib.update(doc['id'],display_name='renamed')
    with pytest.raises(ValueError):svc.enqueue(doc['id'],review['token'])


def test_cancellation_fences_publication_and_off_flag_hides_evidence(owners,monkeypatch):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    lib,db=owners;doc=lib.upload(BytesIO(image_bytes()),'a.png');svc=MultimodalEvidenceService(lib)
    rev=svc.preview(doc['id'],{'kind':'image'},method='review',text='test')
    svc.enqueue(doc['id'],rev['token']);svc.cancel(doc['id']);lib.run_pending()
    assert not records(db)
    rev=svc.preview(doc['id'],{'kind':'image'},method='review',text='test')
    svc.enqueue(doc['id'],rev['token']);lib.run_pending();assert records(db)
    monkeypatch.setenv('ANVAYA_MULTIMODAL_ENABLED','false');assert not records(db)


def test_transcript_manifest_and_temporal_selection(owners):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    lib,db=owners;svc=MultimodalEvidenceService(lib)
    transcript=lib.upload(BytesIO(b'WEBVTT\n\n00:01.250 --> 00:03.500\nPivot the rows.\n\n00:05.000 --> 00:08.000\nSubtract row one.'),'lecture.vtt',subject_id='math')
    frame=lib.upload(BytesIO(image_bytes()),'board.png',subject_id='math',indexing=False)
    manifest=svc.create_manifest(transcript['id'],[{'document_id':frame['id'],'timestamp_ms':2000}],reference='https://www.youtube.com/watch?v=abcdefghijk')
    lib.run_pending();found=records(db)
    assert found[0]['locator']['timestamp_start_ms']==1250
    assert found[0]['locator']['timestamp_end_ms']==3500
    assert svc.temporal(manifest,2000)['cue']['start_ms']==1250
    assert svc.temporal(manifest,2000)['frames'][0]['timestamp_ms']==2000
    with pytest.raises(ValueError):svc.temporal(manifest,9000)
    with pytest.raises(ValueError):svc.create_manifest(transcript['id'],[],reference='file:///etc/passwd')


def test_pptx_uses_presentation_relationship_order():
    from test_native_document_library import pptx_bytes
    from personal_learning_assistant.ingestion.extractors import PPTXExtractor
    units=PPTXExtractor().extract(pptx_bytes(),source_name='slides.pptx')
    assert units[0].slide_number==1 and 'Eigenvalues' in units[0].text


def test_rename_or_flag_off_cannot_republish_visual_text_as_legacy(owners,monkeypatch):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    lib,db=owners;doc=lib.upload(BytesIO(image_bytes()),'private.png');s=MultimodalEvidenceService(lib)
    p=s.preview(doc['id'],{'kind':'image'},method='review',text='private extracted matrix')
    s.enqueue(doc['id'],p['token']);lib.run_pending();assert records(db)
    lib.update(doc['id'],display_name='rename');lib.run_pending()
    assert not records(db)
    monkeypatch.setenv('ANVAYA_MULTIMODAL_ENABLED','false');lib.rebuild(doc['id']);lib.run_pending()
    assert not records(db)


def test_pdf_crop_excludes_off_scope_text_in_local_inspection(owners):
    import fitz
    from personal_learning_assistant.services.multimodal_process_runner import inspect_original
    lib,db=owners;pdf=fitz.open();page=pdf.new_page(width=400,height=400)
    page.insert_text((20,40),'SELECTED MATRIX');page.insert_text((20,350),'PRIVATE OFF CROP')
    doc=lib.upload(BytesIO(pdf.tobytes()),'crop.pdf');pdf.close()
    result=inspect_original(lib.original(doc['id']),'pdf',{'kind':'pdf_page','page':1,'bbox':[0,0,1,.4]})
    assert 'SELECTED' in result['text'] and 'PRIVATE' not in result['text']
