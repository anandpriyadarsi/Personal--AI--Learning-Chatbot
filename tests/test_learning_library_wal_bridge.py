"""Library V2 safety regressions: real SQLite WAL + authorized RAM snapshot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from test_learning_library_read_model import library_db
from personal_learning_assistant.domain.learning_library_models import LibraryQuery
from personal_learning_assistant.services.academic_wal_snapshot import (
    AcademicSnapshotFeed, AuthorizedAcademicSnapshot)
from personal_learning_assistant.services.learning_library_service import (
    LearningLibraryService, LibraryUnavailableError)


def test_live_wal_without_owner_feed_fails_closed_without_get_sidecar_writes(library_db):
    with sqlite3.connect(library_db) as owner:
        assert owner.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        owner.execute("UPDATE resources SET title='New committed library source' WHERE id='r1'")
        owner.commit()
        sidecars = [library_db.with_name(library_db.name + suffix) for suffix in ("-wal", "-shm")]
        before = [p.read_bytes() if p.exists() else None for p in sidecars]
        with pytest.raises(LibraryUnavailableError):
            LearningLibraryService(database_path=library_db).list_items(LibraryQuery())
        after = [p.read_bytes() if p.exists() else None for p in sidecars]
        assert before == after


def test_authorized_wal_memory_snapshot_reads_committed_content_without_opening_source(library_db, monkeypatch):
    with sqlite3.connect(library_db) as owner:
        owner.execute("PRAGMA journal_mode=WAL")
        owner.execute("UPDATE resources SET title='Snapshot visible after commit' WHERE id='r1'")
        owner.commit()
        feed = AcademicSnapshotFeed(library_db)
        feed.publish(owner)
        import personal_learning_assistant.repositories.sqlite.learning_library_repository as library_repository
        real_connect = library_repository.sqlite3.connect
        def guard_connect(path, *args, **kwargs):
            if str(path).startswith("file:"):
                raise AssertionError("Library GET attempted to open live SQLite")
            return real_connect(path, *args, **kwargs)
        monkeypatch.setattr(library_repository.sqlite3, "connect", guard_connect)
        page = LearningLibraryService(
            database_path=library_db, wal_snapshot_provider=feed.latest
        ).list_items(LibraryQuery())
        assert any(i.title == "Snapshot visible after commit" for i in page.items)
        detail = LearningLibraryService(
            database_path=library_db, wal_snapshot_provider=feed.latest
        ).resource_detail("r1")
        assert detail.title == "Snapshot visible after commit"


def test_untrusted_or_stale_wal_snapshot_is_not_accepted(library_db):
    with sqlite3.connect(library_db) as owner:
        owner.execute("PRAGMA journal_mode=WAL")
        owner.commit()
        feed = AcademicSnapshotFeed(library_db)
        feed.publish(owner)
        snapshot = feed.latest()
        assert snapshot is not None
        candidates = [
            lambda: None,
            lambda: AuthorizedAcademicSnapshot(
                database_identity=snapshot.database_identity + "-other",
                payload=snapshot.payload, published_at=snapshot.published_at,
                revision=snapshot.revision),
            lambda: AuthorizedAcademicSnapshot(
                database_identity=snapshot.database_identity,
                payload=snapshot.payload,
                published_at=datetime.now(timezone.utc) - timedelta(hours=2),
                revision=snapshot.revision),
        ]
        for provider in candidates:
            with pytest.raises(LibraryUnavailableError):
                LearningLibraryService(
                    database_path=library_db, wal_snapshot_provider=provider
                ).list_items(LibraryQuery())
