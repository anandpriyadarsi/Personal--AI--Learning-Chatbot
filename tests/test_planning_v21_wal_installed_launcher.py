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
