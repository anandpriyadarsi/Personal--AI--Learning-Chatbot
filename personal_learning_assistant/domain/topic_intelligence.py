"""Immutable B1 observations, not mastery judgments or recovery decisions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class EvidenceReference:
    kind: str
    identifier: str


@dataclass(frozen=True)
class TopicIdentity:
    course_id: str
    course_code: str
    course_name: str
    topic_id: str
    topic_name: str
    stored_status: str
    self_reported_confidence: int | None


@dataclass(frozen=True)
class MappingSnapshot:
    mapping_id: str | None = None
    state: str = 'unknown'
    confidence: float | None = None
    method: str | None = None
    reviewed_at: str | None = None
    review_required: bool | None = None
    provenance: str | None = None


@dataclass(frozen=True)
class IndependenceSnapshot:
    status: str = 'unknown'
    declaration_ref: str | None = None
    assistance_provenance: tuple[EvidenceReference, ...] = ()


@dataclass(frozen=True)
class TopicEvidence:
    evidence_id: str
    session_evaluation_id: str
    session_question_id: str
    response_id: str
    question_id: str
    question_identity: str | None
    session_id: str
    assessment_id: str
    course_id: str
    topic_id: str
    ordinal: int
    mode: str
    session_status: str
    occurred_at_raw: str | None
    occurred_at_utc: datetime | None
    local_date: date | None
    awarded_marks_milli: int | None
    max_marks_milli: int
    outcome: str
    evaluation_status: str
    session_evaluation_status: str | None
    evaluator_type: str
    grading_confidence: float | None
    rubric_version: str
    difficulty: str
    mapping: MappingSnapshot
    independence: IndependenceSnapshot
    mistake_categories: tuple[str, ...]
    source_refs: tuple[EvidenceReference, ...]
    exclusion_reasons: tuple[str, ...]
    source_kind: str = 'assessment_evaluation'

    @property
    def automatic_eligible(self) -> bool:
        # B1 has no historical immutable mapping/independence authority. A later
        # versioned adapter and policy must establish eligibility explicitly.
        return False


@dataclass(frozen=True)
class TopicEvidenceBundle:
    topic: TopicIdentity
    evidence: tuple[TopicEvidence, ...]
    as_of_utc: datetime
    timezone: str
    snapshot_sha256: str
    evidence_fingerprint: str
    contract_version: str = 'topic-evidence-b1-v1'
    supporting_sources_status: str = 'not_read_in_b1'
