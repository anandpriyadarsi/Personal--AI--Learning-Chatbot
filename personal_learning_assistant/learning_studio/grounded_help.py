"""Stateless offline consumer. Authored data never becomes model instructions."""
from copy import deepcopy
import json
from .validation import require
from personal_learning_assistant.domain.academic_evidence import canonical_topic_reference

LEVELS = ('hint', 'concept', 'example', 'self_check')
PROMPTS = {
    'hint': 'Identify what the question asks. Locate the relevant definition or reasoning on the cited page. Try one step yourself.',
    'concept': 'Compare your reasoning with the authored material below. Where does your interpretation differ?',
    'example': 'Work through the source-linked example, then close it and explain each step in your own words.',
    'self_check': 'Return to the exact question and explain your method before checking. A retry after help is assisted practice; independent understanding still needs a separate recheck.',
}


def consume(preview, view, *, event_id, question_id, level, explicit_action=False):
    require(explicit_action is True, 'An explicit learner action is required.', 405)
    require(isinstance(level, str) and level in LEVELS, 'Choose hint, concept, example or self_check.')
    require(preview.get('schema')=='anvaya.educational-note-projection.v1', 'Unsupported note contract.')
    require(preview['module']=={'id':view.module_id,'revision':view.module_revision,'title':view.module_title}
        and preview['source']['sha256']==view.source_sha256, 'Source context changed.', 409)
    require(not view.historical_revision and view.mapping_status=='reviewed_current_catalogue',
        'Current reviewed course/source context is required.', 409)
    record = next((r for r in view.records if r.identifier==event_id and r.kind=='learning_practice'), None)
    require(record is not None and record.qualification=='study_signal' and record.outcome=='incorrect'
        and record.question_id==question_id and record.course_id==view.course_id and record.topic_id==view.topic_id,
        'Exact eligible mistake and question context required.', 409)
    question = next((q for q in preview['questions'] if q['id']==question_id and q['revision']==record.question_revision), None)
    require(question is not None, 'Question revision changed.', 409)
    pages = set(question['pages'])
    refs = [r for r in record.source_refs if r.kind=='learning_source']
    require({r.page for r in refs}==pages and all(r.sha256==view.source_sha256 and r.revision==view.module_revision for r in refs),
        'Question source association changed.', 409)
    allowed = {'definition','teaching','misconception'} if level=='concept' else {'example','table'} if level=='example' else set()
    blocks = []
    for section in preview['sections']:
        for block in section['blocks']:
            if block['kind'] not in allowed or not set(block['pages'])<=pages:
                continue
            # Revalidate nested refs rather than trusting a future producer change.
            require(len(block['source_refs'])==len(block['pages']) and
                {r['page'] for r in block['source_refs']}==set(block['pages']) and
                all(r['module_id']==view.module_id and r['module_revision']==view.module_revision and
                    r['source_sha256']==view.source_sha256 for r in block['source_refs']),
                'Foreign or stale authored citation.',409)
            candidate=deepcopy(block)
            # Only safe teaching fields; no graph, widget, key or arbitrary future field.
            candidate['content']={k:v for k,v in candidate['content'].items() if k in {'text','headers','rows'}}
            if len(blocks)<6 and len(json.dumps(blocks+[candidate],ensure_ascii=False).encode())<=18000:
                blocks.append(candidate)
    return {'schema':'anvaya.grounded-offline-help.v1','module':preview['module'],
        'topic_reference':canonical_topic_reference(view.course_id,view.topic_id),
        'event_id':event_id,'question':question,'source_sha256':view.source_sha256,
        'as_of':view.as_of,'evidence_fingerprint':view.fingerprint,'assistance_level':level,
        'prompt':PROMPTS[level], 'authored_blocks':blocks,
        'source_refs':[{'page':r.page,'url':r.url} for r in refs],
        'context_role':'untrusted_authored_content','provider_used':False,'session_persisted':False,
        'independence':'unknown','mastery':'unknown','history_status':'not_recorded',
        'missing_context':not blocks if allowed else False,
        'reason_status':'authored_guidance_only; individual misconception_not_diagnosed'}
