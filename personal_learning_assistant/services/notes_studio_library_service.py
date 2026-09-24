"""Visual Notes Library read boundary for Phase 7.5.15.2.

The library consumes the canonical Phase 7.5.15.1 NoteCard model. It performs
metadata-only filtering and never opens note bodies, invokes AI, mutates the
vault, or changes legacy note storage.
"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from personal_learning_assistant.services.notes_studio_read_service import (
    NotesStudioReadService,
    NotesStudioReadUnavailableError,
)


MAX_LIBRARY_QUERY_CHARS = 200
MAX_LEGACY_TITLES = 100


class NotesStudioLibraryUnavailableError(RuntimeError):
    """The canonical Notes Studio library cannot be read safely."""


def _clean(value: Any, *, limit: int = MAX_LIBRARY_QUERY_CHARS) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _key(value: Any) -> str:
    return _clean(value).casefold()


def _unique(values: Iterable[str]):
    by_key = {}
    for raw in values:
        value = _clean(raw)
        if value:
            by_key.setdefault(value.casefold(), value)
    return [by_key[item] for item in sorted(by_key)]


def _date_label(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return text
    return parsed.strftime("%d %b %Y").lstrip("0")


def _card_row(card) -> dict:
    return {
        "identity": str(card.identity),
        "relative_path": str(card.relative_path),
        "source_hash": str(card.source_hash),
        "title": str(card.title),
        "topic": str(card.topic),
        "course": str(card.course),
        "note_type": str(card.note_type or "note"),
        "note_date": str(card.note_date),
        "note_date_label": _date_label(card.note_date),
        "card_summary": [str(item) for item in tuple(card.card_summary or ())[:5]],
        "tags": [str(item) for item in (card.tags or ())],
        "revision_status": str(card.revision_status or "unreviewed"),
    }


def _search_scope(card: Mapping[str, object]) -> str:
    values = [
        card.get("title", ""),
        card.get("topic", ""),
        card.get("course", ""),
        card.get("note_type", ""),
        card.get("revision_status", ""),
    ]
    values.extend(card.get("tags", ()) or ())
    values.extend(card.get("card_summary", ()) or ())
    return "\n".join(str(item) for item in values).casefold()


class NotesStudioLibraryWebService:
    """Build compact, filterable Notes Studio cards from canonical read models."""

    def __init__(self, read_service, legacy_service=None):
        self.read_service = read_service
        self.legacy_service = legacy_service

    def _legacy_notes(self):
        if self.legacy_service is None:
            return []
        try:
            workspace = self.legacy_service.notes_workspace()
        except Exception:
            return []
        rows = []
        for item in list(workspace.get("notes", ()))[:MAX_LEGACY_TITLES]:
            rows.append(
                {
                    "position": int(item.get("position", 0) or 0),
                    "title": str(item.get("title", "") or ""),
                    "topic": str(item.get("topic", "") or ""),
                    "difficulty": str(item.get("difficulty", "") or ""),
                }
            )
        return rows

    def workspace(self, *, search="", course="", note_type="", tag=""):
        query = {
            "search": _clean(search),
            "course": _clean(course),
            "note_type": _clean(note_type),
            "tag": _clean(tag),
        }
        try:
            cards = tuple(self.read_service.list_cards())
        except Exception as error:
            raise NotesStudioLibraryUnavailableError(
                "Notes Studio is temporarily unavailable."
            ) from error

        rows = [_card_row(card) for card in cards]
        options = {
            "courses": _unique(row["course"] for row in rows),
            "note_types": _unique(row["note_type"] for row in rows),
            "tags": _unique(tag_value for row in rows for tag_value in row["tags"]),
        }

        search_key = _key(query["search"])
        course_key = _key(query["course"])
        type_key = _key(query["note_type"])
        tag_key = _key(query["tag"])

        filtered = []
        for row in rows:
            if search_key and search_key not in _search_scope(row):
                continue
            if course_key and _key(row["course"]) != course_key:
                continue
            if type_key and _key(row["note_type"]) != type_key:
                continue
            if tag_key and not any(_key(item) == tag_key for item in row["tags"]):
                continue
            filtered.append(row)

        legacy_notes = self._legacy_notes()
        return {
            "available": True,
            "message": "",
            "cards": filtered,
            "legacy_notes": legacy_notes,
            "summary": {
                "total": len(rows),
                "displayed": len(filtered),
                "courses": len(options["courses"]),
                "types": len(options["note_types"]),
                "legacy": len(legacy_notes),
            },
            "query": query,
            "filter_options": options,
        }


def unavailable_notes_studio_library(message: str = "") -> dict:
    return {
        "available": False,
        "message": message
        or "Notes Studio is temporarily unavailable. Your notes were not changed.",
        "cards": [],
        "legacy_notes": [],
        "summary": {
            "total": 0,
            "displayed": 0,
            "courses": 0,
            "types": 0,
            "legacy": 0,
        },
        "query": {"search": "", "course": "", "note_type": "", "tag": ""},
        "filter_options": {"courses": [], "note_types": [], "tags": []},
    }


def build_notes_studio_library_web_service() -> NotesStudioLibraryWebService:
    """Build the library lazily around the existing safe Obsidian reader."""
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

    read_service = NotesStudioReadService(configured_reader)

    # Legacy JSON remains a compatibility source only. Its bodies are never
    # copied into the rich card model or rendered by the visual library.
    legacy_module = import_module(
        "personal_learning_assistant.services.notes_resources_web_service"
    )
    return NotesStudioLibraryWebService(
        read_service,
        legacy_module.build_notes_resources_web_service(),
    )
