"""Explicitly scoped execution store. The migration runner owns schema updates."""

from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from urllib.parse import quote


def has_extended_attempt(connection, session_id):
    # Both the older isolated candidate and the explicitly migrated production
    # extension are protected from legacy submit/expire mutations.
    for table in ("assessment_candidate_execution", "assessment_extended_execution"):
        present = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if present and connection.execute(
            "SELECT 1 FROM " + table + " WHERE session_id=?", (str(session_id),)
        ).fetchone():
            return True
    return False


class _ScopedConnection:
    """Present stable internal candidate SQL over distinct production tables."""
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, *args):
        return self.raw.execute(sql.replace("assessment_candidate_", "assessment_extended_"), *args)

    def __getattr__(self, key):
        return getattr(self.raw, key)


class AssessmentExecutionRepository:
    def __init__(self, path, *, production=False):
        self.path = Path(path)
        self.production = production is True

    @contextmanager
    def open(self, *, write=False):
        if not self.path.is_file() or self.path.is_symlink():
            raise ValueError("Candidate storage unavailable.")
        uri = "file:{}?mode={}".format(
            quote(self.path.resolve().as_posix(), safe="/:"), "rw" if write else "ro"
        )
        db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            table = "assessment_extended_scope" if self.production else "assessment_candidate_scope"
            scope = db.execute("SELECT scope FROM " + table).fetchall()
            expected = "local-self-study-v1" if self.production else "disposable-synthetic-only"
            if len(scope) != 1 or scope[0][0] != expected:
                raise ValueError("Assessment execution store scope is unavailable.")
            if write:
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("BEGIN")
            try:
                yield _ScopedConnection(db) if self.production else db
                if write:
                    db.commit()
                else:
                    db.rollback()
            except BaseException:
                db.rollback()
                raise
        finally:
            db.close()
