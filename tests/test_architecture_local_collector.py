import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest


ROOT = Path(__file__).resolve().parents[1]


def collector():
    path = ROOT / 'scripts/architecture_local_collector.py'
    assert path.exists(), 'Redacted collector is not implemented'
    spec = importlib.util.spec_from_file_location('collector', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_collector_missing_database_is_blocked_without_creation(tmp_path):
    before = list(tmp_path.iterdir())
    result = collector().closed_schema_report(tmp_path / 'missing.db', ROOT, closed=False)
    assert result['status'] == 'BLOCKED'
    assert list(tmp_path.iterdir()) == before


def test_schema_collector_uses_only_stable_copy_and_redacts_records(tmp_path):
    from synthetic_academic import build_academic_database
    path = build_academic_database(tmp_path)
    before = path.read_bytes()
    result = collector().closed_schema_report(path, ROOT, closed=True)
    assert result['status'] == 'PASS'
    assert result['ledger_matches_source'] and result['foreign_key_violations'] == 0
    assert path.read_bytes() == before
    raw = json.dumps(result)
    assert str(tmp_path) not in raw
    assert 'synthetic-ma' not in raw and 'Synthetic Linear Algebra' not in raw
    assert 'schema_migrations' in result['tables_present']


def test_collector_does_not_follow_symlink_database(tmp_path):
    target = tmp_path / 'target.db'
    target.write_bytes(b'not SQL')
    link = tmp_path / 'linked.db'
    try:
        link.symlink_to(target)
    except OSError:
        return
    assert collector().closed_schema_report(link, ROOT, closed=True)['status'] == 'BLOCKED'
    assert target.read_bytes() == b'not SQL'


def test_collector_rejects_writer_during_copy_inspection(tmp_path, monkeypatch):
    from synthetic_academic import build_academic_database
    path = build_academic_database(tmp_path)
    module = collector()
    connect = module.sqlite3.connect

    def changing_source(*args, **kwargs):
        connection = connect(*args, **kwargs)
        # A writer starts after the initial copy check. Inspecting the copied
        # database successfully must not certify the now-changing source.
        path.write_bytes(path.read_bytes() + b'changed-by-writer')
        return connection

    monkeypatch.setattr(module.sqlite3, 'connect', changing_source)
    result = module.closed_schema_report(path, ROOT, closed=True)
    assert result['status'] == 'BLOCKED'
    assert 'changed' in result['reason']
