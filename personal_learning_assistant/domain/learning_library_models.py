"""Immutable presentation contracts; Library owns no persisted identities."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LibraryQuery:
    course_id: str | None = None
    item_kind: str = 'all'
    page: int = 1
    page_size: int = 25

    def __post_init__(self):
        if self.item_kind not in ('all', 'resource', 'document'):
            raise ValueError('Invalid item kind')
        if type(self.page) is not int or self.page < 1:
            raise ValueError('Invalid page')
        if type(self.page_size) is not int or not 1 <= self.page_size <= 100:
            raise ValueError('Invalid page size')
        if (self.page - 1) * self.page_size > 2**63 - 1:
            raise ValueError('Page exceeds supported range')
        if self.course_id is not None and not isinstance(self.course_id, str):
            raise ValueError('Invalid course')


@dataclass(frozen=True)
class LibraryItemRef:
    kind: str
    id: str


@dataclass(frozen=True)
class LibraryAcademicLabel:
    id: str
    label: str


@dataclass(frozen=True)
class LibraryDocumentView:
    document_id: str
    title: str
    kind: str
    mime_type: str
    content_hash: str
    extraction_status: str
    open_target: str


@dataclass(frozen=True)
class LibraryItem:
    key: str
    reference: LibraryItemRef
    title: str
    item_type: str
    provider: str
    courses: tuple[LibraryAcademicLabel, ...]
    topics: tuple[LibraryAcademicLabel, ...]
    learning_status: str | None
    document_count: int
    note_count: int
    extraction_summary: str
    open_target: str


@dataclass(frozen=True)
class LibraryResourceDetail:
    resource_id: str
    title: str
    resource_type: str
    provider: str
    learning_status: str
    updated_at: str
    courses: tuple[LibraryAcademicLabel, ...]
    topics: tuple[LibraryAcademicLabel, ...]
    documents: tuple[LibraryDocumentView, ...]
    notes: tuple[LibraryAcademicLabel, ...]
    external_url: str | None


@dataclass(frozen=True)
class LibraryPage:
    items: tuple[LibraryItem, ...]
    query: LibraryQuery
    courses: tuple[LibraryAcademicLabel, ...]
    total: int
    total_pages: int
    state: str
    coverage_notice: str = ('This view shows registered material. Existing Resources remains available. '
                            'Extraction status is shown; retrieval availability is not checked on this page.')
