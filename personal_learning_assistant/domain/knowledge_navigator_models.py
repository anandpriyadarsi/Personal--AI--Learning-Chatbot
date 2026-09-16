"""Typed contracts for Phase 6.3 Knowledge Navigator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class StudySourceRecommendation:
    source_kind: str
    source_id: str
    title: str
    score: float
    reasons: Tuple[str, ...]
    status: str
    provider: str = ""
    resource_type: str = ""
    progress_status: str = ""
    progress_value: Optional[float] = None
    progress_max_value: Optional[float] = None
    progress_unit: str = ""
    current_chunk_count: int = 0
    study_minutes: int = 0


@dataclass(frozen=True)
class StudyTopicRecommendation:
    topic_id: str
    topic_name: str
    position: int
    status: str
    confidence: Optional[int]
    priority_score: float
    reasons: Tuple[str, ...]
    nearest_due_on: Optional[str]
    upcoming_assessment_count: int
    unresolved_mistake_count: int
    active_memory_count: int
    planned_item_count: int
    study_minutes: int
    sources: Tuple[StudySourceRecommendation, ...]


@dataclass(frozen=True)
class KnowledgeNavigatorResult:
    course_id: str
    course_code: str
    course_name: str
    as_of: str
    focused_topic_id: Optional[str]
    topic_count: int
    topics: Tuple[StudyTopicRecommendation, ...]
    writes_performed: bool
