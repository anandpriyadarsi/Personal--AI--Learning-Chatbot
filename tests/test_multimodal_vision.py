from io import BytesIO
import json
import sqlite3
import pytest
from test_multimodal_jobs import owners,image_bytes,records
from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService


def test_structured_vision_unknown_symbols_and_no_retry_on_timeout(owners,monkeypatch):
    from personal_learning_assistant.tutor.vision_provider import VisionProvider
    lib,db=owners;monkeypatch.setenv('ANVAYA_MM_VISION_MODEL','test-model');monkeypatch.setenv('ANVAYA_MM_VISION_MAX_MICROS','20');monkeypatch.setenv('ANVAYA_MM_MONTHLY_MICROS','100')
    svc=MultimodalEvidenceService(lib);doc=lib.upload(BytesIO(image_bytes()),'unclear.png')
    called=[]
    def analyze(self,image):
        called.append(image)
        return {'text':'Matrix [[1,?],[0,2]]','uncertain':['Entry (1,2) may be -1 or +1.'],'kind':'vision_transcription'}
    monkeypatch.setattr(VisionProvider,'analyze',analyze)
    preview=svc.preview(doc['id'],{'kind':'image'},method='vision')
    assert preview['cost_upper_bound_micros']==20 and 'provider' in preview
    svc.enqueue(doc['id'],preview['token']);lib.run_pending()
    assert len(called)==1 and called[0].startswith('data:image/png;base64,')
    assert records(db)[0]['locator']['mm_status']=='unknown'
    # Replay must not call the provider again after cached publication.
    lib.run_pending();assert len(called)==1
    second=lib.upload(BytesIO(image_bytes()),'timeout.png',duplicate='copy')
    def timeout(self,image):called.append(image);raise TimeoutError('secret upstream detail')
    monkeypatch.setattr(VisionProvider,'analyze',timeout)
    p=svc.preview(second['id'],{'kind':'image'},method='vision');svc.enqueue(second['id'],p['token']);lib.run_pending()
    assert len(called)==2
    # Re-running same generation after an unknown outcome fails closed.
    with lib.connection(write=True) as con:
        con.execute("UPDATE processing_jobs SET state='pending' WHERE document_id=? AND state='failed'",(second['id'],))
        con.execute("UPDATE documents SET status='stored' WHERE id=?",(second['id'],))
    lib.run_pending();assert len(called)==2
    assert 'secret' not in json.dumps(svc.status(second['id']))


def test_vision_result_schema_rejects_confidence_and_instructions():
    from personal_learning_assistant.tutor.vision_provider import validate_result
    with pytest.raises(ValueError):validate_result({'text':'x','uncertain':[],'confidence':.99})
    with pytest.raises(ValueError):validate_result({'text':'x','uncertain':'none'})
    assert validate_result({'text':'x','uncertain':[]})['kind']=='vision_transcription'
