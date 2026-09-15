"""Read-only Phase 5.1 registry readiness check for the promoted local SQLite DB."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    KnowledgeRegistryError,
    SQLiteKnowledgeRegistryRepository,
)


def _parser():
    parser = argparse.ArgumentParser(description="Verify Phase 5.1 registry schema read-only.")
    parser.add_argument("--database", default="data/learning_assistant.db")
    return parser


def _uri(path: Path) -> str:
    value = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode=ro".format(quote(value, safe="/:"))


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    path = Path(args.database)
    if not path.is_file() or path.is_symlink():
        print("PHASE 5.1 REGISTRY READINESS: BLOCKED", file=sys.stderr)
        print("Database is missing or not a regular file: {}".format(path), file=sys.stderr)
        return 1
    try:
        connection = sqlite3.connect(_uri(path), uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            repository = SQLiteKnowledgeRegistryRepository(connection)
            readiness = repository.readiness()
            counts = {
                "knowledge_documents": int(connection.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]),
                "knowledge_chunks": int(connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]),
                "index_jobs": int(connection.execute("SELECT COUNT(*) FROM index_jobs").fetchone()[0]),
                "open_operation_journal": int(connection.execute("SELECT COUNT(*) FROM operation_journal WHERE state NOT IN ('completed','failed')").fetchone()[0]),
                "pending_outbox": int(connection.execute("SELECT COUNT(*) FROM outbox_events WHERE processed_at IS NULL AND failed_at IS NULL").fetchone()[0]),
            }
        finally:
            connection.close()
    except (sqlite3.Error, KnowledgeRegistryError) as error:
        print("PHASE 5.1 REGISTRY READINESS: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    print("PHASE 5.1 REGISTRY READINESS: PASS")
    print(json.dumps({
        "tables": list(readiness.tables),
        "integrity_check": list(readiness.integrity_check),
        "foreign_key_violation_count": len(readiness.foreign_key_violations),
        "reads_only": readiness.total_changes_before == readiness.total_changes_after,
        "counts": counts,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
