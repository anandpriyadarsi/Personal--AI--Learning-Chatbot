"""Normal python phase7_web.py WAL publisher integration (disposable SQLite only)."""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import time

import pytest

from personal_learning_assistant.services.academic_wal_installation import (
    InstalledAcademicWalPublisher, InstalledWalPublisherError,
)
from personal_learning_assistant.ui.web.__main__ import prepare_local_app
from personal_learning_assistant.ui.web.routes import _academic_overview
from tests.test_planning_analysis_v2 import _database, inventory


def _wal_fixture(tmp_path):
    path = _database(tmp_path)
    source = sqlite3.connect(path)
    assert source.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    source.execute("PRAGMA wal_autocheckpoint=0")
    source.execute("UPDATE courses SET name='Committed installed state' WHERE code='MA103N'")
    source.commit()
    return path, source


def test_normal_launcher_connects_trusted_owner_and_real_flask_overview(tmp_path):
    path, writer = _wal_fixture(tmp_path)
    publication = None
    try:
        app, publication = prepare_local_app(assessment_enabled=False, database_path=path)
        assert publication is not None
        assert app.extensions['academic_wal_publisher'] is publication
        assert app.config['ASSESSMENT_EXTENDED_ENABLED'] is False
        assert callable(app.config['ACADEMIC_WAL_SNAPSHOT_PROVIDER'])
        state = publication.state()
        assert state.running and state.has_snapshot, state.error

        # Once owner publication has completed, the actual installed Flask
        # academic read must not use the live SQLite files.
        before = inventory(tmp_path)
        with app.test_request_context('/analysis?course=MA103N'):
            view = _academic_overview()
        assert view['available']
        assert view['source_snapshot']['mode'] == 'owner_published_wal'
        assert view['source_snapshot']['revision'] >= 1
        assert view['courses'][0]['name'] == 'Committed installed state'
        assert inventory(tmp_path) == before
    finally:
        if publication is not None:
            publication.stop()
        writer.close()


def test_launcher_missing_or_nonwal_database_never_initializes_it(tmp_path):
    absent = tmp_path / 'missing.sqlite'
    before = inventory(tmp_path)
    app, publisher = prepare_local_app(assessment_enabled=False, database_path=absent)
    assert publisher is None
    assert 'ACADEMIC_WAL_SNAPSHOT_PROVIDER' not in app.config
    assert inventory(tmp_path) == before
    assert not absent.exists()

    delete = tmp_path / 'delete.sqlite'
    with sqlite3.connect(delete) as connection:
        connection.execute('CREATE TABLE example(k INTEGER)')
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
    before = inventory(tmp_path)
    app, publisher = prepare_local_app(assessment_enabled=False, database_path=delete)
    assert publisher is None
    assert inventory(tmp_path) == before


def test_launcher_does_not_start_publisher_on_import_or_generic_app_factory(tmp_path, monkeypatch):
    import personal_learning_assistant.ui.web.__main__ as module
    from personal_learning_assistant.ui.web import create_app

    from personal_learning_assistant.services.academic_wal_installation import InstalledAcademicWalPublisher
    invoked = []
    original_start = InstalledAcademicWalPublisher.start

    def tracked_start(self, *args, **kwargs):
        invoked.append(1)
        return original_start(self, *args, **kwargs)

    monkeypatch.setattr(InstalledAcademicWalPublisher, 'start', tracked_start)
    app = create_app({'TESTING': True})
    assert 'academic_wal_publisher' not in app.extensions
    assert not invoked
    assert 'ACADEMIC_WAL_SNAPSHOT_PROVIDER' not in app.config


def test_local_owner_publisher_rejects_alias_without_source_side_effect(tmp_path):
    path, writer = _wal_fixture(tmp_path)
    alias = tmp_path / 'alias.db'
    try:
        try:
            alias.symlink_to(path)
        except OSError:
            from unittest.mock import patch
            with patch('pathlib.Path.is_symlink', autospec=True,
                       side_effect=lambda source: source == alias):
                assert not InstalledAcademicWalPublisher._eligible(alias)
            return
        assert not InstalledAcademicWalPublisher._eligible(alias)
        with pytest.raises(InstalledWalPublisherError):
            InstalledAcademicWalPublisher(alias).start()
    finally:
        writer.close()


def test_owner_publisher_does_not_misrepresent_uncommitted_work(tmp_path):
    path, writer = _wal_fixture(tmp_path)
    publication = InstalledAcademicWalPublisher(path, interval_seconds=10)
    try:
        assert publication.start().has_snapshot
        original = publication.feed.latest()
        writer.execute("UPDATE courses SET name='NOT COMMITTED' WHERE code='MA103N'")
        # Publication in another connection must contain only committed data.
        # The existing image remains immutable and as-of its original revision.
        assert publication.feed.latest() is original
        writer.rollback()
    finally:
        publication.stop()
        writer.close()


def test_writer_commit_refreshes_installed_snapshot_without_get_side_effects(tmp_path):
    path, writer = _wal_fixture(tmp_path)
    publisher = InstalledAcademicWalPublisher(path, interval_seconds=60)
    try:
        assert publisher.start().has_snapshot
        first = publisher.feed.latest()
        writer.execute("UPDATE courses SET name='Second committed value' WHERE code='MA103N'")
        writer.commit()
        publisher.request_refresh()  # Explicit owner-side post-commit signal.
        expires = time.monotonic() + 8
        while time.monotonic() < expires:
            newest = publisher.feed.latest()
            if newest is not None and newest.revision > first.revision:
                break
            time.sleep(.05)
        else:
            pytest.fail('Installed owner did not publish a new committed revision')
        from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
        before = inventory(tmp_path)
        view = AcademicOverviewService(
            path, wal_snapshot_provider=publisher.feed.latest,
            now=lambda: datetime.now(timezone.utc),
        ).overview(course='MA103N')
        assert view['source_snapshot']['revision'] > first.revision
        assert view['courses'][0]['name'] == 'Second committed value'
        assert inventory(tmp_path) == before
    finally:
        publisher.stop()
        assert publisher.feed.latest() is None
        writer.close()


def test_connected_normal_analysis_page_renders_fresh_snapshot_metadata(tmp_path):
    path, writer = _wal_fixture(tmp_path)
    publication = None
    try:
        app, publication = prepare_local_app(assessment_enabled=False, database_path=path)
        assert publication is not None and publication.feed.latest() is not None
        response = app.test_client().get('/analysis?course=MA103N')
        assert response.status_code == 200
        assert b'Committed academic snapshot' in response.data
        assert b'Committed installed state' in response.data or b'MA103N' in response.data
    finally:
        if publication is not None:
            publication.stop()
        writer.close()


def test_default_assessment_enabled_startup_preserves_academics_with_backup_first(tmp_path, monkeypatch):
    import config as installed_config

    path, writer = _wal_fixture(tmp_path)
    writer.close()  # Installation activation owns the database before server startup.
    monkeypatch.setattr(installed_config, 'BACKUP_PATH', tmp_path / 'backups')
    with sqlite3.connect(path) as connection:
        original_courses = connection.execute(
            'SELECT id,code,name FROM courses ORDER BY id'
        ).fetchall()
        assert connection.execute(
            'SELECT COUNT(*) FROM schema_migrations WHERE version=15'
        ).fetchone()[0] == 0

    publisher = None
    try:
        app, publisher = prepare_local_app(assessment_enabled=True, database_path=path)
        assert app.config['ASSESSMENT_EXTENDED_ENABLED'] is True
        assert publisher is not None
        assert publisher.state().has_snapshot
        with sqlite3.connect(path) as connection:
            assert connection.execute(
                'SELECT COUNT(*) FROM schema_migrations WHERE version=15'
            ).fetchone()[0] == 1
            assert connection.execute(
                'SELECT id,code,name FROM courses ORDER BY id'
            ).fetchall() == original_courses
            assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        backups = list((tmp_path / 'backups').glob('assessment-before-0015-*.sqlite3'))
        assert len(backups) == 1
        with app.test_request_context('/analysis?course=MA103N'):
            view = _academic_overview()
        assert view['available'] and view['source_snapshot']['mode'] == 'owner_published_wal'
    finally:
        if publisher is not None:
            publisher.stop()
