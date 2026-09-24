from __future__ import annotations

import hashlib
from pathlib import Path


EXPECTED_SHA256 = (
    "915903ca7d7845c1d85c0b9ccb149ecff111d2f20fbf7dd7faa4a6b87e7a8e96"
)


def test_recovered_historical_migration_matches_recorded_checksum():
    root = Path(__file__).resolve().parents[1]
    migration = (
        root
        / "personal_learning_assistant"
        / "repositories"
        / "sqlite"
        / "migrations"
        / "0008_moodle_sync.sql"
    )

    assert migration.is_file()
    assert hashlib.sha256(migration.read_bytes()).hexdigest() == EXPECTED_SHA256

    text = migration.read_text(encoding="utf-8")
    assert "CREATE TABLE moodle_sync_files" in text
    assert "moodle_sync_files_course_status_ix" in text
    assert "moodle_sync_files_local_path_ix" in text
