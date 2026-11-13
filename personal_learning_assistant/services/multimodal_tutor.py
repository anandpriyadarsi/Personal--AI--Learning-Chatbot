"""Direct location retrieval and disclosure guard for the existing Tutor."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import json
import os
import sqlite3
import uuid
from urllib.parse import urlparse
from personal_learning_assistant.domain.multimodal_models import canonical,source_ref,digest
from personal_learning_assistant.domain.retrieval_models import RetrievalHit
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
from .provider_permission_service import PermissionGuard
from .multimodal_evidence_service import enabled


def selected_hits(connection,session,*,allow_unbound=False):
    selected=session.metadata.get('mm_selection')
    if not selected:return ()
    if not enabled():raise ValueError('Multimodal Tutor is disabled; remove selected evidence to continue')
    wanted=session.metadata.get('source_document_id')
    hits=[]
    for r in SQLiteRetrievalSourceRepository(connection).active_records():
        if r['document_id']!=wanted:continue
        loc=r['locator'];actual=loc.get('mm_locator',{})
        bound=session.metadata.get('mm_source_ref')
        if not bound and not allow_unbound:raise ValueError('Exact selected source version unavailable; review and reselect')
        identity_fields=('native_document_id','content_hash','native_generation','metadata_revision','mm_artifact_id','mm_artifact_hash','mm_recipe')
        if bound and any(bound.get(k)!=loc.get(k) for k in identity_fields):raise ValueError('Selected source generation or artifact changed; review and reselect')
        if selected.get('kind')=='transcript_cue':
            if not(actual.get('kind')=='transcript_cue' and actual['start_ms']<selected['end_ms'] and actual['end_ms']>selected['start_ms']):continue
        elif actual!=selected:continue
        hits.append(RetrievalHit(chunk_id=r['chunk_id'],document_id=r['document_id'],text=r['text'],score=1,
            lexical_rank=None,semantic_rank=None,page_number=r['page_number'],locator=loc,resource_ids=r['resource_ids'],
            course_ids=r['course_ids'],topic_ids=r['topic_ids'],providers=r['providers']))
    if not hits:raise ValueError('Selected source/version/location is unavailable; review it again')
    if session.course_id and any(session.course_id not in h.course_ids for h in hits):raise ValueError('Selected evidence is outside the conversation course')
    manifest_id=session.metadata.get('mm_manifest_id')
    if manifest_id:
        root=_root(connection)
        from .native_document_library import _verified_original
        with closing(sqlite3.connect('file:'+str(root/'library.sqlite3')+'?mode=ro',uri=True)) as native:
            native.row_factory=sqlite3.Row
            manifest=native.execute('SELECT * FROM mm_lecture_manifests WHERE id=?',(manifest_id,)).fetchone()
            if not manifest:raise ValueError('Supplied frame manifest unavailable')
            transcript=native.execute('SELECT * FROM documents WHERE id=?',(manifest['transcript_id'],)).fetchone()
            if not transcript or source_ref(dict(transcript))!=json.loads(manifest['source_json']):raise ValueError('Lecture source version changed')
            if transcript['id']!=hits[0].locator['native_document_id']:raise ValueError('Manifest belongs to another source')
            for frame in json.loads(manifest['frames_json']):
                if not selected.get('start_ms',0)<=frame['timestamp_ms']<selected.get('end_ms',0):continue
                doc=native.execute('SELECT * FROM documents WHERE id=?',(frame['document_id'],)).fetchone()
                if not doc or doc['trashed_at'] or source_ref(dict(doc))!=frame['source']:raise ValueError('Supplied frame version changed')
                _verified_original(root,dict(doc))
                for r in SQLiteRetrievalSourceRepository(connection).active_records():
                    if r['locator'].get('native_document_id')!=frame['document_id'] or not r['locator'].get('mm_artifact_id'):continue
                    frame_locator=dict(r['locator'],mm_frame_pts_ms=frame['timestamp_ms'],mm_parent_manifest=manifest_id)
                    hits.append(RetrievalHit(chunk_id=r['chunk_id'],document_id=r['document_id'],text=r['text'],score=1,
                        lexical_rank=None,semantic_rank=None,page_number=None,locator=frame_locator,
                        resource_ids=r['resource_ids'],course_ids=r['course_ids'],topic_ids=r['topic_ids'],providers=r['providers']))
    return tuple(hits[:10])


def _root(connection):
    db=connection.execute('PRAGMA database_list').fetchone()[2]
    return Path(db).resolve().parent/'native_library'


def provider_identity(provider):
    url=str(getattr(provider,'api_url',''));model=str(getattr(provider,'model',''))
    u=urlparse(url)
    if u.scheme!='https' or u.username or u.password or u.fragment or u.hostname in ('localhost','127.0.0.1','::1') or not model:raise ValueError('Configure a trusted HTTPS provider and model locally')
    return url+'#'+model


def disclosure_scope(connection,session,plan):
    locators=[dict(h.locator) for h in plan.hits if h.locator.get('mm_locator')]
    # History also contains previously transmitted source-derived text. The
    # flag-off path cannot silently disclose that history through legacy calls.
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_evidence_snapshots'").fetchone():
        rows=connection.execute('SELECT s.* FROM tutor_evidence_snapshots s JOIN tutor_turns t ON t.id=s.turn_id WHERE t.session_id=?',(session.session_id,)).fetchall()
        for row in rows:
            loc=json.loads(row['locator_json']);src=json.loads(row['source_json'])
            if loc.get('kind') in ('image','transcript_cue','video_frame') or row['artifact_hash']:
                locators.append(dict(mm_locator=loc,mm_source=src))
    if not locators:return None
    if not enabled():raise ValueError('Multimodal disclosure disabled; history remains private')
    root=_root(connection);sources=[]
    from .native_document_library import _verified_original
    with closing(sqlite3.connect('file:'+str(root/'library.sqlite3')+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        for loc in locators:
            expected=loc.get('mm_source') or dict(owner='native_library',document_id=loc['native_document_id'],hash=loc['content_hash'],
                generation=loc['native_generation'],revision=loc['metadata_revision'],course_id=loc.get('routed_course_id') or loc.get('course_id'))
            doc=con.execute('SELECT * FROM documents WHERE id=?',(expected['document_id'],)).fetchone()
            if not doc or doc['trashed_at'] or not doc['indexing_enabled'] or source_ref(dict(doc))!=expected:raise ValueError('Selected source changed')
            _verified_original(root,dict(doc))
            item=dict(source=expected,locator=loc['mm_locator'])
            if item not in sources:sources.append(item)
    return dict(sources=sorted(sources,key=canonical))


def guarded_complete(service,request,session,plan):
    connection=service.tutor_session_service.repository.connection
    scope=disclosure_scope(connection,session,plan)
    if not scope:return service.provider.complete(request)
    if getattr(service.provider,'local_only',False):
        response=service.provider.complete(request)
        if disclosure_scope(connection,session,plan)!=scope:raise ValueError('Selected evidence changed during local answer')
        return response
    identity=provider_identity(service.provider)
    root=_root(connection)
    guard=PermissionGuard(root/'library.sqlite3',monthly_limit_micros=int(os.getenv('ANVAYA_MM_MONTHLY_MICROS','0')))
    receipt=session.metadata.get('mm_answer_permission','')
    # Cost must be a conservative configured upper bound covering the bounded
    # entire request, including history/repair. Unknown pricing disables sends.
    cost=int(os.getenv('ANVAYA_MM_ANSWER_MAX_MICROS','0'))
    if cost<=0:raise ValueError('Cloud answering is local-only until a cost bound and exact consent are configured')
    if hasattr(service.provider,'configured') and not service.provider.configured:raise ValueError('Provider unavailable; no request sent')
    if len(canonical(list(request.messages)))>64_000:raise ValueError('Provider context exceeds reviewed request bound')
    operation='answer:'+digest(dict(session_id=session.session_id,messages=list(request.messages),
        request_identity=getattr(service,'_request_operation',''),
        repair=bool(request.metadata.get('correctness_repair')),retry=bool(request.metadata.get('provider_output_retry'))))
    guard.reserve(receipt,scope,identity,'answer',operation,cost)
    try:
        response=service.provider.complete(replace(request,metadata=dict(request.metadata,multimodal_guarded=True)))
        if not isinstance(response.content,str) or len(response.content)>16000:raise ValueError('Provider output exceeded bounds')
        # Any in-flight source change aborts persistence, including repair calls.
        if disclosure_scope(connection,session,plan)!=scope:raise ValueError('Source changed during provider request')
        with guard.connection() as con:
            permission=con.execute('SELECT * FROM mm_permissions WHERE id=?',(receipt,)).fetchone()
            import time
            if permission['revoked'] or permission['expires']<time.time():raise ValueError('Consent revoked or expired during response')
        guard.finish(operation,'complete')
        return response
    except Exception:
        guard.finish(operation,'outcome_unknown')
        raise ValueError('Provider outcome unavailable; no automatic retry. Review request status before retrying.') from None
