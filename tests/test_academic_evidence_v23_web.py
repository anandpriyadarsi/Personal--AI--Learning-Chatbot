"""Read-only HTTP boundaries and guarded explicit study intent."""
from contextlib import closing
import hashlib
import re
import sqlite3
import pytest
from tests.test_academic_evidence_v23 import owners, NOW, event, inventory, service

def app(owners, **extra):
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
    return create_app({'TESTING':True,'ACADEMIC_EVIDENCE_ENABLED':True,
        'ACADEMIC_EVIDENCE_SERVICE_FACTORY':lambda:service(owners),
        'LEARNING_STUDIO_SERVICE_FACTORY':lambda:owners[1],
        'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY':lambda:build_operational_planner_web_service(owners[0]),
        'PLANNING_LOCAL_TIMEZONE':'UTC','ACADEMIC_TIMEZONE':'UTC','PLANNING_NOW':lambda:NOW.isoformat(),**extra})

def token(response, name='intent_token'):
    match=re.search(r'name="'+name+r'"\s+value="([^"]+)"',response.get_data(as_text=True))
    assert match is not None,response.get_data(as_text=True)
    return match.group(1)

BASE='/academic-evidence/learning/synthetic/1'

def test_index_lesson_json_and_safe_pdf_are_read_only(owners,tmp_path):
    c=app(owners).test_client();before=inventory(tmp_path)
    assert c.get('/academic-evidence').status_code==200
    r=c.get(BASE);assert r.status_code==200 and b'Independent mastery' in r.data
    j=c.get(BASE+'?format=json');assert j.status_code==200 and j.json['mastery']=='unknown'
    pdf=c.get(BASE+'/source.pdf');assert pdf.status_code==200
    assert hashlib.sha256(pdf.data).hexdigest()==owners[2]['source']['sha256']
    assert r.headers['Cache-Control']=='no-store' and inventory(tmp_path)==before

def test_feature_disabled_never_constructs_service(owners):
    def forbidden():raise AssertionError('Disabled feature read an owner')
    c=app(owners,ACADEMIC_EVIDENCE_ENABLED=False,ACADEMIC_EVIDENCE_SERVICE_FACTORY=forbidden).test_client()
    assert c.get('/academic-evidence').status_code==404

@pytest.mark.parametrize('query',['format=unsupported','format=json&format=json','forged=1'])
def test_unsupported_or_repeated_query_is_rejected(owners,query):
    assert app(owners).test_client().get(BASE+'?'+query).status_code==400

def test_explicit_preview_is_not_a_write_and_confirmed_retry_is_one_task(owners,tmp_path):
    c=app(owners).test_client();before=inventory(tmp_path)
    r=c.get(BASE+'/study-preview?minutes=30');assert r.status_code==200
    t=token(r);assert inventory(tmp_path)==before
    one=c.post(BASE+'/study-intent',data={'intent_token':t});two=c.post(BASE+'/study-intent',data={'intent_token':t})
    assert one.status_code==two.status_code==303
    with closing(sqlite3.connect(owners[0])) as db:
        rows=db.execute('SELECT * FROM planner_tasks').fetchall()
        assert len(rows)==1
        assert db.execute('SELECT course_id,topic_id,status FROM planner_tasks').fetchone()==('course-ma','topic-lu','backlog')
    assert c.get(BASE+'?format=json').json['mastery']=='unknown'

def test_new_practice_between_preview_and_action_conflicts(owners):
    c=app(owners).test_client();t=token(c.get(BASE+'/study-preview?minutes=30'));event(owners)
    assert c.post(BASE+'/study-intent',data={'intent_token':t}).status_code==409
    with closing(sqlite3.connect(owners[0])) as db:assert db.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==0

def test_mapping_change_between_preview_and_action_conflicts(owners):
    c=app(owners).test_client();t=token(c.get(BASE+'/study-preview?minutes=30'))
    with closing(sqlite3.connect(owners[0])) as db,db:db.execute("UPDATE topics SET name='Changed' WHERE id='topic-lu'")
    assert c.post(BASE+'/study-intent',data={'intent_token':t}).status_code==409

def test_cross_site_forged_and_restart_tokens_do_not_create_tasks(owners):
    a=app(owners);c=a.test_client();t=token(c.get(BASE+'/study-preview?minutes=30'))
    assert c.post(BASE+'/study-intent',data={'intent_token':t},headers={'Origin':'https://untrusted.invalid'}).status_code==403
    assert c.post(BASE+'/study-intent',data={'intent_token':t+'bad'}).status_code==400
    assert app(owners).test_client().post(BASE+'/study-intent',data={'intent_token':t}).status_code==400
    with closing(sqlite3.connect(owners[0])) as db:assert db.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0]==0

def test_tutor_handoff_is_read_only_offline_and_no_answer_keys(owners,tmp_path):
    c=app(owners).test_client();t=token(c.get(BASE),'review_token');before=inventory(tmp_path)
    r=c.post(BASE+'/tutor-handoff',data={'review_token':t,'student_question':'Help me explain this source.','page':'1'})
    assert r.status_code==200 and r.json['schema']=='anvaya.learning-tutor-handoff.v1'
    assert r.json['independence']=='unknown' and r.json['automatic_tutor_consumption'] is False
    assert len(r.json['help_steps'])==4 and inventory(tmp_path)==before
    assert 'correct_index' not in str(r.json) and 'answer_key' not in str(r.json)
