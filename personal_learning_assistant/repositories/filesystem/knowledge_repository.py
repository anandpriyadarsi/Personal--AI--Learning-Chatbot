"""Filesystem-backed legacy knowledge discovery adapter.

This adapter knows files and the configured Obsidian vault. It deliberately
knows nothing about courses, course_manager, RAG, or terminal presentation.
"""

from __future__ import annotations

import os
from typing import Callable, Iterable, Optional, Union

from knowledge_paths import BASE_DIR
from obsidian_integration import (
    get_obsidian_markdown_files,
    get_vault_path,
)

from personal_learning_assistant.repositories.interfaces import (
    KnowledgeRepository,
)


SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


class LegacyFileKnowledgeRepository:
    """Read-only discovery adapter over existing folders and Obsidian."""

    def __init__(
        self,
        base_dir: Optional[Union[str, os.PathLike]] = None,
        local_folders: Optional[
            Iterable[Union[str, os.PathLike]]
        ] = None,
        obsidian_files_provider: Optional[
            Callable[[], Iterable[str]]
        ] = None,
        vault_path_provider: Optional[
            Callable[[], Optional[str]]
        ] = None,
    ):
        self.base_dir = os.path.abspath(
            os.fspath(base_dir)
            if base_dir is not None
            else BASE_DIR
        )

        if local_folders is None:
            knowledge_dir = os.path.join(
                self.base_dir,
                "knowledge",
            )
            local_folders = (
                os.path.join(
                    knowledge_dir,
                    "obsidian",
                ),
                os.path.join(
                    knowledge_dir,
                    "documents",
                ),
            )

        self.local_folders = tuple(
            os.path.abspath(os.fspath(path))
            for path in local_folders
        )
        self.obsidian_files_provider = (
            obsidian_files_provider
            or get_obsidian_markdown_files
        )
        self.vault_path_provider = (
            vault_path_provider
            or get_vault_path
        )

    def list_document_paths(self):
        paths = []

        for folder in self.local_folders:
            if not os.path.isdir(folder):
                continue

            for root, _dirs, files in os.walk(folder):
                for file_name in files:
                    extension = os.path.splitext(
                        file_name
                    )[1].lower()

                    if extension not in SUPPORTED_EXTENSIONS:
                        continue

                    paths.append(
                        os.path.abspath(
                            os.path.join(
                                root,
                                file_name,
                            )
                        )
                    )

        try:
            obsidian_paths = (
                self.obsidian_files_provider()
                or []
            )
        except OSError:
            obsidian_paths = []

        for path in obsidian_paths:
            extension = os.path.splitext(
                str(path)
            )[1].lower()

            if extension not in SUPPORTED_EXTENSIONS:
                continue

            paths.append(
                os.path.abspath(
                    os.fspath(path)
                )
            )

        return tuple(
            sorted(
                dict.fromkeys(paths)
            )
        )

    def get_vault_path(self):
        try:
            value = self.vault_path_provider()
        except OSError:
            return None

        if not value:
            return None

        return os.path.abspath(
            os.fspath(value)
        )
