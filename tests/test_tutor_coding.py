"""Synthetic canonical owner: durable task/turn, policy and failure gates."""
from contextlib import contextmanager
import json
import sqlite3
from threading import Thread, Event
import pytest

from tests.test_phase7_5_academic_agent_web import build_test_web_service, open_database, FakeProvider, first_retrieval_hit
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.services.coding_activation import activate
from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
from personal_learning_assistant.services.tutor_coding_service import TutorCodingService
from personal_learning_assistant.domain.coding_models import CodingRequest, CodingError


class RecordingProvider(FakeProvider):
    def __init__(self):
        super().__init__(configured=True,response='General explanation (not from project sources)\n\nPredict the shape first.\n\n```python\nα = [1, 2]\nprint(α)\n```')
        self.requests=[]
    def complete(self,request):
        self.requests.append(request)
        return super().complete(request)


@pytest.fixture
def coding(tmp_path):
    provider=RecordingProvider()
    web,path,course,_,retrieval=build_test_web_service(tmp_path,provider=provider)
    activate(path)
    sid=web.create_session(course_id=course['id'],mode='free',source_policy='source_first',title='Synthetic Python practice',workspace='coding')
    app=create_app({'TESTING':True,'TUTOR_CODING_ENABLED':True,'ACADEMIC_AGENT_WEB_SERVICE_FACTORY':lambda:web})
    return app,web,path,course,provider,retrieval,sid


@contextmanager
def use(coding):
    _,web,path,*_=coding
    con=open_database(path)
    try:
        yield TutorCodingService(SQLiteTutorRepository(con),web)
    finally:
        con.close()


def make_task(svc,sid,**overrides):
    return svc.create(sid,{'request_id':'task-create-request-001','title':'Shape practice','template_id':'numpy-shapes','code':'  α = 1\n',**overrides})[0]


def approve(svc,sid,**query):
    preview=svc.source_preview(sid,**query)
    session=svc.repository.get_session(sid)
    state=session.metadata.get('coding_workspace_v1',{})
    return svc.consent(sid,{'expected_consent_revision':state.get('consent_revision',0),'review_token':preview['review_token'],**query})['consent_revision']


def ask_data(task,revision=1,**overrides):
    return {'request_id':'coding-send-request-001','expected_task_revision':task['revision'],'action':'predict',
            'topic':'NumPy shapes','message':'Help with this shape','code':'  α = [1,2]\n','attempt':'I predict shape (2,)',
            'source_consent_revision':revision,**overrides}


def dump_non_tutor(path):
    with open_database(path) as con:
        tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t:[tuple(r) for r in con.execute('SELECT * FROM "'+t+'"')] for t in tables if not t.startswith('tutor_')}


def test_restart_idempotency_and_data_preservation(coding):
    app,web,path,course,provider,retrieval,sid=coding
    before=dump_non_tutor(path)
    with use(coding) as svc:
        task=make_task(svc,sid)
        assert make_task(svc,sid)==task
        with pytest.raises(CodingError) as error: make_task(svc,sid,title='Different')
        assert error.value.status==409
        revision=approve(svc,sid)
        data=ask_data(task,revision)
        result=svc.ask(sid,task['id'],data)
    with use(coding) as restarted:
        replay=restarted.ask(sid,task['id'],data)
        assert replay['replayed'] and replay['assistant_turn_id']==result['assistant_turn_id']
        assert restarted.coding.task(sid,task['id'])['snapshot']['code']=='  α = 1\n'
        for changed in ({'code':'x=2'}, {'action':'hint'}, {'source_consent_revision':2}, {'full_solution':True,'action':'debug'}):
            with pytest.raises(CodingError) as error: restarted.ask(sid,task['id'],dict(data,**changed))
            assert error.value.status==409
    assert len(provider.requests)==1
    assert len(web.session_view(sid)['turns'])==2
    assert dump_non_tutor(path)==before
    assert not any('SECRET_' in str(r) for r in provider.requests)


@pytest.mark.parametrize('field,value',[('context_token','signed-token'),('policy','full'),('surface','assessment'),('owner','/tmp/private'),('history',[]),('verified',True),('messages',[]),('expected_task_revision',True),('hint_level',True),('full_solution','true'),('full_solution',True),('code','x'*12001),('error','x'*3001)])
def test_request_dto_rejects_forged_and_oversized_fields(coding,field,value):
    *_,sid=coding
    with use(coding) as svc:
        task=make_task(svc,sid)
        with pytest.raises(CodingError): svc.ask(sid,task['id'],dict(ask_data(task),**{field:value}))
    assert not coding[4].requests


def test_unicode_byte_budget_does_not_truncate_current_code(coding):
    with use(coding) as svc:
        task=make_task(svc,coding[-1])
        with pytest.raises(CodingError) as error:
            CodingRequest.parse(ask_data(task,code='界'*12000))
        assert error.value.status==413
        data=CodingRequest.parse(ask_data(task,code='\n    α = 1\n')).data
        assert data['code']=='\n    α = 1\n'


@pytest.mark.parametrize('failure',['timeout','empty','malformed','quota'])
def test_provider_failure_is_atomic_and_redacted(coding,failure):
    app,web,path,course,provider,retrieval,sid=coding
    with use(coding) as svc:
        task=make_task(svc,sid);revision=approve(svc,sid)
    def fail(_):
        from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
        if failure=='empty': return TutorProviderResponse(content='',provider_name='fake',provider_model='fake')
        if failure=='malformed': return None
        raise RuntimeError('SECRET_PROVIDER_BODY_KEY_123')
    provider.complete=fail
    response=app.test_client().post(f'/agent/sessions/{sid}/coding/tasks/{task["id"]}/ask',json=ask_data(task,revision),headers={'X-CSRF-Token':app.extensions['tutor_action_csrf']})
    assert response.status_code==503
    assert 'SECRET_PROVIDER' not in response.text
    assert web.session_view(sid)['turns']==[]
    with open_database(path) as con:
        assert con.execute('SELECT COUNT(*) FROM tutor_coding_turn_context').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM tutor_coding_tasks').fetchone()[0]==1


def test_task_cas_archive_and_foreign_nested_ids(coding):
    _,web,_,course,provider,_,sid=coding
    other=web.create_session(course_id=course['id'],workspace='coding')
    with use(coding) as svc:
        task=make_task(svc,sid)
        for call in (lambda:svc.coding.task(other,task['id']),lambda:svc.edit(other,task['id'],{'expected_task_revision':1,'title':'forged'})):
            with pytest.raises(CodingError) as error: call()
            assert error.value.status==404
        updated=svc.edit(sid,task['id'],{'expected_task_revision':1,'code':'print(2)'})
        assert updated['revision']==2
        with pytest.raises(CodingError) as error: svc.edit(sid,task['id'],{'expected_task_revision':1,'code':'print(3)'})
        assert error.value.status==409
        svc.coding.update(sid,task['id'],2,archive=True)
        assert svc.coding.tasks(sid)==[]
        assert svc.coding.task(sid,task['id'],active=False)['archived_at']
    assert not provider.requests


def test_provider_wait_allows_reads_and_rejects_task_change(coding):
    _,web,path,course,provider,_,sid=coding
    entered,release=Event(),Event(); original=provider.complete
    def slow(request):
        entered.set();assert release.wait(10);return original(request)
    provider.complete=slow
    with use(coding) as svc:
        task=make_task(svc,sid);revision=approve(svc,sid)
    outcomes=[]
    def send():
        try:
            with use(coding) as svc: svc.ask(sid,task['id'],ask_data(task,revision))
        except Exception as exc: outcomes.append(exc)
    thread=Thread(target=send);thread.start()
    try:
        assert entered.wait(10)
        assert web.session_view(sid)['turns']==[]
        with use(coding) as svc:
            with pytest.raises(CodingError) as err: svc.ask(sid,task['id'],ask_data(task,revision))
            assert err.value.status==429
            svc.edit(sid,task['id'],{'expected_task_revision':1,'code':'changed'})
    finally:
        release.set();thread.join(15)
    assert len(outcomes)==1 and isinstance(outcomes[0],CodingError) and outcomes[0].status==409
    assert web.session_view(sid)['turns']==[]


def test_context_insert_failure_rolls_back_both_turns(coding,monkeypatch):
    with use(coding) as svc:
        sid=coding[-1];task=make_task(svc,sid);revision=approve(svc,sid)
        def fail(*args): raise sqlite3.IntegrityError('synthetic context failure')
        monkeypatch.setattr(svc.coding,'append_context',fail)
        with pytest.raises(sqlite3.IntegrityError): svc.ask(sid,task['id'],ask_data(task,revision))
    assert coding[1].session_view(sid)['turns']==[]


def test_history_excludes_full_solution_and_rebuild_context(coding):
    provider=coding[4];sid=coding[-1]
    with use(coding) as svc:
        task=make_task(svc,sid);revision=approve(svc,sid)
        provider.response='PRIOR_FULL_SOLUTION_SENTINEL'
        svc.ask(sid,task['id'],ask_data(task,revision,action='debug',full_solution=True))
        provider.response='One small hint only.'
        svc.ask(sid,task['id'],ask_data(task,revision,action='hint',request_id='coding-send-request-002'))
        assert 'PRIOR_FULL_SOLUTION_SENTINEL' not in str(provider.requests[-1].messages)
        svc.ask(sid,task['id'],ask_data(task,revision,action='rebuild',request_id='coding-send-request-003'))
        payload=json.loads(provider.requests[-1].messages[1]['content'])
        assert payload['previous_exchanges']=={}
    assert len(coding[1].session_view(sid)['turns'])==6


def test_json_routes_csrf_origin_host_and_unknown_fields(coding):
    app,*_=coding;sid=coding[-1];client=app.test_client();url=f'/agent/sessions/{sid}/workspace'
    headers={'X-CSRF-Token':app.extensions['tutor_action_csrf']}
    assert client.post(url,json={'workspace':'academic'}).status_code==403
    assert client.post(url,json={'workspace':'academic'},headers={**headers,'Origin':'https://evil.example'}).status_code==403
    assert client.post(url,json={'workspace':'academic'},headers={**headers,'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert client.post(url,json={'workspace':'academic'},headers={**headers,'Host':'evil.example'}).status_code==403
    assert client.post(url,json={'workspace':'academic','owner':'forged'},headers=headers).status_code==400
    assert client.post(url,json={'workspace':'academic'},headers=headers).status_code==200
    assert client.post(url,data={'csrf_token':app.extensions['tutor_action_csrf'],'workspace':'coding'}).status_code==303
    assert client.post(url,json={'workspace':'coding'},headers={**headers,'Origin':'http://localhost'}).status_code==200


def test_feature_off_and_missing_schema_never_migrate_on_get(tmp_path):
    web,path,course,provider,retrieval=build_test_web_service(tmp_path)
    sid=web.create_session(course_id=course['id'])
    app=create_app({'TESTING':True,'TUTOR_CODING_ENABLED':True,'ACADEMIC_AGENT_WEB_SERVICE_FACTORY':lambda:web})
    before=dump_non_tutor(path)
    assert app.test_client().get('/agent/sessions/'+sid).status_code==200
    assert 'needs activation' in app.test_client().get('/agent/sessions/'+sid).text
    with open_database(path) as con: assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_coding_tasks'").fetchone()
    assert dump_non_tutor(path)==before
    app.config['TUTOR_CODING_ENABLED']=False
    assert app.test_client().post(f'/agent/sessions/{sid}/workspace',json={'workspace':'coding'},headers={'X-CSRF-Token':app.extensions['tutor_action_csrf']}).status_code==503


def test_backup_first_activation_and_failure_rollback(tmp_path,monkeypatch):
    import personal_learning_assistant.services.coding_activation as module
    web,path,*_=build_test_web_service(tmp_path)
    before=dump_non_tutor(path)
    broken=tmp_path/'bad.sql';broken.write_text('CREATE TABLE tutor_coding_tasks(id TEXT);\nINVALID SQL;',encoding='utf-8')
    monkeypatch.setattr(module,'MIGRATION',broken)
    with pytest.raises(sqlite3.Error): module.activate(path)
    with open_database(path) as con: assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_coding_tasks'").fetchone()
    assert list(path.parent.glob(path.name+'.before-coding-*.bak'))
    assert dump_non_tutor(path)==before


def test_source_version_change_blocks_academic_and_coding(coding):
    app,web,path,course,provider,retrieval,_=coding
    with open_database(path) as con:
        hit=first_retrieval_hit(con)
        row=con.execute('SELECT content_hash FROM knowledge_documents WHERE id=?',(hit.document_id,)).fetchone()
    # Use source-owned canonical scope; explicit source session derives it.
    sid=web.create_source_session(document_id=hit.document_id,version_hash=row[0])
    with use(coding) as svc:
        svc.workspace(sid,'coding')
        retrieval.hits=(hit,)
        task=make_task(svc,sid);revision=approve(svc,sid)
    with open_database(path) as con:
        con.execute('UPDATE knowledge_documents SET content_hash=? WHERE id=?',('f'*64,hit.document_id))
    with use(coding) as svc:
        with pytest.raises(CodingError) as err: svc.ask(sid,task['id'],ask_data(task,revision))
        assert err.value.status==409
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebValidationError
    with pytest.raises(AcademicAgentWebValidationError): web.ask(sid,'Explain this source')
    assert not provider.requests


def test_notebook_route_is_inert_and_has_safe_headers(coding,tmp_path):
    app,web,path,course,provider,_,sid=coding
    sentinel=tmp_path/'must-not-exist'
    snippet=f'__import__("pathlib").Path({str(sentinel)!r}).write_text("executed")\n</script><img src=x onerror=alert(1)>'
    with use(coding) as svc:
        task=make_task(svc,sid,template_id='',title='../../secret',code=snippet)
    headers={'X-CSRF-Token':app.extensions['tutor_action_csrf']}
    response=app.test_client().post(f'/agent/sessions/{sid}/coding/tasks/{task["id"]}/notebook',json={'expected_task_revision':1,'template_id':'','include_student_code':True},headers=headers)
    assert response.status_code==200
    assert response.mimetype=='application/x-ipynb+json'
    assert response.headers['Cache-Control']=='no-store' and response.headers['X-Content-Type-Options']=='nosniff'
    assert '..' not in response.headers['Content-Disposition']
    notebook=json.loads(response.data)
    assert any(c['source']==snippet for c in notebook['cells'])
    assert not sentinel.exists() and not provider.requests


def test_source_changes_during_generation_cannot_commit(coding):
    app,web,path,course,provider,retrieval,_=coding
    with open_database(path) as con:
        hit=first_retrieval_hit(con)
        version=con.execute('SELECT content_hash FROM knowledge_documents WHERE id=?',(hit.document_id,)).fetchone()[0]
    sid=web.create_source_session(document_id=hit.document_id,version_hash=version)
    retrieval.hits=(hit,)
    original=provider.complete
    def replace(request):
        with open_database(path) as con:con.execute('UPDATE knowledge_documents SET content_hash=? WHERE id=?',('e'*64,hit.document_id))
        return original(request)
    with use(coding) as svc:
        svc.workspace(sid,'coding');task=make_task(svc,sid);revision=approve(svc,sid)
        provider.complete=replace
        with pytest.raises(CodingError) as err:svc.ask(sid,task['id'],ask_data(task,revision))
        assert err.value.status==409
    assert web.session_view(sid)['turns']==[]


@pytest.mark.parametrize('change',['trash','disable','move','missing','generation','metadata','same_hash_foreign'])
def test_native_identity_generation_placement_and_original_are_authoritative(coding,change):
    from io import BytesIO
    from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
    from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
    from personal_learning_assistant.domain.retrieval_models import RetrievalHit
    app,web,path,course,provider,retrieval,sid=coding
    lib=NativeDocumentLibrary(path.parent/'native_library',autostart=False)
    try:
        lib.configure_tutor(path,path.parent/'retrieval-native')
        doc=lib.upload(BytesIO(b'Synthetic NumPy shape reduction example.'),'practice.txt',subject_id=course['id'])
        lib.run_pending()
        def hit_for(doc_id):
            with open_database(path) as con:
                records=SQLiteRetrievalSourceRepository(con).active_records()
            record=next(r for r in records if r['locator'].get('native_document_id')==doc_id)
            return RetrievalHit(chunk_id=record['chunk_id'],document_id=record['document_id'],text=record['text'],score=.9,
                lexical_rank=1,semantic_rank=None,page_number=None,locator=record['locator'],resource_ids=(),course_ids=record['course_ids'],topic_ids=(),providers=())
        hit=hit_for(doc['id']);retrieval.hits=(hit,)
        with use(coding) as svc:
            task=make_task(svc,sid);revision=approve(svc,sid)
        if change=='trash':lib.trash(doc['id'])
        elif change=='disable':lib.set_indexing(doc['id'],False)
        elif change=='missing':lib.original(doc['id']).unlink()
        elif change=='same_hash_foreign':
            foreign=lib.upload(BytesIO(b'Synthetic NumPy shape reduction example.'),'foreign.txt',subject_id='foreign-course',duplicate='copy')
            lib.run_pending();retrieval.hits=(hit_for(foreign['id']),)
        else:
            with lib.connection(write=True) as con:
                if change=='move':con.execute("UPDATE documents SET subject_id='foreign-course' WHERE id=?",(doc['id'],))
                elif change=='generation':con.execute('UPDATE documents SET generation=generation+1 WHERE id=?',(doc['id'],))
                else:con.execute('UPDATE documents SET metadata_revision=metadata_revision+1 WHERE id=?',(doc['id'],))
        with use(coding) as svc:
            with pytest.raises(CodingError) as err:svc.ask(sid,task['id'],ask_data(task,revision))
            assert err.value.status==409
        assert not provider.requests
    finally:lib.close()


def test_bounded_history_200_turns_and_performance_samples(coding):
    import os
    from pathlib import Path
    from time import perf_counter
    from personal_learning_assistant.services.coding_notebooks import export_notebook
    app,web,path,course,provider,retrieval,sid=coding
    with use(coding) as svc:
        task=make_task(svc,sid,code='x'*12000);revision=approve(svc,sid)
        # Populate 200 persisted turns using Tutor's own exchange; no provider.
        for index in range(100):
            with svc.repository.atomic_exchange(sid):
                user=svc.sessions.add_user_turn(sid,'Synthetic attempt '+str(index))
                assistant=svc.sessions.add_assistant_turn(sid,'Context '*500,support_level='mixed')
                data=ask_data(task,revision,request_id=f'synthetic-history-{index:04d}')
                from personal_learning_assistant.domain.coding_models import digest
                svc.coding.append_context(task['id'],CodingRequest.parse(data).data,digest(data),[],user,assistant)
        history=svc.coding.history(task['id'])
        assert len(json.dumps(history))<=8100 and history['older_context_omitted']
        svc.ask(sid,task['id'],ask_data(task,revision,code='x'*12000))
        assert len(str(provider.requests[-1].messages))<40000
    client=app.test_client();headers={'X-CSRF-Token':app.extensions['tutor_action_csrf']}
    samples={'history_ms':[],'task_save_ms':[],'notebook_ms':[]}
    for index in range(30):
        start=perf_counter();response=client.get('/agent/sessions/'+sid);samples['history_ms'].append((perf_counter()-start)*1000)
        assert response.status_code==200
        start=perf_counter();response=client.post(f'/agent/sessions/{sid}/coding/tasks/{task["id"]}',json={'expected_task_revision':index+1,'code':'x'*12000},headers=headers);samples['task_save_ms'].append((perf_counter()-start)*1000)
        assert response.status_code==200
        start=perf_counter();export_notebook(response.json['task'],template_id='numpy-shapes');samples['notebook_ms'].append((perf_counter()-start)*1000)
    report={'samples':samples,'p95_ms':{k:sorted(v)[28] for k,v in samples.items()},'fixture':'200 synthetic turns, 12,000-character saved code; no provider time', 'sample_count':30}
    folder=os.environ.get('ANVAYA_WEB_RESULTS')
    if folder:
        Path(folder).mkdir(parents=True,exist_ok=True)
        (Path(folder)/'coding-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
