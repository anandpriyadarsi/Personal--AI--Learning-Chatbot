import json
import re
import sqlite3

import pytest

from test_assessment_studio_phase_d import _database, _submitted_session, _evaluation, _app, _runner, NOW


def _evaluated(tmp_path):
    path = _database(tmp_path)
    sid = _submitted_session(path)
    service = _evaluation(path)
    service.create(sid)
    return path, sid, service, {q['question_number']: q for q in service.results(sid)['questions']}


def test_rendered_grading_form_submits_to_actual_response_and_preserves_review_context(tmp_path):
    path, sid, service, questions = _evaluated(tmp_path)
    eid = questions['7']['evaluation_id']
    client = _app(path).test_client()
    page = client.get(f'/assessments/evaluations/{eid}/review').get_data(as_text=True)
    action = re.search(r'<form method="post" action="([^"]+/review)"', page).group(1)
    assert action == f'/assessments/evaluations/{eid}/review'
    result = client.post(action, data={'evaluator_type':'teacher','awarded_marks':'5','confirm_final':'1'})
    assert result.status_code == 303
    assert f'question={eid}' in result.headers['Location']
    assert service.response_editor(eid)['status'] == 'confirmed'


def test_pending_cannot_be_classified_and_repository_rechecks_the_boundary(tmp_path):
    from personal_learning_assistant.services.assessment_evaluation_service import AssessmentEvaluationValidationError
    from personal_learning_assistant.repositories.sqlite.assessment_evaluation_repository import SQLiteAssessmentEvaluationRepository, AssessmentEvaluationRepositoryConflictError
    path, sid, service, questions = _evaluated(tmp_path)
    eid = questions['7']['evaluation_id']
    with pytest.raises(AssessmentEvaluationValidationError, match='Grade'):
        service.classify_mistake(eid, {'category':'concept_gap','source_type':'user'})
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        with pytest.raises(AssessmentEvaluationRepositoryConflictError, match='graded'):
            SQLiteAssessmentEvaluationRepository(db).add_mistake(eid,mistake_id='blocked',category='concept_gap',note='',source_type='user',status='confirmed',now=NOW)
        assert db.execute('SELECT COUNT(*) FROM assessment_evaluation_mistakes').fetchone()[0] == 0


def test_historical_pending_classification_cannot_create_mistake_evidence_for_correct_grade(tmp_path):
    path, sid, service, questions = _evaluated(tmp_path)
    eid = questions['7']['evaluation_id']
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO assessment_evaluation_mistakes (id,response_evaluation_id,category,note,source_type,status,created_at,confirmed_at) VALUES ('historic',?,'concept_gap','','user','confirmed',?,?)",(eid,NOW,NOW))
    service.save_manual_evaluation(eid,{'evaluator_type':'teacher','awarded_marks':'5','confirm_final':True})
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM mistake_events').fetchone()[0] == 0
        assert db.execute("SELECT mistake_event_id FROM assessment_evaluation_mistakes WHERE id='historic'").fetchone() == (None,)


def test_revised_correct_provisional_grade_cannot_confirm_a_mistake(tmp_path):
    from personal_learning_assistant.services.assessment_evaluation_service import AssessmentEvaluationConflictError
    path, sid, service, questions = _evaluated(tmp_path)
    eid = questions['7']['evaluation_id']
    service.save_manual_evaluation(eid,{'evaluator_type':'alex_ai','awarded_marks':'2'})
    item = service.classify_mistake(eid,{'category':'concept_gap','source_type':'alex_ai'})
    mid = item['mistakes'][0]['id']
    service.save_manual_evaluation(eid,{'evaluator_type':'teacher','awarded_marks':'5','confirm_final':True})
    with pytest.raises(AssessmentEvaluationConflictError):
        service.confirm_mistake(mid)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM mistake_events').fetchone()[0] == 0
        assert db.execute('SELECT status FROM assessment_evaluation_mistakes WHERE id=?',(mid,)).fetchone()[0] == 'provisional'


def test_focused_review_filters_snapshot_options_and_keeps_other_questions_out_of_html(tmp_path):
    path, sid, service, questions = _evaluated(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE question_options SET option_text='MUTATED LIVE OPTION' WHERE question_id='q2'")
    result = service.results(sid, outcome='incorrect', question=questions['2']['evaluation_id'])
    assert len(result['review_questions']) == 1
    assert result['selected_question']['selected_options'] == ('A · Wrong',)
    assert result['selected_question']['correct_options'] == ('B · Correct',)
    assert result['negative_marks_total'] == '1'
    assert result['course_id'] == 'course-ma'
    assert service.results(sid,outcome='bad',question='missing')['selected_question']['ordinal'] == 1
    client = _app(path).test_client()
    html = client.get(f'/assessments/sessions/{sid}/evaluation?outcome=incorrect').get_data(as_text=True)
    assert html.count('data-review-question=') == 1
    assert 'A · Wrong' in html and 'B · Correct' in html
    assert 'MUTATED LIVE OPTION' not in html
    assert 'Explain LU factorization.' not in html
    assert 'course_id=course-ma' in html
    pending = client.get(f'/assessments/sessions/{sid}/evaluation?outcome=needs_grading').get_data(as_text=True)
    assert f'/evaluations/{questions["7"]["evaluation_id"]}/mistakes' not in pending
    assert 'Grade response' in pending
    empty = client.get(f'/assessments/sessions/{sid}/evaluation?outcome=unanswered').get_data(as_text=True)
    assert 'No questions match this filter' in empty


def test_active_session_results_remain_unavailable(tmp_path):
    path = _database(tmp_path)
    sid = _runner(path).start('assessment-d',confirmed=True)['session_id']
    response = _app(path).test_client().get(f'/assessments/sessions/{sid}/evaluation')
    assert response.status_code in (404,409)
    assert 'MCQ solution' not in response.get_data(as_text=True)


def test_course_recovery_scope_and_post_redirect_context(tmp_path):
    from test_assessment_studio_phase_f import _database as recovery_db, _service, _app as recovery_app
    path = recovery_db(tmp_path)
    service = _service(path)
    before = path.read_bytes()
    visible = service.workspace(course_id='course-ma')
    assert len(visible['candidates']) == 2
    assert visible['selected_course_id'] == 'course-ma'
    assert service.workspace(course_id='missing')['candidates'] == ()
    assert path.read_bytes() == before
    client = recovery_app(path).test_client()
    html = client.get('/assessments/adaptive?course_id=course-ma').get_data(as_text=True)
    assert 'name="course_id" value="course-ma"' in html
    assert 'Create a retest with Alex' in html
    generated = client.post('/assessments/adaptive/generate',data={'course_id':'course-ma','evidence_fingerprint':visible['candidates'][0]['evidence_fingerprint']})
    assert generated.status_code == 303 and 'course_id=course-ma' in generated.headers['Location']
    assert service.workspace(course_id='missing')['saved'] == ()
    item = service.workspace(course_id='course-ma')['pending'][0]
    applied = client.post(f'/assessments/adaptive/{item["id"]}/apply',data={'course_id':'course-ma','revision':item['revision'],'title':'Recovery','priority':'P1','estimated_minutes':'30'})
    assert applied.status_code == 303 and 'course_id=course-ma' in applied.headers['Location']

def test_course_filter_precedes_recommendation_limit_and_generation_uses_same_scope(tmp_path):
    from test_assessment_studio_phase_f import _database as recovery_db, _service
    path = recovery_db(tmp_path)
    service = _service(path)
    report = service.intelligence.weak_topics()
    topic = report['topics'][0]
    distractors = tuple({**topic,'course_id':f'other-{i}','topic_id':f'other-topic-{i}'} for i in range(12))
    class Evidence:
        def weak_topics(self):
            return {**report,'topics':(*distractors, *report['topics'])}
    service.intelligence = Evidence()
    scoped = service.workspace(course_id='course-ma')
    assert len(scoped['candidates']) == 2
    service.generate([scoped['candidates'][0]['evidence_fingerprint']], course_id='course-ma')
    assert len(service.workspace(course_id='course-ma')['pending']) == 1


def test_results_and_editor_reject_an_active_session_even_with_existing_evaluation(tmp_path):
    path, sid, service, questions = _evaluated(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE assessment_test_sessions SET status='active' WHERE id=?", (sid,))
    client = _app(path).test_client()
    for url in (f'/assessments/sessions/{sid}/evaluation',f'/assessments/evaluations/{questions["1"]["evaluation_id"]}/review'):
        response = client.get(url)
        assert response.status_code == 409
        assert 'MCQ solution' not in response.get_data(as_text=True)

def test_corrected_grade_excludes_old_confirmed_labels_from_analytics_and_recovery(tmp_path):
    from personal_learning_assistant.services.assessment_intelligence_service import AssessmentIntelligenceService
    path, sid, service, questions = _evaluated(tmp_path)
    eid = questions['7']['evaluation_id']
    service.save_manual_evaluation(eid,{'evaluator_type':'teacher','awarded_marks':'2'})
    service.classify_mistake(eid,{'category':'concept_gap','source_type':'user'})
    service.save_manual_evaluation(eid,{'evaluator_type':'teacher','awarded_marks':'5','confirm_final':True})
    intelligence = AssessmentIntelligenceService(path)
    assert intelligence.overview()['mistake_patterns'] == ()
    assert all(topic['mistake_count'] == 0 for topic in intelligence.weak_topics()['topics'])
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM assessment_evaluation_mistakes').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM mistake_events').fetchone()[0] == 0
