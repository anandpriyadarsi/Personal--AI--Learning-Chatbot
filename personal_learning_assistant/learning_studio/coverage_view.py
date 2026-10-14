"""Bounded, read-only reviewer projection. Filtering never changes review authority."""
from copy import deepcopy
from .validation import PackageError, require, validate_mapping
from .reader import parse_page


def project_coverage(module, report, args, catalogue=None):
    page=args.get('page','');state=args.get('state','');issue=args.get('issue','');severity=args.get('severity','')
    page_number=parse_page(page,module['source']['page_count']) if page else None
    require(state in {'','mapped','excluded','unresolved'},'Unknown coverage state.',404)
    require(severity in {'','needs_review','recorded'},'Unknown review priority.',404)
    require(not issue or any(i['id']==issue for i in report['unresolved']),'Unknown targeted review issue.',404)
    chosen=next((i for i in report['unresolved'] if i['id']==issue),None)
    inventory={e['id']:e for e in report['inventory']};entries=[]
    counts={name:sum(e['state']==name for e in report['coverage']) for name in ('mapped','excluded','unresolved')}
    for entry in report['coverage']:
        element=inventory[entry['element_id']];priority='needs_review' if entry['state']=='unresolved' else 'recorded'
        if page_number and element['page']!=page_number:continue
        if state and entry['state']!=state:continue
        if severity and priority!=severity:continue
        if chosen and element['page'] not in chosen['pages']:continue
        related=[i for i in report['unresolved'] if element['page'] in i['pages']] if entry['state']=='unresolved' else []
        next_action=(chosen['next_action'] if chosen else related[0]['next_action'] if related else
                     'Compare the exact source element with the linked authored block; a location is not semantic approval.' if entry['state']=='mapped' else
                     'Inspect the exclusion reason and original element before proposing a new immutable revision.' if entry['state']=='excluded' else
                     'Inspect the source element and locate or author a source-faithful explanation in a new revision.')
        entries.append({'element':element,'coverage':entry,'priority':priority,'issues':related,'next_action':next_action})
    mapping_status='unmapped / needs review'
    if module['mapping']:
        mapping_status='needs_review'
        try:
            validate_mapping(module['mapping'],catalogue or {})
            mapping_status='reviewed_current_catalogue'
        except PackageError:
            pass  # Historical mapping is retained; only this current read model changes.
    return deepcopy({'entries':entries,'counts':counts,'filters':{'page':page,'state':state,'issue':issue,'severity':severity},
                     'axes':{'source_fidelity':report['review']['status'],'instructor_intent':'not recorded',
                             'external_authenticity':report['external_facts']['status'],'academic_mapping':mapping_status}})
