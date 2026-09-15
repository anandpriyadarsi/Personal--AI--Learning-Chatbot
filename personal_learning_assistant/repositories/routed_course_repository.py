"""CourseRepository compatibility router for Phase 4.11.

Legacy/dual-read states preserve the Phase-2 JSON repository.  After the atomic
SQLite authority switch, course/topic state is read/written through the SQLite
compatibility projection while the Phase-5 document-link sub-domain stays
legacy-read-only until its own migration.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Optional, Union

from personal_learning_assistant.repositories.json.course_repository import (
    LegacyJsonCourseRepository,
)
from personal_learning_assistant.repositories.structured_authority_router import (
    DeferredStructuredDomainWriteError,
    STORE_COURSES,
    maybe_load_sqlite_structured_store,
    maybe_save_sqlite_structured_store,
)


PathLike = Union[str, Path]


class RoutedCourseRepository:
    def __init__(self, path: Optional[PathLike] = None) -> None:
        self.legacy_repository = LegacyJsonCourseRepository(path=path)
        self.path = self.legacy_repository.path

    def load_state(self):
        routed = maybe_load_sqlite_structured_store(STORE_COURSES, self.path)
        if routed is not None:
            return deepcopy(routed)
        return self.legacy_repository.load_state()

    def save_state(self, state):
        if maybe_save_sqlite_structured_store(STORE_COURSES, self.path, state):
            return self.load_state()
        return self.legacy_repository.save_state(state)

    def get_document_link(self, document_key: str):
        # Phase 5 still owns document_links; reads remain available from JSON.
        return self.legacy_repository.get_document_link(document_key)

    def list_document_links(self):
        return self.legacy_repository.list_document_links()

    def upsert_document_link(self, document_key: str, link):
        state = self.load_state()
        links = state.setdefault("document_links", {})
        links[str(document_key)] = dict(link)
        # In SQLite mode this intentionally raises because the Phase-5-deferred
        # document_links would differ from the read-only legacy value.
        saved = self.save_state(state)
        return deepcopy(saved.get("document_links", {}).get(str(document_key)))

    def delete_document_link(self, document_key: str) -> bool:
        state = self.load_state()
        links = state.setdefault("document_links", {})
        if document_key not in links:
            return False
        del links[document_key]
        self.save_state(state)
        return True


__all__ = (
    "DeferredStructuredDomainWriteError",
    "RoutedCourseRepository",
)
