"""Immutable academic template models for Notes Studio."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class NoteTemplateSection:
    heading: str
    guidance: str


@dataclass(frozen=True)
class NoteTemplate:
    template_id: str
    name: str
    note_type: str
    description: str
    best_for: str
    sections: Tuple[NoteTemplateSection, ...]
    revision_status: str = "unreviewed"
