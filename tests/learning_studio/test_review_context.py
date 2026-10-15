import copy
import pytest
from .helpers import package, source_pdf, catalogue
from .test_service import publish,event
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app


@pytest.fixture
def studio(tmp_path):
    return LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:source_pdf(),catalogue_loader=catalogue)


def test_review_context_only_graded_misses_exact_version_no_keys(studio):
    p=publish(studio,package(mapped=True))
    other=package(module_id='other');publish(studio,other)
    studio.attempt('other',event(other,'other-wrong'))
    empty=studio.review_context('synthetic',1)
    assert empty['missed_questions']==[] and empty['attempts']==0
    studio.attempt('synthetic',event(p,'wrong'))
    studio.attempt('synthetic',event(p,'correct',1))
    new=copy.deepcopy(p);new['module_revision']=2
    new['questions'][0]['revision']=2;new['questions'][0]['correct_index']=0
    publish(studio,new)
    brief=studio.review_context('synthetic',1)
    assert brief['module_revision']==1 and brief['source']['sha256']==p['source']['sha256']
    assert brief['attempts']==2 and brief['evidence_label']=='Limited evidence'
    assert brief['missed_questions'][0]['question_revision']==1
    assert brief['missed_questions'][0]['latest_correct'] is True
    assert '/synthetic/1' in brief['missed_questions'][0]['lesson_url']
    assert brief['mapping_status']=='reviewed_current_catalogue'
    assert 'correct_index' not in str(brief) and 'explanation' not in str(brief)
    assert 'other' not in str(brief)


def test_review_context_detects_missing_mapping_and_get_is_pure(studio):
    p=publish(studio,package(mapped=True));studio.attempt('synthetic',event(p))
    studio.catalogue_loader=lambda:{'available':True,'courses':[]}
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio})
    c=app.test_client();before=studio.store.path.read_bytes()
    response=c.get('/learning/modules/synthetic/1/review-context')
    assert response.status_code==200
    assert response.json['mapping_status']=='needs_review'
    assert response.json['automatic_tutor_consumption'] is False
    assert c.get('/learning/modules/synthetic/1/review-brief').status_code==200
    assert b'Copy review brief' in c.get('/learning/modules/synthetic/1?view=weak').data
    assert studio.store.path.read_bytes()==before
