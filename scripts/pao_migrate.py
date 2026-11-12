"""Explicit backup-first PAO activation. Default dry-run is physically read-only."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'personal_learning_assistant/repositories/sqlite/optional_migrations/0018_pao_execution.sql'


def migrate(database, *, apply=False, backup_path=None):
    path = Path(database)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Choose an existing owner database, not a symlink.')
    uri = 'file:' + quote(path.resolve().as_posix(), safe='/:')
    wal, shm = Path(str(path)+'-wal'), Path(str(path)+'-shm')
    if not apply and wal.exists() and not shm.exists():
        raise ValueError('WAL requires its existing owner SHM. Stop writers and checkpoint, or use a verified online backup.')
    query = '?mode=rw' if apply else ('?mode=ro' if wal.exists() else '?mode=ro&immutable=1')
    con = sqlite3.connect(uri + query, uri=True, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'planner_tasks', 'weekly_reviews', 'daily_agendas'} <= tables:
            raise ValueError('Core planner migrations must be installed first.')
        script = MIGRATION.read_text()
        checksum = hashlib.sha256(script.encode()).hexdigest()
        ready = 'planner_command_receipts' in tables
        if ready:
            ledger = con.execute('SELECT checksum FROM pao_optional_migrations WHERE version=18').fetchone()
            if ledger is None or ledger[0] != checksum:
                raise ValueError('PAO migration checksum or activation ledger mismatch.')
        contradictions = con.execute("SELECT COUNT(*) FROM planner_tasks WHERE (status='completed' AND completed_at IS NULL) OR (status NOT IN ('completed','archived') AND completed_at IS NOT NULL)").fetchone()[0]
        result = {'version': 18, 'checksum': checksum, 'ready': ready,
                  'contradictory_tasks': contradictions, 'applied': False,
                  'history_policy': 'Ambiguous histories retained; no inferred work or approval.'}
        identity_script = MIGRATION.with_name('0019_obsidian_source_identity.sql').read_text()
        identity_checksum = hashlib.sha256(identity_script.encode()).hexdigest()
        identity_ready = 'obsidian_identity_reconciliation' in tables
        if identity_ready:
            identity_ledger = con.execute('SELECT checksum FROM pao_optional_migrations WHERE version=19').fetchone()
            if identity_ledger is None or identity_ledger[0] != identity_checksum:
                raise ValueError('Obsidian reconciliation checksum or activation ledger mismatch.')
        from personal_learning_assistant.services.obsidian_source_identity_service import ObsidianSourceIdentityService
        result['identity_inventory'] = ObsidianSourceIdentityService(con).preview_identity_migration()
        result['identity_ready'] = identity_ready
        if not apply or (ready and identity_ready):
            return result
        backup = Path(backup_path) if backup_path else path.with_name(path.name+'.before-pao-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.bak')
        if backup.exists() or backup.resolve() == path.resolve():
            raise ValueError('Backup destination must be new.')
        with sqlite3.connect(str(backup)) as target:
            con.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup verification failed.')
        # Statements run in a single transaction, including the checksum ledger.
        from personal_learning_assistant.repositories.sqlite.migration_runner import _iter_sql_statements
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute('CREATE TABLE IF NOT EXISTS pao_optional_migrations(version INTEGER PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)')
            for version, body, body_hash, installed in ((18,script,checksum,ready),(19,identity_script,identity_checksum,identity_ready)):
                if installed:
                    continue
                for statement in _iter_sql_statements(body):
                    con.execute(statement)
                con.execute('INSERT INTO pao_optional_migrations VALUES(?,?,?)', (version,body_hash,datetime.now(timezone.utc).isoformat()))
            if con.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Foreign key validation failed.')
            con.commit()
        except Exception:
            con.rollback()
            raise
        return {**result, 'ready': True, 'identity_ready': True, 'applied': True, 'backup': str(backup)}
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='data/learning_assistant.db')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(migrate(args.database, apply=args.apply), indent=2))

if __name__ == '__main__':
    main()
