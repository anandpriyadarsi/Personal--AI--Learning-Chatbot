"""Adaptive conversational state for ANVAYA Tutor 2.1.

The state is deliberately small, explicit, and session-local. It lives inside
tutor_sessions.metadata_json and never writes academic mastery/progress.
"""

from __future__ import annotations

import json
import re
from typing import Mapping

from personal_learning_assistant.tutor.intent import TutorIntent, classify_tutor_intent


STATE_KEY = "adaptive_tutor_state"
STATE_VERSION = 3
_MAX_TEXT = 700
_EVAL_PATTERN = re.compile(
    r"^\s*<!--ANVAYA_EVAL\s+(\{.*?\})\s*-->\s*",
    re.DOTALL,
)


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
        "last_evaluation_reason": "",
        "last_misconception": "",
        "last_math_verification": "not_applicable",
        "last_math_claims_checked": 0,
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
    state["last_evaluation_reason"] = _clean(
        raw.get("last_evaluation_reason"), 240
    )
    state["last_misconception"] = _clean(
        raw.get("last_misconception"), 240
    )
    math_status = _clean(
        raw.get("last_math_verification"), 40
    ).casefold()
    if math_status not in {
        "not_applicable",
        "passed",
        "repaired",
        "blocked",
    }:
        math_status = "not_applicable"
    state["last_math_verification"] = math_status
    try:
        checked = int(raw.get("last_math_claims_checked") or 0)
    except (TypeError, ValueError):
        checked = 0
    state["last_math_claims_checked"] = max(0, checked)
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
    if clean["last_evaluation_reason"]:
        rows.append(
            "last_evaluation_reason={}".format(clean["last_evaluation_reason"])
        )
    if clean["last_misconception"]:
        rows.append(
            "last_misconception={}".format(clean["last_misconception"])
        )
    if clean["last_math_verification"] != "not_applicable":
        rows.append(
            "last_math_verification={}".format(
                clean["last_math_verification"]
            )
        )
        rows.append(
            "last_math_claims_checked={}".format(
                clean["last_math_claims_checked"]
            )
        )
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


def evaluation_protocol():
    return (
        "For this quiz-answer turn, begin your raw response with exactly one hidden "
        "machine-readable line in this format: "
        '<!--ANVAYA_EVAL {"status":"STATUS",'
        '"reason":"brief reason","misconception":"brief misconception or empty"}--> '
        "Replace STATUS with exactly one of: correct, partial, incorrect, unclear. "
        "Do not output the option list itself. Then write the normal student-facing Tutor "
        "reply. The hidden marker is for "
        "ANVAYA only and will be removed before display. Classify conservatively: use "
        "'correct' only when the essential reasoning is correct, 'partial' when the core "
        "idea is present but incomplete, 'incorrect' for a substantive mathematical or "
        "conceptual error, and 'unclear' when the answer is too ambiguous to judge."
    )


def extract_answer_evaluation(content):
    raw = str(content or "")
    match = _EVAL_PATTERN.match(raw)
    fallback = {
        "status": "unclear",
        "reason": "",
        "misconception": "",
        "present": False,
    }
    if match is None:
        return raw.strip(), fallback
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw[match.end():].strip(), fallback
    if not isinstance(payload, dict):
        return raw[match.end():].strip(), fallback

    status = _clean(payload.get("status"), 40).casefold()
    if status not in {"correct", "partial", "incorrect", "unclear"}:
        status = "unclear"
    evaluation = {
        "status": status,
        "reason": _clean(payload.get("reason"), 240),
        "misconception": _clean(payload.get("misconception"), 240),
        "present": True,
    }
    return raw[match.end():].strip(), evaluation


def mark_math_blocked(
    state,
    *,
    student_message,
    teaching_intent,
    checked_claims=0,
):
    current = load_adaptive_state({STATE_KEY: state})
    updated = dict(current)
    updated["interaction_count"] = current["interaction_count"] + 1
    updated["last_intent"] = _clean(teaching_intent, 80)
    updated["last_teaching_move"] = "correctness_block"
    updated["last_math_verification"] = "blocked"
    updated["last_math_claims_checked"] = max(0, int(checked_claims or 0))
    if teaching_intent == "quiz_answer":
        updated["last_student_answer"] = _clean(student_message)
        updated["answer_status"] = "unclear"
        # Preserve the existing pending question so the student can retry.
        updated["quiz_active"] = current["quiz_active"]
        updated["awaiting_student_answer"] = current["awaiting_student_answer"]
        updated["pending_question"] = current["pending_question"]
    return updated


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
    answer_evaluation=None,
    math_verification=None,
    math_repaired=False,
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
        evaluation = dict(answer_evaluation or {})
        status = _clean(evaluation.get("status"), 40).casefold()
        if status not in {"correct", "partial", "incorrect", "unclear"}:
            status = "unclear"
        updated["answer_status"] = status
        updated["last_evaluation_reason"] = _clean(
            evaluation.get("reason"), 240
        )
        updated["last_misconception"] = _clean(
            evaluation.get("misconception"), 240
        )
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

    if math_verification is not None and bool(
        getattr(math_verification, "applicable", False)
    ):
        updated["last_math_verification"] = (
            "repaired"
            if math_repaired and bool(getattr(math_verification, "passed", False))
            else (
                "passed"
                if bool(getattr(math_verification, "passed", False))
                else "blocked"
            )
        )
        updated["last_math_claims_checked"] = max(
            0,
            int(getattr(math_verification, "checked_claims", 0) or 0),
        )
    else:
        updated["last_math_verification"] = "not_applicable"
        updated["last_math_claims_checked"] = 0

    return updated
