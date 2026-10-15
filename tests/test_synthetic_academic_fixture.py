from pathlib import Path
import sqlite3

import pytest


def test_synthetic_fixture_is_scoped_and_contains_grounding_and_reopen_session(tmp_path):
    from synthetic_academic import build_academic_database

    path = build_academic_database(tmp_path)
    assert path == tmp_path / 'learning_assistant.db'
    assert not (Path(__file__).resolve().parents[1] / 'data/learning_assistant.db').exists()
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT id FROM courses').fetchall() == [('synthetic-ma',)]
        assert db.execute('SELECT id FROM knowledge_chunks').fetchall() == [('synthetic-chunk',)]
        assert db.execute('SELECT id FROM tutor_sessions').fetchall() == [('synthetic-tutor-session',)]


def test_synthetic_fixture_refuses_existing_database_without_changing_bytes(tmp_path):
    from synthetic_academic import build_academic_database

    path = tmp_path / 'learning_assistant.db'
    path.write_bytes(b'preserve this')
    with pytest.raises(FileExistsError):
        build_academic_database(tmp_path)
    assert path.read_bytes() == b'preserve this'
