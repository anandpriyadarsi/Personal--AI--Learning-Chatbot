from __future__ import annotations

import importlib
import sqlite3
import sys

import pytest


FOUNDATION_TABLES = {
    "schema_migrations",
    "app_settings",
    "migration_imports",
    "operation_journal",
    "outbox_events",
}


def _fresh_import(name):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_config_declares_database_path_without_creating_it():
    import config

    assert config.DATABASE_PATH == config.DATA_PATH / "learning_assistant.db"


def test_importing_sqlite_modules_does_not_open_a_database(monkeypatch):
    calls = []

    def fail_connect(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("SQLite database opened during module import")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)

    _fresh_import(
        "personal_learning_assistant.repositories.sqlite.connection"
    )
    _fresh_import(
        "personal_learning_assistant.repositories.sqlite.migration_runner"
    )

    assert calls == []


def test_connection_applies_required_pragmas(tmp_path):
    from personal_learning_assistant.repositories.sqlite.connection import (
        connect_database,
    )

    database_path = tmp_path / "connection.db"
    connection = connect_database(database_path)

    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    finally:
        connection.close()


def test_transaction_commits_and_rolls_back(tmp_path):
    from personal_learning_assistant.repositories.sqlite.connection import (
        connect_database,
        transaction,
    )

    connection = connect_database(tmp_path / "transaction.db")
    try:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")

        with transaction(connection):
            connection.execute(
                "INSERT INTO sample (value) VALUES (?)",
                ("kept",),
            )

        with pytest.raises(RuntimeError):
            with transaction(connection):
                connection.execute(
                    "INSERT INTO sample (value) VALUES (?)",
                    ("rolled-back",),
                )
                raise RuntimeError("force rollback")

        values = [
            row[0]
            for row in connection.execute(
                "SELECT value FROM sample ORDER BY rowid"
            ).fetchall()
        ]
        assert values == ["kept"]
    finally:
        connection.close()


def test_foundation_migration_is_idempotent(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import (
        DEFAULT_MIGRATIONS_PATH,
        apply_migrations,
    )

    migrations = tmp_path / "migrations"
    migrations.mkdir()

    foundation = DEFAULT_MIGRATIONS_PATH / "0001_foundation.sql"
    (migrations / foundation.name).write_bytes(foundation.read_bytes())

    database_path = tmp_path / "learning_assistant.db"

    assert apply_migrations(
        database_path,
        migrations_path=migrations,
    ) == (1,)
    assert apply_migrations(
        database_path,
        migrations_path=migrations,
    ) == ()

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert FOUNDATION_TABLES.issubset(tables)

        rows = connection.execute(
            "SELECT version, name, length(checksum) "
            "FROM schema_migrations"
        ).fetchall()
        assert rows == [(1, "foundation", 64)]

        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_applied_migration_checksum_drift_is_rejected(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import (
        DEFAULT_MIGRATIONS_PATH,
        MigrationDriftError,
        apply_migrations,
    )

    migrations = tmp_path / "migrations"
    migrations.mkdir()

    source = DEFAULT_MIGRATIONS_PATH / "0001_foundation.sql"
    copied = migrations / source.name
    copied.write_bytes(source.read_bytes())

    database_path = tmp_path / "drift.db"
    assert apply_migrations(
        database_path,
        migrations_path=migrations,
    ) == (1,)

    copied.write_text(
        copied.read_text(encoding="utf-8") + "\n-- changed after apply\n",
        encoding="utf-8",
    )

    with pytest.raises(MigrationDriftError):
        apply_migrations(
            database_path,
            migrations_path=migrations,
        )


def test_failed_migration_rolls_back_schema_changes(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import (
        DEFAULT_MIGRATIONS_PATH,
        apply_migrations,
    )

    migrations = tmp_path / "migrations"
    migrations.mkdir()

    foundation = DEFAULT_MIGRATIONS_PATH / "0001_foundation.sql"
    (migrations / foundation.name).write_bytes(foundation.read_bytes())
    (migrations / "0002_broken.sql").write_text(
        "CREATE TABLE should_rollback (id TEXT PRIMARY KEY);\n"
        "THIS IS NOT VALID SQL;\n",
        encoding="utf-8",
    )

    database_path = tmp_path / "rollback.db"
    with pytest.raises(sqlite3.Error):
        apply_migrations(
            database_path,
            migrations_path=migrations,
        )

    connection = sqlite3.connect(database_path)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'should_rollback'"
        ).fetchone()
        assert exists is None

        applied = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert applied == [(1,)]
    finally:
        connection.close()
