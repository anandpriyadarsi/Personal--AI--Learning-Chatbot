"""Supplemental exact-revision evidence; a retry or elapsed day is not independence."""
from datetime import datetime,timedelta,timezone
import json
from .service import OWNER

MAX_QUESTIONS=100
REVIEW_INTERVAL_HOURS=24

def quality_report(service,module_id,revision,*,at=None,question_ids=None):
    module=service.module(module_id,revision);service.source(module_id,revision)
    at=at or datetime.now(timezone.utc)
    with service.store.connection() as con:
        attempts=con.execute('SELECT question_id,question_revision,correct,timestamp FROM attempts WHERE owner=? AND module_id=? AND revision=? AND source_hash=? ORDER BY seq',
            (OWNER,module_id,revision,module['source']['sha256'])).fetchall()
        version=con.execute('PRAGMA user_version').fetchone()[0]
        engagement=[] if version==1 else con.execute('SELECT payload_json FROM engagement_events WHERE owner=? AND module_id=? AND revision=?',(OWNER,module_id,revision)).fetchall()
        readings=[] if version==1 else con.execute('SELECT payload_json FROM reading_events WHERE owner=? AND module_id=? AND revision=?',(OWNER,module_id,revision)).fetchall()
    by_question={}
    for row in attempts:by_question.setdefault((row['question_id'],row['question_revision']),[]).append(row)
    summary=dict(total_questions=len(module['questions']),unanswered=0,wrong=0,correct=0,retry_correct=0,distinct_attempted=len(by_question),attempt_events=len(attempts))
    questions=[]
    for q in module['questions']:
        rows=by_question.get((q['id'],q['revision']),[]);wrong=[r for r in rows if not r['correct']]
        status='never_practised' if not rows else ('needs_review' if not rows[-1]['correct'] else 'recovered_needs_recheck' if wrong else 'checked_correct')
        summary[{'never_practised':'unanswered','needs_review':'wrong','recovered_needs_recheck':'retry_correct','checked_correct':'correct'}[status]]+=1
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
        questions.append({'question_id':q['id'],'question_revision':q['revision'],'pages':q['pages'],'status':status,
            'attempt_count':len(rows),'incorrect_count':len(wrong),'last_attempt':rows[-1]['timestamp'] if rows else None,
            'last_incorrect':wrong[-1]['timestamp'] if wrong else None,'suggestion':suggestion,'suggested_after':due,
            'reason':reason,'fresh_question_id':fresh,'independent_recheck':'unverified / insufficient evidence'})
    questions.sort(key=lambda q:({'needs_review':0,'recovered_needs_recheck':1,'never_practised':2,'checked_correct':3}[q['status']],q['suggestion']!='due'))
    selected=questions if question_ids is None else [q for q in questions if q['question_id'] in question_ids]
    actions=[json.loads(r['payload_json'])['action'] for r in engagement]
    return {'schema':'anvaya.learning-quality.v1','owner_scope':OWNER,'module_id':module_id,'module_revision':revision,
        'source':module['source'],'authority':'supplemental low-stakes practice and ungraded self-report','generated_at':at.isoformat(),
        'summary':summary,'questions':selected[:MAX_QUESTIONS],'questions_total':len(selected),'questions_truncated':len(selected)>MAX_QUESTIONS,
        'self_reports':{'reflection_events':actions.count('reflection'),'remembered_events':actions.count('remembered'),
            'revealed_events':actions.count('reveal'),'reading_events':len(readings),
            'label':'Event counts only; reading, reveal, remembering and teach-back are ungraded self-report.'},
        'semantic_review_pages':sum(p['status']!='verified' for p in module['pages']),'independent_recheck_confirmed':False,
        'limitations':'Distinct question versions are counted once per immutable module revision. Page overlap suggests related practice, not validated conceptual equivalence. No mastery, official grade, recovery eligibility, planner or Tutor memory authority.'}
