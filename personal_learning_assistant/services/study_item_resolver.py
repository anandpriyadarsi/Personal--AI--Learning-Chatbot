"""Resolve canonical study-item identities without inferring academic relationships."""

from __future__ import annotations

import hashlib
import sqlite3
import unicodedata
import uuid

from personal_learning_assistant.domain.study_item_models import StudyItemIdentity
from personal_learning_assistant.repositories.sqlite.search_metadata_repository import (
    SQLiteSearchMetadataRepository,
)


def _normalized_path_key(relative_path: str) -> str:
    return unicodedata.normalize(
        "NFC",
        str(relative_path or "").replace("\\", "/").strip(),
    ).casefold()


def obsidian_identity(note) -> StudyItemIdentity:
    vault_identity = str(note.get("vault_identity") or "").strip()
    relative_path = str(note.get("relative_path") or "").strip()
    source_hash = str(note.get("source_hash") or "").strip().lower()
    if not vault_identity.startswith("vault:"):
        raise LookupError("Obsidian vault identity is unavailable")
    assistant_id = note.get("assistant_id")
    note_identity = ""
    if assistant_id:
        try:
            note_identity = "assistant:" + str(uuid.UUID(str(assistant_id)))
        except (ValueError, TypeError, AttributeError):
            note_identity = ""
    if not note_identity:
        material = vault_identity + "\0" + _normalized_path_key(relative_path)
        note_identity = "path:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
    return StudyItemIdentity(
        kind="obsidian_note",
        item_id=note_identity,
        version_hash=source_hash,
    )


class StudyItemResolver:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.metadata = SQLiteSearchMetadataRepository(connection)

    def knowledge_document(self, document_id: str) -> StudyItemIdentity:
        item = self.metadata.document(str(document_id or "").strip())
        if item is None:
            raise LookupError("knowledge document was not found")
        return StudyItemIdentity(
            kind="knowledge_document",
            item_id=item["document_id"],
            version_hash=item["version_hash"],
        )
