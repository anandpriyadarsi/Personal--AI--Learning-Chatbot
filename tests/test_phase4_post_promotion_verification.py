from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.authority_promotion import (
    AuthorityControlState,
    scan_structured_sources,
    write_authority_control_atomic,
)
from personal_learning_assistant.migration.post_promotion_verification import (
    EXPECTED_STORES,
    PostPromotionVerificationError,
    _find_deferred_study_plan_topics,
    verify_post_promotion_closure,
)
from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
    PROJECTION_PREFIX,
)
from personal_learning_assistant.migration.compatibility_projection_seed import (
    SEED_MANIFEST_SETTING,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


REQUIRED_JSON = (
    "courses.json",
    "assessments.json",
    "assessment_workspace.json",
    "learning_memory.json",
    "course_progress_history.json",
    "weekly_study_plans.json",
    "multi_course_weekly_plans.json",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    data = root / "data"
    data.mkdir(parents=True)
    for filename in REQUIRED_JSON:
        (data / filename).write_text("{}\n", encoding="utf-8")
    db = data / "learning_assistant.db"
    apply_migrations(db)

    manifest = scan_structured_sources(data)
    connection = sqlite3.connect(str(db), isolation_level=None)
    try:
        for store in EXPECTED_STORES:
            connection.execute(
                "INSERT INTO app_settings (key,value_json,updated_at) VALUES (?,?,?)",
                (PROJECTION_PREFIX + store, "{}", "2026-09-15T00:00:00Z"),
            )
        connection.execute(
            "INSERT INTO app_settings (key,value_json,updated_at) VALUES (?,?,?)",
            (
                SEED_MANIFEST_SETTING,
                json.dumps(manifest.manifest_hash),
                "2026-09-15T00:00:00Z",
            ),
        )
    finally:
        connection.close()

    state = AuthorityControlState(
        storage_backend="sqlite",
        cutover_id="test-cutover",
        source_manifest_hash=manifest.manifest_hash,
        sqlite_sha256=_sha(db),
        promoted_at="2026-09-15T00:00:00Z",
        legacy_writes_blocked=True,
    )
    write_authority_control_atomic(root / ".phase4_authority.json", state)
    return root


def test_clean_promoted_runtime_passes_read_only_closure(tmp_path):
    root = _fixture_root(tmp_path)
    db = root / "data" / "learning_assistant.db"
    before = db.read_bytes()
    report = verify_post_promotion_closure(
        project_root=root,
        require_promoted_database_hash=True,
    )
    assert report.status == "pass"
    assert report.routed_store_count == 9
    assert report.legacy_write_guard_blocked is True
    assert report.integrity_check == ("ok",)
    assert report.foreign_key_violation_count == 0
    assert report.reads_only is True
    assert db.read_bytes() == before


def test_source_drift_blocks_closure(tmp_path):
    root = _fixture_root(tmp_path)
    (root / "data" / "courses.json").write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(PostPromotionVerificationError, match="source manifest changed"):
        verify_post_promotion_closure(project_root=root)


def test_database_byte_drift_blocks_immediate_closure(tmp_path):
    root = _fixture_root(tmp_path)
    db = root / "data" / "learning_assistant.db"
    connection = sqlite3.connect(str(db), isolation_level=None)
    try:
        connection.execute(
            "INSERT INTO app_settings (key,value_json,updated_at) VALUES (?,?,?)",
            ("test.after_promotion", "{}", "2026-09-15T00:00:01Z"),
        )
    finally:
        connection.close()
    with pytest.raises(PostPromotionVerificationError, match="bytes changed"):
        verify_post_promotion_closure(project_root=root)


def test_missing_projection_is_detected(tmp_path):
    root = _fixture_root(tmp_path)
    db = root / "data" / "learning_assistant.db"
    connection = sqlite3.connect(str(db), isolation_level=None)
    try:
        connection.execute(
            "DELETE FROM app_settings WHERE key=?",
            (PROJECTION_PREFIX + EXPECTED_STORES[0],),
        )
    finally:
        connection.close()

    # Update the control hash only so this test reaches projection validation.
    manifest = scan_structured_sources(root / "data")
    state = AuthorityControlState(
        storage_backend="sqlite",
        cutover_id="test-cutover",
        source_manifest_hash=manifest.manifest_hash,
        sqlite_sha256=_sha(db),
        promoted_at="2026-09-15T00:00:00Z",
        legacy_writes_blocked=True,
    )
    # Replace test control through direct test bytes; production transition API
    # intentionally rejects sqlite->sqlite replacement with changed evidence.
    (root / ".phase4_authority.json").write_text(
        json.dumps(state.to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PostPromotionVerificationError, match="missing Phase 4 compatibility projection"):
        verify_post_promotion_closure(project_root=root)


def test_deferred_study_plan_topic_is_reported_without_raw_text(tmp_path):
    db = tmp_path / "review.db"
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.execute(
        "CREATE TABLE migration_imports ("
        "id TEXT, source_path TEXT, source_hash TEXT, source_type TEXT, "
        "source_version TEXT, legacy_key TEXT, target_table TEXT, target_id TEXT, "
        "imported_at TEXT, details_json TEXT)"
    )
    connection.execute(
        "CREATE TABLE study_plan_items (id TEXT PRIMARY KEY, topic_id TEXT)"
    )
    details = {
        "kind": "study_plan_item",
        "raw_course_id": "C1",
        "raw_topic": "Private Topic Value",
        "target_course_id": "course-1",
        "target_topic_id": None,
    }
    connection.execute(
        "INSERT INTO migration_imports VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "m1",
            "data/weekly_study_plans.json",
            "a" * 64,
            "legacy_json",
            "1",
            "plan:1/item:1",
            "study_plan_items",
            "item-1",
            "2026-09-15T00:00:00Z",
            json.dumps(details),
        ),
    )
    connection.execute(
        "INSERT INTO study_plan_items(id,topic_id) VALUES (?,NULL)", ("item-1",)
    )

    class Snapshot:
        canonical_path = "data/weekly_study_plans.json"
        source_hash = "a" * 64
        status = "valid_json"

    class Manifest:
        sources = (Snapshot(),)

    result = _find_deferred_study_plan_topics(connection, Manifest())
    connection.close()
    assert len(result) == 1
    assert result[0].legacy_key == "plan:1/item:1"
    assert "Private Topic Value" not in json.dumps(result[0].to_dict())


def test_active_cutover_lock_blocks_closure(tmp_path):
    root = _fixture_root(tmp_path)
    (root / ".phase4_cutover.lock").write_text("{}\n", encoding="utf-8")
    with pytest.raises(PostPromotionVerificationError, match="lock remains"):
        verify_post_promotion_closure(project_root=root)


def test_backup_verifier_accepts_final_promotion_evidence_schema(tmp_path):
    from personal_learning_assistant.migration.post_promotion_verification import (
        verify_promotion_backup,
    )

    backup = tmp_path / "backup"
    legacy = backup / "legacy_structured_json"
    sqlite_dir = backup / "sqlite"
    legacy.mkdir(parents=True)
    sqlite_dir.mkdir()

    source_file = legacy / "courses.json"
    source_file.write_text("{}\n", encoding="utf-8")

    sqlite_backup = sqlite_dir / "learning_assistant.db"
    apply_migrations(sqlite_backup)
    sqlite_sha = _sha(sqlite_backup)
    source_sha = _sha(source_file)
    source_manifest_hash = "b" * 64
    cutover_id = "cutover-1"

    artifacts = [
        {
            "relative_path": "legacy_structured_json/courses.json",
            "kind": "legacy_structured_json",
            "sha256": source_sha,
            "byte_count": source_file.stat().st_size,
        },
        {
            "relative_path": "sqlite/learning_assistant.db",
            "kind": "sqlite_online_backup",
            "sha256": sqlite_sha,
            "byte_count": sqlite_backup.stat().st_size,
        },
    ]
    manifest = {
        "version": 1,
        "created_at": "2026-09-15T00:00:00Z",
        "source_manifest_hash": source_manifest_hash,
        "authority_state_before": {"storage_backend": "legacy"},
        "artifacts": artifacts,
    }
    manifest_path = backup / "cutover_backup_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    manifest_sha = _sha(manifest_path)

    evidence = {
        "version": 1,
        "status": "promoted",
        "cutover_id": cutover_id,
        "promoted_at": "2026-09-15T00:00:00Z",
        "source_manifest_hash": source_manifest_hash,
        "initial_sqlite_authority_sha256": sqlite_sha,
        "backup_manifest_sha256": manifest_sha,
        "new_authority_state": {
            "version": 1,
            "storage_backend": "sqlite",
            "cutover_id": cutover_id,
            "source_manifest_hash": source_manifest_hash,
            "sqlite_sha256": sqlite_sha,
            "promoted_at": "2026-09-15T00:00:00Z",
            "legacy_writes_blocked": True,
        },
    }
    (backup / "final_promotion_evidence.json").write_text(
        json.dumps(evidence, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verify_promotion_backup(
        backup,
        expected_cutover_id=cutover_id,
        expected_source_manifest_hash=source_manifest_hash,
        expected_sqlite_sha256=sqlite_sha,
    )
    assert result.evidence_present is True
    assert result.manifest_sha256 == manifest_sha
