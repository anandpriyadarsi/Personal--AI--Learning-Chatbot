"""Deterministic teaching orchestration for ANVAYA Tutor 2.3.

Tutor 2.3.1 established bounded teaching moves. Tutor 2.3.2 added one bounded
diagnostic question for genuinely ambiguous initial requests. Tutor 2.3.3
continues a pending pedagogical question across turns. Tutor 2.3.4 adds
course-scoped prerequisite repair. Tutor 2.3.5 adds bounded adaptive practice
sequencing. Goal completion remains reserved for Tutor 2.3.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from personal_learning_assistant.tutor.concept_dependencies import (
    plan_prerequisite_review,
    prerequisite_decision_mapping,
)
from personal_learning_assistant.tutor.diagnostic_planner import (
    plan_diagnostic_question,
)
from personal_learning_assistant.tutor.practice_sequencer import (
    plan_practice_sequence,
    practice_sequence_instruction,
    practice_sequence_mapping,
)
from personal_learning_assistant.tutor.session_goal import (
    session_goal_mapping,
)
from personal_learning_assistant.tutor.socratic_loop import (
    socratic_outcome_instruction,
)


TEACHING_PLAN_KEY = "tutor23_teaching_plan"
TEACHING_MOVES = (
    "explain",
    "ask_diagnostic",
    "give_hint",
    "ask_student_to_try",
    "repair_misconception",
    "review_prerequisite",
    "give_example",
    "practice",
    "quiz",
    "check_understanding",
    "summarize",
    "finish_goal",
)

_INTENT_MOVES = {
    "hint": "give_hint",
    "quiz": "quiz",
    "verify_reasoning": "check_understanding",
    "follow_up_reference": "explain",
    "example": "give_example",
    "practice": "practice",
    "summary": "summarize",
    "guidance": "explain",
    "explain_differently": "explain",
    "quiz_answer": "check_understanding",
    "explain": "explain",
}


def _clean(value, limit=500):
    return " ".join(str(value or "").strip().split())[: int(limit)]


@dataclass(frozen=True)
class TeachingPlan:
    next_move: str
    reason: str
    goal: str
    goal_status: str
    student_action_expected: bool = False
    diagnostic_question: str = ""
    target_concept: str = ""
    prerequisite_concept: str = ""
    prerequisite_reason: str = ""
    target_topic_id: str = ""
    prerequisite_topic_id: str = ""
    return_to_goal: bool = True
    practice_active: bool = False
    practice_level: int = 3
    practice_level_name: str = "standard_application"
    practice_format: str = "mixed"
    practice_focus: str = ""
    practice_reason: str = ""
    practice_after_correct_level: int = 4
    practice_after_partial_level: int = 3
    practice_after_incorrect_level: int = 2
    practice_after_unclear_level: int = 2


def build_teaching_plan(
    question,
    *,
    teaching_intent,
    adaptive_state,
    session_goal,
    teaching_policy=None,
    course_context=None,
):
    """Choose one deterministic next move while keeping current intent dominant."""
    intent = _clean(teaching_intent, 80).casefold() or "explain"
    state = dict(adaptive_state or {})
    goal = session_goal_mapping(session_goal)

    move = _INTENT_MOVES.get(intent, "explain")
    reason = "current_teaching_intent"
    student_action_expected = move in {"quiz", "practice", "check_understanding"}

    if (
        intent == "quiz_answer"
        and bool(state.get("awaiting_student_answer"))
        and _clean(state.get("pending_question"), 500)
    ):
        move = "check_understanding"
        reason = "pending_socratic_answer"
        student_action_expected = True

    # Current-session misconception may refine a generic explanation, but it
    # never overrides an explicit student request such as hint/example/quiz.
    if (
        intent in {"explain", "explain_differently"}
        and _clean(state.get("last_misconception"), 240)
    ):
        move = "repair_misconception"
        reason = "current_session_misconception"
        student_action_expected = False

    diagnostic_question = ""
    if move == "explain" and intent == "explain":
        diagnostic = plan_diagnostic_question(
            question,
            teaching_intent=intent,
            adaptive_state=state,
            session_goal=goal,
        )
        if diagnostic.should_ask:
            move = "ask_diagnostic"
            reason = diagnostic.reason
            student_action_expected = True
            diagnostic_question = diagnostic.question

    prerequisite = prerequisite_decision_mapping(
        plan_prerequisite_review(
            question,
            teaching_intent=intent,
            adaptive_state=state,
            session_goal=goal,
            course_context=course_context,
        )
    )
    if (
        prerequisite["should_review"]
        and move in {
            "explain",
            "ask_diagnostic",
            "check_understanding",
            "repair_misconception",
        }
    ):
        move = "review_prerequisite"
        reason = prerequisite["reason"]
        student_action_expected = False
        diagnostic_question = ""

    practice = practice_sequence_mapping(
        plan_practice_sequence(
            question,
            teaching_intent=intent,
            adaptive_state=state,
            teaching_policy=teaching_policy,
        )
    )
    if move == "review_prerequisite":
        practice = practice_sequence_mapping({"active": False})
    elif (
        practice["active"]
        and intent == "quiz_answer"
        and _clean(state.get("pending_question_kind"), 40).casefold()
        == "practice"
    ):
        move = "practice"
        reason = "adaptive_practice_answer"
        student_action_expected = True

    return TeachingPlan(
        next_move=move,
        reason=reason,
        goal=goal["goal"],
        goal_status=goal["status"],
        student_action_expected=student_action_expected,
        diagnostic_question=diagnostic_question,
        target_concept=prerequisite["target_concept"],
        prerequisite_concept=prerequisite["prerequisite_concept"],
        prerequisite_reason=prerequisite["reason"],
        target_topic_id=prerequisite["target_topic_id"],
        prerequisite_topic_id=prerequisite["prerequisite_topic_id"],
        return_to_goal=prerequisite["return_to_goal"],
        practice_active=practice["active"],
        practice_level=practice["level"],
        practice_level_name=practice["level_name"],
        practice_format=practice["format"],
        practice_focus=practice["focus"],
        practice_reason=practice["reason"],
        practice_after_correct_level=practice["after_correct_level"],
        practice_after_partial_level=practice["after_partial_level"],
        practice_after_incorrect_level=practice["after_incorrect_level"],
        practice_after_unclear_level=practice["after_unclear_level"],
    )


def teaching_plan_mapping(plan):
    if isinstance(plan, Mapping):
        move = _clean(plan.get("next_move"), 80)
        if move not in TEACHING_MOVES:
            move = "explain"
        return {
            "next_move": move,
            "reason": _clean(plan.get("reason"), 120),
            "goal": _clean(plan.get("goal"), 360),
            "goal_status": (
                _clean(plan.get("goal_status"), 40).casefold() or "active"
            ),
            "student_action_expected": bool(
                plan.get("student_action_expected", False)
            ),
            "diagnostic_question": _clean(
                plan.get("diagnostic_question"),
                280,
            ),
            "target_concept": _clean(plan.get("target_concept"), 220),
            "prerequisite_concept": _clean(
                plan.get("prerequisite_concept"),
                220,
            ),
            "prerequisite_reason": _clean(
                plan.get("prerequisite_reason"),
                120,
            ),
            "target_topic_id": _clean(plan.get("target_topic_id"), 120),
            "prerequisite_topic_id": _clean(
                plan.get("prerequisite_topic_id"),
                120,
            ),
            "return_to_goal": bool(plan.get("return_to_goal", True)),
            "practice_active": bool(plan.get("practice_active", False)),
            "practice_level": int(plan.get("practice_level") or 3),
            "practice_level_name": _clean(
                plan.get("practice_level_name"),
                80,
            ) or "standard_application",
            "practice_format": _clean(plan.get("practice_format"), 60) or "mixed",
            "practice_focus": _clean(plan.get("practice_focus"), 260),
            "practice_reason": _clean(plan.get("practice_reason"), 120),
            "practice_after_correct_level": int(
                plan.get("practice_after_correct_level") or 4
            ),
            "practice_after_partial_level": int(
                plan.get("practice_after_partial_level") or 3
            ),
            "practice_after_incorrect_level": int(
                plan.get("practice_after_incorrect_level") or 2
            ),
            "practice_after_unclear_level": int(
                plan.get("practice_after_unclear_level") or 2
            ),
            "planned_at": _clean(plan.get("planned_at"), 80),
        }

    return {
        "next_move": plan.next_move,
        "reason": plan.reason,
        "goal": plan.goal,
        "goal_status": plan.goal_status,
        "student_action_expected": bool(plan.student_action_expected),
        "diagnostic_question": _clean(plan.diagnostic_question, 280),
        "target_concept": _clean(plan.target_concept, 220),
        "prerequisite_concept": _clean(plan.prerequisite_concept, 220),
        "prerequisite_reason": _clean(plan.prerequisite_reason, 120),
        "target_topic_id": _clean(plan.target_topic_id, 120),
        "prerequisite_topic_id": _clean(plan.prerequisite_topic_id, 120),
        "return_to_goal": bool(plan.return_to_goal),
        "practice_active": bool(plan.practice_active),
        "practice_level": int(plan.practice_level),
        "practice_level_name": _clean(plan.practice_level_name, 80),
        "practice_format": _clean(plan.practice_format, 60),
        "practice_focus": _clean(plan.practice_focus, 260),
        "practice_reason": _clean(plan.practice_reason, 120),
        "practice_after_correct_level": int(
            plan.practice_after_correct_level
        ),
        "practice_after_partial_level": int(
            plan.practice_after_partial_level
        ),
        "practice_after_incorrect_level": int(
            plan.practice_after_incorrect_level
        ),
        "practice_after_unclear_level": int(
            plan.practice_after_unclear_level
        ),
        "planned_at": "",
    }


def teaching_plan_prompt(plan):
    data = teaching_plan_mapping(plan)
    return "\n".join(
        (
            "next_move={}".format(data["next_move"]),
            "reason={}".format(data["reason"] or "(none)"),
            "student_action_expected={}".format(
                str(data["student_action_expected"]).lower()
            ),
            "diagnostic_question={}".format(
                data["diagnostic_question"] or "(none)"
            ),
            "target_concept={}".format(
                data["target_concept"] or "(none)"
            ),
            "prerequisite_concept={}".format(
                data["prerequisite_concept"] or "(none)"
            ),
            "prerequisite_reason={}".format(
                data["prerequisite_reason"] or "(none)"
            ),
            "return_to_goal={}".format(
                str(data["return_to_goal"]).lower()
            ),
            "practice_active={}".format(
                str(data["practice_active"]).lower()
            ),
            "practice_level={}".format(data["practice_level"]),
            "practice_level_name={}".format(data["practice_level_name"]),
            "practice_format={}".format(data["practice_format"]),
            "practice_focus={}".format(
                data["practice_focus"] or "(none)"
            ),
            "practice_reason={}".format(
                data["practice_reason"] or "(none)"
            ),
        )
    )


def teaching_plan_instruction(plan):
    data = teaching_plan_mapping(plan)
    move = data["next_move"]
    instructions = {
        "explain": (
            "Explain the current question directly in a coherent teaching sequence."
        ),
        "ask_diagnostic": (
            "Ask exactly one short diagnostic question and stop. Do not begin "
            "the explanation yet. Use this question: {}".format(
                data["diagnostic_question"]
                or "Which part is blocking you most?"
            )
        ),
        "give_hint": (
            "Give only the next useful hint; leave meaningful reasoning for the student."
        ),
        "give_example": (
            "Use one concrete example and connect every important step to the idea."
        ),
        "practice": (
            practice_sequence_instruction(
                data,
                answering=(
                    data["reason"] == "adaptive_practice_answer"
                ),
            )
            if data["practice_active"]
            else (
                "Give one suitable practice task and do not reveal the full solution immediately."
            )
        ),
        "quiz": (
            practice_sequence_instruction(data, answering=False)
            if data["practice_active"]
            else "Ask one short question and wait for the student's answer."
        ),
        "check_understanding": (
            (
                "Evaluate the student's answer to the pending Tutor question. "
                + socratic_outcome_instruction()
            )
            if data["reason"] == "pending_socratic_answer"
            else (
                "Evaluate the student's current reasoning before introducing new material."
            )
        ),
        "summarize": (
            "Give a concise learning-oriented recap of the current request."
        ),
        "repair_misconception": (
            "Repair only the current-session misconception that is relevant to the current question, then return to the question."
        ),
        "review_prerequisite": (
            "Repair only the minimum prerequisite needed now: {}. Connect it explicitly "
            "back to the target concept {} and then return to the original session goal. "
            "Do not recursively descend into another prerequisite in the same turn."
        ).format(
            data["prerequisite_concept"] or "the identified prerequisite",
            data["target_concept"] or "the current topic",
        ),
    }
    rows = [
        "The CURRENT QUESTION remains authoritative over this plan.",
        instructions.get(
            move,
            "Teach the current question clearly without changing its subject.",
        ),
        "Treat the session goal as session-local orientation, not proof of mastery or progress.",
        "Do not declare the goal complete in Tutor 2.3.5.",
        "When next_move=ask_diagnostic, ask only the supplied diagnostic question and wait. Do not add a second diagnostic question.",
        "When reason=pending_socratic_answer, respond to the pending question before teaching anything unrelated and ask at most one next pedagogical question.",
        "When next_move=review_prerequisite, teach only the named prerequisite, make the bridge back to the target explicit, and do not open a second prerequisite branch.",
        "When practice_active=true, give at most one task at a time and change difficulty by at most one bounded level from evaluated current-session evidence.",
        "Never describe a practice level as mastery, ability, intelligence, or academic progress.",
    ]
    return " ".join(rows)


def commit_teaching_plan(metadata, plan, *, now):
    payload = dict(metadata or {})
    data = teaching_plan_mapping(plan)
    data["planned_at"] = _clean(now, 80)
    payload[TEACHING_PLAN_KEY] = data
    return payload


def load_teaching_plan(metadata):
    raw = dict(metadata or {}).get(TEACHING_PLAN_KEY)
    if not isinstance(raw, Mapping):
        return teaching_plan_mapping({})
    return teaching_plan_mapping(raw)
