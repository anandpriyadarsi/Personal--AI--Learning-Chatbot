"""Inspect provider requests, or recover one only after ALL writers are stopped.

The acknowledgement flag is an operator assertion, not proof of process death.
No timestamp exists in this ledger; sending does not mean stale.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from personal_learning_assistant.services.provider_permission_service import PermissionGuard


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='Existing Native Library SQLite owner')
    parser.add_argument('--list', action='store_true', help='Read-only request summary (default)')
    parser.add_argument('--dry-run', action='store_true', help='Read-only request summary; never mutate')
    parser.add_argument('--operation', help='Exact operation ID; optional filter in read-only mode')
    parser.add_argument('--mark-unknown', action='store_true', help='Retain reservation and block replay; never refund or resend')
    parser.add_argument('--writers-stopped', action='store_true', help='I have actually stopped ALL ANVAYA app and worker writers')
    args = parser.parse_args(argv)
    if args.mark_unknown and (not args.writers_stopped or not args.operation or args.list or args.dry_run):
        parser.error('Recovery requires --operation ID --mark-unknown --writers-stopped; do not combine with --list/--dry-run')
    database = Path(args.database).resolve()
    if not database.is_file():
        parser.error('Existing database required; nothing was created')
    try:
        # Inspect existing schema with no creation, migration, or write locks.
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as con:
            con.row_factory = sqlite3.Row
            query = 'SELECT id AS operation,month,reserved,actual,status FROM mm_provider_requests'
            rows = con.execute(query + (' WHERE id=?' if args.operation else '') + ' ORDER BY id', (args.operation,) if args.operation else ()).fetchall()
        if args.mark_unknown:
            report = PermissionGuard(database).mark_unknown(args.operation)
        else:
            report = dict(dry_run=True, requests=[dict(row) for row in rows])
    except (sqlite3.Error, ValueError):
        parser.error('Request inspection/recovery failed; operation must exist and be sending or already outcome_unknown')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
