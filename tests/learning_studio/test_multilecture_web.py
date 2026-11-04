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
