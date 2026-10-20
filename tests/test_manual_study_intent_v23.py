"""Transactional manual intent is distinct from automatic remediation."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import sqlite3
import pytest
from tests.test_academic_evidence_v23 import owners

def task_owner(owners):
    from personal_learning_assistant.services.operational_task_service import OperationalTaskService
    from personal_learning_assistant.repositories.sqlite.planner_task_repository import SQLitePlannerTaskRepository
    return OperationalTaskService(SQLitePlannerTaskRepository(owners[0]))

def payload():
    return dict(intent_id=str(uuid4()),title='Manual practice: exact lesson',description='Student chose module synthetic revision 1.',course_id='course-ma',topic_id='topic-lu',topic_name='LU Factorization',estimated_minutes=30)

def test_one_intent_has_one_stable_receipt_and_does_not_mutate_factory(owners):
    s=task_owner(owners);p=payload();factory=s._id_factory
    one=s.create_manual_study_task(**p);two=s.create_manual_study_task(**p)
    assert one['id']==two['id'] and two['status']=='backlog'
    assert one['course_id']=='course-ma' and one['topic_id']=='topic-lu' and one['external_id'] is None
    assert s._id_factory is factory
    with closing(sqlite3.connect(owners[0])) as c,c:assert c.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==1

def test_concurrent_repeat_intent_is_one_receipt(owners):
    s=task_owner(owners);p=payload()
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda _:s.create_manual_study_task(**p),range(8)))
    assert len({r['id'] for r in rows})==1
    with closing(sqlite3.connect(owners[0])) as c,c:assert c.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==1

def test_completed_receipt_is_not_reset_by_retry(owners):
    s=task_owner(owners);p=payload();one=s.create_manual_study_task(**p)
    s.transition(one['id'],'completed')
    assert s.create_manual_study_task(**p)['status']=='completed'

@pytest.mark.parametrize('change',[{'title':'Different'},{'estimated_minutes':60},{'description':'Changed source context'}])
def test_same_intent_different_context_conflicts_without_rows(owners,change):
    from personal_learning_assistant.services.operational_task_service import OperationalTaskConflictError
    s=task_owner(owners);p=payload();s.create_manual_study_task(**p)
    before=owners[0].read_bytes()
    with pytest.raises(OperationalTaskConflictError):s.create_manual_study_task(**{**p,**change})
    assert owners[0].read_bytes()==before

@pytest.mark.parametrize('sql',["UPDATE topics SET deleted_at='2026-10-01' WHERE id='topic-lu'","UPDATE topics SET name='Stale name' WHERE id='topic-lu'","UPDATE topics SET course_id='other' WHERE id='topic-lu'","UPDATE courses SET deleted_at='2026-10-01' WHERE id='course-ma'"])
def test_active_exact_identity_is_checked_in_writer_transaction(owners,sql):
    from personal_learning_assistant.services.operational_task_service import OperationalTaskConflictError
    with closing(sqlite3.connect(owners[0])) as c,c:
        c.execute("INSERT INTO courses(id,code,name,created_at,updated_at) VALUES('other','OTHER','Other','2026-10-01','2026-10-01')");c.execute(sql)
    before=owners[0].read_bytes()
    with pytest.raises(OperationalTaskConflictError):task_owner(owners).create_manual_study_task(**payload())
    assert owners[0].read_bytes()==before

@pytest.mark.parametrize('key,value',[('intent_id','not-a-uuid'),('estimated_minutes',False),('estimated_minutes',0),('estimated_minutes',181)])
def test_invalid_intent_never_creates_a_task(owners,key,value):
    from personal_learning_assistant.services.operational_task_service import OperationalTaskValidationError
    with pytest.raises(OperationalTaskValidationError):task_owner(owners).create_manual_study_task(**{**payload(),key:value})
    with closing(sqlite3.connect(owners[0])) as c,c:assert c.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==0
