from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _hash_tree(root: Path):
    result = {}
    if not root.exists():
        return result
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        result[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def _write_required_sources(data: Path):
    payloads = {
        "notes.json": [],
        "courses.json": {"version": 1, "courses": []},
        "learning_memory.json": {"version": "V1", "entries": []},
        "course_progress_history.json": {"version": 1, "courses": {}},
        "weekly_study_plans.json": {"version": 1, "plans": []},
        "multi_course_weekly_plans.json": {"version": 1, "plans": []},
        "assessments.json": {"version": 1, "assessments": []},
        "assessment_workspace.json": {"version": 1, "workspaces": []},
        "obsidian_config.json": {"version": 1, "enabled": False},
    }
    for name, value in payloads.items():
        (data / name).write_text(json.dumps(value), encoding="utf-8")
    (data / "resources.json").write_bytes(b"")


def test_legacy_source_scanner_is_read_only_and_deterministic(tmp_path):
    from personal_learning_assistant.migration.legacy_source_scanner import (
        STATUS_EMPTY,
        STATUS_MISSING,
        STATUS_VALID_JSON,
        scan_legacy_sources,
    )

    data = tmp_path / "data"
    data.mkdir()
    _write_required_sources(data)

    before = _hash_tree(data)
    first = scan_legacy_sources(data)
    second = scan_legacy_sources(data)
    after = _hash_tree(data)

    assert before == after
    assert first.manifest_hash == second.manifest_hash
    assert len(first.sources) == 12

    by_name = {Path(item.canonical_path).name: item for item in first.sources}
    assert by_name["courses.json"].status == STATUS_VALID_JSON
    assert by_name["courses.json"].source_version == "1"
    assert by_name["learning_memory.json"].source_version == "V1"
    assert by_name["resources.json"].status == STATUS_EMPTY
    assert by_name["resources.json"].source_hash == hashlib.sha256(b"").hexdigest()
    assert by_name["resources.json"].issue == ""
    assert by_name["intelligent_study_plans.json"].status == STATUS_MISSING
    assert by_name["semester_grade_config.json"].status == STATUS_MISSING

    portable = json.dumps(first.to_dict(), sort_keys=True)
    assert str(tmp_path) not in portable
    assert "data/courses.json" in portable


def test_scanner_flags_invalid_required_and_unexpected_json(tmp_path):
    from personal_learning_assistant.migration.legacy_source_scanner import (
        STATUS_INVALID_JSON,
        STATUS_MISSING,
        scan_legacy_sources,
    )

    data = tmp_path / "data"
    data.mkdir()
    (data / "courses.json").write_text("{broken", encoding="utf-8")
    (data / "extra.json").write_text("{}", encoding="utf-8")

    manifest = scan_legacy_sources(data)
    by_name = {Path(item.canonical_path).name: item for item in manifest.sources}

    assert by_name["courses.json"].status == STATUS_INVALID_JSON
    assert by_name["notes.json"].status == STATUS_MISSING
    assert "required" in by_name["notes.json"].issue
    assert manifest.unexpected_json_paths == ("data/extra.json",)


def test_scanner_missing_directory_does_not_create_it(tmp_path):
    from personal_learning_assistant.migration.legacy_source_scanner import (
        STATUS_MISSING,
        scan_legacy_sources,
    )

    data = tmp_path / "does-not-exist"
    manifest = scan_legacy_sources(data)

    assert not data.exists()
    assert all(source.status == STATUS_MISSING for source in manifest.sources)


def _apply_foundation_only(database_path, tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import (
        DEFAULT_MIGRATIONS_PATH,
        apply_migrations,
    )

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    source = DEFAULT_MIGRATIONS_PATH / "0001_foundation.sql"
    (migrations / source.name).write_bytes(source.read_bytes())
    assert apply_migrations(database_path, migrations_path=migrations) == (1,)


def test_import_ledger_is_idempotent_and_detects_conflicts(tmp_path):
    from personal_learning_assistant.migration.import_ledger import (
        MigrationImportConflictError,
        MigrationImportLedger,
        build_import_identity,
    )
    from personal_learning_assistant.repositories.sqlite.connection import (
        connect_database,
    )

    database_path = tmp_path / "ledger.db"
    _apply_foundation_only(database_path, tmp_path)
    connection = connect_database(database_path)

    try:
        ledger = MigrationImportLedger(connection)
        identity = build_import_identity(
            source_path="data/courses.json",
            source_hash="a" * 64,
            source_type="legacy_json",
            source_version="1",
            legacy_key="MA103N",
            target_table="courses",
        )

        first = ledger.record_import(
            identity,
            target_id="course-1",
            details={"kind": "course"},
            imported_at="2026-09-14T00:00:00Z",
        )
        second = ledger.record_import(
            identity,
            target_id="course-1",
            details={"kind": "ignored-on-repeat"},
        )

        assert first.created is True
        assert second.created is False
        assert second.record.id == first.record.id
        assert second.record.details == {"kind": "course"}
        assert len(ledger.list_for_source("data/courses.json")) == 1

        with pytest.raises(MigrationImportConflictError):
            ledger.record_import(identity, target_id="course-2")
    finally:
        connection.close()


def test_changed_source_hash_is_a_new_import_identity(tmp_path):
    from personal_learning_assistant.migration.import_ledger import (
        MigrationImportLedger,
        build_import_identity,
    )
    from personal_learning_assistant.repositories.sqlite.connection import (
        connect_database,
    )

    database_path = tmp_path / "ledger-hash.db"
    _apply_foundation_only(database_path, tmp_path)
    connection = connect_database(database_path)

    try:
        ledger = MigrationImportLedger(connection)
        one = build_import_identity(
            source_path="data/courses.json",
            source_hash="1" * 64,
            source_type="legacy_json",
            source_version="1",
            legacy_key="MA103N",
            target_table="courses",
        )
        two = build_import_identity(
            source_path="data/courses.json",
            source_hash="2" * 64,
            source_type="legacy_json",
            source_version="1",
            legacy_key="MA103N",
            target_table="courses",
        )

        assert ledger.record_import(one, target_id="course-1").created is True
        assert ledger.record_import(two, target_id="course-1").created is True
        assert len(ledger.list_for_source("data/courses.json")) == 2
    finally:
        connection.close()


def test_snapshot_to_ledger_uses_portable_identity(tmp_path):
    from personal_learning_assistant.migration.import_ledger import MigrationImportLedger
    from personal_learning_assistant.migration.legacy_source_scanner import (
        scan_legacy_sources,
    )
    from personal_learning_assistant.repositories.sqlite.connection import (
        connect_database,
    )

    data = tmp_path / "data"
    data.mkdir()
    _write_required_sources(data)
    manifest = scan_legacy_sources(data)
    courses = next(
        item
        for item in manifest.sources
        if item.canonical_path == "data/courses.json"
    )

    database_path = tmp_path / "snapshot.db"
    _apply_foundation_only(database_path, tmp_path)
    connection = connect_database(database_path)
    try:
        ledger = MigrationImportLedger(connection)
        result = ledger.record_snapshot_import(
            courses,
            legacy_key="MA103N",
            target_table="courses",
            target_id="course-1",
        )
        assert result.created is True
        assert result.record.identity.source_path == "data/courses.json"
        assert result.record.identity.source_hash == courses.source_hash
        assert result.record.identity.source_version == "1"
    finally:
        connection.close()


def test_invalid_source_snapshot_cannot_create_ledger_mapping(tmp_path):
    from personal_learning_assistant.migration.import_ledger import (
        MigrationImportLedger,
        MigrationImportValidationError,
    )
    from personal_learning_assistant.migration.legacy_source_scanner import (
        scan_legacy_sources,
    )
    from personal_learning_assistant.repositories.sqlite.connection import (
        connect_database,
    )

    data = tmp_path / "data"
    data.mkdir()
    (data / "courses.json").write_text("not-json", encoding="utf-8")
    courses = next(
        item
        for item in scan_legacy_sources(data).sources
        if item.canonical_path == "data/courses.json"
    )

    database_path = tmp_path / "invalid.db"
    _apply_foundation_only(database_path, tmp_path)
    connection = connect_database(database_path)
    try:
        ledger = MigrationImportLedger(connection)
        with pytest.raises(MigrationImportValidationError):
            ledger.record_snapshot_import(
                courses,
                legacy_key="MA103N",
                target_table="courses",
                target_id="course-1",
            )
    finally:
        connection.close()


def test_import_identity_rejects_absolute_paths_and_bad_hashes():
    from personal_learning_assistant.migration.import_ledger import (
        MigrationImportValidationError,
        build_import_identity,
    )

    with pytest.raises(MigrationImportValidationError):
        build_import_identity(
            source_path="C:/Users/example/data/courses.json",
            source_hash="a" * 64,
            source_type="legacy_json",
            target_table="courses",
        )

    with pytest.raises(MigrationImportValidationError):
        build_import_identity(
            source_path="data/courses.json",
            source_hash="not-a-hash",
            source_type="legacy_json",
            target_table="courses",
        )
