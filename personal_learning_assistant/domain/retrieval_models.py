"""Typed models for Phase 5.8 rebuildable retrieval and RAG context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class RetrievalFilters:
    course_ids: Tuple[str, ...] = ()
    topic_ids: Tuple[str, ...] = ()
    resource_ids: Tuple[str, ...] = ()
    document_ids: Tuple[str, ...] = ()
    lecture_numbers: Tuple[str, ...] = ()
    providers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    document_id: str
    text: str
    score: float
    lexical_rank: Optional[int]
    semantic_rank: Optional[int]
    page_number: Optional[int]
    locator: Mapping[str, object]
    resource_ids: Tuple[str, ...]
    course_ids: Tuple[str, ...]
    topic_ids: Tuple[str, ...]
    providers: Tuple[str, ...]


@dataclass(frozen=True)
class RetrievalPreview:
    active_document_count: int
    active_chunk_count: int
    pending_handoff_count: int
    completed_handoff_count: int
    stale_handoff_count: int
    source_fingerprint: str
    current_index_generation: str
    index_is_current: bool
    semantic_available: bool


@dataclass(frozen=True)
class BuiltIndex:
    generation_id: str
    directory: str
    chunk_count: int
    lexical_backend: str
    semantic_enabled: bool
    embedding_model: str
    embedding_version: str
    source_fingerprint: str


@dataclass(frozen=True)
class RAGContext:
    query: str
    context_text: str
    hits: Tuple[RetrievalHit, ...]
    total_characters: int
    source_count: int
