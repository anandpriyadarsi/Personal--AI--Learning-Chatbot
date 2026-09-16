"""Typed models for Phase 5.3 Obsidian vault registration and link graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class VaultScanIssue:
    severity: str
    category: str
    relative_path: str
    message: str


@dataclass(frozen=True)
class NoteLinkIntent:
    source_position: str
    raw_target: str
    target_kind: str
    heading: str = ""
    block_id: str = ""


@dataclass(frozen=True)
class VaultNoteFingerprint:
    relative_path: str
    path_key: str
    absolute_path: str
    source_hash: str
    file_mtime_ns: int
    title: str
    note_type: str
    confidence: Optional[int]
    revision_status: str
    assistant_id: Optional[str]
    tags: Tuple[str, ...]
    frontmatter_extra: Mapping[str, object]
    links: Tuple[NoteLinkIntent, ...]


@dataclass(frozen=True)
class VaultScanResult:
    vault_key: str
    vault_name: str
    vault_root: str
    notes: Tuple[VaultNoteFingerprint, ...]
    issues: Tuple[VaultScanIssue, ...]
    ignored_symlinks: int
    manifest_hash: str

    @property
    def note_count(self) -> int:
        return len(self.notes)

    @property
    def blocking_issue_count(self) -> int:
        return sum(item.severity == "blocking" for item in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "warning" for item in self.issues)


@dataclass(frozen=True)
class VaultRecord:
    id: str
    name: str
    root_path: str
    path_key: str
    enabled: bool
    last_scanned_at: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class NoteMetadataRecord:
    id: str
    vault_id: str
    relative_path: str
    path_key: str
    title: str
    note_type: str
    confidence: Optional[int]
    revision_status: str
    source_hash: str
    file_mtime_ns: int
    frontmatter_extra_json: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class NoteLinkRecord:
    id: str
    source_note_id: str
    target_note_id: Optional[str]
    unresolved_target: str
    source_position: str
    heading: str
    block_id: str
    link_type: str
    created_at: str


@dataclass(frozen=True)
class VaultRegistryPlan:
    vault_id: str
    vault_key: str
    note_count: int
    create_count: int
    match_count: int
    update_count: int
    missing_registry_count: int
    tag_count: int
    resolved_link_count: int
    unresolved_link_count: int
    ambiguous_link_count: int
    external_link_count: int
    blocking_issue_count: int
    warning_count: int
    scan_manifest_hash: str


@dataclass(frozen=True)
class VaultRegistryResult:
    vault_id: str
    vault_key: str
    created: int
    matched: int
    updated: int
    missing_registry_ids: Tuple[str, ...]
    tag_count: int
    resolved_link_count: int
    unresolved_link_count: int
    ambiguous_link_count: int
    external_link_count: int
    blocking_issue_count: int
    warning_count: int
    scan_manifest_hash: str
