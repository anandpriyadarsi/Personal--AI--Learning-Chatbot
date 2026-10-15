import copy
import hashlib
import importlib.util
from pathlib import Path
from .helpers import package, source_pdf, catalogue


def test_preflight_rejects_hash_without_rewriting():
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf(); p=package(raw); p['source']['sha256']='0'*64
    before=copy.deepcopy(p)
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert not report['valid'] and report['errors'][0]['field']=='source.sha256'
    assert p==before


def test_preflight_checks_registry_and_private_projection():
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf();p=package(raw)
    assert not preflight(p,raw,{},catalogue(),source_id='different')['valid']
    result=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert result['valid'] and result['private_key_projection']=='excluded'
    assert result['mapping']=='unmapped' and result['semantic_review']=='needs_review'


def test_validation_health_requires_browser_even_for_feature():
    path=Path(__file__).resolve().parents[2]/'scripts'/'learning_studio_validate.py'
    spec=importlib.util.spec_from_file_location('studio_validate',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert 'playwright' in module.DEPENDENCIES
    assert module.BASE=='6e520035b6b9ccf8e14c176b35b43e384c95d103'


def test_preflight_rejects_invalid_locator_and_stale_mapping():
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf();p=package(raw);p['questions'][0]['pages']=[3]
    assert not preflight(p,raw,{},catalogue(),source_id='fixture-source')['valid']
    p=package(raw,mapped=True)
    assert not preflight(p,raw,{}, {'available':False,'courses':[]},source_id='fixture-source')['valid']


def test_cli_export_does_not_overwrite_and_reports_failure(tmp_path):
    import json,subprocess,sys
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf();p=package(raw)
    source=tmp_path/'source.pdf';source.write_bytes(raw)
    manifest=tmp_path/'module.json';manifest.write_text(json.dumps(p))
    output=tmp_path/'export.zip';output.write_bytes(b'protected')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([sys.executable,str(root/'scripts/learning_studio_preflight.py'),str(manifest),'--source',str(source),'--source-id','fixture-source','--export',str(output)],capture_output=True,text=True)
    assert result.returncode==1 and output.read_bytes()==b'protected'
    assert not json.loads(result.stdout)['valid']


def test_missing_dependency_health_fails_before_gates(monkeypatch):
    path=Path(__file__).resolve().parents[2]/'scripts'/'learning_studio_validate.py'
    spec=importlib.util.spec_from_file_location('studio_health',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    real=module.importlib.import_module
    def missing(name):
        if name=='playwright':raise ImportError('missing')
        return real(name)
    monkeypatch.setattr(module.importlib,'import_module',missing)
    result=module.health()
    assert not result['valid'] and any('Missing playwright' in error for error in result['errors'])


def test_pilot_cli_exports_v2_restored_cards_and_coverage(tmp_path):
    import json,subprocess,sys,zipfile
    from personal_learning_assistant.learning_studio.demo import synthetic_pdf,synthetic_package
    from personal_learning_assistant.learning_studio.pilot_quality import normalize_pilot
    from personal_learning_assistant.learning_studio.coverage import build_coverage
    raw=synthetic_pdf();canonical,assets=synthetic_package(raw);digest=hashlib.sha256(raw).hexdigest()
    proposed={'schema':'anvaya.learning-module.v1','title':'Synthetic pilot','source_sha256':digest,'source_page_count':20,'source_original_filename':'source.pdf',
      'lessons':[{'page':i,'title':f'Synthetic lesson {i}','image_file':f'assets/page-{i:02}.png','image_sha256':hashlib.sha256(assets[f'assets/page-{i:02}.png']).hexdigest(),'source_text':f'Synthetic source page {i}. Demonstration only. No academic evidence.','source_text_sha256':hashlib.sha256(f'Synthetic source page {i}. Demonstration only. No academic evidence.'.encode()).hexdigest(),'notes':'Complete synthetic teaching notes','points':['Observe','Compare'],'activity':'Compare two cases'} for i in range(1,21)],
      'revision':{'markdown':'Complete synthetic revision','source_pages':[1,20],'cards':[{'id':f'card{i}','page':i,'prompt':f'Prompt {i}','answer':f'Answer {i}'} for i in range(1,13)]},'questions':[]}
    candidate=tmp_path/'pilot.zip';source=tmp_path/'source.pdf';source.write_bytes(raw)
    with zipfile.ZipFile(candidate,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('ANVAYA_Learning_Module_Proposed_v1.json',json.dumps(proposed));z.writestr('Source_Fidelity_Coverage_Report.json',json.dumps({'original_source_sha256':digest,'slide_details':[]}));z.writestr('ORIGINAL_20_Page_Presentation.pdf',raw)
        for name,data in assets.items():z.writestr(name,data)
    p,original,owned=normalize_pilot(candidate.read_bytes(),source_id='synthetic-only')
    coverage=build_coverage(p,original,reviewer='Synthetic test reviewer',method='Mechanical synthetic fixture only; unresolved fidelity')
    companion=tmp_path/'coverage.json';companion.write_text(json.dumps(coverage));output=tmp_path/'normalized.zip'
    root=Path(__file__).resolve().parents[2]
    cmd=[sys.executable,str(root/'scripts/learning_studio_preflight.py'),str(candidate),'--pilot','--source',str(source),'--source-id','synthetic-only','--coverage',str(companion),'--export',str(output)]
    result=subprocess.run(cmd,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    with zipfile.ZipFile(output) as z:
        exported=json.loads(z.read('module.json'));assert exported['schema']=='anvaya.learning-module.v2'
        assert len([b for b in exported['revision'] if b['kind']=='recall'])==12
        assert json.loads(z.read('coverage.json'))==coverage
    # A companion for another source ID has a different package digest and must fail.
    cmd[cmd.index('synthetic-only')]='another-source'
    result=subprocess.run(cmd,capture_output=True,text=True)
    assert result.returncode==1 and not json.loads(result.stdout)['valid']


import pytest
@pytest.mark.parametrize('manifest',[[],None,'not-an-object'])
def test_preflight_malformed_source_is_bounded_field_error(manifest):
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf();p=package(raw);p['source']=manifest
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert not report['valid']
    assert report['errors'][0]['field']=='source'
    assert 'structured object' in report['errors'][0]['message']
