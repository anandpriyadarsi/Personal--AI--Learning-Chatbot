"""Phase 5.1 operation-journal and outbox coordination service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    SQLiteKnowledgeRegistryRepository,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class OperationCoordinationService:
    """Small state-machine boundary for future file+DB and derived-index work."""

    def __init__(self, repository: SQLiteKnowledgeRegistryRepository, *, now=_utc_now):
        self.repository = repository
        self._now = now

    def begin_operation(
        self,
        *,
        kind: str,
        target_path: Optional[str] = None,
        before_hash: Optional[str] = None,
    ):
        kind = str(kind or "").strip()
        if not kind:
            raise ValueError("kind is required")
        return self.repository.create_journal_entry(
            operation_id=str(uuid.uuid4()),
            kind=kind,
            target_path=None if target_path is None else str(target_path),
            before_hash=None if before_hash is None else str(before_hash),
            now=self._now(),
        )

    def mark_file_applied(self, operation_id: str, *, after_hash: str):
        return self.repository.transition_journal_entry(
            operation_id,
            state="file_applied",
            now=self._now(),
            after_hash=str(after_hash),
        )

    def mark_database_committed(self, operation_id: str):
        return self.repository.transition_journal_entry(
            operation_id,
            state="database_committed",
            now=self._now(),
        )

    def complete_operation(self, operation_id: str):
        return self.repository.transition_journal_entry(
            operation_id,
            state="completed",
            now=self._now(),
        )

    def fail_operation(self, operation_id: str, *, error: str):
        return self.repository.transition_journal_entry(
            operation_id,
            state="failed",
            now=self._now(),
            error=str(error),
        )

    def enqueue_event(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Optional[Mapping[str, Any]] = None,
    ):
        event = {
            "id": str(uuid.uuid4()),
            "event_type": str(event_type),
            "entity_type": str(entity_type),
            "entity_id": str(entity_id),
            "payload": dict(payload or {}),
            "created_at": self._now(),
        }
        return self.repository.enqueue_outbox(event)

    def pending_events(self, limit: int = 100):
        return self.repository.list_pending_outbox(limit)

    def mark_event_processed(self, event_id: str):
        return self.repository.mark_outbox_processed(event_id, now=self._now())

    def mark_event_failed(self, event_id: str, *, error: str):
        return self.repository.mark_outbox_failed(
            event_id, now=self._now(), error=str(error)
        )
