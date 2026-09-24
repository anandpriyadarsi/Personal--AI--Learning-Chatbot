"""Read-only view models for the rich Notes Studio library and reader."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple


@dataclass(frozen=True)
class NoteCard:
    """Canonical, storage-neutral card representation for one Markdown note."""

    identity: str
    relative_path: str
    source_hash: str
    title: str
    topic: str
    course: str
    note_type: str
    note_date: str
    card_summary: Tuple[str, ...]
    tags: Tuple[str, ...]
    revision_status: str
    source: str = ""


@dataclass(frozen=True)
class NoteDetail:
    """Full read-only note view composed from a safe current vault read."""

    card: NoteCard
    text: str
    wikilinks: Tuple[Mapping[str, object], ...]
    backlinks: Tuple[Mapping[str, object], ...]
    related_notes: Tuple[Mapping[str, object], ...] = ()
    connection_facets: Tuple[Mapping[str, object], ...] = ()
