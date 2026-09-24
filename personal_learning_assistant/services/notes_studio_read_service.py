"""Canonical read-only Notes Studio boundary for Phase 7.5.15.1.

Markdown in the configured Obsidian vault remains authoritative. This service
composes the existing scanner and hash-checked workspace reader; it performs no
adoption, registry refresh, indexing, persistence, or note mutation.
"""
from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path
from typing import Mapping

from personal_learning_assistant.domain.notes_studio_read_models import NoteCard, NoteDetail
from personal_learning_assistant.services.notes_studio_connections_service import (
    build_connection_context,
)


class NotesStudioReadError(RuntimeError):
    pass


class NotesStudioReadNotFoundError(NotesStudioReadError):
    pass


class NotesStudioReadUnavailableError(NotesStudioReadError):
    pass


def _frontmatter_values(raw_frontmatter: object) -> Mapping[str, object]:
    """Parse only the small metadata subset already supported by ANVAYA.

    This intentionally is not a general YAML parser. It supports scalar values
    and simple list/list-item forms so read semantics stay deterministic.
    """
    lines = str(raw_frontmatter or "").splitlines()
    values = {}
    current = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw[:1].isspace() and stripped.startswith("-") and current:
            item = stripped[1:].strip().strip("'\"")
            if item:
                existing = values.get(current)
                if not isinstance(existing, list):
                    existing = []
                existing.append(item)
                values[current] = existing
            continue
        if ":" not in raw:
            current = None
            continue
        key, value = raw.split(":", 1)
        key = key.strip().casefold()
        current = key or None
        if not current:
            continue
        value = value.strip()
        if not value:
            values.setdefault(current, [])
            continue
        if value.startswith("[") and value.endswith("]"):
            values[current] = [
                item.strip().strip("'\"")
                for item in value[1:-1].split(",")
                if item.strip().strip("'\"")
            ]
        else:
            values[current] = value.strip("'\"")
    return values


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if isinstance(value, list):
        return ""
    return str(value or "").strip()


def _summary(values: Mapping[str, object]):
    value = values.get("card_summary", ())
    if isinstance(value, str):
        candidates = (value,)
    elif isinstance(value, list):
        candidates = tuple(value)
    else:
        candidates = ()
    cleaned = []
    for item in candidates:
        text = " ".join(str(item or "").split())
        if text:
            cleaned.append(text)
        if len(cleaned) == 5:
            break
    return tuple(cleaned)


def _identity(note) -> str:
    assistant_id = str(note.assistant_id or "").strip()
    if assistant_id:
        return "assistant:" + assistant_id
    path = str(note.relative_path).replace("\\", "/")
    return "vault-note:{}@{}".format(path, str(note.source_hash or "").lower())


class NotesStudioReadService:
    """Compose rich card/detail reads from the existing safe vault reader."""

    def __init__(self, reader_factory):
        self.reader_factory = reader_factory

    def _reader_and_scan(self):
        try:
            reader = self.reader_factory()
            scan = reader.scan()
            return reader, scan
        except Exception as error:
            raise NotesStudioReadUnavailableError(
                "The Notes Studio vault could not be scanned safely."
            ) from error

    @staticmethod
    def _card(note) -> NoteCard:
        extra = dict(note.frontmatter_extra or {})
        values = _frontmatter_values(extra.get("raw_frontmatter", ""))
        note_date = _text(values, "note_date") or _text(values, "date")
        source = (
            _text(values, "source")
            or _text(values, "source_title")
            or _text(values, "source_name")
        )
        return NoteCard(
            identity=_identity(note),
            relative_path=str(note.relative_path),
            source_hash=str(note.source_hash),
            title=str(note.title),
            topic=_text(values, "topic"),
            course=_text(values, "course"),
            note_type=str(note.note_type or "note"),
            note_date=note_date,
            card_summary=_summary(values),
            tags=tuple(str(item) for item in (note.tags or ())),
            revision_status=str(note.revision_status or "unreviewed"),
            source=source,
        )

    def list_cards(self):
        _reader, scan = self._reader_and_scan()
        return tuple(self._card(note) for note in scan.notes)

    def get_detail(self, relative_path: str) -> NoteDetail:
        reader, scan = self._reader_and_scan()
        requested = str(relative_path or "").strip().replace("\\", "/")
        note = next(
            (
                item
                for item in scan.notes
                if str(item.relative_path).replace("\\", "/").casefold()
                == requested.casefold()
            ),
            None,
        )
        if note is None:
            raise NotesStudioReadNotFoundError("That Markdown note was not found.")

        try:
            payload = reader.read_note(
                str(note.relative_path),
                expected_hash=str(note.source_hash or ""),
            )
        except Exception as error:
            raise NotesStudioReadUnavailableError(
                "The note changed or could not be read safely."
            ) from error

        # Reuse the established live-link algorithm without creating registry state.
        from personal_learning_assistant.services.obsidian_workspace_service import (
            ObsidianWorkspaceService,
        )

        links = ObsidianWorkspaceService._link_context(
            ObsidianWorkspaceService.__new__(ObsidianWorkspaceService),
            reader,
            scan,
            str(note.relative_path),
            str(payload["text"]),
        )
        current_card = self._card(note)
        cards = tuple(self._card(item) for item in scan.notes)
        connections = build_connection_context(
            current_card,
            cards,
            wikilinks=tuple(links["outgoing"]),
            backlinks=tuple(links["backlinks"]),
        )
        return NoteDetail(
            card=current_card,
            text=str(payload["text"]),
            wikilinks=tuple(links["outgoing"]),
            backlinks=tuple(links["backlinks"]),
            related_notes=tuple(connections["related_notes"]),
            connection_facets=tuple(connections["facets"]),
        )


def build_configured_notes_studio_read_service() -> NotesStudioReadService:
    """Build the canonical read service lazily from the configured Obsidian vault."""

    config_api = import_module("obsidian_integration")
    reader_module = import_module(
        "personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader"
    )

    def configured_reader():
        try:
            config = config_api.load_config()
            config = dict(config) if isinstance(config, dict) else {}
            vault_path = str(config.get("vault_path") or "").strip()
            if not vault_path or not bool(config.get("enabled", False)):
                raise NotesStudioReadUnavailableError(
                    "Connect and enable an Obsidian vault before opening Notes Studio."
                )
            candidate = Path(vault_path)
            if candidate.is_symlink():
                raise NotesStudioReadUnavailableError(
                    "The configured Obsidian vault is unavailable."
                )
            valid, _message = config_api.validate_vault_path(vault_path)
            if not valid:
                raise NotesStudioReadUnavailableError(
                    "The configured Obsidian vault is unavailable."
                )
            return reader_module.ObsidianWorkspaceReader(
                vault_path,
                vault_key="obsidian-vault",
            )
        except NotesStudioReadUnavailableError:
            raise
        except Exception as error:
            raise NotesStudioReadUnavailableError(
                "The configured Obsidian vault is unavailable."
            ) from error

    return NotesStudioReadService(configured_reader)
