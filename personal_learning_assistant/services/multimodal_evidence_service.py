"""Selected evidence under the existing Native Library owner and leased queue."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from urllib.parse import urlparse,parse_qs
from itsdangerous import URLSafeTimedSerializer,BadSignature
from personal_learning_assistant.domain.multimodal_models import canonical,digest,integer,source_ref,validate_locator,location_label
from .multimodal_schema import available

_REVIEW_SECRET=secrets.token_bytes(32)
RECIPE='multimodal-local-v1'


def enabled():
    return os.getenv('ANVAYA_MULTIMODAL_ENABLED','').lower() in ('1','true','yes')


class MultimodalEvidenceService:
    def __init__(self,library):
        self.lib=library;self.signer=URLSafeTimedSerializer(_REVIEW_SECRET,salt='mm-scope-v1')

    def check(self):
        if not enabled():raise ValueError('Multimodal processing is disabled')
        with self.lib.connection() as con:
            if not available(con):raise ValueError('Stop ANVAYA and explicitly activate multimodal schema first')

    def preview(self,document_id,locator,*,method='local',text=''):
        self.check();doc=self.lib.get(document_id);loc=validate_locator(locator)
        if doc['trashed_at'] or doc['availability']!='available':raise ValueError('Original unavailable')
        allowed={'pdf':'pdf_page','pptx':'pptx_slide','png':'image','jpg':'image','jpeg':'image','webp':'image','srt':'transcript_cue','vtt':'transcript_cue'}
        if allowed.get(doc['kind'])!=loc['kind']:raise ValueError('Location does not match original format')
        if method not in ('local','review','vision'):raise ValueError('Only local processing or explicit user transcription is enabled')
        if not isinstance(text,str) or len(text)>16000 or (method=='review' and not text.strip()):raise ValueError('Supply a bounded transcription')
        if doc['kind'] in ('png','jpg','jpeg','webp') and doc['size']>10*1024*1024:raise ValueError('Image processing limit is 10 MiB')
        scope=dict(source=source_ref(doc),locator=loc,method=method,text=text)
        provider='local';cost=0
        if method=='vision':
            if doc['kind']=='pptx':raise ValueError('Export the selected slide as PNG or PDF; faithful slide rendering is unavailable')
            from personal_learning_assistant.tutor.vision_provider import VisionProvider
            provider=VisionProvider().identity;cost=int(os.getenv('ANVAYA_MM_VISION_MAX_MICROS','0'))
            if cost<=0:raise ValueError('Configure a conservative per-image cost bound first; default is local-only')
        scope.update(provider=provider,cost=cost)
        return dict(token=self.signer.dumps(scope),scope=scope,description=doc['display_name']+' · '+location_label(loc),cost_upper_bound_micros=cost,provider=provider,
                    coverage=('Only the selected image/crop is sent. Provider retention rules apply; store=false does not promise zero retention.' if method=='vision' else 'Only the selected page/image; no cloud transmission.'),expires_in_seconds=600)

    def enqueue(self,document_id,token):
        self.check()
        try:scope=self.signer.loads(token,max_age=600)
        except BadSignature as exc:raise ValueError('Review expired; review scope again') from exc
        with self.lib.connection(write=True) as con:
            doc=self.lib._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            if scope['source']!=source_ref(doc) or doc['trashed_at']:raise ValueError('Source changed after review')
            self.lib._cancel_job(document_id)
            con.execute("UPDATE documents SET generation=generation+1,indexing_enabled=1,status='stored',tutor_state='preparing' WHERE id=?",(document_id,))
            doc=self.lib._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            receipt=None
            if scope['method']=='vision':
                from personal_learning_assistant.tutor.vision_provider import VisionProvider
                if VisionProvider().identity!=scope['provider']:raise ValueError('Provider changed after review')
                # Write the receipt in the same Native-owner transaction as scope.
                import time
                receipt=uuid.uuid4().hex
                consent=dict(source=source_ref(doc),locator=scope['locator'])
                con.execute('INSERT INTO mm_permissions VALUES(?,?,?,?,?,?,0)',(receipt,canonical(consent),scope['provider'],'extract',scope['cost'],time.time()+900))
            con.execute('INSERT OR REPLACE INTO mm_selections VALUES(?,?,?,?,?,?,?,?)',
                        (document_id,canonical(source_ref(doc)),canonical(scope['locator']),scope['method'],scope['text'],receipt,'queued',''))
            self.lib._enqueue_publication(con,document_id)
        self.lib._wake.set()
        return self.status(document_id)

    def status(self,document_id):
        self.check();doc=self.lib.get(document_id)
        with self.lib.connection() as con:
            row=con.execute('SELECT state,error,locator_json FROM mm_selections WHERE document_id=?',(document_id,)).fetchone()
            items=[dict(r) for r in con.execute('SELECT id,locator_json,kind,status,uncertain_json FROM mm_artifacts WHERE document_id=? AND source_json=?',(document_id,canonical(source_ref(doc))))]
        return dict(state=(row['state'] if row else 'stored'),reason_code=(row['error'].split(':',1)[0] if row and row['error'] else ''),error=(row['error'] if row else ''),artifacts=items,
                    tutor_state=doc['tutor_state'])

    def cancel(self,document_id):
        self.check()
        with self.lib.connection(write=True) as con:
            self.lib._cancel_job(document_id)
            con.execute("UPDATE documents SET generation=generation+1,status='stored',tutor_state='stored_only' WHERE id=?",(document_id,))
            con.execute("UPDATE processing_jobs SET state='cancelled' WHERE document_id=? AND state IN ('pending','running')",(document_id,))
            con.execute("UPDATE mm_selections SET state='cancelled',error='' WHERE document_id=?",(document_id,))
        return self.status(document_id)

    def create_manifest(self,transcript_id,frames,*,reference=''):
        self.check();doc=self.lib.get(transcript_id)
        if doc['kind'] not in ('srt','vtt') or doc['trashed_at']:raise ValueError('Choose an uploaded timestamped transcript')
        from personal_learning_assistant.ingestion.extractors import TranscriptExtractor
        cues=TranscriptExtractor().extract(self.lib.original(transcript_id).read_bytes(),source_name=doc['original_name'])
        if not isinstance(frames,list) or len(frames)>20:raise ValueError('At most 20 supplied frames')
        if reference:
            u=urlparse(reference)
            if (u.scheme!='https' or u.netloc not in ('www.youtube.com','youtube.com','youtu.be') or u.username or u.fragment):raise ValueError('Use a safe YouTube reference; no media is fetched')
            video=u.path.lstrip('/') if u.netloc=='youtu.be' else parse_qs(u.query).get('v',[''])[0]
            import re
            if not re.fullmatch('[A-Za-z0-9_-]{11}',video):raise ValueError('Invalid video reference')
            reference='https://www.youtube.com/watch?v='+video
        bound=[]
        for f in frames:
            if not isinstance(f,dict) or set(f)!={'document_id','timestamp_ms'}:raise ValueError('Choose frame identity and supplied timestamp')
            frame=self.lib.get(f['document_id']);timestamp=integer(f['timestamp_ms'])
            if frame['kind'] not in ('png','jpg','jpeg','webp') or frame['trashed_at'] or frame['subject_id']!=doc['subject_id']:raise ValueError('Frame must be an available image in the same course')
            if timestamp>max(c.timestamp_end_ms for c in cues):raise ValueError('Frame outside supplied transcript interval')
            self.lib.original(frame['id'])
            bound.append(dict(document_id=frame['id'],timestamp_ms=timestamp,source=source_ref(frame),alignment='user_supplied'))
        identity=uuid.uuid4().hex
        with self.lib.connection(write=True) as con:
            con.execute('INSERT INTO mm_lecture_manifests VALUES(?,?,?,?,?,1)',(identity,transcript_id,canonical(source_ref(doc)),canonical(bound),reference))
        return identity

    def temporal(self,manifest_id,timestamp_ms):
        self.check();integer(timestamp_ms)
        with self.lib.connection() as con:row=con.execute('SELECT * FROM mm_lecture_manifests WHERE id=?',(manifest_id,)).fetchone()
        if not row:raise ValueError('Lecture manifest unavailable')
        doc=self.lib.get(row['transcript_id'])
        if source_ref(doc)!=json.loads(row['source_json']) or doc['trashed_at']:raise ValueError('Transcript version changed')
        from personal_learning_assistant.ingestion.extractors import TranscriptExtractor
        cues=TranscriptExtractor().extract(self.lib.original(doc['id']).read_bytes(),source_name=doc['original_name'])
        cue=next((c for c in cues if c.timestamp_start_ms<=timestamp_ms<c.timestamp_end_ms),None)
        if not cue:raise ValueError('No supplied cue covers this time; timing is unavailable')
        frames=[]
        for f in json.loads(row['frames_json']):
            frame=self.lib.get(f['document_id'])
            if source_ref(frame)!=f['source'] or frame['trashed_at']:raise ValueError('Supplied frame version changed')
            self.lib.original(frame['id'])
            if cue.timestamp_start_ms<=f['timestamp_ms']<cue.timestamp_end_ms:frames.append(f)
        return dict(cue=dict(text=cue.text,start_ms=cue.timestamp_start_ms,end_ms=cue.timestamp_end_ms),
                    frames=frames,reference=row['reference'],alignment='user_supplied',transcript_id=doc['id'])


def extract_selected(library,doc,cancelled):
    """Called only by the existing claimed worker. None means legacy extraction."""
    if not enabled():return None
    with library.connection() as con:
        if not available(con):return None
        row=con.execute('SELECT * FROM mm_selections WHERE document_id=?',(doc['id'],)).fetchone()
    if not row or row['source_json']!=canonical(source_ref(doc)) or row['state']=='cancelled':return None
    loc=json.loads(row['locator_json'])
    from .multimodal_process_runner import inspect_original
    try:
        result=inspect_original(library.original(doc['id']),doc['kind'],loc,cancelled)
        if row['method']=='vision':
            with library.connection() as con:
                if doc.get('_processing_job') and not library._publication_is_current(con,doc,doc['_processing_job'],doc['_lease_owner']):raise ValueError('Processing lease lost before dispatch')
            from personal_learning_assistant.tutor.vision_provider import VisionProvider
            from .provider_permission_service import PermissionGuard
            provider=VisionProvider()
            if not provider.key:raise ValueError('Provider key missing; no request sent')
            guard=PermissionGuard(library.database,monthly_limit_micros=int(os.getenv('ANVAYA_MM_MONTHLY_MICROS','0')))
            scope=dict(source=source_ref(doc),locator=loc)
            operation='vision:'+digest(dict(scope=scope,recipe=RECIPE,provider=provider.identity))
            # Durable unique operation fences lease expiry/crash replay. A
            # response lost before artifact commit is blocked, never re-billed.
            cost=int(os.getenv('ANVAYA_MM_VISION_MAX_MICROS','0'))
            if not result.get('image'):raise ValueError('No faithful selected image available')
            if cancelled():raise ValueError('Cancelled before dispatch')
            guard.reserve(row['permission_id'],scope,provider.identity,'extract',operation,cost)
            try:
                result=provider.analyze(result['image'])
                from personal_learning_assistant.tutor.vision_provider import validate_result
                result=validate_result({k:result[k] for k in ('text','uncertain')})
                with guard.connection() as con:
                    receipt=con.execute('SELECT revoked,expires FROM mm_permissions WHERE id=?',(row['permission_id'],)).fetchone()
                    import time
                    if receipt['revoked'] or receipt['expires']<time.time() or cancelled():raise ValueError('Consent revoked or job cancelled')
                guard.finish(operation,'complete')
            except Exception:
                guard.finish(operation,'outcome_unknown')
                raise ValueError('Provider outcome unknown; automatic retry is blocked') from None
        text=row['review_text'] if row['method']=='review' else result['text']
        uncertain=[] if row['method']=='review' else result['uncertain']
        kind='user_transcription' if row['method']=='review' else result['kind']
        status='observed' if row['method']=='review' else ('unknown' if uncertain else 'observed')
        if not text.strip():text='Visual content is unreadable locally. Supply a transcription or a clearer image. Critical mathematical symbols are unknown.'
        # Preserve source/recipe/locator and separate append-only user review.
        recipe=RECIPE+':'+row['method']+(':'+provider.identity if row['method']=='vision' else ':pinned-local-parsers')
        identity=digest(dict(source=source_ref(doc),locator=loc,recipe=recipe,method=row['method'],text=text))
        with library.connection(write=True) as con:
            current=library._doc(con.execute('SELECT * FROM documents WHERE id=?',(doc['id'],)).fetchone())
            selection=con.execute('SELECT * FROM mm_selections WHERE document_id=?',(doc['id'],)).fetchone()
            lease_current=(not doc.get('_processing_job') or library._publication_is_current(con,doc,doc['_processing_job'],doc['_lease_owner']))
            if not lease_current or source_ref(current)!=source_ref(doc) or not selection or selection['state']=='cancelled' or cancelled():raise ValueError('Source changed, lease lost or job cancelled')
            con.execute('INSERT OR REPLACE INTO mm_artifacts VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (identity,doc['id'],canonical(source_ref(doc)),canonical(loc),recipe,hashlib.sha256(text.encode()).hexdigest(),text,kind,status,canonical(uncertain)))
            if row['method']=='review':con.execute('INSERT OR IGNORE INTO mm_reviews VALUES(?,?,?,?,?)',(identity,identity,hashlib.sha256(text.encode()).hexdigest(),text,datetime.now(timezone.utc).isoformat()))
            con.execute("UPDATE mm_selections SET state='processing',error='' WHERE document_id=?",(doc['id'],))
        return [(loc.get('page',loc.get('slide',1)),text)],('partial' if uncertain else 'ready'),'Selected scope only; local machine reading may be wrong. Review critical symbols.'
    except Exception as error:
        message=str(error).lower()
        reason=('budget_limit' if 'budget' in message else 'consent_required' if 'consent' in message else
                'outcome_unknown' if 'outcome' in message or 'already dispatched' in message else
                'provider_unavailable' if 'key' in message else 'source_changed' if 'source' in message or 'lease' in message else
                'cancelled' if 'cancel' in message else 'local_processing_failed')
        with library.connection(write=True) as con:
            if not doc.get('_processing_job') or library._publication_is_current(con,doc,doc['_processing_job'],doc['_lease_owner']):
                con.execute("UPDATE mm_selections SET state='blocked',error=? WHERE document_id=? AND source_json=?",(reason+': Original preserved. Review processing details before retrying paid work.',doc['id'],canonical(source_ref(doc))))
        raise


def artifact_units(library,doc):
    """Current immutable artifacts for publication; empty for ordinary documents."""
    if not enabled():return []
    with library.connection() as con:
        if not available(con):return []
        rows=con.execute('SELECT * FROM mm_artifacts WHERE document_id=? AND source_json=?',(doc['id'],canonical(source_ref(doc)))).fetchall()
    return [dict(r) for r in rows]
