"""Read-only guided recall selection; misses guide rereading, never mastery."""
from copy import deepcopy
from .validation import require


def guided_revision(module, weak, budget='full'):
    require(budget in {'5','15','full'}, 'Unknown revision time budget.',404)
    cards=[b for b in module['revision'] if b['kind']=='recall']
    misses={page for question in weak if question.get('incorrect_count',0)>0 for page in question.get('pages',[])}
    # Stable sort retains author order within each group; each card appears once.
    ordered=sorted(cards,key=lambda b:not bool(misses.intersection(b['pages'])))
    limit=4 if budget=='5' else 12
    selected=cards if budget=='full' else ordered[:limit]
    comparisons=[]
    for section in module['sections']:
        if any(b['kind'] in {'table','graph'} for b in section['blocks']):
            comparisons.append({'section_id':section['id'],'title':section['title'],'pages':section['pages']})
    comparisons.sort(key=lambda s:not bool(misses.intersection(s['pages'])))
    reason=('Recall cards touching pages with recorded misses come first. A correct retry remains recovered and needs recheck; repeated retries do not create independent evidence.' if misses else 'No recorded misses in this revision. Cards follow authored order; this is a suggested review sequence, not a diagnosis of weakness.')
    return deepcopy({'cards':selected,'weak_pages':sorted(misses),'selection_reason':reason,
                     'comparisons':comparisons[:3 if budget!='full' else 20],
                     'easy_to_forget':ordered[:3], 'is_subset':budget!='full',
                     'checklist':['Attempt the selected recall prompts before revealing answers.',
                                  'Explain one source-linked distinction without copying the notes.',
                                  'Check original-page wording and retain attribution or uncertainty.',
                                  'Recheck recorded mistakes; a correct retry is not proof of mastery.',
                                  'Open Full revision for all remaining notes and lists.']})
