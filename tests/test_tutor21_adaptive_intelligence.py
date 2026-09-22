from __future__ import annotations

import sqlite3

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
    STATE_KEY,
    load_adaptive_state,
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
        content = self.responses.pop(0)
        return TutorProviderResponse(
            content=content,
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="req-{}".format(len(self.requests)),
        )


def _env(tmp_path, responses):
    path = tmp_path / "tutor21.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(repository)
    session = sessions.create_session(
        TutorSessionSpec(
            mode="doubt",
            source_policy="source_first",
            title="Adaptive quiz",
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


def test_quiz_turn_persists_pending_question_in_session_metadata(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        retrieval,
        provider,
        engine,
    ) = _env(
        tmp_path,
        [
            (
                "Question 1\n\n"
                "Give an example of a spanning but linearly dependent set in "
                r"\(\mathbb R^3\). Why is it not a basis?"
            )
        ],
    )

    engine.answer(
        session.session_id,
        "Quiz me one question at a time on span, linear independence and basis.",
    )

    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["interaction_count"] == 1
    assert state["quiz_active"] is True
    assert state["awaiting_student_answer"] is True
    assert "Why is it not a basis?" in state["pending_question"]
    assert provider.requests[0].metadata["teaching_intent"] == "quiz"
    assert len(retrieval.calls) == 1
    connection.close()


def test_next_short_reply_is_treated_as_answer_to_pending_quiz_question(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        retrieval,
        provider,
        engine,
    ) = _env(
        tmp_path,
        [
            "Question 1\n\nWhy is the set {v1, v2, v3} not a basis?",
            (
                "Correct idea: the third vector is redundant because it is a linear "
                "combination of the first two.\n\n"
                "Question 2\n\nWhat property must be added to spanning to obtain a basis?"
            ),
        ],
    )

    engine.answer(session.session_id, "Quiz me one question at a time.")
    retrieval.calls.clear()

    engine.answer(
        session.session_id,
        "Because v3 can be written as v1 + v2, so it is redundant.",
    )

    second_request = provider.requests[1]
    assert second_request.metadata["teaching_intent"] == "quiz_answer"
    assert "STUDENT STATE" in second_request.messages[-1]["content"]
    assert "pending_question=Why is the set" in second_request.messages[-1]["content"]

    assert len(retrieval.calls) >= 2
    first_query = retrieval.calls[0][0]
    assert "Why is the set" in first_query
    assert "v3 can be written as v1 + v2" in first_query

    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["interaction_count"] == 2
    assert state["quiz_active"] is True
    assert state["awaiting_student_answer"] is True
    assert state["last_student_answer"].startswith("Because v3")
    assert state["pending_question"].startswith(
        "What property must be added to spanning"
    )
    connection.close()


def test_hint_during_active_quiz_preserves_pending_question(tmp_path):
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
        [
            "Question 1\n\nWhy does linear dependence create redundancy?",
            "Hint: ask whether one vector can be constructed from the others.",
        ],
    )

    engine.answer(session.session_id, "Quiz me one question at a time.")
    before = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    engine.answer(session.session_id, "Give me a hint only. Do not solve it.")
    after = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert provider.requests[1].metadata["teaching_intent"] == "hint"
    assert after["quiz_active"] is True
    assert after["awaiting_student_answer"] is True
    assert after["pending_question"] == before["pending_question"]
    connection.close()


def test_explicit_confusion_is_remembered_without_writing_learning_memory(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(
        tmp_path,
        [
            "Think of independence as removing redundant directions. "
            "Can you identify which vector is redundant?"
        ],
    )

    engine.answer(
        session.session_id,
        "I still don't understand why a basis needs linear independence.",
    )
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert "still don't understand" in state["unresolved_doubt"].casefold()

    # Tutor 2.1 state remains session-local and does not mutate global learning memory.
    assert connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0] == 0
    connection.close()


def test_adaptive_state_defaults_are_safe_for_old_tutor_sessions():
    state = load_adaptive_state({"origin": "older-session"})
    assert state["interaction_count"] == 0
    assert state["quiz_active"] is False
    assert state["awaiting_student_answer"] is False
    assert state["pending_question"] == ""
    assert state["answer_status"] == "unassessed"



def test_tutor21_template_tolerates_legacy_session_without_adaptive_state():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")

    assert (
        "session.adaptive_state if session and session.adaptive_state is defined else {}"
        in template
    )
    assert "session.adaptive_state.quiz_active" not in template
    assert "session.adaptive_state.awaiting_student_answer" not in template



def test_quiz_answer_hidden_evaluation_is_stripped_and_persisted_in_state(tmp_path):
    (
        connection,
        repository,
        sessions,
        session,
        _retrieval,
        provider,
        engine,
    ) = _env(
        tmp_path,
        [
            "Question 1\n\nWhy is a spanning dependent set not a basis?",
            (
                '<!--ANVAYA_EVAL {"status":"correct",'
                '"reason":"Identified redundancy from linear dependence.",'
                '"misconception":""}-->\n'
                "Exactly. Linear dependence means at least one vector is redundant.\n\n"
                "Question 2\n\nWhy does removing redundancy help coordinate uniqueness?"
            ),
        ],
    )

    engine.answer(session.session_id, "Quiz me one question at a time.")
    result = engine.answer(
        session.session_id,
        "Because one vector can be written as a combination of the others.",
    )

    assert "ANVAYA_EVAL" not in result.assistant_turn.content
    assert result.assistant_turn.content.startswith("Exactly.")
    assert "ANVAYA_EVAL" not in sessions.transcript(session.session_id)[-1].content

    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["answer_status"] == "correct"
    assert "redundancy" in state["last_evaluation_reason"].casefold()
    assert state["last_misconception"] == ""
    assert provider.requests[1].metadata["teaching_intent"] == "quiz_answer"
    assert "ANVAYA_EVAL" in provider.requests[1].messages[-1]["content"]
    connection.close()


def test_partial_quiz_answer_records_misconception_without_global_mastery_write(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(
        tmp_path,
        [
            "Question 1\n\nWhy must a basis be linearly independent?",
            (
                '<!--ANVAYA_EVAL {"status":"partial",'
                '"reason":"Recognizes uniqueness but does not connect it to redundancy.",'
                '"misconception":"Thinks spanning alone guarantees unique coordinates."}-->\n'
                "You have the uniqueness idea. The missing link is redundancy.\n\n"
                "Question 2\n\nWhat happens if one vector is a combination of the others?"
            ),
        ],
    )

    engine.answer(session.session_id, "Quiz me one question at a time.")
    engine.answer(
        session.session_id,
        "Because then every vector has coordinates.",
    )

    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["answer_status"] == "partial"
    assert "spanning alone" in state["last_misconception"].casefold()
    assert connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0] == 0
    connection.close()


def test_missing_quiz_evaluation_marker_degrades_to_unclear_not_error(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(
        tmp_path,
        [
            "Question 1\n\nWhy is v3 redundant?",
            (
                "Your answer is difficult to judge from that wording.\n\n"
                "Question 2\n\nCan you express v3 using v1 and v2?"
            ),
        ],
    )

    engine.answer(session.session_id, "Quiz me one question at a time.")
    result = engine.answer(session.session_id, "because it is")

    assert result.assistant_turn.content.startswith("Your answer")
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["answer_status"] == "unclear"
    connection.close()


def test_malformed_hidden_evaluation_is_removed_and_falls_back_to_unclear(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        _retrieval,
        _provider,
        engine,
    ) = _env(
        tmp_path,
        [
            "Question 1\n\nWhy is the set dependent?",
            (
                '<!--ANVAYA_EVAL {"status":not-json}-->\n'
                "Let's inspect the relation among the vectors.\n\n"
                "Question 2\n\nCan one vector be formed from the others?"
            ),
        ],
    )

    engine.answer(session.session_id, "Quiz me one question at a time.")
    result = engine.answer(session.session_id, "not sure")

    assert "ANVAYA_EVAL" not in result.assistant_turn.content
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["answer_status"] == "unclear"
    connection.close()
