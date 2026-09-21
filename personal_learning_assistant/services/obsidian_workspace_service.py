"""Phase 7.5.12 browser-facing Obsidian workspace boundary.

This module is intentionally thin at import time. It does not import the legacy
Obsidian configuration module or filesystem reader until the factory is called.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from importlib import import_module
from pathlib import Path
from typing import Any, Dict


MAX_QUERY_CHARS = 300
MAX_BROWSE_NOTES = 500
MAX_SEARCH_RESULTS = 100
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_WIKILINK = re.compile(r"(?<!!)\[\[([^\[\]\r\n]+)\]\]")


class ObsidianWorkspaceError(RuntimeError):
    """Base safe web-facing Obsidian workspace error."""


class ObsidianWorkspaceValidationError(ObsidianWorkspaceError):
    """User input or current configuration is invalid."""


class ObsidianWorkspaceNotFoundError(ObsidianWorkspaceError):
    """The requested Markdown note is not present in the current vault scan."""


class ObsidianWorkspaceUnavailableError(ObsidianWorkspaceError):
    """The workspace backend is temporarily unavailable."""


def _clean_query(value: Any) -> str:
    return " ".join(str(value or "").strip().split())[:MAX_QUERY_CHARS]


def _configured_path(config: Dict[str, Any]) -> str:
    return str(config.get("vault_path") or "").strip()


def _empty_workspace(*, message: str = "") -> Dict[str, Any]:
    return {
        "available": True,
        "message": str(message or ""),
        "configured": False,
        "enabled": False,
        "valid": False,
        "vault_path": "",
        "vault_name": "",
        "query": "",
        "searched": False,
        "notes": [],
        "summary": {
            "markdown_files": 0,
            "result_count": 0,
            "displayed_count": 0,
            "truncated": False,
        },
        "issues": {
            "blocking": 0,
            "warnings": 0,
            "ignored_symlinks": 0,
            "search_skipped": 0,
        },
    }


def unavailable_obsidian_workspace(message: str = "") -> Dict[str, Any]:
    workspace = _empty_workspace(
        message=message
        or "Obsidian workspace is temporarily unavailable. Your vault was not changed."
    )
    workspace["available"] = False
    return workspace


def _is_absolute_like(value: str) -> bool:
    text = str(value or "").strip()
    return (
        Path(text).is_absolute()
        or text.startswith("/")
        or text.startswith("\\")
        or bool(_WINDOWS_ABSOLUTE.match(text))
    )


def _normalize_requested_note_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        raise ObsidianWorkspaceValidationError("Choose a Markdown note to open.")
    if _is_absolute_like(text):
        raise ObsidianWorkspaceValidationError("Note path must stay inside the vault.")
    while text.startswith("./"):
        text = text[2:]
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ObsidianWorkspaceValidationError("Note path must stay inside the vault.")
    normalized = "/".join(parts)
    if not normalized.lower().endswith(".md"):
        raise ObsidianWorkspaceValidationError("Only Markdown notes can be opened.")
    return normalized


def _vault_identity(vault_path: str) -> str:
    resolved = str(Path(vault_path).resolve(strict=False))
    normalized = unicodedata.normalize(
        "NFC",
        os.path.normcase(resolved),
    ).replace("\\", "/")
    if len(normalized) > 1 and not re.fullmatch(r"[A-Za-z]:/", normalized):
        normalized = normalized.rstrip("/")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return "vault:" + digest


class ObsidianWorkspaceService:
    """Normalize live Obsidian browsing/configuration for the local web UI."""

    def __init__(self, config_api, reader_factory):
        self.config_api = config_api
        self.reader_factory = reader_factory

    def _load_config(self) -> Dict[str, Any]:
        try:
            config = self.config_api.load_config()
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError(
                "Obsidian configuration is temporarily unavailable."
            ) from error
        return dict(config) if isinstance(config, dict) else {}

    def _path_is_valid(self, vault_path: str) -> bool:
        if not vault_path:
            return False
        try:
            candidate = Path(vault_path)
            if candidate.is_symlink():
                return False
            valid, _message = self.config_api.validate_vault_path(vault_path)
            return bool(valid)
        except Exception:
            return False

    def _reader(self, vault_path: str):
        try:
            return self.reader_factory(vault_path, vault_key="obsidian-vault")
        except TypeError:
            # Small injected test doubles may accept only the root path.
            return self.reader_factory(vault_path)
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError(
                "The configured Obsidian vault could not be opened safely."
            ) from error

    @staticmethod
    def _browse_row(note) -> Dict[str, Any]:
        return {
            "relative_path": str(note.relative_path),
            "title": str(note.title),
            "tags": [str(item) for item in (note.tags or ())],
            "note_type": str(note.note_type or "note"),
            "revision_status": str(note.revision_status or "unreviewed"),
            "source_hash": str(note.source_hash or ""),
        }

    def workspace(self, search: Any = "") -> Dict[str, Any]:
        query = _clean_query(search)
        config = self._load_config()
        vault_path = _configured_path(config)
        workspace = _empty_workspace()
        workspace["query"] = query
        workspace["searched"] = bool(query)
        workspace["configured"] = bool(vault_path)
        workspace["enabled"] = bool(config.get("enabled", False))
        workspace["vault_path"] = vault_path
        workspace["vault_name"] = Path(vault_path).name if vault_path else ""

        if not vault_path:
            workspace["message"] = "No Obsidian vault is connected yet."
            return workspace

        workspace["valid"] = self._path_is_valid(vault_path)
        if not workspace["enabled"]:
            workspace["message"] = "This Obsidian vault is configured but currently disabled."
            return workspace
        if not workspace["valid"]:
            workspace["message"] = (
                "The configured Obsidian vault is unavailable. Choose or reconnect a valid vault folder."
            )
            return workspace

        reader = self._reader(vault_path)
        try:
            scan = reader.scan()
        except Exception as error:
            # Reader exceptions are intentionally not reflected verbatim.
            raise ObsidianWorkspaceUnavailableError(
                "The Obsidian vault could not be scanned safely."
            ) from error

        workspace["vault_name"] = str(scan.vault_name or workspace["vault_name"])
        workspace["summary"]["markdown_files"] = int(scan.note_count)
        workspace["issues"] = {
            "blocking": int(scan.blocking_issue_count),
            "warnings": int(scan.warning_count),
            "ignored_symlinks": int(scan.ignored_symlinks),
            "search_skipped": 0,
        }

        if query:
            try:
                rows = list(reader.search(scan, query, limit=MAX_SEARCH_RESULTS))
            except Exception as error:
                raise ObsidianWorkspaceUnavailableError(
                    "Live vault search is temporarily unavailable."
                ) from error
            workspace["notes"] = rows
            workspace["summary"]["result_count"] = len(rows)
            workspace["summary"]["displayed_count"] = len(rows)
            workspace["issues"]["search_skipped"] = int(
                getattr(reader, "search_warning_count", 0) or 0
            )
            return workspace

        rows = [self._browse_row(note) for note in scan.notes[:MAX_BROWSE_NOTES]]
        workspace["notes"] = rows
        workspace["summary"]["result_count"] = len(rows)
        workspace["summary"]["displayed_count"] = len(rows)
        workspace["summary"]["truncated"] = scan.note_count > MAX_BROWSE_NOTES
        return workspace

    @staticmethod
    def _wikilink_parts(raw_value: str):
        raw = str(raw_value or "").strip()
        target_part, separator, alias = raw.partition("|")
        target_part = target_part.strip()
        alias = alias.strip() if separator else ""
        path_part, heading_separator, heading = target_part.partition("#")
        return {
            "raw": raw,
            "target": path_part.strip(),
            "heading": heading.strip() if heading_separator else "",
            "label": alias or target_part.strip(),
        }

    @staticmethod
    def _link_lookup(scan):
        lookup = {}
        for item in scan.notes:
            relative_path = str(item.relative_path).replace("\\", "/")
            without_suffix = (
                relative_path[:-3]
                if relative_path.lower().endswith(".md")
                else relative_path
            )
            keys = {
                str(item.title or "").strip(),
                Path(relative_path).stem,
                relative_path,
                without_suffix,
            }
            for key in keys:
                normalized = unicodedata.normalize(
                    "NFC", str(key or "").strip()
                ).casefold()
                if normalized:
                    lookup.setdefault(normalized, []).append(item)
        return lookup

    @staticmethod
    def _resolve_link(target: str, lookup):
        normalized = unicodedata.normalize(
            "NFC", str(target or "").strip().replace("\\", "/")
        ).casefold()
        if normalized.endswith(".md"):
            without_suffix = normalized[:-3]
        else:
            without_suffix = normalized
        candidates = list(lookup.get(normalized, ()))
        if not candidates and without_suffix != normalized:
            candidates = list(lookup.get(without_suffix, ()))
        if not candidates and normalized and not normalized.endswith(".md"):
            candidates = list(lookup.get(normalized + ".md", ()))
        unique = {
            str(item.relative_path).replace("\\", "/").casefold(): item
            for item in candidates
        }
        if len(unique) != 1:
            return None, len(unique) > 1
        return next(iter(unique.values())), False

    def _link_context(self, reader, scan, current_path: str, source: str):
        lookup = self._link_lookup(scan)
        outgoing = []
        seen_outgoing = set()
        for match in _WIKILINK.finditer(str(source or "")):
            parts = self._wikilink_parts(match.group(1))
            resolved, ambiguous = self._resolve_link(parts["target"], lookup)
            resolved_path = (
                ""
                if resolved is None
                else str(resolved.relative_path).replace("\\", "/")
            )
            key = (parts["raw"], resolved_path)
            if key in seen_outgoing:
                continue
            seen_outgoing.add(key)
            outgoing.append(
                {
                    **parts,
                    "resolved_path": resolved_path,
                    "resolved_title": (
                        "" if resolved is None else str(resolved.title)
                    ),
                    "ambiguous": bool(ambiguous),
                }
            )

        backlinks = []
        current_key = str(current_path).replace("\\", "/").casefold()
        for candidate in scan.notes:
            candidate_path = str(candidate.relative_path).replace("\\", "/")
            if candidate_path.casefold() == current_key:
                continue
            try:
                payload = reader.read_note(
                    candidate_path,
                    expected_hash=str(candidate.source_hash or ""),
                )
            except Exception:
                continue
            linked = False
            for match in _WIKILINK.finditer(str(payload.get("text") or "")):
                parts = self._wikilink_parts(match.group(1))
                resolved, _ambiguous = self._resolve_link(parts["target"], lookup)
                if (
                    resolved is not None
                    and str(resolved.relative_path)
                    .replace("\\", "/")
                    .casefold()
                    == current_key
                ):
                    linked = True
                    break
            if linked:
                backlinks.append(
                    {
                        "relative_path": candidate_path,
                        "title": str(candidate.title or Path(candidate_path).stem),
                    }
                )
        backlinks.sort(
            key=lambda item: (
                item["title"].casefold(),
                item["relative_path"].casefold(),
            )
        )
        return {
            "outgoing": tuple(outgoing),
            "backlinks": tuple(backlinks),
        }

    def note_preview(self, relative_path: Any) -> Dict[str, Any]:
        requested = _normalize_requested_note_path(relative_path)
        config = self._load_config()
        vault_path = _configured_path(config)
        if not vault_path or not bool(config.get("enabled", False)):
            raise ObsidianWorkspaceValidationError(
                "Connect and enable an Obsidian vault before opening notes."
            )
        if not self._path_is_valid(vault_path):
            raise ObsidianWorkspaceValidationError(
                "The configured Obsidian vault is unavailable."
            )

        reader = self._reader(vault_path)
        try:
            scan = reader.scan()
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError(
                "The Obsidian vault could not be scanned safely."
            ) from error

        note = next(
            (
                item
                for item in scan.notes
                if str(item.relative_path).casefold() == requested.casefold()
            ),
            None,
        )
        if note is None:
            raise ObsidianWorkspaceNotFoundError(
                "That Markdown note is not present in the current vault."
            )
        try:
            payload = reader.read_note(
                str(note.relative_path),
                expected_hash=str(note.source_hash or ""),
            )
        except Exception as error:
            # Invalid paths are already filtered above; runtime read conflicts are
            # presented as availability failures to avoid leaking filesystem detail.
            raise ObsidianWorkspaceUnavailableError(
                "The selected note changed or could not be read safely. Refresh the vault and try again."
            ) from error

        link_context = self._link_context(
            reader,
            scan,
            str(note.relative_path),
            str(payload["text"]),
        )
        return {
            "title": str(note.title),
            "relative_path": str(note.relative_path),
            "assistant_id": (
                None if note.assistant_id is None else str(note.assistant_id)
            ),
            "vault_name": str(scan.vault_name),
            "vault_identity": _vault_identity(vault_path),
            "tags": [str(item) for item in (note.tags or ())],
            "note_type": str(note.note_type or "note"),
            "revision_status": str(note.revision_status or "unreviewed"),
            "source_hash": str(payload["source_hash"]),
            "size_bytes": int(payload["size_bytes"]),
            "text": str(payload["text"]),
            "wikilinks": link_context["outgoing"],
            "backlinks": link_context["backlinks"],
        }

    def markdown_snapshot(self, *, max_notes=500, max_bytes=32 * 1024 * 1024):
        """Return a bounded read-only Markdown snapshot without backlink rescans."""
        config = self._load_config()
        vault_path = _configured_path(config)
        if not vault_path or not bool(config.get("enabled", False)):
            raise ObsidianWorkspaceValidationError(
                "Connect and enable an Obsidian vault before exporting it."
            )
        if not self._path_is_valid(vault_path):
            raise ObsidianWorkspaceValidationError(
                "The configured Obsidian vault is unavailable."
            )
        reader = self._reader(vault_path)
        try:
            scan = reader.scan()
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError(
                "The Obsidian vault could not be scanned safely."
            ) from error

        rows = []
        total_bytes = 0
        bounded_notes = max(1, min(int(max_notes), MAX_BROWSE_NOTES))
        bounded_bytes = max(1, int(max_bytes))
        for note in scan.notes[:bounded_notes]:
            try:
                payload = reader.read_note(
                    str(note.relative_path),
                    expected_hash=str(note.source_hash or ""),
                )
            except Exception:
                continue
            size = int(payload.get("size_bytes") or 0)
            if rows and total_bytes + size > bounded_bytes:
                break
            total_bytes += size
            rows.append(
                {
                    "relative_path": str(note.relative_path),
                    "title": str(note.title),
                    "source_hash": str(payload.get("source_hash") or ""),
                    "text": str(payload.get("text") or ""),
                    "size_bytes": size,
                }
            )
        return tuple(rows)

    def connect_vault(self, vault_path: Any) -> Dict[str, Any]:
        raw = str(vault_path or "").strip()
        if not raw:
            raise ObsidianWorkspaceValidationError("Choose an Obsidian vault folder.")
        try:
            normalized = self.config_api.normalize_vault_path(raw)
            candidate = Path(normalized)
            if candidate.is_symlink():
                raise ObsidianWorkspaceValidationError(
                    "Choose an existing Obsidian vault folder containing a .obsidian directory."
                )
            valid, _message = self.config_api.validate_vault_path(normalized)
            if not valid:
                raise ObsidianWorkspaceValidationError(
                    "Choose an existing Obsidian vault folder containing a .obsidian directory."
                )
            success, result = self.config_api.set_vault_path(normalized)
        except ObsidianWorkspaceValidationError:
            raise
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError(
                "Obsidian configuration could not be updated."
            ) from error
        if not success:
            raise ObsidianWorkspaceValidationError(
                "Choose an existing Obsidian vault folder containing a .obsidian directory."
            )
        return {"vault_path": str(result), "enabled": True}

    def enable_vault(self) -> Dict[str, Any]:
        config = self._load_config()
        vault_path = _configured_path(config)
        if not vault_path or not self._path_is_valid(vault_path):
            raise ObsidianWorkspaceValidationError(
                "Choose an existing Obsidian vault folder containing a .obsidian directory."
            )
        try:
            success, result = self.config_api.enable_vault()
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError(
                "Obsidian configuration could not be updated."
            ) from error
        if not success:
            raise ObsidianWorkspaceValidationError(
                "Choose an existing Obsidian vault folder containing a .obsidian directory."
            )
        return {"vault_path": str(result), "enabled": True}

    def disable_vault(self) -> Dict[str, Any]:
        try:
            self.config_api.disable_vault()
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError(
                "Obsidian configuration could not be updated."
            ) from error
        return {"enabled": False}


def build_obsidian_workspace_service() -> ObsidianWorkspaceService:
    """Build the workspace lazily so Flask startup never touches the vault."""
    config_api = import_module("obsidian_integration")
    reader_module = import_module(
        "personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader"
    )
    return ObsidianWorkspaceService(
        config_api,
        reader_module.ObsidianWorkspaceReader,
    )
