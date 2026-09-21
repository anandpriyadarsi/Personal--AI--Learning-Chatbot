from __future__ import annotations

import hashlib
import sqlite3
import uuid

import pytest

import personal_learning_assistant.repositories.sqlite.obsidian_study_repository as repository_module
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.obsidian_study_repository import (
    ObsidianStudyRepositoryConflictError,
    ObsidianStudyRepositoryError,
    ObsidianStudyRepositoryNotFoundError,
    SQLiteObsidianStudyRepository,
)


NOW = "2026-09-19T15:00:00Z"
VAULT_IDENTITY = "vault:" + "a" * 64
NOTE_IDENTITY = "assistant:11111111-1111-4111-8111-111111111111"
SOURCE_HASH = "b" * 64


def _migrated_database(tmp_path):
    database_path = tmp_path / "learning_assistant.db"
    applied = apply_migrations(database_path)
    return database_path, applied


def _table_columns(connection, table_name):
    return {
        str(row[1]): {
            "type": str(row[2]),
            "not_null": bool(row[3]),
            "default": row[4],
            "primary_key": bool(row[5]),
        }
        for row in connection.execute(
            'PRAGMA table_info("{}")'.format(table_name)
        ).fetchall()
    }


def _repository(tmp_path):
    database_path, _ = _migrated_database(tmp_path)
    return database_path, SQLiteObsidianStudyRepository(database_path)


def _session_id():
    return str(uuid.uuid4())


def test_0005_obsidian_study_migration_is_complete_idempotent_and_clean(tmp_path):
    database_path, applied = _migrated_database(tmp_path)

    assert applied[:5] == (1, 2, 3, 4, 5)
    assert apply_migrations(database_path) == ()

    connection = sqlite3.connect(str(database_path))
    try:
        migrations = connection.execute(
            "SELECT version,name,length(checksum) "
            "FROM schema_migrations ORDER BY version"
        ).fetchall()
        migration_0005 = next(row for row in migrations if row[0] == 5)
        assert migration_0005 == (5, "obsidian_study_companion", 64)

        sessions = _table_columns(connection, "obsidian_reading_sessions")
        assert set(sessions) == {
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
        }
        assert sessions["active_seconds"]["default"] == "0"
        assert sessions["max_scroll_bps"]["default"] == "0"
        assert sessions["last_event_sequence"]["default"] == "0"

        entries = _table_columns(connection, "obsidian_companion_entries")
        assert set(entries) == {
            "id",
            "vault_identity",
            "note_identity",
            "relative_path",
            "entry_type",
            "entry_text",
            "created_at",
            "updated_at",
            "archived_at",
        }

        indexes = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name LIKE 'obsidian_%'"
            ).fetchall()
        }
        assert {
            "obsidian_reading_sessions_note_time_ix",
            "obsidian_reading_sessions_updated_ix",
            "obsidian_companion_entries_note_type_time_ix",
        }.issubset(indexes)

        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_0005_constraints_reject_invalid_session_and_companion_rows(tmp_path):
    database_path, _ = _migrated_database(tmp_path)
    connection = sqlite3.connect(str(database_path), isolation_level=None)
    try:
        base_session = (
            "session-1",
            VAULT_IDENTITY,
            NOTE_IDENTITY,
            "Math/LU.md",
            SOURCE_HASH,
            NOW,
            None,
            0,
            0,
            0,
            NOW,
            NOW,
        )
        connection.execute(
            "INSERT INTO obsidian_reading_sessions VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?)",
            base_session,
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO obsidian_reading_sessions VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "session-2",
                    VAULT_IDENTITY,
                    NOTE_IDENTITY,
                    "Math/LU.md",
                    SOURCE_HASH,
                    NOW,
                    None,
                    -1,
                    0,
                    0,
                    NOW,
                    NOW,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO obsidian_companion_entries VALUES "
                "(?,?,?,?,?,?,?,?,?)",
                (
                    "entry-1",
                    VAULT_IDENTITY,
                    NOTE_IDENTITY,
                    "Math/LU.md",
                    "answer",
                    "not an allowed type",
                    NOW,
                    NOW,
                    None,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO obsidian_companion_entries VALUES "
                "(?,?,?,?,?,?,?,?,?)",
                (
                    "entry-2",
                    VAULT_IDENTITY,
                    NOTE_IDENTITY,
                    "Math/LU.md",
                    "doubt",
                    "x" * 2001,
                    NOW,
                    NOW,
                    None,
                ),
            )
    finally:
        connection.close()


def test_reading_history_is_empty_and_read_only_before_tracking(tmp_path):
    database_path, repository = _repository(tmp_path)
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()

    history = repository.reading_history(
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
    )

    assert history == {
        "times_opened": 0,
        "last_read_at": None,
        "total_active_seconds": 0,
        "last_session_active_seconds": 0,
        "max_scroll_bps": 0,
        "recent_sessions": (),
    }
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == before


def test_session_events_aggregate_server_totals_and_ignore_replays(tmp_path):
    _database_path, repository = _repository(tmp_path)
    first_id = _session_id()

    created = repository.create_session(
        session_id=first_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now="2026-09-19T15:00:00Z",
    )
    assert created["active_seconds"] == 0
    assert created["accepted"] is True

    first = repository.heartbeat(
        session_id=first_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=30,
        scroll_bps=2500,
        now="2026-09-19T15:00:30Z",
    )
    assert first["active_seconds"] == 30
    assert first["max_scroll_bps"] == 2500
    assert first["accepted"] is True

    replay = repository.heartbeat(
        session_id=first_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=30,
        scroll_bps=9000,
        now="2026-09-19T15:00:31Z",
    )
    assert replay["accepted"] is False
    assert replay["active_seconds"] == 30
    assert replay["max_scroll_bps"] == 2500

    second = repository.heartbeat(
        session_id=first_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=2,
        delta_seconds=60,
        scroll_bps=5000,
        now="2026-09-19T15:01:30Z",
    )
    assert second["active_seconds"] == 90

    ended = repository.end_session(
        session_id=first_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=3,
        delta_seconds=10,
        scroll_bps=7500,
        now="2026-09-19T15:01:40Z",
    )
    assert ended["accepted"] is True
    assert ended["active_seconds"] == 100
    assert ended["max_scroll_bps"] == 7500
    assert ended["ended_at"] == "2026-09-19T15:01:40Z"

    end_replay = repository.end_session(
        session_id=first_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=3,
        delta_seconds=10,
        scroll_bps=9000,
        now="2026-09-19T15:01:41Z",
    )
    assert end_replay["accepted"] is False
    assert end_replay["active_seconds"] == 100
    assert end_replay["max_scroll_bps"] == 7500

    second_id = _session_id()
    repository.create_session(
        session_id=second_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now="2026-09-19T16:00:00Z",
    )
    repository.end_session(
        session_id=second_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=5,
        scroll_bps=1000,
        now="2026-09-19T16:00:05Z",
    )

    history = repository.reading_history(
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
    )
    assert history["times_opened"] == 2
    assert history["last_read_at"] == "2026-09-19T16:00:00Z"
    assert history["total_active_seconds"] == 105
    assert history["last_session_active_seconds"] == 5
    assert history["max_scroll_bps"] == 7500
    assert [item["id"] for item in history["recent_sessions"]] == [
        second_id,
        first_id,
    ]


def test_history_recent_sessions_is_capped_at_five(tmp_path):
    _database_path, repository = _repository(tmp_path)
    ids = []
    for ordinal in range(6):
        session_id = _session_id()
        ids.append(session_id)
        repository.create_session(
            session_id=session_id,
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
            relative_path="Math/LU.md",
            source_hash=SOURCE_HASH,
            now="2026-09-19T1{}:00:00Z".format(ordinal),
        )

    history = repository.reading_history(
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
    )

    assert history["times_opened"] == 6
    assert len(history["recent_sessions"]) == 5
    assert [item["id"] for item in history["recent_sessions"]] == list(
        reversed(ids[1:])
    )


def test_session_updates_require_exact_note_vault_and_source_scope(tmp_path):
    _database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )

    for changes in (
        {"vault_identity": "vault:" + "c" * 64},
        {"note_identity": "path:" + "d" * 64},
        {"source_hash": "e" * 64},
    ):
        values = {
            "session_id": session_id,
            "vault_identity": VAULT_IDENTITY,
            "note_identity": NOTE_IDENTITY,
            "source_hash": SOURCE_HASH,
            "sequence": 1,
            "delta_seconds": 10,
            "scroll_bps": 100,
            "now": "2026-09-19T15:00:10Z",
        }
        values.update(changes)
        with pytest.raises(ObsidianStudyRepositoryNotFoundError):
            repository.heartbeat(**values)


def test_heartbeat_after_end_is_a_conflict(tmp_path):
    _database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )
    repository.end_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=0,
        scroll_bps=0,
        now="2026-09-19T15:00:01Z",
    )

    with pytest.raises(ObsidianStudyRepositoryConflictError):
        repository.heartbeat(
            session_id=session_id,
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
            source_hash=SOURCE_HASH,
            sequence=2,
            delta_seconds=10,
            scroll_bps=100,
            now="2026-09-19T15:00:11Z",
        )


def test_end_finalizes_an_accepted_heartbeat_replay_without_double_counting(tmp_path):
    _database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )
    repository.heartbeat(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=30,
        scroll_bps=4000,
        now="2026-09-19T15:00:30Z",
    )

    ended = repository.end_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=30,
        scroll_bps=7500,
        now="2026-09-19T15:00:31Z",
    )

    assert ended["accepted"] is True
    assert ended["active_seconds"] == 30
    assert ended["max_scroll_bps"] == 7500
    assert ended["ended_at"] == "2026-09-19T15:00:31Z"
    replay = repository.end_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=30,
        scroll_bps=9000,
        now="2026-09-19T15:00:32Z",
    )
    assert replay["accepted"] is False
    assert replay["active_seconds"] == 30
    assert replay["max_scroll_bps"] == 7500


def test_end_replay_adds_only_activity_accrued_after_in_flight_heartbeat(tmp_path):
    _database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )
    repository.heartbeat(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=30,
        scroll_bps=4000,
        now="2026-09-19T15:00:30Z",
    )

    ended = repository.end_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=35,
        replayed_delta_seconds=30,
        scroll_bps=7500,
        now="2026-09-19T15:00:35Z",
    )

    assert ended["accepted"] is True
    assert ended["active_seconds"] == 35
    assert ended["max_scroll_bps"] == 7500
    assert ended["ended_at"] == "2026-09-19T15:00:35Z"


def test_end_counts_full_delta_when_it_beats_in_flight_heartbeat(tmp_path):
    _database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )

    ended = repository.end_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=35,
        replayed_delta_seconds=30,
        scroll_bps=7500,
        now="2026-09-19T15:00:35Z",
    )

    assert ended["accepted"] is True
    assert ended["active_seconds"] == 35
    with pytest.raises(ObsidianStudyRepositoryConflictError):
        repository.heartbeat(
            session_id=session_id,
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
            source_hash=SOURCE_HASH,
            sequence=1,
            delta_seconds=30,
            scroll_bps=4000,
            now="2026-09-19T15:00:36Z",
        )


@pytest.mark.parametrize("replayed_delta_seconds", (-1, 36, True, 1.5, "30"))
def test_end_rejects_invalid_replayed_delta_before_mutation(
    tmp_path, replayed_delta_seconds
):
    _database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )

    with pytest.raises(ValueError):
        repository.end_session(
            session_id=session_id,
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
            source_hash=SOURCE_HASH,
            sequence=1,
            delta_seconds=35,
            replayed_delta_seconds=replayed_delta_seconds,
            scroll_bps=7500,
            now="2026-09-19T15:00:35Z",
        )

    history = repository.reading_history(
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
    )
    assert history["total_active_seconds"] == 0
    assert history["recent_sessions"][0]["ended_at"] is None


def test_end_counts_outstanding_delta_when_heartbeat_never_arrived(tmp_path):
    _database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )

    ended = repository.end_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        source_hash=SOURCE_HASH,
        sequence=1,
        delta_seconds=30,
        scroll_bps=5000,
        now="2026-09-19T15:00:31Z",
    )

    assert ended["accepted"] is True
    assert ended["active_seconds"] == 30
    with pytest.raises(ObsidianStudyRepositoryConflictError):
        repository.heartbeat(
            session_id=session_id,
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
            source_hash=SOURCE_HASH,
            sequence=1,
            delta_seconds=30,
            scroll_bps=5000,
            now="2026-09-19T15:00:32Z",
        )


def test_repository_rolls_back_failed_session_update_and_redacts_database_error(tmp_path):
    database_path, repository = _repository(tmp_path)
    session_id = _session_id()
    repository.create_session(
        session_id=session_id,
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        source_hash=SOURCE_HASH,
        now=NOW,
    )
    connection = sqlite3.connect(str(database_path), isolation_level=None)
    try:
        connection.execute(
            "CREATE TRIGGER fail_obsidian_session_update "
            "BEFORE UPDATE ON obsidian_reading_sessions "
            "BEGIN SELECT RAISE(ABORT, 'C:/SECRET/database failure'); END"
        )
    finally:
        connection.close()

    with pytest.raises(ObsidianStudyRepositoryError) as error:
        repository.heartbeat(
            session_id=session_id,
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
            source_hash=SOURCE_HASH,
            sequence=1,
            delta_seconds=10,
            scroll_bps=100,
            now="2026-09-19T15:00:10Z",
        )
    assert "SECRET" not in str(error.value)

    connection = sqlite3.connect(str(database_path))
    try:
        row = connection.execute(
            "SELECT active_seconds,last_event_sequence "
            "FROM obsidian_reading_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        assert row == (0, 0)
    finally:
        connection.close()


def test_missing_or_unmigrated_database_is_unavailable_without_creation(tmp_path):
    missing = tmp_path / "missing.db"
    repository = SQLiteObsidianStudyRepository(missing)

    with pytest.raises(ObsidianStudyRepositoryError):
        repository.reading_history(
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
        )
    assert not missing.exists()


def test_schema_validation_failure_closes_open_connection(tmp_path):
    class EmptyCursor:
        @staticmethod
        def fetchall():
            return []

    class MissingSchemaConnection:
        def __init__(self):
            self.closed = False

        @staticmethod
        def execute(_query):
            return EmptyCursor()

        def close(self):
            self.closed = True

    connection = MissingSchemaConnection()
    repository = SQLiteObsidianStudyRepository(
        tmp_path / "injected.db",
        connection_factory=lambda _path, *, writable: connection,
    )

    with pytest.raises(ObsidianStudyRepositoryError):
        repository.reading_history(
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
        )

    assert connection.closed is True


def test_open_database_closes_connection_when_pragma_initialization_fails(
    tmp_path, monkeypatch
):
    class BrokenPragmaConnection:
        def __init__(self):
            self.row_factory = None
            self.closed = False

        @staticmethod
        def execute(_query):
            raise sqlite3.OperationalError("C:/SECRET pragma failure")

        def close(self):
            self.closed = True

    database_path = tmp_path / "existing.db"
    database_path.touch()
    connection = BrokenPragmaConnection()
    monkeypatch.setattr(
        repository_module.sqlite3,
        "connect",
        lambda *_args, **_kwargs: connection,
    )

    with pytest.raises(ObsidianStudyRepositoryError) as error:
        repository_module._open_database(database_path, writable=False)

    assert connection.closed is True
    assert "SECRET" not in str(error.value)


def test_companion_entries_persist_with_type_order_and_note_isolation(tmp_path):
    database_path, repository = _repository(tmp_path)
    note_path = tmp_path / "Vault" / "Math" / "LU.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# LU\nAuthoritative Markdown\n", encoding="utf-8")
    markdown_before = hashlib.sha256(note_path.read_bytes()).hexdigest()

    doubt = repository.add_entry(
        entry_id=str(uuid.uuid4()),
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        entry_type="doubt",
        entry_text="Why is pivoting required?",
        now="2026-09-19T15:01:00Z",
    )
    key_point = repository.add_entry(
        entry_id=str(uuid.uuid4()),
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        entry_type="key_point",
        entry_text="Doolittle keeps the diagonal of L equal to one.",
        now="2026-09-19T15:02:00Z",
    )
    repository.add_entry(
        entry_id=str(uuid.uuid4()),
        vault_identity=VAULT_IDENTITY,
        note_identity="path:" + "c" * 64,
        relative_path="Math/Other.md",
        entry_type="key_point",
        entry_text="Belongs to another note.",
        now="2026-09-19T15:03:00Z",
    )

    reopened = SQLiteObsidianStudyRepository(database_path)
    entries = reopened.list_entries(
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
    )

    assert [item["id"] for item in entries] == [key_point["id"], doubt["id"]]
    assert [item["entry_type"] for item in entries] == ["key_point", "doubt"]
    assert entries[0]["entry_text"].endswith("equal to one.")
    assert all(item["archived_at"] is None for item in entries)
    assert hashlib.sha256(note_path.read_bytes()).hexdigest() == markdown_before


def test_archive_hides_entry_and_is_persistent(tmp_path):
    database_path, repository = _repository(tmp_path)
    entry = repository.add_entry(
        entry_id=str(uuid.uuid4()),
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        entry_type="key_point",
        entry_text="Triangular solves follow factorization.",
        now=NOW,
    )

    archived = repository.archive_entry(
        entry_id=entry["id"],
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        now="2026-09-19T15:05:00Z",
    )

    assert archived["archived_at"] == "2026-09-19T15:05:00Z"
    reopened = SQLiteObsidianStudyRepository(database_path)
    assert reopened.list_entries(
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
    ) == ()


def test_archive_cannot_cross_note_or_vault_scope(tmp_path):
    _database_path, repository = _repository(tmp_path)
    entry = repository.add_entry(
        entry_id=str(uuid.uuid4()),
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
        relative_path="Math/LU.md",
        entry_type="doubt",
        entry_text="What happens with a zero pivot?",
        now=NOW,
    )

    with pytest.raises(ObsidianStudyRepositoryNotFoundError):
        repository.archive_entry(
            entry_id=entry["id"],
            vault_identity=VAULT_IDENTITY,
            note_identity="path:" + "f" * 64,
            now="2026-09-19T15:05:00Z",
        )
    with pytest.raises(ObsidianStudyRepositoryNotFoundError):
        repository.archive_entry(
            entry_id=entry["id"],
            vault_identity="vault:" + "f" * 64,
            note_identity=NOTE_IDENTITY,
            now="2026-09-19T15:05:00Z",
        )

    assert [
        item["id"]
        for item in repository.list_entries(
            vault_identity=VAULT_IDENTITY,
            note_identity=NOTE_IDENTITY,
        )
    ] == [entry["id"]]


def test_companion_list_is_read_only_and_database_constraints_reject_bad_text(tmp_path):
    database_path, repository = _repository(tmp_path)
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()

    assert repository.list_entries(
        vault_identity=VAULT_IDENTITY,
        note_identity=NOTE_IDENTITY,
    ) == ()
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == before

    connection = sqlite3.connect(str(database_path), isolation_level=None)
    try:
        for entry_type, entry_text in (
            ("answer", "not allowed"),
            ("doubt", "   "),
            ("key_point", "x" * 2001),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO obsidian_companion_entries "
                    "(id,vault_identity,note_identity,relative_path,entry_type,"
                    "entry_text,created_at,updated_at,archived_at) "
                    "VALUES (?,?,?,?,?,?,?,?,NULL)",
                    (
                        str(uuid.uuid4()),
                        VAULT_IDENTITY,
                        NOTE_IDENTITY,
                        "Math/LU.md",
                        entry_type,
                        entry_text,
                        NOW,
                        NOW,
                    ),
                )
    finally:
        connection.close()
