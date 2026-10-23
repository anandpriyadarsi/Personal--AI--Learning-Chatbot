"""Reserved optional migrations, checked on disposable databases only."""
import sqlite3
import pytest

from personal_learning_assistant.repositories.sqlite import migration_runner as runner


@pytest.mark.parametrize('assessment,memory,extras', [
    (False, False, ()), (True, False, (15,)),
    (False, True, (16,)), (True, True, (15, 16)),
])
def test_migration_options_and_restart_keep_checksum_history(tmp_path, assessment, memory, extras):
    path = tmp_path / 'options.db'
    assert runner.apply_migrations(path, enable_extended_assessment=assessment,
        enable_tutor_memory_candidates=memory) == tuple(range(1, 15)) + extras
    with sqlite3.connect(path) as db:
        history = db.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
        assert len(history) == 14 + len(extras)
        assert bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_memory_candidates'").fetchone()) == memory
        assert db.execute('SELECT COUNT(*) FROM learning_memory_entries').fetchone()[0] == 0
    assert runner.apply_migrations(path) == ()  # Disabled flags do not invalidate applied optional history.
    with sqlite3.connect(path) as db:
        assert history == db.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()


def test_optional_migration_checksum_drift_is_rejected_without_writes(tmp_path):
    path = tmp_path / 'drift.db'
    runner.apply_migrations(path, enable_tutor_memory_candidates=True)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE schema_migrations SET checksum=? WHERE version=16", ('0' * 64,))
    with pytest.raises(runner.MigrationDriftError, match='0016 checksum changed'):
        runner.apply_migrations(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM tutor_memory_candidates').fetchone()[0] == 0


def test_failed_optional_migration_rolls_back_partial_schema_and_ledger(tmp_path, monkeypatch):
    path = tmp_path / 'failure.db'
    runner.apply_migrations(path)
    original = runner._iter_sql_statements
    def broken(sql):
        if 'CREATE TABLE tutor_memory_candidates' in sql:
            yield 'CREATE TABLE should_roll_back (id TEXT);'
            yield 'INVALID SQL;'
        else:
            yield from original(sql)
    monkeypatch.setattr(runner, '_iter_sql_statements', broken)
    with pytest.raises(sqlite3.OperationalError):
        runner.apply_migrations(path, enable_tutor_memory_candidates=True)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0] == 14
        assert not db.execute("SELECT name FROM sqlite_master WHERE name IN ('should_roll_back','tutor_memory_candidates')").fetchall()
