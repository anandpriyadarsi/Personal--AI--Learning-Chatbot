"""Typed models for Phase 5.6 Unified Ingestion Pipeline."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

@dataclass(frozen=True)
class ExtractedUnit:
    text: str
    kind: str
    page_number: Optional[int] = None
    section_path: str = ""
    slide_number: Optional[int] = None
    timestamp_start_ms: Optional[int] = None
    timestamp_end_ms: Optional[int] = None
    locator: Mapping[str, object] = None

@dataclass(frozen=True)
class PreparedChunk:
    ordinal: int
    text: str
    text_hash: str
    page_number: Optional[int]
    char_start: int
    char_end: int
    chunk_type: str
    locator: Mapping[str, object]

@dataclass(frozen=True)
class IngestionPreviewItem:
    document_id: str
    state: str
    adapter: str
    content_hash: str
    extraction_status: str
    extraction_version: str

@dataclass(frozen=True)
class IngestionPreview:
    total: int
    ready: int
    current: int
    unsupported: int
    missing_source: int
    hash_mismatch: int
    remote_only: int
    items: Tuple[IngestionPreviewItem, ...]

@dataclass(frozen=True)
class IngestionResult:
    document_id: str
    status: str
    adapter: str
    extraction_version: str
    chunk_count: int
    handoff_job_id: Optional[str]
    message: str = ""
