"""WAL academic overview must be physically read-only and source-authenticated."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import sqlite3

import pytest

from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
from personal_learning_assistant.services.academic_wal_snapshot import (
    AcademicSnapshotFeed, AcademicSnapshotUnavailable,
)
from tests.test_planning_analysis_v2 import NOW, _database, inventory


def _wal(tmp_path):
    path = _database(tmp_path)
    writer = sqlite3.connect(path)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("UPDATE courses SET name='Latest committed source' WHERE code='MA103N'")
    writer.commit()
    return path, writer


def _overview(path, provider=None, *, at=NOW, maximum=120):
    return AcademicOverviewService(
        path, now=lambda: at, wal_snapshot_provider=provider,
        max_snapshot_age_seconds=maximum,
    ).overview(course='MA103N')


def test_live_wal_requires_trusted_feed_but_never_modifies_source(tmp_path):
    path, writer = _wal(tmp_path)
    try:
        before = inventory(tmp_path)
        blocked = _overview(path)
        assert not blocked['available']
        assert blocked['source_snapshot'] is None
        assert blocked['source_status']['academic_snapshot'] == 'unavailable'
        assert inventory(tmp_path) == before
    finally:
        writer.close()


def test_owner_publication_includes_uncheckpointed_commit_and_read_is_physically_invariant(tmp_path, monkeypatch):
    path, writer = _wal(tmp_path)
    try:
        feed = AcademicSnapshotFeed(path)
        assert feed.publish(writer, at=NOW) == 1
        before = inventory(tmp_path)
        # The Analysis request may open :memory: only, never path/-wal/-shm.
        original_connect = sqlite3.connect
        opened = []

        def monitored_connect(database, *args, **kwargs):
            opened.append(str(database))
            assert database == ':memory:', 'Analysis opened a source SQLite connection'
            return original_connect(database, *args, **kwargs)

        monkeypatch.setattr('personal_learning_assistant.services.academic_overview_service.sqlite3.connect', monitored_connect)
        view = _overview(path, feed.latest)
        assert view['available']
        assert view['source_snapshot']['mode'] == 'owner_published_wal'
        assert view['source_snapshot']['revision'] == 1
        assert view['courses'] and view['courses'][0]['name'] == 'Latest committed source'
        assert opened == [':memory:']
        assert inventory(tmp_path) == before
    finally:
        writer.close()


def test_feed_is_revisioned_and_fails_closed_when_owner_cannot_publish(tmp_path):
    path, writer = _wal(tmp_path)
    try:
        feed = AcademicSnapshotFeed(path)
        feed.publish(writer, at=NOW)
        writer.execute("UPDATE courses SET name='New committed version' WHERE code='MA103N'")
        writer.commit()
        # A previously published snapshot is honest about its revision, not an
        # implicit read of the latest live WAL content.
        before = inventory(tmp_path)
        old = _overview(path, feed.latest)
        assert old['courses'][0]['name'] == 'Latest committed source'
        assert inventory(tmp_path) == before
        assert feed.publish(writer, at=NOW + timedelta(seconds=10)) == 2
        newest = _overview(path, feed.latest, at=NOW + timedelta(seconds=10))
        assert newest['courses'][0]['name'] == 'New committed version'
        assert newest['source_snapshot']['revision'] == 2

        writer.execute("UPDATE courses SET name='UNCOMMITTED' WHERE code='MA103N'")
        with pytest.raises(AcademicSnapshotUnavailable):
            feed.publish(writer, at=NOW + timedelta(seconds=11))
        assert feed.latest() is None
        assert not _overview(path, feed.latest, at=NOW + timedelta(seconds=11))['available']
        writer.rollback()
    finally:
        writer.close()


def test_stale_future_wrong_identity_and_invalid_images_never_reach_analysis(tmp_path):
    path, writer = _wal(tmp_path)
    try:
        feed = AcademicSnapshotFeed(path)
        feed.publish(writer, at=NOW)
        genuine = feed.latest()
        initial = inventory(tmp_path)
        variants = [
            (replace(genuine, published_at=NOW - timedelta(hours=1)), NOW),
            (replace(genuine, published_at=NOW + timedelta(hours=1)), NOW),
            (replace(genuine, database_identity='not-the-owner'), NOW),
            (replace(genuine, payload=b'not-an-sqlite-snapshot'), NOW),
            (replace(genuine, revision=0), NOW),
        ]
        for forged, at in variants:
            view = _overview(path, lambda forged=forged: forged, at=at)
            assert not view['available'] and view['courses'] == []
            assert view['source_status']['academic_snapshot'] == 'unavailable'
            assert inventory(tmp_path) == initial
        assert not _overview(path, lambda: None)['available']
        assert inventory(tmp_path) == initial
    finally:
        writer.close()


def test_publisher_rejects_unrelated_db_and_does_not_replace_bad_state(tmp_path):
    path, owner = _wal(tmp_path)
    other = tmp_path / 'other.sqlite'
    foreign = sqlite3.connect(other)
    try:
        foreign.execute('PRAGMA journal_mode=WAL')
        foreign.execute('CREATE TABLE foreign_study(x)')
        foreign.commit()
        feed = AcademicSnapshotFeed(path)
        with pytest.raises(AcademicSnapshotUnavailable):
            feed.publish(foreign, at=NOW)
        assert feed.latest() is None
        assert feed.publish(owner, at=NOW) == 1
        with pytest.raises(AcademicSnapshotUnavailable):
            feed.publish(owner, at=NOW.replace(tzinfo=None))
        assert feed.latest() is None
        assert not _overview(path, feed.latest)['available']
    finally:
        foreign.close()
        owner.close()


def test_snapshot_feed_rejects_symlink_owner_identity(tmp_path):
    path, owner = _wal(tmp_path)
    link = tmp_path / 'alias.db'
    try:
        try:
            link.symlink_to(path)
        except OSError:
            # Windows CI may forbid real symlinks. Exercise the production
            # guard via a mocked symlink predicate instead of skipping.
            from unittest.mock import patch
            with patch('pathlib.Path.is_symlink', autospec=True,
                       side_effect=lambda subject: subject == link):
                with pytest.raises(AcademicSnapshotUnavailable):
                    AcademicSnapshotFeed(link).publish(owner, at=NOW)
            return
        feed = AcademicSnapshotFeed(link)
        with pytest.raises(AcademicSnapshotUnavailable):
            feed.publish(owner, at=NOW)
        assert feed.latest() is None
    finally:
        owner.close()


def test_flask_installed_overview_receives_provider_not_writer_connection(tmp_path, monkeypatch):
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.ui.web.routes import _academic_overview
    import config as installed_config

    path, writer = _wal(tmp_path)
    try:
        feed = AcademicSnapshotFeed(path)
        feed.publish(writer, at=NOW)
        monkeypatch.setattr(installed_config, 'DATABASE_PATH', str(path))
        app = create_app({
            'ACADEMIC_WAL_SNAPSHOT_PROVIDER': feed.latest,
            'ACADEMIC_WAL_SNAPSHOT_MAX_AGE': 120,
        })
        # Flask's default factory uses real wall time, so publish a fresh
        # owner snapshot just before the request.
        feed.publish(writer)
        before = inventory(tmp_path)
        with app.test_request_context('/analysis?course=MA103N'):
            view = _academic_overview()
        assert view['source_snapshot']['mode'] == 'owner_published_wal'
        assert view['courses'][0]['name'] == 'Latest committed source'
        assert inventory(tmp_path) == before
    finally:
        writer.close()
