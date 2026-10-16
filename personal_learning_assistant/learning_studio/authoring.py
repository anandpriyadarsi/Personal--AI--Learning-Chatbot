"""Read-only package preflight. No registry/store initialization or checksum repairs."""
import copy
import hashlib
from .source_features import pdf_features
from .validation import PackageError, validate_package, locators, validate_mapping, validate_block, shape


def preflight(package, source, assets, catalogue, *, source_id, coverage=None):
    errors=[]
    warnings=[]
    def error(field,message,repair=None):
        errors.append({'field':field,'message':message,'repair':repair or 'Correct the authored manifest against the registered original; do not alter source bytes or expected checksums.'})
    def warning(field,code,message,repair):
        warnings.append({'field':field,'code':code,'message':message,'repair':repair})
    if not isinstance(package,dict):
        error('package','Expected a structured object.')
        return {'valid':False,'errors':errors}
    manifest=package.get('source')
    try:
        shape(manifest, {'source_id', 'sha256', 'filename', 'media_type', 'page_count'})
    except PackageError as exc:
        error('source',str(exc))
        return {'valid':False,'errors':errors}
    if not isinstance(source,bytes):
        error('source.original','Supply immutable original PDF bytes, not previews or extracted text.')
        return {'valid':False,'errors':errors}
    if manifest.get('source_id')!=source_id:error('source.source_id','Source ID does not match the explicitly supplied registry identity.')
    if manifest.get('sha256')!=hashlib.sha256(source).hexdigest():error('source.sha256','Registered original source hash mismatch.')
    if isinstance(package,dict) and isinstance(manifest,dict):
        count=manifest.get('page_count')
        if type(count) is int and 1<=count<=500:
            pages=package.get('pages')
            if isinstance(pages,list):
                for i,page in enumerate(pages):
                    if not isinstance(page,dict):continue
                    if 'preview' in page and not isinstance(page['preview'],str):
                        error(f'pages[{i}].preview','Preview must name an owned raster asset.')
                    elif page.get('preview') and (not isinstance(assets,dict) or page['preview'] not in assets):
                        error(f'pages[{i}].preview','Page preview is missing from owned assets.',
                              'Supply the named owned raster asset from this original page; never substitute another source.')
                    elif not page.get('preview'):
                        warning(f'pages[{i}].preview','missing-preview','No page preview supplied.',
                                'Supply an owned original-page raster preview when layout matters; text-only reading remains available.')
                    if not isinstance(page.get('text'),str):
                        error(f'pages[{i}].text','Extracted source text must be a string.')
                    elif not page['text'].strip():
                        warning(f'pages[{i}].text','missing-excerpt','No extracted source text supplied.',
                                'Inspect the original page and supply a faithful text alternative, or document nontext/unavailable content in coverage.')
            for collection in ('questions','sections','revision'):
                values=package.get(collection)
                if isinstance(values,list):
                    seen=set()
                    for i,item in enumerate(values):
                        if not isinstance(item,dict):continue
                        if collection!='revision' and isinstance(item.get('id'),str):
                            if item['id'] in seen:
                                error(f'{collection}[{i}].id','Duplicate authored identity.',
                                      'Give this new item a distinct stable ID; preserve published identities and past attempts.')
                            seen.add(item['id'])
                        try:locators(item.get('pages'),count)
                        except PackageError as exc:error(f'{collection}[{i}].pages',str(exc))
                        if collection=='revision':
                            try:validate_block(item,count,assets,schema=package.get('schema'))
                            except PackageError as exc:error(f'revision[{i}]',str(exc))
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
            try:validate_coverage(coverage,valid,source,assets)
            except PackageError as exc:error('coverage',str(exc),'Review the exact source, module revision, inventory and teaching locators. Rebuild a new companion only after review; never rewrite digests to hide mismatch.')
    except PackageError as exc:
        if not errors:error('package',str(exc))
    if errors:return {'valid':False,'errors':errors}
    from .diagnostics import quality_diagnostics
    warnings.extend(quality_diagnostics(valid))
    features=pdf_features(source)
    for page in features['pages']:
        if page['raster_resources'] or page['form_resources'] or not page['text_available']:
            warning(f"pages[{page['page']-1}]",'pdf-material-review',
                f"Page {page['page']}: {page['raster_resources']} direct raster and {page['form_resources']} form resources; text {'present' if page['text_available'] else 'absent'}. Resource presence is not visual coverage.",
                'Compare this original page and inventory relevant figure/formula relationships. Nested drawings, OCR and speaker notes remain unsupported / needs review.')
    from .coverage import normalized
    for index,question in enumerate(valid['questions']):
        if len({normalized(option) for option in question['options']})!=len(question['options']):
            warning(f'questions[{index}]','ambiguous-options','Choices become indistinguishable after whitespace/case normalization; the original key has not been changed.',
                'Review this exact question and cited source privately. Correct changed choices only through a new authored question revision.')
    if not any(b['kind']=='recall' for b in valid['revision']):
        warning('revision','recall-subset-unavailable','No authored recall cards for the quick review subset.',
                'Author source-linked prompts and answers in a new immutable revision; full notes remain available.')
    if not any(b['kind']!='recall' for b in valid['revision']):
        warning('revision','full-notes-unreviewed','Full revision consists only of recall cards.',
                'Review whether full author notes, lists and comparisons are missing. Preflight cannot certify completeness.')
    if valid['questions']:
        warning('questions','question-support-unreviewed','Page locators are structurally valid; answer support is not semantically certified.',
                'Compare every prompt, choice and explanation privately against cited pages; retain uncertain attribution.')
    public=copy.deepcopy(valid)
    for question in public['questions']:
        question.pop('correct_index');question.pop('explanation')
    assert all('correct_index' not in q and 'explanation' not in q for q in public['questions'])
    fidelity='verified' if all(p['status']=='verified' for p in valid['pages']) else 'needs_review'
    return {'valid':True,'errors':[], 'warnings':warnings[:100],'module_id':valid['module_id'],'revision':valid['module_revision'],
        'source_sha256':manifest['sha256'],'pages':len(valid['pages']),'questions':len(valid['questions']),
        'warnings_total':len(warnings),'warnings_truncated':len(warnings)>100,
        'private_key_projection':'excluded','mapping':'reviewed-current' if valid['mapping'] else 'unmapped',
        'semantic_review':fidelity,
        'review_axes':{'source_identity':'validated','source_fidelity':'author-reported '+fidelity,
            'instructor_intent':'not certified','external_authenticity':'not certified',
            'canonical_mapping':'reviewed-current' if valid['mapping'] else 'unmapped'},
        'source_material':features,
        'coverage':'validated' if coverage is not None else 'not supplied; semantic coverage unresolved'}
