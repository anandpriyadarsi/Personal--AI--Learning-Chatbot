"""Deterministic teaching orchestration for ANVAYA Tutor 2.3.

Tutor 2.3.1 established bounded teaching moves. Tutor 2.3.2 added one bounded
diagnostic question for genuinely ambiguous initial requests. Tutor 2.3.3
continues a pending pedagogical question across turns. Concept dependency
reasoning, practice sequencing, and goal completion remain reserved for later
Tutor 2.3 units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from personal_learning_assistant.tutor.diagnostic_planner import (
    plan_diagnostic_question,
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


def build_teaching_plan(
    question,
    *,
    teaching_intent,
    adaptive_state,
    session_goal,
    teaching_policy=None,
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

    # review_prerequisite and finish_goal remain reserved for later 2.3 units.
    return TeachingPlan(
        next_move=move,
        reason=reason,
        goal=goal["goal"],
        goal_status=goal["status"],
        student_action_expected=student_action_expected,
        diagnostic_question=diagnostic_question,
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
            "planned_at": _clean(plan.get("planned_at"), 80),
        }

    return {
        "next_move": plan.next_move,
        "reason": plan.reason,
        "goal": plan.goal,
        "goal_status": plan.goal_status,
        "student_action_expected": bool(plan.student_action_expected),
        "diagnostic_question": _clean(plan.diagnostic_question, 280),
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
            "Give one suitable practice task and do not reveal the full solution immediately."
        ),
        "quiz": (
            "Ask one short question and wait for the student's answer."
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
    }
    rows = [
        "The CURRENT QUESTION remains authoritative over this plan.",
        instructions.get(
            move,
            "Teach the current question clearly without changing its subject.",
        ),
        "Treat the session goal as session-local orientation, not proof of mastery or progress.",
        "Do not declare the goal complete in Tutor 2.3.3.",
        "When next_move=ask_diagnostic, ask only the supplied diagnostic question and wait. Do not add a second diagnostic question.",
        "When reason=pending_socratic_answer, respond to the pending question before teaching anything unrelated and ask at most one next pedagogical question.",
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
