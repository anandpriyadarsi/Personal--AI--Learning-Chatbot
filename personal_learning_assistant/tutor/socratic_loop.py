"""Socratic-loop helpers for ANVAYA Tutor 2.3.3.

This module derives compact session-local outcomes from a pending Tutor question.
It does not write mastery, progress, or long-term learning memory.
"""

from __future__ import annotations

from typing import Mapping


SOCRATIC_OUTCOMES = ("", "advance", "clarify", "repair", "unclear")
PENDING_QUESTION_KINDS = ("", "diagnostic", "quiz", "socratic_check")


def _clean(value, limit=280):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def outcome_from_evaluation(evaluation):
    payload = dict(evaluation or {})
    status = _clean(payload.get("status"), 40).casefold()
    if status == "correct":
        return "advance"
    if status == "partial":
        return "clarify"
    if status == "incorrect":
        return "repair"
    return "unclear"


def socratic_outcome_instruction():
    return (
        "For an answer to a pending Tutor question, evaluate the student's current "
        "answer before moving on. If correct, briefly acknowledge the decisive idea and "
        "advance with at most one next check question. If partial, clarify only the "
        "missing link and ask at most one adjusted check question. If incorrect, repair "
        "the specific misconception briefly and ask at most one simpler check question. "
        "If unclear, ask at most one clarification question. Never ask multiple questions "
        "in the same turn, never restart the whole topic, and never declare mastery."
    )


def normalize_pending_kind(value):
    clean = _clean(value, 40).casefold()
    return clean if clean in PENDING_QUESTION_KINDS else ""


def normalize_socratic_outcome(value):
    clean = _clean(value, 40).casefold()
    return clean if clean in SOCRATIC_OUTCOMES else ""
