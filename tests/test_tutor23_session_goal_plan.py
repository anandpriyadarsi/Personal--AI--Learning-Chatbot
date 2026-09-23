from __future__ import annotations

import sqlite3

from personal_learning_assistant.domain.tutor_models import (
    TutorProviderResponse,
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
from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner
from personal_learning_assistant.tutor.session_goal import (
    SESSION_GOAL_KEY,
    commit_session_goal,
    infer_session_goal,
    load_session_goal,
    resolve_session_goal,
)
from personal_learning_assistant.tutor.teaching_orchestrator import (
    TEACHING_PLAN_KEY,
    build_teaching_plan,
    load_teaching_plan,
    teaching_plan_mapping,
)


def test_first_request_infers_bounded_session_goal():
    goal = resolve_session_goal(
        "Explain why elimination multipliers are stored in L.",
        {},
        teaching_intent="explain",
    )

    assert goal["status"] == "active"
    assert goal["source"] == "inferred"
    assert goal["goal"].startswith("Understand ")
    assert "elimination multipliers" in goal["goal"]
    assert len(goal["goal"]) <= 360


def test_hint_and_quiz_intents_produce_learning_oriented_goals():
    assert infer_session_goal(
        "Give me a hint for why the multiplier enters L.",
        "hint",
    ).startswith("Work through ")

    assert infer_session_goal(
        "Quiz me on span and basis.",
        "quiz",
    ).startswith("Check understanding of ")


def test_follow_up_keeps_existing_goal():
    metadata = {
        SESSION_GOAL_KEY: {
            "version": 1,
            "goal": "Understand why elimination multipliers form L",
            "status": "active",
            "goal_evidence": [],
            "source": "inferred",
            "created_at": "2026-09-23T10:00:00Z",
            "updated_at": "2026-09-23T10:00:00Z",
        }
    }

    goal = resolve_session_goal(
        "Can you show me a small example of that?",
        metadata,
        teaching_intent="example",
    )

    assert goal["goal"] == "Understand why elimination multipliers form L"
    assert goal["created_at"] == "2026-09-23T10:00:00Z"


def test_explicit_topic_shift_replaces_old_goal():
    metadata = {
        SESSION_GOAL_KEY: {
            "version": 1,
            "goal": "Understand why elimination multipliers form L",
            "status": "active",
            "goal_evidence": [],
            "source": "inferred",
            "created_at": "2026-09-23T10:00:00Z",
            "updated_at": "2026-09-23T10:00:00Z",
        }
    }

    goal = resolve_session_goal(
        "Now explain determinant expansion by cofactors. Do not continue the LU discussion.",
        metadata,
        teaching_intent="explain",
    )

    assert goal["goal"] != metadata[SESSION_GOAL_KEY]["goal"]
    assert "determinant expansion" in goal["goal"].casefold()
    assert goal["source"] == "topic_shift"
    assert goal["created_at"] == ""


def test_commit_goal_sets_timestamps_without_rewriting_unchanged_goal_time():
    resolved = resolve_session_goal(
        "Explain LU factorization.",
        {},
        teaching_intent="explain",
    )
    metadata = commit_session_goal(
        {},
        resolved,
        now="2026-09-23T10:00:00Z",
    )
    first = load_session_goal(metadata)

    assert first["created_at"] == "2026-09-23T10:00:00Z"
    assert first["updated_at"] == "2026-09-23T10:00:00Z"

    metadata = commit_session_goal(
        metadata,
        first,
        now="2026-09-23T10:05:00Z",
    )
    unchanged = load_session_goal(metadata)

    assert unchanged["created_at"] == "2026-09-23T10:00:00Z"
    assert unchanged["updated_at"] == "2026-09-23T10:00:00Z"


def test_current_intent_controls_deterministic_teaching_move():
    goal = {
        "goal": "Understand LU factorization",
        "status": "active",
    }

    hint = build_teaching_plan(
        "Give me a hint.",
        teaching_intent="hint",
        adaptive_state={},
        session_goal=goal,
        teaching_policy={"practice_difficulty": "challenge"},
    )
    example = build_teaching_plan(
        "Show me an example.",
        teaching_intent="example",
        adaptive_state={},
        session_goal=goal,
        teaching_policy={"scaffolding": "guided"},
    )
    quiz = build_teaching_plan(
        "Quiz me.",
        teaching_intent="quiz",
        adaptive_state={},
        session_goal=goal,
        teaching_policy={},
    )

    assert hint.next_move == "give_hint"
    assert example.next_move == "give_example"
    assert quiz.next_move == "quiz"
    assert quiz.student_action_expected is True


def test_current_session_misconception_can_refine_generic_explanation():
    plan = build_teaching_plan(
        "Explain this again.",
        teaching_intent="explain",
        adaptive_state={
            "last_misconception": "Treats L as the matrix after elimination."
        },
        session_goal={
            "goal": "Understand how L is constructed",
            "status": "active",
        },
        teaching_policy={},
    )

    assert plan.next_move == "repair_misconception"
    assert plan.reason == "current_session_misconception"


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
            content=(
                "LU factorization stores elimination multipliers in the "
                "lower-triangular factor."
            ),
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="request-1",
        )


def _environment(tmp_path):
    path = tmp_path / "tutor23_fix1.db"
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
        now=lambda: "2026-09-23T10:00:00Z",
        id_factory=id_factory,
    )
    session = repository.create_session(
        session_id="session-1",
        course_id=None,
        topic_id=None,
        assessment_id=None,
        resource_id=None,
        mode="concept",
        source_policy="source_first",
        title="Tutor 2.3.1",
        metadata_json="{}",
        created_at="2026-09-23T09:00:00Z",
    )
    return path, connection, repository, sessions, session


def test_grounding_plan_carries_goal_and_same_teaching_plan_to_provider(tmp_path):
    _path, connection, _repository, sessions, session = _environment(tmp_path)
    planner = TutorGroundingPlanner(_EmptyRetrieval(), sessions)

    plan = planner.plan(
        session,
        "Give me a hint for understanding why multipliers enter L.",
        transcript=(),
    )
    request = planner.provider_request(session, plan, transcript=())

    assert plan.session_goal["goal"]
    assert plan.teaching_plan["next_move"] == "give_hint"
    assert request.metadata["session_goal"] == plan.session_goal
    assert request.metadata["teaching_plan"] == plan.teaching_plan

    prompt = request.messages[-1]["content"]
    assert "SESSION GOAL" in prompt
    assert "TEACHING PLAN" in prompt
    assert "next_move=give_hint" in prompt
    assert "CURRENT QUESTION" in prompt
    assert "Give me a hint" in prompt
    assert "not mastery/progress" in prompt
    connection.close()


def test_successful_exchange_persists_only_session_orchestration_state(tmp_path):
    _path, connection, repository, sessions, _session = _environment(tmp_path)
    provider = _Provider()
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=_EmptyRetrieval(),
        provider=provider,
    )

    before_memory = connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]

    result = engine.answer(
        "session-1",
        "Explain why elimination multipliers are stored in L.",
    )

    refreshed = repository.get_session("session-1")
    goal = load_session_goal(refreshed.metadata)
    teaching_plan = load_teaching_plan(refreshed.metadata)
    after_memory = connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]

    assert result.assistant_turn.content
    assert goal["goal"]
    assert goal["status"] == "active"
    assert goal["created_at"] == result.assistant_turn.created_at
    assert teaching_plan["next_move"] == "explain"
    assert teaching_plan["planned_at"] == result.assistant_turn.created_at
    assert SESSION_GOAL_KEY in refreshed.metadata
    assert TEACHING_PLAN_KEY in refreshed.metadata
    assert after_memory == before_memory
    connection.close()


def test_follow_up_plan_reuses_persisted_goal(tmp_path):
    _path, connection, repository, sessions, _session = _environment(tmp_path)
    provider = _Provider()
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=_EmptyRetrieval(),
        provider=provider,
    )

    engine.answer("session-1", "Explain LU factorization.")
    first = load_session_goal(repository.get_session("session-1").metadata)

    engine.answer("session-1", "Show me a small example of that.")
    second = load_session_goal(repository.get_session("session-1").metadata)
    teaching_plan = load_teaching_plan(
        repository.get_session("session-1").metadata
    )

    assert second["goal"] == first["goal"]
    assert teaching_plan["next_move"] == "give_example"
    connection.close()


def test_session_template_exposes_goal_and_move_as_non_mastery_context():
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

    assert "ANVAYA Tutor 2.3" in template
    assert "Session goal" in template
    assert "Current teaching move" in template
    assert "not mastery or academic progress" in template
