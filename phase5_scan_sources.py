"""Operator CLI for Phase 5.2 source preview/registration.

Preview is the default and opens SQLite read-only. Applying source metadata to
SQLite requires both ``--apply`` and the exact confirmation phrase. Source files
are never moved, renamed, rewritten or deleted by this command.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.filesystem.source_scanner import (
    FileSystemSourceScanner,
    SourceRootError,
    SourceScannerError,
)
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    KnowledgeRegistryError,
    SQLiteKnowledgeRegistryRepository,
)
from personal_learning_assistant.services.knowledge_registry_service import (
    KnowledgeRegistryService,
)
from personal_learning_assistant.services.source_scanner_service import (
    DocumentSourceScannerService,
    SourceScanBlockedError,
)


CONFIRMATION_PHRASE = "REGISTER_PHASE5_SOURCES"


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Preview/register Phase 5.2 "
            "knowledge source metadata."
        )
    )
    parser.add_argument(
        "--database",
        default="data/learning_assistant.db",
    )
    parser.add_argument(
        "--root",
        action="append",
        required=True,
        metavar="KEY=PATH",
        help=(
            "Explicit source root. Repeat for "
            "multiple roots."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
    )
    parser.add_argument(
        "--confirm",
        default="",
    )
    return parser


def _parse_root(value: str):
    if "=" not in value:
        raise ValueError(
            "--root must use KEY=PATH"
        )

    key, raw_path = value.split("=", 1)
    key = key.strip()
    raw_path = raw_path.strip()

    if not key or not raw_path:
        raise ValueError(
            "--root must contain a non-empty "
            "KEY and PATH"
        )

    return key, Path(raw_path)


def _sqlite_uri(
    path: Path,
    mode: str,
) -> str:
    text = (
        str(path.resolve(strict=False))
        .replace("\\", "/")
    )
    return "file:{}?mode={}".format(
        quote(text, safe="/:"),
        mode,
    )


def _open_existing(
    path: Path,
    *,
    writable: bool,
):
    if (
        not path.is_file()
        or path.is_symlink()
    ):
        raise RuntimeError(
            "SQLite database is missing or "
            "not a regular file: {}".format(path)
        )

    mode = "rw" if writable else "ro"

    connection = sqlite3.connect(
        _sqlite_uri(path, mode),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        "PRAGMA foreign_keys=ON"
    )
    connection.execute(
        "PRAGMA busy_timeout=5000"
    )

    return connection


def _plan_dict(plan):
    return {
        "root_key": plan.root_key,
        "scan_manifest_hash": (
            plan.scan_manifest_hash
        ),
        "scanned_count": plan.scanned_count,
        "create_count": plan.create_count,
        "match_count": plan.match_count,
        "update_count": plan.update_count,
        "duplicate_group_count": (
            plan.duplicate_group_count
        ),
        "missing_registry_count": len(
            plan.missing_registry_ids
        ),
        "issue_count": plan.issue_count,
        "ignored_unsupported": (
            plan.ignored_unsupported
        ),
        "ignored_symlinks": (
            plan.ignored_symlinks
        ),
    }


def _result_dict(result):
    return {
        "root_key": result.root_key,
        "scan_manifest_hash": (
            result.scan_manifest_hash
        ),
        "scanned_count": len(result.items),
        "created": result.created,
        "matched": result.matched,
        "updated": result.updated,
        "duplicate_group_count": len(
            result.duplicate_groups
        ),
        "missing_registry_count": len(
            result.missing_registry_ids
        ),
        "issue_count": result.issue_count,
        "ignored_unsupported": (
            result.ignored_unsupported
        ),
        "ignored_symlinks": (
            result.ignored_symlinks
        ),
    }


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    if (
        args.apply
        and args.confirm
        != CONFIRMATION_PHRASE
    ):
        print(
            "PHASE 5.2 SOURCE REGISTRATION: "
            "BLOCKED",
            file=sys.stderr,
        )
        print(
            "--apply requires --confirm "
            + CONFIRMATION_PHRASE,
            file=sys.stderr,
        )
        return 2

    if (
        not args.apply
        and args.confirm
    ):
        print(
            "--confirm is only valid "
            "with --apply",
            file=sys.stderr,
        )
        return 2

    try:
        roots = [
            _parse_root(value)
            for value in args.root
        ]

        keys = [
            key.strip().lower()
            for key, _path in roots
        ]

        if len(keys) != len(set(keys)):
            raise ValueError(
                "root keys must be unique "
                "in one run"
            )

        database = Path(args.database)

        connection = _open_existing(
            database,
            writable=args.apply,
        )

        try:
            repository = (
                SQLiteKnowledgeRegistryRepository(
                    connection
                )
            )
            registry = (
                KnowledgeRegistryService(
                    repository
                )
            )
            orchestration = (
                DocumentSourceScannerService(
                    repository,
                    registry,
                )
            )

            scans = tuple(
                FileSystemSourceScanner(
                    key,
                    path,
                ).scan()
                for key, path in roots
            )

            if args.apply:
                issue_count = sum(
                    len(scan.issues)
                    for scan in scans
                )
                if issue_count:
                    raise SourceScanBlockedError(
                        "one or more roots contain "
                        "{} unresolved scan issue(s); "
                        "no registration was started"
                        .format(issue_count)
                    )

            outputs = []

            for scan in scans:
                if args.apply:
                    result = (
                        orchestration.apply(
                            scan
                        )
                    )
                    outputs.append(
                        _result_dict(result)
                    )
                else:
                    outputs.append(
                        _plan_dict(
                            orchestration.preview(
                                scan
                            )
                        )
                    )
        finally:
            connection.close()

    except (
        OSError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
        KnowledgeRegistryError,
        SourceRootError,
        SourceScannerError,
        SourceScanBlockedError,
    ) as error:
        label = (
            "REGISTRATION"
            if args.apply
            else "PREVIEW"
        )
        print(
            "PHASE 5.2 SOURCE {}: BLOCKED".format(
                label
            ),
            file=sys.stderr,
        )
        print(
            "{}: {}".format(
                type(error).__name__,
                error,
            ),
            file=sys.stderr,
        )
        return 1

    label = (
        "REGISTRATION"
        if args.apply
        else "PREVIEW"
    )

    print(
        "PHASE 5.2 SOURCE {}: PASS".format(
            label
        )
    )
    print(
        json.dumps(
            {
                "mode": (
                    "apply"
                    if args.apply
                    else "preview"
                ),
                "root_count": len(outputs),
                "roots": outputs,
                "source_files_modified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
