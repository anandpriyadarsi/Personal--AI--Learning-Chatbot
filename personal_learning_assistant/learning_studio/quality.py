"""Supplemental exact-revision evidence; a retry or elapsed day is not independence."""
from datetime import datetime,timedelta,timezone
import json
from .service import OWNER
from .validation import integer, require

MAX_QUESTIONS=100
REVIEW_INTERVAL_HOURS=24
REVIEW_STATES=frozenset({'all','needs_review','recovered_needs_recheck','never_practised','checked_correct'})

def quality_report(service,module_id,revision,*,at=None,question_ids=None,status='all',page=None,offset=0,limit=MAX_QUESTIONS):
    module=service.module(module_id,revision);service.source(module_id,revision)
    require(status in REVIEW_STATES,'Unknown revision queue status.')
    integer(offset,0,1000000);integer(limit,1,MAX_QUESTIONS)
    if page is not None:integer(page,1,module['source']['page_count'])
    at=at or datetime.now(timezone.utc)
    with service.store.connection() as con:
        attempts=con.execute('SELECT question_id,question_revision,correct,timestamp FROM attempts WHERE owner=? AND module_id=? AND revision=? AND source_hash=? ORDER BY seq',
            (OWNER,module_id,revision,module['source']['sha256'])).fetchall()
        version=con.execute('PRAGMA user_version').fetchone()[0]
        engagement=[] if version==1 else con.execute('SELECT payload_json FROM engagement_events WHERE owner=? AND module_id=? AND revision=?',(OWNER,module_id,revision)).fetchall()
        readings=[] if version==1 else con.execute('SELECT payload_json FROM reading_events WHERE owner=? AND module_id=? AND revision=?',(OWNER,module_id,revision)).fetchall()
    by_question={}
    for row in attempts:by_question.setdefault((row['question_id'],row['question_revision']),[]).append(row)
    current_versions={(q['id'],q['revision']) for q in module['questions']}
    summary=dict(total_questions=len(module['questions']),unanswered=0,wrong=0,correct=0,retry_correct=0,
        distinct_attempted=sum(key in current_versions for key in by_question),
        attempt_events=sum(len(rows) for key,rows in by_question.items() if key in current_versions))
    questions=[]
    for q in module['questions']:
        rows=by_question.get((q['id'],q['revision']),[]);wrong=[r for r in rows if not r['correct']]
        question_status='never_practised' if not rows else ('needs_review' if not rows[-1]['correct'] else 'recovered_needs_recheck' if wrong else 'checked_correct')
        summary[{'never_practised':'unanswered','needs_review':'wrong','recovered_needs_recheck':'retry_correct','checked_correct':'correct'}[question_status]]+=1
        fresh=next((other['id'] for other in module['questions'] if other['id']!=q['id'] and (other['id'],other['revision']) not in by_question and set(other['pages'])&set(q['pages'])),None)
        due=None;suggestion='unanswered';reason='Try this authored question without revealing explanations.'
        if rows:
            suggestion='insufficient';reason='A valid server timestamp is required for a timed suggestion.'
            try:
                timestamp=datetime.fromisoformat(rows[-1]['timestamp'])
                if timestamp.tzinfo is not None and timestamp<=at:
                    due=(timestamp+timedelta(hours=REVIEW_INTERVAL_HOURS)).isoformat()
                    suggestion='due' if at>=datetime.fromisoformat(due) else 'later'
                    reason='Suggested 24-hour gap after the latest attempt, not a validated mastery threshold. Reusing this item may test memory of its answer.'
            except (TypeError,ValueError):pass
        questions.append({'question_id':q['id'],'question_revision':q['revision'],'pages':q['pages'],'status':question_status,
            'attempt_count':len(rows),'incorrect_count':len(wrong),'last_attempt':rows[-1]['timestamp'] if rows else None,
            'last_incorrect':wrong[-1]['timestamp'] if wrong else None,'suggestion':suggestion,'suggested_after':due,
            'reason':reason,'fresh_question_id':fresh,'independent_recheck':'unverified / insufficient evidence'})
    questions.sort(key=lambda q:({'needs_review':0,'recovered_needs_recheck':1,'never_practised':2,'checked_correct':3}[q['status']],q['suggestion']!='due'))
    selected=[q for q in questions if (question_ids is None or q['question_id'] in question_ids)
        and (status=='all' or q['status']==status)
        and (page is None or page in q['pages'])]
    total=len(selected)
    pagination={'total':total,'offset':offset,'limit':limit,'shown':len(selected[offset:offset+limit]),
        'has_previous':offset>0,'has_next':offset+limit<total,
        'previous_offset':max(0,offset-limit),'next_offset':offset+limit if offset+limit<total else None}
    actions=[json.loads(r['payload_json'])['action'] for r in engagement]
    return {'schema':'anvaya.learning-quality.v1','owner_scope':OWNER,'module_id':module_id,'module_revision':revision,
        'source':module['source'],'authority':'supplemental low-stakes practice and ungraded self-report','generated_at':at.isoformat(),
        'summary':summary,'questions':selected[offset:offset+limit],'questions_total':total,
        'questions_truncated':offset>0 or pagination['has_next'],'pagination':pagination,
        'filters':{'status':status,'page':page},
        'self_reports':{'reflection_events':actions.count('reflection'),'remembered_events':actions.count('remembered'),
            'revealed_events':actions.count('reveal'),'reading_events':len(readings),
            'label':'Event counts only; reading, reveal, remembering and teach-back are ungraded self-report.'},
        'semantic_review_pages':sum(p['status']!='verified' for p in module['pages']),'independent_recheck_confirmed':False,
        'limitations':'This queue is a paginated, read-only view of distinct current question versions, not an exhaustive independent assessment. Distinct question versions are counted once per immutable module revision. Page overlap suggests related practice, not validated conceptual equivalence. No mastery, official grade, recovery eligibility, planner or Tutor memory authority.'}
