"""Read-only operator CLI for Phase 4 post-promotion verification and closure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from personal_learning_assistant.migration.post_promotion_verification import (
    PostPromotionVerificationError,
    verify_post_promotion_closure,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an already-promoted Phase 4 SQLite authority without "
            "changing SQLite, legacy JSON, authority control, or backups."
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
        help="Final promotion backup directory created by the locked cutover.",
    )
    parser.add_argument(
        "--allow-post-promotion-db-changes",
        action="store_true",
        help=(
            "Allow a database SHA different from the promotion-time SHA. "
            "Do not use for the immediate Phase 4 closure run."
        ),
    )
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = verify_post_promotion_closure(
            project_root=Path(args.project_root),
            backup_directory=Path(args.backup_dir),
            require_promoted_database_hash=not args.allow_post_promotion_db_changes,
        )
    except (PostPromotionVerificationError, OSError, ValueError) as error:
        print("PHASE 4 POST-PROMOTION VERIFICATION: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1

    if report.status == "pass_with_review":
        print("PHASE 4 POST-PROMOTION VERIFICATION: PASS WITH REVIEW")
    else:
        print("PHASE 4 POST-PROMOTION VERIFICATION: PASS")
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    print("")
    print("Verification was read-only. No authority/data/backup mutation was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
