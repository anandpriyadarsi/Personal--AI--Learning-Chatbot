from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.authority_promotion import (
    AuthorityControlState,
    BACKEND_DUAL_READ,
    BACKEND_LEGACY,
    BACKEND_SQLITE,
    LegacyWriteBlockedError,
    LocalMutationLock,
    OPTIONAL_STRUCTURED_SOURCE_FILENAMES,
    PromotionInputError,
    PromotionLockError,
    PromotionSafetyError,
    PromotionValidationError,
    REQUIRED_STRUCTURED_TABLES,
    STRUCTURED_SOURCE_FILENAMES,
    assert_legacy_write_allowed,
    build_sqlite_authority_state,
    create_final_cutover_backup,
    read_authority_control,
    scan_structured_sources,
    validate_control_transition,
    validate_sqlite_readiness,
    validate_structured_manifest,
    verify_manifest_unchanged,
    write_authority_control_atomic,
)
from personal_learning_assistant.repositories.sqlite.connection import (
    connect_database,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _structured_data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for filename in STRUCTURED_SOURCE_FILENAMES:
        if filename in OPTIONAL_STRUCTURED_SOURCE_FILENAMES:
            continue
        _write_json(data / filename, {"version": 1, "fixture": filename})
    return data


def _migrated_connection(tmp_path: Path):
    db = tmp_path / "shadow.db"
    assert (apply_migrations(db))[:2] == (1, 2)
    return connect_database(db, synchronous="FULL")


def test_missing_control_defaults_to_legacy_without_creating_file(tmp_path):
    path = tmp_path / "authority.json"
    state = read_authority_control(path)
    assert state.storage_backend == BACKEND_LEGACY
    assert state.legacy_writes_blocked is False
    assert not path.exists()


def test_dual_read_control_allows_legacy_writes(tmp_path):
    path = tmp_path / "authority.json"
    state = AuthorityControlState(storage_backend=BACKEND_DUAL_READ)
    write_authority_control_atomic(path, state)
    assert assert_legacy_write_allowed(path) == state


def test_sqlite_state_requires_writer_block_and_evidence():
    with pytest.raises(PromotionInputError):
        AuthorityControlState(storage_backend=BACKEND_SQLITE)


def test_sqlite_control_blocks_legacy_writer(tmp_path):
    db = tmp_path / "verified.db"
    db.write_bytes(b"sqlite-backup-evidence")
    state = build_sqlite_authority_state(
        source_manifest_hash="a" * 64,
        sqlite_backup_path=db,
        cutover_id="cutover-test",
        promoted_at="2099-01-01T00:00:00Z",
    )
    path = tmp_path / "authority.json"
    write_authority_control_atomic(path, state)
    with pytest.raises(LegacyWriteBlockedError):
        assert_legacy_write_allowed(path)


def test_control_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "authority.json"
    state = AuthorityControlState(storage_backend=BACKEND_DUAL_READ)
    write_authority_control_atomic(path, state)
    assert read_authority_control(path) == state
    assert not list(tmp_path.glob(".authority.json.*.tmp"))


def test_control_compare_and_swap_detects_changed_state(tmp_path):
    path = tmp_path / "authority.json"
    legacy = AuthorityControlState()
    dual = AuthorityControlState(storage_backend=BACKEND_DUAL_READ)
    write_authority_control_atomic(path, dual)
    with pytest.raises(PromotionSafetyError):
        write_authority_control_atomic(path, legacy, expected_current=legacy)


def test_unknown_control_field_is_rejected(tmp_path):
    path = tmp_path / "authority.json"
    _write_json(path, {"version": 1, "storage_backend": "legacy", "surprise": True})
    with pytest.raises(PromotionInputError):
        read_authority_control(path)


def test_sqlite_rollback_requires_explicit_approval(tmp_path):
    db = tmp_path / "verified.db"
    db.write_bytes(b"db")
    sqlite_state = build_sqlite_authority_state(
        source_manifest_hash="b" * 64,
        sqlite_backup_path=db,
        cutover_id="cutover-1",
        promoted_at="2099-01-01T00:00:00Z",
    )
    legacy_state = AuthorityControlState()
    with pytest.raises(PromotionSafetyError):
        validate_control_transition(sqlite_state, legacy_state)
    validate_control_transition(sqlite_state, legacy_state, allow_rollback=True)


def test_mutation_lock_is_exclusive_and_releasable(tmp_path):
    path = tmp_path / "phase4-cutover.lock"
    first = LocalMutationLock(path)
    second = LocalMutationLock(path)
    evidence = first.acquire()
    assert path.exists()
    assert evidence.token
    with pytest.raises(PromotionLockError):
        second.acquire()
    first.release()
    assert not path.exists()


def test_mutation_lock_never_steals_existing_stale_file(tmp_path):
    path = tmp_path / "phase4-cutover.lock"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(PromotionLockError):
        LocalMutationLock(path).acquire()
    assert path.exists()


def test_mutation_lock_refuses_to_delete_changed_ownership(tmp_path):
    path = tmp_path / "phase4-cutover.lock"
    lock = LocalMutationLock(path)
    lock.acquire()
    path.write_text(json.dumps({"token": "different"}), encoding="utf-8")
    with pytest.raises(PromotionLockError):
        lock.release()
    assert path.exists()


def test_structured_source_list_does_not_promote_phase5_domains():
    assert "notes.json" not in STRUCTURED_SOURCE_FILENAMES
    assert "resources.json" not in STRUCTURED_SOURCE_FILENAMES
    assert "obsidian_config.json" not in STRUCTURED_SOURCE_FILENAMES


def test_structured_manifest_accepts_required_and_missing_optional_sources(tmp_path):
    data = _structured_data_dir(tmp_path)
    manifest = scan_structured_sources(data)
    validate_structured_manifest(manifest)
    statuses = {Path(item.canonical_path).name: item.status for item in manifest.sources}
    for optional in OPTIONAL_STRUCTURED_SOURCE_FILENAMES:
        assert statuses[optional] == "missing"


def test_structured_manifest_rejects_missing_required_source(tmp_path):
    data = _structured_data_dir(tmp_path)
    (data / "courses.json").unlink()
    manifest = scan_structured_sources(data)
    with pytest.raises(PromotionValidationError):
        validate_structured_manifest(manifest)


def test_manifest_verification_passes_when_sources_are_unchanged(tmp_path):
    data = _structured_data_dir(tmp_path)
    before = scan_structured_sources(data)
    after = scan_structured_sources(data)
    result = verify_manifest_unchanged(before, after)
    assert result.unchanged


def test_manifest_verification_rejects_delta_after_lock_scan(tmp_path):
    data = _structured_data_dir(tmp_path)
    before = scan_structured_sources(data)
    _write_json(data / "courses.json", {"version": 1, "changed": True})
    after = scan_structured_sources(data)
    with pytest.raises(PromotionValidationError):
        verify_manifest_unchanged(before, after)


def test_sqlite_readiness_requires_phase3_schema(tmp_path):
    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(PromotionValidationError):
            validate_sqlite_readiness(connection)
    finally:
        connection.close()


def test_sqlite_readiness_accepts_full_migrated_schema_without_writes(tmp_path):
    connection = _migrated_connection(tmp_path)
    try:
        before = connection.total_changes
        result = validate_sqlite_readiness(connection)
        assert result.passed
        assert set((1, 2)).issubset(result.migration_versions)
        assert set(REQUIRED_STRUCTURED_TABLES).isdisjoint(result.missing_tables)
        assert connection.total_changes == before
    finally:
        connection.close()


def test_sqlite_readiness_detects_foreign_key_corruption(tmp_path):
    connection = _migrated_connection(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO semester_courses (semester_id, course_id) VALUES (?, ?)",
            ("missing-semester", "missing-course"),
        )
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(PromotionValidationError):
            validate_sqlite_readiness(connection)
    finally:
        connection.close()


def test_final_backup_copies_exact_source_bytes_and_online_sqlite(tmp_path):
    data = _structured_data_dir(tmp_path)
    manifest = scan_structured_sources(data)
    connection = _migrated_connection(tmp_path)
    backup_parent = tmp_path / "backups"
    backup_parent.mkdir()
    output = backup_parent / "cutover-1"
    try:
        before_changes = connection.total_changes
        source_bytes = {p.name: p.read_bytes() for p in data.glob("*.json")}
        result = create_final_cutover_backup(
            connection,
            manifest,
            data_directory=data,
            output_directory=output,
            authority_state_before=AuthorityControlState(),
        )
        assert result.manifest_path.exists()
        assert result.sqlite_backup_path.exists()
        assert connection.total_changes == before_changes
        for name, raw in source_bytes.items():
            assert (output / "legacy_structured_json" / name).read_bytes() == raw
        backup = sqlite3.connect(str(result.sqlite_backup_path))
        try:
            assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert backup.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            backup.close()
    finally:
        connection.close()


def test_final_backup_refuses_to_overwrite_existing_directory(tmp_path):
    data = _structured_data_dir(tmp_path)
    manifest = scan_structured_sources(data)
    connection = _migrated_connection(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    try:
        with pytest.raises(PromotionSafetyError):
            create_final_cutover_backup(
                connection,
                manifest,
                data_directory=data,
                output_directory=output,
            )
    finally:
        connection.close()


def test_final_backup_refuses_live_data_subdirectory(tmp_path):
    data = _structured_data_dir(tmp_path)
    manifest = scan_structured_sources(data)
    connection = _migrated_connection(tmp_path)
    try:
        with pytest.raises(PromotionSafetyError):
            create_final_cutover_backup(
                connection,
                manifest,
                data_directory=data,
                output_directory=data / "cutover-backup",
            )
    finally:
        connection.close()


def test_backup_fails_if_source_changes_after_manifest(tmp_path):
    data = _structured_data_dir(tmp_path)
    manifest = scan_structured_sources(data)
    _write_json(data / "assessments.json", {"version": 1, "delta": True})
    connection = _migrated_connection(tmp_path)
    parent = tmp_path / "backups"
    parent.mkdir()
    output = parent / "cutover"
    try:
        with pytest.raises(PromotionValidationError):
            create_final_cutover_backup(
                connection,
                manifest,
                data_directory=data,
                output_directory=output,
            )
        assert not output.exists()
    finally:
        connection.close()


def test_build_sqlite_authority_state_uses_verified_backup_hash(tmp_path):
    backup = tmp_path / "learning_assistant.db"
    backup.write_bytes(b"verified-final-backup")
    state = build_sqlite_authority_state(
        source_manifest_hash="c" * 64,
        sqlite_backup_path=backup,
        cutover_id="phase4-final",
        promoted_at="2099-01-01T00:00:00Z",
    )
    assert state.storage_backend == BACKEND_SQLITE
    assert state.legacy_writes_blocked is True
    assert len(state.sqlite_sha256) == 64


def test_no_helper_has_implicit_production_database_path():
    import inspect
    import personal_learning_assistant.migration.authority_promotion as module

    source = inspect.getsource(module)
    assert "data/learning_assistant.db" not in source
    assert "DATABASE_PATH" not in source
