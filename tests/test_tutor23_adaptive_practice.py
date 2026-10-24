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
from personal_learning_assistant.tutor.practice_sequencer import (
    next_level_for_status,
    plan_practice_sequence,
    practice_sequence_instruction,
)
from personal_learning_assistant.tutor.teaching_orchestrator import (
    build_teaching_plan,
    teaching_plan_instruction,
    teaching_plan_mapping,
)


def _goal():
    return {
        "goal": "Understand LU Factorization",
        "status": "active",
        "goal_evidence": (),
        "source": "inferred",
    }


def test_standard_practice_starts_at_level_three():
    plan = plan_practice_sequence(
        "Give me a practice problem on LU factorization.",
        teaching_intent="practice",
        adaptive_state={},
        teaching_policy={"practice_difficulty": "standard"},
    )

    assert plan.active is True
    assert plan.level == 3
    assert plan.level_name == "standard_application"
    assert plan.format == "mixed"
    assert plan.reason == "standard_practice_start"


def test_tutor22_supported_policy_starts_one_level_lower():
    plan = plan_practice_sequence(
        "Give me a practice problem.",
        teaching_intent="practice",
        adaptive_state={},
        teaching_policy={"practice_difficulty": "supported"},
    )

    assert plan.level == 2
    assert plan.reason == "personalized_policy_supported_start"


def test_tutor22_challenge_policy_starts_at_level_four_not_mastery():
    plan = plan_practice_sequence(
        "Give me a practice problem.",
        teaching_intent="practice",
        adaptive_state={},
        teaching_policy={"practice_difficulty": "challenge"},
    )

    assert plan.level == 4
    assert plan.reason == "personalized_policy_challenge_start"
    assert plan.level < 5


def test_explicit_harder_and_easier_requests_move_only_one_level():
    harder = plan_practice_sequence(
        "Give me a harder practice problem.",
        teaching_intent="practice",
        adaptive_state={"practice_level": 3},
        teaching_policy={},
    )
    easier = plan_practice_sequence(
        "Give me an easier practice problem.",
        teaching_intent="practice",
        adaptive_state={"practice_level": 3},
        teaching_policy={},
    )

    assert harder.level == 4
    assert harder.reason == "student_requested_harder"
    assert easier.level == 2
    assert easier.reason == "student_requested_easier"


def test_current_incorrect_answer_moves_down_only_one_level_even_with_misconception():
    plan = plan_practice_sequence(
        "Give me another practice problem.",
        teaching_intent="practice",
        adaptive_state={
            "practice_level": 4,
            "answer_status": "incorrect",
            "last_socratic_outcome": "repair",
            "last_misconception": "Thinks U stores elimination multipliers.",
        },
        teaching_policy={"practice_difficulty": "challenge"},
    )

    assert plan.level == 3
    assert plan.format == "misconception_targeted"
    assert "U stores elimination multipliers" in plan.focus


def test_partial_answer_holds_current_practice_level():
    plan = plan_practice_sequence(
        "Give me another practice problem.",
        teaching_intent="practice",
        adaptive_state={
            "practice_level": 4,
            "answer_status": "partial",
            "last_socratic_outcome": "clarify",
        },
        teaching_policy={},
    )

    assert plan.level == 4
    assert plan.reason == "current_session_hold_practice_level"


def test_current_correct_answer_allows_only_one_step_up():
    plan = plan_practice_sequence(
        "Give me another practice problem.",
        teaching_intent="practice",
        adaptive_state={
            "practice_level": 3,
            "answer_status": "correct",
            "last_socratic_outcome": "advance",
        },
        teaching_policy={},
    )

    assert plan.level == 4
    assert plan.reason == "current_session_success_allows_step_up"


def test_explicit_computational_format_beats_automatic_misconception_format():
    plan = plan_practice_sequence(
        "Give me a harder computational practice problem.",
        teaching_intent="practice",
        adaptive_state={
            "practice_level": 3,
            "answer_status": "incorrect",
            "last_socratic_outcome": "repair",
            "last_misconception": "Uses the wrong elimination multiplier.",
        },
        teaching_policy={},
    )

    assert plan.level == 4
    assert plan.format == "computational"
    assert "wrong elimination multiplier" in plan.focus
    assert plan.reason == "student_requested_harder"


def test_post_prerequisite_practice_becomes_bridge_task():
    plan = plan_practice_sequence(
        "Give me a practice problem now.",
        teaching_intent="practice",
        adaptive_state={
            "practice_level": 3,
            "last_teaching_move": "review_prerequisite",
            "answer_status": "unassessed",
        },
        teaching_policy={},
    )

    assert plan.level == 2
    assert plan.format == "prerequisite_bridge"
    assert "bridge the repaired prerequisite" in plan.focus
    assert plan.reason == "post_prerequisite_bridge_practice"


def test_next_level_transition_is_bounded_at_both_ends():
    assert next_level_for_status(3, "correct") == 4
    assert next_level_for_status(3, "partial") == 3
    assert next_level_for_status(3, "incorrect") == 2
    assert next_level_for_status(3, "unclear") == 2
    assert next_level_for_status(5, "correct") == 5
    assert next_level_for_status(1, "incorrect") == 1


def test_teaching_plan_carries_adaptive_practice_contract():
    plan = build_teaching_plan(
        "Give me a conceptual practice problem on LU factorization.",
        teaching_intent="practice",
        adaptive_state={},
        session_goal=_goal(),
        teaching_policy={"practice_difficulty": "standard"},
        course_context={},
    )
    mapped = teaching_plan_mapping(plan)
    instruction = teaching_plan_instruction(plan)

    assert mapped["next_move"] == "practice"
    assert mapped["practice_active"] is True
    assert mapped["practice_level"] == 3
    assert mapped["practice_format"] == "conceptual"
    assert "at most one practice task at a time" in instruction
    assert "question mark" in instruction
    assert "Never describe a practice level as mastery" in instruction


def test_pending_practice_answer_stays_in_adaptive_practice_move():
    plan = build_teaching_plan(
        "I used multiplier 2.",
        teaching_intent="quiz_answer",
        adaptive_state={
            "awaiting_student_answer": True,
            "pending_question": "What multiplier eliminates a21?",
            "pending_question_kind": "practice",
            "practice_active": True,
            "practice_level": 3,
            "practice_format": "computational",
        },
        session_goal=_goal(),
        teaching_policy={},
        course_context={},
    )
    mapped = teaching_plan_mapping(plan)
    instruction = teaching_plan_instruction(plan)

    assert mapped["next_move"] == "practice"
    assert mapped["reason"] == "adaptive_practice_answer"
    assert mapped["practice_level"] == 3
    assert "correct -> level 4" in instruction
    assert "partial -> level 3" in instruction
    assert "incorrect -> level 2" in instruction


def test_initial_practice_task_becomes_pending_even_if_imperative():
    state = evolve_adaptive_state(
        {},
        student_message="Give me practice.",
        assistant_message="Compute the LU factorization of A = [[2,1],[4,3]].",
        teaching_intent="practice",
        teaching_move="practice",
        practice_level=3,
        practice_format="computational",
    )

    assert state["practice_active"] is True
    assert state["practice_level"] == 3
    assert state["practice_format"] == "computational"
    assert state["practice_step_count"] == 1
    assert state["awaiting_student_answer"] is True
    assert state["pending_question_kind"] == "practice"
    assert state["pending_question"].startswith("Compute the LU")


def test_correct_practice_answer_steps_up_and_keeps_one_next_task():
    current = {
        "version": 6,
        "interaction_count": 1,
        "last_intent": "practice",
        "last_teaching_move": "practice",
        "quiz_active": False,
        "awaiting_student_answer": True,
        "pending_question": "What is the elimination multiplier?",
        "pending_question_kind": "practice",
        "last_student_answer": "",
        "last_socratic_outcome": "",
        "socratic_step_count": 1,
        "practice_active": True,
        "practice_level": 3,
        "practice_step_count": 1,
        "practice_format": "computational",
        "practice_focus": "",
        "unresolved_doubt": "",
        "answer_status": "pending",
        "last_evaluation_reason": "",
        "last_misconception": "",
        "last_math_verification": "not_applicable",
        "last_math_claims_checked": 0,
    }

    state = evolve_adaptive_state(
        current,
        student_message="2",
        assistant_message=(
            "Correct. Now what multiplier eliminates the entry in row 3?"
        ),
        teaching_intent="quiz_answer",
        teaching_move="practice",
        practice_level=3,
        practice_format="computational",
        answer_evaluation={
            "status": "correct",
            "reason": "Correct multiplier.",
            "misconception": "",
        },
    )

    assert state["answer_status"] == "correct"
    assert state["last_socratic_outcome"] == "advance"
    assert state["practice_level"] == 4
    assert state["practice_active"] is True
    assert state["pending_question_kind"] == "practice"
    assert state["practice_step_count"] == 2


def test_incorrect_practice_answer_steps_down_once_and_targets_misconception():
    current = {
        "version": 6,
        "interaction_count": 1,
        "last_intent": "practice",
        "last_teaching_move": "practice",
        "quiz_active": False,
        "awaiting_student_answer": True,
        "pending_question": "What is the elimination multiplier?",
        "pending_question_kind": "practice",
        "last_student_answer": "",
        "last_socratic_outcome": "",
        "socratic_step_count": 1,
        "practice_active": True,
        "practice_level": 4,
        "practice_step_count": 1,
        "practice_format": "computational",
        "practice_focus": "",
        "unresolved_doubt": "",
        "answer_status": "pending",
        "last_evaluation_reason": "",
        "last_misconception": "",
        "last_math_verification": "not_applicable",
        "last_math_claims_checked": 0,
    }

    state = evolve_adaptive_state(
        current,
        student_message="4",
        assistant_message=(
            "Not quite. What multiplier should you use for row 2?"
        ),
        teaching_intent="quiz_answer",
        teaching_move="practice",
        practice_level=4,
        practice_format="computational",
        answer_evaluation={
            "status": "incorrect",
            "reason": "Used the target entry instead of the ratio.",
            "misconception": "Treats the target entry itself as the multiplier.",
        },
    )

    assert state["practice_level"] == 3
    assert state["practice_format"] == "misconception_targeted"
    assert "target entry itself" in state["practice_focus"]
    assert state["pending_question_kind"] == "practice"


def test_hint_during_practice_preserves_pending_practice_state():
    current = {
        "version": 6,
        "interaction_count": 2,
        "last_intent": "practice",
        "last_teaching_move": "practice",
        "quiz_active": False,
        "awaiting_student_answer": True,
        "pending_question": "What multiplier eliminates a21?",
        "pending_question_kind": "practice",
        "last_student_answer": "",
        "last_socratic_outcome": "",
        "socratic_step_count": 1,
        "practice_active": True,
        "practice_level": 3,
        "practice_step_count": 1,
        "practice_format": "computational",
        "practice_focus": "",
        "unresolved_doubt": "",
        "answer_status": "pending",
        "last_evaluation_reason": "",
        "last_misconception": "",
        "last_math_verification": "not_applicable",
        "last_math_claims_checked": 0,
    }

    state = evolve_adaptive_state(
        current,
        student_message="Give me a hint only.",
        assistant_message="Hint: divide the target entry by the pivot.",
        teaching_intent="hint",
        teaching_move="give_hint",
    )

    assert state["practice_active"] is True
    assert state["practice_level"] == 3
    assert state["pending_question_kind"] == "practice"
    assert state["pending_question"] == "What multiplier eliminates a21?"


def test_pending_practice_reply_resolves_as_answer_intent():
    intent = resolve_adaptive_intent(
        "2",
        {
            "awaiting_student_answer": True,
            "pending_question": "What multiplier eliminates a21?",
            "pending_question_kind": "practice",
            "practice_active": True,
            "practice_level": 3,
        },
    )

    assert intent.name == "quiz_answer"


def test_student_override_cancels_active_practice_but_keeps_last_level():
    state = contextualize_adaptive_state(
        "Just explain it.",
        {
            "awaiting_student_answer": True,
            "pending_question": "What multiplier eliminates a21?",
            "pending_question_kind": "practice",
            "practice_active": True,
            "practice_level": 3,
            "practice_step_count": 2,
            "practice_format": "computational",
            "answer_status": "pending",
        },
    )

    assert state["practice_active"] is False
    assert state["practice_level"] == 3
    assert state["pending_question"] == ""
    assert state["pending_question_kind"] == ""
    assert state["answer_status"] == "unassessed"


def test_explicit_topic_shift_resets_practice_sequence():
    state = contextualize_adaptive_state(
        "Now explain cofactor expansion.",
        {
            "awaiting_student_answer": True,
            "pending_question": "What multiplier eliminates a21 in LU?",
            "pending_question_kind": "practice",
            "practice_active": True,
            "practice_level": 4,
            "practice_step_count": 3,
            "practice_format": "computational",
            "practice_focus": "LU factorization",
        },
    )

    assert state["practice_active"] is False
    assert state["practice_level"] == 0
    assert state["practice_step_count"] == 0
    assert state["practice_format"] == ""
    assert state["pending_question"] == ""


def test_existing_quiz_lineage_remains_quiz_not_practice():
    state = evolve_adaptive_state(
        {
            "quiz_active": True,
            "awaiting_student_answer": True,
            "pending_question": "Why is this set dependent?",
            "pending_question_kind": "quiz",
            "practice_active": False,
            "practice_level": 0,
            "answer_status": "pending",
        },
        student_message="Because one vector is a combination of the others.",
        assistant_message="Correct. What condition is needed for a basis?",
        teaching_intent="quiz_answer",
        teaching_move="check_understanding",
        answer_evaluation={
            "status": "correct",
            "reason": "Correct dependence argument.",
            "misconception": "",
        },
    )

    assert state["quiz_active"] is True
    assert state["pending_question_kind"] == "quiz"
    assert state["practice_active"] is False
    assert state["practice_level"] == 0


def test_practice_instruction_never_claims_mastery():
    sequence = plan_practice_sequence(
        "Give me a harder problem.",
        teaching_intent="practice",
        adaptive_state={"practice_level": 4},
        teaching_policy={},
    )
    instruction = practice_sequence_instruction(sequence, answering=False)

    assert "mastery" not in instruction.casefold()
    assert "one practice task" in instruction



class _EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


class _SequenceProvider:
    configured = True

    def __init__(self, responses):
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


def test_real_tutor_service_persists_and_advances_practice_loop(tmp_path):
    path = tmp_path / "tutor23_fix5.db"
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
        now=lambda: "2026-09-23T15:00:00Z",
        id_factory=id_factory,
    )
    session = sessions.create_session(
        TutorSessionSpec(
            mode="concept",
            source_policy="source_first",
            title="Tutor 2.3.5 practice integration",
        )
    )
    provider = _SequenceProvider(
        (
            "For A = [[2,1],[4,3]], what multiplier eliminates the first entry in row 2?",
            (
                '<!--ANVAYA_EVAL {"status":"correct",'
                '"reason":"Correct elimination multiplier.",'
                '"misconception":""}-->\n'
                "Correct. What multiplier would eliminate 6 below a pivot of 2?"
            ),
        )
    )
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=_EmptyRetrieval(),
        provider=provider,
    )

    before_memory = connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]
    before_progress = connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0]

    first = engine.answer(
        session.session_id,
        "Give me a computational practice problem on elimination.",
    )
    first_state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert first.assistant_turn.content.endswith("?")
    assert first_state["practice_active"] is True
    assert first_state["practice_level"] == 3
    assert first_state["practice_format"] == "computational"
    assert first_state["pending_question_kind"] == "practice"
    assert first_state["practice_step_count"] == 1

    second = engine.answer(session.session_id, "2")
    second_state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )

    assert "ANVAYA_EVAL" not in second.assistant_turn.content
    assert second_state["answer_status"] == "correct"
    assert second_state["last_socratic_outcome"] == "advance"
    assert second_state["practice_level"] == 4
    assert second_state["practice_active"] is True
    assert second_state["pending_question_kind"] == "practice"
    assert second_state["practice_step_count"] == 2
    assert len(provider.requests) == 2
    assert (
        provider.requests[1].metadata["teaching_plan"]["reason"]
        == "adaptive_practice_answer"
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0] == before_memory
    assert connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0] == before_progress
    connection.close()


def test_tutor_template_exposes_practice_plan_as_session_local():
    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")

    assert "Practice sequence:" in template
    assert "Practice plan:" in template
    assert "Session-local, not mastery" in template
