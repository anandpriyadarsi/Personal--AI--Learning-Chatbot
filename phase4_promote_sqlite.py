"""Operator CLI for the explicit Final Phase-4 locked SQLite promotion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from personal_learning_assistant.migration.final_locked_promotion import (
    CONFIRMATION_PHRASE,
    FinalLockedPromotionError,
    preflight_final_locked_promotion,
    promote_final_locked_sqlite_authority,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight or explicitly execute the final locked Phase-4 structured "
            "authority promotion to SQLite."
        )
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Repository/project root containing data/ (default: current directory).",
    )
    parser.add_argument(
        "--backup-dir",
        required=True,
        help=(
            "New final cutover backup directory. Relative paths are resolved "
            "against --project-root; its parent must already exist."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--preflight",
        action="store_true",
        help="Run read-only safety checks. No database/control/lock/backup is created.",
    )
    mode.add_argument(
        "--confirm",
        metavar="PHRASE",
        help="Execute only when PHRASE exactly equals {}.".format(CONFIRMATION_PHRASE),
    )
    return parser


def _json(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.project_root)
    backup = Path(args.backup_dir)
    try:
        if args.preflight:
            result = preflight_final_locked_promotion(
                project_root=root,
                backup_directory=backup,
            )
            print("FINAL PHASE 4 SQLITE PROMOTION PREFLIGHT: PASS")
            print(_json(result.to_dict()))
            print("")
            print("No writes were performed. Stop every Personal AI Learning Assistant")
            print("process before the later explicit promotion command.")
            return 0

        if args.confirm != CONFIRMATION_PHRASE:
            print(
                "BLOCKED: execution requires the exact confirmation phrase: {}".format(
                    CONFIRMATION_PHRASE
                ),
                file=sys.stderr,
            )
            return 2

        print("FINAL PHASE 4 LOCKED SQLITE AUTHORITY PROMOTION")
        print("This operation will make SQLite authoritative for Phase-4 structured state.")
        print("Legacy structured JSON will be retained but its structured writers will be blocked.")
        result = promote_final_locked_sqlite_authority(
            project_root=root,
            backup_directory=backup,
            confirmation=args.confirm,
        )
        print("FINAL PHASE 4 SQLITE AUTHORITY PROMOTION: SUCCESS")
        print(_json(result.to_dict()))
        return 0
    except (FinalLockedPromotionError, ValueError, OSError) as error:
        print("FINAL PHASE 4 SQLITE AUTHORITY PROMOTION: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
