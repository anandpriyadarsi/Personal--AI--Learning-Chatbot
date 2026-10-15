"""Versioned source-element locations, separate from semantic/factual certification.

Text inventory completeness is mechanical; mapping proves a notes location exists,
not that a paraphrase is true. Source fidelity needs the explicitly named reviewer.
"""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import re
import unicodedata
from .validation import PackageError, HASH, identity, integer, items, locators, require, shape, text

SCHEMA='anvaya.learning-coverage.v1'
MAX_ELEMENTS=4000


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def package_digest(package):
    p=copy.deepcopy(package);p.pop('history',None)
    return digest(p)


def normalized(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',value)).casefold()


def source_inventory(source):
    from pypdf import PdfReader
    try:
        pdf=PdfReader(io.BytesIO(source),strict=True)
        result=[]
        for page_num,page in enumerate(pdf.pages,1):
            for line_num,line in enumerate((page.extract_text() or '').splitlines(),1):
                if line.strip():
                    result.append({'id':f'p{page_num:03}-line{line_num:04}','page':page_num,
                        'kind':'text','text':line,'locator':{'line':line_num}})
                    require(len(result)<=MAX_ELEMENTS,'Coverage inventory exceeds supported element count.',413)
        return result
    except PackageError:raise
    except Exception as error:raise PackageError('Coverage original PDF could not be inventoried.') from error


def block_text(block):
    if block['kind']=='source':return ''
    values=[]
    def visit(v):
        if isinstance(v,str):values.append(v)
        elif isinstance(v,dict):
            for key,value in v.items():
                if key not in {'id','kind','pages','widget','graph_type'}:visit(value)
        elif isinstance(v,list):
            for value in v:visit(value)
    visit(block)
    return '\n'.join(values)


def build_coverage(package, source, *, reviewer, method):
    inventory=source_inventory(source);coverage=[]
    for element in inventory:
        candidates=[(s,i,b) for s in package['sections'] for i,b in enumerate(s['blocks'])
                    if element['page'] in b['pages'] and block_text(b)]
        exact=next(((s,i,b) for s,i,b in candidates if normalized(element['text']) in normalized(block_text(b))),None)
        if exact:
            s,i,b=exact
            # The location quote is exact notes text, not a semantic-equivalence score.
            coverage.append({'element_id':element['id'],'state':'mapped','mappings':[
                {'section_id':s['id'],'block_index':i,'quote':block_text(b)[:600]}]})
        else:coverage.append({'element_id':element['id'],'state':'unresolved','reason':'No exact text location: inspect the authored paraphrase or visual meaning.','mappings':[]})
    sha=hashlib.sha256(source).hexdigest();pd=package_digest(package)
    return {'schema':SCHEMA,'module_id':package['module_id'],'module_revision':package['module_revision'],
            'source_sha256':sha,'package_digest':pd,'inventory':inventory,'coverage':coverage,
            'review':{'status':'needs_review','reviewer':reviewer,'method':method,
                'reviewed_at':datetime.now(timezone.utc).isoformat(),'source_sha256':sha,'package_digest':pd,
                'inventory_digest':digest(inventory),'authority':'source-fidelity-only'},
            'external_facts':{'status':'pending','note':'Source fidelity does not certify external claims.'},
            'unresolved':[]}


def validate_coverage(record,package,source,assets=None):
    require(isinstance(record,dict),'Coverage companion must be an object.')
    try:encoded=json.dumps(record,allow_nan=False).encode()
    except (ValueError,TypeError,RecursionError) as error:raise PackageError('Coverage must be bounded JSON.') from error
    require(len(encoded)<=2_000_000,'Coverage exceeds2MB.',413)
    shape(record,{'schema','module_id','module_revision','source_sha256','package_digest','inventory','coverage','review','external_facts','unresolved'})
    require(record['schema']==SCHEMA,'Unsupported coverage schema.')
    require(record['module_id']==package['module_id'] and record['module_revision']==package['module_revision'],'Coverage module/revision mismatch.',409)
    source_sha=hashlib.sha256(source).hexdigest();pd=package_digest(package)
    require(record['source_sha256']==source_sha==package['source']['sha256'],'Coverage source changed; review is stale.',409)
    require(record['package_digest']==pd,'Coverage content changed; review is stale.',409)
    count=package['source']['page_count'];inventory=items(record['inventory'],MAX_ELEMENTS,nonempty=True);ids=set()
    allowed={'text','heading','bullet','list_member','named_term','table_header','table_cell','association_cell',
             'equation','caption','annotation','diagram_relationship','table_relationship','qualitative_scale','decoration','unsupported_visual'}
    for e in inventory:
        shape(e,{'id','page','kind','text','locator'},{'group','visual_evidence','relationship'})
        identity(e['id']);integer(e['page'],1,count);require(e['id'] not in ids,'Duplicate source element.');ids.add(e['id'])
        require(isinstance(e['kind'], str) and e['kind'] in allowed,'Unsupported inventory element type.');text(e['text'],10000)
        shape(e['locator'],set(),{'line','rect'})
        require(bool(e['locator']),'Source element needs a locator.')
        if 'line' in e['locator']:integer(e['locator']['line'],1,100000)
        if 'rect' in e['locator']:
            rect=e['locator']['rect'];require(isinstance(rect,list) and len(rect)==4 and all(type(x) in (int,float) and 0<=x<=10000 for x in rect) and rect[0]<=rect[2] and rect[1]<=rect[3],'Invalid visual source locator.')
        if 'group' in e:text(e['group'],200)
        if 'relationship' in e:text(e['relationship'],2000)
    # No missing text line can hide behind a complete page/image count.
    for expected in source_inventory(source):
        require(any(e['page']==expected['page'] and normalized(expected['text']) in normalized(e['text'])
                    for e in inventory),'Source text inventory omitted an original element.')
    reviews=items(record['coverage'],MAX_ELEMENTS,nonempty=True);seen=set();sections={s['id']:s for s in package['sections']}
    for entry in reviews:
        shape(entry,{'element_id','state','mappings'},{'reason'})
        identity(entry['element_id']);require(entry['element_id'] in ids and entry['element_id'] not in seen,'Invalid/duplicate coverage element.');seen.add(entry['element_id'])
        require(isinstance(entry['state'], str) and entry['state'] in {'mapped','unresolved','excluded'},'Unsupported coverage state.')
        mappings=items(entry['mappings'],30)
        if entry['state']=='mapped':require(bool(mappings),'Mapped coverage needs a notes location.')
        else:text(entry.get('reason'),2000)
        element=next(e for e in inventory if e['id']==entry['element_id'])
        if element['kind']=='unsupported_visual':require(entry['state']=='unresolved','Unsupported visual must remain unresolved.')
        if element['kind'] in {'diagram_relationship','table_relationship','qualitative_scale'} and entry['state']=='mapped':
            ev=element.get('visual_evidence');shape(ev or {},{'reviewer','method','preview_sha256'})
            text(ev['reviewer'],300);text(ev['method'],1000)
            preview=package['pages'][element['page']-1].get('preview')
            require(preview in (assets or {}) and hashlib.sha256(assets[preview]).hexdigest()==ev['preview_sha256'],'Visual inspection needs the matching owned preview.')
        for target in mappings:
            shape(target,{'section_id','block_index','quote'});text(target['quote'],10000)
            identity(target['section_id']);section=sections.get(target['section_id']);require(section is not None,'Coverage notes section does not exist.')
            index=integer(target['block_index'],0,len(section['blocks'])-1)
            block=section['blocks'][index]
            require(element['page'] in block['pages'] and target['quote'] in block_text(block),'Coverage points to unavailable or non-teaching text.')
    require(seen==ids,'Every inventoried element needs explicit coverage or an unresolved/excluded reason.')
    review=record['review'];shape(review,{'status','reviewer','method','reviewed_at','source_sha256','package_digest','inventory_digest','authority'})
    require(isinstance(review['status'], str) and review['status'] in {'needs_review','agent_reviewed'},'Coverage cannot certify external/instructor approval.')
    require(review['authority']=='source-fidelity-only' and review['source_sha256']==source_sha and review['package_digest']==pd and review['inventory_digest']==digest(inventory),'Coverage review assertion is stale.',409)
    text(review['reviewer'],300);text(review['method'],3000)
    try:datetime.fromisoformat(review['reviewed_at'])
    except (TypeError,ValueError) as error:raise PackageError('Invalid review date.') from error
    shape(record['external_facts'],{'status','note'});require(isinstance(record['external_facts']['status'], str) and record['external_facts']['status'] in {'pending','bounded_checks'},'External factual certainty is not established by coverage.');text(record['external_facts']['note'],5000)
    for item in items(record['unresolved'],100):
        shape(item,{'id','pages','snippet','issue','next_action'});identity(item['id']);locators(item['pages'],count)
        for key in ('snippet','issue','next_action'):text(item[key],6000)
    return copy.deepcopy(record)
