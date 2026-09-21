"""Canonical study-item identity for Phase 7.5.12.2."""

from __future__ import annotations

from dataclasses import dataclass
import re


_HASH = re.compile(r"^[0-9a-f]{64}$")
_KINDS = {
    "obsidian_note",
    "knowledge_document",
    "resource",
    "external_lecture",
}


@dataclass(frozen=True)
class StudyItemIdentity:
    kind: str
    item_id: str
    version_hash: str

    def __post_init__(self) -> None:
        kind = str(self.kind or "").strip()
        item_id = str(self.item_id or "").strip()
        version_hash = str(self.version_hash or "").strip().lower()
        if kind not in _KINDS:
            raise ValueError("unsupported study item kind")
        if not item_id or len(item_id) > 500:
            raise ValueError("study item identity is invalid")
        if not _HASH.fullmatch(version_hash):
            raise ValueError("study item version hash must be SHA-256")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "item_id", item_id)
        object.__setattr__(self, "version_hash", version_hash)

    @property
    def key(self) -> str:
        return "{}:{}".format(self.kind, self.item_id)
