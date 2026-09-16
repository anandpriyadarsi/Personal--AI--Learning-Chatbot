"""Typed Phase 6.7 Adaptive Mentor contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class MentorPracticeSummary:
    available: bool
    session_count: int
    completed_session_count: int
    deterministic_attempt_count: int
    correct_attempt_count: int
    incorrect_attempt_count: int
    advisory_attempt_count: int
    latest_attempt_at: Optional[str]

    @property
    def deterministic_accuracy(self):
        if self.deterministic_attempt_count <= 0:
            return None
        return self.correct_attempt_count / self.deterministic_attempt_count


@dataclass(frozen=True)
class MentorTopicState:
    topic_id: str
    topic_name: str
    status: str
    confidence: Optional[int]
    navigator_priority_score: float
    exam_priority_score: float
    combined_priority_score: float
    unresolved_mistake_count: int
    active_memory_count: int
    upcoming_assessment_count: int
    target_assessment_in_scope: bool
    practice: MentorPracticeSummary
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class MentorAction:
    sequence: int
    action_type: str
    topic_id: str
    topic_name: str
    title: str
    priority_score: float
    reasons: Tuple[str, ...]
    resource_id: Optional[str] = None
    question_id: Optional[str] = None
    assessment_id: Optional[str] = None
    source_labels: Tuple[str, ...] = ()
    advisory: bool = True


@dataclass(frozen=True)
class AdaptiveMentorReport:
    course_id: str
    course_code: str
    course_name: str
    as_of: str
    target_assessment_id: Optional[str]
    target_assessment_title: Optional[str]
    practice_history_available: bool
    topics: Tuple[MentorTopicState, ...]
    actions: Tuple[MentorAction, ...]
    llm_called: bool
    writes_performed: bool
    authoritative_state_changes: bool
