"""Phase 7.5.12 browser-facing Obsidian workspace boundary.

This module is intentionally thin at import time. It does not import the legacy
Obsidian configuration module or filesystem reader until the factory is called.
"""
from __future__ import annotations

import hashlib
import os
import re
import posixpath
import uuid
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
        self._scan_cache = None

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
            scan = self._scan(reader, config)
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

    def _scan(self, reader, config):
        from .obsidian_manifest_service import manifest_scan
        manifest = config.get("source_manifest")
        if manifest and config.get("connection_id") == manifest.get("connection_id"):
            return manifest_scan(manifest)
        key = (_configured_path(config), config.get("connection_id"))
        if self._scan_cache is None or self._scan_cache[0] != key:
            self._scan_cache = (key, reader.scan())
        return self._scan_cache[1]

    def refresh_manifest(self):
        from .obsidian_manifest_service import build_manifest
        config = self._load_config()
        path = _configured_path(config)
        if not path or not self._path_is_valid(path):
            raise ObsidianWorkspaceValidationError("Connect a valid vault before refreshing.")
        scan = self._reader(path).scan()
        manifest = build_manifest(scan, config.get("source_manifest"), connection_id=config.get("connection_id"))
        if not config.get('source_manifest'):
            from .study_item_resolver import obsidian_identity
            prior_vault = ('vault:' + hashlib.sha256(str(config['connection_id']).encode()).hexdigest()
                           if config.get('connection_id') else _vault_identity(path))
            for row in manifest['items']:
                identity = obsidian_identity({'vault_identity': prior_vault, 'relative_path': row['relative_path'], 'source_hash': row['source_hash']})
                row['legacy_reference'] = {'vault_identity': prior_vault, 'note_identity': identity.item_id}
        config.update(connection_id=manifest["connection_id"], source_manifest=manifest)
        self.config_api.save_config(config)
        self._scan_cache = None
        return manifest

    def relocate_connection(self, vault_path, *, expected_connection_id):
        config = self._load_config()
        manifest = config.get('source_manifest') or {}
        if (not manifest or config.get('connection_mode', 'folder') != 'folder'
                or config.get('connection_id') != expected_connection_id):
            raise ObsidianWorkspaceValidationError('Refresh and review the current folder connection before relocating it.')
        candidate = Path(str(vault_path or '').strip()).expanduser().absolute()
        if not self._path_is_valid(str(candidate)):
            raise ObsidianWorkspaceValidationError('Choose an available vault folder.')
        scan = self._reader(str(candidate)).scan()
        expected = {row['relative_path']: row['source_hash'] for row in manifest['items'] if row.get('state') != 'missing'}
        observed = {row.relative_path: row.source_hash for row in scan.notes}
        if expected != observed:
            raise ObsidianWorkspaceValidationError('The destination differs from the saved manifest. Refresh the original connection or choose Replace connection.')
        config['vault_path'] = str(candidate)
        self.config_api.save_config(config)
        self._scan_cache = None
        return {'connection_id': expected_connection_id, 'relocated': True}

    def confirm_rename(self, old_path, new_path, *, expected_hash):
        old_path = _normalize_requested_note_path(old_path)
        new_path = _normalize_requested_note_path(new_path)
        config = self._load_config()
        manifest = config.get("source_manifest") or {}
        items = manifest.get("items", [])
        old = next((row for row in items if row["relative_path"] == old_path), None)
        if not old or old.get("state") == "conflict" or old["source_hash"] != expected_hash:
            raise ObsidianWorkspaceValidationError("Refresh the manifest and confirm the source version.")
        if any(row["relative_path"] == new_path and row.get("state") != "missing" for row in items):
            raise ObsidianWorkspaceValidationError("The destination already has a distinct source identity.")
        reader = self._reader(_configured_path(config))
        reader.read_note(new_path, expected_hash=expected_hash)
        try:
            reader.read_note(old_path)
        except Exception:
            pass
        else:
            raise ObsidianWorkspaceValidationError("Both paths still exist; copies cannot be merged as a rename.")
        old["relative_path"] = new_path
        manifest.setdefault("aliases", []).append({"old_path": old_path, "item_id": old["id"], "provenance": "user_confirmed"})
        config["source_manifest"] = manifest
        self.config_api.save_config(config)
        return self.refresh_manifest()

    @staticmethod
    def _resolve_relative(target, lookup, current_path):
        normalized = unicodedata.normalize("NFC", str(target).replace("\\", "/")).casefold()
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(current_path), normalized))
        for key in (relative, normalized):
            if key.startswith("../") or key.startswith("/"):
                continue
            candidates = lookup.get(key, ()) or lookup.get(key + ".md", ())
            exact = {item.relative_path: item for item in candidates if item.relative_path.casefold() in {key, key + ".md"}}
            if len(exact) == 1:
                return next(iter(exact.values())), False
            if len(exact) > 1:
                return None, True
        return ObsidianWorkspaceService._resolve_link(target, lookup)

    def _link_context(self, reader, scan, current_path: str, source: str):
        lookup = self._link_lookup(scan)
        outgoing, backlinks = [], []
        for candidate in scan.notes:
            for link in candidate.links:
                if link.target_kind not in {"wiki", "markdown", "note", "wikilink", "internal"}:
                    continue
                parts = self._wikilink_parts(link.raw_target)
                resolved, ambiguous = self._resolve_relative(parts["target"], lookup, candidate.relative_path)
                if candidate.relative_path == current_path:
                    if link.target_kind == "wiki":
                        try:
                            line, column = (int(value) for value in link.source_position.split(":"))
                            match = _WIKILINK.match(source.splitlines()[line - 1][column - 1:])
                            if match:
                                parts = self._wikilink_parts(match.group(1))
                        except (ValueError, IndexError):
                            pass
                    outgoing.append({**parts, "heading": link.heading or parts["heading"], "block_id": link.block_id,
                                     "resolved_path": resolved.relative_path if resolved else "",
                                     "resolved_title": resolved.title if resolved else "", "ambiguous": ambiguous})
                elif resolved and resolved.relative_path == current_path:
                    if not any(row["relative_path"] == candidate.relative_path for row in backlinks):
                        backlinks.append({"relative_path": candidate.relative_path, "title": candidate.title})
        return {"outgoing": tuple(outgoing), "backlinks": tuple(backlinks)}

    def validate_note_version(self, relative_path, source_hash=""):
        requested = _normalize_requested_note_path(relative_path)
        config = self._load_config()
        manifest = config.get("source_manifest") or {}
        if not manifest:
            return self.note_preview(requested, decorate=False, expected_hash=source_hash)
        if not config.get("enabled") or not self._path_is_valid(_configured_path(config)):
            raise ObsidianWorkspaceValidationError("Connect an available vault first.")
        row = next((item for item in manifest.get("items", []) if item["relative_path"] == requested and item.get("state") != "missing"), None)
        if row is None:
            raise ObsidianWorkspaceNotFoundError("Source is missing from the saved manifest. Refresh explicitly after changing paths.")
        try:
            payload = self._reader(_configured_path(config)).read_note(requested, expected_hash=source_hash or row["source_hash"])
        except Exception as error:
            raise ObsidianWorkspaceUnavailableError("The selected source changed or is missing. Refresh its manifest before retrying.") from error
        return {"title": row["title"], "relative_path": requested, "assistant_id": row.get("assistant_id"),
                "source_hash": payload["source_hash"], "text": payload["text"], "size_bytes": payload["size_bytes"],
                "vault_identity": "vault:" + hashlib.sha256(str(config["connection_id"]).encode()).hexdigest(),
                "vault_name": manifest["vault_name"], "connection_id": config["connection_id"],
                "source_item_id": row["id"], "identity_conflict": row.get("state") == "conflict"}

    def read_asset(self, relative_path):
        config = self._load_config()
        if not config.get("enabled") or not self._path_is_valid(_configured_path(config)):
            raise ObsidianWorkspaceValidationError("Connect an available vault first.")
        return self._reader(_configured_path(config)).read_asset(relative_path)

    def note_preview(self, relative_path: Any, *, decorate=True, expected_hash="") -> Dict[str, Any]:
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
            scan = self._scan(reader, config)
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
                expected_hash=expected_hash or str(note.source_hash or ""),
            )
        except Exception as error:
            # Invalid paths are already filtered above; runtime read conflicts are
            # presented as availability failures to avoid leaking filesystem detail.
            raise ObsidianWorkspaceUnavailableError(
                "The selected note changed or could not be read safely. Refresh the vault and try again."
            ) from error

        link_context = self._link_context(reader, scan, str(note.relative_path), str(payload["text"])) if decorate else {"outgoing": (), "backlinks": ()}
        manifest = config.get("source_manifest") or {}
        item = next((row for row in manifest.get("items", []) if row["relative_path"] == note.relative_path), {})
        connection_id = config.get("connection_id")
        conflict = bool(note.assistant_id and sum(other.assistant_id == note.assistant_id for other in scan.notes) > 1)
        stable_vault = "vault:" + hashlib.sha256(str(connection_id).encode()).hexdigest() if connection_id else _vault_identity(vault_path)
        return {
            "title": str(note.title),
            "relative_path": str(note.relative_path),
            "assistant_id": (
                None if note.assistant_id is None else str(note.assistant_id)
            ),
            "vault_name": str(scan.vault_name),
            "vault_identity": stable_vault,
            "connection_id": connection_id,
            "source_item_id": item.get("id"),
            "identity_conflict": conflict,
            "legacy_reference": item.get('legacy_reference'),
            "manifest_revision": manifest.get("revision"),
            "manifest_observed_at": manifest.get("observed_at", ""),
            "tags": [str(item) for item in (note.tags or ())],
            "note_type": str(note.note_type or "note"),
            "revision_status": str(note.revision_status or "unreviewed"),
            "source_hash": str(payload["source_hash"]),
            "size_bytes": int(payload["size_bytes"]),
            "text": str(payload["text"]),
            "wikilinks": link_context["outgoing"],
            "backlinks": link_context["backlinks"],
        }

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
            if callable(getattr(self.config_api, "save_config", None)):
                from .obsidian_manifest_service import build_manifest
                scan = self._reader(normalized).scan()
                config = self._load_config()
                connection_id = str(uuid.uuid4())
                manifest = build_manifest(scan, connection_id=connection_id)
                config.update(vault_path=normalized, enabled=True, connection_mode="folder", connection_id=connection_id, source_manifest=manifest)
                for key in ("snapshot_id", "snapshot_name", "snapshot_imported_at", "snapshot_exclusions"):
                    config.pop(key, None)
                self.config_api.save_config(config)
                self._scan_cache = None
                success, result = True, normalized
            else:
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
