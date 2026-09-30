import json
from pathlib import Path
from test_assessment_studio_phase_c import _database, _service, _app, Clock


def test_preflight_marking_groups_are_aggregate_and_spoiler_safe(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    view = _service(path, clock).preflight('assessment-1')
    assert sum(item['question_count'] for item in view['marking_groups']) == 4
    assert any(item['negative_marks'] == '0.25' for item in view['marking_groups'])
    encoded = json.dumps(view)
    for hidden in ('SECRET-', 'lower triangular', 'correct_option_ids', 'answer_json', 'rubric'):
        assert hidden not in encoded
    html = _app(path, clock).test_client().get('/assessments/tests/assessment-1').get_data(as_text=True)
    assert 'Marking scheme' in html
    assert 'Wrong answer penalty' in html


def test_action_json_returns_state_and_safe_destination_and_heartbeat_counts(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)
    sid = service.start('assessment-1', confirmed=True)['session_id']
    qid = service.runner_view(sid)['question']['session_question_id']
    client = _app(path, clock).test_client()
    response = client.post(f'/assessments/sessions/{sid}/questions/{qid}/action',json={
        'action':'save_next','current_ordinal':1,'next_ordinal':2,'response':{'selected_option_ids':['B']},'focus_seconds_delta':5})
    assert response.status_code == 200
    assert response.get_json()['state'] == 'answered'
    assert response.get_json()['redirect_url'].endswith('?q=2')
    counts = client.post(f'/assessments/sessions/{sid}/heartbeat',json={}).get_json()['palette_counts']
    assert counts['answered'] == 1
    assert counts['not_visited'] == 3
    cleared = client.post(f'/assessments/sessions/{sid}/questions/{qid}/action',json={'action':'clear','current_ordinal':1})
    assert cleared.get_json()['state'] == 'not_answered'
    clock.advance(61)
    expired = client.post(f'/assessments/sessions/{sid}/questions/{qid}/action',json={'action':'save_next','response':{'selected_option_ids':['B']}})
    assert expired.get_json()['status'] == 'expired'
    assert expired.get_json()['redirect_url'].endswith('/summary')
    assert 'SECRET-' not in json.dumps(expired.get_json())

def test_runner_mcq_guidance_scrollable_palette_and_full_width_toggle(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)
    sid = service.start('assessment-1', confirmed=True)['session_id']
    html = _app(path, clock).test_client().get(
        f'/assessments/sessions/{sid}?q=1'
    ).get_data(as_text=True)

    assert '<h3>MCQ</h3>' in html
    assert 'MCQ · Single correct answer' in html
    assert 'Select exactly one option.' in html
    assert 'id="assessment-palette-scroll"' in html
    assert 'id="assessment-palette-close"' in html
    assert 'id="assessment-palette-open"' in html
    assert 'Hide palette' in html
    assert 'Question palette' in html

    css = Path(
        'personal_learning_assistant/ui/web/static/css/app.css'
    ).read_text(encoding='utf-8')
    assert '.question-palette-scroll {' in css
    assert 'overflow-y: auto;' in css
    assert '.assessment-runner.is-palette-collapsed .exam-layout {' in css


def test_timeout_summary_explains_saved_response_boundary(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    service = _service(path, clock)
    sid = service.start('assessment-1', confirmed=True)['session_id']
    clock.advance(61)
    response = _app(path,clock).test_client().get(f'/assessments/sessions/{sid}/summary')
    assert response.status_code == 200
    assert 'last successfully saved' in response.get_data(as_text=True)
