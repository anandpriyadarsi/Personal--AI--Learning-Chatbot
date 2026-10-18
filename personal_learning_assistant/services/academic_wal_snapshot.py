"""Owner-published WAL snapshots for read-only Planning/Analysis.

Normal Analysis requests never open the live SQLite connection or its -wal/-shm
sidecars. Only the authoritative academic *writer owner* may call publish() on
its already-open, transaction-free connection after a durable commit.

The owner uses SQLite's online backup API to publish a committed in-memory
snapshot. This is an explicit owner operation, NOT a read-route side effect.
No WAL parsing, checkpoint commands, raw -wal/-shm copying or immutable live
SQLite connections are used. If no trusted publisher is configured, fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading

MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
SQLITE_HEADER = b"SQLite format 3\x00"


class AcademicSnapshotUnavailable(RuntimeError):
    """Snapshot cannot be trusted, built, or served; no academic result is returned."""


@dataclass(frozen=True)
class AuthorizedAcademicSnapshot:
    database_identity: str
    payload: bytes
    published_at: datetime
    revision: int


def _identity(path: Path) -> str:
    """Reject symlink aliases; the installed owner must explicitly name the DB."""
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents):
        raise AcademicSnapshotUnavailable("The academic database identity is unavailable.")
    return str(path.resolve(strict=True))


class AcademicSnapshotFeed:
    """An owner-scoped, process-local bounded feed of committed SQLite database images.

    Create one feed for one installed DB. Publish ONLY on the writer owner's
    committed connection, in its owning thread. A Flask reader receives merely
    `feed.latest`; it never receives the writer connection or write credentials.
    """

    def __init__(self, database_path, *, max_bytes=MAX_SNAPSHOT_BYTES):
        if type(max_bytes) is not int or not 0 < max_bytes <= MAX_SNAPSHOT_BYTES:
            raise ValueError("Invalid academic snapshot size policy.")
        self._path = Path(database_path)
        self._max_bytes = max_bytes
        self._lock = threading.RLock()
        self._publication_lock = threading.Lock()
        self._latest: AuthorizedAcademicSnapshot | None = None
        self._revision = 0

    def latest(self) -> AuthorizedAcademicSnapshot | None:
        with self._lock:
            return self._latest

    def invalidate(self) -> None:
        with self._lock:
            self._latest = None

    def publish(self, owner_connection: sqlite3.Connection, *, at: datetime | None = None):
        """Run explicitly after commit, on the authorized owner's connection thread.

        SQLite online backup yields a consistent snapshot including WAL commits.
        Its source-side coordination belongs to the owner's publication event;
        Analysis GET requests themselves touch ONLY the resulting memory bytes.
        """
        with self._publication_lock:
            try:
                db_id = _identity(self._path)
                if not isinstance(owner_connection, sqlite3.Connection):
                    raise AcademicSnapshotUnavailable("An authorized SQLite owner connection is required.")
                if owner_connection.in_transaction:
                    raise AcademicSnapshotUnavailable("Publish only after the source transaction commits.")
                locations = owner_connection.execute("PRAGMA database_list").fetchall()
                main = next((row[2] for row in locations if row[1] == "main"), None)
                if not main or str(Path(main).resolve(strict=True)) != db_id:
                    raise AcademicSnapshotUnavailable("Academic snapshot source identity does not match.")
                if owner_connection.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                    raise AcademicSnapshotUnavailable("This feed is restricted to WAL-mode academic databases.")
                timestamp = at if at is not None else datetime.now(timezone.utc)
                if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
                    raise AcademicSnapshotUnavailable("Publication timestamp must be timezone-aware.")
                # Source connection exists already: do not create another file-based
                # SQLite connection or switch journal mode. Destination is RAM only.
                target = sqlite3.connect(":memory:")
                try:
                    owner_connection.backup(target, pages=128, sleep=0.02)
                    # SQLite's backup preserves the source WAL header (02/02)
                    # even in RAM; normalize using RAM-only VACUUM before
                    # deserialize so the image needs no external -wal/-shm.
                    target.execute("VACUUM")
                    raw = target.serialize()
                    if (not isinstance(raw, bytes) or len(raw) < 100 or
                            len(raw) > self._max_bytes or not raw.startswith(SQLITE_HEADER) or
                            raw[18:20] != b"\x01\x01"):
                        raise AcademicSnapshotUnavailable("SQLite snapshot is invalid or exceeds policy.")
                    if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise AcademicSnapshotUnavailable("The committed SQLite snapshot failed integrity checks.")
                finally:
                    target.close()
                with self._lock:
                    self._revision += 1
                    self._latest = AuthorizedAcademicSnapshot(
                        database_identity=db_id, payload=raw,
                        published_at=timestamp.astimezone(timezone.utc),
                        revision=self._revision)
                    return self._latest.revision
            except (OSError, sqlite3.Error, ValueError, AcademicSnapshotUnavailable) as error:
                self.invalidate()  # Never keep an older snapshot after failed publication.
                raise AcademicSnapshotUnavailable("A trustworthy academic snapshot could not be published.") from error
