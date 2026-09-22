"""Adaptive conversational state for ANVAYA Tutor 2.1.

The state is deliberately small, explicit, and session-local. It lives inside
tutor_sessions.metadata_json and never writes academic mastery/progress.
"""

from __future__ import annotations

import re
from typing import Mapping

from personal_learning_assistant.tutor.intent import TutorIntent, classify_tutor_intent


STATE_KEY = "adaptive_tutor_state"
STATE_VERSION = 1
_MAX_TEXT = 700


def _clean(value, limit=_MAX_TEXT):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def default_adaptive_state():
    return {
        "version": STATE_VERSION,
        "interaction_count": 0,
        "last_intent": "",
        "last_teaching_move": "",
        "quiz_active": False,
        "awaiting_student_answer": False,
        "pending_question": "",
        "last_student_answer": "",
        "unresolved_doubt": "",
        "answer_status": "unassessed",
    }


def load_adaptive_state(metadata):
    state = default_adaptive_state()
    raw = dict(metadata or {}).get(STATE_KEY)
    if not isinstance(raw, Mapping):
        return state
    state["interaction_count"] = max(0, int(raw.get("interaction_count") or 0))
    state["last_intent"] = _clean(raw.get("last_intent"), 80)
    state["last_teaching_move"] = _clean(raw.get("last_teaching_move"), 80)
    state["quiz_active"] = bool(raw.get("quiz_active", False))
    state["awaiting_student_answer"] = bool(
        raw.get("awaiting_student_answer", False)
    )
    state["pending_question"] = _clean(raw.get("pending_question"))
    state["last_student_answer"] = _clean(raw.get("last_student_answer"))
    state["unresolved_doubt"] = _clean(raw.get("unresolved_doubt"))
    answer_status = _clean(raw.get("answer_status"), 40).casefold()
    if answer_status not in {
        "unassessed",
        "pending",
        "correct",
        "partial",
        "incorrect",
        "unclear",
    }:
        answer_status = "unassessed"
    state["answer_status"] = answer_status
    return state


def adaptive_state_prompt(state):
    clean = load_adaptive_state({STATE_KEY: state})
    rows = [
        "interaction_count={}".format(clean["interaction_count"]),
        "quiz_active={}".format(str(clean["quiz_active"]).lower()),
        "awaiting_student_answer={}".format(
            str(clean["awaiting_student_answer"]).lower()
        ),
        "last_intent={}".format(clean["last_intent"] or "(none)"),
        "answer_status={}".format(clean["answer_status"]),
    ]
    if clean["pending_question"]:
        rows.append("pending_question={}".format(clean["pending_question"]))
    if clean["unresolved_doubt"]:
        rows.append("unresolved_doubt={}".format(clean["unresolved_doubt"]))
    if clean["last_student_answer"]:
        rows.append("last_student_answer={}".format(clean["last_student_answer"]))
    return "\n".join(rows)


def resolve_adaptive_intent(question, state):
    base = classify_tutor_intent(question)
    clean_state = load_adaptive_state({STATE_KEY: state})
    if (
        clean_state["awaiting_student_answer"]
        and clean_state["pending_question"]
        and base.name in {"explain", "verify_reasoning"}
    ):
        return TutorIntent(
            name="quiz_answer",
            instruction=(
                "This message is the student's answer to the pending Tutor question. "
                "Evaluate that answer before teaching anything new. If it is correct, "
                "acknowledge the exact reason it is correct, then ask exactly one suitable "
                "next question. If it is partially correct or incorrect, identify only the "
                "missing or mistaken idea, explain that briefly, then ask one adjusted next "
                "question. Do not restart the topic from the beginning and do not ask more "
                "than one new question."
            ),
        )
    return base


def retrieval_queries(question, state, intent_name):
    clean_question = _clean(question, 1200)
    clean_state = load_adaptive_state({STATE_KEY: state})
    candidates = []

    if intent_name == "quiz_answer" and clean_state["pending_question"]:
        candidates.append(
            _clean(
                clean_state["pending_question"] + " " + clean_question,
                1600,
            )
        )
        candidates.append(clean_state["pending_question"])
    else:
        candidates.append(clean_question)

    if (
        intent_name in {"explain_differently", "hint", "quiz_answer"}
        and clean_state["unresolved_doubt"]
    ):
        candidates.append(clean_state["unresolved_doubt"])

    unique = []
    seen = set()
    for candidate in candidates:
        candidate = _clean(candidate, 1600)
        key = candidate.casefold()
        if candidate and key not in seen:
            unique.append(candidate)
            seen.add(key)
    return tuple(unique[:3]) or (clean_question,)


def _last_question(text):
    clean = str(text or "").strip()
    if not clean:
        return ""
    # Strip simple Markdown noise while preserving mathematical text.
    clean = re.sub(r"[*_\x60#>]+", "", clean)
    matches = re.findall(r"([^?\n]{4,700}\?)", clean)
    if not matches:
        return ""
    return _clean(matches[-1])


def evolve_adaptive_state(
    state,
    *,
    student_message,
    assistant_message,
    teaching_intent,
):
    current = load_adaptive_state({STATE_KEY: state})
    updated = dict(current)
    updated["interaction_count"] = current["interaction_count"] + 1
    updated["last_intent"] = _clean(teaching_intent, 80)
    updated["last_teaching_move"] = _clean(teaching_intent, 80)

    student = _clean(student_message)
    lowered = student.casefold()
    if any(
        marker in lowered
        for marker in (
            "don't understand",
            "do not understand",
            "still confused",
            "i am confused",
            "not clear",
            "doesn't make sense",
            "does not make sense",
        )
    ):
        updated["unresolved_doubt"] = student

    next_question = _last_question(assistant_message)

    if teaching_intent == "quiz":
        updated["quiz_active"] = True
        updated["awaiting_student_answer"] = bool(next_question)
        updated["pending_question"] = next_question
        updated["answer_status"] = "pending" if next_question else "unassessed"
    elif teaching_intent == "quiz_answer":
        updated["quiz_active"] = bool(next_question)
        updated["awaiting_student_answer"] = bool(next_question)
        updated["pending_question"] = next_question
        updated["last_student_answer"] = student
        # 2.1.1 records the answer without inventing a correctness label.
        updated["answer_status"] = "unassessed"
    elif teaching_intent == "hint" and current["quiz_active"]:
        # A hint during a quiz does not consume the pending question.
        updated["quiz_active"] = True
        updated["awaiting_student_answer"] = current["awaiting_student_answer"]
        updated["pending_question"] = current["pending_question"]
        updated["answer_status"] = current["answer_status"]
    else:
        updated["quiz_active"] = False
        updated["awaiting_student_answer"] = False
        updated["pending_question"] = ""
        updated["answer_status"] = "unassessed"

    return updated
