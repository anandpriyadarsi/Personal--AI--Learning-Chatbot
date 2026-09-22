from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

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
from personal_learning_assistant.tutor.student_model import (
    build_persistent_student_model,
    student_model_prompt,
)
from personal_learning_assistant.tutor.student_signals import (
    SIGNAL_HISTORY_KEY,
    aggregate_stable_signals,
    append_signal_history,
    derive_turn_signals,
    load_signal_history,
)


def _event(
    *,
    kind,
    session_id,
    turn_id,
    observed_at,
    text="",
    course_id="course-ma",
    topic_id="topic-lu",
):
    return {
        "kind": kind,
        "text": text,
        "session_id": session_id,
        "turn_id": turn_id,
        "course_id": course_id,
        "topic_id": topic_id,
        "intent": "quiz_answer",
        "observed_at": observed_at,
    }


def test_stable_signal_requires_two_distinct_sessions():
    one = _event(
        kind="misconception",
        session_id="s1",
        turn_id="t1",
        observed_at="2026-09-20T10:00:00Z",
        text="Confuses L with the eliminated matrix.",
    )

    assert aggregate_stable_signals((("s1", (one,)),)) == ()


def test_same_signal_across_two_sessions_becomes_stable_with_provenance():
    first = _event(
        kind="misconception",
        session_id="s1",
        turn_id="t1",
        observed_at="2026-09-20T10:00:00Z",
        text="Confuses L with the eliminated matrix.",
    )
    second = _event(
        kind="misconception",
        session_id="s2",
        turn_id="t9",
        observed_at="2026-09-22T18:00:00Z",
        text="confuses L with the eliminated matrix",
    )

    stable = aggregate_stable_signals(
        (("s1", (first,)), ("s2", (second,)))
    )

    assert len(stable) == 1
    signal = stable[0]
    assert signal.kind == "misconception"
    assert signal.event_count == 2
    assert signal.session_count == 2
    assert signal.first_observed_at == "2026-09-20T10:00:00Z"
    assert signal.last_observed_at == "2026-09-22T18:00:00Z"
    assert signal.provenance == ("s1:t1", "s2:t9")


def test_topic_scopes_do_not_mix_into_one_stable_signal():
    lu = _event(
        kind="hint_requested",
        session_id="s1",
        turn_id="t1",
        observed_at="2026-09-20T10:00:00Z",
        topic_id="topic-lu",
    )
    basis = _event(
        kind="hint_requested",
        session_id="s2",
        turn_id="t2",
        observed_at="2026-09-21T10:00:00Z",
        topic_id="topic-basis",
    )

    assert aggregate_stable_signals(
        (("s1", (lu,)), ("s2", (basis,)))
    ) == ()


def test_signal_history_is_idempotent_and_bounded():
    metadata = {}
    first = _event(
        kind="hint_requested",
        session_id="s1",
        turn_id="t0",
        observed_at="2026-09-20T10:00:00Z",
    )
    metadata = append_signal_history(metadata, (first,))
    metadata = append_signal_history(metadata, (first,))

    assert len(load_signal_history(metadata)) == 1

    events = tuple(
        _event(
            kind="answer_correct",
            session_id="s1",
            turn_id="t{}".format(index),
            observed_at="2026-09-20T10:{:02d}:00Z".format(index % 60),
            text="evaluation {}".format(index),
        )
        for index in range(45)
    )
    metadata = append_signal_history(metadata, events)

    history = load_signal_history(metadata)
    assert len(history) == 40
    assert history[-1]["turn_id"] == "t44"


def test_derive_turn_signals_records_interaction_observations():
    session = SimpleNamespace(
        session_id="s1",
        course_id="course-ma",
        topic_id="topic-lu",
    )
    assistant = SimpleNamespace(
        turn_id="t2",
        created_at="2026-09-22T18:00:00Z",
    )
    state = {
        "answer_status": "partial",
        "last_evaluation_reason": "Core idea present but missing one step.",
        "unresolved_doubt": "Still unsure how multipliers enter L.",
        "last_misconception": "Thinks U stores the multipliers.",
        "last_math_verification": "repaired",
    }

    events = derive_turn_signals(
        session=session,
        assistant_turn=assistant,
        teaching_intent="hint",
        adaptive_state=state,
    )
    kinds = {item["kind"] for item in events}

    assert {
        "hint_requested",
        "answer_partial",
        "doubt",
        "misconception",
        "math_repaired",
    }.issubset(kinds)
    assert all(item["turn_id"] == "t2" for item in events)


def _course(connection, course_id, code, name):
    connection.execute(
        "INSERT INTO courses("
        "id,code,name,status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,'active','2026-09-01T00:00:00Z',"
        "'2026-09-01T00:00:00Z',NULL)",
        (course_id, code, name),
    )


def _database(tmp_path):
    path = tmp_path / "tutor22_signals.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    _course(connection, "course-ma", "MA103N", "Linear Algebra")
    connection.execute(
        "INSERT INTO topics("
        "id,course_id,name,normalized_name,position,status,confidence,"
        "raw_import_status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,1,'active',3,NULL,?,?,NULL)",
        (
            "topic-lu",
            "course-ma",
            "LU Factorization",
            "lu factorization",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
        ),
    )
    repository = SQLiteTutorRepository(connection)
    return connection, repository


def _insert_session(repository, *, session_id, metadata, created_at):
    repository.create_session(
        session_id=session_id,
        course_id="course-ma",
        topic_id="topic-lu",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title=session_id,
        metadata_json=json.dumps(metadata),
        created_at=created_at,
    )
    return repository.get_session(session_id)


def test_student_model_exposes_only_cross_session_stable_patterns(tmp_path):
    connection, repository = _database(tmp_path)

    meta1 = append_signal_history(
        {},
        (
            _event(
                kind="misconception",
                session_id="s1",
                turn_id="t1",
                observed_at="2026-09-20T10:00:00Z",
                text="Confuses L with the eliminated matrix.",
            ),
            _event(
                kind="hint_requested",
                session_id="s1",
                turn_id="t2",
                observed_at="2026-09-20T10:05:00Z",
            ),
        ),
    )
    meta2 = append_signal_history(
        {},
        (
            _event(
                kind="misconception",
                session_id="s2",
                turn_id="t8",
                observed_at="2026-09-22T18:00:00Z",
                text="confuses L with the eliminated matrix",
            ),
            _event(
                kind="hint_requested",
                session_id="s2",
                turn_id="t9",
                observed_at="2026-09-22T18:05:00Z",
            ),
        ),
    )
    _insert_session(
        repository,
        session_id="s1",
        metadata=meta1,
        created_at="2026-09-20T10:00:00Z",
    )
    _insert_session(
        repository,
        session_id="s2",
        metadata=meta2,
        created_at="2026-09-22T18:00:00Z",
    )
    current = _insert_session(
        repository,
        session_id="current",
        metadata={},
        created_at="2026-09-23T00:00:00Z",
    )

    model = build_persistent_student_model(repository, current)

    assert len(model.stable_signals) == 2
    kinds = {item["kind"] for item in model.stable_signals}
    assert kinds == {"misconception", "hint_requested"}

    prompt = student_model_prompt(model)
    assert "stable_cross_session_signal=" in prompt
    assert "sessions=2" in prompt
    assert "s1:t1" in prompt
    assert "s2:t8" in prompt
    connection.close()


class _EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


class _Provider:
    configured = True

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return TutorProviderResponse(
            content="Think about which row operation creates the multiplier.",
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="req-1",
        )


def test_real_tutor_hint_turn_records_signal_history(tmp_path):
    connection, repository = _database(tmp_path)
    sessions = TutorSessionService(
        repository,
        now=lambda: "2026-09-23T00:00:00Z",
        id_factory=lambda prefix: prefix + "-generated",
    )
    session = sessions.create_session(
        TutorSessionSpec(
            mode="doubt",
            source_policy="source_first",
            course_id="course-ma",
            topic_id="topic-lu",
            title="signal integration",
        )
    )
    provider = _Provider()
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=_EmptyRetrieval(),
        provider=provider,
    )

    result = engine.answer(
        session.session_id,
        "Give me a hint only.",
    )

    refreshed = repository.get_session(session.session_id)
    history = load_signal_history(refreshed.metadata)

    assert result.assistant_turn.content.startswith("Think about")
    assert any(item["kind"] == "hint_requested" for item in history)
    hint = next(item for item in history if item["kind"] == "hint_requested")
    assert hint["turn_id"] == result.assistant_turn.turn_id
    assert hint["topic_id"] == "topic-lu"
    connection.close()



def test_topic_scoped_student_model_does_not_pull_other_topic_history(tmp_path):
    connection, repository = _database(tmp_path)
    connection.execute(
        "INSERT INTO topics("
        "id,course_id,name,normalized_name,position,status,confidence,"
        "raw_import_status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,2,'active',3,NULL,?,?,NULL)",
        (
            "topic-basis",
            "course-ma",
            "Basis",
            "basis",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
        ),
    )

    basis_meta = append_signal_history(
        {},
        (
            _event(
                kind="misconception",
                session_id="basis-1",
                turn_id="b1",
                observed_at="2026-09-20T10:00:00Z",
                text="Thinks spanning alone guarantees a basis.",
                topic_id="topic-basis",
            ),
        ),
    )
    repository.create_session(
        session_id="basis-1",
        course_id="course-ma",
        topic_id="topic-basis",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title="basis",
        metadata_json=json.dumps(basis_meta),
        created_at="2026-09-20T10:00:00Z",
    )

    lu_meta = append_signal_history(
        {},
        (
            _event(
                kind="hint_requested",
                session_id="lu-1",
                turn_id="l1",
                observed_at="2026-09-21T10:00:00Z",
                topic_id="topic-lu",
            ),
        ),
    )
    repository.create_session(
        session_id="lu-1",
        course_id="course-ma",
        topic_id="topic-lu",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title="lu old",
        metadata_json=json.dumps(lu_meta),
        created_at="2026-09-21T10:00:00Z",
    )

    current = repository.create_session(
        session_id="lu-current",
        course_id="course-ma",
        topic_id="topic-lu",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title="lu current",
        metadata_json="{}",
        created_at="2026-09-23T00:00:00Z",
    )

    model = build_persistent_student_model(repository, current)
    prompt = student_model_prompt(model)

    assert model.previous_sessions_considered == 1
    assert "spanning alone guarantees" not in prompt.casefold()
    connection.close()


def test_tutor22_template_surfaces_stable_patterns_without_mastery_language():
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

    assert "Stable cross-session pattern" in template
    assert "sessions" in template
    assert "observations" in template
    assert "not a mastery score" in template
