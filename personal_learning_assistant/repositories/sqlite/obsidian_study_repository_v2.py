"""Phase 7.5.12.2 compatibility adapter: Obsidian Reader on unified study memory."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from urllib.parse import quote

from personal_learning_assistant.domain.study_item_models import StudyItemIdentity
from personal_learning_assistant.repositories.sqlite.obsidian_study_repository import (
    ObsidianStudyRepositoryConflictError,
    ObsidianStudyRepositoryError,
    ObsidianStudyRepositoryNotFoundError,
)
from personal_learning_assistant.repositories.sqlite.study_interaction_repository import (
    SQLiteStudyInteractionRepository,
    StudyInteractionConflictError,
    StudyInteractionNotFoundError,
    StudyInteractionRepositoryError,
)


_ZERO_HASH = "0" * 64


def _open_database(path, *, writable):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ObsidianStudyRepositoryError(
            "Obsidian study storage is temporarily unavailable."
        )
    uri = "file:{}?mode={}".format(
        quote(str(path.resolve()).replace("\\", "/"), safe="/:"),
        "rw" if writable else "ro",
    )
    try:
        con = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=5000")
        return con
    except sqlite3.Error as error:
        raise ObsidianStudyRepositoryError(
            "Obsidian study storage is temporarily unavailable."
        ) from error


def _identity(note_identity, source_hash=None):
    return StudyItemIdentity(
        kind="obsidian_note",
        item_id=str(note_identity),
        version_hash=str(source_hash or _ZERO_HASH).lower(),
    )


def _session_view(row):
    return {
        "id": row["session_id"],
        "active_seconds": row["active_seconds"],
        "max_scroll_bps": row["max_scroll_bps"],
        "accepted": row["accepted"],
        "ended_at": row["ended_at"],
    }


def _translate(error):
    if isinstance(error, StudyInteractionNotFoundError):
        return ObsidianStudyRepositoryNotFoundError(str(error))
    if isinstance(error, StudyInteractionConflictError):
        return ObsidianStudyRepositoryConflictError(str(error))
    return ObsidianStudyRepositoryError(str(error))


def supports_unified_study_schema(database_path) -> bool:
    """Return True only when migration 0007 study-memory tables are present."""
    path = Path(database_path)
    if path.is_symlink() or not path.is_file():
        return False
    try:
        uri = "file:{}?mode=ro".format(
            quote(str(path.resolve()).replace("\\", "/"), safe="/:")
        )
        con = sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            tables = {
                str(row[0])
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            con.close()
    except sqlite3.Error:
        return False
    return {
        "study_item_reading_sessions",
        "study_item_companion_entries",
    } <= tables


class SQLiteObsidianStudyRepositoryV2:
    """Keep the Phase 7.5.12.1 service contract while persisting in v2 tables."""

    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _repo(self, *, writable):
        con = _open_database(self.database_path, writable=writable)
        try:
            return con, SQLiteStudyInteractionRepository(con)
        except Exception:
            con.close()
            raise

    def reading_history(self, *, vault_identity, note_identity, recent_limit=5):
        del vault_identity
        con, repo = self._repo(writable=False)
        try:
            return repo.reading_history(
                _identity(note_identity), recent_limit=recent_limit
            )
        except StudyInteractionRepositoryError as error:
            raise _translate(error) from error
        finally:
            con.close()

    def create_session(
        self, *, session_id, vault_identity, note_identity, relative_path,
        source_hash, now
    ):
        del vault_identity
        con, repo = self._repo(writable=True)
        try:
            row = repo.create_session(
                session_id=session_id,
                identity=_identity(note_identity, source_hash),
                locator={"relative_path": relative_path},
                now=now,
            )
            return _session_view(row)
        except StudyInteractionRepositoryError as error:
            raise _translate(error) from error
        finally:
            con.close()

    def heartbeat(
        self, *, session_id, vault_identity, note_identity, source_hash,
        sequence, delta_seconds, scroll_bps, now
    ):
        del vault_identity
        con, repo = self._repo(writable=True)
        try:
            return _session_view(
                repo.heartbeat(
                    session_id=session_id,
                    identity=_identity(note_identity, source_hash),
                    sequence=sequence,
                    delta_seconds=delta_seconds,
                    scroll_bps=scroll_bps,
                    now=now,
                )
            )
        except StudyInteractionRepositoryError as error:
            raise _translate(error) from error
        finally:
            con.close()

    def end_session(
        self, *, session_id, vault_identity, note_identity, source_hash,
        sequence, delta_seconds, scroll_bps, now, replayed_delta_seconds=None
    ):
        del vault_identity
        con, repo = self._repo(writable=True)
        try:
            return _session_view(
                repo.end_session(
                    session_id=session_id,
                    identity=_identity(note_identity, source_hash),
                    sequence=sequence,
                    delta_seconds=delta_seconds,
                    scroll_bps=scroll_bps,
                    replayed_delta_seconds=(
                        delta_seconds
                        if replayed_delta_seconds is None
                        else replayed_delta_seconds
                    ),
                    now=now,
                )
            )
        except StudyInteractionRepositoryError as error:
            raise _translate(error) from error
        finally:
            con.close()

    def list_entries(self, *, vault_identity, note_identity):
        del vault_identity
        con, repo = self._repo(writable=False)
        try:
            return repo.list_entries(_identity(note_identity))
        except StudyInteractionRepositoryError as error:
            raise _translate(error) from error
        finally:
            con.close()

    def add_entry(
        self, *, entry_id, vault_identity, note_identity, relative_path,
        entry_type, entry_text, now, source_hash=None
    ):
        del vault_identity
        con, repo = self._repo(writable=True)
        try:
            return repo.add_entry(
                entry_id=entry_id,
                identity=_identity(note_identity, source_hash),
                entry_type=entry_type,
                entry_text=entry_text,
                locator={"relative_path": relative_path},
                now=now,
            )
        except StudyInteractionRepositoryError as error:
            raise _translate(error) from error
        finally:
            con.close()

    def archive_entry(
        self, *, entry_id, vault_identity, note_identity, now
    ):
        del vault_identity
        con, repo = self._repo(writable=True)
        try:
            return repo.archive_entry(
                entry_id=entry_id,
                identity=_identity(note_identity),
                now=now,
            )
        except StudyInteractionRepositoryError as error:
            raise _translate(error) from error
        finally:
            con.close()
