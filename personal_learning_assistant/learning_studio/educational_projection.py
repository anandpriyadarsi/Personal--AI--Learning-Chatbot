"""Versioned educational/Tutor projections of existing authored owner blocks."""
from datetime import datetime, timezone
import copy
import json
from .read_snapshot import frozen_studio
from .validation import PackageError, identity, integer, require, text, validate_mapping, validate_package

def build_preview(studio,module_id,revision,*,catalogue=None,as_of=None):
    identity(module_id);integer(revision,1,1_000_000)
    stamp=as_of or datetime.now(timezone.utc)
    require(isinstance(stamp,datetime) and stamp.tzinfo is not None,'Aware preview clock required.')
    s=frozen_studio(studio,catalogue=catalogue)
    p=s.module(module_id,revision,public=False);p.pop('history',None)
    raw=s.source(module_id,revision)
    with s.store.connection() as con:
        assets={r['name']:r['bytes'] for r in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?',(module_id,revision))}
    structural=copy.deepcopy(p);structural['mapping']=None
    validate_package(structural,{'available':False,'courses':[]},raw,assets)
    status='unverified'
    if p['mapping'] and p['mapping'].get('topic_id'):
        try:validate_mapping(p['mapping'],catalogue or {});status='reviewed_current_catalogue'
        except PackageError:pass
    def refs(pages):
        return [{'module_id':module_id,'module_revision':revision,'source_id':p['source']['source_id'],
            'source_sha256':p['source']['sha256'],'page':page,
            'semantic_status':p['pages'][page-1]['status'],
            'review_flags':list(p['pages'][page-1]['review_flags']),
            'url':f'/academic-evidence/learning/{module_id}/{revision}/source.pdf#page={page}'} for page in pages]
    def blocks(values):
        return [{'kind':b['kind'],'pages':list(b['pages']),'content':{k:copy.deepcopy(v) for k,v in b.items() if k not in {'kind','pages','answer'}},
            'source_refs':refs(b['pages']),'authority':'authored_owner_content'} for b in values]
    return {'schema':'anvaya.educational-note-projection.v1','as_of':stamp.astimezone(timezone.utc).isoformat(),
        'module':{'id':module_id,'revision':revision,'title':p['title']},
        'source':{**p['source'],'validation':'published_snapshot_validated','registry_freshness':'not_checked'},
        'mapping':copy.deepcopy(p['mapping']),'mapping_status':status,'sections':[{'id':sec['id'],'title':sec['title'],'pages':sec['pages'],
            'blocks':blocks(sec['blocks'])} for sec in p['sections']],
        'revision':blocks(p['revision']),
        'questions':[{'id':q['id'],'revision':q['revision'],'prompt':q['prompt'],'pages':q['pages'],
            'url':f'/learning/modules/{module_id}/{revision}?view=practice&question={q["id"]}#question-{q["id"]}'} for q in p['questions']],
        'independence':'unknown','mastery':'unknown','semantic_review':'Authored fidelity flags are not an independent source certification.'}

def tutor_handoff(studio,payload,*,catalogue=None,as_of=None):
    require(isinstance(payload,dict) and set(payload)=={'module_id','module_revision','source_sha256','pages','student_question'},'Unsupported Tutor handoff fields.')
    text(payload['student_question'],2000)
    preview=build_preview(studio,payload['module_id'],payload['module_revision'],catalogue=catalogue,as_of=as_of)
    require(payload['source_sha256']==preview['source']['sha256'],'Source revision changed.',409)
    pages=payload['pages']
    require(isinstance(pages,list) and 1<=len(pages)<=20,'Choose 1–20 distinct source pages.')
    require(all(type(p) is int and 1<=p<=preview['source']['page_count'] for p in pages),'Invalid source page.')
    require(len(set(pages))==len(pages),'Choose distinct source pages.')
    blocks=[]
    for section in preview['sections']:
        for b in section['blocks']:
            if set(b['pages'])<=set(pages) and b['kind']!='recall' and len(blocks)<6:
                blocks.append(b)
    result={'schema':'anvaya.learning-tutor-handoff.v1','module':preview['module'],'source':preview['source'],
        'mapping_status':preview['mapping_status'],'student_question':payload['student_question'],
        'pages':pages,'authored_blocks':blocks,'independence':'unknown','mastery':'unknown',
        'automatic_tutor_consumption':False,'provider_used':False,
        'consumer_status':'manual_read_only_handoff; automatic module-bound Tutor consumer unavailable',
        'help_steps':['Locate the exact cited source page.','Identify the relevant authored definition or worked example.',
                      'Try one step yourself and explain your choice.','Teach the idea back in your own words; independent recheck is still required.']}
    while blocks and len(json.dumps(result,ensure_ascii=False).encode())>32000:blocks.pop()
    require(len(json.dumps(result,ensure_ascii=False).encode())<=32000,'Tutor handoff exceeds its bound.',413)
    return result
