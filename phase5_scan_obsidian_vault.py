"""Operator CLI for Phase 5.3 Obsidian vault preview/registration."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from obsidian_integration import get_vault_path
from personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner import (
    ObsidianVaultRootError,
    ObsidianVaultScanner,
    ObsidianVaultScannerError,
)
from personal_learning_assistant.repositories.sqlite.obsidian_vault_repository import (
    ObsidianVaultRepositoryError,
    SQLiteObsidianVaultRepository,
)
from personal_learning_assistant.services.obsidian_vault_registry_service import (
    ObsidianVaultRegistryService,
)


CONFIRMATION_PHRASE = "REGISTER_PHASE5_OBSIDIAN_VAULT"


def _parser():
    parser = argparse.ArgumentParser(
        description="Preview/register Obsidian note metadata and link graph."
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    path_group = parser.add_mutually_exclusive_group(required=True)
    path_group.add_argument("--vault-path")
    path_group.add_argument("--configured", action="store_true")
    parser.add_argument("--vault-key", default="obsidian-vault")
    parser.add_argument("--vault-name", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser


def _sqlite_uri(path: Path, mode: str) -> str:
    text = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode={}".format(quote(text, safe="/:"), mode)


def _open_existing(path: Path, *, writable: bool):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(
            "SQLite database is missing or not a regular file: {}".format(path)
        )
    connection = sqlite3.connect(
        _sqlite_uri(path, "rw" if writable else "ro"),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _report(plan_or_result, *, mode: str, configured: bool):
    result = {
        "mode": mode,
        "configured": configured,
        "vault_key": plan_or_result.vault_key,
        "scan_manifest_hash": plan_or_result.scan_manifest_hash,
        "blocking_issue_count": plan_or_result.blocking_issue_count,
        "warning_count": plan_or_result.warning_count,
        "markdown_files_modified": False,
    }
    if mode == "preview":
        result.update(
            {
                "note_count": plan_or_result.note_count,
                "create_count": plan_or_result.create_count,
                "match_count": plan_or_result.match_count,
                "update_count": plan_or_result.update_count,
                "missing_registry_count": plan_or_result.missing_registry_count,
                "tag_count": plan_or_result.tag_count,
                "resolved_link_count": plan_or_result.resolved_link_count,
                "unresolved_link_count": plan_or_result.unresolved_link_count,
                "ambiguous_link_count": plan_or_result.ambiguous_link_count,
                "external_link_count": plan_or_result.external_link_count,
            }
        )
    else:
        result.update(
            {
                "created": plan_or_result.created,
                "matched": plan_or_result.matched,
                "updated": plan_or_result.updated,
                "missing_registry_count": len(plan_or_result.missing_registry_ids),
                "tag_count": plan_or_result.tag_count,
                "resolved_link_count": plan_or_result.resolved_link_count,
                "unresolved_link_count": plan_or_result.unresolved_link_count,
                "ambiguous_link_count": plan_or_result.ambiguous_link_count,
                "external_link_count": plan_or_result.external_link_count,
            }
        )
    return result


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.apply and args.confirm != CONFIRMATION_PHRASE:
        print("PHASE 5.3 OBSIDIAN REGISTRATION: BLOCKED", file=sys.stderr)
        print(
            "--apply requires --confirm {}".format(CONFIRMATION_PHRASE),
            file=sys.stderr,
        )
        return 2
    if not args.apply and args.confirm:
        print("--confirm is only valid with --apply", file=sys.stderr)
        return 2

    configured = bool(args.configured)
    vault_path = get_vault_path() if configured else args.vault_path
    if configured and not vault_path:
        print("PHASE 5.3 OBSIDIAN PREVIEW: SKIPPED")
        print(
            json.dumps(
                {
                    "configured": False,
                    "mode": "preview",
                    "reason": "no enabled valid Obsidian vault is configured",
                    "markdown_files_modified": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    try:
        scanner = ObsidianVaultScanner(
            args.vault_key,
            vault_path,
            vault_name=args.vault_name or None,
        )
        scan = scanner.scan()
        connection = _open_existing(Path(args.database), writable=args.apply)
        try:
            repository = SQLiteObsidianVaultRepository(connection)
            service = ObsidianVaultRegistryService(repository)
            if args.apply:
                outcome = service.apply(scan)
                mode = "apply"
            else:
                outcome = service.preview(scan)
                mode = "preview"
        finally:
            connection.close()
    except (
        OSError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
        ObsidianVaultRootError,
        ObsidianVaultScannerError,
        ObsidianVaultRepositoryError,
    ) as error:
        label = "REGISTRATION" if args.apply else "PREVIEW"
        print("PHASE 5.3 OBSIDIAN {}: BLOCKED".format(label), file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1

    label = "REGISTRATION" if args.apply else "PREVIEW"
    print("PHASE 5.3 OBSIDIAN {}: PASS".format(label))
    print(json.dumps(_report(outcome, mode=mode, configured=configured), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
