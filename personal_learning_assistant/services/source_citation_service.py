"""Immutable per-turn evidence locations and fail-closed original resolution."""
import json
import uuid
from personal_learning_assistant.domain.multimodal_models import canonical,validate_locator,source_ref
from personal_learning_assistant.ingestion.chunking import decode_chunk_type


def save_snapshot(connection,turn_id,evidence,*,context=None):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_evidence_snapshots'").fetchone():return
    row=connection.execute('SELECT c.chunk_type,d.content_hash,d.path_key FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id WHERE c.id=?',(evidence.chunk_id,)).fetchone()
    if not row:return
    loc=decode_chunk_type(row['chunk_type'])[1]
    native=loc.get('native_document_id')
    source=(dict(owner='native_library',document_id=native,hash=loc.get('content_hash'),generation=loc.get('native_generation'),
                 revision=loc.get('metadata_revision'),course_id=loc.get('routed_course_id') or loc.get('course_id')) if native else
            dict(owner='canonical',document_id=evidence.document_id,hash=row['content_hash']))
    exact=loc.get('mm_locator')
    if context and context.get('mm_parent_manifest') and context.get('mm_frame_pts_ms') is not None:
        frame=dict(kind='video_frame',schema_version=2,frame_pts_ms=context['mm_frame_pts_ms'],
                   asset_id=native,alignment='user_supplied',parent_source_ref=context['mm_parent_manifest'])
        if exact and exact.get('bbox'):frame['bbox']=exact['bbox']
        exact=validate_locator(frame)
    if not exact:
        if loc.get('page'):exact=dict(schema_version=2,kind='pdf_page',page=loc['page'])
        elif loc.get('slide'):exact=dict(schema_version=2,kind='pptx_slide',slide=loc['slide'])
        else:exact=dict(schema_version=0,kind='legacy_unavailable')
    connection.execute('INSERT INTO tutor_evidence_snapshots VALUES(?,?,?,?,?,?,?)',
        (uuid.uuid4().hex,turn_id,evidence.citation_label,canonical(source),canonical(exact),loc.get('filename',row['path_key']),loc.get('mm_artifact_hash','')))


def resolve_snapshot(connection,snapshot_id,library):
    row=connection.execute('SELECT * FROM tutor_evidence_snapshots WHERE id=?',(snapshot_id,)).fetchone()
    if not row:raise ValueError('Historical evidence snapshot unavailable')
    source=json.loads(row['source_json']);loc=validate_locator(json.loads(row['locator_json']))
    if source['owner']!='native_library':raise ValueError('Exact original version is unavailable for this legacy source')
    doc=library.get(source['document_id'])
    if doc['trashed_at'] or source_ref(doc)!=source or not doc['indexing_enabled']:raise ValueError('Original version or permission changed; historical source is unavailable')
    from .native_document_library import _verified_original
    original=_verified_original(library.root,doc)
    if row['artifact_hash']:
        with library.connection() as native:
            artifact=native.execute('SELECT 1 FROM mm_artifacts WHERE document_id=? AND source_json=? AND content_hash=?',
                (doc['id'],row['source_json'],row['artifact_hash'])).fetchone()
        if not artifact:raise ValueError('Historical evidence artifact is unavailable')
    result=dict(document_id=doc['id'],locator=loc,title=row['title'],source=source,_original_path=original,mime=doc['mime'])
    if loc['kind']=='video_frame':
        with library.connection() as native:
            manifest=native.execute('SELECT * FROM mm_lecture_manifests WHERE id=?',(loc.get('parent_source_ref'),)).fetchone()
            if not manifest:raise ValueError('Supplied frame manifest unavailable')
            expected=next((f for f in json.loads(manifest['frames_json']) if f['document_id']==doc['id'] and f['timestamp_ms']==loc['frame_pts_ms'] and f['source']==source),None)
            parent=native.execute('SELECT * FROM documents WHERE id=?',(manifest['transcript_id'],)).fetchone()
            if not expected or not parent or parent['trashed_at'] or source_ref(dict(parent))!=json.loads(manifest['source_json']):raise ValueError('Supplied frame parent version unavailable')
            _verified_original(library.root,dict(parent))
    if loc['kind']=='transcript_cue':
        from personal_learning_assistant.ingestion.extractors import TranscriptExtractor
        cues=TranscriptExtractor().extract(original.read_bytes(),source_name=doc['original_name'])
        cue=next((u for u in cues if u.timestamp_start_ms==loc['start_ms'] and u.timestamp_end_ms==loc['end_ms']),None)
        if not cue:raise ValueError('Exact transcript cue is unavailable')
        result['cue_text']=cue.text
    return result
