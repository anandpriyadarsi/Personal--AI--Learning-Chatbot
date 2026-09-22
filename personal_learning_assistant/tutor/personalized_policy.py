"""Deterministic personalized teaching policy for ANVAYA Tutor 2.2.4.

The policy changes *how* ANVAYA teaches. It never changes the current question,
declares mastery, or writes academic progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


_NEGATIVE_MEMORY_KINDS = {
    "misconception",
    "recurring_doubt",
    "scaffolding_need",
    "practice_need",
    "clarification_need",
    "calculation_review_need",
    "calculation_risk",
    "weakness",
    "weak_topic",
}

_POSITIVE_MEMORY_KINDS = {
    "demonstrated_strength",
    "verified_calculation_strength",
    "mastered_topic",
}

_NEGATIVE_SIGNAL_KINDS = {
    "misconception",
    "doubt",
    "hint_requested",
    "answer_partial",
    "answer_incorrect",
    "answer_unclear",
    "math_repaired",
    "math_blocked",
}

_POSITIVE_SIGNAL_KINDS = {
    "answer_correct",
    "math_verified",
}


@dataclass(frozen=True)
class PersonalizedTeachingPolicy:
    scaffolding: str = "standard"
    prerequisite_depth: str = "normal"
    explanation_style: str = "balanced"
    practice_difficulty: str = "standard"
    quiz_progression: str = "normal"
    revisit_misconceptions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def _clean(value, limit=280):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def _memory_kind(value):
    clean = _clean(value)
    if not clean:
        return ""
    head = clean.split(":", 1)[0]
    return head.split("/", 1)[0].strip().casefold()


def _mapping(model):
    if isinstance(model, Mapping):
        return dict(model)
    return {
        "learning_memory": tuple(
            getattr(model, "learning_memory", ()) or ()
        ),
        "stable_signals": tuple(
            getattr(model, "stable_signals", ()) or ()
        ),
    }


def build_personalized_teaching_policy(
    persistent_student_model,
    adaptive_state,
    *,
    teaching_intent="",
):
    model = _mapping(persistent_student_model)
    state = dict(adaptive_state or {})
    memory = tuple(model.get("learning_memory") or ())
    stable = tuple(model.get("stable_signals") or ())

    negative_history = 0
    positive_history = 0
    misconception_texts = []
    reasons = []

    for item in memory:
        kind = _memory_kind(item)
        if kind in _NEGATIVE_MEMORY_KINDS:
            negative_history += 1
        if kind in _POSITIVE_MEMORY_KINDS:
            positive_history += 1
        if kind == "misconception":
            text = _clean(item)
            if text and text not in misconception_texts:
                misconception_texts.append(text)

    for signal in stable:
        if not isinstance(signal, Mapping):
            continue
        kind = _clean(signal.get("kind"), 60).casefold()
        if kind in _NEGATIVE_SIGNAL_KINDS:
            negative_history += 1
        if kind in _POSITIVE_SIGNAL_KINDS:
            positive_history += 1
        if kind == "misconception":
            text = _clean(signal.get("text"))
            if text and text not in misconception_texts:
                misconception_texts.append(text)

    answer_status = _clean(state.get("answer_status"), 40).casefold()
    unresolved = _clean(state.get("unresolved_doubt"))
    current_misconception = _clean(state.get("last_misconception"))
    math_status = _clean(
        state.get("last_math_verification"), 40
    ).casefold()

    current_needs_support = bool(
        unresolved
        or current_misconception
        or answer_status in {"partial", "incorrect", "unclear"}
        or math_status in {"repaired", "blocked"}
    )
    current_success = bool(
        answer_status == "correct"
        or math_status == "passed"
    )

    scaffolding = "standard"
    prerequisite_depth = "normal"
    explanation_style = "balanced"
    practice_difficulty = "standard"
    quiz_progression = "normal"

    if current_needs_support:
        scaffolding = "guided"
        prerequisite_depth = "reinforce"
        explanation_style = "intuition_then_steps"
        practice_difficulty = "supported"
        quiz_progression = "slow"
        reasons.append("current_session_needs_support")
    elif negative_history:
        scaffolding = "guided"
        prerequisite_depth = "brief_reinforcement"
        explanation_style = "intuition_then_steps"
        practice_difficulty = "supported"
        quiz_progression = "hold"
        reasons.append("repeated_historical_support_signal")

    if current_success and positive_history and not current_needs_support:
        scaffolding = "light"
        prerequisite_depth = "minimal"
        explanation_style = "concise_then_challenge"
        practice_difficulty = "challenge"
        quiz_progression = "advance"
        reasons.append("current_success_plus_repeated_strength")

    intent = _clean(teaching_intent, 80).casefold()
    if intent in {"hint", "explain_differently"} and scaffolding == "standard":
        scaffolding = "guided"
        explanation_style = "intuition_then_steps"
        reasons.append("current_teaching_intent_requests_support")

    if current_misconception:
        if current_misconception not in misconception_texts:
            misconception_texts.insert(0, current_misconception)

    return PersonalizedTeachingPolicy(
        scaffolding=scaffolding,
        prerequisite_depth=prerequisite_depth,
        explanation_style=explanation_style,
        practice_difficulty=practice_difficulty,
        quiz_progression=quiz_progression,
        revisit_misconceptions=tuple(misconception_texts[:3]),
        reasons=tuple(dict.fromkeys(reasons)),
    )


def teaching_policy_mapping(policy):
    if isinstance(policy, Mapping):
        return {
            "scaffolding": _clean(policy.get("scaffolding"), 40) or "standard",
            "prerequisite_depth": _clean(
                policy.get("prerequisite_depth"), 60
            ) or "normal",
            "explanation_style": _clean(
                policy.get("explanation_style"), 60
            ) or "balanced",
            "practice_difficulty": _clean(
                policy.get("practice_difficulty"), 40
            ) or "standard",
            "quiz_progression": _clean(
                policy.get("quiz_progression"), 40
            ) or "normal",
            "revisit_misconceptions": tuple(
                _clean(item)
                for item in tuple(
                    policy.get("revisit_misconceptions") or ()
                )[:3]
                if _clean(item)
            ),
            "reasons": tuple(
                _clean(item, 100)
                for item in tuple(policy.get("reasons") or ())[:6]
                if _clean(item, 100)
            ),
        }
    return {
        "scaffolding": policy.scaffolding,
        "prerequisite_depth": policy.prerequisite_depth,
        "explanation_style": policy.explanation_style,
        "practice_difficulty": policy.practice_difficulty,
        "quiz_progression": policy.quiz_progression,
        "revisit_misconceptions": tuple(policy.revisit_misconceptions),
        "reasons": tuple(policy.reasons),
    }


def teaching_policy_prompt(policy):
    data = teaching_policy_mapping(policy)
    lines = [
        "scaffolding={}".format(data["scaffolding"]),
        "prerequisite_depth={}".format(data["prerequisite_depth"]),
        "explanation_style={}".format(data["explanation_style"]),
        "practice_difficulty={}".format(data["practice_difficulty"]),
        "quiz_progression={}".format(data["quiz_progression"]),
    ]
    for item in data["revisit_misconceptions"]:
        lines.append("possible_misconception_to_revisit=" + item)
    for item in data["reasons"]:
        lines.append("policy_reason=" + item)
    return "\n".join(lines)


def teaching_policy_instruction(policy):
    data = teaching_policy_mapping(policy)
    rows = [
        "Apply this policy only to HOW you teach the CURRENT QUESTION.",
        "Never replace the current question with an old topic or historical doubt.",
        "Never describe these signals as proof of mastery, weakness, intelligence, or ability.",
    ]

    if data["scaffolding"] == "guided":
        rows.append(
            "Use smaller reasoning steps and check one missing link at a time; "
            "avoid dumping the full solution when a hint or guided attempt is appropriate."
        )
    elif data["scaffolding"] == "light":
        rows.append(
            "Keep scaffolding light and avoid re-explaining prerequisites the student "
            "has just demonstrated successfully unless they ask."
        )

    if data["prerequisite_depth"] == "reinforce":
        rows.append(
            "Reconnect the minimum prerequisite needed before continuing, then return "
            "immediately to the current question."
        )
    elif data["prerequisite_depth"] == "brief_reinforcement":
        rows.append(
            "Give at most one brief prerequisite reminder when directly relevant."
        )
    elif data["prerequisite_depth"] == "minimal":
        rows.append(
            "Do not repeat prerequisite material unless the current answer reveals a gap."
        )

    if data["explanation_style"] == "intuition_then_steps":
        rows.append(
            "Prefer intuition first, then a concrete step-by-step example, then notation."
        )
    elif data["explanation_style"] == "concise_then_challenge":
        rows.append(
            "Be concise on familiar mechanics and spend the saved attention on one deeper "
            "connection, edge case, or challenge."
        )

    if data["practice_difficulty"] == "supported":
        rows.append(
            "For practice, stay at the same difficulty or one step easier until the missing "
            "idea is demonstrated."
        )
    elif data["practice_difficulty"] == "challenge":
        rows.append(
            "For practice, one modest step harder is allowed; do not jump several levels."
        )

    if data["quiz_progression"] == "slow":
        rows.append(
            "During a quiz, do not advance difficulty after partial/incorrect/unclear work; "
            "repair the exact gap first."
        )
    elif data["quiz_progression"] == "hold":
        rows.append(
            "During a quiz, keep the next question near the current level until evidence "
            "in this session supports advancing."
        )
    elif data["quiz_progression"] == "advance":
        rows.append(
            "During a quiz, a modest increase in difficulty is allowed only after the "
            "current answer is correct."
        )

    if data["revisit_misconceptions"]:
        rows.append(
            "Revisit a listed possible misconception only if it is directly relevant to "
            "the current question; otherwise ignore it."
        )

    return " ".join(rows)
