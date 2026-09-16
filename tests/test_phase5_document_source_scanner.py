from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.domain.source_scanner_models import (
    SourceScanIssue,
    SourceScanResult,
)
from personal_learning_assistant.repositories.filesystem.source_scanner import (
    FileSystemSourceScanner,
    SourceRootError,
)
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    SQLiteKnowledgeRegistryRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.knowledge_registry_service import (
    KnowledgeRegistryService,
)
from personal_learning_assistant.services.source_scanner_service import (
    DocumentSourceScannerService,
    SourceScanBlockedError,
)

NOW = "2026-09-16T00:00:00Z"


def _repo(tmp_path: Path):
    db = tmp_path / "registry.db"
    apply_migrations(db)
    connection = sqlite3.connect(
        str(db),
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        "PRAGMA foreign_keys=ON"
    )
    repository = (
        SQLiteKnowledgeRegistryRepository(
            connection
        )
    )
    registry = KnowledgeRegistryService(
        repository,
        now=lambda: NOW,
    )
    return db, connection, repository, registry


def _write(path: Path, data: bytes):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_bytes(data)


def test_scan_is_deterministic_and_portable(tmp_path):
    root = tmp_path / "sources"
    _write(root / "B" / "two.PDF", b"pdf")
    _write(root / "a.md", b"note")

    first = FileSystemSourceScanner(
        "project-docs",
        root,
    ).scan()
    second = FileSystemSourceScanner(
        "project-docs",
        root,
    ).scan()

    assert first.manifest_hash == second.manifest_hash
    assert [
        item.path_key
        for item in first.sources
    ] == [
        "project-docs/B/two.PDF",
        "project-docs/a.md",
    ]
    assert all(
        str(tmp_path) not in item.path_key
        for item in first.sources
    )


def test_raw_bytes_are_hashed_without_rewrite(tmp_path):
    root = tmp_path / "sources"
    source = root / "raw.txt"
    raw = b"line1\r\nline2\x00\xff"
    _write(source, raw)

    before = source.read_bytes()
    result = FileSystemSourceScanner(
        "docs",
        root,
    ).scan()

    assert (
        result.sources[0].content_hash
        == hashlib.sha256(raw).hexdigest()
    )
    assert source.read_bytes() == before


def test_unsupported_files_are_counted(tmp_path):
    root = tmp_path / "sources"
    _write(root / "a.xyz", b"x")
    _write(root / "b.pdf", b"y")

    result = FileSystemSourceScanner(
        "docs",
        root,
    ).scan()

    assert result.scanned_count == 1
    assert result.ignored_unsupported == 1


def test_symlink_root_is_rejected_if_supported(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"

    try:
        link.symlink_to(
            target,
            target_is_directory=True,
        )
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    with pytest.raises(
        SourceRootError,
        match="symlink",
    ):
        FileSystemSourceScanner(
            "docs",
            link,
        ).scan()


def test_preview_is_read_only(tmp_path):
    root = tmp_path / "sources"
    _write(root / "a.pdf", b"a")

    db, connection, repository, registry = (
        _repo(tmp_path)
    )
    service = DocumentSourceScannerService(
        repository,
        registry,
    )
    scan = FileSystemSourceScanner(
        "docs",
        root,
    ).scan()

    before_changes = connection.total_changes
    before_bytes = db.read_bytes()

    plan = service.preview(scan)

    assert plan.create_count == 1
    assert connection.total_changes == before_changes

    connection.close()
    assert db.read_bytes() == before_bytes


def test_apply_then_rescan_is_idempotent(tmp_path):
    root = tmp_path / "sources"
    _write(root / "a.pdf", b"a")

    _db, connection, repository, registry = (
        _repo(tmp_path)
    )
    service = DocumentSourceScannerService(
        repository,
        registry,
    )

    first = service.apply(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )
    changes_after_first = connection.total_changes

    second = service.apply(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )

    assert first.created == 1
    assert second.matched == 1
    assert connection.total_changes == changes_after_first
    assert len(repository.list_documents()) == 1
    assert len(
        repository.list_pending_outbox()
    ) == 1

    connection.close()


def test_content_change_preserves_document_id(tmp_path):
    root = tmp_path / "sources"
    source = root / "a.pdf"
    _write(source, b"a")

    _db, connection, repository, registry = (
        _repo(tmp_path)
    )
    service = DocumentSourceScannerService(
        repository,
        registry,
    )

    first = service.apply(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )
    first_id = first.items[0].document_id

    source.write_bytes(b"changed")

    second = service.apply(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )

    assert second.updated == 1
    assert (
        second.items[0].document_id
        == first_id
    )
    assert len(
        repository.list_pending_outbox()
    ) == 2

    connection.close()


def test_duplicate_content_is_flagged_not_merged(tmp_path):
    root = tmp_path / "sources"
    _write(root / "a.pdf", b"same")
    _write(root / "copy.pdf", b"same")

    _db, connection, repository, registry = (
        _repo(tmp_path)
    )
    service = DocumentSourceScannerService(
        repository,
        registry,
    )

    result = service.apply(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )

    assert result.created == 2
    assert len(result.duplicate_groups) == 1
    assert len(result.duplicate_groups[0]) == 2
    assert len(repository.list_documents()) == 2

    connection.close()


def test_removed_source_is_flagged_not_deleted(tmp_path):
    root = tmp_path / "sources"
    source = root / "a.pdf"
    _write(source, b"a")

    _db, connection, repository, registry = (
        _repo(tmp_path)
    )
    service = DocumentSourceScannerService(
        repository,
        registry,
    )

    first = service.apply(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )
    source.unlink()

    plan = service.preview(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )

    assert (
        plan.missing_registry_ids
        == (first.items[0].document_id,)
    )
    assert (
        repository.get_document(
            first.items[0].document_id
        )
        is not None
    )

    connection.close()


def test_scan_issues_block_apply_before_write(tmp_path):
    root = tmp_path / "sources"
    _write(root / "a.pdf", b"a")

    _db, connection, repository, registry = (
        _repo(tmp_path)
    )
    service = DocumentSourceScannerService(
        repository,
        registry,
    )
    clean = FileSystemSourceScanner(
        "docs",
        root,
    ).scan()

    blocked = SourceScanResult(
        root=clean.root,
        sources=clean.sources,
        issues=(
            SourceScanIssue(
                "unreadable_file",
                "docs/x.pdf",
                "PermissionError",
            ),
        ),
        ignored_unsupported=(
            clean.ignored_unsupported
        ),
        ignored_symlinks=(
            clean.ignored_symlinks
        ),
        manifest_hash=clean.manifest_hash,
    )

    before = connection.total_changes

    with pytest.raises(
        SourceScanBlockedError
    ):
        service.apply(blocked)

    assert connection.total_changes == before
    assert repository.list_documents() == ()

    connection.close()


def test_preview_detects_duplicate_before_apply(tmp_path):
    root = tmp_path / "sources"
    _write(root / "a.pdf", b"same")
    _write(root / "b.pdf", b"same")

    _db, connection, repository, registry = (
        _repo(tmp_path)
    )
    service = DocumentSourceScannerService(
        repository,
        registry,
    )

    plan = service.preview(
        FileSystemSourceScanner(
            "docs",
            root,
        ).scan()
    )

    assert plan.duplicate_group_count == 1
    assert plan.create_count == 2
    assert repository.list_documents() == ()

    connection.close()


def test_root_key_validation(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()

    with pytest.raises(
        ValueError,
        match="root_key",
    ):
        FileSystemSourceScanner(
            "Bad Root/Key",
            root,
        )
