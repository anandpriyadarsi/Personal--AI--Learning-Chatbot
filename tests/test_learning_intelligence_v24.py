"""V2.4 owner identity and temporal qualification; disposable owners only."""
from contextlib import closing
import sqlite3
import pytest
from tests.test_academic_evidence_v23 import owners, service, NOW


def test_topic_reference_is_versioned_and_uses_canonical_ids(owners):
    from personal_learning_assistant.domain import academic_evidence as domain
    factory = getattr(domain, 'canonical_topic_reference', None)
    assert callable(factory), 'A stable cross-feature topic identity is required'
    one = factory('course-ma', 'topic-lu')
    assert one['schema'] == 'anvaya.topic-reference.v1'
    assert one['owner'] == 'academic_registry'
    assert one['course_id'] == 'course-ma' and one['topic_id'] == 'topic-lu'
    assert one == factory('course-ma', 'topic-lu')
    assert one['key'] != factory('other-course', 'topic-lu')['key']
    assert factory(None, 'topic-lu') is None
    assert service(owners).learning('synthetic', 1).to_dict()['topic_reference'] == one


def test_reversed_task_clocks_are_blocked(owners):
    from personal_learning_assistant.services.operational_task_service import OperationalTaskService
    from personal_learning_assistant.repositories.sqlite.planner_task_repository import SQLitePlannerTaskRepository
    tasks = OperationalTaskService(SQLitePlannerTaskRepository(owners[0]), now=lambda:NOW.isoformat())
    row = tasks.create_task(title='Study', course_id='course-ma', topic_id='topic-lu')
    with closing(sqlite3.connect(owners[0])) as con, con:
        con.execute("UPDATE planner_tasks SET created_at='2026-10-20T10:00:00Z', updated_at='2026-10-19T10:00:00Z' WHERE id=?", (row['id'],))
    record = next(r for r in service(owners).learning('synthetic',1).records if r.kind=='planner_task')
    assert record.qualification == 'blocked'
    assert 'timestamp_order_invalid' in record.reasons
    assert all(r.url is None for r in record.source_refs)


def test_revision_and_recall_remain_separate_ungraded_events(owners):
    studio=owners[1];p=owners[2];section=p['sections'][0]
    studio.record_progress('synthetic',1,{'event_id':'revision-view','section_id':section['id'],'view':'revision','budget':'5'})
    view=service(owners).learning('synthetic',1)
    rows=[r for r in view.records if r.kind=='learning_revision']
    assert len(rows)==1 and rows[0].evaluator=='self_report'
    assert rows[0].qualification=='revision_signal' and rows[0].actual_minutes is None
    assert rows[0].identifier=='learning_reading_event:revision-view'
    assert rows[0].independence=='unknown'
    assert 'time_budget_is_not_actual_effort' in rows[0].reasons


def test_invalid_revision_time_is_blocked_without_leaking_reflection_text(owners,monkeypatch):
    from personal_learning_assistant.learning_studio import service as owner
    monkeypatch.setattr(owner,'now',lambda:'2027-01-01T00:00:00Z')
    section=owners[2]['sections'][0]['id']
    owners[1].record_progress('synthetic',1,{'event_id':'future-review','section_id':section,'view':'revision'})
    view=service(owners).learning('synthetic',1)
    record=next(r for r in view.records if r.kind=='learning_revision')
    assert record.qualification=='blocked' and 'occurrence_after_as_of' in record.reasons
    assert all(r.url is None for r in record.source_refs)


def test_revision_does_not_guess_pages_from_selected_section(owners):
    section=owners[2]['sections'][0]['id']
    owners[1].record_progress('synthetic',1,{'event_id':'quick-revision','section_id':section,'view':'revision','budget':'5'})
    record=next(r for r in service(owners).learning('synthetic',1).records if r.kind=='learning_revision')
    assert 'rendered_revision_selection_not_recorded' in record.reasons
    assert all(r.page is None for r in record.source_refs)


def test_reversed_assessment_grading_clocks_are_blocked(owners):
    with closing(sqlite3.connect(owners[0])) as db,db:
        db.execute("UPDATE assessment_response_evaluations SET created_at='2026-10-20T10:00:00Z', updated_at='2026-10-19T10:00:00Z', confirmed_at='2026-10-18T10:00:00Z' WHERE id='ev-sq1'")
    record=next(r for r in service(owners).learning('synthetic',1).records if r.identifier=='assessment_response_evaluation:ev-sq1')
    assert record.qualification=='blocked' and 'timestamp_order_invalid' in record.reasons
    assert all(r.url is None for r in record.source_refs)
