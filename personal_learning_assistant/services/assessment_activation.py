"""Explicit, backup-first activation of ANVAYA's private Assessment practice mode.

Invoked ONLY by the local `phase7_web.py` launcher. Library imports and
`create_app()` remain side-effect free. No existing academic table is emptied,
replaced, copied to Git or interpreted as authoritative self-evaluation.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
from uuid import uuid4

import config
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def _inspection(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Assessment activation stopped: SQLite integrity check failed.")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("Assessment activation stopped: SQLite foreign-key errors exist.")


def _extension_applied(database: Path) -> bool:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        _inspection(db)
        has_ledger = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not has_ledger:
            return False
        return db.execute(
            "SELECT 1 FROM schema_migrations WHERE version=15"
        ).fetchone() is not None


def _make_backup(database: Path, directory: Path) -> Path:
    if directory.is_symlink():
        raise RuntimeError("Assessment backup directory may not be a symlink.")
    directory.mkdir(parents=True, exist_ok=True)
    name = (
        "assessment-before-0015-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-" + uuid4().hex[:10] + ".sqlite3"
    )
    destination = directory / name
    temporary = directory / ("." + name + ".incomplete")
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            _inspection(source)
            with closing(sqlite3.connect(str(temporary))) as output:
                source.backup(output)
                _inspection(output)
        if destination.exists():
            raise RuntimeError("Unexpected Assessment backup collision.")
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


def activate_assessment_extension(
    database_path=None, *, backup_path=None
) -> dict:
    """Install additive migration 0015 once and verify the private practice scope.

    Existing assessment history and all migrations 0001-0014 are preserved.
    Existing databases are backed up with SQLite's consistent backup API
    before changing any schema. On any error the launcher MUST NOT start.
    """
    database = Path(database_path if database_path is not None else config.DATABASE_PATH)
    backup_dir = Path(backup_path if backup_path is not None else config.BACKUP_PATH)
    if database.is_symlink() or database.is_dir() or database.parent.is_symlink():
        raise RuntimeError("Assessment database path must be a regular local file.")
    existed = database.is_file()
    prior_extension = _extension_applied(database) if existed else False
    backup = None
    if existed and not prior_extension:
        backup = _make_backup(database, backup_dir)
    if not existed:
        database.parent.mkdir(parents=True, exist_ok=True)

    applied_now = apply_migrations(database, enable_extended_assessment=True)

    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        _inspection(db)
        row = db.execute("SELECT scope FROM assessment_extended_scope").fetchall()
        migration = db.execute(
            "SELECT 1 FROM schema_migrations WHERE version=15"
        ).fetchone()
        if row != [("local-self-study-v1",)] or migration is None:
            raise RuntimeError("Assessment practice schema is unavailable after migration.")
    return {
        "enabled": True,
        "new_database": not existed,
        "new_migrations": tuple(applied_now),
        "backup": str(backup) if backup is not None else None,
    }
