"""Explicit backup-first optional migration. Never called by web startup or GET."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from urllib.parse import quote

MIGRATION = Path(__file__).parents[1] / 'repositories/sqlite/optional_migrations/0017_tutor_coding.sql'


def activate(database):
    path = Path(database).resolve(strict=True)
    if not path.is_file():
        raise ValueError('The canonical Tutor database must exist.')
    # mode=rw prevents accidentally creating a new owner database on a typo.
    con = sqlite3.connect('file:' + quote(path.as_posix(),safe='/:') + '?mode=rw', uri=True)
    try:
        con.execute('PRAGMA foreign_keys=ON')
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_coding_tasks'").fetchone():
            from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
            from personal_learning_assistant.repositories.sqlite.tutor_coding_repository import SQLiteTutorCodingRepository
            if not SQLiteTutorCodingRepository(SQLiteTutorRepository(con)).available():
                raise ValueError('Coding schema incomplete; restore or inspect the failed activation.')
            return None
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_sessions'").fetchone():
            raise ValueError('Tutor schema is missing; activate the existing canonical owner first.')
        backup = path.with_name(path.name + '.before-coding-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.bak')
        with sqlite3.connect(str(backup)) as target:
            con.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity check failed; migration not attempted.')
        script = MIGRATION.read_text(encoding='utf-8')
        con.executescript('BEGIN IMMEDIATE;\n' + script)
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Coding activation failed foreign-key validation.')
        # Optional migrations have a separate ledger; do not advance core migrations past optional 0015/16.
        con.execute('CREATE TABLE IF NOT EXISTS tutor_optional_migrations (version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)')
        con.execute("INSERT INTO tutor_optional_migrations VALUES (17,?)",(datetime.now(timezone.utc).isoformat(),))
        con.commit()
        return backup
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='data/learning_assistant.db')
    args = parser.parse_args()
    backup = activate(args.database)
    print('Coding Studio ready. ' + (f'Canonical backup: {backup}' if backup else 'Already activated.'))

if __name__ == '__main__':
    main()
