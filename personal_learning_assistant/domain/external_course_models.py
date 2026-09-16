"""Typed models for Phase 5.7 external-course knowledge packages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class ExternalLecture:
    lecture_number: str
    lecture_title: str
    official_lecture_url: str
    major_concepts: Tuple[str, ...]
    prerequisites: Tuple[str, ...]
    nitk_weeks: Tuple[str, ...]
    nitk_alignment: str
    priority: str
    raw: Mapping[str, object]


@dataclass(frozen=True)
class ExternalKnowledgeChunk:
    chunk_id: str
    chunk_type: str
    lecture_number: Optional[str]
    lecture_numbers: Tuple[str, ...]
    lecture_title: Optional[str]
    topic: str
    concepts: Tuple[str, ...]
    prerequisites: Tuple[str, ...]
    related_concepts: Tuple[str, ...]
    nitk_weeks: Tuple[str, ...]
    priority: str
    text: str
    source: Mapping[str, object]
    source_url: str
    supporting_source_urls: Tuple[str, ...]
    retrieval_queries: Tuple[str, ...]
    answer_modes: Tuple[str, ...]
    content_version: str
    content_hash: str


@dataclass(frozen=True)
class ExternalCoursePackage:
    root: str
    course_id: str
    course_title: str
    instructor: str
    version: str
    source_policy: Tuple[str, ...]
    official_hubs: Mapping[str, str]
    manifest: Mapping[str, object]
    lectures: Tuple[ExternalLecture, ...]
    chunks: Tuple[ExternalKnowledgeChunk, ...]
    manifest_sha256: str
    inventory_sha256: str
    schema_sha256: str
    chunks_sha256: str
    manifest_size: int
    inventory_size: int
    schema_size: int
    chunks_size: int


@dataclass(frozen=True)
class TopicResolution:
    raw_label: str
    state: str
    topic_ids: Tuple[str, ...]


@dataclass(frozen=True)
class ExternalCoursePreview:
    course_id: str
    package_version: str
    lecture_count: int
    chunk_count: int
    lecture_chunk_count: int
    concept_chunk_count: int
    local_course_code: str
    local_course_id: str
    unique_topic_label_count: int
    mapped_topic_label_count: int
    unresolved_topic_label_count: int
    ambiguous_topic_label_count: int
    planned_resource_count: int
    matched_resource_count: int
    planned_document_count: int
    matched_document_count: int
    extraction_current: bool
    source_manifest_hash: str


@dataclass(frozen=True)
class ExternalCourseApplyResult:
    course_resource_id: str
    lecture_resource_count: int
    knowledge_document_count: int
    chunk_count: int
    mapped_topic_link_count: int
    unresolved_topic_label_count: int
    handoff_job_id: str
    extraction_version: str
