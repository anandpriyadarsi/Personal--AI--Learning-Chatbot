"""Read-only operator preview for Phase 5.5 Resources 2 migration/reconciliation."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.resources2_repository import (
    Resources2RepositoryError,
    SQLiteResources2Repository,
)
from personal_learning_assistant.services.resource_legacy_reconciliation import (
    reconcile_legacy_resources,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Preview legacy Resources 2 reconciliation without writes."
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--legacy-resources", default="data/resources.json")
    return parser


def _uri(path: Path) -> str:
    value = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode=ro".format(quote(value, safe="/:"))


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    db = Path(args.database)
    if not db.is_file() or db.is_symlink():
        print("PHASE 5.5 RESOURCES 2 PREVIEW: BLOCKED", file=sys.stderr)
        print("production SQLite database is missing/not regular", file=sys.stderr)
        return 1
    try:
        connection = sqlite3.connect(
            _uri(db), uri=True, isolation_level=None, timeout=5.0
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            repository = SQLiteResources2Repository(connection)
            before = connection.total_changes
            report = reconcile_legacy_resources(args.legacy_resources, repository)
            after = connection.total_changes
            resource_count = connection.execute(
                "SELECT COUNT(*) FROM resources"
            ).fetchone()[0]
        finally:
            connection.close()
    except (OSError, sqlite3.Error, Resources2RepositoryError, ValueError) as error:
        print("PHASE 5.5 RESOURCES 2 PREVIEW: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1

    if before != after:
        print("PHASE 5.5 RESOURCES 2 PREVIEW: BLOCKED", file=sys.stderr)
        print("read-only preview unexpectedly changed SQLite", file=sys.stderr)
        return 1

    decisions = {}
    for item in report.legacy_decisions:
        decisions[item.decision] = decisions.get(item.decision, 0) + 1

    print("PHASE 5.5 RESOURCES 2 PREVIEW: PASS")
    print(
        json.dumps(
            {
                "source_status": report.source_status,
                "source_byte_count": report.source_byte_count,
                "source_sha256": report.source_sha256,
                "validated_legacy_records": report.validated_legacy_records,
                "legacy_decision_counts": decisions,
                "registered_resource_count": int(resource_count),
                "unlinked_document_candidate_count": len(report.document_candidates),
                "unlinked_note_candidate_count": len(report.note_candidates),
                "preview_writes_performed": False,
                "auto_import_performed": False,
                "auto_merge_performed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
