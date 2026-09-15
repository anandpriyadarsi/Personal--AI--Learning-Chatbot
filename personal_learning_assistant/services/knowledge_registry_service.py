"""Phase 5.1 application service for stable knowledge metadata registration."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional

from personal_learning_assistant.domain.knowledge_registry_models import (
    KnowledgeChunkInput,
)
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    KnowledgeRegistryConflictError,
    SQLiteKnowledgeRegistryRepository,
)


_NAMESPACE = uuid.UUID("e3334c65-5cc2-4c52-bd02-94fcba153aea")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_hash(value: str, label: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError("{} must be a lowercase/uppercase SHA-256 hex digest".format(label))
    return text


class KnowledgeRegistryService:
    """Register source identity/provenance without reading or rewriting source files."""

    def __init__(self, repository: SQLiteKnowledgeRegistryRepository, *, now=_utc_now):
        self.repository = repository
        self._now = now

    @staticmethod
    def _clean_identity(canonical_uri: Optional[str], path_key: Optional[str]):
        uri = str(canonical_uri or "").strip() or None
        path = str(path_key or "").strip().replace("\\", "/") or None
        if uri is None and path is None:
            raise ValueError("canonical_uri or path_key is required")
        return uri, path

    @staticmethod
    def _document_id(kind: str, canonical_uri: Optional[str], path_key: Optional[str]) -> str:
        identity = "uri:" + canonical_uri if canonical_uri else "path:" + str(path_key)
        return str(uuid.uuid5(_NAMESPACE, "knowledge-document|{}|{}".format(kind, identity)))

    def register_document(
        self,
        *,
        kind: str,
        content_hash: str,
        canonical_uri: Optional[str] = None,
        path_key: Optional[str] = None,
        mime_type: str = "",
        size_bytes: Optional[int] = None,
        source_timestamp: Optional[str] = None,
    ):
        kind = str(kind or "").strip()
        if not kind:
            raise ValueError("kind is required")
        canonical_uri, path_key = self._clean_identity(canonical_uri, path_key)
        content_hash = _require_hash(content_hash, "content_hash")
        if size_bytes is not None and int(size_bytes) < 0:
            raise ValueError("size_bytes must be non-negative")
        document_id = self._document_id(kind, canonical_uri, path_key)
        now = self._now()
        existing = self.repository.get_document(document_id)
        event_type = "knowledge.document.registered"
        if existing is not None and existing.content_hash != content_hash:
            event_type = "knowledge.document.content_changed"
        event = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "entity_type": "knowledge_document",
            "entity_id": document_id,
            "payload": {"kind": kind, "content_hash": content_hash},
            "created_at": now,
        }
        return self.repository.register_document(
            document_id=document_id,
            kind=kind,
            canonical_uri=canonical_uri,
            path_key=path_key,
            mime_type=str(mime_type or ""),
            content_hash=content_hash,
            size_bytes=None if size_bytes is None else int(size_bytes),
            source_timestamp=None if source_timestamp is None else str(source_timestamp),
            now=now,
            outbox_event=event,
        )

    def record_extraction(
        self,
        document_id: str,
        *,
        extraction_version: str,
        chunks: Iterable[KnowledgeChunkInput],
    ):
        extraction_version = str(extraction_version or "").strip()
        if not extraction_version:
            raise ValueError("extraction_version is required")
        document = self.repository.get_document(str(document_id))
        if document is None:
            raise KnowledgeRegistryConflictError("unknown document")
        prepared = []
        for item in chunks:
            if item.ordinal < 0:
                raise ValueError("chunk ordinal must be non-negative")
            text_hash = _require_hash(item.text_hash, "text_hash")
            if item.page_number is not None and item.page_number < 1:
                raise ValueError("page_number must be >= 1")
            if item.char_start is not None and item.char_start < 0:
                raise ValueError("char_start must be non-negative")
            if item.char_end is not None and item.char_end < 0:
                raise ValueError("char_end must be non-negative")
            if (
                item.char_start is not None
                and item.char_end is not None
                and item.char_end < item.char_start
            ):
                raise ValueError("char_end must be >= char_start")
            chunk_id = str(
                uuid.uuid5(
                    _NAMESPACE,
                    "knowledge-chunk|{}|{}|{}".format(
                        document.id, extraction_version, item.ordinal
                    ),
                )
            )
            prepared.append(
                {
                    "id": chunk_id,
                    "ordinal": item.ordinal,
                    "page_number": item.page_number,
                    "char_start": item.char_start,
                    "char_end": item.char_end,
                    "chunk_type": item.chunk_type,
                    "text_hash": text_hash,
                    "chunk_text": item.chunk_text,
                }
            )
        now = self._now()
        event = {
            "id": str(uuid.uuid4()),
            "event_type": "knowledge.document.extracted",
            "entity_type": "knowledge_document",
            "entity_id": document.id,
            "payload": {
                "extraction_version": extraction_version,
                "chunk_count": len(prepared),
            },
            "created_at": now,
        }
        return self.repository.replace_chunks(
            document_id=document.id,
            extraction_version=extraction_version,
            chunks=prepared,
            now=now,
            outbox_event=event,
        )

    def schedule_index_job(
        self,
        document_id: str,
        *,
        index_kind: str,
        model_name: str = "",
        model_version: str = "",
        index_version: str = "",
    ):
        document = self.repository.get_document(str(document_id))
        if document is None:
            raise KnowledgeRegistryConflictError("unknown document")
        identity = "|".join(
            (
                document.id,
                document.content_hash,
                str(index_kind),
                str(model_name),
                str(model_version),
                str(index_version),
            )
        )
        job_id = str(uuid.uuid5(_NAMESPACE, "index-job|" + identity))
        return self.repository.schedule_index_job(
            job_id=job_id,
            document_id=document.id,
            content_hash=document.content_hash,
            index_kind=str(index_kind),
            model_name=str(model_name),
            model_version=str(model_version),
            index_version=str(index_version),
            now=self._now(),
        )
