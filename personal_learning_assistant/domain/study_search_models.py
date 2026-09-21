"""Student-facing search contracts for Phase 7.5.12.2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class StudySearchResult:
    item_kind: str
    item_id: str
    version_hash: str
    title: str
    subtitle: str
    source_label: str
    snippet: str
    course_ids: Tuple[str, ...] = ()
    course_labels: Tuple[str, ...] = ()
    topic_ids: Tuple[str, ...] = ()
    topic_labels: Tuple[str, ...] = ()
    provider: str = ""
    open_target: str = ""
    matched_chunk_ids: Tuple[str, ...] = ()
    page_numbers: Tuple[int, ...] = ()
    relevance_reasons: Tuple[str, ...] = ()
    times_opened: int = 0
    total_active_seconds: int = 0
    last_read_at: Optional[str] = None


@dataclass(frozen=True)
class SearchSuggestion:
    kind: str
    label: str
    subtitle: str
    value: str
    open_target: str = ""
