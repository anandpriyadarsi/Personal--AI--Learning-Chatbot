"""Phase 7.3 Full Restore + Reverse-Restore Rehearsal CLI."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from personal_learning_assistant.phase7.restore_rehearsal import (
    CONFIRMATION_PHRASE,
    preview_restore_rehearsal,
    rehearse_recovery_pair,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 7.3 isolated full restore + reverse-restore rehearsal"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("--recovery-root", required=True)

    rehearse = sub.add_parser("rehearse")
    rehearse.add_argument("--recovery-root", required=True)
    rehearse.add_argument("--project-root", default=".")
    rehearse.add_argument("--work-root", required=True)
    rehearse.add_argument("--course-code", default="MA103N")
    rehearse.add_argument("--as-of", default="2026-09-16")
    rehearse.add_argument(
        "--smoke-query",
        default="LU factorization triangular matrices",
    )
    rehearse.add_argument("--confirm", default="")

    verify = sub.add_parser("verify-report")
    verify.add_argument("--work-root", required=True)
    return parser


def _json_result(value):
    if hasattr(value, "__dict__"):
        value = value.__dict__
    return json.dumps(value, indent=2, ensure_ascii=False, default=list)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "preview":
            result = preview_restore_rehearsal(Path(args.recovery_root))
            print("PHASE 7.3 RESTORE REHEARSAL PREVIEW: PASS")
            print(_json_result(result))
            return 0

        if args.command == "verify-report":
            report = Path(args.work_root) / "phase7_restore_rehearsal_report.json"
            if not report.is_file() or report.is_symlink():
                raise RuntimeError("rehearsal report is missing or unsafe")
            value = json.loads(report.read_text(encoding="utf-8"))
            required = (
                value.get("status") == "pass"
                and value.get("retained_pair_unchanged") is True
                and value.get("backups_equivalent") is True
                and value.get("restore_performed_only_in_isolation") is True
                and value.get("production_or_live_source_accessed") is False
                and value.get("retirement_or_deletion_performed") is False
            )
            if not required:
                raise RuntimeError("rehearsal report does not satisfy Phase 7.3")
            print("PHASE 7.3 RESTORE REHEARSAL REPORT: PASS")
            print(_json_result(value))
            return 0

        if args.confirm != CONFIRMATION_PHRASE:
            print("PHASE 7.3 RESTORE REHEARSAL: BLOCKED", file=sys.stderr)
            print(
                "--confirm must equal {}".format(CONFIRMATION_PHRASE),
                file=sys.stderr,
            )
            return 2

        result = rehearse_recovery_pair(
            recovery_root=Path(args.recovery_root),
            project_root=Path(args.project_root).resolve(),
            work_root=Path(args.work_root),
            course_code=args.course_code,
            as_of=date.fromisoformat(args.as_of),
            smoke_query=args.smoke_query,
            confirmation=args.confirm,
        )
        print("PHASE 7.3 FULL RESTORE + REVERSE-RESTORE: PASS")
        print(
            _json_result(
                {
                    "status": result.status,
                    "output_name": result.output_directory.name,
                    "report": result.report_path.name,
                    "source_snapshot_identity_sha256": (
                        result.source_snapshot_identity_sha256
                    ),
                    "retained_pair_unchanged": (
                        result.retained_pair_unchanged
                    ),
                    "backups_equivalent": result.backups_equivalent,
                    "restore_performed_only_in_isolation": (
                        result.restore_performed_only_in_isolation
                    ),
                    "backup_A": result.backup_a.__dict__,
                    "backup_B": result.backup_b.__dict__,
                }
            )
        )
        return 0
    except Exception as error:
        print("PHASE 7.3 RESTORE REHEARSAL: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
