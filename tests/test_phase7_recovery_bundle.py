from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.phase7.recovery_bundle import (
    CONFIRMATION_PHRASE,
    RecoveryBundleError,
    RecoveryOutputError,
    RecoveryVerificationError,
    create_two_verified_backups,
    preview_recovery,
    verify_recovery_pair,
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


def _env(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "data").mkdir()
    (project / "personal_learning_assistant" / "repositories" / "sqlite" / "migrations").mkdir(
        parents=True
    )
    # Inventory scanner needs at least one normal source file but the recovery
    # implementation itself does not require the repository's migration SQL
    # files to exist in synthetic tests.
    (project / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

    db = project / "data" / "learning_assistant.db"
    applied = apply_migrations(db)
    assert applied[:4] == (1, 2, 3, 4)

    c = sqlite3.connect(str(db), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
        "confidence,raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t1','c1','LU','lu',1,'learning',2,NULL,?,?,NULL)",
        (NOW, NOW),
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "LU.md"
    note.write_text("# LU\nA = LU\n", encoding="utf-8")
    import hashlib

    note_hash = hashlib.sha256(note.read_bytes()).hexdigest()
    c.execute(
        "INSERT INTO vaults(id,name,root_path,path_key,enabled,last_scanned_at,created_at,updated_at) "
        "VALUES ('v1','Vault',?,'vault',1,NULL,?,?)",
        (str(vault), NOW, NOW),
    )
    c.execute(
        "INSERT INTO note_metadata(id,vault_id,relative_path,path_key,title,note_type,"
        "confidence,revision_status,pinned_at,archived_at,trashed_at,source_hash,"
        "file_mtime_ns,frontmatter_extra_json,created_at,updated_at) "
        "VALUES ('n1','v1','LU.md','lu.md','LU','note',4,'reviewed',NULL,NULL,NULL,"
        "?,1,'{}',?,?)",
        (note_hash, NOW, NOW),
    )

    source_root = tmp_path / "sources"
    source_root.mkdir()
    source = source_root / "handout.txt"
    source.write_text("LU handout", encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    c.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,"
        "content_hash,size_bytes,source_timestamp,extraction_status,extraction_version,"
        "extraction_error,created_at,updated_at) "
        "VALUES ('d1','text',NULL,'docs/handout.txt','text/plain',?,?,NULL,"
        "'completed','v1',NULL,?,?)",
        (source_hash, source.stat().st_size, NOW, NOW),
    )
    c.close()

    authority = project / ".phase4_authority.json"
    _authority(authority)
    (project / "data" / "courses.json").write_text(
        '{"version":1}\n', encoding="utf-8"
    )
    return project, db, authority, vault, source_root


def _create(tmp_path, **kwargs):
    project, db, authority, vault, source_root = _env(tmp_path)
    output = tmp_path / "phase7-recovery-test"
    result = create_two_verified_backups(
        project_root=project,
        database_path=db,
        authority_path=authority,
        output_root=output,
        source_roots={"docs": source_root},
        git_identity={"commit": "abc", "branch": "phase7/deprecation-observation"},
        confirmation=CONFIRMATION_PHRASE,
        **kwargs,
    )
    return result, output, project, db, authority, vault, source_root


def test_preview_is_read_only_and_reports_external_roots(tmp_path):
    project, db, authority, vault, source_root = _env(tmp_path)
    before = db.read_bytes()
    result = preview_recovery(
        project_root=project,
        database_path=db,
        authority_path=authority,
        source_roots={},
        git_identity={"commit": "abc", "branch": "phase7/deprecation-observation"},
    )
    assert result["writes_performed"] is False
    assert result["restore_performed"] is False
    assert result["required_source_root_keys"] == ["docs"]
    assert result["provided_source_root_keys"] == []
    assert result["external_or_unavailable_source_count"] == 1
    assert db.read_bytes() == before


def test_two_backups_are_created_independently_and_verify(tmp_path):
    result, output, *_ = _create(tmp_path)
    assert result["backup_a_verified"] is True
    assert result["backup_b_verified"] is True
    assert (output / "backup-A" / "recovery_manifest.json").is_file()
    assert (output / "backup-B" / "recovery_manifest.json").is_file()
    pair = verify_recovery_pair(output)
    assert pair["backup_a_verified"] is True
    assert pair["backup_b_verified"] is True
    assert pair["restore_performed"] is False


def test_sqlite_backups_have_same_logical_identity(tmp_path):
    result, output, *_ = _create(tmp_path)
    pair = verify_recovery_pair(output)
    assert pair["sqlite_logical_sha256"] == result["sqlite_logical_sha256"]
    for label in ("backup-A", "backup-B"):
        c = sqlite3.connect(str(output / label / "sqlite" / "learning_assistant.db"))
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


def test_registered_vault_note_and_explicit_source_bytes_are_copied(tmp_path):
    result, output, *_ = _create(tmp_path)
    for label in ("backup-A", "backup-B"):
        assert (output / label / "vaults" / "vault" / "LU.md").is_file()
        assert (
            output
            / label
            / "sources"
            / "docs"
            / "handout.txt"
        ).is_file()


def test_unprovided_source_root_is_preserved_as_manifest_reference(tmp_path):
    project, db, authority, vault, source_root = _env(tmp_path)
    output = tmp_path / "phase7-recovery-external"
    create_two_verified_backups(
        project_root=project,
        database_path=db,
        authority_path=authority,
        output_root=output,
        source_roots={},
        git_identity={"commit": "abc", "branch": "phase7/deprecation-observation"},
        confirmation=CONFIRMATION_PHRASE,
    )
    manifest = json.loads(
        (
            output
            / "backup-A"
            / "manifests"
            / "sources.json"
        ).read_text(encoding="utf-8")
    )
    row = manifest["documents"][0]
    assert row["status"] == "root_not_provided"
    assert row["backup_path"] is None
    assert row["registered_content_hash"]


def test_secret_sensitive_registered_generic_source_is_never_copied(tmp_path):
    project, db, authority, vault, source_root = _env(tmp_path)
    secret = source_root / ".env"
    secret.write_text("TOKEN=secret", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(secret.read_bytes()).hexdigest()
    c = sqlite3.connect(str(db))
    c.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,"
        "content_hash,size_bytes,source_timestamp,extraction_status,extraction_version,"
        "extraction_error,created_at,updated_at) "
        "VALUES ('d2','text',NULL,'docs/.env','text/plain',?,?,NULL,"
        "'completed','v1',NULL,?,?)",
        (digest, secret.stat().st_size, NOW, NOW),
    )
    c.commit()
    c.close()

    output = tmp_path / "phase7-recovery-secret"
    create_two_verified_backups(
        project_root=project,
        database_path=db,
        authority_path=authority,
        output_root=output,
        source_roots={"docs": source_root},
        git_identity={"commit": "abc", "branch": "phase7/deprecation-observation"},
        confirmation=CONFIRMATION_PHRASE,
    )
    sources = json.loads(
        (
            output
            / "backup-A"
            / "manifests"
            / "sources.json"
        ).read_text(encoding="utf-8")
    )
    secret_row = next(row for row in sources["documents"] if row["document_id"] == "d2")
    assert secret_row["status"] == "secret_sensitive_excluded"
    assert secret_row["backup_path"] is None
    assert not (output / "backup-A" / "sources" / "docs" / ".env").exists()


def test_retrieval_indexes_and_virtualenv_are_not_payload(tmp_path):
    result, output, project, *_ = _create(tmp_path)
    (project / ".phase5_retrieval").mkdir()
    (project / ".phase5_retrieval" / "index.bin").write_bytes(b"derived")
    (project / ".venv").mkdir()
    (project / ".venv" / "secret.txt").write_text("x", encoding="utf-8")
    for label in ("backup-A", "backup-B"):
        paths = [
            path.relative_to(output / label).as_posix()
            for path in (output / label).rglob("*")
            if path.is_file()
        ]
        assert not any(".phase5_retrieval" in path for path in paths)
        assert not any(".venv" in path for path in paths)


def test_existing_output_is_never_overwritten(tmp_path):
    project, db, authority, vault, source_root = _env(tmp_path)
    output = tmp_path / "phase7-recovery-existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(RecoveryOutputError):
        create_two_verified_backups(
            project_root=project,
            database_path=db,
            authority_path=authority,
            output_root=output,
            source_roots={"docs": source_root},
            git_identity={},
            confirmation=CONFIRMATION_PHRASE,
        )
    assert marker.read_text(encoding="utf-8") == "keep"


def test_output_inside_project_is_rejected(tmp_path):
    project, db, authority, vault, source_root = _env(tmp_path)
    with pytest.raises(RecoveryOutputError):
        create_two_verified_backups(
            project_root=project,
            database_path=db,
            authority_path=authority,
            output_root=project / "phase7-recovery-bad",
            source_roots={"docs": source_root},
            git_identity={},
            confirmation=CONFIRMATION_PHRASE,
        )


def test_tampered_payload_fails_pair_verification(tmp_path):
    result, output, *_ = _create(tmp_path)
    path = output / "backup-A" / "control" / "phase4_authority.json"
    path.write_text("tampered", encoding="utf-8")
    with pytest.raises(RecoveryVerificationError):
        verify_recovery_pair(output)


def test_confirmation_is_required(tmp_path):
    project, db, authority, vault, source_root = _env(tmp_path)
    with pytest.raises(RecoveryBundleError):
        create_two_verified_backups(
            project_root=project,
            database_path=db,
            authority_path=authority,
            output_root=tmp_path / "phase7-recovery-confirm",
            source_roots={"docs": source_root},
            git_identity={},
            confirmation="yes",
        )
