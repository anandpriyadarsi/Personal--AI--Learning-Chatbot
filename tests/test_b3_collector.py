"""Private synthetic closed-copy collector tests, compatible with Windows CI."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from tests.test_architecture_local_collector import collector, ROOT
from tests.test_topic_evidence_repository import _database, update


def test_default_never_inspects_database_or_sidecars(tmp_path, monkeypatch):
    m = collector()
    monkeypatch.setattr(m, '_inventory', lambda _: pytest.fail('default accessed database'))
    monkeypatch.setattr(m.sqlite3, 'connect', lambda *a,**kw: pytest.fail('default opened database'))
    result = m.closed_schema_report(tmp_path / 'absent.db', ROOT, closed=False)
    assert result['status'] == 'BLOCKED' and result['reason_code'] == 'writers_not_attested'
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('payload', ['{', '[]', '{"storage_backend":"sqlite"}',
    '{"storage_backend":"legacy","legacy_writes_blocked":"false"}',
    '{"version":true,"storage_backend":"legacy"}'])
def test_malformed_control_is_invalid_and_redacted(tmp_path, payload):
    m = collector()
    (tmp_path / '.phase4_authority.json').write_text(payload, encoding='utf-8')
    assert hasattr(m, 'backend_report'), 'Strict redacted backend inspection missing'
    result = m.backend_report(tmp_path)
    assert result == {'backend':'unknown','status':'INVALID','reason_code':'control_invalid'}
    assert str(tmp_path) not in json.dumps(result)


def test_absent_control_is_legacy_but_unverified_without_creation(tmp_path):
    m = collector()
    assert hasattr(m, 'backend_report'), 'Strict backend inspection missing'
    assert m.backend_report(tmp_path) == {'backend':'legacy','status':'UNVERIFIABLE','reason_code':'control_absent_legacy_default'}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('suffix', ['-wal','-shm','-journal'])
def test_sidecar_links_are_blocked_even_when_dangling(tmp_path, suffix):
    path = _database(tmp_path)
    target = tmp_path / 'missing-target'
    link = Path(str(path) + suffix)
    link.symlink_to(target)
    result = collector().closed_schema_report(path, ROOT, closed=True)
    assert result['status'] == 'BLOCKED'
    assert result['reason_code'] == 'unsafe_database_inventory'
    assert not target.exists() and link.is_symlink()


def test_parent_alias_is_blocked(tmp_path):
    folder = tmp_path / 'real'
    folder.mkdir()
    path = _database(folder)
    link = tmp_path / 'alias'
    link.symlink_to(folder, target_is_directory=True)
    result = collector().closed_schema_report(link / path.name, ROOT, closed=True)
    assert result['status'] == 'BLOCKED'


def test_unrecovered_rollback_journal_is_blocked_without_checkpoint(tmp_path):
    path = _database(tmp_path)
    journal = Path(str(path) + '-journal')
    journal.write_bytes(b'private stale/hot journal')
    before = path.read_bytes()
    result = collector().closed_schema_report(path, ROOT, closed=True)
    assert result['status'] == 'BLOCKED' and result['reason_code'] == 'unsafe_database_inventory'
    assert path.read_bytes() == before and journal.read_bytes() == b'private stale/hot journal'


def test_corrupt_database_returns_fixed_reason_without_local_paths(tmp_path):
    path = tmp_path / 'private-name.db'
    path.write_bytes(b'private academic content')
    result = collector().closed_schema_report(path, ROOT, closed=True)
    assert result['status'] == 'INVALID' and result['reason_code'] == 'copied_schema_invalid'
    assert str(tmp_path) not in json.dumps(result) and 'private' not in json.dumps(result)


def test_permissions_failure_is_blocked_and_does_not_leak_exception(tmp_path, monkeypatch):
    path = _database(tmp_path)
    m = collector()
    monkeypatch.setattr(m, '_inventory', lambda _: (_ for _ in ()).throw(PermissionError('secret/path/learner-answer')))
    result = m.closed_schema_report(path, ROOT, closed=True)
    assert result['status'] == 'BLOCKED' and result['reason_code'] == 'copy_access_failed'
    assert 'secret' not in json.dumps(result)


def test_copied_bytes_must_match_source_before_sqlite_is_opened(tmp_path, monkeypatch):
    path = _database(tmp_path)
    m = collector()
    copy = m.shutil.copy2
    def corrupt_copy(src, dest):
        result = copy(src,dest)
        Path(dest).write_bytes(Path(dest).read_bytes() + b'damage')
        return result
    monkeypatch.setattr(m.shutil, 'copy2', corrupt_copy)
    monkeypatch.setattr(m.sqlite3, 'connect', lambda *a,**kw: pytest.fail('opened damaged copy'))
    result = m.closed_schema_report(path, ROOT, closed=True)
    assert result['status'] == 'BLOCKED' and result['reason_code'] == 'copied_bytes_mismatch'


def test_missing_tables_is_invalid_without_migration_or_repair(tmp_path):
    path = tmp_path / 'empty.db'
    with closing(sqlite3.connect(path)) as c:
        c.execute('CREATE TABLE unrelated(secret TEXT)')
    before = path.read_bytes()
    result = collector().closed_schema_report(path, ROOT, closed=True)
    assert result['status'] in ('FAIL','INVALID') and path.read_bytes() == before


def test_manifest_redacts_unexpected_schema_and_ledger_names(tmp_path):
    path = _database(tmp_path)
    update(path, 'CREATE TABLE private_answer_path(secret TEXT)')
    update(path, "UPDATE schema_migrations SET name='learner-response-secret' WHERE version=14")
    result = collector().closed_schema_report(path, ROOT, closed=True)
    raw = json.dumps(result)
    assert 'private_answer' not in raw and 'learner-response' not in raw and str(tmp_path) not in raw
    assert result['b3_authority']['ledger_status'] == 'INVALID'


def test_real_wal_is_copied_complete_query_only_and_removed_locally(tmp_path, monkeypatch):
    path = _database(tmp_path)
    m = collector()
    real_connect = m.sqlite3.connect
    opened = []
    def inspect_connect(connection_uri, *args, **kwargs):
        assert '?mode=ro' in connection_uri and 'immutable' not in connection_uri
        assert path.as_uri() not in connection_uri
        opened.append(Path(connection_uri.removeprefix('file:').split('?')[0]))
        return real_connect(connection_uri, *args, **kwargs)
    with closing(real_connect(path)) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute("UPDATE topics SET confidence=4 WHERE id='topic-lu'")
        writer.commit()
        # Synthetic writer is idle; explicit fixture attestation rehearses the
        # closed-copy algorithm without claiming this is production evidence.
        before = {p.name:p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
        monkeypatch.setattr(m.sqlite3, 'connect', inspect_connect)
        result = m.closed_schema_report(path, ROOT, closed=True)
        assert result['status'] == 'PASS'
        assert result['b3_authority']['ledger_status'] == 'PASS'
        assert result['copied_roles'] == ['main','shm','wal']
        assert result['source_files_stable'] and result['copy_deleted_locally']
        assert all(p.read_bytes() == before[p.name] for p in tmp_path.iterdir() if p.is_file())
    assert opened and all(not p.exists() for p in opened)


def test_invalid_control_blocks_closed_copy_before_database_access(tmp_path, monkeypatch):
    m = collector()
    (tmp_path / '.phase4_authority.json').write_text('{', encoding='utf-8')
    monkeypatch.setattr(m, '_inventory', lambda _: pytest.fail('invalid control allowed copy'))
    result = m.closed_schema_report(tmp_path / 'absent.db', tmp_path, closed=True)
    assert result['reason_code'] == 'control_invalid'


def test_actual_default_cli_returns_redacted_identity_without_db_access(tmp_path):
    output = tmp_path / 'identity.json'
    command = [sys.executable, str(ROOT / 'scripts/architecture_local_collector.py'),
               '--repo', str(ROOT), '--output', str(output)]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=45)
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['version'] == 2
    assert report['closed_schema_copy']['reason_code'] == 'writers_not_attested'
    assert report['GATE_A_LOCAL_PRODUCTION_AUTHORITY'] == 'BLOCKED'
    assert report['config_matches_requested_checkout'] is True
    assert len(report['launcher_source_sha256']) == 64
    assert str(ROOT) not in json.dumps(report) and str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize('field,value', [('cutover_id',None), ('promoted_at',None), ('promoted_at','2026-10-13'),
    ('promoted_at','9999-12-31T23:59:59-01:00'), ('source_manifest_hash',True), ('storage_backend',['sqlite'])])
def test_promoted_control_rejects_coerced_provenance(tmp_path, field, value):
    payload = {'version':1,'storage_backend':'sqlite','legacy_writes_blocked':True,
               'cutover_id':'verified-cutover','source_manifest_hash':'a'*64,
               'sqlite_sha256':'b'*64,'promoted_at':'2026-10-13T00:00:00Z'}
    payload[field] = value
    (tmp_path / '.phase4_authority.json').write_text(json.dumps(payload), encoding='utf-8')
    assert collector().backend_report(tmp_path)['status'] == 'INVALID'
