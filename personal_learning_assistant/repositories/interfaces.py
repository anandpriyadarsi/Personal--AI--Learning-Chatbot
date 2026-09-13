"""Repository protocols used by Phase 2 services."""

from typing import Any, Dict, Protocol


CourseState = Dict[str, Any]


class CourseRepository(Protocol):
    """Persistence boundary for course state."""

    def load_state(self) -> CourseState:
        """Return normalized course state without mutating storage."""
        ...

    def save_state(self, state: CourseState) -> CourseState:
        """Persist normalized course state explicitly."""
        ...

    def get_document_link(self, document_key: str):
        """Return one normalized document-link record or None."""
        ...

    def list_document_links(self):
        """Return normalized document-link records keyed by document key."""
        ...

    def upsert_document_link(self, document_key: str, link):
        """Create or replace one document-link record explicitly."""
        ...

    def delete_document_link(self, document_key: str) -> bool:
        """Delete one document-link record if present."""
        ...

class NoteRepository(Protocol):
    """Read boundary for the legacy notes store during Phase 2."""

    def load_notes(self):
        """Return legacy note dictionaries without mutating storage."""
        ...

