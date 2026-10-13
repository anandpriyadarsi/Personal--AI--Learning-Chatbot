"""Read-only package preflight. No registry/store initialization or checksum repairs."""
import copy
import hashlib
from .validation import PackageError, validate_package, locators, validate_mapping, validate_block, shape


def preflight(package, source, assets, catalogue, *, source_id, coverage=None):
    errors=[]
    def error(field,message): errors.append({'field':field,'message':message,'repair':'Correct the authored manifest against the registered original; do not alter source bytes or expected checksums.'})
    if not isinstance(package,dict):
        error('package','Expected a structured object.')
        return {'valid':False,'errors':errors}
    manifest=package.get('source')
    try:
        shape(manifest, {'source_id', 'sha256', 'filename', 'media_type', 'page_count'})
    except PackageError as exc:
        error('source',str(exc))
        return {'valid':False,'errors':errors}
    if manifest.get('source_id')!=source_id:error('source.source_id','Source ID does not match the explicitly supplied registry identity.')
    if manifest.get('sha256')!=hashlib.sha256(source).hexdigest():error('source.sha256','Registered original source hash mismatch.')
    if isinstance(package,dict) and isinstance(manifest,dict):
        count=manifest.get('page_count')
        if type(count) is int and 1<=count<=500:
            for collection in ('questions','sections','revision'):
                values=package.get(collection)
                if isinstance(values,list):
                    for i,item in enumerate(values):
                        if not isinstance(item,dict):continue
                        try:locators(item.get('pages'),count)
                        except PackageError as exc:error(f'{collection}[{i}].pages',str(exc))
                        if collection=='sections' and isinstance(item.get('blocks'),list):
                            for j,block in enumerate(item['blocks']):
                                try:validate_block(block,count,assets,schema=package.get('schema'))
                                except PackageError as exc:error(f'sections[{i}].blocks[{j}]',str(exc))
        try:validate_mapping(package.get('mapping'),catalogue)
        except PackageError as exc:error('mapping',str(exc))
    try:
        valid=validate_package(package,catalogue,source,assets)
        if coverage is not None:
            from .coverage import validate_coverage
            validate_coverage(coverage,valid,source,assets)
    except PackageError as exc:
        if not errors:error('package',str(exc))
    if errors:return {'valid':False,'errors':errors}
    public=copy.deepcopy(valid)
    for question in public['questions']:
        question.pop('correct_index');question.pop('explanation')
    assert all('correct_index' not in q and 'explanation' not in q for q in public['questions'])
    return {'valid':True,'errors':[], 'module_id':valid['module_id'],'revision':valid['module_revision'],
        'source_sha256':manifest['sha256'],'pages':len(valid['pages']),'questions':len(valid['questions']),
        'private_key_projection':'excluded','mapping':'reviewed-current' if valid['mapping'] else 'unmapped',
        'semantic_review':'verified' if all(p['status']=='verified' for p in valid['pages']) else 'needs_review',
        'coverage':'validated' if coverage is not None else 'not supplied; semantic coverage unresolved'}
