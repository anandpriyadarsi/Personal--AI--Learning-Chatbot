"""Source-linked V2.3 tests use disposable canonical and Learning owner stores."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sqlite3
import pytest
from tests.learning_studio.helpers import package, source_pdf
from tests.test_assessment_studio_phase_e import _database
from personal_learning_assistant.learning_studio.service import LearningStudioService

NOW=datetime(2026,10,21,10,tzinfo=timezone.utc)

def api():
    from personal_learning_assistant.services import academic_evidence_service
    return academic_evidence_service

def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

@pytest.fixture
def owners(tmp_path,monkeypatch):
    from personal_learning_assistant.learning_studio import service as owner
    monkeypatch.setattr(owner,'now',lambda:NOW.isoformat())
    db=_database(tmp_path)
    # This branch exercises the stable DELETE read contract. WAL is covered by
    # its own owner-publication and fail-closed cases; never change a live source.
    with closing(sqlite3.connect(db)) as c:
        assert c.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete'
    raw=source_pdf();p=package(raw,mapped=True)
    p['mapping'].update(course_id='course-ma',topic_id='topic-lu',topic_name='LU Factorization')
    cat={'available':True,'courses':[{'id':'course-ma','code':'MA103N','name':'Linear Algebra','topics':[{'id':'topic-lu','name':'LU Factorization'}]}]}
    studio=LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:raw,catalogue_loader=lambda:cat)
    studio.stage(p);studio.publish('synthetic',1)
    return db,studio,p

def service(owners,**kwargs):
    return api().AcademicEvidenceService(owners[0],studio=owners[1],now=lambda:NOW,**kwargs)

def event(owners,key='practice-1',selection=0):
    return owners[1].attempt('synthetic',{'event_id':key,'module_revision':1,'source_sha256':owners[2]['source']['sha256'],'question_id':'q1','question_revision':1,'selection':selection})

def test_source_qualified_practice_remains_a_study_signal(owners,tmp_path):
    event(owners);before=inventory(tmp_path);v=service(owners).learning('synthetic',1)
    assert v.schema=='anvaya.academic-evidence.v1' and v.policy_version=='academic-evidence-v2.3.1'
    assert v.source_status=='published_snapshot_validated' and v.mapping_status=='reviewed_current_catalogue'
    assert v.production_authority=='blocked' and v.mastery=='unknown' and not v.automatic_eligible
    r=next(r for r in v.records if r.kind=='learning_practice')
    assert r.qualification=='study_signal' and r.independence=='unknown' and r.evaluator=='deterministic_practice' and r.outcome=='incorrect'
    assert r.source_refs[0].sha256==owners[2]['source']['sha256'] and v.manual_task_allowed
    assert inventory(tmp_path)==before
    assert 'correct_index' not in str(v.to_dict()) and 'source_blob' not in str(v.to_dict()) and str(owners[0]) not in str(v.to_dict())

def test_absence_is_unknown_not_failed_grade(owners):
    v=service(owners).learning('synthetic',1)
    assert not any(r.kind=='learning_practice' for r in v.records) and v.mastery=='unknown'
    assert any('No practice' in s for s in v.explanations)

@pytest.mark.parametrize('sql',["UPDATE topics SET deleted_at='2026-10-01' WHERE id='topic-lu'","UPDATE topics SET name='Changed' WHERE id='topic-lu'","UPDATE topics SET course_id='other-course' WHERE id='topic-lu'","UPDATE courses SET deleted_at='2026-10-01' WHERE id='course-ma'"])
def test_stale_deleted_cross_course_mapping_never_qualifies(owners,sql):
    with closing(sqlite3.connect(owners[0])) as c,c:
        c.execute("INSERT INTO courses(id,code,name,created_at,updated_at) VALUES('other-course','OTHER','Other',?,?)",(NOW.isoformat(),)*2);c.execute(sql)
    v=service(owners).learning('synthetic',1)
    assert v.mapping_status=='unverified' and not v.manual_task_allowed and v.mastery=='unknown'

@pytest.mark.parametrize('field,value,reason',[('source_hash','0'*64,'source_revision_mismatch'),('question_revision',2,'question_revision_mismatch'),('question_id','forged','question_identity_unavailable'),('timestamp','2027-01-01T00:00:00Z','occurrence_after_as_of'),('timestamp','2026-10-19T00:00:00','occurrence_invalid'),('correct',1,'practice_outcome_conflict')])
def test_adversarial_captured_owner_event_is_blocked(owners,field,value,reason):
    event(owners)
    with owners[1].store.connection() as c:r=dict(c.execute('SELECT * FROM attempts').fetchone())
    r[field]=value
    rows=api().qualify_learning_events(owners[2],[r],as_of=NOW,mapping_status='reviewed_current_catalogue')
    assert len(rows)==1 and rows[0].qualification=='blocked' and reason in rows[0].reasons
    assert all(not ref.url for ref in rows[0].source_refs)

def test_duplicate_event_is_blocked_not_counted_twice(owners):
    event(owners)
    with owners[1].store.connection() as c:r=dict(c.execute('SELECT * FROM attempts').fetchone())
    rows=api().qualify_learning_events(owners[2],[r,r],as_of=NOW,mapping_status='reviewed_current_catalogue')
    assert len(rows)==1 and rows[0].qualification=='blocked' and 'duplicate_event' in rows[0].reasons

def test_repeated_correct_answers_do_not_prove_independence(owners):
    s=service(owners);old=s.learning('synthetic',1)
    for i in range(3):event(owners,'correct-'+str(i),1)
    v=s.learning('synthetic',1);rows=[r for r in v.records if r.kind=='learning_practice']
    assert len(rows)==3 and v.fingerprint!=old.fingerprint
    assert all(r.qualification=='study_signal' and r.independence=='unknown' for r in rows)
    assert v.mastery=='unknown' and not v.automatic_eligible

def test_historical_assessment_mapping_and_source_are_unverified(owners):
    v=service(owners).topic('course-ma','topic-lu');rows=[r for r in v.records if r.kind=='assessment_evaluation']
    assert len(rows)==3 and all(r.mapping_status=='unverified' and r.source_status=='historical_unverified' for r in rows)
    assert all(r.independence=='unknown' and r.qualification!='qualified' for r in rows)

def test_wrong_namespaced_bridge_is_blocked(owners):
    with closing(sqlite3.connect(owners[0])) as c,c:
        c.execute("INSERT INTO question_attempts(id,question_id,attempt_number,outcome,max_marks_milli,occurred_at,evaluation_ref) VALUES('bridge','q1',1,'incorrect',2000,?,'assessment_response_evaluation:wrong')",(NOW.isoformat(),))
        c.execute("UPDATE assessment_response_evaluations SET question_attempt_id='bridge' WHERE id='ev-sq1'")
    r=next(r for r in service(owners).topic('course-ma','topic-lu').records if r.identifier=='assessment_response_evaluation:ev-sq1')
    assert r.qualification=='blocked' and 'inconsistent_bridge_reference' in r.reasons and all(not ref.url for ref in r.source_refs)

def test_missing_database_never_created(tmp_path):
    p=tmp_path/'absent.db'
    assert api().AcademicEvidenceService(p,now=lambda:NOW).catalogue()['available'] is False and not p.exists()

def test_no_live_loaders_are_called(owners):
    def unsafe(*a,**k):raise AssertionError('Live loader called')
    owners[1].source_loader=unsafe;owners[1].catalogue_loader=unsafe
    assert service(owners).learning('synthetic',1).source_status=='published_snapshot_validated'

@pytest.mark.parametrize('suffix',['-wal','-shm','-journal'])
def test_studio_sidecars_fail_closed_without_changes(owners,tmp_path,suffix):
    Path(str(owners[1].store.path)+suffix).write_bytes(b'synthetic sidecar');before=inventory(tmp_path)
    with pytest.raises(Exception) as e:service(owners).learning('synthetic',1)
    assert getattr(e.value,'status',None)==503 and inventory(tmp_path)==before

def test_wal_without_publisher_preserves_inventory(owners,tmp_path):
    c=sqlite3.connect(owners[0])
    try:
        c.execute('PRAGMA journal_mode=WAL');c.execute("UPDATE topics SET confidence=2 WHERE id='topic-lu'");c.commit();before=inventory(tmp_path)
        assert service(owners).catalogue()['available'] is False and inventory(tmp_path)==before
    finally:c.close()

def test_frozen_owner_connections_are_memory_query_only(owners):
    from personal_learning_assistant.learning_studio.read_snapshot import frozen_studio
    s=frozen_studio(owners[1],catalogue=service(owners).catalogue())
    with s.store.connection() as c:
        assert c.execute('PRAGMA query_only').fetchone()[0]==1 and c.execute('PRAGMA database_list').fetchone()[2]==''
        with pytest.raises(sqlite3.OperationalError):c.execute('CREATE TABLE forbidden(id)')
    with pytest.raises(Exception):
        with s.store.connection(write=True):pass
