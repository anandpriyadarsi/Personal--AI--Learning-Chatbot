"""Adaptive conversational state for ANVAYA Tutor 2.1.

The state is deliberately small, explicit, and session-local. It lives inside
tutor_sessions.metadata_json and never writes academic mastery/progress.
"""

from __future__ import annotations

import json
import re
from typing import Mapping

from personal_learning_assistant.tutor.intent import TutorIntent, classify_tutor_intent
from personal_learning_assistant.tutor.practice_sequencer import (
    clamp_level,
    next_level_for_status,
)
from personal_learning_assistant.tutor.socratic_loop import (
    normalize_pending_kind,
    normalize_socratic_outcome,
    outcome_from_evaluation,
)


STATE_KEY = "adaptive_tutor_state"
STATE_VERSION = 7
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
        "pending_question_kind": "",
        "last_student_answer": "",
        "last_socratic_outcome": "",
        "socratic_step_count": 0,
        "practice_active": False,
        "practice_level": 0,
        "practice_step_count": 0,
        "practice_format": "",
        "practice_focus": "",
        "exit_check_count": 0,
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
    state["pending_question_kind"] = normalize_pending_kind(
        raw.get("pending_question_kind")
    )
    state["last_student_answer"] = _clean(raw.get("last_student_answer"))
    state["last_socratic_outcome"] = normalize_socratic_outcome(
        raw.get("last_socratic_outcome")
    )
    try:
        socratic_steps = int(raw.get("socratic_step_count") or 0)
    except (TypeError, ValueError):
        socratic_steps = 0
    state["socratic_step_count"] = max(0, socratic_steps)
    state["practice_active"] = bool(raw.get("practice_active", False))
    try:
        raw_practice_level = int(raw.get("practice_level") or 0)
    except (TypeError, ValueError):
        raw_practice_level = 0
    state["practice_level"] = (
        clamp_level(raw_practice_level)
        if raw_practice_level > 0
        else 0
    )
    try:
        practice_steps = int(raw.get("practice_step_count") or 0)
    except (TypeError, ValueError):
        practice_steps = 0
    state["practice_step_count"] = max(0, practice_steps)
    practice_format = _clean(raw.get("practice_format"), 60).casefold()
    if practice_format not in {
        "",
        "conceptual",
        "computational",
        "mixed",
        "misconception_targeted",
        "prerequisite_bridge",
    }:
        practice_format = ""
    state["practice_format"] = practice_format
    state["practice_focus"] = _clean(raw.get("practice_focus"), 260)
    try:
        exit_checks = int(raw.get("exit_check_count") or 0)
    except (TypeError, ValueError):
        exit_checks = 0
    state["exit_check_count"] = max(0, exit_checks)
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
        if clean["pending_question_kind"]:
            rows.append(
                "pending_question_kind={}".format(
                    clean["pending_question_kind"]
                )
            )
    if clean["last_socratic_outcome"]:
        rows.append(
            "last_socratic_outcome={}".format(
                clean["last_socratic_outcome"]
            )
        )
    if clean["socratic_step_count"]:
        rows.append(
            "socratic_step_count={}".format(
                clean["socratic_step_count"]
            )
        )
    if clean["practice_level"]:
        rows.append(
            "practice_active={}".format(
                str(clean["practice_active"]).lower()
            )
        )
        rows.append(
            "practice_level={}".format(clean["practice_level"])
        )
        rows.append(
            "practice_step_count={}".format(
                clean["practice_step_count"]
            )
        )
        if clean["practice_format"]:
            rows.append(
                "practice_format={}".format(clean["practice_format"])
            )
        if clean["practice_focus"]:
            rows.append(
                "practice_focus={}".format(clean["practice_focus"])
            )
    if clean["exit_check_count"]:
        rows.append(
            "exit_check_count={}".format(clean["exit_check_count"])
        )
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


_TOPIC_STOPWORDS = {
    "about", "again", "also", "and", "answer", "because", "but", "can",
    "could", "does", "explain", "for", "from", "give", "how", "into", "just",
    "me", "more", "now", "only", "please", "show", "that", "the", "then",
    "this", "use", "what", "when", "which", "why", "with", "you", "your",
}

_TOPIC_SHIFT_CUES = (
    r"\bnow\b",
    r"\binstead\b",
    r"\bmove (?:on|to)\b",
    r"\bnew topic\b",
    r"\bexplain\b",
    r"\bteach me\b",
    r"\btell me about\b",
    r"\bcompute\b",
    r"\bcalculate\b",
    r"\bfactori[sz](?:e|ation)\b",
)

_CONTINUITY_PHRASES = (
    r"\bexplain it\b",
    r"\banother way\b",
    r"\bthe same (?:thing|idea|question)\b",
    r"\bthis again\b",
)

_PENDING_OVERRIDE_CUES = (
    r"\bjust explain\b",
    r"\bexplain (?:it|this|the topic)\b",
    r"\bskip (?:the )?(?:question|diagnostic|quiz)\b",
    r"\bdo not ask\b",
    r"\bdon't ask\b",
    r"\bgive me (?:the )?(?:answer|explanation)\b",
)


def is_pending_override_request(question, state):
    current = load_adaptive_state({STATE_KEY: state})
    if not (
        current["awaiting_student_answer"]
        and current["pending_question"]
    ):
        return False
    lowered = _clean(question, 1200).casefold()
    return any(
        re.search(pattern, lowered)
        for pattern in _PENDING_OVERRIDE_CUES
    )


def _clear_pending_question(state):
    updated = dict(state)
    updated["quiz_active"] = False
    updated["awaiting_student_answer"] = False
    updated["pending_question"] = ""
    updated["pending_question_kind"] = ""
    updated["practice_active"] = False
    if updated["answer_status"] == "pending":
        updated["answer_status"] = "unassessed"
    return updated


def _topic_terms(value):
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_+\-^]*", str(value or ""))
        if len(token) > 2 and token.casefold() not in _TOPIC_STOPWORDS
    }


def is_explicit_topic_shift(question, state):
    """Detect an explicit new-topic request without treating short quiz answers as shifts."""
    clean = _clean(question, 1200)
    lowered = clean.casefold()
    if any(re.search(pattern, lowered) for pattern in _CONTINUITY_PHRASES):
        return False
    if not any(re.search(pattern, lowered) for pattern in _TOPIC_SHIFT_CUES):
        return False

    current = load_adaptive_state({STATE_KEY: state})
    anchor = (
        current["pending_question"]
        if current["awaiting_student_answer"] and current["pending_question"]
        else current["unresolved_doubt"] or current["last_misconception"]
    )
    if not anchor:
        return False

    question_terms = _topic_terms(clean)
    anchor_terms = _topic_terms(anchor)
    if len(question_terms) < 2 or not anchor_terms:
        return False

    return len(question_terms & anchor_terms) == 0


def contextualize_adaptive_state(question, state):
    """Drop stale conversational anchors on explicit student override/topic shift."""
    current = load_adaptive_state({STATE_KEY: state})

    if is_pending_override_request(question, current):
        return _clear_pending_question(current)

    if not is_explicit_topic_shift(question, current):
        return current

    updated = _clear_pending_question(current)
    updated["unresolved_doubt"] = ""
    updated["answer_status"] = "unassessed"
    updated["last_evaluation_reason"] = ""
    updated["last_misconception"] = ""
    updated["last_socratic_outcome"] = ""
    updated["practice_active"] = False
    updated["practice_level"] = 0
    updated["practice_step_count"] = 0
    updated["practice_format"] = ""
    updated["practice_focus"] = ""
    return updated


def resolve_adaptive_intent(question, state):
    base = classify_tutor_intent(question)
    raw_state = load_adaptive_state({STATE_KEY: state})
    if (
        is_pending_override_request(question, raw_state)
        or is_explicit_topic_shift(question, raw_state)
    ):
        return base
    clean_state = contextualize_adaptive_state(question, raw_state)
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
        "For this answer to a pending Tutor question, begin your raw response with exactly one hidden "
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


def _last_practice_task(text):
    question = _last_question(text)
    if question:
        return question
    clean = str(text or "").strip()
    if not clean:
        return ""
    clean = re.sub(r"[*_\x60#>]+", "", clean)
    blocks = [
        _clean(item, 700)
        for item in re.split(r"\n\s*\n|\n", clean)
        if _clean(item, 700)
    ]
    return blocks[-1] if blocks else ""


def evolve_adaptive_state(
    state,
    *,
    student_message,
    assistant_message,
    teaching_intent,
    teaching_move="",
    planned_question="",
    planned_exit_check="",
    practice_level=0,
    practice_format="",
    practice_focus="",
    answer_evaluation=None,
    math_verification=None,
    math_repaired=False,
):
    current = load_adaptive_state({STATE_KEY: state})
    updated = dict(current)
    updated["interaction_count"] = current["interaction_count"] + 1
    updated["last_intent"] = _clean(teaching_intent, 80)
    updated["last_teaching_move"] = _clean(
        teaching_move or teaching_intent,
        80,
    )

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
    next_practice_task = _last_practice_task(assistant_message)

    planned = _clean(planned_question)
    exit_check = _clean(planned_exit_check)
    move = _clean(teaching_move, 80).casefold()

    if move == "ask_diagnostic":
        pending = planned or next_question
        updated["quiz_active"] = False
        updated["awaiting_student_answer"] = bool(pending)
        updated["pending_question"] = pending
        updated["pending_question_kind"] = (
            "diagnostic" if pending else ""
        )
        updated["answer_status"] = "pending" if pending else "unassessed"
        updated["last_socratic_outcome"] = ""
        if pending:
            updated["socratic_step_count"] = (
                current["socratic_step_count"] + 1
            )
    elif move == "check_understanding" and exit_check:
        updated["quiz_active"] = False
        updated["practice_active"] = False
        updated["awaiting_student_answer"] = True
        updated["pending_question"] = exit_check
        updated["pending_question_kind"] = "exit_check"
        updated["answer_status"] = "pending"
        updated["last_socratic_outcome"] = ""
        updated["exit_check_count"] = current["exit_check_count"] + 1
        updated["socratic_step_count"] = (
            current["socratic_step_count"] + 1
        )
    elif move == "review_prerequisite":
        # A prerequisite repair may finish with one provider-generated
        # check-for-understanding question. If it does, keep that question in
        # the same deterministic pending-question lineage so the student's
        # short reply is evaluated as an answer rather than reclassified as a
        # fresh request. Declarative prerequisite explanations remain
        # non-interactive.
        pending = next_question
        updated["quiz_active"] = False
        updated["practice_active"] = False
        updated["awaiting_student_answer"] = bool(pending)
        updated["pending_question"] = pending
        updated["pending_question_kind"] = (
            "socratic_check" if pending else ""
        )
        updated["answer_status"] = "pending" if pending else "unassessed"
        updated["last_socratic_outcome"] = ""
        if pending:
            updated["socratic_step_count"] = (
                current["socratic_step_count"] + 1
            )
    elif teaching_intent == "practice":
        pending = next_practice_task
        updated["quiz_active"] = False
        updated["awaiting_student_answer"] = bool(pending)
        updated["pending_question"] = pending
        updated["pending_question_kind"] = (
            "practice" if pending else ""
        )
        updated["answer_status"] = "pending" if pending else "unassessed"
        updated["last_socratic_outcome"] = ""
        updated["practice_active"] = bool(pending)
        planned_level = int(practice_level or 0)
        if planned_level > 0:
            updated["practice_level"] = clamp_level(planned_level)
        updated["practice_format"] = _clean(
            practice_format,
            60,
        ).casefold()
        updated["practice_focus"] = _clean(practice_focus, 260)
        if pending:
            updated["practice_step_count"] = (
                current["practice_step_count"] + 1
            )
            updated["socratic_step_count"] = (
                current["socratic_step_count"] + 1
            )
    elif teaching_intent == "quiz":
        updated["quiz_active"] = True
        updated["awaiting_student_answer"] = bool(next_question)
        updated["pending_question"] = next_question
        updated["pending_question_kind"] = (
            "quiz" if next_question else ""
        )
        updated["answer_status"] = "pending" if next_question else "unassessed"
        updated["last_socratic_outcome"] = ""
        if next_question:
            updated["socratic_step_count"] = (
                current["socratic_step_count"] + 1
            )
    elif teaching_intent == "quiz_answer":
        quiz_lineage = bool(
            current["quiz_active"]
            or current["pending_question_kind"] == "quiz"
        )
        practice_lineage = bool(
            current["practice_active"]
            or current["pending_question_kind"] == "practice"
        )
        exit_check_lineage = (
            current["pending_question_kind"] == "exit_check"
        )
        # Exit checks are deliberately one-shot. Initial practice may use an
        # imperative task without '?', but after evaluated answers a real next
        # question is required to continue ordinary quiz/practice lineage.
        pending_follow_up = (
            ""
            if exit_check_lineage
            else next_question
        )
        updated["quiz_active"] = (
            quiz_lineage and bool(pending_follow_up)
        )
        updated["practice_active"] = (
            practice_lineage and bool(pending_follow_up)
        )
        updated["awaiting_student_answer"] = bool(pending_follow_up)
        updated["pending_question"] = pending_follow_up
        updated["pending_question_kind"] = (
            (
                "quiz"
                if quiz_lineage
                else (
                    "practice"
                    if practice_lineage
                    else (
                        "exit_check"
                        if exit_check_lineage
                        else "socratic_check"
                    )
                )
            )
            if pending_follow_up
            else ""
        )
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
        updated["last_socratic_outcome"] = outcome_from_evaluation(
            evaluation
        )
        updated["socratic_step_count"] = (
            current["socratic_step_count"] + 1
        )
        if practice_lineage:
            base_level = int(current.get("practice_level") or 0)
            if base_level <= 0:
                base_level = int(practice_level or 3)
            updated["practice_level"] = next_level_for_status(
                base_level,
                status,
            )
            next_format = _clean(practice_format, 60).casefold()
            next_focus = _clean(practice_focus, 260)
            misconception = _clean(
                evaluation.get("misconception"),
                240,
            )
            if (
                status in {"partial", "incorrect", "unclear"}
                and misconception
            ):
                next_format = "misconception_targeted"
                next_focus = misconception
            if next_format:
                updated["practice_format"] = next_format
            if next_focus:
                updated["practice_focus"] = next_focus
            if pending_follow_up:
                updated["practice_step_count"] = (
                    current["practice_step_count"] + 1
                )
    elif (
        teaching_intent == "hint"
        and current["awaiting_student_answer"]
        and current["pending_question"]
    ):
        # A requested hint does not consume the pending pedagogical question.
        updated["quiz_active"] = current["quiz_active"]
        updated["awaiting_student_answer"] = True
        updated["pending_question"] = current["pending_question"]
        updated["pending_question_kind"] = current["pending_question_kind"]
        updated["answer_status"] = current["answer_status"]
        updated["last_socratic_outcome"] = current["last_socratic_outcome"]
        updated["practice_active"] = current["practice_active"]
        updated["practice_level"] = current["practice_level"]
        updated["practice_step_count"] = current["practice_step_count"]
        updated["practice_format"] = current["practice_format"]
        updated["practice_focus"] = current["practice_focus"]
    else:
        updated["quiz_active"] = False
        updated["awaiting_student_answer"] = False
        updated["pending_question"] = ""
        updated["pending_question_kind"] = ""
        updated["answer_status"] = "unassessed"
        updated["practice_active"] = False
        if teaching_intent != "quiz_answer":
            updated["last_socratic_outcome"] = current[
                "last_socratic_outcome"
            ]

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
