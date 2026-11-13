"""Displayed pixels and extracted text must represent the same immutable region."""
from io import BytesIO
import base64
import hashlib
import pytest
import fitz
from PIL import Image
from personal_learning_assistant.services.multimodal_process_runner import inspect_original
from test_multimodal_jobs import owners,records
from test_multimodal_web import app


@pytest.mark.parametrize('rotation,box,label',[
    (0,[0,0,.5,.25],'TOP_LEFT_SECRET'),
    (90,[0,0,.25,.5],'BOTTOM_LEFT_SELECTED'),
    (180,[.5,0,1,.25],'BOTTOM_LEFT_SELECTED'),
    (270,[.75,.5,1,1],'BOTTOM_LEFT_SELECTED'),
])
@pytest.mark.parametrize('cropped',[False,True])
def test_display_crop_text_and_pixels_agree(tmp_path,rotation,box,label,cropped):
    pdf=fitz.open();p=pdf.new_page(width=400,height=600)
    p.insert_text((40,70),'TOP_LEFT_SECRET')
    p.insert_text((40,520),'BOTTOM_LEFT_SELECTED')
    # Red and blue region patches let the test inspect rendered pixels too.
    p.draw_rect(fitz.Rect(25,20,35,30),color=(1,0,0),fill=(1,0,0))
    p.draw_rect(fitz.Rect(25,540,35,550),color=(0,0,1),fill=(0,0,1))
    if cropped:p.set_cropbox(fitz.Rect(10,10,390,590))
    p.set_rotation(rotation);path=tmp_path/'rotated.pdf';pdf.save(path);pdf.close()
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    result=inspect_original(path,'pdf',{'kind':'pdf_page','page':1,'bbox':box})
    assert label in result['text']
    other='BOTTOM_LEFT_SELECTED' if label=='TOP_LEFT_SECRET' else 'TOP_LEFT_SECRET'
    assert other not in result['text']
    image=Image.open(BytesIO(base64.b64decode(result['image'].split(',')[1]))).convert('RGB')
    pixels=list(image.get_flattened_data());channel=0 if label=='TOP_LEFT_SECRET' else 2
    assert any(c[channel]>200 and c[(channel+1)%3]<70 and c[(channel+2)%3]<70 for c in pixels)
    assert not any(c[2-channel]>200 and c[1]<70 and c[channel]<70 for c in pixels)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('box',[[0,0,1,1],[0,0,.001,.001],[.999,.999,1,1]])
def test_crop_helper_bounds(tmp_path,box):
    from personal_learning_assistant.services.multimodal_process_runner import display_crop_to_pdf_clip
    pdf=fitz.open();page=pdf.new_page();page.set_rotation(90)
    rect=display_crop_to_pdf_clip(page,box)
    assert not rect.is_empty and not rect.is_infinite


@pytest.mark.parametrize('box',[[0,0,float('nan'),1],[-.1,0,1,1],[0,0,0,1],[True,0,1,1]])
def test_crop_helper_rejects_invalid_bounds(box):
    from personal_learning_assistant.services.multimodal_process_runner import display_crop_to_pdf_clip
    pdf=fitz.open();page=pdf.new_page()
    with pytest.raises(ValueError):display_crop_to_pdf_clip(page,box)


def test_exif_display_orientation_is_applied_once(tmp_path):
    image=Image.new('RGB',(80,120),'white')
    for x in range(80):
        for y in range(90,120):image.putpixel((x,y),(0,0,255))
    exif=image.getexif();exif[274]=6
    path=tmp_path/'oriented.jpg';image.save(path,exif=exif)
    result=inspect_original(path,'jpg',{'kind':'image','bbox':[0,0,.25,1]})
    crop=Image.open(BytesIO(base64.b64decode(result['image'].split(',')[1]))).convert('RGB')
    assert crop.width==30 and crop.height==80
    assert crop.getpixel((10,40))[2]>200


def test_pdf_citation_displays_exact_retained_crop_and_rejects_rename(app,owners):
    import sqlite3
    from contextlib import closing
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec,TutorEvidence
    lib,db=owners
    pdf=fitz.open();p=pdf.new_page(width=400,height=600);p.insert_text((40,520),'BOTTOM_LEFT_SELECTED');p.set_rotation(90)
    raw=pdf.tobytes();pdf.close();doc=lib.upload(BytesIO(raw),'Rotated.pdf')
    svc=MultimodalEvidenceService(lib)
    review=svc.preview(doc['id'],{'kind':'pdf_page','page':1,'bbox':[0,0,.25,.5]})
    svc.enqueue(doc['id'],review['token']);lib.run_pending();record=records(db)[0]
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        repo=SQLiteTutorRepository(con);sessions=TutorSessionService(repo)
        session=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='Exact crop'))
        with repo.atomic_exchange(session.session_id):
            sessions.add_user_turn(session.session_id,'Explain this')
            sessions.add_assistant_turn(session.session_id,'Selected reading [S1]',support_level='grounded',evidence=(TutorEvidence(chunk_id=record['chunk_id'],document_id=record['document_id'],ordinal=1,citation_label='S1'),))
        snapshot=con.execute('SELECT id FROM tutor_evidence_snapshots').fetchone()[0]
    client=app.test_client();url='/sources/evidence/'+snapshot
    view=client.get(url)
    assert b'Exact retained PDF page' in view.data and b'Selected crop boundary' in view.data
    assert b'Return to selected page' in view.data
    rendered=client.get(url+'/preview.png')
    assert rendered.status_code==200 and rendered.mimetype=='image/png'
    assert lib.original(doc['id']).read_bytes()==raw
    lib.update(doc['id'],display_name='Renamed')
    assert client.get(url+'/preview.png').status_code in (400,410)
    assert client.get(url).status_code==410
