"""Redacted local identity collector. Default: no SQLite connection or DB copy.

Run with the actual installed interpreter and --repo matching the actual launcher.
--closed-no-writers explicitly attests application/backup/sync writers are stopped.
Only then copy all DB/WAL/SHM files, verify stable bytes, and inspect the copy.
The private copy is deleted locally; output contains no academic rows or paths.
"""
from __future__ import annotations

import argparse
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


REQUIRED = ('schema_migrations', 'courses', 'topics', 'topic_aliases', 'question_topic_mappings',
            'assessment_test_session_questions', 'assessment_response_evaluations',
            'assessment_recovery_recommendations', 'planner_tasks', 'daily_agendas',
            'daily_agenda_items', 'month_plan_imports', 'month_plan_import_items',
            'weekly_reviews', 'study_sessions', 'app_settings', 'migration_imports')


def _files(database: Path) -> tuple[Path, ...]:
    return tuple(p for p in [database, Path(str(database) + '-wal'), Path(str(database) + '-shm')] if p.exists())


def _inventory(database: Path) -> dict:
    result = {}
    for p in _files(database):
        if p.is_symlink() or not p.is_file():
            raise ValueError('Database or sidecar is not a regular file')
        result[p.name] = {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    return result


def closed_schema_report(database: Path, repo: Path, *, closed: bool) -> dict:
    if not closed:
        return {'status': 'BLOCKED', 'reason': 'Closed application and no writers not attested; no database access performed'}
    if any(p.is_symlink() for p in (database, *database.parents)) or not database.is_file():
        return {'status': 'BLOCKED', 'reason': 'Database absent or unsafe path; nothing created'}
    before = _inventory(database)
    with tempfile.TemporaryDirectory(prefix='anvaya-local-schema-copy-') as temporary:
        copy_root = Path(temporary)
        for source in _files(database):
            shutil.copy2(source, copy_root / source.name)
        if before != _inventory(database):
            return {'status': 'BLOCKED', 'reason': 'Source/sidecar bytes changed while copying; copy rejected'}
        copy = copy_root / database.name
        # Never immutable mode: included WAL must be interpreted on this copy.
        connection = sqlite3.connect(copy.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            connection.execute('PRAGMA query_only=ON')
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            ledger = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall() if 'schema_migrations' in tables else []
            migrations = repo / 'personal_learning_assistant/repositories/sqlite/migrations'
            expected = []
            for sql in sorted(migrations.glob('*.sql')):
                match = re.fullmatch(r'(\d{4})_(.+)\.sql', sql.name)
                if not match or sql.is_symlink():
                    raise ValueError('Unsupported source migration inventory')
                expected.append((int(match[1]), match[2], hashlib.sha256(sql.read_bytes()).hexdigest()))
            contiguous = [r[0] for r in expected] == list(range(1, len(expected) + 1)) and bool(expected)
            integrity = connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            fk_count = len(connection.execute('PRAGMA foreign_key_check').fetchall())
            present = sorted(set(REQUIRED) & tables)
            missing = sorted(set(REQUIRED) - tables)
            columns = {table: [r[1] for r in connection.execute('PRAGMA table_info(' + table + ')')] for table in present}
            projection_count = connection.execute("SELECT COUNT(*) FROM app_settings WHERE key LIKE 'phase4.compatibility_projection.%'").fetchone()[0] if 'app_settings' in tables else 0
            matched = contiguous and ledger == expected
            if before != _inventory(database):
                return {'status': 'BLOCKED', 'reason': 'Source/sidecar bytes changed during inspection; copy rejected'}
            return {'status': 'PASS' if matched and integrity and not fk_count and not missing else 'FAIL',
                    'scope': 'Closed stable copied schema only; not production readiness',
                    'source_files_stable': True, 'ledger_matches_source': matched, 'ledger': ledger,
                    'integrity_ok': integrity, 'foreign_key_violations': fk_count,
                    'tables_present': present, 'missing_tables': missing, 'columns': columns,
                    'projection_key_count': projection_count,
                    'projection_freshness_and_identity': 'BLOCKED: keys alone do not prove normalized/projection parity',
                    'copy_deleted_locally': True}
        finally:
            connection.close()


def _other_windows_python_count() -> int:
    # Do not log executable paths or command lines. A running unrelated Python
    # process conservatively blocks copying until the operator resolves it.
    command = "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\\.exe$' -and $_.ProcessId -ne " + str(os.getpid()) + " }).Count"
    return int(subprocess.check_output(['powershell', '-NoProfile', '-Command', command], text=True).strip())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--closed-no-writers', action='store_true')
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    output = args.output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)) or output.resolve().is_relative_to(repo) or output.exists():
        parser.error('Output must be a new file outside the installed checkout')
    root = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(root).resolve() != repo:
        parser.error('Pass the exact installed checkout root')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    control = repo / '.phase4_authority.json'
    backend = 'legacy_default_control_absent'
    if control.exists():
        if control.is_symlink():
            parser.error('Authority control is a symlink; stop and review locally')
        try:
            raw = json.loads(control.read_text(encoding='utf-8'))
            value = raw.get('storage_backend') if isinstance(raw, dict) else None
            backend = value if value in {'legacy', 'dual_read', 'sqlite'} else 'unknown_requires_review'
        except (ValueError, OSError):
            backend = 'unreadable_requires_review'
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
            count = _other_windows_python_count()
            process_result = 'no_other_python_processes' if count == 0 else 'BLOCKED: other Python processes exist'
            closed = count == 0
    report = {'schema': 'anvaya.local-authority-manifest', 'version': 1,
              'source_head': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
              'working_tree_clean': not bool(git('status', '--porcelain=v1', '-uall')),
              'python_version': sys.version.split()[0], 'platform': platform.system(),
              'sqlite_version': sqlite3.sqlite_version,
              'interpreter_path_sha256': hashlib.sha256(str(Path(sys.executable).resolve()).encode()).hexdigest(),
              'config_matches_requested_checkout': True, 'authority_backend': backend,
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
