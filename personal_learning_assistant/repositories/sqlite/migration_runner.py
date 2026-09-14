"""Deterministic, checksum-verified SQLite schema migration runner."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple, Union

from .connection import connect_database, transaction


MigrationPath = Union[str, Path]
DEFAULT_MIGRATIONS_PATH = Path(__file__).with_name("migrations")
_MIGRATION_NAME = re.compile(
    r"^(?P<version>\d{4})_(?P<name>[a-z0-9][a-z0-9_]*)\.sql$"
)


class MigrationError(RuntimeError):
    """Base class for migration discovery/application failures."""


class MigrationFormatError(MigrationError):
    """Raised when migration files do not follow the required format."""


class MigrationDriftError(MigrationError):
    """Raised when an already-applied migration changed or disappeared."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _checksum(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def discover_migrations(
    migrations_path: MigrationPath = DEFAULT_MIGRATIONS_PATH,
) -> Tuple[Migration, ...]:
    """Load validated SQL migrations in strictly sequential version order."""
    root = Path(migrations_path)

    if not root.is_dir():
        raise MigrationFormatError(
            "Migration directory does not exist: {}".format(root)
        )

    migrations: List[Migration] = []

    for path in sorted(root.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationFormatError(
                "Invalid migration filename: {}".format(path.name)
            )

        raw = path.read_bytes()
        try:
            sql = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MigrationFormatError(
                "Migration must be UTF-8: {}".format(path.name)
            ) from exc

        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=match.group("name"),
                path=path,
                checksum=_checksum(raw),
                sql=sql,
            )
        )

    if not migrations:
        raise MigrationFormatError(
            "No SQL migrations found in {}".format(root)
        )

    versions = [migration.version for migration in migrations]
    expected = list(range(1, len(migrations) + 1))
    if versions != expected:
        raise MigrationFormatError(
            "Migration versions must be contiguous starting at 0001; "
            "found {}".format(versions)
        )

    return tuple(migrations)


def _table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _applied_migrations(
    connection: sqlite3.Connection,
) -> Dict[int, Tuple[str, str]]:
    if not _table_exists(connection, "schema_migrations"):
        return {}

    rows = connection.execute(
        "SELECT version, name, checksum "
        "FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {
        int(row["version"]): (str(row["name"]), str(row["checksum"]))
        for row in rows
    }


def _iter_sql_statements(sql: str) -> Iterable[str]:
    """Yield complete SQL statements without using executescript auto-commit."""
    buffer: List[str] = []

    for line in sql.splitlines(keepends=True):
        buffer.append(line)
        candidate = "".join(buffer).strip()

        if candidate and sqlite3.complete_statement(candidate):
            yield candidate
            buffer = []

    tail = "".join(buffer).strip()
    if tail:
        raise MigrationFormatError(
            "Migration ends with an incomplete SQL statement"
        )


def _validate_applied_history(
    migrations: Sequence[Migration],
    applied: Dict[int, Tuple[str, str]],
) -> None:
    discovered = {migration.version: migration for migration in migrations}

    for version, (applied_name, applied_checksum) in applied.items():
        migration = discovered.get(version)
        if migration is None:
            raise MigrationDriftError(
                "Applied migration {:04d} is missing from source".format(version)
            )
        if migration.name != applied_name:
            raise MigrationDriftError(
                "Applied migration {:04d} name changed".format(version)
            )
        if migration.checksum != applied_checksum:
            raise MigrationDriftError(
                "Applied migration {:04d} checksum changed".format(version)
            )


def apply_migrations(
    database_path: MigrationPath,
    *,
    migrations_path: MigrationPath = DEFAULT_MIGRATIONS_PATH,
) -> Tuple[int, ...]:
    """Apply pending schema migrations atomically and return applied versions.

    The database path is mandatory. Phase 3 callers should pass a temporary
    database until the later structured-domain cutover is explicitly approved.
    """
    migrations = discover_migrations(migrations_path)
    connection = connect_database(
        database_path,
        synchronous="FULL",
    )

    applied_now: List[int] = []

    try:
        applied = _applied_migrations(connection)
        _validate_applied_history(migrations, applied)

        for migration in migrations:
            if migration.version in applied:
                continue

            with transaction(connection, immediate=True):
                for statement in _iter_sql_statements(migration.sql):
                    connection.execute(statement)

                if not _table_exists(connection, "schema_migrations"):
                    raise MigrationError(
                        "Migration {:04d} did not create schema_migrations"
                        .format(migration.version)
                    )

                connection.execute(
                    "INSERT INTO schema_migrations "
                    "(version, name, checksum, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        _utc_now_text(),
                    ),
                )

            applied_now.append(migration.version)
            applied[migration.version] = (
                migration.name,
                migration.checksum,
            )
    finally:
        connection.close()

    return tuple(applied_now)
