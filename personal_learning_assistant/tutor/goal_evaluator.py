"""Session-local understanding / exit checks for ANVAYA Tutor 2.3.6.

This module evaluates only the current Tutor session goal. A likely-met status
is not mastery, academic progress, a grade, or long-term learning memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from personal_learning_assistant.tutor.session_goal import (
    session_goal_mapping,
)


_UNRESOLVED_CUES = (
    r"\bi (?:still )?(?:do not|don't) understand\b",
    r"\bi(?:'m| am) still confused\b",
    r"\bi(?:'m| am) confused\b",
    r"\bnot clear\b",
    r"\bdoes(?:n't| not) make sense\b",
    r"\bi(?:'m| am) not sure\b",
    r"\bi still (?:do not|don't) get\b",
)

_UNDERSTANDING_CUES = (
    r"\bi understand(?: it| this| now)?\b",
    r"\bi get it(?: now)?\b",
    r"\bi got it\b",
    r"\bgot it\b",
    r"\bthat makes sense(?: now)?\b",
    r"\bit makes sense(?: now)?\b",
    r"\bthat(?:'s| is) clear(?: now)?\b",
    r"\bi think i understand\b",
)

_EXIT_CHECK_REQUESTS = (
    r"\bcheck (?:if|whether) i understand\b",
    r"\bcheck my understanding\b",
    r"\btest my understanding\b",
    r"\bcan (?:we|i) finish\b",
    r"\bam i ready to move on\b",
    r"\bcan (?:we|i) move on\b",
    r"\bdo i understand (?:this|it)\b",
)

_MAX_EVIDENCE = 12


def _clean(value, limit=360):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def _matches_any(value, patterns):
    clean = _clean(value, 1200).casefold()
    return any(re.search(pattern, clean) for pattern in patterns)


def has_unresolved_cue(question):
    return _matches_any(question, _UNRESOLVED_CUES)


def has_understanding_cue(question):
    return _matches_any(question, _UNDERSTANDING_CUES)


def is_exit_check_request(question):
    return _matches_any(question, _EXIT_CHECK_REQUESTS)


def _append_evidence(goal, value):
    result = dict(session_goal_mapping(goal))
    evidence = list(result.get("goal_evidence") or ())
    clean = _clean(value, 240)
    if clean and clean not in evidence:
        evidence.append(clean)
    result["goal_evidence"] = tuple(evidence[-_MAX_EVIDENCE:])
    return result


def contextualize_goal_for_turn(question, goal_state):
    """Reflect explicit current-session confusion without inferring mastery."""
    goal = dict(session_goal_mapping(goal_state))
    if not goal["goal"]:
        return goal
    if not has_unresolved_cue(question):
        return goal

    goal["status"] = "unresolved"
    return _append_evidence(
        goal,
        "student_reported_unresolved: {}".format(_clean(question, 180)),
    )


def exit_check_question(goal_state):
    goal = session_goal_mapping(goal_state)
    goal_text = _clean(goal.get("goal"), 280)
    if not goal_text:
        return ""
    return _clean(
        "Before we close this session goal, explain in your own words the "
        "key idea or method you would use for: {}?".format(goal_text),
        500,
    )


@dataclass(frozen=True)
class ExitCheckDecision:
    should_ask: bool = False
    reason: str = ""
    question: str = ""


def plan_exit_check(
    question,
    *,
    teaching_intent,
    adaptive_state,
    session_goal,
):
    """Choose one bounded exit check only when the current request warrants it."""
    state = dict(adaptive_state or {})
    goal = session_goal_mapping(session_goal)

    if not goal["goal"]:
        return ExitCheckDecision()

    if (
        bool(state.get("awaiting_student_answer"))
        and _clean(state.get("pending_question"), 500)
    ):
        return ExitCheckDecision()

    if has_unresolved_cue(question):
        return ExitCheckDecision()

    if goal["status"] == "likely_met":
        return ExitCheckDecision()

    explicit_request = is_exit_check_request(question)
    understanding_claim = has_understanding_cue(question)

    if not explicit_request and not understanding_claim:
        return ExitCheckDecision()

    intent = _clean(teaching_intent, 80).casefold()
    if intent in {
        "hint",
        "practice",
        "quiz",
        "example",
        "summary",
        "explain_differently",
    } and not explicit_request:
        return ExitCheckDecision()

    question_text = exit_check_question(goal)
    if not question_text:
        return ExitCheckDecision()

    return ExitCheckDecision(
        should_ask=True,
        reason=(
            "explicit_exit_check_requested"
            if explicit_request
            else "student_reports_understanding"
        ),
        question=question_text,
    )


def evaluate_goal_after_turn(
    goal_state,
    *,
    teaching_plan,
    adaptive_state,
):
    """Update goal status only from a completed Tutor 2.3.6 exit-check answer."""
    goal = dict(session_goal_mapping(goal_state))
    plan = dict(teaching_plan or {})
    state = dict(adaptive_state or {})

    if not goal["goal"]:
        return goal

    if _clean(plan.get("reason"), 120) != "pending_exit_check_answer":
        return goal

    status = _clean(state.get("answer_status"), 40).casefold()
    math_status = _clean(
        state.get("last_math_verification"),
        40,
    ).casefold()
    misconception = _clean(state.get("last_misconception"), 220)
    reason = _clean(state.get("last_evaluation_reason"), 180)

    if (
        status == "correct"
        and math_status != "blocked"
        and not misconception
    ):
        goal["status"] = "likely_met"
        return _append_evidence(
            goal,
            "exit_check_correct{}".format(
                ": {}".format(reason) if reason else ""
            ),
        )

    if status in {"partial", "incorrect", "unclear"}:
        goal["status"] = "unresolved"
        label = "exit_check_{}".format(status)
    elif math_status == "blocked":
        goal["status"] = "unresolved"
        label = "exit_check_math_blocked"
    elif misconception:
        goal["status"] = "unresolved"
        label = "exit_check_misconception"
    else:
        # Missing/invalid evaluation is not evidence of understanding.
        goal["status"] = "active"
        label = "exit_check_unassessed"

    detail = reason or misconception
    return _append_evidence(
        goal,
        "{}{}".format(
            label,
            ": {}".format(detail) if detail else "",
        ),
    )
