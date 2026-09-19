"""Repository protocols used by Phase 2 services."""

from typing import Any, Dict, Protocol


CourseState = Dict[str, Any]
AssessmentState = Dict[str, Any]
QuestionState = Dict[str, Any]


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


class AssessmentRepository(Protocol):
    """Persistence boundary for legacy-shaped assessment state."""

    def load_state(self) -> AssessmentState:
        """Return assessment state without mutating storage."""
        ...

    def save_state(self, state: AssessmentState) -> AssessmentState:
        """Persist assessment state through the selected authoritative backend."""
        ...


class QuestionRepository(Protocol):
    """Persistence boundary for the legacy assessment-question workspace."""

    def load_state(self) -> QuestionState:
        """Return question-workspace state without mutating storage."""
        ...

    def save_state(self, state: QuestionState) -> QuestionState:
        """Persist question-workspace state through the selected authority."""
        ...


class NoteRepository(Protocol):
    """Persistence boundary for the legacy notes store during Phase 2."""

    def load_notes(self):
        """Return legacy note dictionaries without mutating storage."""
        ...

    def append_note(self, note):
        """Persist one legacy-shaped note through an explicit command."""
        ...

    def replace_note(self, position: int, note):
        """Replace one 1-based legacy note row through an explicit command."""
        ...


class ResourceRepository(Protocol):
    # Persistence boundary required by the Phase 2 ResourceService.

    def load_resources(self):
        ...

    def append_resource(self, resource):
        ...

    def replace_resource(self, position: int, resource):
        ...


class KnowledgeRepository(Protocol):
    # Read-only document discovery boundary.

    def list_document_paths(self):
        ...

    def get_vault_path(self):
        ...


class CourseKnowledgeContext(Protocol):
    # Read-only bridge used by Knowledge during Phase 2.

    def find_course(
        self,
        identifier,
    ):
        ...

    def get_document_metadata(
        self,
        file_path,
        content=None,
    ):
        ...
