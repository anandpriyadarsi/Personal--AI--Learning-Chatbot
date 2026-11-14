from contextlib import closing
from io import BytesIO
import sqlite3
from types import SimpleNamespace
import pytest
from test_multimodal_jobs import owners,image_bytes,records
from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService


def lecture_selection(owners,count,*,unread=False,text=None):
    lib,db=owners;svc=MultimodalEvidenceService(lib)
    transcript=lib.upload(BytesIO(b'WEBVTT\n\n00:12.500 --> 00:18.000\nPerform the shown row operation.'),'Lecture.vtt')
    frames=[]
    for i in range(count):
        doc=lib.upload(BytesIO(image_bytes()),f'Board {i+1}.png',duplicate='copy',indexing=False)
        if not unread:
            review=svc.preview(doc['id'],{'kind':'image'},method='review',review_complete=True,text=text or f'Matrix [[1,{i}],[0,2]]')
            svc.enqueue(doc['id'],review['token'])
        frames.append(dict(document_id=doc['id'],timestamp_ms=13000+i*100))
    lib.run_pending();manifest=svc.create_manifest(transcript['id'],frames)
    record=next(r for r in records(db) if r['locator']['native_document_id']==transcript['id'])
    session=SimpleNamespace(course_id=None,metadata={'source_document_id':record['document_id'],'source_version_hash':transcript['sha256'],'mm_selection':record['locator']['mm_locator'],'mm_source_ref':record['locator'],'mm_manifest_id':manifest})
    return session,frames


@pytest.mark.parametrize('count',[0,1,9,10,11,20])
def test_frame_limit_is_honest_and_immutable(owners,count):
    from personal_learning_assistant.services.multimodal_tutor import select_evidence
    lib,db=owners;session,frames=lecture_selection(owners,count)
    with closing(sqlite3.connect(db)) as con:selection=select_evidence(con,session)
    assert selection.coverage.selected_frame_count==count
    assert selection.coverage.selected_cue_count==1
    assert len(selection.hits)<=10
    assert selection.coverage.requires_narrowing==(count>=10)
    assert sum(reason=='hit_limit' for _,reason in selection.coverage.excluded)==max(0,count-9)
    assert selection.coverage.complete==(count<10)
    with pytest.raises((AttributeError,TypeError)):selection.coverage.complete=True


def test_unread_frames_disclosed_instead_of_board_understanding(owners):
    from personal_learning_assistant.services.multimodal_tutor import select_evidence
    lib,db=owners;session,frames=lecture_selection(owners,2,unread=True)
    with closing(sqlite3.connect(db)) as con:selection=select_evidence(con,session)
    assert len(selection.hits)==1
    assert sum(reason=='unread' for _,reason in selection.coverage.excluded)==2
    assert not selection.coverage.complete


def test_atomic_matrix_exceeding_context_is_not_sliced(owners):
    from personal_learning_assistant.services.multimodal_tutor import select_evidence
    lib,db=owners;session,_=lecture_selection(owners,1,text='Matrix ['+'1,'*6500+'2]')
    with closing(sqlite3.connect(db)) as con:selection=select_evidence(con,session,max_chars=12000)
    assert selection.coverage.requires_narrowing
    assert any(reason=='context_budget' for _,reason in selection.coverage.excluded)
    assert not any('Matrix [' in h.text for h in selection.hits)


def test_uncertain_late_frame_is_checked_before_bound_drops_it(owners):
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    lib,db=owners;session,frames=lecture_selection(owners,11,text='Matrix [[1,?],[0,2]]')
    class Retrieval:
        def search(self,*args,**kwargs):return ()
    class Provider:
        def complete(self,request):raise AssertionError('Incomplete selection dispatched')
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        sessions=TutorSessionService(SQLiteTutorRepository(con))
        actual=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='Lecture',metadata=session.metadata))
        result=GroundedTutorService(tutor_session_service=sessions,retrieval_service=Retrieval(),provider=Provider()).answer(actual.session_id,'Compute the matrix rank')
        assert result.assistant_turn.support_level=='insufficient'
        assert 'unclear' in result.assistant_turn.content.lower()
        assert '[S2]' in result.assistant_turn.content


def test_capped_clear_frames_require_narrowing_without_dispatch(owners):
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    lib,db=owners;session,_=lecture_selection(owners,11)
    class Retrieval:
        def search(self,*args,**kwargs):return ()
    class Provider:
        def complete(self,request):raise AssertionError('Capped selection dispatched')
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        sessions=TutorSessionService(SQLiteTutorRepository(con));s=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='Bounded',metadata=session.metadata))
        answer=GroundedTutorService(tutor_session_service=sessions,retrieval_service=Retrieval(),provider=Provider()).answer(s.session_id,'Explain every supplied frame').assistant_turn
        assert answer.support_level=='insufficient' and 'narrow' in answer.content.lower()


def test_transcript_does_not_establish_missing_board_content(owners):
    from personal_learning_assistant.services.multimodal_tutor import select_evidence
    from personal_learning_assistant.services.multimodal_fidelity import clarification_for_plan
    lib,db=owners;session,_=lecture_selection(owners,0)
    with closing(sqlite3.connect(db)) as con:selection=select_evidence(con,session)
    plan=SimpleNamespace(hits=selection.hits,evidence_selection=selection,question='Explain the matrix shown on the board')
    assert 'not visible' in clarification_for_plan(plan)


def test_plain_text_context_keeps_existing_truncation_semantics():
    from personal_learning_assistant.retrieval.rag_context import assemble_context
    from personal_learning_assistant.domain.retrieval_models import RetrievalHit
    hit=RetrievalHit(chunk_id='plain',document_id='plain-doc',text='a'*16000,score=1,lexical_rank=None,semantic_rank=None,page_number=None,locator={},resource_ids=(),course_ids=(),topic_ids=(),providers=())
    context=assemble_context('explain',(hit,),max_chars=12000)
    assert context.total_characters==12000 and len(context.hits)==1


@pytest.mark.parametrize('mixed',[False,True])
@pytest.mark.parametrize('question',['Explain the selected evidence and point out anything uncertain.','Compute the matrix rank'])
def test_unread_selected_frames_block_dispatch_even_without_visual_keywords(owners,mixed,question):
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    lib,db=owners;session,frames=lecture_selection(owners,2,unread=True)
    if mixed:
        # Manifest review predates the processed frame, so rebind a fresh exact
        # manifest rather than bypassing its generation fence.
        svc=MultimodalEvidenceService(lib)
        p=svc.preview(frames[0]['document_id'],{'kind':'image'},method='review',review_complete=True,text='Matrix [[1,2],[0,1]]')
        svc.enqueue(frames[0]['document_id'],p['token']);lib.run_pending()
        transcript=next(r for r in records(db) if r['document_id']==session.metadata['source_document_id'])
        session.metadata['mm_manifest_id']=svc.create_manifest(transcript['locator']['native_document_id'],frames)
    class Retrieval:
        def search(self,*args,**kwargs):return ()
    class Provider:
        def complete(self,request):raise AssertionError('Unread selected frame was ignored before dispatch')
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        sessions=TutorSessionService(SQLiteTutorRepository(con));s=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='Unread',metadata=session.metadata))
        answer=GroundedTutorService(tutor_session_service=sessions,retrieval_service=Retrieval(),provider=Provider()).answer(s.session_id,question).assistant_turn
        assert answer.support_level=='insufficient' and 'unread' in answer.content.lower()
