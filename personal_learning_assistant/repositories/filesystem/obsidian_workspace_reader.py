"""Read-only Obsidian workspace browsing/search helpers for Phase 7.5.12.

The configured vault remains authoritative. This module may read Markdown bytes,
but it never creates, rewrites, moves, deletes, registers, or indexes notes.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, Tuple

from personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner import (
    ObsidianVaultRootError,
    ObsidianVaultScanner,
    ObsidianVaultScannerError,
    normalize_relative_path,
)


MAX_EXCERPT_CHARS = 360
MAX_ASSET_BYTES = 20 * 1024 * 1024
_ALLOWED_ASSET_MIMETYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


class ObsidianWorkspaceReadError(RuntimeError):
    """A vault note could not be read safely."""


class ObsidianWorkspacePathError(ObsidianWorkspaceReadError):
    """A requested vault/note path is invalid or unsafe."""


def _hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_absolute_like(value: str) -> bool:
    text = str(value or "").strip()
    return (
        Path(text).is_absolute()
        or text.startswith("/")
        or text.startswith("\\")
        or bool(_WINDOWS_ABSOLUTE.match(text))
    )


def _excerpt(text: str, query: str) -> str:
    compact = " ".join(str(text or "").split())
    if not compact:
        return ""
    if len(compact) <= MAX_EXCERPT_CHARS:
        return compact

    needle = str(query or "").casefold()
    index = compact.casefold().find(needle)
    if index < 0:
        return compact[:MAX_EXCERPT_CHARS].rstrip() + "…"

    half = MAX_EXCERPT_CHARS // 2
    start = max(0, index - half)
    end = min(len(compact), start + MAX_EXCERPT_CHARS)
    start = max(0, end - MAX_EXCERPT_CHARS)
    snippet = compact[start:end].strip()
    if start:
        snippet = "…" + snippet
    if end < len(compact):
        snippet = snippet + "…"
    return snippet


class ObsidianWorkspaceReader:
    """Safely scan, search, and preview Markdown in one explicit vault."""

    def __init__(self, vault_root, *, vault_key="obsidian-vault"):
        self.root = Path(vault_root)
        if self.root.is_symlink():
            raise ObsidianWorkspacePathError(
                "Configured vault cannot be a symlink."
            )
        try:
            self.scanner = ObsidianVaultScanner(vault_key, self.root)
        except (TypeError, ValueError) as error:
            raise ObsidianWorkspacePathError(
                "The configured Obsidian vault is unavailable."
            ) from error
        self.search_warning_count = 0

    def scan(self):
        try:
            return self.scanner.scan()
        except ObsidianVaultRootError as error:
            raise ObsidianWorkspacePathError(
                "The configured Obsidian vault is unavailable."
            ) from error
        except ObsidianVaultScannerError as error:
            raise ObsidianWorkspaceReadError(
                "The Obsidian vault could not be read safely."
            ) from error
        except OSError as error:
            raise ObsidianWorkspaceReadError(
                "The Obsidian vault could not be read safely."
            ) from error

    def normalize_note_path(self, relative_path: str) -> str:
        text = str(relative_path or "").strip()
        if not text:
            raise ObsidianWorkspacePathError("Choose a Markdown note to open.")
        if _is_absolute_like(text):
            raise ObsidianWorkspacePathError(
                "Note path must stay inside the vault."
            )
        try:
            normalized = normalize_relative_path(text)
        except (TypeError, ValueError) as error:
            raise ObsidianWorkspacePathError(
                "Note path must stay inside the vault."
            ) from error
        if not normalized.lower().endswith(".md"):
            raise ObsidianWorkspacePathError("Only Markdown notes can be opened.")
        return normalized

    def _resolve_markdown(self, relative_path: str):
        normalized = self.normalize_note_path(relative_path)
        candidate = self.root / Path(normalized)
        current = self.root
        if current.is_symlink():
            raise ObsidianWorkspacePathError("The selected note is unavailable.")
        for part in Path(normalized).parts:
            current = current / part
            if current.is_symlink():
                raise ObsidianWorkspacePathError("The selected note is unavailable.")
        root = self.root.resolve(strict=False)
        target = candidate.resolve(strict=False)
        if target == root or root not in target.parents:
            raise ObsidianWorkspacePathError(
                "Note path must stay inside the vault."
            )
        if not target.is_file():
            raise ObsidianWorkspacePathError("The selected note is unavailable.")
        return target, normalized

    def normalize_asset_path(self, relative_path: str) -> str:
        text = str(relative_path or "").strip()
        if not text:
            raise ObsidianWorkspacePathError("Choose an image inside the vault.")
        if _is_absolute_like(text):
            raise ObsidianWorkspacePathError(
                "Image path must stay inside the vault."
            )
        try:
            normalized = normalize_relative_path(text)
        except (TypeError, ValueError) as error:
            raise ObsidianWorkspacePathError(
                "Image path must stay inside the vault."
            ) from error
        suffix = Path(normalized).suffix.casefold()
        if suffix not in _ALLOWED_ASSET_MIMETYPES:
            raise ObsidianWorkspacePathError(
                "Only PNG, JPEG, GIF, and WebP images can be opened."
            )
        return normalized

    def _resolve_asset(self, relative_path: str):
        normalized = self.normalize_asset_path(relative_path)
        candidate = self.root / Path(normalized)
        current = self.root
        if current.is_symlink():
            raise ObsidianWorkspacePathError("The selected image is unavailable.")
        for part in Path(normalized).parts:
            current = current / part
            if current.is_symlink():
                raise ObsidianWorkspacePathError(
                    "The selected image is unavailable."
                )
        root = self.root.resolve(strict=False)
        target = candidate.resolve(strict=False)
        if target == root or root not in target.parents:
            raise ObsidianWorkspacePathError(
                "Image path must stay inside the vault."
            )
        if not target.is_file():
            raise ObsidianWorkspacePathError(
                "The selected image is unavailable."
            )
        return target, normalized

    def read_asset(self, relative_path: str) -> Dict[str, object]:
        target, normalized = self._resolve_asset(relative_path)
        try:
            before = target.stat()
            if before.st_size > MAX_ASSET_BYTES:
                raise ObsidianWorkspaceReadError(
                    "The selected image is too large to open safely."
                )
            raw = target.read_bytes()
            after = target.stat()
        except ObsidianWorkspaceReadError:
            raise
        except OSError as error:
            raise ObsidianWorkspaceReadError(
                "The selected image could not be read safely."
            ) from error

        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise ObsidianWorkspaceReadError(
                "The image changed while it was being read. Refresh and try again."
            )
        if len(raw) > MAX_ASSET_BYTES:
            raise ObsidianWorkspaceReadError(
                "The selected image is too large to open safely."
            )

        suffix = Path(normalized).suffix.casefold()
        return {
            "relative_path": normalized,
            "bytes": raw,
            "mimetype": _ALLOWED_ASSET_MIMETYPES[suffix],
            "source_hash": _hash_bytes(raw),
            "size_bytes": len(raw),
        }

    def read_note(self, relative_path: str, *, expected_hash: str = "") -> Dict[str, object]:
        target, normalized = self._resolve_markdown(relative_path)
        try:
            before = target.stat()
            raw = target.read_bytes()
            after = target.stat()
        except OSError as error:
            raise ObsidianWorkspaceReadError(
                "The selected note could not be read safely."
            ) from error

        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise ObsidianWorkspaceReadError(
                "The note changed while it was being read. Refresh and try again."
            )

        source_hash = _hash_bytes(raw)
        expected = str(expected_hash or "").strip().lower()
        if expected and source_hash.lower() != expected:
            raise ObsidianWorkspaceReadError(
                "The note changed since the vault was scanned. Refresh and try again."
            )
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ObsidianWorkspaceReadError(
                "The selected Markdown note is not valid UTF-8."
            ) from error

        return {
            "relative_path": normalized,
            "text": text,
            "source_hash": source_hash,
            "size_bytes": len(raw),
        }

    def search(self, scan, query: str, *, limit: int = 100) -> Tuple[Dict[str, object], ...]:
        clean_query = " ".join(str(query or "").strip().split())
        if not clean_query:
            self.search_warning_count = 0
            return ()
        try:
            bounded_limit = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            bounded_limit = 100

        needle = clean_query.casefold()
        results = []
        warnings = 0
        for note in scan.notes:
            title = str(note.title or "")
            relative_path = str(note.relative_path or "")
            tags = tuple(str(item) for item in (note.tags or ()))
            metadata_scope = ""
            if needle in title.casefold():
                metadata_scope = "title"
            elif needle in relative_path.casefold():
                metadata_scope = "path"
            elif any(needle in tag.casefold() for tag in tags):
                metadata_scope = "tag"

            body_text = ""
            body_match = False
            try:
                payload = self.read_note(
                    relative_path,
                    expected_hash=str(note.source_hash or ""),
                )
                body_text = str(payload["text"])
                body_match = needle in body_text.casefold()
            except ObsidianWorkspaceReadError:
                warnings += 1

            if not metadata_scope and not body_match:
                continue
            scope = metadata_scope or "body"
            results.append(
                {
                    "relative_path": relative_path,
                    "title": title,
                    "tags": list(tags),
                    "note_type": str(note.note_type or "note"),
                    "revision_status": str(note.revision_status or "unreviewed"),
                    "source_hash": str(note.source_hash or ""),
                    "excerpt": _excerpt(body_text, clean_query),
                    "match_scope": scope,
                }
            )

        priority = {"title": 0, "path": 1, "tag": 2, "body": 3}
        results.sort(
            key=lambda item: (
                priority.get(str(item["match_scope"]), 9),
                str(item["relative_path"]).casefold(),
            )
        )
        self.search_warning_count = warnings
        return tuple(results[:bounded_limit])
