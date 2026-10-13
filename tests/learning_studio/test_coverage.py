import copy
import importlib.util
import pytest
from .helpers import package, source_pdf
from personal_learning_assistant.learning_studio.demo import synthetic_pdf
from personal_learning_assistant.learning_studio.validation import PackageError


def api():
    name='personal_learning_assistant.learning_studio.coverage'
    assert importlib.util.find_spec(name) is not None, 'Versioned source-element coverage is not implemented'
    return __import__(name,fromlist=['build_coverage'])


def fixture():
    raw=synthetic_pdf(2);p=package(raw)
    p['sections'][0]['blocks'][1]['text']='Synthetic source page 1. Demonstration only. No academic evidence.'
    c=api();record=c.build_coverage(p,raw,reviewer='Fixture author',method='Explicit authored source locations')
    return c,p,raw,record


def test_inventory_and_notes_locations_are_independent_of_original_availability():
    c,p,raw,r=fixture()
    assert len(r['inventory'])>=4 and r['review']['status']=='needs_review'
    assert c.validate_coverage(r,p,raw)==r
    assert r['external_facts']['status']=='pending'


def test_omitted_bullet_missing_member_and_stale_comparison_fail_closed():
    c,p,raw,r=fixture()
    broken=copy.deepcopy(r);broken['coverage'].pop()
    with pytest.raises(PackageError,match='coverage'):c.validate_coverage(broken,p,raw)
    broken=copy.deepcopy(r);broken['inventory'].pop()
    with pytest.raises(PackageError):c.validate_coverage(broken,p,raw)
    changed=copy.deepcopy(p);changed['sections'][0]['blocks'][1]['text']='The cases are identical, not contrasted.'
    with pytest.raises(PackageError,match='stale'):c.validate_coverage(r,changed,raw)


def test_source_change_bad_locator_and_uninspected_visual_are_rejected():
    c,p,raw,r=fixture()
    with pytest.raises(PackageError):c.validate_coverage(r,p,source_pdf())
    broken=copy.deepcopy(r);broken['inventory'][0]['page']=3
    with pytest.raises(PackageError):c.validate_coverage(broken,p,raw)
    broken=copy.deepcopy(r);broken['coverage'][0]['mappings']=[{'section_id':'missing','block_index':0,'quote':'anything'}]
    with pytest.raises(PackageError):c.validate_coverage(broken,p,raw)


def test_canonical_bundle_keeps_companion_separate_from_owned_images():
    import io,json,zipfile
    from personal_learning_assistant.learning_studio import archive
    assert hasattr(archive,'decode_bundle'),'Companion-aware canonical importer is not implemented'
    c,p,raw,r=fixture();out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('module.json',json.dumps(p));z.writestr('coverage.json',json.dumps(r))
    module,assets,coverage=archive.decode_bundle(out.getvalue(),'lecture.zip')
    assert module==p and assets=={} and coverage==r
    with pytest.raises(PackageError):archive.decode_upload(out.getvalue(),'lecture.zip')
