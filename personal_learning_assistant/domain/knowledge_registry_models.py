"""Typed Phase 5.1 models for the knowledge registry and coordination queues."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class KnowledgeDocumentRecord:
    id: str
    kind: str
    canonical_uri: Optional[str]
    path_key: Optional[str]
    mime_type: str
    content_hash: str
    size_bytes: Optional[int]
    source_timestamp: Optional[str]
    extraction_status: str
    extraction_version: str
    extraction_error: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class KnowledgeChunkInput:
    ordinal: int
    text_hash: str
    chunk_type: str = "text"
    page_number: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    chunk_text: Optional[str] = None


@dataclass(frozen=True)
class KnowledgeChunkRecord:
    id: str
    document_id: str
    ordinal: int
    page_number: Optional[int]
    char_start: Optional[int]
    char_end: Optional[int]
    chunk_type: str
    text_hash: str
    extraction_version: str
    chunk_text: Optional[str]


@dataclass(frozen=True)
class IndexJobRecord:
    id: str
    document_id: str
    content_hash: str
    index_kind: str
    model_name: str
    model_version: str
    index_version: str
    status: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    failed_at: Optional[str]
    error: Optional[str]


@dataclass(frozen=True)
class OperationJournalRecord:
    id: str
    kind: str
    target_path: Optional[str]
    before_hash: Optional[str]
    after_hash: Optional[str]
    state: str
    error: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class OutboxEventRecord:
    id: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: Mapping[str, Any]
    created_at: str
    processed_at: Optional[str]
    failed_at: Optional[str]
    error: Optional[str]
    attempts: int


@dataclass(frozen=True)
class DocumentRegistrationResult:
    document: KnowledgeDocumentRecord
    action: str


@dataclass(frozen=True)
class RegistryReadiness:
    tables: Tuple[str, ...]
    integrity_check: Tuple[str, ...]
    foreign_key_violations: Tuple[Tuple[Any, ...], ...]
    total_changes_before: int
    total_changes_after: int

    @property
    def passed(self) -> bool:
        return (
            self.integrity_check == ("ok",)
            and not self.foreign_key_violations
            and self.total_changes_before == self.total_changes_after
        )
