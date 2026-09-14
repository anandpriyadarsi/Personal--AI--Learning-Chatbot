"""SQLite connection and explicit transaction helpers.

Importing this module never opens or creates a database. Callers must supply a
specific database path, which keeps Phase 3 tests and migrations pointed at
explicit temporary databases instead of the future production database.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union


DatabasePath = Union[str, Path]
_ALLOWED_SYNCHRONOUS = {"NORMAL", "FULL"}


class SQLiteConfigurationError(ValueError):
    """Raised when an unsupported SQLite connection option is requested."""


def connect_database(
    database_path: DatabasePath,
    *,
    synchronous: str = "NORMAL",
    busy_timeout_ms: int = 5000,
) -> sqlite3.Connection:
    """Open one configured SQLite connection for a single operation.

    The parent directory must already exist. This helper deliberately does not
    create directories so importing/configuring persistence never mutates the
    filesystem unexpectedly.
    """
    path = Path(database_path)
    synchronous_mode = synchronous.upper()

    if synchronous_mode not in _ALLOWED_SYNCHRONOUS:
        raise SQLiteConfigurationError(
            "synchronous must be NORMAL or FULL"
        )

    if busy_timeout_ms < 0:
        raise SQLiteConfigurationError(
            "busy_timeout_ms must be non-negative"
        )

    if not path.parent.exists():
        raise FileNotFoundError(
            "SQLite parent directory does not exist: {}".format(path.parent)
        )

    if path.exists() and path.is_dir():
        raise IsADirectoryError(str(path))

    connection = sqlite3.connect(
        str(path),
        timeout=max(busy_timeout_ms / 1000.0, 0.001),
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "PRAGMA busy_timeout = {}".format(int(busy_timeout_ms))
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            "PRAGMA synchronous = {}".format(synchronous_mode)
        )
    except Exception:
        connection.close()
        raise

    return connection


@contextmanager
def transaction(
    connection: sqlite3.Connection,
    *,
    immediate: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Run a block inside one explicit SQLite transaction.

    Nested transactions are intentionally rejected at this infrastructure
    layer. Higher-level repositories can add savepoints later if a real use
    case requires them.
    """
    if connection.in_transaction:
        raise RuntimeError(
            "transaction() cannot start inside an existing transaction"
        )

    connection.execute(
        "BEGIN IMMEDIATE" if immediate else "BEGIN"
    )

    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
