"""Canonical tutor modes and source-policy rules for Phase 6.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from personal_learning_assistant.domain.tutor_models import (
    SOURCE_POLICIES,
    TUTOR_MODES,
)


@dataclass(frozen=True)
class TutorModePolicy:
    mode: str
    purpose: str
    preferred_source_roles: Tuple[str, ...]


_POLICIES = {
    "concept": TutorModePolicy(
        "concept",
        "Explain intuition first, then formal detail.",
        ("professor", "course", "personal_note", "external_course"),
    ),
    "doubt": TutorModePolicy(
        "doubt",
        "Diagnose a specific confusion without skipping prerequisites.",
        ("professor", "course", "personal_note", "external_course"),
    ),
    "summary": TutorModePolicy(
        "summary",
        "Summarize only the selected grounded material.",
        ("selected_resource", "professor", "course", "personal_note"),
    ),
    "exam": TutorModePolicy(
        "exam",
        "Prioritize course/professor/PYQ evidence over external explanations.",
        ("professor", "course", "pyq", "personal_note", "external_course"),
    ),
    "lecture": TutorModePolicy(
        "lecture",
        "Stay scoped to the selected lecture/resource unless fallback is needed.",
        ("selected_resource", "course", "personal_note"),
    ),
    "revision": TutorModePolicy(
        "revision",
        "Prefer concise recall from course and personal material.",
        ("personal_note", "professor", "course", "pyq"),
    ),
    "guidance": TutorModePolicy(
        "guidance",
        "Recommend an evidence-backed next learning action.",
        ("professor", "course", "personal_note", "external_course"),
    ),
    "free": TutorModePolicy(
        "free",
        "General academic conversation while preserving source boundaries.",
        ("course", "personal_note", "external_course"),
    ),
}


def get_mode_policy(mode: str) -> TutorModePolicy:
    value = str(mode or "").strip().casefold()
    if value not in TUTOR_MODES:
        raise ValueError("unsupported tutor mode: {!r}".format(mode))
    return _POLICIES[value]


def validate_source_policy(source_policy: str) -> str:
    value = str(source_policy or "").strip().casefold()
    if value not in SOURCE_POLICIES:
        raise ValueError(
            "unsupported tutor source policy: {!r}".format(source_policy)
        )
    return value
