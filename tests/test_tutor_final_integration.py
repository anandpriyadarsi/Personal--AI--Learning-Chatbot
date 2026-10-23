"""Current-head regressions using disposable Tutor state only."""
import pytest
from tests.test_tutor21_correctness import _env

from personal_learning_assistant.tutor.adaptive_state import (
    evolve_adaptive_state, extract_answer_evaluation,
)


@pytest.mark.parametrize("reply", [
    "LU factorization separates a matrix into lower and upper triangular parts.",
    "Here is how to compute the factors.\n\nThe multiplier is stored in L.",
    "I cannot provide a practice problem from the available sources.",
    "Compute the determinant. The determinant is 4.",
])
def test_explanation_is_not_a_pending_practice_task(reply):
    state = evolve_adaptive_state({}, student_message="Give me computational practice.",
        assistant_message=reply, teaching_intent="practice", teaching_move="practice")
    assert state["pending_question"] == ""
    assert not state["awaiting_student_answer"]
    assert not state["practice_active"]


@pytest.mark.parametrize("reply", [
    "Compute the determinant of [[1,2],[3,4]].",
    "Find the multiplier that eliminates 6 below a pivot of 2.",
    "What multiplier eliminates 6 below a pivot of 2?",
    "Find x if the determinant is 4 for [[x,1],[2,3]].",
])
def test_explicit_practice_tasks_remain_pending(reply):
    state = evolve_adaptive_state({}, student_message="Give me computational practice.",
        assistant_message=reply, teaching_intent="practice", teaching_move="practice")
    assert state["pending_question"] == reply
    assert state["awaiting_student_answer"]


def test_previous_solution_does_not_consume_next_unsolved_task():
    state = evolve_adaptive_state({}, student_message='Give practice.',
        assistant_message='The previous answer is 3.\n\nCompute the determinant of [[1,2],[3,4]].',
        teaching_intent='practice', teaching_move='practice')
    assert state['pending_question'] == 'Compute the determinant of [[1,2],[3,4]].'


@pytest.mark.parametrize("marker", [
    '<!--ANVAYA_EVAL broken -->',
    '<!--ANVAYA_EVAL {"status":"correct" -->',
    '<!--ANVAYA_EVAL ["correct"] -->',
])
def test_malformed_private_evaluation_is_removed_without_inventing_correctness(marker):
    visible, evaluation = extract_answer_evaluation(marker + "\nTry the pivot again.")
    assert visible == "Try the pivot again."
    assert evaluation["status"] == "unclear"
    assert evaluation["present"] is False


@pytest.mark.parametrize("failure_point", ["add_assistant_turn", "update_session_metadata"])
def test_exchange_rolls_back_both_turns_when_persistence_fails(tmp_path, monkeypatch, failure_point):
    connection, repo, sessions, session, provider, engine = _env(tmp_path, ["A clear explanation."])
    before = repo.get_session(session.session_id).metadata
    def fail(*args, **kwargs):
        raise RuntimeError("injected storage failure")
    monkeypatch.setattr(sessions, failure_point, fail)
    with pytest.raises(RuntimeError, match="injected storage failure"):
        engine.answer(session.session_id, "Explain span.")
    assert repo.list_turns(session.session_id) == ()
    assert repo.get_session(session.session_id).metadata == before
    assert not connection.in_transaction
    connection.close()


def test_duplicate_feedback_replay_is_idempotent(tmp_path):
    connection, repo, sessions, session, provider, engine = _env(tmp_path, ["A clear explanation."])
    answer = engine.answer(session.session_id, "Explain span.")
    first = sessions.record_feedback(answer.assistant_turn.turn_id, helpful=True)
    second = sessions.record_feedback(answer.assistant_turn.turn_id, helpful=True)
    assert first.feedback_id == second.feedback_id
    assert connection.execute("SELECT COUNT(*) FROM tutor_feedback").fetchone()[0] == 1
    sessions.record_feedback(answer.assistant_turn.turn_id, helpful=False)
    sessions.record_feedback(answer.assistant_turn.turn_id, helpful=True)
    assert connection.execute("SELECT COUNT(*) FROM tutor_feedback").fetchone()[0] == 1
    assert connection.execute("SELECT helpful FROM tutor_feedback").fetchone()[0] == 1
    connection.close()


def test_local_math_preserves_latex_and_markdown_without_executable_html():
    from personal_learning_assistant.ui.web.tutor_rendering import render_tutor_markdown
    result = str(render_tutor_markdown(
        r"**Factors** \(L=\begin{bmatrix}1&0\\3&1\end{bmatrix}\) "
        + "\n\n`x_1`\n\n" + r"$x_1^2$ <img src=x onerror=alert(1)>"))
    assert 'data-assessment-math' in result
    assert r'\begin{bmatrix}' in result
    assert '<strong>Factors</strong>' in result
    assert '<code>x_1</code>' in result
    assert '<img ' not in result


def test_concurrent_session_change_rejects_stale_answer_without_partial_turns(tmp_path):
    import sqlite3
    connection, repo, sessions, session, provider, engine = _env(tmp_path, [])
    from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
    def competing_answer(request):
        assert not connection.in_transaction  # Never hold a DB lock across generation.
        second = sqlite3.connect(tmp_path / 'tutor21_correctness.db', isolation_level=None)
        second.execute('UPDATE tutor_sessions SET metadata_json=? WHERE id=?',
                       ('{"concurrent":"preserved"}', session.session_id))
        second.close()
        return TutorProviderResponse(content='A stale answer.', provider_name='fake', provider_model='fake')
    provider.complete = competing_answer
    with pytest.raises(Exception, match='session changed'):
        engine.answer(session.session_id, 'Explain span.')
    assert repo.list_turns(session.session_id) == ()
    assert repo.get_session(session.session_id).metadata == {"concurrent": "preserved"}
    assert not connection.in_transaction
    connection.close()


def test_browser_request_replay_reuses_persisted_answer_without_provider(tmp_path):
    connection, repo, sessions, session, provider, engine = _env(tmp_path, ['A clear explanation.'])
    request_id = 'synthetic-request-12345'
    first = engine.answer(session.session_id, 'Explain span.', request_id=request_id)
    replay = engine.answer(session.session_id, 'Explain span.', request_id=request_id)
    assert replay.assistant_turn.turn_id == first.assistant_turn.turn_id
    assert len(provider.requests) == 1
    assert len(repo.list_turns(session.session_id)) == 2
    with pytest.raises(Exception, match='different question'):
        engine.answer(session.session_id, 'Explain basis.', request_id=request_id)
    assert len(provider.requests) == 1
    connection.close()


def test_receipt_eviction_uses_turn_order_after_sorted_json_roundtrip(tmp_path):
    connection, repo, sessions, session, provider, engine = _env(tmp_path, ['A clear explanation.'] * 34)
    for number in range(32):
        engine.answer(session.session_id, 'Explain span.', request_id=f'z-request-{number:08d}')
    latest = engine.answer(session.session_id, 'Explain span.', request_id='a-request-00000000')
    engine.answer(session.session_id, 'Explain span.', request_id='z-request-00000032')
    replay = engine.answer(session.session_id, 'Explain span.', request_id='a-request-00000000')
    assert replay.assistant_turn.turn_id == latest.assistant_turn.turn_id
    assert len(provider.requests) == 34
    assert len(repo.get_session(session.session_id).metadata['tutor_request_receipts']) == 32
    connection.close()


def test_web_adapter_translates_storage_conflict_to_recoverable_error(tmp_path, monkeypatch):
    from tests.test_phase7_5_academic_agent_web import build_test_web_service, FakeProvider
    from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebUnavailableError
    from personal_learning_assistant.repositories.sqlite.tutor_repository import TutorRepositoryError
    service, path, course, provider, _ = build_test_web_service(tmp_path, provider=FakeProvider())
    session_id = service.create_session(course_id=course['id'], mode='doubt', source_policy='source_first')
    def fail(*args, **kwargs):
        raise TutorRepositoryError('Tutor session changed; refresh before retrying')
    monkeypatch.setattr(GroundedTutorService, 'answer', fail)
    with pytest.raises(AcademicAgentWebUnavailableError, match='could not be saved'):
        service.ask(session_id, 'Explain span.')
    assert provider.calls == 0


def test_browser_csrf_is_required_even_without_request_identity():
    from tests.test_phase7_5_academic_agent_web import fake_web_app, FakeWebService
    fake = FakeWebService()
    client = fake_web_app(fake).test_client()
    assert client.post('/agent/sessions', data={'mode':'doubt'}).status_code == 403
    assert client.post('/agent/sessions/session-1/ask', data={'question':'Explain span.'}).status_code == 403
    assert fake.llm_calls == 0


def test_provider_markdown_images_cannot_make_automatic_external_requests():
    from personal_learning_assistant.ui.web.tutor_rendering import render_tutor_markdown
    result = str(render_tutor_markdown('![private diagram](https://example.invalid/collect?data=private)'))
    assert '<img' not in result
    assert 'https://example.invalid' not in result
    assert 'private diagram' in result


def test_unclosed_math_metadata_fails_closed_and_is_never_displayed():
    from personal_learning_assistant.tutor.correctness import extract_and_verify_math
    visible, verification = extract_and_verify_math('A visible explanation.\n<!--ANVAYA_MATH {"claims":')
    assert visible == 'A visible explanation.'
    assert verification.applicable and not verification.passed
