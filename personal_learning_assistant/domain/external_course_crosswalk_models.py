"""Typed review artifacts for Phase 5.7 MIT 18.06 ↔ MA103N crosswalk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class TopicCatalogEntry:
    topic_id: str
    name: str
    normalized_name: str
    aliases: Tuple[str, ...]


@dataclass(frozen=True)
class CrosswalkSuggestion:
    topic_id: str
    topic_name: str
    score: float
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class CrosswalkDecision:
    external_label: str
    decision: str
    target_topic_id: Optional[str]
    target_topic_name: Optional[str]
    reviewed: bool
    review_note: str


@dataclass(frozen=True)
class ReviewedCrosswalk:
    schema_version: int
    external_course_id: str
    package_version: str
    source_manifest_hash: str
    local_course_code: str
    local_course_id: str
    mappings: Mapping[str, str]
    reviewed_unresolved: Tuple[str, ...]
    crosswalk_sha256: str
    complete: bool


@dataclass(frozen=True)
class CrosswalkPreview:
    external_course_id: str
    package_version: str
    local_course_code: str
    local_course_id: str
    unique_external_label_count: int
    exact_mapped_label_count: int
    reviewed_mapped_label_count: int
    reviewed_unresolved_label_count: int
    pending_review_label_count: int
    ambiguous_exact_label_count: int
    crosswalk_complete: bool
    crosswalk_sha256: str
