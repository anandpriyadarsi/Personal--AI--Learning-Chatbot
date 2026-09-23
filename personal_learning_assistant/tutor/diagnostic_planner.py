"""Bounded diagnostic-question planning for ANVAYA Tutor 2.3.2.

Tutor 2.3.2 may ask one deterministic diagnostic question when the student's
initial gap is genuinely unclear. Tracking a pending diagnostic exchange and
interpreting the student's reply belong to Tutor 2.3.3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


_MAX_QUESTION = 280

_EXPLICIT_TEACHING_INTENTS = {
    "hint",
    "quiz",
    "verify_reasoning",
    "follow_up_reference",
    "example",
    "practice",
    "summary",
    "guidance",
    "explain_differently",
    "quiz_answer",
}

_DIRECT_EXPLANATION_CUES = (
    r"\bexplain\s+(?:why|how|what|when|where)\b",
    r"\bwhy\b",
    r"\bhow\b",
    r"\bwhat (?:is|are|does|happens)\b",
    r"\bdifference between\b",
    r"\bcompare\b",
    r"\bderive\b",
    r"\bprove\b",
)

_AMBIGUOUS_GAP_CUES = (
    r"\bi (?:do not|don't) understand\b",
    r"\bi(?:'m| am) confused\b",
    r"\bconfused about\b",
    r"\bhelp me with\b",
    r"\bstruggling with\b",
    r"\bstuck (?:on|with)\b",
    r"\bnot clear\b",
    r"\bunclear\b",
)

_BARE_REQUEST_PREFIXES = (
    r"^(?:please\s+)?(?:teach me|help me with|tell me about)\b",
)


def _clean(value, limit=_MAX_QUESTION):
    return " ".join(str(value or "").strip().split())[: int(limit)]


@dataclass(frozen=True)
class DiagnosticDecision:
    should_ask: bool
    reason: str
    question: str = ""


def _is_initial_turn(adaptive_state):
    state = dict(adaptive_state or {})
    try:
        return int(state.get("interaction_count", 0) or 0) <= 0
    except (TypeError, ValueError):
        return True


def _has_known_current_gap(adaptive_state):
    state = dict(adaptive_state or {})
    return bool(
        _clean(state.get("last_misconception"), 240)
        or _clean(state.get("unresolved_doubt"), 240)
    )


def _subject_from_goal(session_goal):
    goal = dict(session_goal or {})
    text = _clean(goal.get("goal"), 220)
    if not text:
        return "this topic"
    lowered = text.casefold()
    prefixes = (
        "understand ",
        "work through ",
        "check understanding of ",
        "practice ",
        "review the key ideas in ",
        "decide the next useful learning step for ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    text = re.sub(r"\s+with hints$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+through an example$", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\s+using a different explanation$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return _clean(text, 180) or "this topic"


def _diagnostic_question(session_goal):
    subject = _subject_from_goal(session_goal)
    return _clean(
        "For {}, which part is blocking you most: the core idea, how the "
        "steps work, or why the method works?".format(subject),
        _MAX_QUESTION,
    )


def plan_diagnostic_question(
    question,
    *,
    teaching_intent,
    adaptive_state,
    session_goal,
):
    """Return one bounded diagnostic decision without mutating Tutor state."""
    clean = _clean(question, 1000)
    lowered = clean.casefold()
    intent = _clean(teaching_intent, 80).casefold() or "explain"

    if not clean:
        return DiagnosticDecision(False, "empty_question")

    if intent in _EXPLICIT_TEACHING_INTENTS:
        return DiagnosticDecision(False, "explicit_teaching_request")

    if _has_known_current_gap(adaptive_state):
        return DiagnosticDecision(False, "current_gap_already_known")

    # 2.3.2 asks automatically only on an initial ambiguous request. Tutor
    # 2.3.3 will add pending-question continuity for later turns.
    if not _is_initial_turn(adaptive_state):
        return DiagnosticDecision(False, "not_initial_ambiguous_request")

    if any(re.search(pattern, lowered) for pattern in _DIRECT_EXPLANATION_CUES):
        return DiagnosticDecision(False, "specific_question_already_clear")

    ambiguous = any(
        re.search(pattern, lowered) for pattern in _AMBIGUOUS_GAP_CUES
    )
    bare_request = any(
        re.search(pattern, lowered) for pattern in _BARE_REQUEST_PREFIXES
    )
    word_count = len(re.findall(r"\b[\w^+-]+\b", clean))

    if not ambiguous and not bare_request and word_count > 5:
        return DiagnosticDecision(False, "enough_request_detail")

    if not ambiguous and not bare_request and word_count > 3:
        return DiagnosticDecision(False, "no_clear_diagnostic_need")

    return DiagnosticDecision(
        True,
        "initial_gap_unclear",
        _diagnostic_question(session_goal),
    )


def diagnostic_decision_mapping(decision):
    if isinstance(decision, Mapping):
        return {
            "should_ask": bool(decision.get("should_ask", False)),
            "reason": _clean(decision.get("reason"), 120),
            "question": _clean(decision.get("question"), _MAX_QUESTION),
        }
    return {
        "should_ask": bool(decision.should_ask),
        "reason": _clean(decision.reason, 120),
        "question": _clean(decision.question, _MAX_QUESTION),
    }
