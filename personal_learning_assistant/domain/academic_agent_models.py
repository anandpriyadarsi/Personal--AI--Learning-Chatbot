"""Typed Phase 6.8 Academic Agent Cutover contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class AcademicAgentActionPlan:
    course_id: str
    course_code: str
    as_of: str
    target_assessment_id: Optional[str]
    action_sequence: int
    action_type: str
    title: str
    topic_id: str
    topic_name: str
    priority_score: float
    reasons: Tuple[str, ...]
    resource_id: Optional[str]
    note_id: Optional[str]
    question_id: Optional[str]
    assessment_id: Optional[str]
    source_labels: Tuple[str, ...]
    route: str
    fingerprint: str
    confirmation_phrase: str
    writes_expected: bool
    provider_call_expected: bool
    executable: bool
    blocked_reason: str


@dataclass(frozen=True)
class AcademicAgentExecutionResult:
    fingerprint: str
    action_type: str
    route: str
    status: str
    result_type: str
    result_id: Optional[str]
    payload: Mapping[str, object]
    writes_performed: bool
    provider_called: bool
    already_executed: bool
