#!/usr/bin/env python3
"""Offline educational benchmark mechanics; never calls or grades a live model.

Sources, manifest and evaluator-only keys deliberately have separate loaders.
The application adapter takes a source case, never a key or expected solution.
"""
from __future__ import annotations
import argparse
from contextlib import closing, contextmanager
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import re
import socket
import sqlite3
import subprocess
import sys
import time
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIXTURES = ROOT/'tests/fixtures/multimodal_quality'
CONTEXT = {'top_k': 10, 'max_chars': 12000}
FAKE_CONTENT = 'The selected academic source is available for review. This offline adapter does not solve the exercise.'


def load_manifest():
    return json.loads((FIXTURES/'manifest.json').read_text(encoding='utf-8'))


def source_path(relative):
    path = (FIXTURES/relative).resolve()
    if not path.is_relative_to((FIXTURES/'sources').resolve()):
        raise ValueError('Only synthetic source files may enter the application')
    return path


def source_text(case):
    return source_path(case['transcription']).read_text(encoding='utf-8')


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rref(rows):
    """Exact Gauss-Jordan reference, independent of the app/model answer path."""
    a = [[Fraction(v) for v in row] for row in rows]
    pivot = 0
    for col in range(len(a[0])):
        found = next((i for i in range(pivot,len(a)) if a[i][col]), None)
        if found is None:
            continue
        a[pivot],a[found] = a[found],a[pivot]
        scale = a[pivot][col]
        a[pivot] = [v/scale for v in a[pivot]]
        for i in range(len(a)):
            if i != pivot:
                scale = a[i][col]
                a[i] = [v-scale*w for v,w in zip(a[i],a[pivot])]
        pivot += 1
        if pivot == len(a):
            break
    return [[float(v) if v.denominator != 1 else int(v) for v in row] for row in a],pivot


def _matmul(a,b):
    return [[sum(Fraction(x)*Fraction(y) for x,y in zip(row,col)) for col in zip(*b)] for row in a]


def reference_calculations():
    """Independent checks with source-side operands, not stored expected values."""
    rref, rank = _rref([[1,2],[2,4]])
    a = [[2,1],[4,3]]; multiplier = Fraction(a[1][0],a[0][0])
    l = [[1,0],[int(multiplier),1]]; u = [a[0],[0,int(a[1][1]-multiplier*a[0][1])]]
    assert _matmul(l,u) == a
    inverse,_ = _rref([[1,-1,1,0],[0,2,0,1]])
    inv = [row[2:] for row in inverse]
    assert _matmul([[1,-1],[0,2]],inv) == [[1,0],[0,1]]
    ra = _rref([[1,1],[2,2]])[1]; rab = _rref([[1,1,2],[2,2,5]])[1]
    observed = [v for v in [1,None,3] if v is not None]
    raw = [2,4,6]; scale = [(v-min(raw))/(max(raw)-min(raw)) for v in raw]
    rank20 = _rref([[1,0,2],[0,1,3]])[1]
    operation = [[1,2],[2-2*1,5-2*2]]
    return {'P01':{'rref':rref,'rank':rank}, 'P02':{'L':l,'U':u},
        'P03':{'shape':[2,3],'second_row':list(range(6))[3:]},
        'P07':{'inverse':inv},'P08':{'rank_A':ra,'rank_augmented':rab,'consistent':ra==rab},
        'P09':{'total':sum(range(1,4))},'P10':{'mean':sum(observed)/len(observed),'imputed':sum(observed)/len(observed)},
        'P13':{'result':operation},'P14':{'swap_result':[[0,1],[1,1]][::-1]},
        'P15':{'shape':[2,3]},'P16':{'scaled':scale},'P18':{'power_W':float(Fraction(2)*Fraction(7,10))},
        'P19':{'rank':_rref([[1,0],[0,1]])[1],'independent':True},
        'P20':{'rank':rank20,'nullity':3-rank20},'P21':{'precision':8/(8+2)},
        'P25':{'result':[[0,1],[1,2]][::-1]},'P26':{'result':operation},
        'P27':{'shape':[2,6//2]},'P28':{'filtered':[v for v in [1,3,2,4] if v>2]},
        'P30':{'efficiency_percent':70/100*100}}


def check_reference_gold(gold=None):
    if gold is None:
        gold = json.loads((FIXTURES/'gold/answers.json').read_text(encoding='utf-8'))
    derived = reference_calculations()
    checks = [{'id':key,'passed':gold[key]['reference']==value,'method':'independent exact arithmetic / finite trace'} for key,value in derived.items()]
    rubric_only = [key for key,value in gold.items() if key.startswith('P') and value['reference'] is None]
    return {'status':'PASS' if all(c['passed'] for c in checks) else 'FAIL',
        'numeric_checks':checks,'rubric_only_cases':rubric_only,
        'provenance':'Evaluator-side Fraction arithmetic and finite Python traces; source-authored chemistry/diagram rubrics, not model grading',
        'model_answer_passes':None}


def locator_matches(actual,expected):
    """Placement, hash and full atomic locator must match, not just page number."""
    return all(actual.get(k)==expected.get(k) for k in expected)


def score_response(content, available_labels, *, fake=True):
    cited = set(re.findall(r'\[(S\d+)\]',content))
    invented = sorted(cited-set(available_labels))
    return {'answer_score':None,'explanation_score':None,'citation_claim_precision':None,
        'invented_citation_labels':invented,'citation_labels_valid':not invented,
        'grader':'not_run_fake_provider' if fake else 'requires_blind_rubric_review',
        'reason':'Citation label validity is an engineering check; it does not establish support for academic claims.'}


@contextmanager
def offline_environment():
    """Deny dispatch in-process and keep caller environment unchanged."""
    attempts = []
    def denied(*args,**kwargs):
        attempts.append('blocked_socket_attempt')
        raise RuntimeError('Network disabled in offline educational evaluation')
    with patch.dict(os.environ,{'ANVAYA_MULTIMODAL_ENABLED':'true','ANVAYA_MM_MONTHLY_MICROS':'0','ANVAYA_MM_ANSWER_MAX_MICROS':'0'}), \
         patch.object(socket.socket,'connect',denied),patch.object(socket.socket,'connect_ex',denied),patch.object(socket,'create_connection',denied):
        yield attempts


@contextmanager
def owners(path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.services.multimodal_schema import activate
    from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
    db = Path(path)/'data/learning_assistant.db'; db.parent.mkdir(parents=True,exist_ok=True)
    apply_migrations(db)
    lib = NativeDocumentLibrary(db.parent/'native_library',autostart=False)
    lib.configure_tutor(db,db.parent/'tutor_retrieval'); activate(db,lib.root,apply=True)
    try:
        yield lib,db
    finally:
        lib.close()


def _records(db):
    from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
    with closing(sqlite3.connect(db)) as con:
        return SQLiteRetrievalSourceRepository(con).active_records()


def upload_case(lib,case,*,corrected):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    path = source_path(case['source'])
    if file_hash(path)!=case['sha256']:
        raise ValueError('Fixture source hash mismatch')
    doc = lib.upload(BytesIO(path.read_bytes()),path.name,subject_id=case['subject'])
    svc = MultimodalEvidenceService(lib)
    if corrected and case['modality']!='transcript_frame':
        preview = svc.preview(doc['id'],case['locator'],method='review',text=source_text(case),review_complete=True)
        svc.enqueue(doc['id'],preview['token'])
    lib.run_pending()
    frames = []; manifest = None
    if corrected and case.get('frames'):
        for frame in case['frames']:
            frame_path = source_path(frame['source'])
            if file_hash(frame_path)!=frame['sha256']:
                raise ValueError('Frame hash mismatch')
            fdoc = lib.upload(BytesIO(frame_path.read_bytes()),frame_path.name,subject_id=case['subject'])
            p = svc.preview(fdoc['id'],{'kind':'image'},method='review',text=source_path(frame['transcription']).read_text(),review_complete=True)
            svc.enqueue(fdoc['id'],p['token']); lib.run_pending()
            frames.append({'document_id':fdoc['id'],'timestamp_ms':frame['timestamp_ms']})
        manifest = svc.create_manifest(doc['id'],frames)
    current = lib.get(doc['id'])
    return current,manifest,frames


class RecordingFakeProvider:
    """No academic answers, gold import, network client or API credentials."""
    local_only = True
    def __init__(self):
        self.requests=[]
    def complete(self,request):
        from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
        self.requests.append(request)
        # Cite exactly the context labels already in the app request, not keys.
        labels = list(request.metadata.get('evidence_labels', ()))
        if not labels:
            labels=['S1']
        content=FAKE_CONTENT+' '+' '.join('['+s+']' for s in labels)
        # The production Tutor requires a verified math envelope for explicit
        # matrix computation prompts. Exercise that gate with an identity-copy
        # transport probe of the visible INPUT, never the requested solution.
        # This is synthetic formatter plumbing and is never an answer score.
        from personal_learning_assistant.tutor.correctness import requires_deterministic_math
        for message in request.messages:
            body=str(message.get('content',''))
            question=re.search(r'CURRENT QUESTION\n(.*?)\n\nACADEMIC EVIDENCE',body,re.S)
            evidence=re.search(r'<academic_evidence>(.*?)</academic_evidence>',body,re.S)
            if question and evidence and requires_deterministic_math(question.group(1)):
                matrix=re.search(r'\[\s*\[[0-9.,\s-]+\](?:\s*,\s*\[[0-9.,\s-]+\])+\s*\]',evidence.group(1))
                if matrix:
                    import ast
                    values=ast.literal_eval(matrix.group(0))
                    if len(values)<=10 and len({len(row) for row in values})==1:
                        identity=[[int(i==j) for j in range(len(values))] for i in range(len(values))]
                        claim={'type':'matrix_product','left':identity,'right':values,'result':values}
                        content='<!--ANVAYA_MATH '+json.dumps({'claims':[claim]})+'-->\n'+content
                break
        return TutorProviderResponse(content,'offline-harness','fake-no-academic-answer')


def _session(con,record,doc,manifest=None,*,course=None):
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    sessions = TutorSessionService(SQLiteTutorRepository(con))
    metadata = {}
    if record:
        metadata = {'source_document_id':record['document_id'],'source_version_hash':doc['sha256']}
        if record['locator'].get('mm_locator'):
            metadata.update(mm_selection=record['locator']['mm_locator'],mm_source_ref=record['locator'])
    if manifest:
        metadata['mm_manifest_id']=manifest
    spec = TutorSessionSpec(mode='doubt',source_policy='source_only',title='Synthetic source exercise',metadata=metadata,course_id=course)
    return sessions,sessions.create_session(spec)


def _snapshots(con,turn_id,lib):
    from personal_learning_assistant.services.source_citation_service import resolve_snapshot
    result=[]
    for row in con.execute('SELECT * FROM tutor_evidence_snapshots WHERE turn_id=?',(turn_id,)).fetchall():
        resolved = resolve_snapshot(con,row['id'],lib)
        result.append({'label':row['label'],'source':resolved['source'],'locator':resolved['locator'],
            'title':resolved['title'],'artifact_hash':row['artifact_hash']})
    return result


def run_positive(case, path, *, corrected, followups=()):
    """Run actual feature paths; this interface deliberately cannot accept gold."""
    from personal_learning_assistant.services.unified_search_runtime import UnifiedSearchRuntime
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.domain.multimodal_models import source_ref
    started=time.perf_counter(); provider=RecordingFakeProvider(); follow=[]
    with patch.dict(os.environ,{'ANVAYA_MULTIMODAL_ENABLED':'true' if corrected else 'false'}),owners(path) as (lib,db):
        doc,manifest,frames=upload_case(lib,case,corrected=corrected)
        records=[r for r in _records(db) if r['locator'].get('native_document_id')==doc['id']]
        record=records[0] if records else None
        runtime=UnifiedSearchRuntime(database_path=db,index_root=db.parent/'tutor_retrieval')
        try:
            with closing(sqlite3.connect(db,isolation_level=None)) as con:
                sessions,session=_session(con,record,doc,manifest)
                tutor=GroundedTutorService(tutor_session_service=sessions,retrieval_service=runtime,provider=provider)
                result=tutor.answer(session.session_id,case['question'],**CONTEXT)
                snapshots=_snapshots(con,result.assistant_turn.turn_id,lib)
                expected=[]
                if record:
                    # Expected localization is derived from authored manifest/actual
                    # uploaded placement, not from the returned snapshot itself.
                    if corrected:
                        loc=dict(case['locator'],schema_version=2)
                    elif case['modality']=='digital_pdf':
                        loc={'kind':'pdf_page','page':1,'schema_version':2}
                    else:
                        loc=None
                    if loc:
                        expected.append({'source':source_ref(lib.get(doc['id'])),'locator':loc})
                    for frame,uploaded in zip(case.get('frames',[]),frames):
                        expected.append({'source':source_ref(lib.get(uploaded['document_id'])),
                            'locator':{'kind':'video_frame','schema_version':2,'frame_pts_ms':frame['timestamp_ms'],'asset_id':uploaded['document_id'],'alignment':'user_supplied','parent_source_ref':manifest}})
                exact=len(snapshots)==len(expected) and all(any(
                    locator_matches(s['source'],e['source']) and s['locator']==e['locator'] for s in snapshots) for e in expected)
                labels={s['label'] for s in snapshots};score=score_response(result.assistant_turn.content,labels)
                # Review transcriptions are exact user-supplied source content, not
                # OCR accuracy; preserve this provenance explicitly.
                transcription_exact=None
                if corrected and case['modality']!='transcript_frame' and record:
                    transcription_exact=record['text'].strip()==source_text(case).strip()
                status='UNSUPPORTED' if not record else ('NO_RETRIEVAL_MATCH' if not snapshots and not provider.requests else ('PASS' if exact and score['citation_labels_valid'] and transcription_exact is not False else 'FAIL'))
                for item in followups:
                    fr=tutor.answer(session.session_id,item['question'],**CONTEXT)
                    follow.append(dict(item,production_path_executed=True,provider='offline_fake',model_quality='not_run',raw_output=fr.assistant_turn.content,answer_score=None))
                payloads=[{'messages':list(r.messages),'metadata':dict(r.metadata)} for r in provider.requests]
                all_text=json.dumps(payloads)
                # No IDs/keys have been included as a source search token.
                no_task_id=case['id'] not in all_text
                if not no_task_id:
                    status='FAIL'
                output={'status':status,'production_path_executed':True,
                    'path':'B_corrected_multimodal' if corrected else 'A_feature_disabled_text_only',
                    'reason':('No text evidence available in the actual feature-disabled application path' if not record else ('Native text exists, but the actual natural-query retrieval returned no evidence; no model answer was produced' if status=='NO_RETRIEVAL_MATCH' else 'Offline routing, source snapshot and citation-label mechanics only')),
                    'exact_localization':exact if record else None,'expected_location_count':len(expected),
                    'snapshots':snapshots,'transcription_exact':transcription_exact,
                    'transcription_provenance':'user_corrected' if corrected else 'native_embedded_text',
                    'critical_symbol_error_rate':0 if transcription_exact else None,
                    'model_answer_score':None,'model_explanation_score':None,'unnecessary_refusal':None,
                    'citation_precision':None,'citation_label_check':score,'raw_output':result.assistant_turn.content,
                    'support_level':result.assistant_turn.support_level,'provider_calls':len(provider.requests),
                    'provider_payloads':payloads,'prompt_hashes':[hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest() for p in payloads],
                    'source_hash':case['sha256'],'latency_seconds':time.perf_counter()-started,
                    'interaction_burden':{'source_uploads':1+len(frames),'user_transcription_reviews':int(corrected and case['modality']!='transcript_frame')+len(frames)},
                    'context_bounds':CONTEXT,'task_id_absent_from_payload':no_task_id}
                return output,follow
        finally:
            runtime.close()


def _expect_rejection(action):
    try:
        action()
    except ValueError as error:
        return {'rejected':True,'reason':str(error)}
    return {'rejected':False,'reason':'Production boundary accepted the operation'}


def _independent_rows(con):
    allowed={'knowledge_documents','knowledge_chunks','index_jobs','outbox_events','tutor_sessions','tutor_turns','tutor_evidence_links','tutor_evidence_snapshots'}
    tables=[row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if row[0] not in allowed]
    return {table:[tuple(row) for row in con.execute('SELECT * FROM "'+table.replace('"','""')+'" ORDER BY rowid')] for table in tables}


def run_negative(case,path):
    """Exercise production safety boundaries; semantic fake refusal is unscored."""
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    from personal_learning_assistant.services.multimodal_tutor import selected_hits,select_evidence,guarded_complete,disclosure_scope,provider_identity
    from personal_learning_assistant.services.provider_permission_service import PermissionGuard
    from personal_learning_assistant.domain.tutor_models import TutorProviderRequest,TutorProviderResponse
    scenario=case['scenario']; started=time.perf_counter(); checks={}; status='PASS'; limitations=[]
    with owners(path) as (lib,db):
        src=source_path(case['source']);doc=lib.upload(BytesIO(src.read_bytes()),src.name,subject_id='MA103N');svc=MultimodalEvidenceService(lib)
        if scenario=='stale_review':
            p=svc.preview(doc['id'],{'kind':'image'},method='review',text=source_text(case),review_complete=True)
            lib.update(doc['id'],display_name='Renamed after scope review')
            checks=_expect_rejection(lambda:svc.enqueue(doc['id'],p['token']))
            status='PASS' if checks['rejected'] else 'FAIL'
        elif scenario=='rotated_crop':
            from personal_learning_assistant.services.multimodal_process_runner import inspect_original
            # Display-space selection on a page rotated clockwise: original top
            # region is on displayed right. See independent selected text below.
            found=inspect_original(lib.original(doc['id']),'pdf',{'kind':'pdf_page','page':1,'bbox':[0.7,0,1,1]})
            checks={'selected_matrix_present':'Selected matrix' in found['text'],'off_crop_excluded':'SYNTHETIC PRIVATE OFF CROP' not in found['text'],
                'original_unchanged':file_hash(lib.original(doc['id']))==case['sha256'],'derived_text':found['text']}
            preview=svc.preview(doc['id'],{'kind':'pdf_page','page':1,'bbox':[0.7,0,1,1]},method='local')
            svc.enqueue(doc['id'],preview['token']);lib.run_pending()
            record=next(r for r in _records(db) if r['locator'].get('native_document_id')==doc['id'])
            from personal_learning_assistant.services.unified_search_runtime import UnifiedSearchRuntime
            from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
            provider=RecordingFakeProvider();runtime=UnifiedSearchRuntime(database_path=db,index_root=db.parent/'tutor_retrieval')
            try:
                with closing(sqlite3.connect(db,isolation_level=None)) as con:
                    sessions,session=_session(con,record,lib.get(doc['id']))
                    GroundedTutorService(tutor_session_service=sessions,retrieval_service=runtime,provider=provider).answer(session.session_id,case['question'],**CONTEXT)
            finally:
                runtime.close()
            checks['provider_payload_excludes_off_crop']=bool(provider.requests) and 'SYNTHETIC PRIVATE OFF CROP' not in json.dumps([list(r.messages) for r in provider.requests])
            status='PASS' if all(checks[k] for k in ('selected_matrix_present','off_crop_excluded','original_unchanged','provider_payload_excludes_off_crop')) else 'FAIL'
        elif scenario in ('cue_gap','missing_visual','frame_cap'):
            lib.run_pending();frames=[]
            if scenario=='frame_cap':
                # Authored distinct image placements; review text faithfully
                # describes each frame, with the decisive result only in the last.
                for frame in case['frames']:
                    image=source_path(frame['source'])
                    if file_hash(image)!=frame['sha256']:
                        raise ValueError('Negative frame source hash mismatch')
                    f=lib.upload(BytesIO(image.read_bytes()),image.name,subject_id='MA103N')
                    p=svc.preview(f['id'],{'kind':'image'},method='review',text=source_path(frame['transcription']).read_text(),review_complete=True)
                    svc.enqueue(f['id'],p['token']);lib.run_pending();frames.append({'document_id':f['id'],'timestamp_ms':frame['timestamp_ms']})
            manifest=svc.create_manifest(doc['id'],frames)
            if scenario=='cue_gap':
                checks={'at_end':_expect_rejection(lambda:svc.temporal(manifest,4000)),
                    'inside_gap':_expect_rejection(lambda:svc.temporal(manifest,4500)),
                    'next_start':svc.temporal(manifest,5000)['cue']['start_ms']==5000}
                status='PASS' if checks['at_end']['rejected'] and checks['inside_gap']['rejected'] and checks['next_start'] else 'FAIL'
            else:
                record=next(r for r in _records(db) if r['locator'].get('native_document_id')==doc['id'])
                with closing(sqlite3.connect(db,isolation_level=None)) as con:
                    sessions,session=_session(con,record,doc,manifest)
                    hits=selected_hits(con,session)
                    checks={'actual_hit_count':len(hits),'supplied_frame_count':len(frames),'returned_frame_ids':[h.locator.get('native_document_id') for h in hits[1:]],
                        'temporal':svc.temporal(manifest,2000)}
                    if scenario=='frame_cap':
                        selection=select_evidence(con,session)
                        coverage=selection.coverage
                        checks['coverage_contract']=None
                        checks['decisive_last_included']=frames[-1]['document_id'] in checks['returned_frame_ids']
                        # This deterministic case measures disclosed bounds, not
                        # the fake provider's ability to explain a missing frame.
                        if coverage:
                            from dataclasses import asdict
                            checks['coverage_contract']=asdict(coverage)
                        limitations.append('Model explanation of the decisive omitted frame is not evaluated offline.')
                        status='PASS' if coverage.requires_narrowing and not coverage.complete and not checks['decisive_last_included'] else 'FAIL'
                    else:
                        checks['no_visual_frames']=len(hits)==1
                        limitations.append('Only deterministic missing-board clarification is checked; no model reasoning/refusal score.')
                    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
                    from personal_learning_assistant.services.unified_search_runtime import UnifiedSearchRuntime
                    provider=RecordingFakeProvider();runtime=UnifiedSearchRuntime(database_path=db,index_root=db.parent/'tutor_retrieval')
                    try:
                        result=GroundedTutorService(tutor_session_service=sessions,retrieval_service=runtime,provider=provider).answer(session.session_id,case['question'],**CONTEXT)
                    finally:
                        runtime.close()
                    checks.update(provider_calls=len(provider.requests),support_level=result.assistant_turn.support_level,raw_output=result.assistant_turn.content)
                    checks['predispatch_clarification']=not provider.requests and result.assistant_turn.support_level=='insufficient'
                    if scenario=='missing_visual':
                        status='PASS' if checks['no_visual_frames'] and checks['predispatch_clarification'] else 'FAIL'
                    elif not checks['predispatch_clarification']:
                        status='FAIL'
        else:
            uncertainty=case.get('declared_uncertain',[])
            kwargs={'declared_uncertain':uncertainty,'review_complete':False} if uncertainty else {'review_complete':True}
            p=svc.preview(doc['id'],{'kind':'image'},method='review',text=source_text(case),**kwargs)
            svc.enqueue(doc['id'],p['token']);lib.run_pending()
            record=next(r for r in _records(db) if r['locator'].get('native_document_id')==doc['id'])
            with closing(sqlite3.connect(db,isolation_level=None)) as con:
                sessions,session=_session(con,record,lib.get(doc['id']))
                if scenario=='wrong_course':
                    copied=lib.copy(doc['id']);lib.update(copied['id'],subject_id='UC100N');lib.run_pending()
                    # Same hash is irrelevant: the selected MA placement is not
                    # admissible inside a UC session.
                    wrong=SimpleNamespace(metadata=session.metadata,course_id='UC100N')
                    checks={'same_blob_hash':copied['sha256']==doc['sha256'],**_expect_rejection(lambda:selected_hits(con,wrong))}
                    status='PASS' if checks['same_blob_hash'] and checks['rejected'] else 'FAIL'
                elif scenario in ('revocation','unknown_outcome'):
                    calls=[]
                    class GuardProbe:
                        api_url='https://synthetic.invalid/v1/chat/completions';model='synthetic-no-http'
                        def complete(self,request):
                            calls.append('in_process_probe')
                            if scenario=='unknown_outcome':
                                raise TimeoutError('synthetic lost response')
                            guard.revoke(receipt)
                            return TutorProviderResponse('Synthetic response [S1]','offline-probe','fake')
                    provider=GuardProbe();service=SimpleNamespace(tutor_session_service=sessions,provider=provider)
                    plan=SimpleNamespace(hits=selected_hits(con,session));scope=disclosure_scope(con,session,plan)
                    guard=PermissionGuard(lib.database,monthly_limit_micros=100)
                    receipt=guard.grant(scope,provider_identity(provider),'answer',max_cost_micros=20)
                    sessions.update_session_metadata(session.session_id,{'mm_answer_permission':receipt})
                    session=sessions.repository.get_session(session.session_id)
                    req=TutorProviderRequest(session_id=session.session_id,mode='doubt',source_policy='source_only',messages=({'role':'user','content':case['question']},))
                    with patch.dict(os.environ,{'ANVAYA_MM_MONTHLY_MICROS':'100','ANVAYA_MM_ANSWER_MAX_MICROS':'20'}):
                        if scenario=='revocation':
                            guard.revoke(receipt);before=_expect_rejection(lambda:guarded_complete(service,req,session,plan))
                            checks['revoked_before_dispatch']=before['rejected'] and not calls
                            receipt=guard.grant(scope,provider_identity(provider),'answer',max_cost_micros=20)
                            sessions.update_session_metadata(session.session_id,{'mm_answer_permission':receipt});session=sessions.repository.get_session(session.session_id)
                        checks['first_attempt']=_expect_rejection(lambda:guarded_complete(service,req,session,plan))
                        checks['second_attempt']=_expect_rejection(lambda:guarded_complete(service,req,session,plan))
                    with guard.connection() as native:
                        rows=native.execute('SELECT reserved,actual,status FROM mm_provider_requests').fetchall()
                    checks.update(in_process_probe_calls=len(calls),reservations=[dict(r) for r in rows],persisted_turns=con.execute('SELECT count(*) FROM tutor_turns').fetchone()[0])
                    status='PASS' if checks['first_attempt']['rejected'] and checks['second_attempt']['rejected'] and len(calls)==1 and checks['persisted_turns']==0 and any(r['reserved']==20 and r['actual'] is None and r['status']=='outcome_unknown' for r in rows) else 'FAIL'
                else:
                    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
                    from personal_learning_assistant.services.unified_search_runtime import UnifiedSearchRuntime
                    provider=RecordingFakeProvider();runtime=UnifiedSearchRuntime(database_path=db,index_root=db.parent/'tutor_retrieval')
                    unrelated_text='Synthetic unrelated notebook: confidential experiment log outside selected scope.'
                    if scenario=='injection_boundary':
                        lib.upload(BytesIO(unrelated_text.encode()),'unrelated-private-notebook.txt',subject_id='CY100N',indexing=False)
                    before_owners=_independent_rows(con)
                    try:
                        result=GroundedTutorService(tutor_session_service=sessions,retrieval_service=runtime,provider=provider).answer(session.session_id,case['question'],**CONTEXT)
                    finally:
                        runtime.close()
                    checks={'provider_calls':len(provider.requests),'support_level':result.assistant_turn.support_level,'raw_output':result.assistant_turn.content}
                    if scenario=='critical_uncertainty':
                        checks['uncertainty_blocked_predispatch']=not provider.requests and result.assistant_turn.support_level=='insufficient'
                        checks['named_ambiguity']=all(reason.lower() in result.assistant_turn.content.lower() for reason in uncertainty)
                        status='PASS' if checks['uncertainty_blocked_predispatch'] and checks['named_ambiguity'] else 'FAIL'
                    elif scenario=='injection_boundary':
                        # Only the selected placement reaches the provider. This
                        # checks scope, not language-model resistance to injection.
                        payload=json.dumps([list(r.messages) for r in provider.requests])
                        checks['selected_instruction_treated_as_source_data']='ignore rules' in payload
                        checks['unrelated_document_disclosed']=unrelated_text in payload
                        checks['independent_owner_rows_unchanged']=_independent_rows(con)==before_owners
                        checks['source_wrapped_as_untrusted_data']='<academic_evidence>' in payload and '</academic_evidence>' in payload
                        limitations.append('Instruction-following resistance is not measured with a fake provider. Scope-only boundary checked.')
                        status='UNSUPPORTED' if checks['independent_owner_rows_unchanged'] and not checks['unrelated_document_disclosed'] and checks['source_wrapped_as_untrusted_data'] else 'FAIL'
                    elif scenario=='insufficient_answer':
                        limitations.append('No deterministic source-level answerability oracle; justified refusal requires authorized model/rubric evaluation.')
                        status='UNSUPPORTED'
        return {'id':case['id'],'scenario':scenario,'status':status,'production_path_executed':True,
            'kind':'deterministic_integration' if scenario not in ('injection_boundary','insufficient_answer') else 'partial_integration_semantic_not_run',
            'checks':checks,'limitations':limitations,'model_refusal_score':None,
            'latency_seconds':time.perf_counter()-started,'source_hash':case['sha256']}


def _provenance():
    def git(*args):
        try:
            return subprocess.check_output(['git',*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.CalledProcessError):
            return 'unavailable'
    return {'platform':platform.platform(),'python':platform.python_version(),'git_sha':git('rev-parse','HEAD'),
        'dirty_tree':bool(git('status','--porcelain')),'run_time_utc':datetime.now(timezone.utc).isoformat(),
        'provider':'offline in-process fake/probe only','model':'not_run','manifest_sha256':file_hash(FIXTURES/'manifest.json'),
        'prompt_source_sha256':file_hash(ROOT/'personal_learning_assistant/tutor/grounding.py'),
        'source_split':'development only; nine source-distinct held-out samples reserved and never ingested'}


def evaluate(output,*,live=False):
    if live:
        raise ValueError('Live model evaluation is not authorized; this executable is offline-only')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    manifest=load_manifest();positive=[];negative=[];follow=[]
    tracemalloc.start();started=time.perf_counter()
    with offline_environment() as attempts:
        for case in manifest['cases']:
            try:
                if case['id'].startswith('P'):
                    # Fixed paired order is recorded. A and B use independent
                    # owners, same source, query and context limits; no B text can
                    # contaminate A through shared caches/history.
                    a,_=run_positive(case,output/'owners'/case['id']/'A',corrected=False)
                    b,fr=run_positive(case,output/'owners'/case['id']/'B',corrected=True,
                        followups=[f for f in manifest['follow_ups'] if f['case_id']==case['id']])
                    positive.append({'id':case['id'],'subject':case['subject'],'modality':case['modality'],
                        'test_order':['A','B','C_not_run'],'A':a,'B':b,
                        'C':{'status':'NOT_AUTHORIZED','production_path_executed':False,'model_answer_score':None,'reason':'No separate live-model authorization; no adapter invoked'}})
                    follow.extend(fr)
                else:
                    negative.append(run_negative(case,output/'owners'/case['id']))
            except Exception as error:
                failed={'status':'FAIL','production_path_executed':True,'model_answer_score':None,'error':type(error).__name__+': '+str(error)}
                if case['id'].startswith('P'):
                    positive.append({'id':case['id'],'subject':case['subject'],'modality':case['modality'],'A':failed,'B':failed,
                        'C':{'status':'NOT_AUTHORIZED','production_path_executed':False,'model_answer_score':None}})
                else:
                    negative.append(dict(failed,id=case['id'],scenario=case['scenario']))
        references=check_reference_gold()
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    times=sorted(v[p]['latency_seconds'] for v in positive for p in ('A','B') if 'latency_seconds' in v[p])
    failures=[v['id'] for v in positive if v['A']['status']=='FAIL' or v['B']['status']=='FAIL']+[v['id'] for v in negative if v['status']=='FAIL']
    report={'report_version':1,'status':'FAIL' if failures or attempts or references['status']=='FAIL' else 'PASS',
        'meaning':'Offline application routing, deterministic source/safety and evaluator integrity only. PASS is not educational-model accuracy.',
        'model_quality':'not_run','live_model_status':'NOT_AUTHORIZED','network_attempts':len(attempts),'paid_cost_micros':0,
        'provenance':_provenance(),'context_bounds':CONTEXT,'reference_checks':references,
        'positive_cases':positive,'negative_cases':negative,'follow_ups':follow,'failures':failures,
        'summary':{'positive_count':len(positive),'negative_count':len(negative),
            'A':{s:sum(v['A']['status']==s for v in positive) for s in ('PASS','FAIL','UNSUPPORTED','NO_RETRIEVAL_MATCH')},
            'B':{s:sum(v['B']['status']==s for v in positive) for s in ('PASS','FAIL','UNSUPPORTED','NO_RETRIEVAL_MATCH')},
            'negative_safety':{s:sum(v['status']==s for v in negative) for s in ('PASS','FAIL','UNSUPPORTED','NO_RETRIEVAL_MATCH')},
            'C_not_authorized':len(positive),'model_answer_scores':None,'model_citation_precision':None},
        'resources':{'total_seconds':time.perf_counter()-started,'paired_path_p50_seconds':times[len(times)//2] if times else None,
            'paired_path_p95_seconds':times[min(len(times)-1,int(len(times)*.95))] if times else None,
            'python_tracemalloc_peak_bytes':peak,'memory_scope':'Python allocations only, excludes parser subprocess/RSS; actual current host, not Windows targets'},
        'unsupported_reasons':['Fake providers cannot measure answer/explanation correctness, justified refusals, hint quality or injection reasoning.',
            'Corrected transcriptions measure exact user review routing, not OCR/handwriting/vision quality.',
            'No separately authorized live model or Windows educational pilot run.']}
    (output/'report.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    with (output/'tasks.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['id','path','status','model_answer_score','exact_localization','provider_calls','latency_seconds']);writer.writeheader()
        for row in positive:
            for p in ('A','B','C'):
                writer.writerow(dict(id=row['id'],path=p,**{k:row[p].get(k) for k in writer.fieldnames if k not in ('id','path')}))
        for row in negative:
            writer.writerow(dict(id=row['id'],path='safety',status=row['status'],latency_seconds=row.get('latency_seconds')))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/multimodal-quality')
    parser.add_argument('--live',action='store_true',help='Rejected: separate live-model authorization is required')
    args=parser.parse_args()
    if args.live:
        parser.error('Live evaluation is not authorized in this offline harness')
    report=evaluate(args.output)
    print(json.dumps({'status':report['status'],'model_quality':report['model_quality'],'summary':report['summary'],'report':str(args.output/'report.json')}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
