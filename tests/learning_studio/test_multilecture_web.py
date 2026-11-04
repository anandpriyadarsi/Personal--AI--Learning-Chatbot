"""Real original snapshots, private keys, portable round trip and durable progress."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
import sqlite3
import pytest
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.validation import PackageError
from personal_learning_assistant.learning_studio.multilecture_authoring import prepare,draft,stage_draft,export_bundle,RUBRIC,generate
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary,LibraryError
from personal_learning_assistant.ui.web import create_app
from .helpers import catalogue


def source_pdf(content):
    import fitz
    doc=fitz.open();page=doc.new_page();page.insert_text((40,70),content)
    raw=doc.tobytes();doc.close();return raw


@pytest.fixture
def group(tmp_path):
    lib=NativeDocumentLibrary(tmp_path/'data/native_library',autostart=False)
    studio=LearningStudioService(tmp_path/'data/learning_studio.sqlite3',source_loader=lambda _:None,catalogue_loader=catalogue)
    docs=[lib.upload(BytesIO(source_pdf(f'Lecture {i}: synthetic batch mean is {i}. Center observations by subtracting the batch mean.')),
                     f'Lecture-{i}.pdf',subject_id='c0') for i in range(1,5)]
    token=prepare(studio,lib,[d['id'] for d in docs],title='Centering a dataset',course_id='c0',topic_id='t0')
    yield studio,lib,docs,token
    lib.close()


def reviewed(studio,token):
    p,_,_=draft(studio,token)
    for i,s in enumerate(p['sections'],1):
        refs=s['pages']
        s['blocks']=[
            {'kind':'objectives','pages':refs,'text':'Explain centering and identify a batch mean before transforming observations.'},
            {'kind':'teaching','pages':refs,'text':f'''The source defines the mean for synthetic batch {i} as {i}. Centering expresses each observation as a difference from this mean. Begin by identifying the batch and the corresponding source, since the mean belongs to that batch alone. For an observation x, subtract {i} to obtain its centered value. A value above the mean produces a positive difference. A value below the mean produces a negative difference. A value equal to the mean produces zero. These signs describe relative position; they do not by themselves describe variability. Compare the worked example, then explain the subtraction in your own words before attempting a new observation.'''},
            {'kind':'example','pages':refs,'text':f'For this batch, x = {i+2}. Centering gives ({i+2}) - ({i}) = 2. The observation lies two units above its batch mean.'},
            {'kind':'misconception','pages':refs,'text':'Do not subtract the mean of a different batch. The example depends on the selected lecture.'},
            {'kind':'recall','pages':refs,'text':f'Center x = {i} for this batch.','answer':f'{i} - {i} = 0.'}]
    p['revision']=[{'kind':'teaching','pages':[1,2,3,4],'text':'Select the correct batch mean, subtract it from each observation, and check the sign. Centering alone does not scale variability.'}]
    p['questions']=[{'id':f'q{i}','revision':1,'kind':'mcq','prompt':f'For batch {i} with mean {i}, what is the centered value of {i+2}?',
        'options':['2','0'],'correct_index':0,'explanation':f'Subtract {i} from {i+2}, giving 2.',
        'pages':[i],'difficulty':'normal','low_stakes':True} for i in range(1,5)]
    return p


def publish_group(group):
    studio,lib,docs,token=group;p=reviewed(studio,token)
    result=stage_draft(studio,token,p,RUBRIC)
    studio.publish(result['module_id'],1)
    return p


def test_four_lecture_immutable_publish_exact_snapshots_and_no_key_leak(group):
    studio,lib,docs,token=group;p=publish_group(group)
    assert len(p['sections'])==4
    for i,(doc,source) in enumerate(zip(docs,p['lecture_sources']),1):
        assert source['order']==i and source['pages']==[i] and source['positions']==[1]
        assert hashlib.sha256(studio.asset(p['module_id'],1,source['asset'])).hexdigest()==doc['sha256']
        with pytest.raises(LibraryError):lib.delete(doc['id'])
    public=studio.module(p['module_id'],1)
    assert all('correct_index' not in q and 'explanation' not in q for q in public['questions'])
    with pytest.raises(PackageError):studio.stage({**p,'title':'mutated same revision'},source_bytes=studio.source(p['module_id'],1))


def test_bad_locator_source_text_and_hash_cannot_be_staged(group):
    studio,lib,docs,token=group;p=reviewed(studio,token)
    for mutation in ('hash','position','excerpt'):
        bad=deepcopy(p)
        if mutation=='hash':bad['lecture_sources'][0]['sha256']='0'*64
        elif mutation=='position':bad['lecture_sources'][0]['positions']=[2]
        else:bad['pages'][0]['text']='False lecture excerpt'
        with pytest.raises(PackageError):stage_draft(studio,token,bad,RUBRIC)
    with pytest.raises(PackageError):stage_draft(studio,token,reviewed(studio,token),[])
    with pytest.raises(PackageError):stage_draft(studio,token,draft(studio,token)[0],RUBRIC)


def test_portable_v2_roundtrip_keeps_all_originals_and_provenance(group,tmp_path):
    from personal_learning_assistant.learning_studio.archive import read_zip
    from personal_learning_assistant.learning_studio.portable_bundle import decode_self_contained_bundle
    studio,lib,docs,token=group;p=publish_group(group)
    raw=export_bundle(studio,p['module_id'],1)
    prepared=decode_self_contained_bundle(read_zip(raw,pilot=True))
    other=LearningStudioService(tmp_path/'roundtrip/learning_studio.sqlite3',source_loader=lambda _:None,catalogue_loader=catalogue)
    other.stage_many_portable(prepared);other.publish(p['module_id'],1)
    assert other.module(p['module_id'],1)['lecture_sources']==p['lecture_sources']
    assert other.source(p['module_id'],1)==studio.source(p['module_id'],1)


def test_nojs_completion_restart_reopen_and_failed_save(group,monkeypatch):
    studio,lib,docs,token=group;p=publish_group(group)
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio})
    c=app.test_client();url=f'/learning/modules/{p["module_id"]}/1'
    form={'csrf_token':app.extensions['learning_studio_csrf'],'section':'lesson-1','completed':'true','event_id':'finish-1'}
    assert c.post(url+'/completion',data=form).status_code==303
    assert c.post(url+'/completion',data=form).status_code==303
    restarted=LearningStudioService(studio.store.path,source_loader=studio.source_loader,catalogue_loader=catalogue)
    assert restarted.resume_learning()['next_section']=='lesson-2'
    form.update(completed='false',event_id='reopen-1');assert c.post(url+'/completion',data=form).status_code==303
    assert restarted.resume_learning()['next_section']=='lesson-1'
    def failed(*a,**k):raise PackageError('Storage is full; lesson was not saved.',503)
    monkeypatch.setattr(studio,'record_progress',failed)
    response=c.post(url+'/completion',data={**form,'completed':'true','event_id':'failed'})
    assert response.status_code==503 and 'Location' not in response.headers


def test_browser_routes_do_not_expose_keys_and_original_links_preserve_bytes(group):
    studio,lib,docs,token=group;p=publish_group(group)
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio})
    c=app.test_client();url=f'/learning/modules/{p["module_id"]}/1'
    page=c.get(url+'?view=learn&section=lesson-1');assert page.status_code==200
    html=page.text
    assert 'Lecture-1.pdf' in html and '/lectures/1/original' in html
    assert 'correct_index' not in html and 'Subtract 1 from 3, giving 2.' not in html
    assert c.get(url+'/lectures/1/original').data==lib.original(docs[0]['id']).read_bytes()
    assert c.get('/learning/author').status_code==200
    assert c.get('/learning/author/'+token).status_code==200
    assert c.post('/learning/author/'+token+'/generate').status_code==403


def test_generation_requires_consent_and_cannot_publish(group):
    from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
    studio,lib,docs,token=group;p=reviewed(studio,token);calls=[]
    class Provider:
        configured=True
        def complete(self,request):
            calls.append(request)
            return TutorProviderResponse(json.dumps({k:p[k] for k in ('sections','revision','questions')}),'synthetic-provider','fixture')
    with pytest.raises(PackageError):generate(studio,token,Provider(),consented=False)
    assert not calls
    next_token=generate(studio,token,Provider(),consented=True)
    generated,_,_=draft(studio,next_token)
    assert len(calls)==1 and len(generated['sections'])==4
    assert all(not value for value in generated['author_review'].values())
    with pytest.raises(PackageError):studio.module(p['module_id'],1)


def test_consent_aware_feedback_uses_real_canonical_results_without_writes(group,tmp_path):
    import sys
    sys.path.insert(0,str(__import__('pathlib').Path(__file__).parents[1]))
    from test_assessment_studio_phase_e import _database
    from personal_learning_assistant.services.assessment_intelligence_service import AssessmentIntelligenceService
    from personal_learning_assistant.learning_studio.assessment_bridge import feedback
    studio,lib,docs,token=group;p=publish_group(group)
    path=_database(tmp_path)
    report=AssessmentIntelligenceService(path)
    package=studio.module(p['module_id'],1);package['mapping']={'course_id':'course-ma','topic_id':'topic-lu','topic_name':'LU Factorization','reviewed':True,'confidence':1.0}
    cat={'available':True,'courses':[{'id':'course-ma','topics':[{'id':'topic-lu','name':'LU Factorization'}]}]}
    studio.catalogue_loader=lambda:cat
    before=path.read_bytes()
    def loader(course):return report.course_report(course)
    assert not feedback(studio,package,loader)['consented']
    studio.record_progress(p['module_id'],1,{'event_id':'consent-1','section_id':'lesson-1','view':'learn','assessment_feedback_consent':True})
    result=feedback(studio,package,loader)
    assert result['available'] and result['needs_revision']
    assert result['topics'][0]['topic_id']=='topic-lu'
    assert path.read_bytes()==before
    studio.record_progress(p['module_id'],1,{'event_id':'revoke-1','section_id':'lesson-1','view':'learn','assessment_feedback_consent':False})
    assert feedback(studio,package,loader)['topics']==[]


def test_friendly_author_form_and_revision_receipts_preserve_source_identity(group):
    from personal_learning_assistant.learning_studio.multilecture_authoring import edit_form
    studio,lib,docs,token=group
    p=reviewed(studio,token)
    data={}
    for i,s in enumerate(p['sections'],1):
        data['order-'+s['id']]=str(5-i)
        data['title-'+s['id']]='Edited '+s['title']
    edited=edit_form(p,data)
    assert edited['sections'][0]['id']=='lesson-4'
    assert edited['lecture_sources']==p['lecture_sources']
    receipt=stage_draft(studio,token,edited,RUBRIC)
    assert receipt['revision']==1
    assert stage_draft(studio,token,edited,RUBRIC)['revision']==1
    studio.publish(p['module_id'],1)
    edited['sections'][0]['blocks'][1]['text']+=' The original batch identity remains unchanged.'
    revision=stage_draft(studio,token,edited,RUBRIC)
    assert revision['revision']==2
    studio.publish(p['module_id'],2)
    assert studio.module(p['module_id'],1)['lecture_sources']==studio.module(p['module_id'],2)['lecture_sources']
    assert studio.reading_state(p['module_id'],2)['completed_sections']==[]


def test_reviewed_assessment_link_bridges_different_owner_ids_without_name_matching(group,tmp_path):
    import sys
    sys.path.insert(0,str(__import__('pathlib').Path(__file__).parents[1]))
    from test_assessment_studio_phase_e import _database
    from personal_learning_assistant.services.assessment_intelligence_service import AssessmentIntelligenceService
    from personal_learning_assistant.learning_studio.assessment_bridge import feedback,reviewed_link
    studio,lib,docs,token=group;p=publish_group(group)
    # The routed topic ID is distinct from the Assessment topic ID. The
    # explicit user review, not a display title, is the bridge authority.
    cat=catalogue();cat['courses'][0]['code']='MA103N';studio.catalogue_loader=lambda:cat
    path=_database(tmp_path);reports=AssessmentIntelligenceService(path);before=path.read_bytes()
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio,
                   'ASSESSMENT_INTELLIGENCE_SERVICE_FACTORY':lambda:reports})
    c=app.test_client();url=f'/learning/modules/{p["module_id"]}/1';csrf=app.extensions['learning_studio_csrf']
    assert '/assessments/tests?course_id=course-ma' in c.get(url+'?view=learn').text
    assert c.post(url+'/assessment-link',data={'csrf_token':csrf,'topic_id':'topic-lu'}).status_code==400
    assert reviewed_link(studio,p['module_id'],1) is None
    assert c.post(url+'/assessment-link',data={'csrf_token':csrf,'topic_id':'foreign-topic','reviewed':'true'}).status_code==400
    assert c.post(url+'/assessment-link',data={'csrf_token':csrf,'topic_id':'topic-lu','reviewed':'true'}).status_code==303
    c.post(url+'/assessment-consent',data={'csrf_token':csrf,'consent':'true'})
    result=feedback(studio,studio.module(p['module_id'],1),reports.course_report,assessment_mapping=reviewed_link(studio,p['module_id'],1))
    assert result['needs_revision'] and result['topics'][0]['topic_id']=='topic-lu'
    assert path.read_bytes()==before


def test_pptx_and_text_sources_keep_real_original_locators_in_a_four_lecture_group(group):
    from tests.test_native_document_library import pptx_bytes
    studio,lib,docs,token=group
    deck=lib.upload(BytesIO(pptx_bytes()),'Lecture deck.pptx',subject_id='c0')
    code=lib.upload(BytesIO(b'print("inert code")\n# Synthetic explanation'),'lab.py',subject_id='c0')
    token=prepare(studio,lib,[docs[0]['id'],deck['id'],docs[1]['id'],code['id']],title='Four related teaching sources',course_id='c0',topic_id='t0')
    p,assets,_=draft(studio,token)
    slide_source=p['lecture_sources'][1]
    assert slide_source['kind']=='pptx' and slide_source['positions']==[1,2]
    assert assets[slide_source['asset']]==lib.original(deck['id']).read_bytes()
    assert p['lecture_sources'][3]['kind']=='py'
    assert p['lecture_sources'][3]['positions']==[1,2]


def test_canonical_formal_schedule_completed_and_reading_states_are_distinct(tmp_path):
    import sys
    sys.path.insert(0,str(__import__('pathlib').Path(__file__).parents[1]))
    from test_assessment_studio_phase_e import _database
    from personal_learning_assistant.learning_studio.assessment_bridge import formal_states
    path=_database(tmp_path)
    with sqlite3.connect(path) as con:
        con.execute("UPDATE assessments SET due_on='2026-12-01' WHERE id='a3'")
        # Keep one genuine scheduled assessment without importing a score.
        con.execute("INSERT INTO assessments(id,course_id,assessment_type,title,due_on,status,description,created_at,updated_at) VALUES('scheduled-only','course-ma','quiz','Upcoming canonical quiz','2026-12-02','pending','','now','now')")
        con.execute("INSERT INTO assessment_runtime_specs(assessment_id,mode,duration_minutes,instructions_text,origin,package_id,package_revision,created_at,updated_at) VALUES('scheduled-only','exam',30,'','external_package','schedule',1,'now','now')")
    before=path.read_bytes();states=formal_states(path,'course-ma')
    assert any(s['state']=='Completed formal attempt' for s in states)
    assert any(s['state']=='Scheduled: 2026-12-02' for s in states)
    assert path.read_bytes()==before


def test_library_handoff_preselects_original_and_real_course_in_author_controls(group):
    studio,lib,docs,token=group
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio})
    client=app.test_client();document_id=docs[2]['id']
    handoff=client.get('/library/files/'+document_id+'/learning')
    assert handoff.status_code==200 and 'Create topic with this lecture' in handoff.text
    assert 'PPTX' in handoff.text and 'require a separate PDF copy' not in handoff.text
    author=client.get('/learning/author?selected='+document_id)
    assert author.status_code==200
    assert f'value="{document_id}" checked' in author.text
    assert 'data-lecture-author' in author.text and 'learning_author.js' in author.text
    assert client.get('/learning/author?selected=missing').status_code==404


def test_v3_verbatim_math_and_code_are_preserved_and_rendered_inertly(group):
    studio,lib,docs,_=group
    raw=b'if x < y:\n    print("<script>literal</script>")'
    code=lib.upload(BytesIO(raw),'comparison.py',subject_id='c0',indexing=False)
    token=prepare(studio,lib,[docs[0]['id'],code['id']],title='Literal comparison evidence',course_id='c0',topic_id='t0')
    p,assets,pdf=draft(studio,token)
    assert 'x < y' in p['pages'][1]['text']
    assert assets[p['lecture_sources'][1]['asset']]==raw
    staged=studio.stage(p,assets,source_bytes=pdf)
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio})
    page=app.test_client().get('/learning/staged/'+staged['module_id']+'/1?view=learn&section=lesson-2')
    assert page.status_code==200
    assert '<script>literal</script>' not in page.text
    assert '&lt;script&gt;literal&lt;/script&gt;' in page.text
    assert 'x &lt; y' in page.text


def test_legacy_package_active_markup_validation_remains_strict():
    from .helpers import package,source_pdf
    from personal_learning_assistant.learning_studio.validation import validate_package
    raw=source_pdf();p=package(raw)
    p['pages'][0]['text']='<script>unsafe</script>'
    with pytest.raises(PackageError):validate_package(p,catalogue(),raw)
