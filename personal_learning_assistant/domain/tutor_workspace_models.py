"""Typed Phase 6.9 Tutor Workspace contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from personal_learning_assistant.domain.adaptive_mentor_models import (
    AdaptiveMentorReport,
)


@dataclass(frozen=True)
class WorkspaceCounts:
    topic_count: int
    resource_count: int
    assessment_count: int
    tutor_session_count: int
    active_tutor_session_count: int
    practice_session_count: int
    active_practice_session_count: int
    deterministic_practice_attempt_count: int
    active_lecture_segment_count: int
    completed_agent_action_count: int
    planned_agent_action_count: int


@dataclass(frozen=True)
class WorkspaceActivity:
    activity_type: str
    entity_id: str
    title: str
    status: str
    mode: str
    topic_id: Optional[str]
    resource_id: Optional[str]
    assessment_id: Optional[str]
    occurred_at: str


@dataclass(frozen=True)
class TutorWorkspaceSnapshot:
    course_id: str
    course_code: str
    course_name: str
    as_of: str
    schema_versions: Tuple[int, ...]
    tutor_schema_ready: bool
    practice_schema_ready: bool
    counts: WorkspaceCounts
    recent_activity: Tuple[WorkspaceActivity, ...]
    mentor: AdaptiveMentorReport
    writes_performed: bool
    provider_called: bool
