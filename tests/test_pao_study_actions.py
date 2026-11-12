from personal_learning_assistant.services.study_action_service import suggest_actions


def test_actions_are_bounded_and_trace_exact_commitments():
    tasks = [dict(id='task '+str(i),title='Commitment',due_on='2026-10-01') for i in range(8)]
    result = suggest_actions(dict(date='2026-10-20',tasks=tasks),max_actions=20)
    assert len(result) == 3
    assert result[0]['source_refs'] == ['planner_task:task 0']
    assert result[0]['url'] == '/planning/tasks?status=all#task-task%200'


def test_stale_deleted_or_unreviewed_sources_cannot_suggest_creation():
    source = dict(module_id='exact-lesson',revision=4,title='Lesson',next_review_on='2026-10-10',mapping_status='confirmed',current=True,source_refs=['learning:exact-lesson:4'])
    for override in ({'current':False},{'mapping_status':'missing'},{'mapping_status':'unreviewed'}):
        assert suggest_actions(dict(date='2026-10-20',revision_queue=[{**source,**override}])) == []
    result = suggest_actions(dict(date='2026-10-20',revision_queue=[source]))
    assert result[0]['url'] == '/academic-evidence/learning/exact-lesson/4/study-preview'
    assert result[0]['source_refs'] == source['source_refs']

from tests.test_academic_evidence_v23 import owners
from tests.test_academic_evidence_v23_web import app, token, BASE
import sqlite3


def test_editable_exact_source_preview_reuses_intent_receipt(owners):
    client = app(owners).test_client()
    preview = client.get(BASE+'/study-preview?minutes=30')
    assert b'name="title"' in preview.data
    assert b'name="estimated_minutes"' in preview.data
    assert b'name="due_on"' in preview.data
    payload = dict(intent_token=token(preview),title='Recheck LU source',estimated_minutes='40',due_on='2026-12-02')
    assert client.post(BASE+'/study-intent',data=payload).status_code == 303
    assert client.post(BASE+'/study-intent',data=payload).status_code == 303
    with sqlite3.connect(owners[0]) as db:
        assert db.execute('SELECT title,estimated_minutes,due_on,course_id,topic_id FROM planner_tasks').fetchall() == [('Recheck LU source',40,'2026-12-02','course-ma','topic-lu')]
    assert client.post(BASE+'/study-intent',data={**payload,'due_on':'2026-12-03'}).status_code == 409
