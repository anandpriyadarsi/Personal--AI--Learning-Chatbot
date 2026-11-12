"""Exact capture identities and lifecycle presentation."""
import sqlite3

import pytest

from tests.test_phase7_5_operational_tasks import _service
from personal_learning_assistant.services.operational_task_service import OperationalTaskValidationError, OperationalTaskConflictError


def _catalogue(path):
    with sqlite3.connect(path) as c:
        for key in ('c1','c2'):
            c.execute("INSERT INTO courses(id,code,name,created_at,updated_at) VALUES(?,?,?,?,?)",(key,key,key,'now','now'))
        c.execute("INSERT INTO topics(id,course_id,name,normalized_name,created_at,updated_at) VALUES('t1','c1','Topic','topic','now','now')")
        c.execute("INSERT INTO assessments(id,course_id,assessment_type,title,created_at,updated_at) VALUES('a1','c1','exam','Exam','now','now')")


def test_exact_course_capture_and_unlinked_all_tasks(tmp_path):
    service,path = _service(tmp_path); _catalogue(path)
    service.create_task(title='Linked',course_id='c1',topic_id='t1',assessment_id='a1')
    service.create_task(title='Unlinked')
    assert [t['title'] for t in service.tasks_workspace(course_id='c1')['tasks']] == ['Linked']
    assert len(service.tasks_workspace()['tasks']) == 2
    assert service.tasks_workspace()['catalogue']['assessments'][0]['due_on'] is None


@pytest.mark.parametrize('refs',[{'course_id':'c2','topic_id':'t1'},{'topic_id':'t1'},{'course_id':'c2','assessment_id':'a1'},{'course_id':'missing'}])
def test_cross_course_or_missing_reference_rejected(tmp_path, refs):
    service,path = _service(tmp_path); _catalogue(path)
    with pytest.raises((OperationalTaskValidationError, OperationalTaskConflictError)):
        service.create_task(title='Invalid',**refs)
    assert not service.tasks_workspace()['tasks']


@pytest.mark.parametrize('day',['someday','2026-02-30','11/12/2026'])
def test_invalid_preferred_day_rejected(tmp_path,day):
    service,_ = _service(tmp_path)
    with pytest.raises(OperationalTaskValidationError): service.create_task(title='x',preferred_day=day)


def test_timing_review_and_legal_history_actions(tmp_path):
    service,path = _service(tmp_path)
    task = service.create_task(title='Legacy',preferred_day='Monday')
    with sqlite3.connect(path) as c:
        c.execute("UPDATE planner_tasks SET preferred_day='eventually',status='skipped' WHERE id=?",(task['id'],))
    shown = service.tasks_workspace(status='all')['tasks'][0]
    assert shown['timing_needs_review']
    assert 'completed' not in shown['allowed_transitions']
    with sqlite3.connect(path) as c: c.execute("UPDATE planner_tasks SET status='archived' WHERE id=?",(task['id'],))
    assert service.tasks_workspace(status='archived')['tasks'][0]['allowed_transitions'] == ()
    assert not service.tasks_workspace()['tasks']


def test_capture_error_preserves_entered_values_and_discloses_details():
    from tests.test_phase7_5_operational_planner_routes import FakePlanner, _app
    from personal_learning_assistant.services.operational_planner_web_service import OperationalPlannerWebValidationError
    from personal_learning_assistant.ui.web.pao_commands import command_token
    fake = FakePlanner()
    def reject(**payload): raise OperationalPlannerWebValidationError('Choose valid timing.')
    fake.create_task = reject
    app = _app(fake)
    with app.test_request_context(): token = command_token('planning')
    response = app.test_client().post('/planning/tasks',data={'pao_token':token,'title':'Keep this title','description':'Keep these details','preferred_day':'someday'})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert 'value="Keep this title"' in html and 'Keep these details</textarea>' in html
    assert 'value="someday"' in html and '<details open>' in html


def test_history_template_only_shows_legal_actions_and_deep_links():
    from tests.test_phase7_5_operational_planner_routes import FakePlanner, _app
    fake = FakePlanner()
    fake.tasks_workspace = lambda **filters: {'available':True,'filters':{'status':'all','course_id':'','priority':''},'summary':{'open':1},'tasks':[
        {'id':'skipped-one','title':'Skipped work','status':'skipped','priority':'P1','estimated_minutes':None,'allowed_transitions':('backlog','planned','archived')},
        {'id':'done-one','title':'Finished work','status':'completed','priority':'P1','estimated_minutes':None,'allowed_transitions':('archived',)},
        {'id':'archived-one','title':'Past work','status':'archived','priority':'P1','estimated_minutes':None,'allowed_transitions':()},]}
    response = _app(fake).test_client().get('/planning/tasks?status=all')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Skipped work' in html and 'Completed' in html and 'Archived' in html
    assert '>Complete</button>' not in html
    assert 'id="task-skipped-one"' in html and '#task-skipped-one' in html


@pytest.mark.parametrize('day,expected',[('Monday','Monday'),('monday','Monday'),('2026-11-12','2026-11-12'),('none',None),('',None)])
def test_preferred_day_accepts_explicit_date_weekday_or_none(tmp_path,day,expected):
    service,_ = _service(tmp_path)
    assert service.create_task(title='Timing',preferred_day=day)['preferred_day'] == expected


def test_deleted_or_inactive_catalogue_records_cannot_be_captured(tmp_path):
    service,path = _service(tmp_path); _catalogue(path)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE topics SET deleted_at='now' WHERE id='t1'")
        c.execute("UPDATE courses SET status='archived' WHERE id='c2'")
    catalogue=service.tasks_workspace()['catalogue']
    assert [c['id'] for c in catalogue['courses']] == ['c1']
    assert not catalogue['topics']
    for refs in ({'course_id':'c1','topic_id':'t1'},{'course_id':'c2'}):
        with pytest.raises(OperationalTaskConflictError): service.create_task(title='Invalid',**refs)
