from contextlib import closing
from io import BytesIO
import json
import sqlite3
import pytest
from test_multimodal_jobs import owners,image_bytes,records
from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
from personal_learning_assistant.services.tutor_session_service import TutorSessionService
from personal_learning_assistant.domain.tutor_models import TutorSessionSpec,TutorProviderResponse


def prepared(owners):
    lib,db=owners;doc=lib.upload(BytesIO(image_bytes()),'matrix.png')
    svc=MultimodalEvidenceService(lib);r=svc.preview(doc['id'],{'kind':'image'},method='review',text='The matrix has two rows and two columns.')
    svc.enqueue(doc['id'],r['token']);lib.run_pending();found=records(db)
    return doc,found[0]


def test_direct_selection_without_lexical_match_and_atomic_snapshot(owners):
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.services.source_citation_service import resolve_snapshot
    from personal_learning_assistant.services.multimodal_tutor import selected_hits
    lib,db=owners;doc,record=prepared(owners)
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        repo=SQLiteTutorRepository(con);sessions=TutorSessionService(repo)
        spec=TutorSessionSpec(mode='doubt',source_policy='source_only',title='Image question',metadata={
            'source_document_id':record['document_id'],'source_version_hash':doc['sha256'],
            'mm_selection':record['locator']['mm_locator'],'mm_source_ref':record['locator']})
        session=sessions.create_session(spec)
        direct=selected_hits(con,session);assert len(direct)==1
        class Retrieval:
            def search(self,*args,**kwargs):return ()
        class LocalProvider:
            local_only=True
            def complete(self,request):
                assert 'two rows' in str(request.messages)
                return TutorProviderResponse('The source describes two rows and two columns [S1].','local-test','fake')
        tutor=GroundedTutorService(tutor_session_service=sessions,retrieval_service=Retrieval(),provider=LocalProvider())
        result=tutor.answer(session.session_id,'What does this show?',request_id='image_request_0001')
        snap=con.execute('SELECT * FROM tutor_evidence_snapshots WHERE turn_id=?',(result.assistant_turn.turn_id,)).fetchone()
        assert snap is not None
        destination=resolve_snapshot(con,snap['id'],lib)
        assert destination['document_id']==doc['id'] and destination['locator']['kind']=='image'
        lib.update(doc['id'],display_name='Renamed')
        with pytest.raises(ValueError):resolve_snapshot(con,snap['id'],lib)


def test_provider_guard_blocks_indirect_disclosure_and_every_retry(owners):
    from personal_learning_assistant.services.multimodal_tutor import guarded_complete
    lib,db=owners;doc,record=prepared(owners)
    class Provider:
        api_url='https://example.invalid/v1/chat/completions';model='model'
        def complete(self,request):raise AssertionError('Unauthorized outbound call')
    from types import SimpleNamespace
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        repo=SQLiteTutorRepository(con);sessions=TutorSessionService(repo)
        session=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='test'))
        service=SimpleNamespace(tutor_session_service=sessions,provider=Provider())
        plan=SimpleNamespace(hits=[SimpleNamespace(locator=record['locator'])])
        request=SimpleNamespace(session_id=session.session_id)
        with pytest.raises(ValueError):guarded_complete(service,request,session,plan)
        with pytest.raises(ValueError):guarded_complete(service,request,session,plan)
        assert not con.execute('SELECT * FROM tutor_turns').fetchall()


def test_unknown_critical_symbols_request_clarification_without_provider(owners):
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    lib,db=owners;doc=lib.upload(BytesIO(image_bytes()),'ambiguous.png');svc=MultimodalEvidenceService(lib)
    r=svc.preview(doc['id'],{'kind':'image'},method='local');svc.enqueue(doc['id'],r['token']);lib.run_pending();record=records(db)[0]
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        sessions=TutorSessionService(SQLiteTutorRepository(con))
        session=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='unclear',metadata={
            'source_document_id':record['document_id'],'source_version_hash':doc['sha256'],'mm_selection':record['locator']['mm_locator'],'mm_source_ref':record['locator']}))
        class Retrieval:
            def search(self,*args,**kwargs):return ()
        class Provider:
            def complete(self,request):raise AssertionError('Unknown symbols must not reach a provider')
        result=GroundedTutorService(tutor_session_service=sessions,retrieval_service=Retrieval(),provider=Provider()).answer(session.session_id,'Find the inverse of this matrix')
        assert 'unclear' in result.assistant_turn.content.lower() or 'unknown' in result.assistant_turn.content.lower()
        assert result.assistant_turn.support_level=='insufficient'


def test_snapshot_rolls_back_with_exchange_failure(owners):
    lib,db=owners;doc,record=prepared(owners)
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        repo=SQLiteTutorRepository(con);sessions=TutorSessionService(repo)
        session=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='rollback'))
        from personal_learning_assistant.domain.tutor_models import TutorEvidence
        evidence=TutorEvidence(chunk_id=record['chunk_id'],document_id=record['document_id'],ordinal=1,citation_label='S1')
        with pytest.raises(RuntimeError):
            with repo.atomic_exchange(session.session_id):
                sessions.add_user_turn(session.session_id,'Question')
                sessions.add_assistant_turn(session.session_id,'Answer [S1]',support_level='grounded',evidence=(evidence,))
                raise RuntimeError('synthetic persistence failure')
        assert con.execute('SELECT count(*) FROM tutor_evidence_snapshots').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM tutor_turns').fetchone()[0]==0


def test_selected_session_cannot_follow_new_artifact_generation(owners):
    from personal_learning_assistant.services.multimodal_tutor import selected_hits
    from types import SimpleNamespace
    lib,db=owners;doc,record=prepared(owners)
    session=SimpleNamespace(course_id=None,metadata={'source_document_id':record['document_id'],'mm_selection':record['locator']['mm_locator'],'mm_source_ref':record['locator']})
    with closing(sqlite3.connect(db)) as con:
        assert selected_hits(con,session)[0].text.startswith('The matrix')
        svc=MultimodalEvidenceService(lib);p=svc.preview(doc['id'],{'kind':'image'},method='review',text='Changed interpretation')
        svc.enqueue(doc['id'],p['token']);lib.run_pending()
        with pytest.raises(ValueError):selected_hits(con,session)


def test_unknown_paid_answer_replay_cannot_dispatch_again(owners,monkeypatch):
    from personal_learning_assistant.services.multimodal_tutor import guarded_complete,disclosure_scope,provider_identity
    from personal_learning_assistant.services.provider_permission_service import PermissionGuard
    from personal_learning_assistant.domain.tutor_models import TutorProviderRequest
    from types import SimpleNamespace
    lib,db=owners;doc,record=prepared(owners)
    monkeypatch.setenv('ANVAYA_MM_MONTHLY_MICROS','100');monkeypatch.setenv('ANVAYA_MM_ANSWER_MAX_MICROS','20')
    calls=[]
    class Provider:
        api_url='https://example.invalid/v1/chat/completions';model='test'
        def complete(self,request):calls.append(1);raise TimeoutError('lost response')
    with closing(sqlite3.connect(db,isolation_level=None)) as con:
        sessions=TutorSessionService(SQLiteTutorRepository(con));session=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',title='request'))
        plan=SimpleNamespace(hits=[SimpleNamespace(locator=record['locator'])]);scope=disclosure_scope(con,session,plan)
        receipt=PermissionGuard(lib.database).grant(scope,provider_identity(Provider()),'answer',max_cost_micros=20)
        sessions.update_session_metadata(session.session_id,{'mm_answer_permission':receipt});session=sessions.repository.get_session(session.session_id)
        service=SimpleNamespace(tutor_session_service=sessions,provider=Provider())
        request=TutorProviderRequest(session_id=session.session_id,mode='doubt',source_policy='source_only',messages=({'role':'user','content':'explain this'},))
        for _ in range(2):
            with pytest.raises(ValueError):guarded_complete(service,request,session,plan)
        assert len(calls)==1


def test_selected_lecture_adds_only_ready_overlapping_supplied_frames(owners):
    from personal_learning_assistant.services.multimodal_tutor import selected_hits
    from types import SimpleNamespace
    lib,db=owners;s=MultimodalEvidenceService(lib)
    transcript=lib.upload(BytesIO(b'WEBVTT\n\n00:01.000 --> 00:04.000\nSwap the rows.'),'lecture.vtt')
    image=lib.upload(BytesIO(image_bytes()),'board.png')
    p=s.preview(image['id'],{'kind':'image'},method='review',text='The board shows a row swap.')
    s.enqueue(image['id'],p['token']);lib.run_pending()
    manifest=s.create_manifest(transcript['id'],[{'document_id':image['id'],'timestamp_ms':2000}])
    transcript_record=next(r for r in records(db) if r['locator']['native_document_id']==transcript['id'])
    session=SimpleNamespace(course_id=None,metadata={'source_document_id':transcript_record['document_id'],
        'mm_selection':transcript_record['locator']['mm_locator'],'mm_source_ref':transcript_record['locator'],'mm_manifest_id':manifest})
    with closing(sqlite3.connect(db)) as con:
        hits=selected_hits(con,session)
        assert len(hits)==2 and any('board' in hit.text for hit in hits)
        lib.update(image['id'],display_name='new scope')
        with pytest.raises(ValueError):selected_hits(con,session)
