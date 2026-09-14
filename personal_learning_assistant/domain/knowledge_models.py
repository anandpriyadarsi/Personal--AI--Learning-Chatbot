"""Typed read models for the Phase 2 knowledge-discovery boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class KnowledgeDocument:
    path: str
    display_name: str
    scope: str


@dataclass(frozen=True)
class KnowledgeDocumentListResult:
    documents: Tuple[KnowledgeDocument, ...]

    @property
    def count(self) -> int:
        return len(self.documents)
