"""Thin local protected routes. No migration or provider call on reads."""
from contextlib import closing
import json
import sqlite3
from urllib.parse import urlsplit
from flask import Blueprint,abort,current_app,jsonify,render_template,request,send_file,url_for
from .native_library import service,protect,payload
from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService,enabled
from personal_learning_assistant.domain.multimodal_models import validate_locator,canonical

multimodal=Blueprint('multimodal',__name__)


def svc():
    if urlsplit(request.host_url).hostname not in ('localhost','127.0.0.1','::1'):abort(403)
    result=MultimodalEvidenceService(service());result.check();return result


def database():
    path=getattr(service(),'_tutor_database',None)
    if not path or not path.is_file():raise ValueError('Existing academic owner is unavailable')
    return path


@multimodal.post('/library/files/<document_id>/multimodal/preview')
@protect
def preview(document_id):
    d=payload({'locator','method','text'})
    return jsonify(svc().preview(document_id,d.get('locator'),method=d.get('method','local'),text=d.get('text','')))


@multimodal.post('/library/files/<document_id>/multimodal/jobs')
@protect
def jobs(document_id):
    return jsonify(svc().enqueue(document_id,payload({'token'}).get('token',''))),202


@multimodal.get('/library/files/<document_id>/multimodal/status')
@protect
def status(document_id):return jsonify(svc().status(document_id))


@multimodal.post('/library/files/<document_id>/multimodal/cancel')
@protect
def cancel(document_id):
    payload(set());return jsonify(svc().cancel(document_id))


@multimodal.post('/library/files/<document_id>/multimodal/ask')
@protect
def ask(document_id):
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    from personal_learning_assistant.services.multimodal_tutor import selected_hits
    from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
    data=payload({'locator','manifest_id'});loc=validate_locator(data.get('locator'));s=svc();doc=s.lib.get(document_id)
    with closing(sqlite3.connect(database(),isolation_level=None)) as con:
        records=[r for r in SQLiteRetrievalSourceRepository(con).active_records() if r['locator'].get('native_document_id')==document_id]
        if not records:raise ValueError('Selected evidence is not ready for Tutor')
        r=records[0];repo=SQLiteTutorRepository(con);sessions=TutorSessionService(repo)
        from types import SimpleNamespace
        course_id=r['course_ids'][0] if len(r['course_ids'])==1 else None
        metadata={'source_document_id':r['document_id'],'source_version_hash':doc['sha256'],
                  'mm_selection':loc,'origin':'multimodal',
                  'prefill_question':'Explain the selected evidence and point out anything uncertain.'}
        if data.get('manifest_id'):metadata['mm_manifest_id']=data['manifest_id']
        direct=selected_hits(con,SimpleNamespace(metadata=metadata,course_id=course_id),allow_unbound=True)
        metadata['mm_source_ref']=dict(direct[0].locator)
        session=sessions.create_session(TutorSessionSpec(mode='doubt',source_policy='source_only',
            course_id=course_id,title='Ask ANVAYA · '+doc['display_name'],metadata=metadata))
    return jsonify(url=url_for('web.academic_agent_session',session_id=session.session_id)),201


@multimodal.post('/library/lecture-manifests')
@protect
def manifest():
    d=payload({'transcript_id','frames','reference'})
    identity=svc().create_manifest(d.get('transcript_id'),d.get('frames',[]),reference=d.get('reference',''))
    return jsonify(id=identity,url=url_for('multimodal.lecture',manifest_id=identity)),201


@multimodal.get('/library/lecture-manifests/<manifest_id>')
@protect
def lecture(manifest_id):
    result=svc().temporal(manifest_id,int(request.args.get('timestamp_ms',0)))
    return render_template('multimodal_lecture.html',lecture=result,manifest_id=manifest_id,
                           csrf_token=current_app.extensions['native_library_csrf'])


@multimodal.get('/sources/evidence/<snapshot_id>')
@protect
def evidence(snapshot_id):
    from personal_learning_assistant.services.source_citation_service import resolve_snapshot
    try:
        with closing(sqlite3.connect(database())) as con:
            con.row_factory=sqlite3.Row;result=resolve_snapshot(con,snapshot_id,service())
        return render_template('multimodal_citation.html',evidence=result,snapshot_id=snapshot_id)
    except ValueError:
        return render_template('multimodal_citation.html',evidence=None,snapshot_id=snapshot_id),410


@multimodal.get('/sources/evidence/<snapshot_id>/original')
@protect
def evidence_original(snapshot_id):
    from personal_learning_assistant.services.source_citation_service import resolve_snapshot
    with closing(sqlite3.connect(database())) as con:
        con.row_factory=sqlite3.Row;result=resolve_snapshot(con,snapshot_id,service())
    doc=service().get(result['document_id'])
    response=send_file(service().original(doc['id']),mimetype=doc['mime'],conditional=True)
    response.headers['Content-Security-Policy']='sandbox'
    return response


@multimodal.post('/agent/sessions/<session_id>/multimodal/answer-preview')
@protect
def answer_preview(session_id):
    from .routes import _academic_agent_service
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.services.multimodal_tutor import disclosure_scope,provider_identity
    import os
    question=payload({'question'}).get('question','Explain the selected source')
    s=svc();web=_academic_agent_service();provider=web._provider()
    with closing(sqlite3.connect(database(),isolation_level=None)) as con:
        sessions=TutorSessionService(SQLiteTutorRepository(con));session=sessions.repository.get_session(session_id)
        retrieval,store=web._retrieval()
        try:
            plan=GroundedTutorService(tutor_session_service=sessions,retrieval_service=retrieval,provider=provider).preview(session_id,question)
            scope=disclosure_scope(con,session,plan)
        finally:
            if store and hasattr(store,'close'):store.close()
    if not scope:raise ValueError('No selected multimodal evidence')
    identity=provider_identity(provider);cost=int(os.getenv('ANVAYA_MM_ANSWER_MAX_MICROS','0'))
    if cost<=0:raise ValueError('Set a conservative provider cost bound before cloud answering')
    token=s.signer.dumps(dict(session_id=session_id,scope=scope,provider=identity,cost=cost,purpose='answer'))
    from personal_learning_assistant.domain.multimodal_models import location_label
    labels=[s.lib.get(item['source']['document_id'])['display_name']+' · '+location_label(item['locator']) for item in scope['sources']]
    return jsonify(token=token,scope=scope,sources=labels,provider=identity,cost_upper_bound_micros=cost,
        disclosure='Selected evidence text and conversation history will be sent. Provider retention rules apply; store=false does not promise zero retention.')


@multimodal.post('/agent/sessions/<session_id>/multimodal/answer-consent')
@protect
def answer_consent(session_id):
    from itsdangerous import BadSignature
    from personal_learning_assistant.services.provider_permission_service import PermissionGuard
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.services.multimodal_tutor import selected_hits,disclosure_scope,provider_identity
    from types import SimpleNamespace
    from .routes import _academic_agent_service
    s=svc()
    try:review=s.signer.loads(payload({'token'}).get('token',''),max_age=600)
    except BadSignature:raise ValueError('Review expired') from None
    if review['session_id']!=session_id or review['purpose']!='answer':raise ValueError('Review scope mismatch')
    if provider_identity(_academic_agent_service()._provider())!=review['provider']:raise ValueError('Provider changed; review again')
    with closing(sqlite3.connect(database(),isolation_level=None)) as con:
        repo=SQLiteTutorRepository(con);sessions=TutorSessionService(repo);session=repo.get_session(session_id)
        scope=disclosure_scope(con,session,SimpleNamespace(hits=selected_hits(con,session)))
        if scope!=review['scope']:raise ValueError('Source changed; review again')
        receipt=PermissionGuard(s.lib.database).grant(scope,review['provider'],'answer',max_cost_micros=review['cost'])
        sessions.update_session_metadata(session_id,dict(session.metadata,mm_answer_permission=receipt))
    return jsonify(permission_id=receipt)


@multimodal.post('/library/multimodal/permissions/<permission_id>/revoke')
@protect
def revoke(permission_id):
    from personal_learning_assistant.services.provider_permission_service import PermissionGuard
    payload(set());s=svc();PermissionGuard(s.lib.database).revoke(permission_id)
    with s.lib.connection() as con:
        pending=[r[0] for r in con.execute('SELECT document_id FROM mm_selections WHERE permission_id=?',(permission_id,))]
    for identity in pending:s.cancel(identity)
    # Existing in-flight response checks the revisioned receipt before publish.
    return jsonify(revoked=True,disclosure='Future calls blocked. Already transmitted data cannot be recalled.')


@multimodal.after_request
def private(response):
    response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
    return response


def register_multimodal(app):
    @app.context_processor
    def flags():return {'multimodal_enabled':enabled(),'native_library_csrf':app.extensions.get('native_library_csrf','')}
    app.register_blueprint(multimodal)
