"""Explicit Phase 6.5 practice-schema preview/apply operator."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
    discover_migrations,
)


CONFIRMATION_PHRASE = "APPLY_PHASE6_PRACTICE_SCHEMA"
TARGET_VERSION = 4


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.5 practice schema operator"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview")
    apply = sub.add_parser("apply")
    apply.add_argument("--confirm", default="")
    return parser


def _uri(path: Path):
    return "file:{}?mode=ro".format(
        quote(str(path.resolve()).replace("\\", "/"), safe="/:")
    )


def _applied(path: Path):
    connection = sqlite3.connect(_uri(path), uri=True)
    try:
        return tuple(
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
    finally:
        connection.close()


def main(argv=None):
    args = _parser().parse_args(argv)
    path = Path(args.database)
    if not path.is_file() or path.is_symlink():
        print("PHASE 6.5 PRACTICE SCHEMA: BLOCKED", file=sys.stderr)
        print("database is missing or not a regular file", file=sys.stderr)
        return 1

    discovered = tuple(item.version for item in discover_migrations())
    before = _applied(path)
    pending = tuple(version for version in discovered if version not in before)

    if args.command == "preview":
        print("PHASE 6.5 PRACTICE SCHEMA PREVIEW: PASS")
        print(
            json.dumps(
                {
                    "applied_versions": before,
                    "discovered_versions": discovered,
                    "pending_versions": pending,
                    "writes_performed": False,
                    "practice_schema_ready": TARGET_VERSION in before,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    later = tuple(version for version in discovered if version > TARGET_VERSION)
    if later:
        print("PHASE 6.5 PRACTICE SCHEMA: BLOCKED", file=sys.stderr)
        print(
            "this operator is superseded by later migration(s): {}".format(later),
            file=sys.stderr,
        )
        return 1
    if args.confirm != CONFIRMATION_PHRASE:
        print("PHASE 6.5 PRACTICE SCHEMA: BLOCKED", file=sys.stderr)
        print(
            "apply requires --confirm {}".format(CONFIRMATION_PHRASE),
            file=sys.stderr,
        )
        return 2

    applied_now = apply_migrations(path)
    after = _applied(path)
    connection = sqlite3.connect(_uri(path), uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()

    required = {
        "practice_sessions",
        "practice_items",
        "practice_item_sources",
        "practice_attempts",
    }
    if (
        integrity != "ok"
        or foreign_keys
        or TARGET_VERSION not in after
        or not required.issubset(tables)
    ):
        print("PHASE 6.5 PRACTICE SCHEMA: BLOCKED", file=sys.stderr)
        print("post-migration integrity/schema validation failed", file=sys.stderr)
        return 1

    print("PHASE 6.5 PRACTICE SCHEMA APPLY: PASS")
    print(
        json.dumps(
            {
                "applied_now": applied_now,
                "applied_versions": after,
                "integrity_check": integrity,
                "foreign_key_violation_count": len(foreign_keys),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
