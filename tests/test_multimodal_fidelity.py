from contextlib import closing
from io import BytesIO
import json
import sqlite3
import pytest
from test_multimodal_jobs import owners,image_bytes,records


@pytest.mark.parametrize('text',[
    'Matrix [[1,?],[0,2]]; entry unknown',
    'Matrix [[1,0/O],[0,2]]; entry unclear',
    'Expression 1/l is ambiguous', 'Matrix sign +/- is unknown',
    'Fraction denominator illegible', 'Superscript unknown', 'Matrix final row missing',
    'Matrix [[1,+/-],[0,2]]', 'x^? + 2', 'Fraction 1/?',
])
def test_approval_cannot_resolve_explicit_critical_ambiguity(text):
    from personal_learning_assistant.services.multimodal_fidelity import assess_reading
    result=assess_reading(text,origin='user_transcription',declared_uncertain=[],review_complete=True)
    assert result['status']=='unknown' and result['uncertain']
    assert result['origin']=='user_transcription'


@pytest.mark.parametrize('text',['print("?")','What does this matrix show?',
    'Matrix [[1,-1],[0,2]]','x = "0/O?"','Why is the rank two?'])
def test_clean_code_and_prose_question_marks_remain_usable(text):
    from personal_learning_assistant.services.multimodal_fidelity import assess_reading
    result=assess_reading(text,origin='user_transcription',declared_uncertain=[],review_complete=True)
    assert result['status']=='observed' and result['uncertain']==[]


def test_structured_unresolved_spans_always_survive():
    from personal_learning_assistant.services.multimodal_fidelity import assess_reading
    result=assess_reading('Matrix [[1,0],[0,2]]',origin='user_transcription',declared_uncertain=['Entry (1,2): 0 or O'],review_complete=True)
    assert result['status']=='unknown' and 'Entry (1,2)' in result['uncertain'][0]


def test_incomplete_user_review_cannot_be_presented_as_resolved():
    from personal_learning_assistant.services.multimodal_fidelity import assess_reading
    result=assess_reading('Matrix [[1,-1],[0,2]]',origin='user_transcription',declared_uncertain=[],review_complete=False)
    assert result['status']=='unknown' and not result['review_complete']


def test_inconsistent_vision_cannot_erase_uncertainty():
    from personal_learning_assistant.tutor.vision_provider import validate_result
    result=validate_result({'text':'Matrix [[1,?],[0,2]]','uncertain':[]})
    assert result['uncertain']


def test_review_scope_binds_completion_spans_and_stale_edits(owners):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    lib,db=owners;doc=lib.upload(BytesIO(image_bytes()),'Unclear matrix.png');svc=MultimodalEvidenceService(lib)
    review=svc.preview(doc['id'],{'kind':'image'},method='review',text='Matrix [[1,?],[0,2]]',review_complete=False,declared_uncertain=['Entry (1,2)'])
    assert review['scope']['review_complete'] is False
    assert review['scope']['declared_uncertain']==['Entry (1,2)']
    svc.enqueue(doc['id'],review['token']);lib.run_pending();record=records(db)[0]
    assert record['locator']['mm_status']=='unknown'
    assert record['locator']['mm_kind']=='user_transcription'
    assert '?' in record['text'] and record['locator']['mm_uncertain']
    # A corrected reading is a new recipe/source generation; no old row rewrite.
    corrected=svc.preview(doc['id'],{'kind':'image'},method='review',text='Matrix [[1,-1],[0,2]]',review_complete=True)
    svc.enqueue(doc['id'],corrected['token']);lib.run_pending()
    assert records(db)[0]['locator']['mm_status']=='observed'
    with lib.connection() as con:assert con.execute('SELECT count(*) FROM mm_artifacts').fetchone()[0]==2


@pytest.mark.parametrize('coding',[False,True])
def test_unclear_review_never_dispatches_in_standard_or_coding(owners,coding):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    lib,db=owners;doc=lib.upload(BytesIO(image_bytes()),'Ambiguous.png');svc=MultimodalEvidenceService(lib)
    r=svc.preview(doc['id'],{'kind':'image'},method='review',text='Matrix [[1,?],[0,2]]; entry unknown')
    svc.enqueue(doc['id'],r['token']);lib.run_pending();record=records(db)[0]
    class Retrieval:
        def search(self,*args,**kwargs):return ()
    class Provider:
        def complete(self,request):raise AssertionError('Unresolved source reached provider')
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        repo=SQLiteTutorRepository(con);sessions=TutorSessionService(repo)
        session=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='Unclear',metadata={'source_document_id':record['document_id'],'source_version_hash':doc['sha256'],'mm_selection':record['locator']['mm_locator'],'mm_source_ref':record['locator']}))
        tutor=GroundedTutorService(tutor_session_service=sessions,retrieval_service=Retrieval(),provider=Provider())
        if coding:
            with repo.atomic_exchange(session.session_id):
                result=tutor.answer_coding(session.session_id,{'topic':'matrix','message':'Compute inverse','action':'explain'},history=(),task_context={},validate_sources=lambda ids:ids,persist_context=lambda *args:None)
            answer=repo.get_turn(result['assistant_turn_id'])
        else:answer=tutor.answer(session.session_id,'Compute inverse').assistant_turn
        assert answer.support_level=='insufficient' and 'unclear' in answer.content.lower()
        assert '[S1]' in answer.content
