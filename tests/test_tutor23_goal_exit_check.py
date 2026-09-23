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
    contextualize_adaptive_state,
    evolve_adaptive_state,
    load_adaptive_state,
    resolve_adaptive_intent,
)
from personal_learning_assistant.tutor.goal_evaluator import (
    contextualize_goal_for_turn,
    evaluate_goal_after_turn,
    exit_check_question,
    plan_exit_check,
)
from personal_learning_assistant.tutor.session_goal import (
    SESSION_GOAL_KEY,
    load_session_goal,
)
from personal_learning_assistant.tutor.teaching_orchestrator import (
    build_teaching_plan,
    teaching_plan_instruction,
    teaching_plan_mapping,
)


def _goal(status="active"):
    return {
        "version": 1,
        "goal": "Understand why elimination multipliers form L in LU factorization",
        "status": status,
        "goal_evidence": (),
        "source": "inferred",
        "created_at": "",
        "updated_at": "",
    }


def test_understanding_claim_requests_exit_check_without_marking_goal_met():
    decision = plan_exit_check(
        "I understand it now.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
    )

    assert decision.should_ask is True
    assert decision.reason == "student_reports_understanding"
    assert "Before we close this session goal" in decision.question
    assert _goal()["status"] == "active"


def test_understanding_of_one_idea_plus_new_question_does_not_exit():
    decision = plan_exit_check(
        "I understand span but why does a basis need linear independence?",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
    )

    assert decision.should_ask is False


def test_understanding_plus_explicit_new_teaching_request_does_not_exit():
    decision = plan_exit_check(
        "I understand span. Now explain linear independence.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
    )

    assert decision.should_ask is False


def test_explicit_exit_request_still_wins_after_understanding_claim():
    decision = plan_exit_check(
        "I understand it now. Can we move on?",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
    )

    assert decision.should_ask is True
    assert decision.reason == "explicit_exit_check_requested"


def test_explicit_understanding_check_request_is_supported():
    decision = plan_exit_check(
        "Check if I understand this.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
    )

    assert decision.should_ask is True
    assert decision.reason == "explicit_exit_check_requested"
    assert decision.question.endswith("?")


def test_unresolved_statement_does_not_trigger_exit_check():
    decision = plan_exit_check(
        "I still don't understand why the multipliers go into L.",
        teaching_intent="explain_differently",
        adaptive_state={},
        session_goal=_goal(),
    )

    assert decision.should_ask is False


def test_pending_tutor_question_blocks_new_exit_check():
    decision = plan_exit_check(
        "I think I understand now.",
        teaching_intent="explain",
        adaptive_state={
            "awaiting_student_answer": True,
            "pending_question": "What is the multiplier?",
            "pending_question_kind": "practice",
        },
        session_goal=_goal(),
    )

    assert decision.should_ask is False


def test_likely_met_goal_does_not_reask_exit_check_without_reopening():
    decision = plan_exit_check(
        "I understand.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal("likely_met"),
    )

    assert decision.should_ask is False


def test_explicit_confusion_reopens_likely_met_goal_as_unresolved():
    goal = contextualize_goal_for_turn(
        "I am still confused about why the multiplier has a positive sign in L.",
        _goal("likely_met"),
    )

    assert goal["status"] == "unresolved"
    assert any(
        item.startswith("student_reported_unresolved:")
        for item in goal["goal_evidence"]
    )


def test_exit_check_question_is_goal_specific_and_bounded():
    question = exit_check_question(_goal())

    assert "elimination multipliers form L" in question
    assert question.endswith("?")
    assert len(question) <= 500


def test_teaching_plan_uses_one_exit_check_for_understanding_claim():
    plan = build_teaching_plan(
        "I understand it now.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
        teaching_policy={},
        course_context={},
    )
    mapped = teaching_plan_mapping(plan)

    assert mapped["next_move"] == "check_understanding"
    assert mapped["reason"] == "student_reports_understanding"
    assert mapped["student_action_expected"] is True
    assert mapped["exit_check_question"].endswith("?")
    assert mapped["goal_status"] == "active"


def test_pending_exit_check_answer_uses_finish_goal_move():
    plan = build_teaching_plan(
        "Because L stores the elimination multipliers.",
        teaching_intent="quiz_answer",
        adaptive_state={
            "awaiting_student_answer": True,
            "pending_question": "Explain the central LU idea?",
            "pending_question_kind": "exit_check",
        },
        session_goal=_goal(),
        teaching_policy={},
        course_context={},
    )
    mapped = teaching_plan_mapping(plan)
    instruction = teaching_plan_instruction(plan)

    assert mapped["next_move"] == "finish_goal"
    assert mapped["reason"] == "pending_exit_check_answer"
    assert "likely met" in instruction
    assert "Do not call it mastery" in instruction


def test_correct_exit_check_marks_only_session_goal_likely_met():
    goal = evaluate_goal_after_turn(
        _goal(),
        teaching_plan={"reason": "pending_exit_check_answer"},
        adaptive_state={
            "answer_status": "correct",
            "last_evaluation_reason": "Explains that L stores elimination multipliers.",
            "last_misconception": "",
            "last_math_verification": "not_applicable",
        },
    )

    assert goal["status"] == "likely_met"
    assert any(
        item.startswith("exit_check_correct")
        for item in goal["goal_evidence"]
    )


def test_partial_exit_check_marks_goal_unresolved():
    goal = evaluate_goal_after_turn(
        _goal(),
        teaching_plan={"reason": "pending_exit_check_answer"},
        adaptive_state={
            "answer_status": "partial",
            "last_evaluation_reason": "Understands U but not where L comes from.",
            "last_misconception": "",
            "last_math_verification": "not_applicable",
        },
    )

    assert goal["status"] == "unresolved"
    assert any(
        item.startswith("exit_check_partial")
        for item in goal["goal_evidence"]
    )


def test_incorrect_exit_check_marks_goal_unresolved():
    goal = evaluate_goal_after_turn(
        _goal(),
        teaching_plan={"reason": "pending_exit_check_answer"},
        adaptive_state={
            "answer_status": "incorrect",
            "last_evaluation_reason": "Places multipliers in U.",
            "last_misconception": "Thinks U stores elimination multipliers.",
            "last_math_verification": "not_applicable",
        },
    )

    assert goal["status"] == "unresolved"
    assert any(
        item.startswith("exit_check_incorrect")
        for item in goal["goal_evidence"]
    )


def test_math_blocked_correct_label_cannot_mark_goal_likely_met():
    goal = evaluate_goal_after_turn(
        _goal(),
        teaching_plan={"reason": "pending_exit_check_answer"},
        adaptive_state={
            "answer_status": "correct",
            "last_evaluation_reason": "Claims the computation is correct.",
            "last_misconception": "",
            "last_math_verification": "blocked",
        },
    )

    assert goal["status"] == "unresolved"
    assert any(
        item.startswith("exit_check_math_blocked")
        for item in goal["goal_evidence"]
    )


def test_non_exit_answer_cannot_mark_goal_likely_met():
    goal = evaluate_goal_after_turn(
        _goal(),
        teaching_plan={"reason": "adaptive_practice_answer"},
        adaptive_state={
            "answer_status": "correct",
            "last_evaluation_reason": "Correct practice answer.",
            "last_misconception": "",
            "last_math_verification": "passed",
        },
    )

    assert goal["status"] == "active"
    assert goal["goal_evidence"] == ()


def test_exit_check_becomes_one_shot_pending_question():
    state = evolve_adaptive_state(
        {},
        student_message="I understand now.",
        assistant_message=exit_check_question(_goal()),
        teaching_intent="explain",
        teaching_move="check_understanding",
        planned_exit_check=exit_check_question(_goal()),
    )

    assert state["awaiting_student_answer"] is True
    assert state["pending_question_kind"] == "exit_check"
    assert state["exit_check_count"] == 1
    assert state["answer_status"] == "pending"


def test_exit_check_answer_clears_pending_lineage_after_one_evaluation():
    current = evolve_adaptive_state(
        {},
        student_message="I understand now.",
        assistant_message=exit_check_question(_goal()),
        teaching_intent="explain",
        teaching_move="check_understanding",
        planned_exit_check=exit_check_question(_goal()),
    )

    next_state = evolve_adaptive_state(
        current,
        student_message="L stores the multipliers used to eliminate entries below pivots.",
        assistant_message=(
            "Correct. That is the decisive connection, so the current session goal "
            "appears likely met based on this session."
        ),
        teaching_intent="quiz_answer",
        teaching_move="finish_goal",
        answer_evaluation={
            "status": "correct",
            "reason": "Correctly connects elimination multipliers to L.",
            "misconception": "",
        },
    )

    assert next_state["answer_status"] == "correct"
    assert next_state["last_socratic_outcome"] == "advance"
    assert next_state["awaiting_student_answer"] is False
    assert next_state["pending_question"] == ""
    assert next_state["pending_question_kind"] == ""
    assert next_state["exit_check_count"] == 1


def test_pending_exit_check_reply_resolves_as_quiz_answer_intent():
    intent = resolve_adaptive_intent(
        "L stores the elimination multipliers.",
        {
            "awaiting_student_answer": True,
            "pending_question": "Explain the main LU idea?",
            "pending_question_kind": "exit_check",
        },
    )

    assert intent.name == "quiz_answer"


def test_student_can_cancel_pending_exit_check():
    state = contextualize_adaptive_state(
        "Just explain it.",
        {
            "awaiting_student_answer": True,
            "pending_question": "Explain the main LU idea?",
            "pending_question_kind": "exit_check",
            "answer_status": "pending",
        },
    )

    assert state["awaiting_student_answer"] is False
    assert state["pending_question"] == ""
    assert state["pending_question_kind"] == ""
    assert state["answer_status"] == "unassessed"


class _EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


class _SequenceProvider:
    configured = True

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return TutorProviderResponse(
            content=self.responses.pop(0),
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="request-{}".format(len(self.requests)),
        )


def _environment(tmp_path, *, source_policy="source_first", responses=()):
    path = tmp_path / "tutor23_fix6.db"
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
        now=lambda: "2026-09-23T16:00:00Z",
        id_factory=id_factory,
    )
    session = sessions.create_session(
        TutorSessionSpec(
            mode="concept",
            source_policy=source_policy,
            title="Tutor 2.3.6 exit-check integration",
        )
    )
    sessions.update_session_metadata(
        session.session_id,
        {
            SESSION_GOAL_KEY: {
                **_goal(),
                "created_at": "2026-09-23T15:30:00Z",
                "updated_at": "2026-09-23T15:30:00Z",
            }
        },
    )
    provider = _SequenceProvider(responses)
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=_EmptyRetrieval(),
        provider=provider,
    )
    return connection, repository, sessions, session, provider, engine


def test_real_service_exit_check_then_correct_answer_marks_likely_met(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        provider,
        engine,
    ) = _environment(
        tmp_path,
        responses=(
            (
                '<!--ANVAYA_EVAL {"status":"correct",'
                '"reason":"Correctly explains that L stores elimination multipliers.",'
                '"misconception":""}-->\n'
                "Correct. The current session goal appears likely met based on this session."
            ),
        ),
    )

    before_memory = connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]
    before_progress = connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0]

    first = engine.answer(session.session_id, "I understand it now.")
    after_prompt = repository.get_session(session.session_id)
    prompt_state = load_adaptive_state(after_prompt.metadata)
    prompt_goal = load_session_goal(after_prompt.metadata)

    assert first.assistant_turn.content.startswith(
        "Before we close this session goal"
    )
    assert provider.requests == []
    assert prompt_state["pending_question_kind"] == "exit_check"
    assert prompt_state["exit_check_count"] == 1
    assert prompt_goal["status"] == "active"

    second = engine.answer(
        session.session_id,
        "L stores the multipliers used during Gaussian elimination, while U is what remains.",
    )
    completed = repository.get_session(session.session_id)
    completed_state = load_adaptive_state(completed.metadata)
    completed_goal = load_session_goal(completed.metadata)

    assert "ANVAYA_EVAL" not in second.assistant_turn.content
    assert len(provider.requests) == 1
    assert (
        provider.requests[0].metadata["teaching_plan"]["reason"]
        == "pending_exit_check_answer"
    )
    assert (
        provider.requests[0].metadata["teaching_plan"]["next_move"]
        == "finish_goal"
    )
    assert completed_state["pending_question_kind"] == ""
    assert completed_state["answer_status"] == "correct"
    assert completed_goal["status"] == "likely_met"
    assert any(
        item.startswith("exit_check_correct")
        for item in completed_goal["goal_evidence"]
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0] == before_memory
    assert connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0] == before_progress
    connection.close()


def test_mixed_understanding_followup_reaches_normal_provider_flow(tmp_path):
    (
        connection,
        _repository,
        _sessions,
        session,
        provider,
        engine,
    ) = _environment(
        tmp_path,
        responses=(
            "General explanation (not from project sources)\n\n"
            "A basis needs linear independence so its vectors contain no redundancy.",
        ),
    )

    result = engine.answer(
        session.session_id,
        "I understand span but why does a basis need linear independence?",
    )

    assert len(provider.requests) == 1
    assert (
        provider.requests[0].metadata["teaching_plan"]["reason"]
        != "student_reports_understanding"
    )
    assert "no redundancy" in result.assistant_turn.content
    connection.close()


def test_source_only_can_ask_exit_check_without_project_evidence(tmp_path):
    (
        connection,
        repository,
        _sessions,
        session,
        provider,
        engine,
    ) = _environment(
        tmp_path,
        source_policy="source_only",
        responses=(),
    )

    result = engine.answer(
        session.session_id,
        "Check if I understand this.",
    )
    stored = repository.get_session(session.session_id)
    state = load_adaptive_state(stored.metadata)

    assert result.assistant_turn.content.startswith(
        "Before we close this session goal"
    )
    assert result.assistant_turn.support_level == "insufficient"
    assert provider.requests == []
    assert state["pending_question_kind"] == "exit_check"
    connection.close()


def test_template_exposes_exit_check_and_goal_evidence():
    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")

    assert "Exit check:" in template
    assert "Goal evidence" in template
    assert "Current-session evidence only · not mastery." in template
    assert "Exit checks asked:" in template
