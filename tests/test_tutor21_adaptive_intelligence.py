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
