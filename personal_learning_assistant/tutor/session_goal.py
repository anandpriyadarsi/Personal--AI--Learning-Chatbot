"""Session-local learning goals for ANVAYA Tutor 2.3.1.

Goals live only in tutor_sessions.metadata_json. They are orchestration context,
not mastery/progress records.
"""

from __future__ import annotations

import re
from typing import Mapping


SESSION_GOAL_KEY = "tutor23_session_goal"
GOAL_VERSION = 1
GOAL_STATUSES = ("active", "likely_met", "unresolved")
_MAX_GOAL = 360

_SHIFT_CUES = (
    r"\bnow\b",
    r"\binstead\b",
    r"\bmove (?:on|to)\b",
    r"\bswitch (?:to|topic)\b",
    r"\bnew topic\b",
    r"\bdo not continue\b",
    r"\bdon't continue\b",
)

_STOPWORDS = {
    "about", "again", "also", "and", "answer", "because", "but", "can",
    "could", "do", "does", "explain", "for", "from", "give", "how", "into",
    "just", "me", "more", "now", "of", "on", "only", "please", "show",
    "that", "the", "then", "this", "to", "use", "what", "when", "which",
    "why", "with", "you", "your",
}


def _clean(value, limit=_MAX_GOAL):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def default_session_goal():
    return {
        "version": GOAL_VERSION,
        "goal": "",
        "status": "active",
        "goal_evidence": (),
        "source": "",
        "created_at": "",
        "updated_at": "",
    }


def load_session_goal(metadata):
    state = default_session_goal()
    raw = dict(metadata or {}).get(SESSION_GOAL_KEY)
    if not isinstance(raw, Mapping):
        return state

    goal = _clean(raw.get("goal"))
    status = _clean(raw.get("status"), 40).casefold()
    if status not in GOAL_STATUSES:
        status = "active"

    evidence = []
    for item in tuple(raw.get("goal_evidence") or ())[:12]:
        clean = _clean(item, 240)
        if clean and clean not in evidence:
            evidence.append(clean)

    state.update(
        {
            "goal": goal,
            "status": status,
            "goal_evidence": tuple(evidence),
            "source": _clean(raw.get("source"), 40),
            "created_at": _clean(raw.get("created_at"), 80),
            "updated_at": _clean(raw.get("updated_at"), 80),
        }
    )
    return state


def _subject_text(question):
    clean = _clean(question)
    if not clean:
        return ""

    patterns = (
        r"^(?:please\s+)?(?:can|could|would)\s+you\s+",
        r"^(?:please\s+)?",
        r"^(?:now\s+)?(?:explain|teach me|show me|tell me about)\s+",
        r"^(?:give me\s+)?(?:one\s+|a\s+)?hint\s+(?:for|about|on)?\s*",
        r"^(?:quiz me|test me)\s+(?:on|about)?\s*",
        r"^(?:give me\s+)?(?:a\s+|one\s+)?practice\s+(?:problem|question)?\s*(?:on|about|for)?\s*",
        r"^(?:summarize|summarise|recap)\s+",
    )
    subject = clean
    for pattern in patterns:
        replaced = re.sub(pattern, "", subject, flags=re.IGNORECASE).strip()
        if replaced != subject:
            subject = replaced
    subject = subject.rstrip(" .?!")
    return _clean(subject or clean, 300)


def infer_session_goal(question, teaching_intent=""):
    subject = _subject_text(question)
    if not subject:
        return ""

    intent = _clean(teaching_intent, 60).casefold()
    if intent == "hint":
        return _clean("Work through {} with hints".format(subject))
    if intent == "quiz":
        return _clean("Check understanding of {}".format(subject))
    if intent == "practice":
        return _clean("Practice {}".format(subject))
    if intent == "summary":
        return _clean("Review the key ideas in {}".format(subject))
    if intent == "example":
        return _clean("Understand {} through an example".format(subject))
    if intent == "verify_reasoning":
        return _clean("Check and repair the reasoning in: {}".format(subject))
    if intent == "explain_differently":
        return _clean("Understand {} using a different explanation".format(subject))
    if intent == "guidance":
        return _clean("Decide the next useful learning step for {}".format(subject))
    return _clean("Understand {}".format(subject))


def _terms(value):
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_+\-^]*", str(value or ""))
        if len(token) > 2 and token.casefold() not in _STOPWORDS
    }


def is_explicit_goal_shift(question, current_goal):
    clean = _clean(question, 1000)
    goal = _clean(current_goal)
    if not clean or not goal:
        return False
    lowered = clean.casefold()
    if not any(re.search(pattern, lowered) for pattern in _SHIFT_CUES):
        return False

    question_terms = _terms(clean)
    goal_terms = _terms(goal)
    if len(question_terms) < 2 or not goal_terms:
        return False
    return len(question_terms & goal_terms) == 0


def resolve_session_goal(
    question,
    metadata,
    *,
    teaching_intent="",
):
    current = load_session_goal(metadata)
    inferred = infer_session_goal(question, teaching_intent)
    if not current["goal"]:
        next_state = dict(current)
        next_state["goal"] = inferred
        next_state["source"] = "inferred"
        return next_state

    if is_explicit_goal_shift(question, current["goal"]):
        next_state = default_session_goal()
        next_state["goal"] = inferred
        next_state["source"] = "topic_shift"
        return next_state

    return current


def session_goal_mapping(goal_state):
    if isinstance(goal_state, Mapping):
        return load_session_goal({SESSION_GOAL_KEY: goal_state})
    return default_session_goal()


def session_goal_prompt(goal_state):
    goal = session_goal_mapping(goal_state)
    rows = [
        "goal={}".format(goal["goal"] or "(not established)"),
        "status={}".format(goal["status"]),
    ]
    if goal["goal_evidence"]:
        rows.append(
            "goal_evidence={}".format(" | ".join(goal["goal_evidence"]))
        )
    if goal["source"]:
        rows.append("goal_source={}".format(goal["source"]))
    return "\n".join(rows)


def commit_session_goal(metadata, goal_state, *, now):
    """Persist a resolved goal without turning it into academic progress."""
    payload = dict(metadata or {})
    existing = load_session_goal(payload)
    resolved = session_goal_mapping(goal_state)
    timestamp = _clean(now, 80)

    if not resolved["goal"]:
        return payload

    changed_goal = existing["goal"] != resolved["goal"]
    changed_state = (
        changed_goal
        or existing["status"] != resolved["status"]
        or tuple(existing["goal_evidence"]) != tuple(resolved["goal_evidence"])
    )

    committed = dict(resolved)
    if changed_goal or not existing["created_at"]:
        committed["created_at"] = timestamp
    else:
        committed["created_at"] = existing["created_at"]

    if changed_state or not existing["updated_at"]:
        committed["updated_at"] = timestamp
    else:
        committed["updated_at"] = existing["updated_at"]

    payload[SESSION_GOAL_KEY] = committed
    return payload
