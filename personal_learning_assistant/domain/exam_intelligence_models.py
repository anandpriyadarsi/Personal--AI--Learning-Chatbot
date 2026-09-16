"""Typed Phase 6.6 PYQ + Exam Intelligence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ExamQuestionEvidence:
    question_id: str
    assessment_id: str
    assessment_title: str
    assessment_type: str
    explicit_pyq: bool
    ordinal: int
    question_text: str
    max_marks_milli: Optional[int]
    accepted_topic_ids: Tuple[str, ...]
    mapping_state: str
    source_count: int
    source_labels: Tuple[str, ...]
    attempt_count: int
    unresolved_mistake_count: int


@dataclass(frozen=True)
class ExamTopicIntelligence:
    topic_id: str
    topic_name: str
    position: int
    status: str
    confidence: Optional[int]
    historical_question_count: int
    historical_assessment_count: int
    explicit_pyq_question_count: int
    total_marks_milli: int
    missing_marks_question_count: int
    source_backed_question_count: int
    attempted_question_count: int
    unresolved_mistake_count: int
    target_assessment_in_scope: bool
    preparation_priority_score: float
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class ExamIntelligenceReport:
    course_id: str
    course_code: str
    course_name: str
    as_of: str
    formal_assessment_count: int
    formal_question_count: int
    explicit_pyq_assessment_count: int
    explicit_pyq_question_count: int
    accepted_mapped_question_count: int
    proposed_only_question_count: int
    unmapped_question_count: int
    source_backed_question_count: int
    upcoming_assessment_count: int
    target_assessment_id: Optional[str]
    target_assessment_title: Optional[str]
    topics: Tuple[ExamTopicIntelligence, ...]
    questions: Tuple[ExamQuestionEvidence, ...]
    prediction_performed: bool
    writes_performed: bool
