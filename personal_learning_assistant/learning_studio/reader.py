"""Validated URL selections; no writes and no assessment keys."""
from .validation import require


def parse_page(value,count):
    require(isinstance(value,str) and 0<len(value)<=6 and value.isascii() and value.isdigit(), 'Invalid source page.',404)
    page=int(value)
    require(1<=page<=count,'Requested source page does not exist.',404)
    return page


def select(module,args,weak,engagement=None):
    section_id=args.get('section',module['sections'][0]['id'])
    selected=next((s for s in module['sections'] if s['id']==section_id),None)
    require(selected is not None,'Requested lesson does not exist in this revision.',404)
    page_value=args.get('page',str(selected['pages'][0]))
    page=parse_page(page_value,module['source']['page_count'])
    selected_page=next((p for p in module['pages'] if p['page']==page),None)
    require(selected_page is not None,'Requested source page does not exist.',404)
    mode=args.get('mode','mixed');require(mode in {'mixed','lesson','recheck'},'Unknown practice mode.',404)
    questions=module['questions']
    if mode=='lesson':questions=[q for q in questions if set(q['pages'])&set(selected['pages'])]
    if mode=='recheck':
        missed={q['question_id'] for q in weak};questions=[q for q in questions if q['id'] in missed]
    qid=args.get('question');index=0
    if qid:
        index=next((i for i,q in enumerate(questions) if q['id']==qid),None)
        require(index is not None,'Requested question is unavailable in this practice selection.',404)
    budget=args.get('budget','full');require(budget in {'5','15','full'},'Unknown revision budget.',404)
    revision=module['revision']
    # Quick recall is an explicit subset; full companion remains one action away.
    cards=[b for b in revision if b['kind']=='recall']
    quick=(cards or revision)[:4 if budget=='5' else 12]
    from .revision import guided_revision
    guide=guided_revision(module,weak,budget,engagement=engagement)
    from .rendering import authored_headings
    outline=[dict(h,anchor=f"ls-block-{module['sections'][0]['id']}-{i}-heading-{h['index']}") for i,b in enumerate(revision) if b['kind']!='recall' and 'text' in b for h in authored_headings(b['text'])]
    return {'revision_outline':outline[:100], 'revision_outline_total':len(outline), 'revision_guide':guide,'selected_section':selected,'section_index':module['sections'].index(selected),
            'visible_sections':module['sections'] if args.get('all')=='1' else [selected],
            'selected_page':selected_page,'visible_pages':module['pages'] if args.get('pages')=='all' else [selected_page],
            'practice_questions':questions if args.get('questions')=='all' else questions[index:index+1],
            'question_lessons':{q['id']:next((section['id'] for section in module['sections'] if set(section['pages'])&set(q['pages'])),selected['id']) for q in module['questions']},'question_index':index,'question_total':len(questions),'question_choices':questions,'practice_mode':mode,
            'revision_blocks':revision if budget=='full' else (guide['cards'] or quick),'revision_budget':budget}
