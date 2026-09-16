"""Phase 7.2 Recovery Bundle + Two Verified Backups CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from personal_learning_assistant.phase7.recovery_bundle import (
    CONFIRMATION_PHRASE,
    create_two_verified_backups,
    preview_recovery,
    verify_recovery_pair,
)


def _common(parser):
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--authority", default=".phase4_authority.json")
    parser.add_argument(
        "--source-root",
        action="append",
        default=[],
        metavar="KEY=PATH",
        help=(
            "Optional explicit root for registered local knowledge sources. "
            "Repeat for multiple roots."
        ),
    )


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 7.2 recovery pair operator"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview")
    _common(preview)

    create = sub.add_parser("create")
    _common(create)
    create.add_argument("--output", required=True)
    create.add_argument("--confirm", default="")

    verify = sub.add_parser("verify")
    verify.add_argument("--bundle-root", required=True)
    return parser


def _parse_roots(values):
    result = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError("--source-root must use KEY=PATH")
        key, path = raw.split("=", 1)
        key = key.strip().lower()
        path = path.strip()
        if not key or not path:
            raise ValueError("--source-root requires non-empty KEY and PATH")
        if key in result:
            raise ValueError("duplicate source-root key: {}".format(key))
        result[key] = Path(path)
    return result


def _git_identity(project_root: Path):
    def run(*args):
        proc = subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()

    try:
        return {
            "commit": run("rev-parse", "HEAD"),
            "branch": run("branch", "--show-current"),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "", "branch": ""}


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            result = verify_recovery_pair(Path(args.bundle_root))
            print("PHASE 7.2 RECOVERY PAIR VERIFICATION: PASS")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=list))
            return 0

        project_root = Path(args.project_root).resolve()
        roots = _parse_roots(args.source_root)
        git_identity = _git_identity(project_root)

        if args.command == "preview":
            result = preview_recovery(
                project_root=project_root,
                database_path=Path(args.database),
                authority_path=Path(args.authority),
                source_roots=roots,
                git_identity=git_identity,
            )
            print("PHASE 7.2 RECOVERY PREVIEW: PASS")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=list))
            return 0

        if args.confirm != CONFIRMATION_PHRASE:
            print("PHASE 7.2 RECOVERY CREATION: BLOCKED", file=sys.stderr)
            print(
                "--confirm must equal {}".format(CONFIRMATION_PHRASE),
                file=sys.stderr,
            )
            return 2

        result = create_two_verified_backups(
            project_root=project_root,
            database_path=Path(args.database),
            authority_path=Path(args.authority),
            output_root=Path(args.output),
            source_roots=roots,
            git_identity=git_identity,
            confirmation=args.confirm,
        )
        print("PHASE 7.2 TWO VERIFIED BACKUPS: PASS")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=list))
        return 0
    except Exception as error:
        print("PHASE 7.2 RECOVERY BUNDLE: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
