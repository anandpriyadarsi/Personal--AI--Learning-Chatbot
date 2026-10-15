"""Explicit external real pilot acceptance; copyrighted lecture data is not committed."""
import hashlib
import os
from pathlib import Path
import sqlite3
import pytest
from personal_learning_assistant.learning_studio.archive import read_zip
from personal_learning_assistant.learning_studio.pilot import convert_pilot
from personal_learning_assistant.learning_studio.demo import make_demo
from personal_learning_assistant.ui.web import create_app

CANDIDATE_SHA = 'e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923'
SOURCE_SHA = '75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411'


@pytest.fixture
def recovered_pilot(tmp_path):
    path = os.environ.get('ANVAYA_TEST_RECOVERED_PILOT_ZIP')
    if not path: pytest.skip('External recovered pilot missing; no actual pilot import is claimed.')
    candidate = Path(path).read_bytes()
    assert hashlib.sha256(candidate).hexdigest() == CANDIDATE_SHA
    package, source, assets = convert_pilot(candidate)
    service = make_demo(tmp_path / 'real-pilot-demo', pilot_zip=path)
    return service, package, source, assets


def test_external_recovered_pilot_strict_import_and_durable_evidence(recovered_pilot):
    service, p, source, assets = recovered_pilot
    assert p['mapping'] is None and p['source']['sha256'] == SOURCE_SHA
    assert len(p['pages']) == 20 and len(p['sections']) == 20 and len(p['questions']) == 31
    assert all(page['status'] == 'needs_review' and page['review_flags'] for page in p['pages'])
    assert service.source(p['module_id'], 1) == source
    for page in p['pages']:
        assert service.asset(p['module_id'], 1, page['preview']) == assets[page['preview']]
    registry = service.store.path.parent / 'source-registry.sqlite3'
    protected_before = hashlib.sha256(registry.read_bytes()).hexdigest()
    app = create_app({'TESTING': True, 'LEARNING_STUDIO_SERVICE_FACTORY': lambda: service})
    client = app.test_client()
    base = f'/learning/modules/{p["module_id"]}/1'
    assert client.get(base+'/source.pdf').data == source
    for view in ('learn','visualise','revision','practice','weak','source'):
        response = client.get(base+'?view='+view)
        assert response.status_code == 200
        if view == 'practice': assert b'correct_index' not in response.data
    for page in range(1,21):
        source_html=client.get(base+'?view=source&page='+str(page)).data
        assert f'id="source-page-{page}"'.encode() in source_html
        assert source_html.count(b'class="ls-source-page"')==1
    assert len(p['revision']) and 'correct_index' not in client.get(base+'/package').json['questions'][0]
    from personal_learning_assistant.learning_studio.pilot_quality import normalize_pilot
    new, _, new_assets=normalize_pilot(Path(os.environ['ANVAYA_TEST_RECOVERED_PILOT_ZIP']).read_bytes(),source_id=service.module(p['module_id'],1)['source']['source_id'])
    service.stage(new,new_assets);service.publish(new['module_id'],2)
    assert new['questions']==p['questions']
    revised=base.rsplit('/',1)[0]+'/2'
    assert client.get(revised+'?view=revision').data.count(b'Reveal recall answer')==12
    for section in new['sections']:
        response=client.get(revised+'?view=learn&section='+section['id'])
        assert response.status_code==200 and response.data.count(b'class="ls-lesson"')==1
    q = p['questions'][0]
    def submit(event_id, selection):
        return client.post(base+'/attempts', json={'event_id': event_id,'module_revision':1,
            'source_sha256':SOURCE_SHA,'question_id':q['id'],'question_revision':q['revision'],
            'selection':selection,'is_correct':True}, headers={'X-Learning-CSRF':app.extensions['learning_studio_csrf']})
    wrong=(q['correct_index']+1)%len(q['options'])
    assert submit('real-wrong',wrong).json['correct'] is False
    assert submit('real-correct',q['correct_index']).json['correct'] is True
    assert service.weak(p['module_id'],1)[0]['status']=='recovered_needs_recheck'
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    reopened=LearningStudioService(service.store.path,source_loader=service.source_loader,catalogue_loader=service.catalogue_loader)
    assert reopened.weak(p['module_id'],1)[0]['incorrect_count']==1
    assert reopened.export()['events'][0]['correct']==0
    assert client.get(base+'?view=weak').status_code==200
    assert hashlib.sha256(registry.read_bytes()).hexdigest()==protected_before
    with sqlite3.connect(service.store.path) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()


def test_external_pilot_demo_does_not_fabricate_course_mappings(recovered_pilot):
    service, p, source, assets = recovered_pilot
    library=service.library()
    assert library['unmapped_count']==1
    assert sum(c['module_count'] for c in library['courses'])==0
    assert service.library(course_id='unmapped')['total']==1
