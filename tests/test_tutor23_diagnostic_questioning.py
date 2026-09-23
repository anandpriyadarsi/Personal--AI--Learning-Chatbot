from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
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
from personal_learning_assistant.tutor.diagnostic_planner import (
    plan_diagnostic_question,
)
from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner
from personal_learning_assistant.tutor.teaching_orchestrator import (
    build_teaching_plan,
    load_teaching_plan,
    teaching_plan_mapping,
)


def _goal(text="Understand LU factorization"):
    return {
        "goal": text,
        "status": "active",
        "goal_evidence": (),
        "source": "inferred",
    }


def test_vague_initial_confusion_asks_one_diagnostic_question():
    decision = plan_diagnostic_question(
        "I don't understand LU factorization.",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
    )

    assert decision.should_ask is True
    assert decision.reason == "initial_gap_unclear"
    assert decision.question.count("?") == 1
    assert "LU factorization" in decision.question
    assert "core idea" in decision.question
    assert "steps" in decision.question


def test_bare_topic_initial_request_can_trigger_diagnosis():
    decision = plan_diagnostic_question(
        "LU factorization",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
    )

    assert decision.should_ask is True
    assert decision.question


def test_explicit_explanation_request_skips_diagnosis():
    for question in (
        "Explain LU factorization.",
        "Teach me LU factorization.",
        "Tell me about LU factorization.",
        "Explain why elimination multipliers go into L.",
        "How is L constructed during LU factorization?",
        "What is LU factorization?",
    ):
        decision = plan_diagnostic_question(
            question,
            teaching_intent="explain",
            adaptive_state={"interaction_count": 0},
            session_goal=_goal(),
        )
        assert decision.should_ask is False, question


def test_explicit_pedagogical_intents_skip_diagnosis():
    for intent in (
        "hint",
        "quiz",
        "verify_reasoning",
        "follow_up_reference",
        "example",
        "practice",
        "summary",
        "guidance",
        "explain_differently",
    ):
        decision = plan_diagnostic_question(
            "I am confused about LU factorization.",
            teaching_intent=intent,
            adaptive_state={"interaction_count": 0},
            session_goal=_goal(),
        )
        assert decision.should_ask is False
        assert decision.reason == "explicit_teaching_request"


def test_known_current_gap_skips_diagnosis():
    decision = plan_diagnostic_question(
        "I don't understand LU factorization.",
        teaching_intent="explain",
        adaptive_state={
            "interaction_count": 0,
            "last_misconception": "Treats L as the matrix after elimination.",
        },
        session_goal=_goal(),
    )

    assert decision.should_ask is False
    assert decision.reason == "current_gap_already_known"


def test_later_ambiguous_turn_does_not_auto_diagnose_in_fix2():
    decision = plan_diagnostic_question(
        "I am still confused about LU factorization.",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 2},
        session_goal=_goal(),
    )

    assert decision.should_ask is False
    assert decision.reason == "not_initial_ambiguous_request"


def test_orchestrator_uses_ask_diagnostic_only_for_ambiguous_initial_explain():
    plan = build_teaching_plan(
        "I don't understand LU factorization.",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
        teaching_policy={"scaffolding": "guided"},
    )

    assert plan.next_move == "ask_diagnostic"
    assert plan.reason == "initial_gap_unclear"
    assert plan.student_action_expected is True
    assert plan.diagnostic_question


def test_orchestrator_preserves_explicit_hint_over_diagnostic_logic():
    plan = build_teaching_plan(
        "I don't understand LU factorization. Give me one hint only.",
        teaching_intent="hint",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
        teaching_policy={},
    )

    assert plan.next_move == "give_hint"
    assert plan.reason == "current_teaching_intent"
    assert plan.diagnostic_question == ""


def test_orchestrator_prefers_known_misconception_repair():
    plan = build_teaching_plan(
        "I don't understand LU factorization.",
        teaching_intent="explain",
        adaptive_state={
            "interaction_count": 0,
            "last_misconception": "Thinks U stores elimination multipliers.",
        },
        session_goal=_goal(),
        teaching_policy={},
    )

    assert plan.next_move == "repair_misconception"
    assert plan.reason == "current_session_misconception"
    assert plan.diagnostic_question == ""


def test_teaching_plan_mapping_preserves_diagnostic_question():
    plan = build_teaching_plan(
        "Help me with LU factorization.",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
        teaching_policy={},
    )
    mapped = teaching_plan_mapping(plan)

    assert mapped["next_move"] == "ask_diagnostic"
    assert mapped["diagnostic_question"] == plan.diagnostic_question


class _EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


class _Provider:
    configured = True

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        plan = dict(request.metadata.get("teaching_plan") or {})
        content = (
            plan.get("diagnostic_question")
            or "I will explain the requested topic directly."
        )
        return TutorProviderResponse(
            content=content,
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="request-1",
        )


def _environment(tmp_path):
    path = tmp_path / "tutor23_fix2.db"
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
        now=lambda: "2026-09-23T12:00:00Z",
        id_factory=id_factory,
    )
    session = repository.create_session(
        session_id="session-diagnostic",
        course_id=None,
        topic_id=None,
        assessment_id=None,
        resource_id=None,
        mode="concept",
        source_policy="source_first",
        title="Tutor 2.3.2",
        metadata_json="{}",
        created_at="2026-09-23T11:59:00Z",
    )
    return connection, repository, sessions, session


def test_grounding_provider_contract_contains_exact_diagnostic_question(tmp_path):
    connection, _repository, sessions, session = _environment(tmp_path)
    planner = TutorGroundingPlanner(_EmptyRetrieval(), sessions)

    plan = planner.plan(
        session,
        "I don't understand LU factorization.",
        transcript=(),
    )
    request = planner.provider_request(session, plan, transcript=())

    assert plan.teaching_plan["next_move"] == "ask_diagnostic"
    question = plan.teaching_plan["diagnostic_question"]
    assert question
    assert request.metadata["teaching_plan"]["diagnostic_question"] == question

    prompt = request.messages[-1]["content"]
    assert "next_move=ask_diagnostic" in prompt
    assert "Ask exactly one short diagnostic question and stop." in prompt
    assert question in prompt
    assert "wait" in prompt.casefold()
    connection.close()


def test_successful_diagnostic_turn_persists_plan_only_in_tutor_metadata(tmp_path):
    connection, repository, sessions, _session = _environment(tmp_path)
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
        "session-diagnostic",
        "I don't understand LU factorization.",
    )

    refreshed = repository.get_session("session-diagnostic")
    plan = load_teaching_plan(refreshed.metadata)
    after_memory = connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]

    assert result.assistant_turn.content == plan["diagnostic_question"]
    assert plan["next_move"] == "ask_diagnostic"
    assert plan["student_action_expected"] is True
    assert plan["diagnostic_question"]
    assert after_memory == before_memory
    connection.close()


def test_diagnostic_question_is_visible_in_tutor_template():
    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")

    assert "Diagnostic question:" in template
    assert "teaching_plan.get('diagnostic_question')" in template
