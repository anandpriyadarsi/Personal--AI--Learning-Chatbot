"""SQLite persistence for unified study reading history and Companion memory."""

from __future__ import annotations

import json
import sqlite3

from personal_learning_assistant.domain.study_item_models import StudyItemIdentity
from personal_learning_assistant.repositories.sqlite.connection import transaction


class StudyInteractionRepositoryError(RuntimeError):
    pass


class StudyInteractionNotFoundError(StudyInteractionRepositoryError):
    pass


class StudyInteractionConflictError(StudyInteractionRepositoryError):
    pass


_REQUIRED = {
    "study_item_reading_sessions": {
        "id", "item_kind", "item_identity", "source_version_hash",
        "source_locator_json", "started_at", "ended_at", "active_seconds",
        "max_scroll_bps", "last_event_sequence", "created_at", "updated_at",
    },
    "study_item_companion_entries": {
        "id", "item_kind", "item_identity", "source_version_hash",
        "entry_type", "entry_text", "locator_json", "created_at",
        "updated_at", "archived_at",
    },
}


def _bounded_int(value, *, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{} must be an integer".format(label))
    if not minimum <= value <= maximum:
        raise ValueError("{} is outside accepted bounds".format(label))
    return value


def _session_view(row, *, accepted=True):
    return {
        "session_id": str(row["id"]),
        "started_at": str(row["started_at"]),
        "ended_at": None if row["ended_at"] is None else str(row["ended_at"]),
        "active_seconds": int(row["active_seconds"]),
        "max_scroll_bps": int(row["max_scroll_bps"]),
        "last_event_sequence": int(row["last_event_sequence"]),
        "accepted": bool(accepted),
    }


def _entry_view(row):
    return {
        "id": str(row["id"]),
        "entry_type": str(row["entry_type"]),
        "entry_text": str(row["entry_text"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "archived_at": None if row["archived_at"] is None else str(row["archived_at"]),
    }


class SQLiteStudyInteractionRepository:
    def __init__(self, connection: sqlite3.Connection, *, validate_schema=True):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        if validate_schema:
            self.validate_schema()

    def validate_schema(self):
        try:
            tables = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing = sorted(set(_REQUIRED) - tables)
            if missing:
                raise StudyInteractionRepositoryError(
                    "study interaction tables missing: {}".format(", ".join(missing))
                )
            for table, required in _REQUIRED.items():
                columns = {
                    str(row[1])
                    for row in self.connection.execute(
                        'PRAGMA table_info("{}")'.format(table)
                    )
                }
                absent = sorted(required - columns)
                if absent:
                    raise StudyInteractionRepositoryError(
                        "{} columns missing: {}".format(table, ", ".join(absent))
                    )
        except StudyInteractionRepositoryError:
            raise
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "study interaction schema is unavailable"
            ) from error

    def _session(self, session_id, identity: StudyItemIdentity):
        try:
            row = self.connection.execute(
                "SELECT * FROM study_item_reading_sessions "
                "WHERE id=? AND item_kind=? AND item_identity=? "
                "AND source_version_hash=?",
                (session_id, identity.kind, identity.item_id, identity.version_hash),
            ).fetchone()
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "reading session is temporarily unavailable"
            ) from error
        if row is None:
            raise StudyInteractionNotFoundError("reading session was not found")
        return row

    def reading_history(self, identity: StudyItemIdentity, *, recent_limit=5):
        limit = _bounded_int(
            recent_limit, label="recent_limit", minimum=1, maximum=10
        )
        try:
            agg = self.connection.execute(
                "SELECT COUNT(*) AS n,COALESCE(SUM(active_seconds),0) AS seconds,"
                "COALESCE(MAX(max_scroll_bps),0) AS progress,"
                "MIN(started_at) AS first_read,MAX(started_at) AS last_read "
                "FROM study_item_reading_sessions "
                "WHERE item_kind=? AND item_identity=?",
                (identity.kind, identity.item_id),
            ).fetchone()
            rows = self.connection.execute(
                "SELECT * FROM study_item_reading_sessions "
                "WHERE item_kind=? AND item_identity=? "
                "ORDER BY started_at DESC,id DESC LIMIT ?",
                (identity.kind, identity.item_id, limit),
            ).fetchall()
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "reading history is temporarily unavailable"
            ) from error
        recent = tuple(_session_view(row) for row in rows)
        return {
            "times_opened": int(agg["n"]),
            "first_read_at": None if agg["first_read"] is None else str(agg["first_read"]),
            "last_read_at": None if agg["last_read"] is None else str(agg["last_read"]),
            "total_active_seconds": int(agg["seconds"]),
            "last_session_active_seconds": 0 if not recent else int(recent[0]["active_seconds"]),
            "max_scroll_bps": int(agg["progress"]),
            "recent_sessions": recent,
        }

    def create_session(self, *, session_id, identity, locator, now):
        locator_json = json.dumps(
            dict(locator or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        try:
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    "INSERT INTO study_item_reading_sessions("
                    "id,item_kind,item_identity,source_version_hash,source_locator_json,"
                    "started_at,ended_at,active_seconds,max_scroll_bps,last_event_sequence,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,NULL,0,0,0,?,?)",
                    (
                        session_id, identity.kind, identity.item_id, identity.version_hash,
                        locator_json, now, now, now,
                    ),
                )
            return _session_view(self._session(session_id, identity))
        except sqlite3.IntegrityError as error:
            raise StudyInteractionConflictError(
                "reading session could not be created"
            ) from error
        except StudyInteractionRepositoryError:
            raise
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "reading session could not be created"
            ) from error

    def heartbeat(
        self, *, session_id, identity, sequence, delta_seconds, scroll_bps, now
    ):
        sequence = _bounded_int(
            sequence, label="sequence", minimum=1, maximum=2_147_483_647
        )
        delta_seconds = _bounded_int(
            delta_seconds, label="delta_seconds", minimum=1, maximum=60
        )
        scroll_bps = _bounded_int(
            scroll_bps, label="scroll_bps", minimum=0, maximum=10000
        )
        accepted = False
        try:
            with transaction(self.connection, immediate=True):
                row = self._session(session_id, identity)
                if row["ended_at"] is not None:
                    raise StudyInteractionConflictError(
                        "reading session already ended"
                    )
                if sequence > int(row["last_event_sequence"]):
                    self.connection.execute(
                        "UPDATE study_item_reading_sessions SET "
                        "active_seconds=active_seconds+?,"
                        "max_scroll_bps=MAX(max_scroll_bps,?),"
                        "last_event_sequence=?,updated_at=? WHERE id=?",
                        (delta_seconds, scroll_bps, sequence, now, session_id),
                    )
                    accepted = True
            return _session_view(
                self._session(session_id, identity), accepted=accepted
            )
        except StudyInteractionRepositoryError:
            raise
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "reading activity could not be recorded"
            ) from error

    def end_session(
        self, *, session_id, identity, sequence, delta_seconds, scroll_bps,
        replayed_delta_seconds, now
    ):
        sequence = _bounded_int(
            sequence, label="sequence", minimum=1, maximum=2_147_483_647
        )
        delta_seconds = _bounded_int(
            delta_seconds, label="delta_seconds", minimum=0, maximum=60
        )
        replayed_delta_seconds = _bounded_int(
            replayed_delta_seconds,
            label="replayed_delta_seconds",
            minimum=0,
            maximum=delta_seconds,
        )
        scroll_bps = _bounded_int(
            scroll_bps, label="scroll_bps", minimum=0, maximum=10000
        )
        accepted = False
        try:
            with transaction(self.connection, immediate=True):
                row = self._session(session_id, identity)
                if row["ended_at"] is None:
                    last_sequence = int(row["last_event_sequence"])
                    if sequence > last_sequence:
                        extra = delta_seconds
                    elif sequence == last_sequence and sequence > 0:
                        extra = delta_seconds - replayed_delta_seconds
                    else:
                        extra = None
                    if extra is not None:
                        self.connection.execute(
                            "UPDATE study_item_reading_sessions SET "
                            "ended_at=?,active_seconds=active_seconds+?,"
                            "max_scroll_bps=MAX(max_scroll_bps,?),"
                            "last_event_sequence=MAX(last_event_sequence,?),"
                            "updated_at=? WHERE id=?",
                            (now, extra, scroll_bps, sequence, now, session_id),
                        )
                        accepted = True
            return _session_view(
                self._session(session_id, identity), accepted=accepted
            )
        except StudyInteractionRepositoryError:
            raise
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "reading session could not be ended"
            ) from error

    def list_entries(self, identity: StudyItemIdentity):
        try:
            rows = self.connection.execute(
                "SELECT * FROM study_item_companion_entries "
                "WHERE item_kind=? AND item_identity=? AND archived_at IS NULL "
                "ORDER BY CASE entry_type "
                "WHEN 'key_point' THEN 0 WHEN 'doubt' THEN 1 ELSE 2 END,"
                "created_at DESC,id DESC",
                (identity.kind, identity.item_id),
            ).fetchall()
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "Study Companion is temporarily unavailable"
            ) from error
        return tuple(_entry_view(row) for row in rows)

    def add_entry(
        self, *, entry_id, identity, entry_type, entry_text, locator, now
    ):
        if entry_type not in {"key_point", "doubt", "personal_note"}:
            raise ValueError("unsupported companion entry type")
        text = str(entry_text or "").strip()
        if not 1 <= len(text) <= 4000:
            raise ValueError("companion entry text is outside accepted bounds")
        locator_json = json.dumps(
            dict(locator or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        try:
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    "INSERT INTO study_item_companion_entries("
                    "id,item_kind,item_identity,source_version_hash,entry_type,"
                    "entry_text,locator_json,created_at,updated_at,archived_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                    (
                        entry_id, identity.kind, identity.item_id, identity.version_hash,
                        entry_type, text, locator_json, now, now,
                    ),
                )
            row = self.connection.execute(
                "SELECT * FROM study_item_companion_entries WHERE id=?",
                (entry_id,),
            ).fetchone()
            return _entry_view(row)
        except sqlite3.IntegrityError as error:
            raise StudyInteractionConflictError(
                "Companion entry could not be saved"
            ) from error
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "Companion entry could not be saved"
            ) from error

    def archive_entry(self, *, entry_id, identity, now):
        try:
            with transaction(self.connection, immediate=True):
                row = self.connection.execute(
                    "SELECT * FROM study_item_companion_entries "
                    "WHERE id=? AND item_kind=? AND item_identity=?",
                    (entry_id, identity.kind, identity.item_id),
                ).fetchone()
                if row is None:
                    raise StudyInteractionNotFoundError(
                        "companion entry was not found"
                    )
                if row["archived_at"] is None:
                    self.connection.execute(
                        "UPDATE study_item_companion_entries "
                        "SET archived_at=?,updated_at=? WHERE id=?",
                        (now, now, entry_id),
                    )
                    row = self.connection.execute(
                        "SELECT * FROM study_item_companion_entries WHERE id=?",
                        (entry_id,),
                    ).fetchone()
            return _entry_view(row)
        except StudyInteractionRepositoryError:
            raise
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "Companion entry could not be archived"
            ) from error

    def reconciliation(self):
        try:
            legacy_reading = self.connection.execute(
                "SELECT COUNT(*) FROM obsidian_reading_sessions"
            ).fetchone()[0]
            backfilled_reading = self.connection.execute(
                "SELECT COUNT(*) FROM obsidian_reading_sessions o "
                "JOIN study_item_reading_sessions n ON n.id=o.id "
                "WHERE n.item_kind='obsidian_note'"
            ).fetchone()[0]
            legacy_entries = self.connection.execute(
                "SELECT COUNT(*) FROM obsidian_companion_entries"
            ).fetchone()[0]
            backfilled_entries = self.connection.execute(
                "SELECT COUNT(*) FROM obsidian_companion_entries o "
                "JOIN study_item_companion_entries n ON n.id=o.id "
                "WHERE n.item_kind='obsidian_note'"
            ).fetchone()[0]
        except sqlite3.Error as error:
            raise StudyInteractionRepositoryError(
                "study interaction reconciliation is unavailable"
            ) from error
        return {
            "legacy_reading": int(legacy_reading),
            "backfilled_reading": int(backfilled_reading),
            "legacy_entries": int(legacy_entries),
            "backfilled_entries": int(backfilled_entries),
            "matches": (
                int(legacy_reading) == int(backfilled_reading)
                and int(legacy_entries) == int(backfilled_entries)
            ),
        }
