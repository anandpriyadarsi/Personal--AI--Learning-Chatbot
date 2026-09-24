"""Read-only rich-image access for Notes Studio Phase 7.5.15.5."""
from __future__ import annotations

from importlib import import_module
from personal_learning_assistant.services.notes_studio_read_service import (
    build_configured_notes_studio_read_service,
)


class NotesStudioAssetError(RuntimeError):
    pass


class NotesStudioAssetNotFoundError(NotesStudioAssetError):
    pass


class NotesStudioAssetUnavailableError(NotesStudioAssetError):
    pass


class NotesStudioAssetService:
    """Serve existing safe raster assets from the configured vault without writes."""

    def __init__(self, reader_factory):
        self.reader_factory = reader_factory

    def read_asset(self, relative_path):
        reader_module = import_module(
            "personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader"
        )
        try:
            reader = self.reader_factory()
            return reader.read_asset(relative_path)
        except reader_module.ObsidianWorkspacePathError as error:
            raise NotesStudioAssetNotFoundError(
                "That image was not found in the current Notes Studio vault."
            ) from error
        except reader_module.ObsidianWorkspaceReadError as error:
            raise NotesStudioAssetUnavailableError(
                "The image could not be read safely."
            ) from error
        except Exception as error:
            raise NotesStudioAssetUnavailableError(
                "The image could not be read safely."
            ) from error


def build_notes_studio_asset_service() -> NotesStudioAssetService:
    read_service = build_configured_notes_studio_read_service()
    return NotesStudioAssetService(read_service.reader_factory)
