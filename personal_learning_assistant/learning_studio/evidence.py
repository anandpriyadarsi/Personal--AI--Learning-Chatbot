"""Read-only practice evidence, separating historical mapping from live validity."""
import json
from .validation import PackageError,validate_mapping


def label(count):
    return 'No evidence' if not count else ('Limited evidence' if count<5 else 'Low-stakes practice evidence')


def summarize(service):
    from .service import OWNER
    result={'schema':'anvaya.learning-evidence-summary.v1','authority':'low-stakes-practice',
            'attempts':0,'ever_missed':0,'latest_correct':0,'reviewed_attempts':0,'unmapped_attempts':0,
            'historically_mapped_attempts':0,'unique_questions':0,'currently_wrong':0,'recovered_needs_recheck':0,
            'groups':[],'trend':[],'evidence_label':'No evidence','tutor_available':False,
            'tutor_reason':'Existing Tutor entry point does not consume this versioned evidence contract.'}
    with service.store.connection() as con:
        if con is None:return result
        rows=con.execute('SELECT a.*,m.package_json FROM attempts a JOIN modules m USING(module_id,revision) WHERE owner=? ORDER BY seq',(OWNER,)).fetchall()
    cat=service.catalogue_loader();groups={};questions={};trend={};states={}
    for r in rows:
        mk=(r['module_id'],r['revision'])
        if mk not in states:
            p=json.loads(r['package_json']);mapping=p['mapping'];status='unmapped'
            if mapping:
                try:validate_mapping(mapping,cat);status='reviewed_current_catalogue'
                except PackageError:status='needs_review'
            states[mk]=(mapping,status)
        mapping,status=states[mk]
        key=(mapping['course_id'] if mapping else None,mapping['topic_name'] if mapping else None,status)
        g=groups.setdefault(key,{'course_id':key[0],'topic_name':key[1],'mapping_status':status,'attempts':0,'incorrect':0,'questions':set(),
                                 'attribution':'Historical lecture mapping; question-level topic attribution has not been independently reviewed.'})
        qkey=(r['module_id'],r['revision'],r['question_id'],r['question_revision'])
        g['questions'].add(qkey);g['attempts']+=1;g['incorrect']+=not r['correct']
        q=questions.setdefault(qkey,{'ever_wrong':False,'latest_correct':False})
        q['ever_wrong']|=not r['correct'];q['latest_correct']=bool(r['correct'])
        day=trend.setdefault(r['timestamp'][:10],{'day':r['timestamp'][:10],'attempts':0,'incorrect':0})
        day['attempts']+=1;day['incorrect']+=not r['correct']
        result['historically_mapped_attempts']+=mapping is not None
        result['reviewed_attempts']+=status=='reviewed_current_catalogue'
        result['unmapped_attempts']+=mapping is None
    for g in groups.values():
        g['unique_questions']=len(g.pop('questions'));g['evidence_label']=label(g['unique_questions'])
    result.update(attempts=len(rows),unique_questions=len(questions),groups=list(groups.values()),trend=list(trend.values()),
                  ever_missed=sum(q['ever_wrong'] for q in questions.values()),latest_correct=sum(q['latest_correct'] for q in questions.values()),
                  currently_wrong=sum(not q['latest_correct'] for q in questions.values()),
                  recovered_needs_recheck=sum(q['ever_wrong'] and q['latest_correct'] for q in questions.values()),evidence_label=label(len(questions)))
    return result
