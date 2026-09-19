"""Read-only Notes + Resources adapters for the local web interface.

Phase 7.5.7 projects the existing Phase 2 service results into browser-friendly
models. Notes/resources services and JSON repositories are imported only when
the corresponding page is requested. This module never creates notes,
resources, or status updates.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any
from urllib.parse import urlsplit


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_external_link(value: Any) -> str:
    """Return only an explicit HTTP(S) URL for an active browser link."""
    text = _text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return text


def build_notes_dashboard(result: Any) -> dict[str, Any]:
    """Normalize a NotesService list/search result without mutating note storage."""
    raw_notes = tuple(_value(result, "notes", ()) or ())
    notes: list[dict[str, Any]] = []
    topics: set[str] = set()
    difficulties: set[str] = set()

    for raw in raw_notes:
        topic = _text(_value(raw, "topic"), "Uncategorized")
        difficulty = _text(_value(raw, "difficulty"), "Unspecified")
        notes.append(
            {
                "position": int(
                    _value(raw, "position", len(notes) + 1) or len(notes) + 1
                ),
                "title": _text(_value(raw, "title"), "Untitled note"),
                "topic": topic,
                "difficulty": difficulty,
                "content": _text(_value(raw, "content")),
            }
        )
        topics.add(topic.casefold())
        difficulties.add(difficulty.casefold())

    return {
        "available": True,
        "message": "",
        "summary": {
            "total": len(notes),
            "topics": len(topics),
            "difficulties": len(difficulties),
        },
        "notes": notes,
    }


def build_resources_dashboard(result: Any) -> dict[str, Any]:
    """Normalize a ResourceService list result without mutating resource storage."""
    raw_resources = tuple(_value(result, "resources", ()) or ())
    resources: list[dict[str, Any]] = []
    types: set[str] = set()
    status_counts = {
        "not_started": 0,
        "in_progress": 0,
        "completed": 0,
    }

    for raw in raw_resources:
        resource_type = _text(_value(raw, "resource_type"), "Resource")
        status = _text(_value(raw, "status"), "Not Started")
        status_key = status.casefold().replace("-", " ").replace("_", " ")
        status_key = "_".join(status_key.split())
        if status_key in status_counts:
            status_counts[status_key] += 1

        link = _text(_value(raw, "link"))
        resources.append(
            {
                "position": int(
                    _value(raw, "position", len(resources) + 1)
                    or len(resources) + 1
                ),
                "title": _text(_value(raw, "title"), "Untitled resource"),
                "resource_type": resource_type,
                "link": link,
                "link_url": _safe_external_link(link),
                "status": status,
            }
        )
        types.add(resource_type.casefold())

    return {
        "available": True,
        "message": "",
        "summary": {
            "total": len(resources),
            "types": len(types),
            **status_counts,
        },
        "resources": resources,
    }


def load_notes_dashboard() -> dict[str, Any]:
    """Read notes through the existing NotesService boundary."""
    service_module = import_module("personal_learning_assistant.services.notes_service")
    repository_module = import_module(
        "personal_learning_assistant.repositories.json.note_repository"
    )
    service = service_module.NotesService(repository_module.LegacyJsonNoteRepository())
    return build_notes_dashboard(service.list_notes())


def load_resources_dashboard() -> dict[str, Any]:
    """Read resources through the existing ResourceService boundary."""
    service_module = import_module("personal_learning_assistant.services.resource_service")
    repository_module = import_module(
        "personal_learning_assistant.repositories.json.resource_repository"
    )
    service = service_module.ResourceService(
        repository_module.LegacyJsonResourceRepository()
    )
    return build_resources_dashboard(service.list_resources())


def unavailable_notes_dashboard() -> dict[str, Any]:
    return {
        "available": False,
        "message": "Notes are temporarily unavailable. Your academic data was not changed.",
        "summary": {"total": 0, "topics": 0, "difficulties": 0},
        "notes": [],
    }


def unavailable_resources_dashboard() -> dict[str, Any]:
    return {
        "available": False,
        "message": "Resources are temporarily unavailable. Your academic data was not changed.",
        "summary": {
            "total": 0,
            "types": 0,
            "not_started": 0,
            "in_progress": 0,
            "completed": 0,
        },
        "resources": [],
    }
