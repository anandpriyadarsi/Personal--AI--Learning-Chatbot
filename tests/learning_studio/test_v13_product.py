"""Synthetic V1.3 reader and review contracts; no private academic assets."""
import copy
import pytest
from .helpers import package
from .test_service import publish, event
from .test_v12_progress import service
from personal_learning_assistant.learning_studio.revision import guided_revision


def recall_module():
    p=package();p['schema']='anvaya.learning-module.v2'
    p['revision'] += [{'kind':'recall','pages':[i%2+1],'text':f'Recall {i}','answer':f'Authored answer {i}'} for i in range(12)]
    return p


def test_revision_queue_explains_exact_question_and_saved_revisit_without_closing_misses():
    p=recall_module();before=copy.deepcopy(p)
    weak=[{'question_id':'q1','question_revision':1,'pages':[1,1],'status':'recovered_needs_recheck','incorrect_count':2,'attempt_count':3}]
    engagement=[{'block_scope':'revision','block_index':2,'response':'revisit','action':'remembered'},{'block_scope':'revision','block_index':1,'response':'remembered','action':'remembered'}]
    result=guided_revision(p,weak,'5',engagement=engagement)
    assert len(result['cards'])==4 and result['cards'][0]['text']=='Recall 1'
    graded=[item for item in result['queue'] if item['kind']=='graded_recheck']
    assert len(graded)==1 and graded[0]['question_id']=='q1' and graded[0]['pages']==[1]
    assert 'correct retry' in graded[0]['reason'] and '3 recorded attempts' in graded[0]['reason']
    assert len([item for item in result['queue'] if item['kind']=='self_report'])==1
    assert before==p


def test_full_revision_keeps_author_order_and_all_recall_even_after_revisit():
    p=recall_module();result=guided_revision(p,[],'full',engagement=[{'block_scope':'revision','block_index':12,'response':'revisit','action':'remembered'}])
    assert result['cards']==p['revision'][1:] and len(result['cards'])==12 and not result['is_subset']


def test_practice_state_is_versioned_key_free_read_only_and_retries_are_not_mastery(tmp_path):
    s=service(tmp_path);p=publish(s);before=s.store.path.read_bytes()
    assert s.practice_state('synthetic',1)['q1']['status']=='never_practised' and before==s.store.path.read_bytes()
    s.attempt('synthetic',event(p,'wrong',0));s.attempt('synthetic',event(p,'retry',1))
    state=s.practice_state('synthetic',1)['q1']
    assert state['status']=='recovered_needs_recheck' and state['attempt_count']==2
    assert not {'correct_index','explanation','selection'} & state.keys()
    newer=copy.deepcopy(p);newer['module_revision']=2;publish(s,newer)
    assert s.practice_state('synthetic',2)['q1']['status']=='never_practised'


def test_source_linked_objectives_accept_ungraded_reflection_only(tmp_path):
    s=service(tmp_path);p=package();p['sections'][0]['blocks'].append({'kind':'objectives','text':'Explain the source distinction from memory.','pages':[1]});publish(s,p)
    saved=s.record_engagement('synthetic',1,{'event_id':'teachback','section_id':'lesson-1','block_index':3,'action':'reflection','response':'My tentative explanation'})
    assert saved['ungraded'] and s.evidence()['attempts']==0


def test_coverage_projection_filters_exact_element_and_keeps_status_axes():
    from personal_learning_assistant.learning_studio.coverage_view import project_coverage
    p=package();report={'review':{'status':'needs_review'},'external_facts':{'status':'pending'},'inventory':[{'id':'e1','page':1,'kind':'text','text':'Synthetic source','locator':{'line':1}}],'coverage':[{'element_id':'e1','state':'unresolved','mappings':[],'reason':'Check the source'}],'unresolved':[{'id':'issue1','pages':[1],'issue':'Meaning uncertain','snippet':'Synthetic','next_action':'Ask the source owner'}]}
    before=copy.deepcopy(report);result=project_coverage(p,report,{'page':'1','state':'unresolved','issue':'issue1'})
    assert result['entries'][0]['element']['id']=='e1' and result['entries'][0]['next_action']=='Ask the source owner'
    assert result['axes']['instructor_intent']=='not recorded' and result['axes']['academic_mapping']=='unmapped / needs review' and report==before


def test_recheck_queue_uses_current_question_revision_when_weak_projection_has_no_version():
    p=recall_module();p['questions'][0]['revision']=7
    result=guided_revision(p,[{'question_id':'q1','pages':[1],'incorrect_count':1,'attempt_count':1,'status':'needs_review'}])
    assert result['queue'][0]['question_revision']==7


@pytest.mark.parametrize('live_change',[{'available':False,'courses':[]},{'available':True,'courses':[]}])
def test_coverage_mapping_axis_revalidates_live_catalogue_without_rewriting_history(tmp_path,live_change):
    from .test_coverage import fixture
    from .helpers import catalogue
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    from personal_learning_assistant.ui.web import create_app
    c,p,raw,r=fixture();p['mapping']=package(mapped=True)['mapping']
    r=c.build_coverage(p,raw,reviewer='Synthetic author',method='Mechanical location review')
    live=catalogue();s=LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:raw,catalogue_loader=lambda:live)
    s.stage(p,coverage=r);s.publish(p['module_id'],1)
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s});client=app.test_client();base='/learning/modules/synthetic/1/coverage'
    assert b'Academic mapping</dt><dd>reviewed ' in client.get(base).data
    live.clear();live.update(live_change);before=s.store.path.read_bytes();response=client.get(base)
    assert response.status_code==200 and b'Academic mapping</dt><dd>needs review' in response.data
    assert s.module('synthetic',1)['mapping']==p['mapping'] and s.store.path.read_bytes()==before


@pytest.mark.parametrize('value',['²','١','9'*10000,'-1','0','3'],ids=['superscript','non_ascii_digit','oversized','negative','zero','outside_source'])
def test_source_page_query_fails_closed_for_unicode_oversized_and_out_of_range(value):
    from personal_learning_assistant.learning_studio.reader import select
    from personal_learning_assistant.learning_studio.coverage_view import project_coverage
    from personal_learning_assistant.learning_studio.validation import PackageError
    p=package();report={'review':{'status':'needs_review'},'external_facts':{'status':'pending'},'inventory':[],'coverage':[],'unresolved':[]}
    for call in (lambda:select(p,{'page':value},[]),lambda:project_coverage(p,report,{'page':value})):
        with pytest.raises(PackageError) as error:call()
        assert error.value.status==404
