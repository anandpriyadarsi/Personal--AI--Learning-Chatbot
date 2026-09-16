"""Phase 7.1 Canonical Runtime + Consumer Inventory CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from personal_learning_assistant.phase7.runtime_inventory import (
    build_inventory,
    render_markdown,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 7.1 static canonical-runtime/legacy-consumer inventory"
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print("PHASE 7.1 CANONICAL RUNTIME INVENTORY: BLOCKED", file=sys.stderr)
        print("project root does not exist", file=sys.stderr)
        return 1

    try:
        report = build_inventory(root)
        text = (
            json.dumps(report, indent=2, ensure_ascii=False)
            if args.format == "json"
            else render_markdown(report)
        )
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
        else:
            print(text)
        print(
            "PHASE 7.1 CANONICAL RUNTIME INVENTORY: PASS",
            file=sys.stderr if args.output else sys.stdout,
        )
        return 0
    except Exception as error:
        print("PHASE 7.1 CANONICAL RUNTIME INVENTORY: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
