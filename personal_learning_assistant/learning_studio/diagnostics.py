"""Mechanical review cues for validated packages; never a semantic certificate."""
import re


def quality_diagnostics(module):
    warnings=[]
    def add(field,code,message,pages):
        warnings.append({'field':field,'code':code,'message':message,'pages':sorted(set(pages)),
            'repair':'Compare the cited original privately. Preserve qualifications and nontext material in a new reviewed revision; this mechanical cue is not semantic approval.'})
    cited={page for block in module['revision'] for page in block['pages']}
    missing=[p['page'] for p in module['pages'] if p['page'] not in cited]
    if missing:add('revision','revision-page-omission','Some physical source pages have no revision citation. Citations alone do not establish completeness.',missing)
    for i,section in enumerate(module['sections']):
        number=re.match(r'^\s*(?:slide|page)\s+(\d+)\b',section['title'],re.I)
        if number and int(number[1]) not in section['pages']:
            add(f'sections[{i}].title','numbering-locator-mismatch','Title page/slide number disagrees with the lesson locators.',section['pages'])
        for j,block in enumerate(section['blocks']):
            if set(block['pages'])-set(section['pages']):
                add(f'sections[{i}].blocks[{j}].pages','lesson-citation-mismatch','Block cites pages outside its lesson. Check cross-page attribution.',block['pages'])
    blocks=[(f'sections[{i}].blocks[{j}]',b) for i,s in enumerate(module['sections']) for j,b in enumerate(s['blocks'])]
    blocks += [(f'revision[{i}]',b) for i,b in enumerate(module['revision'])]
    for field,block in blocks:
        value=block.get('text','')
        if value.rstrip().endswith(('...','…')):
            add(field,'possible-truncation','Text ends in an ellipsis; check intentional omission versus truncated notes.',block['pages'])
        if block['kind']=='source':
            extracts='\n'.join(p['text'] for p in module['pages'] if p['page'] in block['pages'])
            normalize=lambda text:' '.join(text.split())
            if normalize(value) not in normalize(extracts):
                add(field,'source-extract-mismatch','Verbatim-labelled text does not occur in the cited extracted text. Original layout/OCR may need review.',block['pages'])
    for page in module['pages']:
        on_page=[b for _,b in blocks if page['page'] in b['pages']]
        if re.search(r'\b(diagram|chart|figure|equation|matrix|table)\b',page['text'],re.I) and not any(b['kind'] in {'image','table','graph'} for b in on_page):
            add(f"pages[{page['page']-1}]",'nontext-review-needed','Extract mentions visual or mathematical material without a structured visual aid. Inspect the original; text may be insufficient.',[page['page']])
    return warnings
