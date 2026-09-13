"""Typed read models for the legacy JSON Notes subsystem.

Phase 2 keeps ``data/notes.json`` authoritative. These models are read views
only; they are not a new persistence format and do not migrate note bodies.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class NoteView:
    title: str
    topic: str
    difficulty: str
    content: str

    @classmethod
    def from_legacy(cls, data):
        return cls(
            title=str(data.get("title", "")),
            topic=str(data.get("topic", "")),
            difficulty=str(data.get("difficulty", "")),
            content=str(data.get("content", "")),
        )

    def to_legacy_dict(self):
        return {
            "title": self.title,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "content": self.content,
        }


@dataclass(frozen=True)
class ListNotesQuery:
    topic: Optional[str] = None
    difficulty: Optional[str] = None


@dataclass(frozen=True)
class SearchNotesQuery:
    text: str
    topic: Optional[str] = None
    difficulty: Optional[str] = None


@dataclass(frozen=True)
class NoteListResult:
    notes: Tuple[NoteView, ...]


@dataclass(frozen=True)
class NoteCountResult:
    count: int


@dataclass(frozen=True)
class NoteSearchResult:
    query: str
    notes: Tuple[NoteView, ...]
