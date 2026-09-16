"""Typed contracts for Phase 6.4 Lecture Learning Mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class LectureStudySegment:
    session_id: str
    started_at: str
    ended_at: Optional[str]
    duration_minutes: int
    course_id: Optional[str]
    topic_id: Optional[str]
    outcome: str
    confidence: Optional[int]
    note: str


@dataclass(frozen=True)
class LectureLearningSnapshot:
    resource_id: str
    title: str
    resource_type: str
    provider: str
    canonical_uri: Optional[str]
    external_id: Optional[str]
    status: str
    course_ids: Tuple[str, ...]
    topic_ids: Tuple[str, ...]
    current_position: str
    progress_value: Optional[float]
    progress_max_value: Optional[float]
    progress_unit: str
    total_study_minutes: int
    segment_count: int
    active_session_id: Optional[str]
    active_started_at: Optional[str]
    current_chunk_count: int
    next_action: str


@dataclass(frozen=True)
class LectureLearningActionResult:
    action: str
    segment_id: Optional[str]
    recorded_minutes: int
    snapshot: LectureLearningSnapshot
