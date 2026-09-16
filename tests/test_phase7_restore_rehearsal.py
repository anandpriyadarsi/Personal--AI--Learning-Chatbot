from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal_learning_assistant.phase7.recovery_bundle import (
    CONFIRMATION_PHRASE as BACKUP_CONFIRMATION,
    RecoveryVerificationError,
    create_two_verified_backups,
)
from personal_learning_assistant.phase7.restore_rehearsal import (
    CONFIRMATION_PHRASE,
    Phase73SafetyError,
    _reverse_semantic_sha,
    preview_restore_rehearsal,
    rehearse_recovery_pair,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)


NOW = "2026-09-16T20:00:00Z"


def _authority(path):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "storage_backend": "sqlite",
                "cutover_id": "cut",
                "source_manifest_hash": "a" * 64,
                "sqlite_sha256": "b" * 64,
                "promoted_at": NOW,
                "legacy_writes_blocked": True,
            }
        ),
        encoding="utf-8",
    )


def _project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data"
    data.mkdir()
    (project / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

    db = data / "learning_assistant.db"
    applied = apply_migrations(db)
    assert applied[:4] == (1, 2, 3, 4)

    c = sqlite3.connect(str(db))
    c.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
        "confidence,raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t1','c1','LU Factorization','lu factorization',1,'learning',2,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.commit()
    c.close()

    authority = project / ".phase4_authority.json"
    _authority(authority)
    (data / "courses.json").write_text(
        '{"version":1,"courses":[]}\n',
        encoding="utf-8",
    )
    return project, db, authority


def _pair(tmp_path):
    project, db, authority = _project(tmp_path)
    recovery = tmp_path / "phase7-recovery-pair"
    create_two_verified_backups(
        project_root=project,
        database_path=db,
        authority_path=authority,
        output_root=recovery,
        source_roots={},
        git_identity={
            "commit": "abc",
            "branch": "phase7/deprecation-observation",
        },
        confirmation=BACKUP_CONFIRMATION,
    )
    return project, db, authority, recovery


def _retrieval_probe(runtime_db, restored_root, **kwargs):
    c = sqlite3.connect(str(runtime_db))
    try:
        logical_course = c.execute(
            "SELECT id FROM courses WHERE code='MA103N'"
        ).fetchone()[0]
    finally:
        c.close()
    assert logical_course == "c1"
    return {
        "source_fingerprint": "retrieval-source",
        "chunk_count": 10,
        "hit_count": 1,
        "hit_chunk_ids": ("chunk-1",),
    }


def _workspace_probe(runtime_db, restored_root, **kwargs):
    c = sqlite3.connect(str(runtime_db))
    try:
        count = c.execute(
            "SELECT COUNT(*) FROM topics WHERE course_id='c1'"
        ).fetchone()[0]
    finally:
        c.close()
    assert count == 1
    return {
        "sha256": "workspace-state",
        "topic_count": 1,
        "action_count": 1,
    }


def _reverse_probe(exact_db, restored_root, **kwargs):
    c = sqlite3.connect(str(exact_db))
    try:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        c.close()
    return {
        "sha256": "reverse-state",
        "export_status": "pass_with_documented_differences",
        "restore_status": "pass",
        "migration_idempotent": True,
        "import_idempotent": True,
    }


def _rehearse(tmp_path):
    project, db, authority, recovery = _pair(tmp_path)
    work = tmp_path / "phase7-restore-rehearsal"
    before = {
        path.relative_to(recovery).as_posix(): path.read_bytes()
        for path in recovery.rglob("*")
        if path.is_file()
    }
    result = rehearse_recovery_pair(
        recovery_root=recovery,
        project_root=project,
        work_root=work,
        course_code="MA103N",
        as_of=date(2026, 9, 16),
        confirmation=CONFIRMATION_PHRASE,
        retrieval_probe=_retrieval_probe,
        workspace_probe=_workspace_probe,
        reverse_probe=_reverse_probe,
    )
    after = {
        path.relative_to(recovery).as_posix(): path.read_bytes()
        for path in recovery.rglob("*")
        if path.is_file()
    }
    return result, work, project, db, authority, recovery, before, after


def test_preview_verifies_pair_and_performs_no_restore(tmp_path):
    project, db, authority, recovery = _pair(tmp_path)
    before = {
        path.relative_to(recovery).as_posix(): path.read_bytes()
        for path in recovery.rglob("*")
        if path.is_file()
    }
    result = preview_restore_rehearsal(recovery)
    assert result["pair_verified"] is True
    assert result["writes_performed"] is False
    assert result["pair_restore_performed"] is False
    assert not (tmp_path / "phase7-restore-rehearsal").exists()
    after = {
        path.relative_to(recovery).as_posix(): path.read_bytes()
        for path in recovery.rglob("*")
        if path.is_file()
    }
    assert before == after


def test_full_pair_restore_is_isolated_and_equivalent(tmp_path):
    result, work, project, db, authority, recovery, before, after = _rehearse(
        tmp_path
    )
    assert result.status == "pass"
    assert result.retained_pair_unchanged is True
    assert result.backups_equivalent is True
    assert result.restore_performed_only_in_isolation is True
    assert before == after
    assert result.backup_a.sqlite_logical_sha256 == (
        result.backup_b.sqlite_logical_sha256
    )
    assert result.backup_a.workspace_sha256 == result.backup_b.workspace_sha256
    assert (
        result.backup_a.retrieval_source_fingerprint
        == result.backup_b.retrieval_source_fingerprint
    )
    assert (
        result.backup_a.reverse_export_sha256
        == result.backup_b.reverse_export_sha256
    )


def test_exact_restored_database_matches_bundle_identity(tmp_path):
    result, work, project, db, authority, recovery, *_ = _rehearse(tmp_path)
    for label in ("A", "B"):
        path = (
            work
            / "restored-{}".format(label)
            / "state"
            / "phase7_restored_{}.db".format(label.lower())
        )
        c = sqlite3.connect(str(path))
        try:
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert not c.execute("PRAGMA foreign_key_check").fetchall()
            assert tuple(
                row[0]
                for row in c.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            )[:4] == (1, 2, 3, 4)
        finally:
            c.close()


def test_runtime_clone_is_separate_from_exact_authority_copy(tmp_path):
    result, work, project, db, authority, recovery, *_ = _rehearse(tmp_path)
    a = work / "restored-A"
    exact = a / "state" / "phase7_restored_a.db"
    runtime = a / "runtime" / "phase7_runtime_a.db"
    assert exact.is_file()
    assert runtime.is_file()
    assert exact != runtime


def test_report_explicitly_denies_live_access_and_retirement(tmp_path):
    result, work, *_ = _rehearse(tmp_path)
    report = json.loads(
        (work / "phase7_restore_rehearsal_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "pass"
    assert report["production_or_live_source_accessed"] is False
    assert report["semantic_provider_called"] is False
    assert report["llm_provider_called"] is False
    assert report["retirement_or_deletion_performed"] is False
    assert report["phase7_4_runtime_observation_started"] is False


def test_existing_work_root_is_never_overwritten(tmp_path):
    project, db, authority, recovery = _pair(tmp_path)
    work = tmp_path / "phase7-restore-existing"
    work.mkdir()
    marker = work / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(Phase73SafetyError):
        rehearse_recovery_pair(
            recovery_root=recovery,
            project_root=project,
            work_root=work,
            confirmation=CONFIRMATION_PHRASE,
            retrieval_probe=_retrieval_probe,
            workspace_probe=_workspace_probe,
            reverse_probe=_reverse_probe,
        )
    assert marker.read_text(encoding="utf-8") == "keep"


def test_work_root_inside_project_is_rejected(tmp_path):
    project, db, authority, recovery = _pair(tmp_path)
    with pytest.raises(Phase73SafetyError):
        rehearse_recovery_pair(
            recovery_root=recovery,
            project_root=project,
            work_root=project / "phase7-restore-bad",
            confirmation=CONFIRMATION_PHRASE,
            retrieval_probe=_retrieval_probe,
            workspace_probe=_workspace_probe,
            reverse_probe=_reverse_probe,
        )


def test_work_root_inside_recovery_pair_is_rejected(tmp_path):
    project, db, authority, recovery = _pair(tmp_path)
    with pytest.raises(Phase73SafetyError):
        rehearse_recovery_pair(
            recovery_root=recovery,
            project_root=project,
            work_root=recovery / "phase7-restore-bad",
            confirmation=CONFIRMATION_PHRASE,
            retrieval_probe=_retrieval_probe,
            workspace_probe=_workspace_probe,
            reverse_probe=_reverse_probe,
        )


def test_confirmation_is_required(tmp_path):
    project, db, authority, recovery = _pair(tmp_path)
    with pytest.raises(Phase73SafetyError):
        rehearse_recovery_pair(
            recovery_root=recovery,
            project_root=project,
            work_root=tmp_path / "phase7-restore-confirm",
            confirmation="yes",
            retrieval_probe=_retrieval_probe,
            workspace_probe=_workspace_probe,
            reverse_probe=_reverse_probe,
        )


def test_tampered_retained_bundle_blocks_before_rehearsal(tmp_path):
    project, db, authority, recovery = _pair(tmp_path)
    target = recovery / "backup-A" / "control" / "phase4_authority.json"
    target.write_text("tampered", encoding="utf-8")
    with pytest.raises(RecoveryVerificationError):
        rehearse_recovery_pair(
            recovery_root=recovery,
            project_root=project,
            work_root=tmp_path / "phase7-restore-tampered",
            confirmation=CONFIRMATION_PHRASE,
            retrieval_probe=_retrieval_probe,
            workspace_probe=_workspace_probe,
            reverse_probe=_reverse_probe,
        )

def test_reverse_semantic_identity_ignores_raw_relational_snapshot_instance_metadata():
    artifact = SimpleNamespace(
        source_path="data/courses.json",
        relative_path="legacy_json/courses.json",
        sha256="a" * 64,
        byte_count=123,
        record_count=4,
    )
    exported_a = SimpleNamespace(
        artifacts=(artifact,),
        status="pass_with_documented_differences",
        reconciliation=({"source_path": "data/courses.json", "status": "pass"},),
        documented_discrepancies=(),
        unmigrated_legacy_sources=("data/notes.json",),
        relational_snapshot_path=Path("restored-A/phase3_relational_snapshot.json"),
    )
    exported_b = SimpleNamespace(
        artifacts=(artifact,),
        status="pass_with_documented_differences",
        reconciliation=({"source_path": "data/courses.json", "status": "pass"},),
        documented_discrepancies=(),
        unmigrated_legacy_sources=("data/notes.json",),
        relational_snapshot_path=Path("restored-B/phase3_relational_snapshot.json"),
    )
    rehearsal = SimpleNamespace(source_fingerprint="logical-state")
    assert _reverse_semantic_sha(exported_a, rehearsal) == (
        _reverse_semantic_sha(exported_b, rehearsal)
    )


def test_reverse_semantic_identity_detects_exported_artifact_change():
    artifact_a = SimpleNamespace(
        source_path="data/courses.json",
        relative_path="legacy_json/courses.json",
        sha256="a" * 64,
        byte_count=123,
        record_count=4,
    )
    artifact_b = SimpleNamespace(
        source_path="data/courses.json",
        relative_path="legacy_json/courses.json",
        sha256="b" * 64,
        byte_count=123,
        record_count=4,
    )
    base = dict(
        status="pass",
        reconciliation=(),
        documented_discrepancies=(),
        unmigrated_legacy_sources=(),
    )
    rehearsal = SimpleNamespace(source_fingerprint="logical-state")
    assert _reverse_semantic_sha(
        SimpleNamespace(artifacts=(artifact_a,), **base),
        rehearsal,
    ) != _reverse_semantic_sha(
        SimpleNamespace(artifacts=(artifact_b,), **base),
        rehearsal,
    )
