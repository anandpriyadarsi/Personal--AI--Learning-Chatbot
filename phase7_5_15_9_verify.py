"""Read-only operator verifier for Phase 7.5.15.9 final reconciliation."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.migration_runner import (
    discover_migrations,
)
from personal_learning_assistant.services.notes_studio_read_service import (
    build_configured_notes_studio_read_service,
)
from personal_learning_assistant.services.notes_studio_reconciliation_service import (
    CUTOVER_DECISION,
    NotesStudioReconciliationService,
)


class FinalReconciliationError(RuntimeError):
    pass


def _parser():
    parser = argparse.ArgumentParser(
        description="Verify Notes Studio 2.0 reconciliation without production writes."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--legacy-notes", default="data/notes.json")
    return parser


def _uri(path: Path) -> str:
    value = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode=ro".format(quote(value, safe="/:"))


def _verify_sqlite(database_path: Path):
    if not database_path.is_file() or database_path.is_symlink():
        raise FinalReconciliationError(
            "production SQLite database is missing or is not a regular file"
        )

    connection = sqlite3.connect(
        _uri(database_path),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if str(integrity).casefold() != "ok":
            raise FinalReconciliationError(
                "SQLite integrity_check failed: {}".format(integrity)
            )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise FinalReconciliationError(
                "SQLite foreign_key_check reported {} row(s)".format(
                    len(foreign_keys)
                )
            )

        source_migrations = discover_migrations()
        applied = connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        source = [
            (item.version, item.name, item.checksum)
            for item in source_migrations
        ]
        current = [
            (int(row["version"]), str(row["name"]), str(row["checksum"]))
            for row in applied
        ]
        if current != source:
            raise FinalReconciliationError(
                "SQLite migration history does not match current migration source"
            )

        return {
            "integrity_check": "ok",
            "foreign_key_violations": 0,
            "migration_count": len(current),
            "migration_versions": [item[0] for item in current],
        }
    finally:
        connection.close()


def main(argv=None):
    args = _parser().parse_args(argv)
    root = Path(args.project_root).resolve(strict=False)
    database = (root / args.database).resolve(strict=False)
    legacy = (root / args.legacy_notes).resolve(strict=False)

    try:
        sqlite_report = _verify_sqlite(database)
        read_service = build_configured_notes_studio_read_service()
        reconciliation = NotesStudioReconciliationService(
            read_service=read_service,
            legacy_path=legacy,
        ).report()

        if reconciliation["cutover_decision"] != CUTOVER_DECISION:
            raise FinalReconciliationError(
                "unexpected Notes Studio cutover decision"
            )
        if reconciliation["automatic_migration"] is not False:
            raise FinalReconciliationError(
                "automatic legacy migration must remain disabled"
            )
        if reconciliation["legacy_status"] == "invalid":
            raise FinalReconciliationError(
                "legacy notes JSON is invalid and requires review before closure"
            )

        output = {
            "sqlite": sqlite_report,
            "reconciliation": reconciliation,
            "production_writes_performed": False,
            "automatic_legacy_migration": False,
            "tutor_modified": False,
            "retrieval_rebuild_performed": False,
        }
        print("PHASE 7.5.15.9 RECONCILIATION VERIFIER: PASS")
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (
        OSError,
        ValueError,
        sqlite3.Error,
        FinalReconciliationError,
    ) as error:
        print(
            "PHASE 7.5.15.9 RECONCILIATION VERIFIER: BLOCKED",
            file=sys.stderr,
        )
        print(
            "{}: {}".format(type(error).__name__, error),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
