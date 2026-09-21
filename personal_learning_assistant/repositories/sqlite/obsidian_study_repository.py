"""SQLite persistence for Obsidian Reader history and Companion entries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class ObsidianStudyRepositoryError(RuntimeError):
    """The feature-owned study store could not complete an operation."""


class ObsidianStudyRepositoryNotFoundError(ObsidianStudyRepositoryError):
    """The requested session or entry is not in the current note scope."""


class ObsidianStudyRepositoryConflictError(ObsidianStudyRepositoryError):
    """Stored session state conflicts with the requested transition."""


_REQUIRED = {
    "obsidian_reading_sessions": {
        "id",
        "vault_identity",
        "note_identity",
        "relative_path",
        "source_hash",
        "started_at",
        "ended_at",
        "active_seconds",
        "max_scroll_bps",
        "last_event_sequence",
        "created_at",
        "updated_at",
    },
    "obsidian_companion_entries": {
        "id",
        "vault_identity",
        "note_identity",
        "relative_path",
        "entry_type",
        "entry_text",
        "created_at",
        "updated_at",
        "archived_at",
    },
}


def _open_database(database_path: Path, *, writable: bool) -> sqlite3.Connection:
    path = Path(database_path)
    if path.is_symlink() or not path.is_file():
        raise ObsidianStudyRepositoryError(
            "Obsidian study storage is temporarily unavailable."
        )
    uri_path = quote(
        str(path.resolve(strict=False)).replace("\\", "/"),
        safe="/:",
    )
    connection = None
    try:
        connection = sqlite3.connect(
            "file:{}?mode={}".format(uri_path, "rw" if writable else "ro"),
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except sqlite3.Error as error:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        raise ObsidianStudyRepositoryError(
            "Obsidian study storage is temporarily unavailable."
        ) from error


def _session_view(row, *, accepted: bool):
    return {
        "id": str(row["id"]),
        "vault_identity": str(row["vault_identity"]),
        "note_identity": str(row["note_identity"]),
        "relative_path": str(row["relative_path"]),
        "source_hash": str(row["source_hash"]),
        "started_at": str(row["started_at"]),
        "ended_at": None if row["ended_at"] is None else str(row["ended_at"]),
        "active_seconds": int(row["active_seconds"]),
        "max_scroll_bps": int(row["max_scroll_bps"]),
        "last_event_sequence": int(row["last_event_sequence"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "accepted": bool(accepted),
    }


def _entry_view(row):
    return {
        "id": str(row["id"]),
        "vault_identity": str(row["vault_identity"]),
        "note_identity": str(row["note_identity"]),
        "relative_path": str(row["relative_path"]),
        "entry_type": str(row["entry_type"]),
        "entry_text": str(row["entry_text"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "archived_at": (
            None if row["archived_at"] is None else str(row["archived_at"])
        ),
    }


def _validate_event_values(
    *, sequence, delta_seconds, scroll_bps, allow_zero_delta: bool
):
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("sequence must be a positive integer")
    minimum_delta = 0 if allow_zero_delta else 1
    if (
        isinstance(delta_seconds, bool)
        or not isinstance(delta_seconds, int)
        or not minimum_delta <= delta_seconds <= 60
    ):
        raise ValueError("delta_seconds is outside the accepted range")
    if (
        isinstance(scroll_bps, bool)
        or not isinstance(scroll_bps, int)
        or not 0 <= scroll_bps <= 10000
    ):
        raise ValueError("scroll_bps is outside the accepted range")


class SQLiteObsidianStudyRepository:
    """Open one validated connection per read/write operation."""

    def __init__(
        self,
        database_path,
        *,
        connection_factory: Optional[Callable[..., sqlite3.Connection]] = None,
    ):
        self.database_path = Path(database_path)
        self._connection_factory = connection_factory or _open_database

    def _connect(self, *, writable: bool) -> sqlite3.Connection:
        connection = None
        try:
            connection = self._connection_factory(
                self.database_path,
                writable=writable,
            )
            self._validate_schema(connection)
            return connection
        except ObsidianStudyRepositoryError:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise
        except Exception as error:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise ObsidianStudyRepositoryError(
                "Obsidian study storage is temporarily unavailable."
            ) from error

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing_tables = sorted(set(_REQUIRED) - tables)
        if missing_tables:
            raise ObsidianStudyRepositoryError(
                "Obsidian study storage is temporarily unavailable."
            )
        for table_name, required_columns in _REQUIRED.items():
            columns = {
                str(row[1])
                for row in connection.execute(
                    'PRAGMA table_info("{}")'.format(table_name)
                ).fetchall()
            }
            if required_columns - columns:
                raise ObsidianStudyRepositoryError(
                    "Obsidian study storage is temporarily unavailable."
                )

    @staticmethod
    def _scoped_session(
        connection,
        *,
        session_id,
        vault_identity,
        note_identity,
        source_hash,
    ):
        row = connection.execute(
            "SELECT * FROM obsidian_reading_sessions "
            "WHERE id=? AND vault_identity=? AND note_identity=? AND source_hash=?",
            (session_id, vault_identity, note_identity, source_hash),
        ).fetchone()
        if row is None:
            raise ObsidianStudyRepositoryNotFoundError(
                "Reading session was not found for this note."
            )
        return row

    def reading_history(
        self,
        *,
        vault_identity: str,
        note_identity: str,
        recent_limit: int = 5,
    ):
        try:
            bounded_limit = max(1, min(int(recent_limit), 5))
        except (TypeError, ValueError) as error:
            raise ValueError("recent_limit must be an integer") from error
        connection = self._connect(writable=False)
        try:
            aggregate = connection.execute(
                "SELECT COUNT(*) AS times_opened,"
                "COALESCE(SUM(active_seconds),0) AS total_active_seconds,"
                "COALESCE(MAX(max_scroll_bps),0) AS max_scroll_bps "
                "FROM obsidian_reading_sessions "
                "WHERE vault_identity=? AND note_identity=?",
                (vault_identity, note_identity),
            ).fetchone()
            rows = connection.execute(
                "SELECT * FROM obsidian_reading_sessions "
                "WHERE vault_identity=? AND note_identity=? "
                "ORDER BY started_at DESC,id DESC LIMIT ?",
                (vault_identity, note_identity, bounded_limit),
            ).fetchall()
            recent = tuple(_session_view(row, accepted=True) for row in rows)
            latest = None if not recent else recent[0]
            return {
                "times_opened": int(aggregate["times_opened"]),
                "last_read_at": None if latest is None else latest["started_at"],
                "total_active_seconds": int(aggregate["total_active_seconds"]),
                "last_session_active_seconds": (
                    0 if latest is None else int(latest["active_seconds"])
                ),
                "max_scroll_bps": int(aggregate["max_scroll_bps"]),
                "recent_sessions": recent,
            }
        except ObsidianStudyRepositoryError:
            raise
        except sqlite3.Error as error:
            raise ObsidianStudyRepositoryError(
                "Obsidian study history is temporarily unavailable."
            ) from error
        finally:
            connection.close()

    def create_session(
        self,
        *,
        session_id: str,
        vault_identity: str,
        note_identity: str,
        relative_path: str,
        source_hash: str,
        now: str,
    ):
        connection = self._connect(writable=True)
        try:
            with transaction(connection, immediate=True):
                connection.execute(
                    "INSERT INTO obsidian_reading_sessions("
                    "id,vault_identity,note_identity,relative_path,source_hash,"
                    "started_at,ended_at,active_seconds,max_scroll_bps,"
                    "last_event_sequence,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,NULL,0,0,0,?,?)",
                    (
                        session_id,
                        vault_identity,
                        note_identity,
                        relative_path,
                        source_hash,
                        now,
                        now,
                        now,
                    ),
                )
            row = self._scoped_session(
                connection,
                session_id=session_id,
                vault_identity=vault_identity,
                note_identity=note_identity,
                source_hash=source_hash,
            )
            return _session_view(row, accepted=True)
        except ObsidianStudyRepositoryError:
            raise
        except sqlite3.IntegrityError as error:
            raise ObsidianStudyRepositoryConflictError(
                "Reading session could not be created."
            ) from error
        except sqlite3.Error as error:
            raise ObsidianStudyRepositoryError(
                "Reading session could not be created."
            ) from error
        finally:
            connection.close()

    def heartbeat(
        self,
        *,
        session_id: str,
        vault_identity: str,
        note_identity: str,
        source_hash: str,
        sequence: int,
        delta_seconds: int,
        scroll_bps: int,
        now: str,
    ):
        _validate_event_values(
            sequence=sequence,
            delta_seconds=delta_seconds,
            scroll_bps=scroll_bps,
            allow_zero_delta=False,
        )
        connection = self._connect(writable=True)
        try:
            accepted = False
            with transaction(connection, immediate=True):
                row = self._scoped_session(
                    connection,
                    session_id=session_id,
                    vault_identity=vault_identity,
                    note_identity=note_identity,
                    source_hash=source_hash,
                )
                if row["ended_at"] is not None:
                    raise ObsidianStudyRepositoryConflictError(
                        "Reading session has already ended."
                    )
                if sequence > int(row["last_event_sequence"]):
                    connection.execute(
                        "UPDATE obsidian_reading_sessions SET "
                        "active_seconds=active_seconds+?,"
                        "max_scroll_bps=MAX(max_scroll_bps,?),"
                        "last_event_sequence=?,updated_at=? WHERE id=?",
                        (delta_seconds, scroll_bps, sequence, now, session_id),
                    )
                    accepted = True
                row = self._scoped_session(
                    connection,
                    session_id=session_id,
                    vault_identity=vault_identity,
                    note_identity=note_identity,
                    source_hash=source_hash,
                )
            return _session_view(row, accepted=accepted)
        except ObsidianStudyRepositoryError:
            raise
        except sqlite3.Error as error:
            raise ObsidianStudyRepositoryError(
                "Reading activity could not be recorded."
            ) from error
        finally:
            connection.close()

    def end_session(
        self,
        *,
        session_id: str,
        vault_identity: str,
        note_identity: str,
        source_hash: str,
        sequence: int,
        delta_seconds: int,
        scroll_bps: int,
        now: str,
        replayed_delta_seconds=None,
    ):
        _validate_event_values(
            sequence=sequence,
            delta_seconds=delta_seconds,
            scroll_bps=scroll_bps,
            allow_zero_delta=True,
        )
        if replayed_delta_seconds is None:
            # Compatibility for the original end contract: a same-sequence
            # end repeats the complete outstanding heartbeat delta.
            replayed_delta_seconds = delta_seconds
        if (
            isinstance(replayed_delta_seconds, bool)
            or not isinstance(replayed_delta_seconds, int)
            or not 0 <= replayed_delta_seconds <= delta_seconds
        ):
            raise ValueError(
                "replayed_delta_seconds is outside the accepted range"
            )
        connection = self._connect(writable=True)
        try:
            accepted = False
            with transaction(connection, immediate=True):
                row = self._scoped_session(
                    connection,
                    session_id=session_id,
                    vault_identity=vault_identity,
                    note_identity=note_identity,
                    source_hash=source_hash,
                )
                if row["ended_at"] is None:
                    last_sequence = int(row["last_event_sequence"])
                    if sequence > last_sequence:
                        connection.execute(
                            "UPDATE obsidian_reading_sessions SET "
                            "ended_at=?,active_seconds=active_seconds+?,"
                            "max_scroll_bps=MAX(max_scroll_bps,?),"
                            "last_event_sequence=?,updated_at=? WHERE id=?",
                            (
                                now,
                                delta_seconds,
                                scroll_bps,
                                sequence,
                                now,
                                session_id,
                            ),
                        )
                        accepted = True
                    elif sequence == last_sequence and sequence > 0:
                        # An unload beacon may safely replace an in-flight
                        # heartbeat with the same event. If the heartbeat won
                        # the race, add only activity accrued after its payload
                        # was created, then finalize without double-counting.
                        additional_seconds = (
                            delta_seconds - replayed_delta_seconds
                        )
                        connection.execute(
                            "UPDATE obsidian_reading_sessions SET "
                            "ended_at=?,active_seconds=active_seconds+?,"
                            "max_scroll_bps=MAX(max_scroll_bps,?),"
                            "updated_at=? WHERE id=?",
                            (
                                now,
                                additional_seconds,
                                scroll_bps,
                                now,
                                session_id,
                            ),
                        )
                        accepted = True
                row = self._scoped_session(
                    connection,
                    session_id=session_id,
                    vault_identity=vault_identity,
                    note_identity=note_identity,
                    source_hash=source_hash,
                )
            return _session_view(row, accepted=accepted)
        except ObsidianStudyRepositoryError:
            raise
        except sqlite3.Error as error:
            raise ObsidianStudyRepositoryError(
                "Reading session could not be ended."
            ) from error
        finally:
            connection.close()

    def list_entries(self, *, vault_identity: str, note_identity: str):
        connection = self._connect(writable=False)
        try:
            rows = connection.execute(
                "SELECT * FROM obsidian_companion_entries "
                "WHERE vault_identity=? AND note_identity=? "
                "AND archived_at IS NULL "
                "ORDER BY CASE entry_type WHEN 'key_point' THEN 0 ELSE 1 END,"
                "created_at DESC,id DESC",
                (vault_identity, note_identity),
            ).fetchall()
            return tuple(_entry_view(row) for row in rows)
        except sqlite3.Error as error:
            raise ObsidianStudyRepositoryError(
                "Obsidian Companion is temporarily unavailable."
            ) from error
        finally:
            connection.close()

    def add_entry(
        self,
        *,
        entry_id: str,
        vault_identity: str,
        note_identity: str,
        relative_path: str,
        entry_type: str,
        entry_text: str,
        now: str,
        source_hash=None,
    ):
        connection = self._connect(writable=True)
        try:
            with transaction(connection, immediate=True):
                connection.execute(
                    "INSERT INTO obsidian_companion_entries("
                    "id,vault_identity,note_identity,relative_path,entry_type,"
                    "entry_text,created_at,updated_at,archived_at) "
                    "VALUES (?,?,?,?,?,?,?,?,NULL)",
                    (
                        entry_id,
                        vault_identity,
                        note_identity,
                        relative_path,
                        entry_type,
                        entry_text,
                        now,
                        now,
                    ),
                )
            row = connection.execute(
                "SELECT * FROM obsidian_companion_entries WHERE id=?",
                (entry_id,),
            ).fetchone()
            return _entry_view(row)
        except sqlite3.IntegrityError as error:
            raise ObsidianStudyRepositoryConflictError(
                "Companion entry could not be saved."
            ) from error
        except sqlite3.Error as error:
            raise ObsidianStudyRepositoryError(
                "Companion entry could not be saved."
            ) from error
        finally:
            connection.close()

    def archive_entry(
        self,
        *,
        entry_id: str,
        vault_identity: str,
        note_identity: str,
        now: str,
    ):
        connection = self._connect(writable=True)
        try:
            with transaction(connection, immediate=True):
                row = connection.execute(
                    "SELECT * FROM obsidian_companion_entries "
                    "WHERE id=? AND vault_identity=? AND note_identity=?",
                    (entry_id, vault_identity, note_identity),
                ).fetchone()
                if row is None:
                    raise ObsidianStudyRepositoryNotFoundError(
                        "Companion entry was not found for this note."
                    )
                if row["archived_at"] is None:
                    connection.execute(
                        "UPDATE obsidian_companion_entries SET "
                        "archived_at=?,updated_at=? WHERE id=?",
                        (now, now, entry_id),
                    )
                    row = connection.execute(
                        "SELECT * FROM obsidian_companion_entries WHERE id=?",
                        (entry_id,),
                    ).fetchone()
            return _entry_view(row)
        except ObsidianStudyRepositoryError:
            raise
        except sqlite3.Error as error:
            raise ObsidianStudyRepositoryError(
                "Companion entry could not be archived."
            ) from error
        finally:
            connection.close()
