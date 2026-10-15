"""Read-only, deterministic review suggestions; self-report never closes grading."""
from copy import deepcopy
from .validation import require


def guided_revision(module, weak, budget='full', engagement=None):
    require(budget in {'5','15','full'}, 'Unknown revision time budget.',404)
    cards=[(i,b) for i,b in enumerate(module['revision']) if b['kind']=='recall']
    misses={page for question in weak if question.get('incorrect_count',0)>0 for page in question.get('pages',[])}
    reports={}
    for event in engagement or []:
        if event.get('block_scope')=='revision' and type(event.get('block_index')) is int:
            reports.setdefault(event['block_index'],event)
    revisit={i for i,event in reports.items() if event.get('action')=='remembered' and event.get('response')=='revisit'}
    unreviewed={p['page'] for p in module.get('pages',[]) if p['status']!='verified'}
    traps={page for s in module['sections'] for b in s['blocks'] if b['kind']=='misconception' for page in b['pages']}
    ordered=sorted(cards,key=lambda item:(item[0] not in revisit,not bool(misses.intersection(item[1]['pages'])),
                                        not bool(traps.intersection(item[1]['pages'])),not bool(unreviewed.intersection(item[1]['pages']))))
    selected=cards if budget=='full' else ordered[:4 if budget=='5' else 12]
    def priority(index,card):
        reasons=[]
        if index in revisit:reasons.append('You explicitly marked this card for revisiting (self-report).')
        if misses.intersection(card['pages']):reasons.append('Cited pages are linked to recorded graded misses.')
        if traps.intersection(card['pages']):reasons.append('Cited pages include an authored misconception; this is not an exam prediction.')
        if unreviewed.intersection(card['pages']):reasons.append('Original-page fidelity still needs author review; compare the source.')
        return ' '.join(reasons) or 'Authored order; no recorded risk signal for this card.'
    revision_pages={page for b in module['revision'] for page in b['pages']}
    all_pages={p['page'] for p in module.get('pages',[])}
    selected_pages={page for _,b in selected for page in b['pages']}
    queue=[];seen=set();versions={q['id']:q['revision'] for q in module.get('questions',[])}
    for question in weak:
        qid=question.get('question_id');qrev=question.get('question_revision',versions.get(qid,1))
        if not qid or (qid,qrev) in seen:continue
        seen.add((qid,qrev))
        recovered=question.get('status')=='recovered_needs_recheck'
        attempts=question.get('attempt_count',0)
        queue.append({'kind':'graded_recheck','question_id':qid,'question_revision':qrev,
                      'pages':sorted(set(question.get('pages',[]))), 'status':question.get('status','needs_review'),
                      'reason':f"Previously missed {qid} (question revision {qrev}); {'a correct retry still needs a deliberate recheck' if recovered else 'the latest graded response was incorrect'}. {attempts} recorded attempts are repeated practice, not independent evidence."})
    for i,card in cards:
        if i in revisit:
            queue.append({'kind':'self_report','block_index':i,'pages':card['pages'],'prompt':card['text'],
                          'reason':'You explicitly marked this recall card for revisiting. This is ungraded self-report.'})
    comparisons=[{'section_id':s['id'],'title':s['title'],'pages':s['pages']} for s in module['sections'] if any(b['kind'] in {'table','graph'} for b in s['blocks'])]
    comparisons.sort(key=lambda s:not bool(misses.intersection(s['pages'])))
    reason=('Recall cards touching pages with recorded misses come first after cards explicitly marked revisit. A correct retry remains recovered and needs recheck; repeated retries do not create independent evidence.' if misses else 'No recorded misses in this revision. Explicit revisit cards come first in quick modes, then authored order; this is a suggested review sequence, not a diagnosis of weakness.')
    reason+=' Authored misconceptions and pages needing fidelity review break ties; these are review cues, not certified weaknesses.'
    return deepcopy({'cards':[b for _,b in selected],
                     'items':[{'index':i,'block':b,'reason':priority(i,b)} for i,b in selected],
                     'omitted_blocks':len(module['revision'])-len(selected) if budget!='full' else 0,
                     'quick_unavailable':budget!='full' and not cards,
                     'coverage':{'revision_pages':sorted(revision_pages),
                         'missing_revision_pages':sorted(all_pages-revision_pages),
                         'selected_pages':sorted(selected_pages if budget!='full' else revision_pages),
                         'omitted_quick_pages':sorted(all_pages-selected_pages) if budget!='full' else [],
                         'unreviewed_pages':sorted(unreviewed),
                         'lesson_pages':sorted({page for s in module['sections'] for page in s['pages']}),
                         'semantic_certification':False},
                     'weak_pages':sorted(misses),'selection_reason':reason,
                     'queue':queue[:100],'queue_total':len(queue),'queue_truncated':len(queue)>100,
                     'comparisons':comparisons[:3 if budget!='full' else 20],
                     'easy_to_forget':[b for _,b in ordered[:3]],'is_subset':budget!='full',
                     'checklist':['Attempt the selected recall prompts before revealing answers.',
                                  'Explain one source-linked distinction without copying the notes.',
                                  'Check original-page wording and retain attribution or uncertainty.',
                                  'Recheck recorded mistakes; a correct retry is not proof of mastery.',
                                  'Open Full revision for all remaining notes and lists.']})
