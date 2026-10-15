"""Unregistered execution candidate storage. Never installs or migrates a schema."""

from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from urllib.parse import quote


def has_extended_attempt(connection, session_id):
    present = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='assessment_candidate_execution'"
    ).fetchone()
    return bool(
        present
        and connection.execute(
            "SELECT 1 FROM assessment_candidate_execution WHERE session_id=?",
            (str(session_id),),
        ).fetchone()
    )


class AssessmentExecutionRepository:
    def __init__(self, path):
        self.path = Path(path)

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
            scope = db.execute(
                "SELECT scope FROM assessment_candidate_scope"
            ).fetchall()
            if len(scope) != 1 or scope[0][0] != "disposable-synthetic-only":
                raise ValueError("Production authority is not approved.")
            if write:
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("BEGIN")
            try:
                yield db
                if write:
                    db.commit()
                else:
                    db.rollback()
            except BaseException:
                db.rollback()
                raise
        finally:
            db.close()
