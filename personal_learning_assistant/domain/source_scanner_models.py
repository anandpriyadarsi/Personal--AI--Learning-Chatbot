"""Typed models for the Phase 5.2 read-only filesystem source scanner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SourceScanRoot:
    key: str
    path: str


@dataclass(frozen=True)
class SourceFingerprint:
    root_key: str
    path_key: str
    absolute_path: str
    kind: str
    mime_type: str
    content_hash: str
    size_bytes: int
    source_timestamp: str


@dataclass(frozen=True)
class SourceScanIssue:
    category: str
    path_key: str
    message: str


@dataclass(frozen=True)
class SourceScanResult:
    root: SourceScanRoot
    sources: Tuple[SourceFingerprint, ...]
    issues: Tuple[SourceScanIssue, ...]
    ignored_unsupported: int
    ignored_symlinks: int
    manifest_hash: str

    @property
    def scanned_count(self) -> int:
        return len(self.sources)


@dataclass(frozen=True)
class SourceRegistrationItem:
    document_id: str
    path_key: str
    action: str
    content_hash: str
    duplicate_candidate_ids: Tuple[str, ...]


@dataclass(frozen=True)
class SourceRegistrationPlan:
    root_key: str
    scan_manifest_hash: str
    scanned_count: int
    create_count: int
    match_count: int
    update_count: int
    duplicate_group_count: int
    missing_registry_ids: Tuple[str, ...]
    issue_count: int
    ignored_unsupported: int
    ignored_symlinks: int


@dataclass(frozen=True)
class SourceRegistrationResult:
    root_key: str
    scan_manifest_hash: str
    items: Tuple[SourceRegistrationItem, ...]
    missing_registry_ids: Tuple[str, ...]
    duplicate_groups: Tuple[Tuple[str, ...], ...]
    issue_count: int
    ignored_unsupported: int
    ignored_symlinks: int

    @property
    def created(self) -> int:
        return sum(item.action == "created" for item in self.items)

    @property
    def matched(self) -> int:
        return sum(item.action == "matched" for item in self.items)

    @property
    def updated(self) -> int:
        return sum(item.action == "updated" for item in self.items)
