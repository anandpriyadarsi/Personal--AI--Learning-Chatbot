"""Redacted local identity collector. Default: no SQLite connection or DB copy.

Run with the actual installed interpreter and --repo matching the actual launcher.
--closed-no-writers explicitly attests application/backup/sync writers are stopped.
Only then copy all DB/WAL/SHM files, verify stable bytes, and inspect the copy.
The private copy is deleted locally; output contains no academic rows or paths.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

# Support execution from a reviewed tools-only archive outside the installation.
# --repo still identifies the actual installed checkout, not this tool source.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from personal_learning_assistant.repositories.sqlite.b3_authority_repository import (
    inspect_authority, source_migration_ledger,
)


REQUIRED = ('schema_migrations', 'courses', 'topics', 'topic_aliases', 'question_topic_mappings',
            'assessment_test_session_questions', 'assessment_response_evaluations',
            'assessment_recovery_recommendations', 'planner_tasks', 'daily_agendas',
            'daily_agenda_items', 'month_plan_imports', 'month_plan_import_items',
            'weekly_reviews', 'study_sessions', 'app_settings', 'migration_imports')


def _files(database: Path) -> tuple[Path, ...]:
    paths = (database, Path(str(database) + '-wal'), Path(str(database) + '-shm'))
    journal = Path(str(database) + '-journal')
    if journal.exists() or journal.is_symlink():
        raise ValueError('Rollback journal requires separate local recovery review')
    for path in paths:
        if any(p.is_symlink() for p in (path, *path.absolute().parents)):
            raise ValueError('Unsafe database inventory')
        if path.exists() and not path.is_file():
            raise ValueError('Database inventory must be regular files')
    return tuple(p for p in paths if p.exists())


def _inventory(database: Path) -> dict:
    result = {}
    for p in _files(database):
        if p.is_symlink() or not p.is_file():
            raise ValueError('Database or sidecar is not a regular file')
        stat = p.stat()
        result[p.name] = {'bytes': stat.st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                          'identity': (stat.st_dev, stat.st_ino, stat.st_mtime_ns)}
    return result


def closed_schema_report(database: Path, repo: Path, *, closed: bool) -> dict:
    if not closed:
        return {'status': 'BLOCKED', 'reason_code': 'writers_not_attested',
                'reason': 'Closed application and no writers not attested; no database access performed'}
    if backend_report(repo)['status'] == 'INVALID':
        return {'status':'BLOCKED','reason_code':'control_invalid'}
    if any(p.is_symlink() for p in (database, *database.parents)) or not database.is_file():
        return {'status': 'BLOCKED', 'reason_code': 'unsafe_database_inventory', 'reason': 'Database absent or unsafe path; nothing created'}
    try:
        return _closed_schema_report(database, repo)
    except sqlite3.DatabaseError:
        return {'status': 'INVALID', 'reason_code': 'copied_schema_invalid'}
    except OSError:
        return {'status': 'BLOCKED', 'reason_code': 'copy_access_failed'}
    except (ValueError, TypeError):
        return {'status': 'BLOCKED', 'reason_code': 'unsafe_database_inventory'}


def _closed_schema_report(database: Path, repo: Path) -> dict:
    before = _inventory(database)
    result = _inspect_private_copy(database, repo, before)
    # TemporaryDirectory has completed disposal before this statement.
    result['copy_deleted_locally'] = True
    return result


def _inspect_private_copy(database: Path, repo: Path, before: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix='anvaya-local-schema-copy-') as temporary:
        copy_root = Path(temporary)
        for source in _files(database):
            shutil.copy2(source, copy_root / source.name)
        if before != _inventory(database):
            return {'status': 'BLOCKED', 'reason_code': 'source_changed', 'reason': 'Source/sidecar bytes changed while copying; copy rejected'}
        copy = copy_root / database.name
        copied = _inventory(copy)
        if set(before) != set(copied) or any((before[k]['bytes'],before[k]['sha256']) != (copied[k]['bytes'],copied[k]['sha256']) for k in before):
            return {'status':'BLOCKED','reason_code':'copied_bytes_mismatch'}
        # Never immutable mode: included WAL must be interpreted on this copy.
        connection = sqlite3.connect(copy.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            ledger = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall() if 'schema_migrations' in tables else []
            expected = list(source_migration_ledger(repo))
            contiguous = [r[0] for r in expected] == list(range(1, len(expected) + 1)) and bool(expected)
            integrity = connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            fk_count = len(connection.execute('PRAGMA foreign_key_check').fetchall())
            present = sorted(set(REQUIRED) & tables)
            missing = sorted(set(REQUIRED) - tables)
            # Only known source fields enter shareable output; arbitrary local
            # schema names/DDL could contain private text and stay private.
            projection_count = connection.execute("SELECT COUNT(*) FROM app_settings WHERE key LIKE 'phase4.compatibility_projection.%'").fetchone()[0] if 'app_settings' in tables else 0
            matched = contiguous and ledger == expected
            backend = backend_report(repo)
            b3 = inspect_authority(connection, expected_ledger=tuple(expected),
                                   backend=backend['backend'], control_status=backend['status'])
            if before != _inventory(database):
                return {'status': 'BLOCKED', 'reason_code': 'source_changed', 'reason': 'Source/sidecar bytes changed during inspection; copy rejected'}
            result = {'status': 'PASS' if matched and integrity and not fk_count and not missing and b3.schema_status == 'PASS' else 'FAIL',
                    'reason_code': 'closed_copy_inspected',
                    'scope': 'Closed stable copied schema only; not production readiness',
                    'source_files_stable': True, 'ledger_matches_source': matched, 'ledger': b3.ledger,
                    'integrity_ok': integrity, 'foreign_key_violations': fk_count,
                    'tables_present': present, 'missing_tables': missing,
                    'projection_key_count': projection_count,
                    'projection_freshness_and_identity': 'BLOCKED: keys alone do not prove normalized/projection parity',
                    'copied_roles': sorted('main' if name == database.name else name.rsplit('-',1)[-1] for name in before),
                    'b3_authority': asdict(b3)}
        finally:
            connection.close()
        if before != _inventory(database):
            return {'status':'BLOCKED','reason_code':'source_changed','reason':'Source bytes changed; result discarded'}
        after_copy = _inventory(copy)
        # SQLite may coordinate the private SHM. Main/WAL bytes remain protected.
        if any(name not in after_copy or after_copy[name]['sha256'] != item['sha256'] for name,item in copied.items() if not name.endswith('-shm')):
            return {'status':'BLOCKED','reason_code':'copied_sql_state_changed'}
        return result


def backend_report(repo: Path) -> dict:
    """Read only existing control; fixed codes, never arbitrary file content."""
    control = Path(repo).absolute() / '.phase4_authority.json'
    if any(p.is_symlink() for p in (control, *control.parents)):
        return {'backend':'unknown','status':'INVALID','reason_code':'control_invalid'}
    if not control.exists():
        return {'backend':'legacy','status':'UNVERIFIABLE','reason_code':'control_absent_legacy_default'}
    try:
        raw = json.loads(control.read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or type(raw.get('version',1)) is not int or type(raw.get('legacy_writes_blocked',False)) is not bool:
            raise ValueError('Malformed control types')
        string_fields = ('storage_backend','cutover_id','source_manifest_hash','sqlite_sha256','promoted_at')
        if any(key in raw and type(raw[key]) is not str for key in string_fields):
            raise ValueError('Malformed control provenance types')
        if raw.get('storage_backend','legacy').strip().lower().replace('-','_') == 'sqlite':
            if any(not raw.get(key,'').strip() for key in string_fields):
                raise ValueError('Missing promoted provenance')
            stamp = datetime.fromisoformat(raw['promoted_at'].replace('Z','+00:00'))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError('Promotion timezone is unknown')
            stamp.astimezone(timezone.utc)
        # Reuse the actual authority contract, without logging its diagnostic
        # exceptions (these can contain local paths or untrusted field names).
        from personal_learning_assistant.migration.authority_promotion import AuthorityControlState
        value = AuthorityControlState(**raw)
        return {'backend':value.storage_backend,'status':'PASS','reason_code':'control_valid'}
    except (OSError, ValueError, TypeError, RuntimeError, OverflowError):
        return {'backend':'unknown','status':'INVALID','reason_code':'control_invalid'}


def _other_windows_python_count() -> int:
    # Do not log executable paths or command lines. A running unrelated Python
    # process conservatively blocks copying until the operator resolves it.
    command = "$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\\.exe$' -and $_.ProcessId -ne " + str(os.getpid()) + " }).Count"
    return int(subprocess.check_output(['powershell', '-NoProfile', '-Command', command], text=True, stderr=subprocess.DEVNULL, timeout=30).strip())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--closed-no-writers', action='store_true')
    args = parser.parse_args(argv)
    if any(p.is_symlink() for p in (args.repo.absolute(), *args.repo.absolute().parents)):
        parser.error('Installed checkout must not contain symlinks')
    repo = args.repo.resolve()
    output = args.output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)) or output.resolve().is_relative_to(repo) or output.exists():
        parser.error('Output must be a new file outside the installed checkout')
    root = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(root).resolve() != repo:
        parser.error('Pass the exact installed checkout root')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    backend = backend_report(repo)
    # Verify the actual installed config import, with no app or provider launch.
    identity = subprocess.check_output([sys.executable, '-c',
        'import config,json; print(json.dumps({"source":str(config.BASE_PATH),"database":str(config.DATABASE_PATH)}))'],
        cwd=repo, env={**os.environ, 'PYTHONPATH': str(repo), 'PYTHONDONTWRITEBYTECODE': '1'}, text=True)
    config = json.loads(identity)
    if Path(config['source']).resolve() != repo:
        parser.error('Installed config resolves another source root')
    database = Path(config['database'])
    if database.resolve() != (repo / 'data/learning_assistant.db').resolve():
        parser.error('Unexpected database authority path; do not guess')
    closed = args.closed_no_writers
    process_result = 'NOT RUN: no copy requested'
    if closed:
        if platform.system() != 'Windows':
            closed = False
            process_result = 'BLOCKED: local Windows process identity unavailable'
        else:
            try:
                count = _other_windows_python_count()
                process_result = 'no_other_python_processes' if count == 0 else 'BLOCKED: other Python processes exist'
                closed = count == 0
            except (OSError, ValueError, subprocess.SubprocessError):
                closed = False
                process_result = 'BLOCKED: process inventory unavailable'
    # Invalid control never permits schema-copy certification.
    closed = closed and backend['status'] != 'INVALID'
    source_head = git('rev-parse', 'HEAD')
    launcher = repo / 'phase7_web.py'
    if any(p.is_symlink() for p in (launcher, *launcher.parents)) or not launcher.is_file():
        parser.error('Expected installed launcher source is unavailable')
    report = {'schema': 'anvaya.local-authority-manifest', 'version': 2,
              'source_head': source_head,
              'branch_sha256': hashlib.sha256(git('branch', '--show-current').encode()).hexdigest(),
              'working_tree_clean': not bool(git('status', '--porcelain=v1', '-uall')),
              'python_version': sys.version.split()[0], 'platform': platform.system(),
              'sqlite_version': sqlite3.sqlite_version,
              'interpreter_path_sha256': hashlib.sha256(str(Path(sys.executable).resolve()).encode()).hexdigest(),
              'config_matches_requested_checkout': True, 'authority_backend': backend['backend'],
              'launcher_source_sha256': hashlib.sha256(launcher.read_bytes()).hexdigest(),
              'backend_control': backend,
              'launcher_match': 'OPERATOR REVIEW REQUIRED: command must use the actual launcher interpreter and checkout',
              'process_check': process_result, 'closed_schema_copy': closed_schema_report(database, repo, closed=closed),
              'GATE_A_LOCAL_PRODUCTION_AUTHORITY': 'BLOCKED',
              'operator_attestation': bool(args.closed_no_writers),
              'limitations': 'Process scan cannot prove absence of hidden backup/sync writers. Operator attestation required. No vault or academic rows exported.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Redacted manifest written. Local production authority remains BLOCKED pending identity/projection review.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
