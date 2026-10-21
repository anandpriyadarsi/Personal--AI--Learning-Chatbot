"""Metadata-only revision/reflection projection from one frozen Learning owner."""
import json
from urllib.parse import quote
from personal_learning_assistant.domain.academic_evidence import AcademicEvidenceRecord as Record, SourceReference as Ref
from personal_learning_assistant.learning_studio.validation import PackageError, require


def project(studio, package, *, as_of, mapping_status):
    from .academic_evidence_service import _stamp, MAX_EVENTS
    result=[];mapping=package.get('mapping') or {};sections={s['id']:s for s in package['sections']}
    with studio.store.connection() as con:
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table,kind in [('reading_events','learning_revision'),('engagement_events','learning_reflection')]:
            if table not in tables:continue
            where=" AND json_extract(payload_json,'$.view')='revision'" if table=='reading_events' else ''
            rows=con.execute('SELECT event_id,payload_json,timestamp FROM '+table+
                ' WHERE owner=? AND module_id=? AND revision=?'+where+' ORDER BY seq LIMIT ?',
                ('local-owner',package['module_id'],package['module_revision'],MAX_EVENTS+1)).fetchall()
            require(len(rows)<=MAX_EVENTS,'Revision/reflection event inventory exceeds its bound.',413)
            for row in rows:
                reasons=set()
                stamp=_stamp(row['timestamp'],as_of,reasons)
                try:payload=json.loads(row['payload_json'])
                except (ValueError,TypeError) as error:raise PackageError('Invalid owner reflection metadata.',503) from error
                require(isinstance(payload,dict),'Invalid owner reflection metadata.',503)
                section=sections.get(payload.get('section_id'))
                if not section:reasons.add('section_identity_unavailable')
                pages=section['pages'] if section else []
                if kind=='learning_reflection':
                    scope=payload.get('block_scope','section')
                    blocks=package['revision'] if scope=='revision' else section['blocks'] if section else []
                    index=payload.get('block_index')
                    if scope not in {'section','revision'} or type(index) is not int or not 0<=index<len(blocks):
                        reasons.add('block_identity_unavailable');pages=[]
                    else:pages=blocks[index]['pages']
                    outcome=payload.get('action')
                    if outcome not in {'reflection','reveal','remembered'}:reasons.add('reflection_action_invalid')
                else:
                    outcome='revision_opened'
                    # Saved events do not contain the rendered budget selection
                    # or what was actually read. Never substitute section pages.
                    pages=[]
                    reasons.add('rendered_revision_selection_not_recorded')
                blocked=bool(reasons-{'rendered_revision_selection_not_recorded'})
                if kind=='learning_revision':reasons.add('time_budget_is_not_actual_effort')
                refs=tuple(Ref('learning_source',package['source']['source_id'],package['source']['sha256'],
                    package['module_revision'],page,None if blocked else '/academic-evidence/learning/'+
                    quote(package['module_id'],safe='')+'/'+str(package['module_revision'])+'/source.pdf#page='+str(page)) for page in pages)
                if kind=='learning_revision':
                    refs=(Ref('learning_source',package['source']['source_id'],package['source']['sha256'],
                        package['module_revision'],url=None if blocked else '/academic-evidence/learning/'+
                        quote(package['module_id'],safe='')+'/'+str(package['module_revision'])+'/source.pdf'),)
                namespace='learning_reading_event' if table=='reading_events' else 'learning_engagement_event'
                refs+=(Ref(namespace,row['event_id']),)
                result.append(Record(kind,namespace+':'+row['event_id'],mapping.get('course_id'),mapping.get('topic_id'),
                    'blocked' if blocked else 'revision_signal' if kind=='learning_revision' else 'self_reflection_signal',
                    'published_snapshot_validated',mapping_status,'self_report','unverified' if blocked else outcome,
                    stamp,refs,tuple(sorted(reasons)),module_revision=package['module_revision']))
    return tuple(result)
