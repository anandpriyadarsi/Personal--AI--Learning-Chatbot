"""Deterministic teaching-intent hints for Tutor 2.0.

This is deliberately lightweight and local. It does not call an LLM and does
not mutate academic state. The provider still sees the student's original
question; this classifier only supplies a pedagogical hint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TutorIntent:
    name: str
    instruction: str


def _normalize(value):
    return " ".join(str(value or "").casefold().split())


_PATTERNS = (
    (
        "hint",
        (
            r"\bhint\b",
            r"do not solve",
            r"don't solve",
            r"without (?:the )?(?:full )?solution",
            r"no full answer",
        ),
        "Give only the next useful hint. Do not reveal the full solution unless the student asks for it.",
    ),
    (
        "quiz",
        (
            r"\bquiz me\b",
            r"\btest me\b",
            r"ask me (?:a|one|some) question",
            r"one question at a time",
        ),
        "Tutor interactively: ask one short question, wait for the student's reply, then adapt.",
    ),
    (
        "verify_reasoning",
        (
            r"am i right",
            r"is (?:this|my answer|my reasoning) correct",
            r"check my (?:answer|reasoning|solution|work)",
            r"verify (?:this|my)",
        ),
        "Evaluate the student's reasoning first. Identify exactly what is correct and what needs correction before re-explaining.",
    ),
    (
        "example",
        (
            r"\bexample\b",
            r"show me (?:an|a) example",
            r"walk (?:me )?through",
            r"worked example",
        ),
        "Use one concrete example and walk through it step by step, connecting each step to the underlying idea.",
    ),
    (
        "practice",
        (
            r"\bpractice\b",
            r"give me (?:a|one|some) (?:problem|question)",
            r"problem for me",
            r"question for me",
        ),
        "Give a suitable practice problem. Unless explicitly requested, do not immediately reveal the full solution.",
    ),
    (
        "summary",
        (
            r"\bsummar(?:y|ize|ise)\b",
            r"\brecap\b",
            r"key points",
        ),
        "Give a concise learning-oriented recap focused on the few ideas the student should retain.",
    ),
    (
        "guidance",
        (
            r"what should i (?:study|learn|do)",
            r"where should i start",
            r"what next",
            r"next topic",
            r"study first",
        ),
        "Recommend the next learning step using the available course context and explain the reason briefly.",
    ),
    (
        "explain_differently",
        (
            r"still (?:don't|do not) understand",
            r"still confused",
            r"explain (?:it )?(?:again|differently|simply|simpler)",
            r"another way",
            r"simpler way",
        ),
        "Do not repeat the previous explanation. Change the representation: use a simpler intuition, analogy, visual description, or different example.",
    ),
)


def classify_tutor_intent(question):
    clean = _normalize(question)
    for name, patterns, instruction in _PATTERNS:
        if any(re.search(pattern, clean) for pattern in patterns):
            return TutorIntent(name=name, instruction=instruction)
    return TutorIntent(
        name="explain",
        instruction=(
            "Answer as a tutor: identify the key missing idea, explain it at the student's level, "
            "and use a short check-for-understanding when helpful."
        ),
    )
