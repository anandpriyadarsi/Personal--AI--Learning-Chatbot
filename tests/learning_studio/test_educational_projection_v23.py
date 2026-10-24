"""Projection correctness, source independence and faithful authored content."""
from contextlib import closing
from dataclasses import replace
from io import BytesIO
import hashlib
import sqlite3
import pytest
from pypdf import PdfReader
from tests.academic_evidence_v23_fixtures import uc_owners, PAGE_TEXT
from tests.test_academic_evidence_v23 import NOW, inventory, service, event, owners
from tests.test_academic_evidence_v23_web import app, token
from personal_learning_assistant.learning_studio.educational_projection import build_preview, tutor_handoff
from personal_learning_assistant.learning_studio.validation import PackageError

BASE='/academic-evidence/learning/uc100n-demo/1'

def test_real_synthetic_pdf_and_all_authored_instructional_blocks(uc_owners,tmp_path):
    s=service(uc_owners);cat=s.catalogue();before=inventory(tmp_path)
    p=build_preview(uc_owners[1],'uc100n-demo',1,catalogue=cat,as_of=NOW)
    raw=uc_owners[1].source('uc100n-demo',1)
    assert [x.extract_text().strip() for x in PdfReader(BytesIO(raw)).pages]==[x.strip() for x in PAGE_TEXT]
    assert p['mapping']['topic_id']=='v23-data' and p['mapping_status']=='reviewed_current_catalogue'
    blocks=p['sections'][0]['blocks'];assert {'source','definition','table','example','graph','image','activity','misconception','recall'}<={b['kind'] for b in blocks}
    assert 'PRIVATE-RECALL-ANSWER' not in str(p) and 'correct_index' not in str(p)
    assert p['revision'] and all(ref['review_flags'] for b in blocks for ref in b['source_refs'])
    c=app(uc_owners).test_client();html=c.get(BASE).get_data(as_text=True)
    for value in ['measure the score variable','sum 14 then divide by 2','Which column answers','Case IDs label rows','Revision checklist','Synthetic authored fidelity requires']:
        assert value in html,value
    assert 'PRIVATE-RECALL-ANSWER' not in html
    image=c.get(BASE+'/assets/cases.png')
    assert image.status_code==200 and image.mimetype=='image/png'
    assert inventory(tmp_path)==before

@pytest.mark.parametrize('pages',[[0],[4],[True],[1,1],[[]],['1']])
def test_tutor_rejects_invalid_page_shapes(uc_owners,pages):
    with pytest.raises(PackageError):
        tutor_handoff(uc_owners[1],{'module_id':'uc100n-demo','module_revision':1,
            'source_sha256':uc_owners[2]['source']['sha256'],'pages':pages,'student_question':'Why divide by two?'},
            catalogue=service(uc_owners).catalogue(),as_of=NOW)

def test_pdf_remains_available_when_evidence_inventory_is_excessive(owners,tmp_path,monkeypatch):
    from personal_learning_assistant.services.academic_evidence_service import AcademicEvidenceService
    def unavailable(*a,**k):raise PackageError('Practice projection exceeds bound.',413)
    monkeypatch.setattr(AcademicEvidenceService,'learning',unavailable)
    before=inventory(tmp_path);c=app(owners).test_client()
    assert c.get('/academic-evidence/learning/synthetic/1').status_code==413
    pdf=c.get('/academic-evidence/learning/synthetic/1/source.pdf')
    assert pdf.status_code==200 and hashlib.sha256(pdf.data).hexdigest()==owners[2]['source']['sha256']
    assert pdf.headers['Content-Security-Policy']=='sandbox'
    assert inventory(tmp_path)==before

def test_practice_identity_revision_event_and_time_are_traceable(owners):
    event(owners,'distinct-attempt',1)
    v=service(owners).learning('synthetic',1)
    r=next(r for r in v.records if r.kind=='learning_practice')
    assert r.question_id=='q1' and r.question_revision==1
    assert any(ref.kind=='learning_event' and ref.identifier=='distinct-attempt' for ref in r.source_refs)
    assert any(ref.kind=='learning_question' and ref.identifier=='q1' and ref.revision==1 for ref in r.source_refs)
    html=app(owners).test_client().get('/academic-evidence/learning/synthetic/1').get_data(as_text=True)
    for value in ['distinct-attempt','q1','deterministic practice','Assistance: unknown','2026-10-21']:
        assert value in html,value

def test_backlog_is_planning_intent_and_completion_is_self_report(uc_owners):
    from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
    from personal_learning_assistant.services.operational_task_service import OperationalTaskService
    from uuid import uuid4
    owner=build_operational_planner_web_service(uc_owners[0]).tasks
    # Use the projection's frozen clock for the canonical writer too. A real
    # creation time after NOW must correctly be blocked, not backdated by
    # changing only updated_at in this fixture.
    writer=OperationalTaskService(owner.repository,now=lambda:NOW.isoformat())
    task=writer.create_manual_study_task(
        intent_id=str(uuid4()),title='Review source',description='',course_id='v23-uc100n',topic_id='v23-data',
        topic_name='Observations and variables',estimated_minutes=30)
    with closing(sqlite3.connect(uc_owners[0])) as c,c:
        c.execute("UPDATE planner_tasks SET updated_at=?",(NOW.isoformat(),))
    r=next(r for r in service(uc_owners).learning('uc100n-demo',1).records if r.kind=='planner_task')
    assert r.qualification=='planning_intent' and r.actual_minutes is None
    with closing(sqlite3.connect(uc_owners[0])) as c,c:
        c.execute("UPDATE planner_tasks SET status='completed',completed_at=?,updated_at=?",(NOW.isoformat(),)*2)
    r=next(r for r in service(uc_owners).learning('uc100n-demo',1).records if r.kind=='planner_task')
    assert r.qualification=='completion_signal' and r.independence=='unknown'

def test_intent_uses_one_learning_context_and_preserves_captured_topic_name(owners,monkeypatch):
    # A later second owner capture must never replace the mapping used by the
    # reviewed fingerprint. The writer still checks that exact pair/name itself.
    from personal_learning_assistant.services.academic_evidence_service import AcademicEvidenceService
    c=app(owners).test_client();t=token(c.get('/academic-evidence/learning/synthetic/1/study-preview'))
    original=AcademicEvidenceService.frozen_learning;calls=[]
    def guarded(self,*args,**kwargs):
        calls.append(self.studio)
        if len(calls)>2:raise AssertionError('Reopened live owner after fingerprint validation')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(AcademicEvidenceService,'frozen_learning',guarded)
    assert c.post('/academic-evidence/learning/synthetic/1/study-intent',data={'intent_token':t}).status_code==303

@pytest.mark.parametrize('field,value,reason',[
    ('completed_at','2026-10-21T10:00:01+00:00','effort_after_as_of'),
    ('updated_at','2026-10-21T10:00:01+00:00','effort_after_as_of'),
    ('created_at','2026-10-21T10:00:01+00:00','effort_after_as_of'),
    ('completed_at','bad','effort_timestamp_invalid'),
    ('updated_at','2026-10-21T09:00:00','effort_timestamp_invalid'),
    ('completed_at',None,'effort_timestamp_invalid'),
    ('completed_at',NOW.isoformat(),None)])
def test_effort_is_qualified_by_event_clock_not_only_agenda_date(uc_owners,field,value,reason,tmp_path):
    with closing(sqlite3.connect(uc_owners[0])) as c,c:
        c.execute("""INSERT INTO planner_tasks(id,title,priority,status,estimated_minutes,course_id,topic_id,created_at,updated_at,completed_at)
            VALUES('effort-task','Practice','P2','completed',30,'v23-uc100n','v23-data',?,?,?)""",(NOW.isoformat(),)*3)
        c.execute("""INSERT INTO daily_agendas(id,agenda_date,status,generated_at,approved_at,created_at,updated_at)
            VALUES('effort-day','2026-10-21','approved',?,?,?,?)""",(NOW.isoformat(),)*4)
        c.execute("""INSERT INTO daily_agenda_items(id,agenda_id,ordinal,item_kind,source_type,source_id,title,planned_minutes,actual_minutes,status,created_at,updated_at,completed_at)
            VALUES('effort-item','effort-day',1,'task','planner_task','effort-task','Practice',30,35,'completed',?,?,?)""",(NOW.isoformat(),)*3)
        c.execute('UPDATE daily_agenda_items SET '+field+'=? WHERE id=?',(value,'effort-item'))
    before=inventory(tmp_path)
    r=next(r for r in service(uc_owners).learning('uc100n-demo',1).records if r.kind=='planner_task')
    if reason:
        assert r.actual_minutes is None and reason in r.reasons and r.qualification=='blocked'
    else:assert r.actual_minutes==35 and r.qualification=='completion_signal'
    assert inventory(tmp_path)==before

@pytest.mark.parametrize('field',['created_at','updated_at'])
def test_future_task_state_cannot_use_an_older_completion_clock(uc_owners,field):
    with closing(sqlite3.connect(uc_owners[0])) as c,c:
        c.execute("""INSERT INTO planner_tasks(id,title,priority,status,estimated_minutes,course_id,topic_id,created_at,updated_at,completed_at)
            VALUES('future-task','Practice','P2','completed',30,'v23-uc100n','v23-data',?,?,?)""",(NOW.isoformat(),)*3)
        c.execute('UPDATE planner_tasks SET '+field+"='2026-10-21T10:00:01+00:00'")
    r=next(r for r in service(uc_owners).learning('uc100n-demo',1).records if r.kind=='planner_task')
    assert r.qualification=='blocked' and r.outcome=='unverified' and 'occurrence_after_as_of' in r.reasons
    assert r.actual_minutes is None and all(not ref.url for ref in r.source_refs)
