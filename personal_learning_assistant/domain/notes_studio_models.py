"""Phase 5.4 Notes Studio command/result models."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass(frozen=True)
class NoteStudioView:
    id: str
    relative_path: str
    title: str
    note_type: str
    confidence: Optional[int]
    revision_status: str
    pinned_at: Optional[str]
    archived_at: Optional[str]
    trashed_at: Optional[str]
    source_hash: str
    tags: Tuple[str, ...]

@dataclass(frozen=True)
class CreateNoteRequest:
    title: str
    body: str = ""
    note_type: str = "quick"
    confidence: Optional[int] = None
    revision_status: str = "unreviewed"
    tags: Tuple[str, ...] = ()
    topic: str = ""
    course: str = ""
    note_date: str = ""
    card_summary: Tuple[str, ...] = ()

@dataclass(frozen=True)
class UpdateNoteRequest:
    note_id: str
    expected_hash: str
    title: Optional[str] = None
    body: Optional[str] = None
    note_type: Optional[str] = None
    confidence: Optional[int] = None
    revision_status: Optional[str] = None
    tags: Optional[Tuple[str, ...]] = None
    topic: Optional[str] = None
    course: Optional[str] = None
    note_date: Optional[str] = None
    card_summary: Optional[Tuple[str, ...]] = None

@dataclass(frozen=True)
class LegacyNoteDecision:
    legacy_index: int
    legacy_title: str
    decision: str
    candidate_note_ids: Tuple[str, ...]
    reason: str
