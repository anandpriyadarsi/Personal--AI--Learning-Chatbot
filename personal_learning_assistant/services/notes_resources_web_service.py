"""Operational Notes + Resources boundary for the ANVAYA web interface.

Phase 7.5.11 keeps legacy JSON authority and delegates all persistence to the
existing non-interactive NotesService and ResourceService. This module owns
web-facing validation, query normalization, and safe exception mapping.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from personal_learning_assistant.domain.note_models import (
    CreateNoteCommand,
    ListNotesQuery,
    SearchNotesQuery,
    UpdateNoteCommand,
)
from personal_learning_assistant.domain.resource_models import (
    CreateResourceCommand,
    ListResourcesQuery,
    SearchResourcesQuery,
    UpdateResourceStatusCommand,
)
from personal_learning_assistant.services.notes_resources_dashboard_service import (
    build_notes_dashboard,
    build_resources_dashboard,
)


class NotesResourcesWebValidationError(ValueError):
    """The browser request is invalid and no write should occur."""


class NotesResourcesWebNotFoundError(LookupError):
    """A requested note/resource position does not exist."""


class NotesResourcesWebUnavailableError(RuntimeError):
    """Storage/service failure mapped to a safe browser-visible condition."""


def _optional_filter(value: Any):
    text = str(value or "").strip()
    return text or None


def _positive_position(value: Any) -> int:
    try:
        position = int(value)
    except (TypeError, ValueError) as error:
        raise NotesResourcesWebValidationError("Position must be a positive integer.") from error
    if position < 1:
        raise NotesResourcesWebValidationError("Position must be a positive integer.")
    return position


class NotesResourcesWebService:
    """Daily-use Notes/Resources operations for Flask routes."""

    def __init__(self, notes_service, resource_service):
        self.notes_service = notes_service
        self.resource_service = resource_service

    def notes_workspace(self, search="", topic="", difficulty=""):
        search_text = str(search or "").strip()
        topic_text = str(topic or "").strip()
        difficulty_text = str(difficulty or "").strip()
        try:
            if search_text:
                result = self.notes_service.search_notes(
                    SearchNotesQuery(
                        text=search_text,
                        topic=_optional_filter(topic_text),
                        difficulty=_optional_filter(difficulty_text),
                    )
                )
            else:
                result = self.notes_service.list_notes(
                    ListNotesQuery(
                        topic=_optional_filter(topic_text),
                        difficulty=_optional_filter(difficulty_text),
                    )
                )
            workspace = build_notes_dashboard(result)
        except Exception as error:
            raise NotesResourcesWebUnavailableError(
                "Notes are temporarily unavailable."
            ) from error
        workspace["query"] = {
            "search": search_text,
            "topic": topic_text,
            "difficulty": difficulty_text,
        }
        return workspace

    def resources_workspace(self, search="", resource_type="", status=""):
        search_text = str(search or "").strip()
        type_text = str(resource_type or "").strip()
        status_text = str(status or "").strip()
        try:
            if search_text:
                result = self.resource_service.search_resources(
                    SearchResourcesQuery(
                        text=search_text,
                        resource_type=_optional_filter(type_text),
                        status=_optional_filter(status_text),
                    )
                )
            else:
                result = self.resource_service.list_resources(
                    ListResourcesQuery(
                        resource_type=_optional_filter(type_text),
                        status=_optional_filter(status_text),
                    )
                )
            workspace = build_resources_dashboard(result)
        except Exception as error:
            raise NotesResourcesWebUnavailableError(
                "Resources are temporarily unavailable."
            ) from error
        workspace["query"] = {
            "search": search_text,
            "type": type_text,
            "status": status_text,
        }
        return workspace

    def create_note(self, title, topic, difficulty, content):
        title_text = str(title or "").strip()
        if not title_text:
            raise NotesResourcesWebValidationError("Note title is required.")
        topic_text = str(topic or "").strip() or "Uncategorized"
        difficulty_text = str(difficulty or "").strip() or "Unspecified"
        content_text = str(content or "")
        try:
            return self.notes_service.create_note(
                CreateNoteCommand(
                    title=title_text,
                    topic=topic_text,
                    difficulty=difficulty_text,
                    content=content_text,
                )
            )
        except Exception as error:
            raise NotesResourcesWebUnavailableError(
                "The note could not be saved."
            ) from error

    def update_note(self, position, title, topic, difficulty, content):
        note_position = _positive_position(position)
        title_text = str(title or "").strip()
        if not title_text:
            raise NotesResourcesWebValidationError("Note title is required.")
        topic_text = str(topic or "").strip() or "Uncategorized"
        difficulty_text = str(difficulty or "").strip() or "Unspecified"
        content_text = str(content or "")
        try:
            return self.notes_service.update_note(
                UpdateNoteCommand(
                    position=note_position,
                    title=title_text,
                    topic=topic_text,
                    difficulty=difficulty_text,
                    content=content_text,
                )
            )
        except IndexError as error:
            raise NotesResourcesWebNotFoundError("Note was not found.") from error
        except Exception as error:
            raise NotesResourcesWebUnavailableError(
                "The note could not be updated."
            ) from error

    def create_resource(self, title, resource_type, link):
        title_text = str(title or "").strip()
        if not title_text:
            raise NotesResourcesWebValidationError("Resource title is required.")
        type_text = str(resource_type or "").strip() or "Resource"
        link_text = str(link or "").strip()
        try:
            return self.resource_service.create_resource(
                CreateResourceCommand(
                    title=title_text,
                    resource_type=type_text,
                    link=link_text,
                )
            )
        except Exception as error:
            raise NotesResourcesWebUnavailableError(
                "The resource could not be saved."
            ) from error

    def update_resource_status(self, position, status):
        resource_position = _positive_position(position)
        status_text = str(status or "").strip()
        if not status_text:
            raise NotesResourcesWebValidationError("Resource status is required.")
        try:
            return self.resource_service.update_status(
                UpdateResourceStatusCommand(
                    position=resource_position,
                    status=status_text,
                )
            )
        except ValueError as error:
            raise NotesResourcesWebValidationError(
                "Resource status is invalid."
            ) from error
        except IndexError as error:
            raise NotesResourcesWebNotFoundError(
                "Resource was not found."
            ) from error
        except Exception as error:
            raise NotesResourcesWebUnavailableError(
                "The resource could not be updated."
            ) from error


def build_notes_resources_web_service():
    """Construct the operational boundary lazily from current authoritative services."""
    notes_module = import_module("personal_learning_assistant.services.notes_service")
    resources_module = import_module("personal_learning_assistant.services.resource_service")
    note_repository_module = import_module(
        "personal_learning_assistant.repositories.json.note_repository"
    )
    resource_repository_module = import_module(
        "personal_learning_assistant.repositories.json.resource_repository"
    )
    return NotesResourcesWebService(
        notes_service=notes_module.NotesService(
            note_repository_module.LegacyJsonNoteRepository()
        ),
        resource_service=resources_module.ResourceService(
            resource_repository_module.LegacyJsonResourceRepository()
        ),
    )
