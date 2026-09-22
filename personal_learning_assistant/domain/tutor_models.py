"""Typed Phase 6.1 tutor session/evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple


TUTOR_MODES = (
    "concept",
    "doubt",
    "summary",
    "exam",
    "lecture",
    "revision",
    "guidance",
    "free",
)
SOURCE_POLICIES = ("source_only", "source_first")
SESSION_STATUSES = ("active", "completed", "abandoned")
SUPPORT_LEVELS = ("not_evaluated", "grounded", "mixed", "general", "insufficient")
EVIDENCE_RELATIONS = ("support", "background", "contrast")


@dataclass(frozen=True)
class TutorSessionSpec:
    mode: str
    source_policy: str = "source_first"
    course_id: Optional[str] = None
    topic_id: Optional[str] = None
    assessment_id: Optional[str] = None
    resource_id: Optional[str] = None
    title: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TutorSession:
    session_id: str
    mode: str
    source_policy: str
    status: str
    course_id: Optional[str]
    topic_id: Optional[str]
    assessment_id: Optional[str]
    resource_id: Optional[str]
    title: str
    metadata: Mapping[str, object]
    created_at: str
    updated_at: str
    completed_at: Optional[str]


@dataclass(frozen=True)
class TutorEvidence:
    chunk_id: str
    document_id: str
    ordinal: int
    relation_type: str = "support"
    retrieval_score: Optional[float] = None
    citation_label: str = ""


@dataclass(frozen=True)
class TutorTurn:
    turn_id: str
    session_id: str
    ordinal: int
    role: str
    content: str
    support_level: str
    provider_name: str
    provider_model: str
    created_at: str
    evidence: Tuple[TutorEvidence, ...] = ()


@dataclass(frozen=True)
class TutorFeedback:
    feedback_id: str
    turn_id: str
    rating: Optional[int]
    helpful: Optional[bool]
    feedback_text: str
    created_at: str


@dataclass(frozen=True)
class TutorProviderRequest:
    session_id: str
    mode: str
    source_policy: str
    messages: Tuple[Mapping[str, str], ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TutorProviderResponse:
    content: str
    provider_name: str
    provider_model: str
    request_id: str = ""
