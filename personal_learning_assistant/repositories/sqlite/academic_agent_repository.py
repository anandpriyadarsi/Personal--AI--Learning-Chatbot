"""SQLite safety/audit adapter for Phase 6.8 Academic Agent Cutover."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
)
from personal_learning_assistant.repositories.sqlite.connection import transaction


class AcademicAgentRepositoryError(RuntimeError):
    pass


class AcademicAgentAuthorityError(AcademicAgentRepositoryError):
    pass


class AcademicAgentExecutionConflict(AcademicAgentRepositoryError):
    pass


class AcademicAgentAmbiguousTarget(AcademicAgentRepositoryError):
    pass


_REQUIRED = {
    "operation_journal",
    "outbox_events",
    "note_metadata",
    "note_topics",
    "resources",
}


def _utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _new_id(prefix):
    return "{}-{}".format(prefix, uuid.uuid4())


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class SQLiteAcademicAgentRepository:
    """Read-only target resolution plus durable action claim/audit.

    The existing Phase 3 operation_journal is reused; Phase 6.8 introduces no
    new migration.
    """

    JOURNAL_KIND = "academic_agent_action"
    OUTBOX_EVENT = "academic_agent.action_executed"

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        authority_control_path=None,
        now=_utc_now,
        id_factory=_new_id,
        validate_schema=True,
    ):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.authority_control_path = (
            None if authority_control_path is None else Path(authority_control_path)
        )
        self._now = now
        self._id_factory = id_factory
        if validate_schema:
            self.validate_schema()

    def validate_schema(self):
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing = sorted(_REQUIRED - tables)
        if missing:
            raise AcademicAgentRepositoryError(
                "Phase 6.8 required tables missing: {}".format(", ".join(missing))
            )

    def require_sqlite_authority(self):
        if self.authority_control_path is None:
            raise AcademicAgentAuthorityError(
                "agent writes require an explicit authority-control path"
            )
        state = read_authority_control(self.authority_control_path)
        if state.storage_backend != BACKEND_SQLITE or not state.legacy_writes_blocked:
            raise AcademicAgentAuthorityError(
                "agent writes require active SQLite authority"
            )

    def resolve_note(self, topic_id: str, title: str):
        rows = self.connection.execute(
            "SELECT n.id,n.title,n.vault_id,n.relative_path,n.path_key "
            "FROM note_metadata n "
            "JOIN note_topics nt ON nt.note_id=n.id "
            "WHERE nt.topic_id=? AND lower(n.title)=lower(?) "
            "AND n.archived_at IS NULL AND n.trashed_at IS NULL "
            "ORDER BY n.id",
            (topic_id, str(title).strip()),
        ).fetchall()
        if len(rows) > 1:
            raise AcademicAgentAmbiguousTarget(
                "multiple active notes match this mentor recommendation"
            )
        return None if not rows else rows[0]

    def note_handoff(self, note_id: str):
        row = self.connection.execute(
            "SELECT id,title,vault_id,relative_path,path_key "
            "FROM note_metadata WHERE id=? AND archived_at IS NULL "
            "AND trashed_at IS NULL",
            (note_id,),
        ).fetchone()
        if row is None:
            raise AcademicAgentRepositoryError("recommended note is no longer active")
        return {
            "note_id": str(row["id"]),
            "title": str(row["title"]),
            "vault_id": str(row["vault_id"]),
            "relative_path": str(row["relative_path"]),
            "path_key": str(row["path_key"]),
        }

    def resource_handoff(self, resource_id: str):
        row = self.connection.execute(
            "SELECT id,title,resource_type,provider,canonical_uri,external_id,status "
            "FROM resources WHERE id=? AND deleted_at IS NULL AND archived_at IS NULL",
            (resource_id,),
        ).fetchone()
        if row is None:
            raise AcademicAgentRepositoryError(
                "recommended resource is no longer active"
            )
        return {
            "resource_id": str(row["id"]),
            "title": str(row["title"]),
            "resource_type": str(row["resource_type"]),
            "provider": str(row["provider"] or ""),
            "canonical_uri": (
                None if row["canonical_uri"] is None else str(row["canonical_uri"])
            ),
            "external_id": (
                None if row["external_id"] is None else str(row["external_id"])
            ),
            "status": str(row["status"]),
        }

    def _journal_row(self, fingerprint: str):
        return self.connection.execute(
            "SELECT * FROM operation_journal "
            "WHERE kind=? AND target_path=? "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            (self.JOURNAL_KIND, fingerprint),
        ).fetchone()

    def prior_execution(self, fingerprint: str):
        journal = self._journal_row(fingerprint)
        if journal is None:
            return None
        state = str(journal["state"])
        if state != "completed":
            raise AcademicAgentExecutionConflict(
                "a prior execution claim for this exact action is {}. "
                "Do not retry blindly; inspect the journal first.".format(state)
            )
        event = self.connection.execute(
            "SELECT payload_json FROM outbox_events "
            "WHERE event_type=? AND entity_type='agent_action' AND entity_id=? "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            (self.OUTBOX_EVENT, fingerprint),
        ).fetchone()
        if event is None:
            raise AcademicAgentExecutionConflict(
                "completed agent journal exists without matching execution event"
            )
        try:
            return json.loads(str(event["payload_json"]))
        except json.JSONDecodeError as error:
            raise AcademicAgentExecutionConflict(
                "stored agent execution payload is invalid JSON"
            ) from error

    def claim(self, fingerprint: str):
        self.require_sqlite_authority()
        if self._journal_row(fingerprint) is not None:
            raise AcademicAgentExecutionConflict(
                "an execution journal already exists for this exact action"
            )
        now = self._now()
        journal_id = self._id_factory("agent-journal")
        with transaction(self.connection, immediate=True):
            if self._journal_row(fingerprint) is not None:
                raise AcademicAgentExecutionConflict(
                    "an execution journal already exists for this exact action"
                )
            self.connection.execute(
                "INSERT INTO operation_journal("
                "id,kind,target_path,before_hash,after_hash,state,error,"
                "created_at,updated_at) "
                "VALUES (?,?,?,?,?,'planned',NULL,?,?)",
                (
                    journal_id,
                    self.JOURNAL_KIND,
                    fingerprint,
                    fingerprint,
                    None,
                    now,
                    now,
                ),
            )
        return journal_id

    def release_claim(self, journal_id: str):
        """Release a synchronously failed action whose service contract is atomic."""
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT state FROM operation_journal WHERE id=? AND kind=?",
                (journal_id, self.JOURNAL_KIND),
            ).fetchone()
            if row is None:
                return
            if str(row["state"]) != "planned":
                raise AcademicAgentExecutionConflict(
                    "only a planned agent claim can be released"
                )
            self.connection.execute(
                "DELETE FROM operation_journal WHERE id=?",
                (journal_id,),
            )

    def complete(self, journal_id: str, fingerprint: str, payload):
        clean_payload = dict(payload)
        clean_payload["fingerprint"] = fingerprint
        payload_json = _canonical_json(clean_payload)
        result_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        now = self._now()
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT state,target_path FROM operation_journal "
                "WHERE id=? AND kind=?",
                (journal_id, self.JOURNAL_KIND),
            ).fetchone()
            if row is None or str(row["target_path"]) != fingerprint:
                raise AcademicAgentExecutionConflict(
                    "agent execution claim is missing or does not match"
                )
            if str(row["state"]) != "planned":
                raise AcademicAgentExecutionConflict(
                    "agent execution claim is not in planned state"
                )
            self.connection.execute(
                "UPDATE operation_journal SET after_hash=?,state='completed',"
                "updated_at=? WHERE id=?",
                (result_hash, now, journal_id),
            )
            self.connection.execute(
                "INSERT INTO outbox_events("
                "id,event_type,entity_type,entity_id,payload_json,created_at,"
                "processed_at,failed_at,error,attempts) "
                "VALUES (?,?, 'agent_action', ?, ?, ?, NULL, NULL, NULL, 0)",
                (
                    self._id_factory("outbox"),
                    self.OUTBOX_EVENT,
                    fingerprint,
                    payload_json,
                    now,
                ),
            )
        return clean_payload
