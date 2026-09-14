"""Non-interactive knowledge discovery service for Phase 2."""

from __future__ import annotations

import os

from personal_learning_assistant.domain.knowledge_models import (
    KnowledgeDocument,
    KnowledgeDocumentListResult,
)
from personal_learning_assistant.repositories.interfaces import (
    KnowledgeRepository,
)


class KnowledgeService:
    """Expose filesystem knowledge discovery without course/UI coupling."""

    def __init__(
        self,
        repository: KnowledgeRepository,
    ):
        self.repository = repository

    @staticmethod
    def _is_inside(path, parent):
        try:
            return os.path.commonpath(
                [
                    os.path.abspath(path),
                    os.path.abspath(parent),
                ]
            ) == os.path.abspath(parent)
        except (ValueError, OSError):
            return False

    def describe_document(
        self,
        file_path,
    ):
        absolute = os.path.abspath(
            os.fspath(file_path)
        )
        vault_path = (
            self.repository.get_vault_path()
        )

        if (
            vault_path
            and self._is_inside(
                absolute,
                vault_path,
            )
        ):
            relative = os.path.relpath(
                absolute,
                vault_path,
            )
            return KnowledgeDocument(
                path=absolute,
                display_name=(
                    f"Obsidian Vault: {relative}"
                ),
                scope="obsidian_vault",
            )

        base_dir = getattr(
            self.repository,
            "base_dir",
            None,
        )

        if (
            base_dir
            and self._is_inside(
                absolute,
                base_dir,
            )
        ):
            relative = os.path.relpath(
                absolute,
                base_dir,
            )
            return KnowledgeDocument(
                path=absolute,
                display_name=relative,
                scope="project",
            )

        return KnowledgeDocument(
            path=absolute,
            display_name=absolute,
            scope="external",
        )

    def list_documents(self):
        documents = tuple(
            self.describe_document(path)
            for path in (
                self.repository
                .list_document_paths()
            )
        )

        return KnowledgeDocumentListResult(
            documents=documents,
        )
