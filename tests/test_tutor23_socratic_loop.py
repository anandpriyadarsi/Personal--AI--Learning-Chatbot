from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_learning_assistant.domain.tutor_models import (
    TutorProviderResponse,
    TutorSessionSpec,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.services.grounded_tutor_service import (
    GroundedTutorService,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.tutor.adaptive_state import (
    load_adaptive_state,
)
from personal_learning_assistant.tutor.socratic_loop import (
    outcome_from_evaluation,
)


class RecordingRetrieval:
    def __init__(self):
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return ()


class SequenceProvider:
    configured = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        content = self.responses.pop(0)
        return TutorProviderResponse(
            content=content,
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="req-{}".format(len(self.requests)),
        )


def _env(tmp_path, responses=(), *, source_policy="source_first"):
    path = tmp_path / "tutor23_fix3.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    repository = SQLiteTutorRepository(connection)
    counters = {"turn": 0, "other": 0}

    def id_factory(prefix):
        if prefix == "tutor-turn":
            counters["turn"] += 1
            return "turn-{}".format(counters["turn"])
        counters["other"] += 1
        return "{}-{}".format(prefix, counters["other"])

    sessions = TutorSessionService(
        repository,
        id_factory=id_factory,
        now=lambda: "2026-09-23T13:00:00Z",
    )
    session = sessions.create_session(
        TutorSessionSpec(
            mode="doubt",
            source_policy=source_policy,
            title="Tutor 2.3.3 Socratic loop",
        )
    )
    retrieval = RecordingRetrieval()
    provider = SequenceProvider(responses)
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=retrieval,
        provider=provider,
    )
    return connection, repository, sessions, session, retrieval, provider, engine


def _start_diagnostic(engine, session_id):
    return engine.answer(
        session_id,
        "I don't understand LU factorization.",
    )


def test_socratic_outcome_mapping_is_bounded():
    assert outcome_from_evaluation({"status": "correct"}) == "advance"
    assert outcome_from_evaluation({"status": "partial"}) == "clarify"
    assert outcome_from_evaluation({"status": "incorrect"}) == "repair"
    assert outcome_from_evaluation({"status": "unclear"}) == "unclear"
    assert outcome_from_evaluation({}) == "unclear"


def test_diagnostic_turn_becomes_real_pending_tutor_question_without_provider(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        provider,
        engine,
    ) = _env(tmp_path)

    result = _start_diagnostic(engine, session.session_id)
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert provider.requests == []
    assert result.assistant_turn.content.startswith("For LU factorization")
    assert result.assistant_turn.content.endswith("?")
    assert state["interaction_count"] == 1
    assert state["quiz_active"] is False
    assert state["awaiting_student_answer"] is True
    assert state["pending_question"] == result.assistant_turn.content
    assert state["pending_question_kind"] == "diagnostic"
    assert state["answer_status"] == "pending"
    assert state["last_teaching_move"] == "ask_diagnostic"
    assert state["socratic_step_count"] == 1
    connection.close()


def test_source_only_can_ask_diagnostic_without_academic_evidence(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        provider,
        engine,
    ) = _env(tmp_path, source_policy="source_only")

    result = _start_diagnostic(engine, session.session_id)
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert provider.requests == []
    assert result.assistant_turn.content.endswith("?")
    assert result.assistant_turn.support_level == "insufficient"
    assert state["awaiting_student_answer"] is True
    assert state["pending_question_kind"] == "diagnostic"
    connection.close()


def test_next_short_reply_is_answer_to_diagnostic_and_advances_with_one_check(tmp_path):
    response = (
        '<!--ANVAYA_EVAL {"status":"correct",'
        '"reason":"Student identified that L records elimination multipliers.",'
        '"misconception":""}-->\n'
        "Yes. The key idea is that the elimination multipliers are saved in L.\n\n"
        "What would the entry L21 store when row 2 uses multiplier 3?"
    )
    (
        connection,
        repository,
        _sessions,
        session,
        retrieval,
        provider,
        engine,
    ) = _env(tmp_path, [response])

    _start_diagnostic(engine, session.session_id)
    retrieval.calls.clear()

    result = engine.answer(session.session_id, "The core idea.")
    request = provider.requests[0]
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert request.metadata["teaching_intent"] == "quiz_answer"
    assert request.metadata["teaching_plan"]["next_move"] == "check_understanding"
    assert request.metadata["teaching_plan"]["reason"] == "pending_socratic_answer"
    assert "pending_question_kind=diagnostic" in request.messages[-1]["content"]
    assert "at most one next check question" in request.messages[-1]["content"]
    assert "ANVAYA_EVAL" not in result.assistant_turn.content
    assert state["last_student_answer"] == "The core idea."
    assert state["answer_status"] == "correct"
    assert state["last_socratic_outcome"] == "advance"
    assert state["awaiting_student_answer"] is True
    assert state["pending_question_kind"] == "socratic_check"
    assert state["pending_question"].startswith("What would the entry L21")
    assert state["socratic_step_count"] == 2
    assert retrieval.calls
    assert "which part is blocking you most" in retrieval.calls[0][0].casefold()
    connection.close()


def test_partial_answer_records_clarify_outcome_and_keeps_one_follow_up(tmp_path):
    response = (
        '<!--ANVAYA_EVAL {"status":"partial",'
        '"reason":"Student names elimination but not the stored multiplier.",'
        '"misconception":"Does not yet connect the elimination multiplier to L."}-->\n'
        "You have the elimination part. The missing link is what gets saved.\n\n"
        "When row 2 subtracts 3 times row 1, what number should be stored in L21?"
    )
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(tmp_path, [response])

    _start_diagnostic(engine, session.session_id)
    engine.answer(session.session_id, "It is related to elimination.")

    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert state["answer_status"] == "partial"
    assert state["last_socratic_outcome"] == "clarify"
    assert "connect the elimination multiplier" in state[
        "last_misconception"
    ].casefold()
    assert state["pending_question_kind"] == "socratic_check"
    assert state["awaiting_student_answer"] is True
    connection.close()


def test_incorrect_answer_records_repair_outcome(tmp_path):
    response = (
        '<!--ANVAYA_EVAL {"status":"incorrect",'
        '"reason":"Student says U stores the elimination multiplier.",'
        '"misconception":"Thinks U stores elimination multipliers."}-->\n'
        "Not quite. U is the matrix left after elimination; the multiplier is stored in L.\n\n"
        "If the multiplier is 2, which factor should contain that 2?"
    )
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(tmp_path, [response])

    _start_diagnostic(engine, session.session_id)
    engine.answer(session.session_id, "I think U stores it.")

    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["answer_status"] == "incorrect"
    assert state["last_socratic_outcome"] == "repair"
    assert "u stores" in state["last_misconception"].casefold()
    assert state["pending_question_kind"] == "socratic_check"
    connection.close()


def test_unclear_answer_records_unclear_outcome(tmp_path):
    response = (
        '<!--ANVAYA_EVAL {"status":"unclear",'
        '"reason":"Answer is too short to identify the student's reasoning.",'
        '"misconception":""}-->\n'
        "I cannot tell which part you mean yet.\n\n"
        "Do you mean the multiplier calculation or why it is stored in L?"
    )
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(tmp_path, [response])

    _start_diagnostic(engine, session.session_id)
    engine.answer(session.session_id, "that part")

    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["answer_status"] == "unclear"
    assert state["last_socratic_outcome"] == "unclear"
    assert state["awaiting_student_answer"] is True
    connection.close()


def test_hint_during_diagnostic_preserves_pending_question(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        provider,
        engine,
    ) = _env(
        tmp_path,
        ["Hint: focus on the multiplier used during elimination."],
    )

    _start_diagnostic(engine, session.session_id)
    before = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    engine.answer(session.session_id, "Give me a hint only.")
    after = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert provider.requests[0].metadata["teaching_intent"] == "hint"
    assert after["awaiting_student_answer"] is True
    assert after["pending_question"] == before["pending_question"]
    assert after["pending_question_kind"] == "diagnostic"
    assert after["answer_status"] == "pending"
    connection.close()


def test_just_explain_override_cancels_pending_question_instead_of_grading_it(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        provider,
        engine,
    ) = _env(
        tmp_path,
        ["LU factorization rewrites elimination as A = LU."],
    )

    _start_diagnostic(engine, session.session_id)
    engine.answer(session.session_id, "Just explain it.")

    request = provider.requests[0]
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert request.metadata["teaching_intent"] == "explain"
    assert request.metadata["teaching_plan"]["next_move"] == "explain"
    assert state["awaiting_student_answer"] is False
    assert state["pending_question"] == ""
    assert state["pending_question_kind"] == ""
    assert state["answer_status"] == "unassessed"
    connection.close()


def test_explicit_topic_shift_cancels_socratic_loop(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        provider,
        engine,
    ) = _env(
        tmp_path,
        ["Cofactor expansion computes a determinant along a chosen row or column."],
    )

    _start_diagnostic(engine, session.session_id)
    engine.answer(
        session.session_id,
        "Now explain determinant expansion by cofactors. Do not continue LU.",
    )

    request = provider.requests[0]
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert request.metadata["teaching_intent"] == "explain"
    assert request.metadata["teaching_plan"]["next_move"] == "explain"
    assert state["awaiting_student_answer"] is False
    assert state["pending_question"] == ""
    assert state["pending_question_kind"] == ""
    connection.close()


def test_socratic_loop_does_not_write_learning_memory_or_progress(tmp_path):
    response = (
        '<!--ANVAYA_EVAL {"status":"correct",'
        '"reason":"Correctly identifies the stored multiplier.",'
        '"misconception":""}-->\n'
        "Correct. L stores the elimination multiplier."
    )
    (
        connection,
        _repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(tmp_path, [response])

    before_memory = connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]
    before_progress = connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0]

    _start_diagnostic(engine, session.session_id)
    engine.answer(session.session_id, "The multiplier used in elimination.")

    assert connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0] == before_memory
    assert connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0] == before_progress
    connection.close()


def test_socratic_state_is_visible_in_tutor_template():
    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")

    assert "Pending Tutor question:" in template
    assert "pending_question_kind" in template
    assert "Last Socratic outcome:" in template
    assert "socratic_step_count" in template
