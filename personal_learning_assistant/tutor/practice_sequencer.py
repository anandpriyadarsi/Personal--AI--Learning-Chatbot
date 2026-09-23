"""Bounded adaptive practice sequencing for ANVAYA Tutor 2.3.5.

Practice difficulty is session-local orchestration state, not mastery. Current
session evidence dominates; Tutor 2.2 personalized policy may choose a starting
bias but may never prove strength or weakness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


MIN_LEVEL = 1
MAX_LEVEL = 5

LEVEL_NAMES = {
    1: "concept_check",
    2: "guided_application",
    3: "standard_application",
    4: "mixed_transfer",
    5: "challenge",
}

PRACTICE_FORMATS = {
    "conceptual",
    "computational",
    "mixed",
    "misconception_targeted",
    "prerequisite_bridge",
}

_EXPLICIT_EASIER = (
    r"\beasier\b",
    r"\beasy\b",
    r"\bbasic\b",
    r"\bsimpler\b",
    r"\bstep down\b",
)
_EXPLICIT_HARDER = (
    r"\bharder\b",
    r"\bhard\b",
    r"\bchallenge\b",
    r"\badvanced\b",
    r"\bstep up\b",
)
_CONCEPTUAL_CUES = (
    r"\bconceptual\b",
    r"\bintuition\b",
    r"\bwithout calculation\b",
    r"\bno calculation\b",
    r"\btheory\b",
)
_COMPUTATIONAL_CUES = (
    r"\bnumerical\b",
    r"\bcomput",
    r"\bcalculate\b",
    r"\bcalculation\b",
    r"\bsolve\b",
    r"\bmatrix\b",
    r"\bpython\b",
    r"\bcode\b",
)


def _clean(value, limit=300):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def clamp_level(value, default=3):
    try:
        level = int(value)
    except (TypeError, ValueError):
        level = int(default)
    return max(MIN_LEVEL, min(MAX_LEVEL, level))


def level_name(level):
    return LEVEL_NAMES[clamp_level(level)]


def next_level_for_status(level, status):
    """Move by at most one practice level from evaluated current evidence."""
    current = clamp_level(level)
    clean = _clean(status, 40).casefold()
    if clean == "correct":
        return clamp_level(current + 1)
    if clean in {"incorrect", "unclear"}:
        return clamp_level(current - 1)
    return current


def _policy_mapping(policy):
    if isinstance(policy, Mapping):
        return dict(policy)
    if policy is None:
        return {}
    return {
        "practice_difficulty": getattr(
            policy,
            "practice_difficulty",
            "standard",
        ),
        "revisit_misconceptions": tuple(
            getattr(policy, "revisit_misconceptions", ()) or ()
        ),
        "reasons": tuple(getattr(policy, "reasons", ()) or ()),
    }


def _explicit_direction(question):
    lowered = _clean(question, 1000).casefold()
    if any(re.search(pattern, lowered) for pattern in _EXPLICIT_EASIER):
        return "easier"
    if any(re.search(pattern, lowered) for pattern in _EXPLICIT_HARDER):
        return "harder"
    return ""


def _requested_format(question):
    lowered = _clean(question, 1000).casefold()
    if any(re.search(pattern, lowered) for pattern in _CONCEPTUAL_CUES):
        return "conceptual"
    if any(re.search(pattern, lowered) for pattern in _COMPUTATIONAL_CUES):
        return "computational"
    return ""


@dataclass(frozen=True)
class PracticeSequence:
    active: bool = False
    level: int = 3
    level_name: str = "standard_application"
    format: str = "mixed"
    focus: str = ""
    reason: str = ""
    after_correct_level: int = 4
    after_partial_level: int = 3
    after_incorrect_level: int = 2
    after_unclear_level: int = 2
    one_task_only: bool = True


def plan_practice_sequence(
    question,
    *,
    teaching_intent,
    adaptive_state,
    teaching_policy=None,
):
    """Plan one bounded practice task or one continuation of a practice loop."""
    intent = _clean(teaching_intent, 80).casefold()
    state = dict(adaptive_state or {})
    policy = _policy_mapping(teaching_policy)

    pending_kind = _clean(state.get("pending_question_kind"), 40).casefold()
    continuing_practice = (
        intent == "quiz_answer"
        and bool(state.get("awaiting_student_answer"))
        and pending_kind == "practice"
    )
    starting_practice = intent in {"practice", "quiz"}

    if not starting_practice and not continuing_practice:
        return PracticeSequence(active=False)

    try:
        raw_existing_level = int(state.get("practice_level") or 0)
    except (TypeError, ValueError):
        raw_existing_level = 0
    existing_level = (
        clamp_level(raw_existing_level)
        if raw_existing_level > 0
        else 0
    )
    if existing_level:
        level = existing_level
        reason = "continue_session_practice_level"
    else:
        difficulty = _clean(
            policy.get("practice_difficulty"),
            40,
        ).casefold()
        if difficulty == "supported":
            level = 2
            reason = "personalized_policy_supported_start"
        elif difficulty == "challenge":
            level = 4
            reason = "personalized_policy_challenge_start"
        else:
            level = 3
            reason = "standard_practice_start"

    direction = _explicit_direction(question)
    if starting_practice and direction == "easier":
        level = clamp_level(level - 1)
        reason = "student_requested_easier"
    elif starting_practice and direction == "harder":
        level = clamp_level(level + 1)
        reason = "student_requested_harder"

    current_outcome = _clean(
        state.get("last_socratic_outcome"),
        40,
    ).casefold()
    current_status = _clean(state.get("answer_status"), 40).casefold()
    current_misconception = _clean(
        state.get("last_misconception"),
        260,
    )

    # Current-session evidence dominates historical policy when starting a new
    # practice sequence.
    if starting_practice and current_status in {"incorrect", "unclear"}:
        level = min(level, 2)
        reason = "current_session_needs_easier_practice"
    elif starting_practice and current_status == "partial":
        level = min(level, 3)
        reason = "current_session_hold_practice_level"
    elif (
        starting_practice
        and current_status == "correct"
        and current_outcome == "advance"
    ):
        level = clamp_level(max(level, 3) + 1)
        reason = "current_session_success_allows_step_up"

    requested_format = _requested_format(question)
    practice_format = requested_format or _clean(
        state.get("practice_format"),
        60,
    ).casefold()
    focus = ""

    if current_misconception and (
        current_status in {"partial", "incorrect", "unclear"}
        or current_outcome in {"clarify", "repair", "unclear"}
    ):
        practice_format = "misconception_targeted"
        focus = current_misconception
        level = min(level, 2)
        reason = "current_misconception_targeted_practice"
    elif (
        _clean(state.get("last_teaching_move"), 80).casefold()
        == "review_prerequisite"
    ):
        practice_format = "prerequisite_bridge"
        focus = "bridge the repaired prerequisite back to the session goal"
        level = min(level, 3)
        reason = "post_prerequisite_bridge_practice"
    elif requested_format:
        reason = "student_requested_{}_practice".format(requested_format)
    elif practice_format not in PRACTICE_FORMATS:
        practice_format = "mixed"

    if continuing_practice:
        reason = "adaptive_practice_answer"

    level = clamp_level(level)
    return PracticeSequence(
        active=True,
        level=level,
        level_name=level_name(level),
        format=practice_format,
        focus=_clean(focus, 260),
        reason=reason,
        after_correct_level=next_level_for_status(level, "correct"),
        after_partial_level=next_level_for_status(level, "partial"),
        after_incorrect_level=next_level_for_status(level, "incorrect"),
        after_unclear_level=next_level_for_status(level, "unclear"),
        one_task_only=True,
    )


def practice_sequence_mapping(sequence):
    if isinstance(sequence, Mapping):
        active = bool(sequence.get("active", False))
        level = clamp_level(sequence.get("level"), default=3)
        fmt = _clean(sequence.get("format"), 60).casefold()
        if fmt not in PRACTICE_FORMATS:
            fmt = "mixed"
        return {
            "active": active,
            "level": level,
            "level_name": level_name(level),
            "format": fmt,
            "focus": _clean(sequence.get("focus"), 260),
            "reason": _clean(sequence.get("reason"), 120),
            "after_correct_level": clamp_level(
                sequence.get("after_correct_level"),
                default=next_level_for_status(level, "correct"),
            ),
            "after_partial_level": clamp_level(
                sequence.get("after_partial_level"),
                default=level,
            ),
            "after_incorrect_level": clamp_level(
                sequence.get("after_incorrect_level"),
                default=next_level_for_status(level, "incorrect"),
            ),
            "after_unclear_level": clamp_level(
                sequence.get("after_unclear_level"),
                default=next_level_for_status(level, "unclear"),
            ),
            "one_task_only": bool(sequence.get("one_task_only", True)),
        }

    return practice_sequence_mapping(
        {
            "active": sequence.active,
            "level": sequence.level,
            "format": sequence.format,
            "focus": sequence.focus,
            "reason": sequence.reason,
            "after_correct_level": sequence.after_correct_level,
            "after_partial_level": sequence.after_partial_level,
            "after_incorrect_level": sequence.after_incorrect_level,
            "after_unclear_level": sequence.after_unclear_level,
            "one_task_only": sequence.one_task_only,
        }
    )


def practice_sequence_prompt(sequence):
    data = practice_sequence_mapping(sequence)
    if not data["active"]:
        return "(inactive)"
    return "\n".join(
        (
            "practice_level={}".format(data["level"]),
            "practice_level_name={}".format(data["level_name"]),
            "practice_format={}".format(data["format"]),
            "practice_focus={}".format(data["focus"] or "(none)"),
            "practice_reason={}".format(data["reason"] or "(none)"),
            "after_correct_level={}".format(data["after_correct_level"]),
            "after_partial_level={}".format(data["after_partial_level"]),
            "after_incorrect_level={}".format(data["after_incorrect_level"]),
            "after_unclear_level={}".format(data["after_unclear_level"]),
            "one_task_only=true",
        )
    )


def practice_sequence_instruction(sequence, *, answering=False):
    data = practice_sequence_mapping(sequence)
    if not data["active"]:
        return ""

    base = (
        "Give at most one practice task at a time. The planned level is {} ({}) "
        "and the format is {}. ".format(
            data["level"],
            data["level_name"].replace("_", " "),
            data["format"].replace("_", " "),
        )
    )
    if data["focus"]:
        base += "Target this current-session focus: {}. ".format(
            data["focus"]
        )

    if answering:
        base += (
            "First evaluate the student's current answer using the hidden evaluation "
            "protocol. Then adapt the one next task by exactly this bounded rule: "
            "correct -> level {}; partial -> level {}; incorrect -> level {}; "
            "unclear -> level {}. Give brief feedback, then at most one next task. "
            "Do not reveal a full worked solution unless the student asks for it."
        ).format(
            data["after_correct_level"],
            data["after_partial_level"],
            data["after_incorrect_level"],
            data["after_unclear_level"],
        )
    else:
        base += (
            "Ask only the practice task and wait for the student's attempt. Do not "
            "supply the full solution in the same turn."
        )
    return base
