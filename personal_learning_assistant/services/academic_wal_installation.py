"""Local-launcher-owned WAL snapshot publication for ANVAYA Planning/Analysis.

This module has no import-time side effects. Only the explicit local launcher
may start its worker; generic create_app() and Flask GET routes do not connect
to the installed DB, create files, or publish snapshots.

ANVAYA has multiple independent SQLite write owners. The worker is an
explicitly trusted *publication owner*, not a global monkey-patch or a
transaction hook injected into other academic services. It uses a dedicated
read-only SQLite source connection to construct bounded committed backups
on its own thread, periodically. Publisher-side SQLite may legitimately
access the WAL index. HTTP readers never do so.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import threading
from urllib.parse import quote

from .academic_wal_snapshot import AcademicSnapshotFeed, AcademicSnapshotUnavailable


class InstalledWalPublisherError(RuntimeError):
    """The local WAL publisher cannot be started safely."""


@dataclass(frozen=True)
class InstalledWalPublisherState:
    running: bool
    has_snapshot: bool
    error: str


class InstalledAcademicWalPublisher:
    """One owner-thread SQLite connection; bounded in-memory snapshot feed."""

    def __init__(self, database_path, *, interval_seconds=30, max_bytes=None):
        if type(interval_seconds) is not int or not 10 <= interval_seconds <= 60:
            raise ValueError("Publisher refresh must be between 10 and 60 seconds.")
        self.path = Path(database_path)
        self.interval_seconds = interval_seconds
        self.feed = AcademicSnapshotFeed(
            self.path, **({} if max_bytes is None else {"max_bytes": max_bytes})
        )
        self._stop = threading.Event()
        self._first_attempt = threading.Event()
        self._worker = None
        self._error_lock = threading.Lock()
        self._last_error = ""

    def _set_error(self, value):
        with self._error_lock:
            self._last_error = str(value)

    def state(self):
        with self._error_lock:
            error = self._last_error
        return InstalledWalPublisherState(
            running=bool(self._worker and self._worker.is_alive()),
            has_snapshot=self.feed.latest() is not None,
            error=error,
        )

    @staticmethod
    def _eligible(path):
        path = Path(path).absolute()
        if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
            return False
        try:
            with path.open("rb") as stream:
                head = stream.read(20)
            return len(head) == 20 and head[:16] == b"SQLite format 3\\x00" and head[18:20] == bytes((2, 2))
        except OSError:
            return False

    def _run(self):
        connection = None
        try:
            while not self._stop.is_set():
                try:
                    if not self._eligible(self.path):
                        raise InstalledWalPublisherError("Academic WAL source unavailable or unsafe.")
                    if connection is None:
                        safe_path = quote(str(self.path.absolute().resolve(strict=True)).replace("\\\\", "/"), safe="/:")
                        connection = sqlite3.connect(
                            "file:" + safe_path + "?mode=ro", uri=True,
                            isolation_level=None, timeout=2.0,
                        )
                        connection.execute("PRAGMA query_only=ON")
                        connection.execute("PRAGMA busy_timeout=2000")
                    self.feed.publish(connection)
                    self._set_error("")
                except (InstalledWalPublisherError, AcademicSnapshotUnavailable,
                        sqlite3.Error, OSError, ValueError):
                    # No stale academic values survive a failed publication.
                    self.feed.invalidate()
                    self._set_error("Academic owner publication unavailable; retrying locally.")
                    if connection is not None:
                        try:
                            connection.close()
                        except sqlite3.Error:
                            pass
                        connection = None
                finally:
                    self._first_attempt.set()
                self._stop.wait(self.interval_seconds)
        finally:
            if connection is not None:
                connection.close()
            self._first_attempt.set()

    def start(self, *, initial_wait_seconds=8.0):
        """Start once, from the explicit local launcher, never from a web GET."""
        if self._worker is not None:
            raise InstalledWalPublisherError("WAL publication was already initialized.")
        if not self._eligible(self.path):
            raise InstalledWalPublisherError(
                "Academic WAL database is absent or unsuitable; publisher not started."
            )
        self._worker = threading.Thread(
            target=self._run, name="anvaya-academic-wal-owner", daemon=True
        )
        self._worker.start()
        # Initial publication runs off the request path; a bounded boot wait
        # avoids showing stale results if initial publication is slow.
        self._first_attempt.wait(initial_wait_seconds)
        return self.state()

    def stop(self):
        """Signal thread termination; do not checkpoint or close user DB data."""
        self._stop.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=3.0)
        self.feed.invalidate()
