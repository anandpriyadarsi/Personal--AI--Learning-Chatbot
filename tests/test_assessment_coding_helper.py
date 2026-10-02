"""Coding help must stay outside assessment evidence and hidden marking data."""
import json
import sqlite3

import pytest

from test_assessment_studio_phase_c import Clock, _app, _database, _service
from personal_learning_assistant.domain.tutor_models import TutorProviderResponse


class Provider:
    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return TutorProviderResponse("Think about what each row represents. Now try it yourself.", "test", "test")


def setup(tmp_path, mode="practice", **settings):
    path = _database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE assessment_runtime_specs SET mode=?", (mode,))
    clock = Clock()
    service = _service(path, clock)
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    qid = service.runner_view(sid)["question"]["session_question_id"]
    app = _app(path, clock)
    provider = Provider()
    app.config.update(CODING_HELPER_PROVIDER_FACTORY=lambda: provider, **settings)
    return app.test_client(), service, provider, path, clock, sid, qid


def endpoint(sid, qid):
    return f"/assessments/sessions/{sid}/questions/{qid}/coding-helper"


def dump(path):
    with sqlite3.connect(path) as db:
        return "\n".join(db.iterdump())


def test_colab_and_drawer_are_available_for_practice(tmp_path):
    client, _, _, _, _, sid, _ = setup(tmp_path)
    html = client.get(f"/assessments/sessions/{sid}").get_data(as_text=True)
    assert 'href="https://colab.research.google.com/"' in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert 'id="coding-helper-dialog"' in html
    assert "Operations Map" in html


@pytest.mark.parametrize("destination,expected", [
    ("https://colab.research.google.com/drive/example", "https://colab.research.google.com/drive/example"),
    ("javascript:alert(1)", "https://colab.research.google.com/"),
    ("https://evil.example/", "https://colab.research.google.com/"),
    ("https://colab.research.google.com@evil.example/", "https://colab.research.google.com/"),
])
def test_colab_url_is_validated(tmp_path, destination, expected):
    client, _, _, _, _, sid, _ = setup(tmp_path, ASSESSMENT_COLAB_URL=destination)
    html = client.get(f"/assessments/sessions/{sid}").get_data(as_text=True)
    assert f'href="{expected}"' in html


@pytest.mark.parametrize("action", ["hint", "concept", "operation", "explain_code", "debug", "memory", "pseudocode", "rebuild"])
def test_helper_modes_use_safe_context_and_never_write(tmp_path, action):
    client, service, provider, path, _, sid, qid = setup(tmp_path)
    before = dump(path)
    response = client.post(endpoint(sid, qid), json={
        "action": action, "topic": "Pandas filtering", "message": "What should I try?",
        "code": "print([1, 2])", "error": "unexpected shape", "include_question": True,
        "answer_json": "INJECTED-KEY", "solution": "INJECTED-SOLUTION",
    })
    assert response.status_code == 200
    assert response.get_json()["reply"].startswith("Think about")
    assert dump(path) == before
    request = provider.requests[0]
    encoded = json.dumps([*request.messages, request.metadata])
    for hidden in ("SECRET-", "INJECTED-", "correct_option_ids", "answer_json", "rubric_text", "expected_method"):
        assert hidden not in encoded
    data = json.loads(request.messages[-1]["content"])
    assert data["visible_context"]["question_text"] == "Which factor in A=LU is lower triangular?"
    assert data["code"] == "print([1, 2])"
    assert data["action"] == action


def test_question_context_is_opt_in_and_stage_and_full_solution_are_explicit(tmp_path):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    response = client.post(endpoint(sid, qid), json={"action":"hint", "topic":"loops", "hint_level":2})
    assert response.status_code == 200
    data = json.loads(provider.requests[-1].messages[-1]["content"])
    assert "question_text" not in data["visible_context"]
    assert data["hint_level"] == 2
    assert data["full_solution"] is False
    response = client.post(endpoint(sid, qid), json={"action":"pseudocode", "topic":"loops", "full_solution":True})
    assert response.status_code == 200
    assert json.loads(provider.requests[-1].messages[-1]["content"])["full_solution"] is True


def test_exam_helper_disabled_in_ui_and_server(tmp_path):
    client, _, provider, path, _, sid, qid = setup(tmp_path, mode="exam")
    html = client.get(f"/assessments/sessions/{sid}").get_data(as_text=True)
    assert 'id="coding-helper-dialog"' not in html
    before = dump(path)
    assert client.post(endpoint(sid, qid), json={"action":"hint", "mode":"practice"}).status_code == 403
    assert not provider.requests
    assert dump(path) == before


def test_restricted_exam_allows_only_generic_concepts_without_question_context(tmp_path):
    client, _, provider, _, _, sid, qid = setup(tmp_path, mode="exam", ASSESSMENT_CODING_HELPER_EXAM_POLICY="concepts")
    assert client.post(endpoint(sid, qid), json={"action":"debug","code":"x=1"}).status_code == 403
    assert client.post(endpoint(sid, qid), json={"action":"concept","topic":"loops", "include_question":True}).status_code == 403
    assert client.post(endpoint(sid, qid), json={"action":"concept","topic":"loops","full_solution":True}).status_code == 403
    result = client.post(endpoint(sid, qid), json={"action":"concept","topic":"loops"})
    assert result.status_code == 200
    data = json.loads(provider.requests[-1].messages[-1]["content"])
    assert data["visible_context"] == {}
    assert data["topic"] == "Python loops"
    assert "general concepts only" in provider.requests[-1].messages[0]["content"]
    html = client.get(f"/assessments/sessions/{sid}").get_data(as_text=True)
    assert '<select name="topic"' in html


@pytest.mark.parametrize("topic", ["What does np.array([1,2,3])[1] return?", "Solve my exam task", ""])
def test_restricted_exam_rejects_arbitrary_topic_text(tmp_path, topic):
    client, _, provider, path, _, sid, qid = setup(tmp_path, mode="exam", ASSESSMENT_CODING_HELPER_EXAM_POLICY="concepts")
    before = dump(path)
    result = client.post(endpoint(sid, qid), json={"action":"concept", "topic":topic})
    assert result.status_code == 403
    assert not provider.requests
    assert dump(path) == before


def test_disabled_config_and_invalid_exam_policy_fail_closed(tmp_path):
    client, _, provider, _, _, sid, qid = setup(tmp_path, ASSESSMENT_CODING_HELPER_ENABLED=False)
    assert client.post(endpoint(sid,qid),json={"action":"hint"}).status_code == 403
    assert not provider.requests


@pytest.mark.parametrize("payload", [[], {"action":"unknown"}, {"action":"hint","code":"x"*12001}, {"action":"hint","hint_level":99}, {"action":"hint","full_solution":"false"}])
def test_invalid_input_does_not_call_provider(tmp_path, payload):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    assert client.post(endpoint(sid,qid), json=payload).status_code == 400
    assert not provider.requests


def test_helper_rejects_foreign_question_and_expiry_without_mutating_session(tmp_path):
    client, _, provider, path, clock, sid, qid = setup(tmp_path)
    assert client.post(endpoint(sid,"missing"),json={"action":"hint"}).status_code == 404
    clock.advance(61)
    before = dump(path)
    assert client.post(endpoint(sid,qid),json={"action":"hint"}).status_code == 409
    assert dump(path) == before
    assert not provider.requests


def test_provider_failure_is_safe_and_map_remains_available(tmp_path):
    client, _, provider, path, _, sid, qid = setup(tmp_path)
    def fail(_request):
        raise RuntimeError("SECRET-KEY-and-provider-details")
    provider.complete = fail
    before = dump(path)
    result = client.post(endpoint(sid,qid),json={"action":"concept","topic":"lists"})
    assert result.status_code == 503
    assert "SECRET" not in result.get_data(as_text=True)
    assert "Operations Map" in result.get_json()["error"]
    assert dump(path) == before


def test_operations_map_covers_requested_categories_and_complete_cards():
    from personal_learning_assistant.services.coding_operations import OPERATION_CARDS
    assert {c["category"] for c in OPERATION_CARDS} == {"Python","NumPy","Pandas","Data cleaning","Visualization"}
    assert len(OPERATION_CARDS) >= 65
    assert len({c["id"] for c in OPERATION_CARDS}) == len(OPERATION_CARDS)
    for card in OPERATION_CARDS:
        for key in ("what","why","syntax","input","example","output","mistake"):
            assert isinstance(card[key],str) and card[key].strip()
        compile(card["example"], card["what"], "exec")


def test_repeated_answer_action_is_idempotent_for_evidence_and_session_scoped(tmp_path):
    client, service, _, path, _, sid, qid = setup(tmp_path)
    action_url = f"/assessments/sessions/{sid}/questions/{qid}/action"
    payload = {"action":"save_next","response":{"selected_option_ids":["B"]},"next_ordinal":2}
    assert client.post(action_url,json=payload).status_code == 200
    assert client.post(action_url,json=payload).status_code == 200
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM assessment_test_events WHERE session_id=? AND event_type='response_saved'",(sid,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM assessment_test_responses WHERE session_question_id=?",(qid,)).fetchone()[0] == 1
    assert client.post(action_url.replace(sid,"unrelated-attempt"),json=payload).status_code == 404
    assert service.runner_view(sid)["question"]["response"] == {"selected_option_ids":["B"]}


@pytest.mark.parametrize("exam", [False, True])
def test_windows_acceptance_fixture_is_disposable_and_route_scoped(tmp_path, monkeypatch, exam):
    from scripts.assessment_live_acceptance import build_fixture
    monkeypatch.delenv("ANVAYA_CODING_HELPER_EXAM_POLICY", raising=False)
    monkeypatch.delenv("ANVAYA_CODING_HELPER_ENABLED", raising=False)
    app, sid, path = build_fixture(tmp_path, exam=exam)
    assert path.parent == tmp_path
    client = app.test_client()
    for route in ("/", "/agent", "/assessments", "/assessments/sessions/unrelated-attempt"):
        assert client.get(route).status_code == 404
    response = client.get(f"/assessments/sessions/{sid}")
    assert response.status_code == 200
    assert ('id="coding-helper-dialog"' in response.get_data(as_text=True)) is not exam
    with sqlite3.connect(path) as db:
        qid = db.execute("SELECT id FROM assessment_test_session_questions WHERE session_id=? AND ordinal=1", (sid,)).fetchone()[0]
    before = dump(path)
    result = client.post(endpoint(sid, qid), json={"action":"concept", "topic":"Pandas filtering"})
    if exam:
        assert result.status_code == 403
    else:
        assert result.status_code == 200
        assert "DEMO RESPONSE" in result.get_json()["reply"]
    assert dump(path) == before
