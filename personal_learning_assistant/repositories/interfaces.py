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
