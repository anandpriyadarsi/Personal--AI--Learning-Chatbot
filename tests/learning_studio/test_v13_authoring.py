"""Actionable structural diagnostics do not certify semantic source support."""
import copy
import pytest
from personal_learning_assistant.learning_studio.authoring import preflight
from .helpers import catalogue, package, source_pdf


def test_preflight_reports_each_missing_preview_and_duplicate_identity():
    raw=source_pdf();p=package(raw)
    p['pages'][0]['preview']='assets/missing.png'
    p['questions'].append(copy.deepcopy(p['questions'][0]));p['sections'].append(copy.deepcopy(p['sections'][0]))
    before=copy.deepcopy(p);report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert not report['valid']
    assert {'pages[0].preview','questions[1].id','sections[1].id'} <= {e['field'] for e in report['errors']}
    assert 'owned raster asset' in next(e['repair'] for e in report['errors'] if e['field']=='pages[0].preview')
    assert p==before


def test_preflight_warns_without_inventing_semantic_support():
    raw=source_pdf();p=package(raw);p['pages'][0]['text']=''
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert report['valid']
    assert {'missing-excerpt','missing-preview','recall-subset-unavailable','question-support-unreviewed'} <= {w['code'] for w in report['warnings']}
    assert report['review_axes']=={'source_identity':'validated','source_fidelity':'author-reported needs_review','instructor_intent':'not certified','external_authenticity':'not certified','canonical_mapping':'unmapped'}
    assert 'correct_index' not in str(report) and p['questions'][0]['explanation'] not in str(report)


def test_preflight_names_revision_block_and_invalid_original():
    raw=source_pdf();p=package(raw);p['revision'][0]['pages']=[3]
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert not report['valid'] and any(e['field']=='revision[0].pages' for e in report['errors'])
    report=preflight(package(raw),None,{},catalogue(),source_id='fixture-source')
    assert not report['valid'] and report['errors'][0]['field']=='source.original'


def test_verified_page_label_does_not_certify_external_authenticity():
    raw=source_pdf();p=package(raw)
    for page in p['pages']:page['status']='verified';page['review_flags']=[]
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert report['valid'] and report['review_axes']['source_fidelity']=='author-reported verified'
    assert report['review_axes']['external_authenticity']=='not certified'


@pytest.mark.parametrize('field,value',[('text',None),('text',[]),('preview',{})])
def test_preflight_malformed_page_fields_are_structured_errors(field,value):
    raw=source_pdf();p=package(raw);p['pages'][0][field]=value
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert not report['valid'] and any(e['field']==f'pages[0].{field}' for e in report['errors'])
