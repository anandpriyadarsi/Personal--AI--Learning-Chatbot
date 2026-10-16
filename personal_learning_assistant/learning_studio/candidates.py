"""Explicit teaching corrections: new staged notes, never source/key rewriting."""
from copy import deepcopy
from .coverage import block_text,package_digest
from .validation import integer,require,shape,text

class CandidateMixin:
    def create_candidate(self,module_id,revision,payload):
        shape(payload,{'target_revision','section_id','block_index','text','reason'})
        target=integer(payload['target_revision'],revision+1,1000000)
        text(payload['text']);text(payload['reason'],2000)
        original=self.module(module_id,revision,staged=True,public=False)
        candidate=deepcopy(original);candidate.pop('history')
        section=next((s for s in candidate['sections'] if s['id']==payload['section_id']),None)
        require(section is not None,'Unknown correction lesson.')
        index=integer(payload['block_index'],0,len(section['blocks'])-1);block=section['blocks'][index]
        require(block['kind'] in {'teaching','definition','example','misconception','objectives'},
                'Use canonical authored import for structured material; original extracts and keys cannot be edited here.')
        require(block['text']!=payload['text'],'No changed teaching material; no new revision is needed.',409)
        block['text']=payload['text'];candidate['module_revision']=target
        for page in candidate['pages']:
            if page['page'] in block['pages']:
                page['status']='needs_review'
                page['review_flags']=page['review_flags'][:29]+['Changed teaching candidate needs source comparison.']
        report=self.coverage_report(module_id,revision)
        if report:
            report=deepcopy(report)
            for entry in report['coverage']:
                entry['mappings']=[m for m in entry['mappings'] if not (
                    m['section_id']==section['id'] and m['block_index']==index and m['quote'] not in block_text(block))]
                if entry['state']=='mapped' and not entry['mappings']:
                    entry.update(state='unresolved',reason='Changed teaching invalidated the previous location quote; compare the original element.')
            report['module_revision']=target;report['package_digest']=package_digest(candidate)
            from .service import now
            report['review'].update(status='needs_review',reviewer='Correction candidate; review pending',
                method=f"Parent package {package_digest(original)}; changed {section['id']} block {index+1}. Reason: {payload['reason']}",
                reviewed_at=now(),package_digest=report['package_digest'])
        with self.store.connection() as con:
            assets={r['name']:r['bytes'] for r in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?',(module_id,revision))}
        return self.stage(candidate,assets,report,candidate=True)
