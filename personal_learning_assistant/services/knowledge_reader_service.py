"""Readable Knowledge source + reusable Study Companion view."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from urllib.parse import quote, urlparse

from personal_learning_assistant.domain.study_item_models import StudyItemIdentity
from personal_learning_assistant.repositories.sqlite.search_metadata_repository import (
    SQLiteSearchMetadataRepository,
)
from personal_learning_assistant.repositories.sqlite.study_interaction_repository import (
    SQLiteStudyInteractionRepository,
)
from personal_learning_assistant.services.study_interaction_service import (
    StudyInteractionService,
)


class KnowledgeReaderNotFoundError(RuntimeError):
    pass


class KnowledgeReaderUnavailableError(RuntimeError):
    pass


def _open(path, *, writable):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise KnowledgeReaderUnavailableError("academic database is unavailable")
    uri = "file:{}?mode={}".format(
        quote(str(path.resolve()).replace("\\", "/"), safe="/:"),
        "rw" if writable else "ro",
    )
    con = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _safe_external_url(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    return text if parsed.scheme.lower() in {"http", "https"} and parsed.netloc else ""


class KnowledgeReaderService:
    def __init__(self, *, database_path="data/learning_assistant.db"):
        self.database_path = Path(database_path)

    def _resolve(self, con, document_id):
        repo = SQLiteSearchMetadataRepository(con)
        meta = repo.document(str(document_id or "").strip())
        if meta is None:
            raise KnowledgeReaderNotFoundError("knowledge source was not found")
        identity = StudyItemIdentity(
            "knowledge_document", meta["document_id"], meta["version_hash"]
        )
        return repo, meta, identity

    def _current_identity(self, document_id, version_hash):
        con = _open(self.database_path, writable=False)
        try:
            _repo, meta, identity = self._resolve(con, document_id)
            if identity.version_hash != str(version_hash or "").strip().lower():
                raise KnowledgeReaderUnavailableError(
                    "source changed; refresh the Knowledge Reader"
                )
            return identity, {"document_id": meta["document_id"]}
        finally:
            con.close()

    def view(self, document_id):
        con = _open(self.database_path, writable=False)
        try:
            repo, meta, identity = self._resolve(con, document_id)
            chunks = repo.document_chunks(meta["document_id"])
            interaction = StudyInteractionService(
                SQLiteStudyInteractionRepository(con)
            )
            return {
                **meta,
                "identity": identity,
                "history": interaction.history(identity),
                "companion": interaction.companion(identity),
                "content": tuple(
                    {
                        "chunk_id": str(row["id"]),
                        "ordinal": int(row["ordinal"]),
                        "page_number": (
                            None if row["page_number"] is None else int(row["page_number"])
                        ),
                        "text": str(row["chunk_text"]),
                    }
                    for row in chunks
                ),
                "open_original_url": _safe_external_url(meta["canonical_uri"]),
            }
        finally:
            con.close()

    def start_reading(self, *, document_id, version_hash):
        identity, locator = self._current_identity(document_id, version_hash)
        con = _open(self.database_path, writable=True)
        try:
            return StudyInteractionService(
                SQLiteStudyInteractionRepository(con)
            ).start_reading(identity=identity, locator=locator)
        finally:
            con.close()

    def heartbeat(
        self, *, document_id, version_hash, session_id, sequence,
        delta_seconds, scroll_bps
    ):
        identity, _locator = self._current_identity(document_id, version_hash)
        con = _open(self.database_path, writable=True)
        try:
            return StudyInteractionService(
                SQLiteStudyInteractionRepository(con)
            ).heartbeat(
                identity=identity,
                session_id=session_id,
                sequence=sequence,
                delta_seconds=delta_seconds,
                scroll_bps=scroll_bps,
            )
        finally:
            con.close()

    def end_reading(
        self, *, document_id, version_hash, session_id, sequence,
        delta_seconds, scroll_bps, replayed_delta_seconds=0
    ):
        identity, _locator = self._current_identity(document_id, version_hash)
        con = _open(self.database_path, writable=True)
        try:
            return StudyInteractionService(
                SQLiteStudyInteractionRepository(con)
            ).end_reading(
                identity=identity,
                session_id=session_id,
                sequence=sequence,
                delta_seconds=delta_seconds,
                scroll_bps=scroll_bps,
                replayed_delta_seconds=replayed_delta_seconds,
            )
        finally:
            con.close()

    def add_entry(self, *, document_id, version_hash, entry_type, entry_text):
        identity, locator = self._current_identity(document_id, version_hash)
        con = _open(self.database_path, writable=True)
        try:
            return StudyInteractionService(
                SQLiteStudyInteractionRepository(con)
            ).add_entry(
                identity=identity,
                entry_type=entry_type,
                entry_text=entry_text,
                locator=locator,
            )
        finally:
            con.close()

    def archive_entry(self, *, document_id, version_hash, entry_id):
        identity, _locator = self._current_identity(document_id, version_hash)
        con = _open(self.database_path, writable=True)
        try:
            return StudyInteractionService(
                SQLiteStudyInteractionRepository(con)
            ).archive_entry(identity=identity, entry_id=entry_id)
        finally:
            con.close()


def build_knowledge_reader_service():
    return KnowledgeReaderService()
