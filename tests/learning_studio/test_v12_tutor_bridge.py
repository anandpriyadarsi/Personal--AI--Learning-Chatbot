import copy
import json
import pytest
from .helpers import package, source_pdf, catalogue
from .test_service import publish, event
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.tutor_bridge import prepare_review, MAX_CONTEXT_BYTES, MAX_MISSES
from personal_learning_assistant.learning_studio.validation import PackageError


@pytest.fixture
def studio(tmp_path):
    s = LearningStudioService(tmp_path/'learning_studio.sqlite3', source_loader=lambda _:source_pdf(), catalogue_loader=catalogue)
    publish(s, package(mapped=True))
    return s


def action(s, **extra):
    return prepare_review(s, {'module_id':'synthetic', 'module_revision':1, **extra}, explicit_action=True)


def test_adapter_requires_explicit_action(studio):
    before = studio.store.path.read_bytes()
    with pytest.raises(PackageError): prepare_review(studio, {'module_id':'synthetic','module_revision':1})
    assert studio.store.path.read_bytes() == before


def test_adapter_reads_exact_owner_module_revision(studio):
    other = package(module_id='other'); publish(studio,other);studio.attempt('other',event(other,'other-wrong'))
    p = package(mapped=True); studio.attempt('synthetic',event(p))
    p2=copy.deepcopy(p);p2['module_revision']=2;publish(studio,p2)
    result=action(studio)
    assert result['module_revision']==1 and result['attempts']==1
    assert 'other' not in json.dumps(result)
    assert prepare_review(studio,{'module_id':'synthetic','module_revision':2},explicit_action=True)['attempts']==0


@pytest.mark.parametrize('field', ['owner','correctness','source_hash','timestamp','mapping','redirect','prompt'])
def test_adapter_rejects_forged_source_and_correctness(studio,field):
    with pytest.raises(PackageError): action(studio, **{field:'forged'})


def test_adapter_keeps_empty_and_limited_labels(studio):
    assert action(studio)['evidence_label']=='No evidence'
    for i in range(10): studio.attempt('synthetic',event(package(mapped=True),f'retry-{i}'))
    assert action(studio)['evidence_label']=='Limited evidence'


def test_adapter_keeps_wrong_then_correct_history(studio):
    p=package(mapped=True);studio.attempt('synthetic',event(p,'wrong'));studio.attempt('synthetic',event(p,'right',1))
    miss=action(studio)['missed_questions'][0]
    assert miss['latest_correct'] and miss['incorrect_count']==1
    assert miss['status']=='recovered_needs_recheck' and miss['question_revision']==1


def test_adapter_requires_live_reviewed_mapping(studio):
    studio.catalogue_loader=lambda:{'available':True,'courses':[]}
    assert action(studio)['mapping_status']=='needs_review'
    p=package(module_id='unmapped');publish(studio,p)
    assert prepare_review(studio,{'module_id':'unmapped','module_revision':1},explicit_action=True)['mapping_status']=='unmapped'


def test_adapter_verifies_source_and_references(studio):
    with pytest.raises(PackageError):prepare_review(studio,{'module_id':'synthetic','module_revision':99},explicit_action=True)
    def unavailable(*args):
        raise PackageError('Immutable source snapshot is unavailable.', 409)
    studio.source=unavailable
    with pytest.raises(PackageError):action(studio)


def test_adapter_omits_private_answer_keys(studio):
    studio.attempt('synthetic',event(package(mapped=True)))
    result=json.dumps(action(studio))
    assert 'correct_index' not in result and 'explanation' not in result and 'Correct"' not in result


def test_adapter_does_not_mutate_other_authorities(studio,tmp_path):
    authorities=tmp_path/'academic-grades-notes-knowledge';authorities.write_bytes(b'protected authority fixture')
    before=studio.store.path.read_bytes(); protected=authorities.read_bytes()
    action(studio)
    assert studio.store.path.read_bytes()==before and authorities.read_bytes()==protected


def test_adapter_respects_provider_unavailable(studio):
    result=action(studio)
    assert result['status']=='blocked' and result['automatic_tutor_consumption'] is False
    assert 'session_id' not in result and 'provider' not in result


def test_adapter_context_bounds_and_duplicate_action(studio):
    original=studio.review_context
    def large(*args):
        c=original(*args);studio.attempt('synthetic',event(package(mapped=True),'bounded')) if not c['attempts'] else None
        c=original(*args);c['missed_questions']=c['missed_questions']*200
        return c
    studio.review_context=large
    first=action(studio);before=studio.store.path.read_bytes();second=action(studio)
    assert first==second and studio.store.path.read_bytes()==before
    assert len(first['missed_questions'])<=MAX_MISSES and first['omitted_misses']>0
    assert len(json.dumps(first,ensure_ascii=False).encode())<=MAX_CONTEXT_BYTES


def test_adapter_rejects_invalid_source_locator(studio):
    studio.attempt('synthetic',event(package(mapped=True)));original=studio.review_context
    def corrupt(*args):
        c=original(*args);c['missed_questions'][0]['pages']=[999];return c
    studio.review_context=corrupt
    with pytest.raises(PackageError):action(studio)
