from .helpers import package, source_pdf, catalogue
from .test_service import publish,event
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.analysis_view import component
from personal_learning_assistant.ui.web import create_app


def studio(tmp_path):
    return LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:source_pdf(),catalogue_loader=catalogue)


def test_component_missing_store_no_initialization(tmp_path):
    s=studio(tmp_path);result=component(s)
    assert result['evidence_label']=='No evidence' and result['signals']==[]
    assert not s.store.path.exists()


def test_component_recovery_actions_mapping_and_purity(tmp_path):
    s=studio(tmp_path);p=publish(s,package(mapped=True))
    s.attempt('synthetic',event(p,'wrong'));s.attempt('synthetic',event(p,'right',1))
    s.catalogue_loader=lambda:{'available':False,'courses':[]}
    before=s.store.path.read_bytes();result=component(s);signal=result['signals'][0]
    assert signal['recovered']==1 and signal['currently_wrong']==0
    assert signal['mapping_status']=='needs_review'
    assert '/synthetic/1' in signal['recheck_url'] and '#question-q1' in signal['recheck_url']
    assert signal['evidence_label']=='Limited evidence' and 'recheck' in signal['reason']
    assert s.store.path.read_bytes()==before


def test_integrated_analysis_missing_store(tmp_path):
    s=studio(tmp_path);app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    response=app.test_client().get('/analysis')
    assert response.status_code==200
    assert b'No evidence' in response.data and b'Try a lesson self-check' in response.data
    assert not s.store.path.exists()


def test_integrated_analysis_actionable_and_pure(tmp_path):
    s=studio(tmp_path);p=publish(s,package());s.attempt('synthetic',event(p))
    before=s.store.path.read_bytes();app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    response=app.test_client().get('/analysis')
    assert response.status_code==200
    assert b'Review lesson' in response.data and b'Recheck' in response.data and b'Open revision' in response.data
    assert b'unmapped' in response.data and b'Limited evidence' in response.data
    assert s.store.path.read_bytes()==before


def test_component_correct_only_is_insufficient_not_mastery(tmp_path):
    s=studio(tmp_path);p=publish(s,package());s.attempt('synthetic',event(p,'right',1))
    result=component(s)
    assert result['signals'][0]['evidence_label']=='Limited evidence'
    assert 'do not establish mastery' in result['signals'][0]['reason']


def test_component_bounds_recent_lectures(tmp_path):
    s=studio(tmp_path)
    for i in range(10):
        p=package(module_id=f'lecture-{i}');publish(s,p);s.attempt(p['module_id'],event(p,f'event-{i}'))
    result=component(s)
    assert len(result['signals'])==8 and result['truncated']
    assert '/lecture-9/1' in result['signals'][0]['review_url']


def test_component_source_failure_keeps_other_analysis_available(tmp_path):
    from personal_learning_assistant.learning_studio.validation import PackageError
    s=studio(tmp_path);p=publish(s,package());s.attempt('synthetic',event(p))
    def unavailable(*args):raise PackageError('source unavailable',503)
    s.source=unavailable
    result=component(s)
    assert result['available'] and result['signals'][0]['unavailable']
    assert 'review_url' not in result['signals'][0]
