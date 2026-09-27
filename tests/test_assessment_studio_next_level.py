from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_assessment_studio_phase_d import _database, _submitted_session, _evaluation


def _workspace(path, now=None):
    from personal_learning_assistant.services.assessment_workspace_service import AssessmentWorkspaceService
    return AssessmentWorkspaceService(path, now_fn=lambda: now or datetime(2026, 9, 27, tzinfo=timezone.utc))


def _app(path):
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    from personal_learning_assistant.services.assessment_package_service import AssessmentPackageService
    return create_app({
        'TESTING': True,
        'ASSESSMENT_WORKSPACE_SERVICE_FACTORY': lambda: _workspace(path),
        'ASSESSMENT_RUNNER_SERVICE_FACTORY': lambda: AssessmentRunnerService(path),
        'ASSESSMENT_PACKAGE_SERVICE_FACTORY': lambda: AssessmentPackageService(path),
    })


def test_lifecycle_projection_is_read_only_and_contains_no_question_material(tmp_path):
    path = _database(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = _workspace(path).library()
    assert result['total'] == 1
    row = result['rows'][0]
    assert row['state'] == 'ready'
    assert row['action_url'] == '/assessments/tests/assessment-d'
    assert row['max_marks'] == '24'
    assert row['question_count'] == 8
    text = json.dumps(result)
    for hidden in ('Correct MCQ', 'Wrong MCQ with negative', 'MCQ solution', 'correct_option_ids', 'rubric_text', 'options_json', 'answer_key'):
        assert hidden not in text
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    html = _app(path).test_client().get('/assessments/tests').get_data(as_text=True)
    assert 'Phase D Evaluation Test' in html
    assert 'Correct MCQ' not in html
    assert 'name="q"' in html
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_missing_database_is_not_created(tmp_path):
    from personal_learning_assistant.services.assessment_workspace_service import AssessmentWorkspaceUnavailableError
    path = tmp_path / 'absent.db'
    with pytest.raises(AssessmentWorkspaceUnavailableError):
        _workspace(path).library()
    assert not path.exists()


def test_latest_attempt_actions_and_expiry_are_honest_without_writes(tmp_path):
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    path = _database(tmp_path)
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    runner = AssessmentRunnerService(path, now_fn=lambda: now)
    session = runner.start('assessment-d', confirmed=True)['session_id']
    active = _workspace(path, now).library()['rows'][0]
    assert active['state'] == 'active'
    assert active['action_url'] == f'/assessments/sessions/{session}'
    before = path.read_bytes()
    expired = _workspace(path, now + timedelta(hours=2)).library()['rows'][0]
    assert expired['state'] == 'time_ended'
    assert 'Resume' not in expired['action_label']
    assert path.read_bytes() == before
    runner.submit(session)
    assert _workspace(path).library()['rows'][0]['state'] == 'needs_evaluation'
    _evaluation(path).create(session)
    assert _workspace(path).library()['rows'][0]['state'] == 'completed'
    assert _workspace(path).history('assessment-d')['rows'][0]['session_id'] == session


def test_incomplete_grading_gets_a_results_action(tmp_path):
    path = _database(tmp_path)
    session = _submitted_session(path)
    _evaluation(path).create(session)
    row = _workspace(path).library()['rows'][0]
    assert row['state'] == 'needs_grading'
    assert row['action_url'] == f'/assessments/sessions/{session}/evaluation'
    assert row['attempt_count'] == 1


def test_library_paginates_past_old_100_row_cap_and_search_is_literal(tmp_path):
    path = _database(tmp_path)
    with sqlite3.connect(path) as db:
        for index in range(105):
            aid = f'extra-{index:03}'
            title = 'Literal 50%_ quiz' if index == 104 else f'Library item {index:03}'
            db.execute("INSERT INTO assessments (id,course_id,assessment_type,title,status,max_points_milli,created_at,updated_at) VALUES (?, 'course-ma','quiz',?,'pending',1000,?,?)", (aid,title,'2026-09-27T00:00:00Z','2026-09-27T00:00:00Z'))
            db.execute("INSERT INTO assessment_runtime_specs (assessment_id,mode,duration_minutes,origin,created_at,updated_at) VALUES (?,'exam',30,'external_package',?,?)",(aid,'2026-09-27T00:00:00Z','2026-09-27T00:00:00Z'))
    service = _workspace(path)
    pages = [service.library(page=n) for n in range(1,7)]
    assert pages[0]['total'] == 106
    assert len({row['id'] for page in pages for row in page['rows']}) == 106
    assert len(pages[-1]['rows']) == 6
    literal = service.library(query='50%_')
    assert literal['total'] == 1
    assert service.library(query='LIBRARY ITEM 001')['total'] == 1
    assert service.library(course_id='unknown')['total'] == 0
    assert service.library(kind='exam')['total'] == 0
    assert service.library(page='not-a-number')['page'] == 1
    assert service.library(query='nothing')['rows'] == ()


def test_newest_package_revision_only_and_rejected_is_explicit(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import AssessmentPackageService
    path = _database(tmp_path)
    service = AssessmentPackageService(path)
    package = json.loads((Path(__file__).resolve().parents[1] / 'examples/anvaya_assessment_package_v1.example.json').read_text())
    one = service.stage_upload('one.json', json.dumps(package).encode())
    package['package_revision'] += 1
    two = service.stage_upload('two.json', json.dumps(package).encode())
    view = _workspace(path).library(state='preparation')
    assert [x['id'] for x in view['rows']] == [two['id']]
    assert view['rows'][0]['package_revision'] == 2
    assert _app(path).test_client().get(view['rows'][0]['action_url']).status_code == 200
    service.reject(two['id'])
    assert _workspace(path).library(state='preparation')['total'] == 0
    assert _workspace(path).library(state='rejected')['rows'][0]['id'] == two['id']
    assert service.review(one['id'])['status'] == 'review'


def test_history_pagination_and_home_continuation(tmp_path):
    path = _database(tmp_path)
    session = _submitted_session(path)
    client = _app(path).test_client()
    page = client.get('/assessments')
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert 'Continue where you left off' in text
    assert f'/assessments/sessions/{session}/summary' in text
    history = client.get('/assessments/tests/assessment-d/history')
    assert history.status_code == 200
    assert 'Attempt history' in history.get_data(as_text=True)
    assert client.get('/assessments/tests/missing/history').status_code == 404


def test_blind_review_lifecycle_and_context_actions(tmp_path):
    from test_assessment_studio_blind_review import _database as blind_db, _package, _service, _raw
    path = blind_db(tmp_path)
    service = _service(path)
    staged = service.stage_upload('ready.json', _raw(_package()))
    client = _app(path).test_client()
    page = client.get(f'/assessments/import/{staged["id"]}/review').get_data(as_text=True)
    assert 'data-preflight-state="ready"' in page
    assert 'data-confirm-reject' in page
    approved = service.approve(staged['id'])
    page = client.get(f'/assessments/import/{staged["id"]}/review').get_data(as_text=True)
    assert 'data-preflight-state="approved"' in page
    assert f'/assessments/tests/{approved}' in page
    package = _package(); package['package_id'] = 'rejected-test'
    rejected = service.stage_upload('rejected.json', _raw(package)); service.reject(rejected['id'])
    page = client.get(f'/assessments/import/{rejected["id"]}/review').get_data(as_text=True)
    assert 'data-preflight-state="rejected"' in page
    assert 'Approve &amp; add to tests' not in page
    assert 'Needs Alex review' not in page


def test_authoring_dialog_names_and_manual_blind_prompt_fallback(tmp_path):
    from test_assessment_studio_blind_review import _database as blind_db, _package, _service, _raw
    path = blind_db(tmp_path)
    client = _app(path).test_client()
    page = client.get('/assessments/import?kind=quiz').get_data(as_text=True)
    assert 'aria-labelledby="assessment-subject-title"' in page
    assert '<noscript>' in page
    package = _package(); package['questions'][0]['review_required'] = True
    staged = _service(path).stage_upload('review.json', _raw(package))
    page = client.get(f'/assessments/import/{staged["id"]}/review').get_data(as_text=True)
    assert '<label for="assessment-alex-review-prompt">' in page
    assert 'readonly' in page
    assert package['questions'][0]['text'] not in page
