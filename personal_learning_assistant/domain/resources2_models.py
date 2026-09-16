"""Typed models for Phase 5.5 Resources 2 Core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


CANONICAL_RESOURCE_STATUSES = (
    "saved",
    "not_started",
    "in_progress",
    "paused",
    "completed",
    "needs_review",
    "abandoned",
    "archived",
)


@dataclass(frozen=True)
class ResourceRecord:
    id: str
    resource_type: str
    title: str
    canonical_uri: Optional[str]
    provider: str
    external_id: Optional[str]
    status: str
    rating: Optional[int]
    quality_note: str
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    archived_at: Optional[str]
    deleted_at: Optional[str]


@dataclass(frozen=True)
class ResourceCourseLink:
    course_id: str
    role: str = "supporting"


@dataclass(frozen=True)
class ResourceTopicLink:
    topic_id: str
    relation_source: str = "explicit"
    confidence: Optional[float] = None


@dataclass(frozen=True)
class ResourceNoteLink:
    note_id: str
    role: str = "related"


@dataclass(frozen=True)
class ResourceAssessmentLink:
    assessment_id: str
    role: str = "related"


@dataclass(frozen=True)
class ResourceDocumentLink:
    document_id: str
    role: str = "source"


@dataclass(frozen=True)
class CreateResource2Command:
    title: str
    resource_type: str
    canonical_uri: Optional[str] = None
    provider: str = ""
    external_id: Optional[str] = None
    status: str = "not_started"
    rating: Optional[int] = None
    quality_note: str = ""
    course_links: Tuple[ResourceCourseLink, ...] = ()
    topic_links: Tuple[ResourceTopicLink, ...] = ()
    note_links: Tuple[ResourceNoteLink, ...] = ()
    assessment_links: Tuple[ResourceAssessmentLink, ...] = ()
    document_links: Tuple[ResourceDocumentLink, ...] = ()
    allow_duplicate: bool = False


@dataclass(frozen=True)
class UpdateResource2Command:
    resource_id: str
    title: Optional[str] = None
    resource_type: Optional[str] = None
    canonical_uri: Optional[str] = None
    provider: Optional[str] = None
    external_id: Optional[str] = None
    rating: Optional[int] = None
    quality_note: Optional[str] = None


@dataclass(frozen=True)
class ResourceProgressCommand:
    resource_id: str
    status: str
    occurred_at: str
    value: Optional[float] = None
    max_value: Optional[float] = None
    unit: str = ""
    position: str = ""
    note: str = ""


@dataclass(frozen=True)
class ResourceProgressEvent:
    id: str
    resource_id: str
    occurred_at: str
    status: str
    value: Optional[float]
    max_value: Optional[float]
    unit: str
    position: str
    note: str


@dataclass(frozen=True)
class DuplicateCandidate:
    resource_id: str
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class ResourceRelations:
    courses: Tuple[ResourceCourseLink, ...]
    topics: Tuple[ResourceTopicLink, ...]
    notes: Tuple[ResourceNoteLink, ...]
    assessments: Tuple[ResourceAssessmentLink, ...]
    documents: Tuple[ResourceDocumentLink, ...]


@dataclass(frozen=True)
class ResourceDetails:
    resource: ResourceRecord
    relations: ResourceRelations
    history: Tuple[ResourceProgressEvent, ...]


@dataclass(frozen=True)
class LegacyResourceDecision:
    legacy_index: int
    title: str
    decision: str
    candidate_resource_ids: Tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class CandidateResource:
    source_kind: str
    source_id: str
    suggested_type: str
    suggested_title: str
    identity_hint: str
    duplicate_resource_ids: Tuple[str, ...]


@dataclass(frozen=True)
class ResourceReconciliationReport:
    source_status: str
    source_sha256: str
    source_byte_count: int
    validated_legacy_records: int
    legacy_decisions: Tuple[LegacyResourceDecision, ...]
    document_candidates: Tuple[CandidateResource, ...]
    note_candidates: Tuple[CandidateResource, ...]
