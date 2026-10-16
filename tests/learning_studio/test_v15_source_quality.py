"""Source review acceptance with disposable synthetic material only."""
import copy
import json
import sqlite3
import pytest
from .test_coverage import fixture
from .helpers import catalogue
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.validation import PackageError
from personal_learning_assistant.ui.web import create_app

def setup(tmp_path):
    c,p,raw,r=fixture()
    s=LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:raw,catalogue_loader=catalogue)
    s.stage(p,coverage=r);s.publish('synthetic',1)
    return s,p,r

def correction():
    return dict(target_revision=2,section_id='lesson-1',block_index=1,text='A careful source-linked explanation.',reason='Retain the qualification.')

def test_candidate_preserves_source_keys_history_and_stays_unpublished(tmp_path):
    s,p,r=setup(tmp_path)
    s.attempt('synthetic',dict(event_id='original',module_revision=1,source_sha256=p['source']['sha256'],question_id='q1',question_revision=1,selection=0))
    before=s.module('synthetic',1,public=False);history=s.export()
    assert hasattr(s,'create_candidate'), 'Correction candidate operation missing'
    result=s.create_candidate('synthetic',1,correction())
    assert result['state']=='staged' and s.create_candidate('synthetic',1,correction())==result
    new=s.module('synthetic',2,staged=True,public=False)
    assert s.module('synthetic',1,public=False)==before and s.export()==history
    assert new['questions']==p['questions'] and new['source']==p['source']
    assert s.source('synthetic',2,staged=True)==s.source('synthetic',1)
    with pytest.raises(PackageError):s.module('synthetic',2)
    assert s.library(course_id='unmapped')['modules'][0]['revision']==1
    r=s.coverage_report('synthetic',2)
    assert r['review']['status']=='needs_review' and 'Parent package' in r['review']['method']
    assert not any(e['state']=='mapped' and any(t['block_index']==1 for t in e['mappings']) for e in r['coverage'])
    with s.store.connection(write=True) as con:
        with pytest.raises(sqlite3.IntegrityError):con.execute("UPDATE modules SET title='overwrite'")

@pytest.mark.parametrize('change',[{'target_revision':1},{'target_revision':True},{'block_index':0},
    {'text':'Synthetic source page 1. Demonstration only. No academic evidence.'},
    {'text':'<script>alert(1)</script>'},{'correct_index':0},{'reason':''},{'section_id':'missing'},{'text':'x'*30001}])
def test_bad_candidate_is_rejected_without_writes(tmp_path,change):
    s,p,r=setup(tmp_path);before=s.store.path.read_bytes()
    assert hasattr(s,'create_candidate'), 'Correction candidate operation missing'
    with pytest.raises(PackageError):s.create_candidate('synthetic',1,dict(correction(),**change))
    assert s.store.path.read_bytes()==before

def test_candidate_csrf_key_privacy_and_single_form(tmp_path):
    s,p,r=setup(tmp_path);app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s});c=app.test_client()
    path='/learning/modules/synthetic/1/coverage/candidate'
    assert c.post(path,json=correction()).status_code==403
    result=c.post(path,json=correction(),headers={'X-Learning-CSRF':app.extensions['learning_studio_csrf']})
    assert result.status_code==201 and 'correct_index' not in result.text and p['questions'][0]['explanation'] not in result.text
    text=c.get('/learning/modules/synthetic/1/coverage').text
    assert text.count('id="ls-candidate-target"')==1 and 'Source visually checked' in text
    before=s.store.path.read_bytes();assert c.get('/learning/staged/synthetic/2?view=learn').status_code==200
    assert s.store.path.read_bytes()==before

def test_provenance_conflict_and_published_target_rejected(tmp_path):
    s,p,r=setup(tmp_path)
    assert hasattr(s,'create_candidate'), 'Correction candidate operation missing'
    s.create_candidate('synthetic',1,correction());before=s.store.path.read_bytes()
    with pytest.raises(PackageError):s.create_candidate('synthetic',1,dict(correction(),reason='Competing rationale'))
    assert s.store.path.read_bytes()==before
    s.publish('synthetic',2);before=s.store.path.read_bytes()
    with pytest.raises(PackageError):s.create_candidate('synthetic',1,correction())
    assert s.store.path.read_bytes()==before

def test_concurrent_candidates_have_one_atomic_winner(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    s,p,r=setup(tmp_path);barrier=Barrier(2);stage=s.stage
    assert hasattr(s,'create_candidate'), 'Correction candidate operation missing'
    def synchronized(*args,**kwargs):
        barrier.wait(timeout=10);return stage(*args,**kwargs)
    monkeypatch.setattr(s,'stage',synchronized)
    def create(reason):
        try:return s.create_candidate('synthetic',1,dict(correction(),reason=reason))['state']
        except PackageError:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(create,['First','Second']))
    assert sorted(results)==['conflict','staged']
    with s.store.connection() as con:assert con.execute('SELECT count(*) FROM coverage_reports WHERE revision=2').fetchone()[0]==1

def test_six_axes_and_unvalidated_visual_metadata_never_certify():
    from personal_learning_assistant.learning_studio.coverage_view import project_coverage
    c,p,raw,r=fixture();r['review']['status']='agent_reviewed';r['inventory'][0]['visual_evidence']={'invalid':True}
    result=project_coverage(p,r,{})
    assert 'review_dimensions' in result, 'Separate six review dimensions missing'
    axes=result['review_dimensions']
    assert {'mechanically_present','source_visually_checked','source_faithfully_interpreted','instructor_intent_reviewed','external_claim_checked','canonical_topic_mapping_reviewed'}==set(axes)
    assert axes['source_visually_checked']['status']=='not recorded'
    assert all(not a['certified'] for a in axes.values())

def test_ambiguous_options_warn_without_choice_or_key_leak():
    from personal_learning_assistant.learning_studio.authoring import preflight
    c,p,raw,r=fixture();p['questions'][0]['options']=['  Same answer','same ANSWER  ']
    result=preflight(p,raw,{},catalogue(),source_id='fixture-source')
    assert result['valid'] and 'ambiguous-options' in {w['code'] for w in result['warnings']}
    assert 'Same answer' not in json.dumps(result) and 'correct_index' not in json.dumps(result)

def test_pdf_resource_cues_are_structural_not_visual_extraction():
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,NumberObject,DecodedStreamObject
    from personal_learning_assistant.learning_studio import authoring
    assert hasattr(authoring,'pdf_features'), 'Bounded PDF material inspection missing'
    writer=PdfWriter();page=writer.add_blank_page(width=100,height=100)
    image=DecodedStreamObject();image.set_data(b'\0\0\0');image.update({NameObject('/Subtype'):NameObject('/Image'),NameObject('/Width'):NumberObject(1),NameObject('/Height'):NumberObject(1)})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im1'):writer._add_object(image)})})
    out=io.BytesIO();writer.write(out);features=authoring.pdf_features(out.getvalue())
    assert features['pages'][0]['raster_resources']==1 and not features['semantic_certification']
    assert features['vector_formula_speaker_notes']=='unsupported / needs review'


def test_changed_explanation_invalidates_retained_source_quote(tmp_path):
    s,p,r=setup(tmp_path)
    before=s.coverage_report('synthetic',1)
    assert any(m['section_id']=='lesson-1' and m['block_index']==1
               for e in before['coverage'] for m in e['mappings'])
    previous=p['sections'][0]['blocks'][1]['text']
    s.create_candidate('synthetic',1,dict(correction(),
        text=previous+'\\n\\nAn additional interpretation that needs fresh source review.'))
    new=s.coverage_report('synthetic',2)
    assert all(not (m['section_id']=='lesson-1' and m['block_index']==1)
               for e in new['coverage'] for m in e['mappings'])
    assert any(e['state']=='unresolved' for e in new['coverage'])
    assert new['review']['status']=='needs_review'
    assert s.coverage_report('synthetic',1)==before


def test_correction_cannot_jump_module_revisions(tmp_path):
    s,p,r=setup(tmp_path)
    original=s.store.path.read_bytes()
    with pytest.raises(PackageError,match='next consecutive'):
        s.create_candidate('synthetic',1,dict(correction(),target_revision=9))
    assert s.store.path.read_bytes()==original
    assert s.library(course_id='unmapped')['modules'][0]['revision']==1
