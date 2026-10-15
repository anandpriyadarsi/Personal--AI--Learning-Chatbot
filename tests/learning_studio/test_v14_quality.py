"""Known-truth quality regressions; synthetic sources only."""
import copy
import re
from .helpers import package, catalogue, source_pdf
from .test_service import publish
from .test_v12_progress import service
from personal_learning_assistant.learning_studio.reader import select
from personal_learning_assistant.learning_studio.revision import guided_revision
from personal_learning_assistant.ui.web import create_app


def test_quick_without_recall_does_not_silently_show_unbounded_full_notes():
    p=package();p['revision'][0]['text']='A complete long note. '*1000
    result=select(p,{'budget':'5'},[])
    assert result['revision_blocks']==[]
    assert result['revision_guide']['omitted_blocks']==1
    assert result['revision_guide']['quick_unavailable']
    assert select(p,{'budget':'full'},[])['revision_blocks']==p['revision']


def test_identical_recall_blocks_keep_their_exact_author_indices():
    p=package();card={'kind':'recall','pages':[1],'text':'Same prompt','answer':'Same answer'}
    p['revision'] += [copy.deepcopy(card),copy.deepcopy(card)]
    result=select(p,{'budget':'5'},[],engagement=[{'block_scope':'revision','block_index':2,'action':'remembered','response':'revisit'}])
    assert [item['index'] for item in result['revision_items']]==[2,1]
    assert 'explicitly' in result['revision_items'][0]['reason'].lower()
    assert p['revision'][1]==p['revision'][2]


def test_revision_discloses_cited_pages_and_unreviewed_source_without_certification():
    p=package();p['revision'][0]['pages']=[1]
    result=guided_revision(p,[])
    assert result['coverage']['revision_pages']==[1]
    assert result['coverage']['missing_revision_pages']==[2]
    assert result['coverage']['unreviewed_pages']==[1,2]
    assert result['coverage']['semantic_certification'] is False
    assert result['coverage']['lesson_pages']==[1]


def test_related_exercise_is_lesson_scoped_and_never_exposes_private_keys():
    p=package();p['questions'].insert(0,dict(copy.deepcopy(p['questions'][0]),id='other-page',pages=[2]))
    result=select(p,{},[])
    assert result['related_question']['id']=='q1'
    assert not {'correct_index','explanation'} & result['related_question'].keys()


def test_duplicate_card_routes_have_distinct_ids_and_saved_state_indices(tmp_path):
    s=service(tmp_path);p=package();p['revision'] += [{'kind':'recall','pages':[1],'text':'Same','answer':'Answer'}]*2
    publish(s,p);app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    client=app.test_client();before=s.store.path.read_bytes()
    text=client.get('/learning/modules/synthetic/1?view=revision&budget=5').text
    assert re.findall(r'data-engagement-index="(\d+)"',text)==['1','2']
    assert s.store.path.read_bytes()==before


def test_full_revision_preserves_companion_and_every_lesson_concept(tmp_path):
    s=service(tmp_path);p=package();p['sections'][0]['blocks'][1]['text']='Distinctive lesson qualification absent from companion.'
    publish(s,p);app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    text=app.test_client().get('/learning/modules/synthetic/1?view=revision&budget=full').text
    assert 'Distinctive lesson qualification absent from companion.' in text
    assert 'Recall the contrast.' in text and 'semantic coverage' in text


def test_preflight_warns_for_numbering_truncation_and_revision_omissions():
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf();p=package(raw);p['sections'][0]['title']='Slide 8: comparison'
    p['sections'][0]['blocks'][1]['text']='An incomplete explanation...'
    p['revision'][0]['pages']=[1]
    result=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert result['valid']
    codes={w['code'] for w in result['warnings']}
    assert {'numbering-locator-mismatch','possible-truncation','revision-page-omission'}<=codes
    assert 'correct_index' not in str(result)


def test_coverage_summary_separates_physical_from_semantic_review():
    from .test_coverage import fixture
    from personal_learning_assistant.learning_studio.coverage_view import project_coverage
    c,p,raw,report=fixture()
    result=project_coverage(p,report,{})
    assert result['availability']['original_pages']==2
    assert result['availability']['preview_pages']==0
    assert result['availability']['author_verified_pages']==0
    assert result['availability']['semantic_certification'] is False


def test_diagnostics_are_bounded_immutable_and_flag_nontext_review():
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf();p=package(raw);p['pages'][0]['text']='Inspect the diagram and equation in the original.'
    before=copy.deepcopy(p);report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert p==before and report['valid']
    assert 'nontext-review-needed' in {w['code'] for w in report['warnings']}
    assert len(report['warnings'])<=100


def test_reader_labels_stale_mapping_as_unknown_without_rewriting_history(tmp_path):
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    live=catalogue();s=LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:source_pdf(),catalogue_loader=lambda:live)
    p=package(mapped=True);publish(s,p);live['courses'][0]['topics']=[]
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    before=s.store.path.read_bytes();text=app.test_client().get('/learning/modules/synthetic/1?view=learn').text
    assert 'Historical mapping needs review' in text
    assert s.module('synthetic',1)['mapping']==p['mapping'] and s.store.path.read_bytes()==before


def test_preflight_large_review_queue_discloses_bounded_warning_output():
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf(120);p=package(raw);p['source']['page_count']=120
    p['pages']=[dict(copy.deepcopy(p['pages'][0]),page=i,text='') for i in range(1,121)]
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert report['valid'] and len(report['warnings'])==100
    assert report['warnings_total']>100 and report['warnings_truncated']


def test_preflight_counts_diagnostics_beyond_projection_limit():
    from personal_learning_assistant.learning_studio.authoring import preflight
    raw=source_pdf();p=package(raw)
    p['revision']=[{'kind':'teaching','pages':[1],'text':'An incomplete thought...'} for _ in range(100)]
    report=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert report['warnings_total']>=104 and report['warnings_truncated']


def test_revision_source_navigation_uses_cited_lesson_not_engagement_identity(tmp_path):
    from html import unescape
    s=service(tmp_path);p=package();p['sections'].append({'id':'lesson-2','title':'Second lesson','pages':[2],'blocks':[{'kind':'teaching','text':'Second concept','pages':[2]}]})
    p['revision'].append({'kind':'recall','text':'Second page recall','answer':'Answer','pages':[2]})
    publish(s,p);app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    text=app.test_client().get('/learning/modules/synthetic/1?view=revision&question=q1').text
    card=unescape(re.search(r'<article[^>]+id="ls-block-lesson-1-1".*?</article>',text,re.S)[0])
    assert 'section=lesson-2' in card and 'page=2' in card and 'question=q1' in card
    budget_links=re.findall(r'href="([^"]*budget=[^"]+)"',text)
    assert budget_links and all('question=q1' in link for link in budget_links)
    supplement=re.search(r'<section class="ls-full-lessons".*?</section>',text,re.S)[0]
    assert 'question=q1' in supplement


def test_revision_and_lesson_widgets_have_unique_dom_identities(tmp_path):
    from .test_v12_contracts import activity
    s=service(tmp_path);p=package();p['schema']='anvaya.learning-module.v2'
    p['sections'][0]['blocks'][0]=activity();p['revision'][0]=activity()
    publish(s,p);app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    text=app.test_client().get('/learning/modules/synthetic/1?view=revision').text
    ids=re.findall(r'\bid="([^"]+)"',text)
    assert len(ids)==len(set(ids))


def test_equal_cards_persist_separately_and_new_revision_keeps_prior_history(tmp_path):
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    s=service(tmp_path);p=package();card={'kind':'recall','text':'Same','answer':'Answer','pages':[1]}
    p['revision'] += [copy.deepcopy(card),copy.deepcopy(card)];publish(s,p)
    payload={'event_id':'separate-card','section_id':'lesson-1','block_scope':'revision','block_index':2,'action':'remembered','response':'revisit'}
    first=s.record_engagement('synthetic',1,payload)
    assert s.record_engagement('synthetic',1,payload)==first
    reopened=LearningStudioService(s.store.path,source_loader=lambda _:source_pdf(),catalogue_loader=catalogue)
    saved=reopened.engagement_state('synthetic',1,'lesson-1')
    assert len(saved)==1 and saved[0]['block_index']==2
    newer=copy.deepcopy(p);newer['module_revision']=2;publish(reopened,newer)
    assert reopened.engagement_state('synthetic',2,'lesson-1')==[]
    assert reopened.engagement_state('synthetic',1,'lesson-1')==saved
