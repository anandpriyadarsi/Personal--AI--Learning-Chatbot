"""Phase 7.4 Legacy Usage Observation / Consumer Watch CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from personal_learning_assistant.phase7.consumer_watch import (
    build_observation_report,
    preview_consumer_watch,
    render_observation_markdown,
    run_observed_script,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 7.4 privacy-minimal legacy consumer observation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("--project-root", default=".")

    run = sub.add_parser("run")
    run.add_argument("--project-root", default=".")
    run.add_argument("--observation-root", required=True)
    run.add_argument("--script", required=True)
    run.add_argument(
        "--script-arg",
        action="append",
        default=[],
        help="Optional argument passed to the observed project script. Values are not logged.",
    )

    report = sub.add_parser("report")
    report.add_argument("--project-root", default=".")
    report.add_argument("--observation-root", required=True)
    report.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
    )
    report.add_argument("--output")
    return parser


def _emit(value, *, output=None, markdown=False):
    text = (
        render_observation_markdown(value)
        if markdown
        else json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=list,
        )
    )
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            text + ("" if text.endswith("\n") else "\n"),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print(text)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "preview":
            result = preview_consumer_watch(Path(args.project_root))
            print("PHASE 7.4 CONSUMER WATCH PREVIEW: PASS")
            _emit(result)
            return 0

        if args.command == "run":
            result = run_observed_script(
                project_root=Path(args.project_root),
                observation_root=Path(args.observation_root),
                script_path=Path(args.script),
                script_args=tuple(args.script_arg),
            )
            print("")
            print("PHASE 7.4 OBSERVED SESSION: PASS")
            _emit(
                {
                    "session_id": result.session_id,
                    "state": result.state,
                    "unique_event_count": result.unique_event_count,
                    "observed_component_count": (
                        result.observed_component_count
                    ),
                    "exit_code": result.exit_code,
                    "event_stream_sha256": result.event_stream_sha256,
                }
            )
            return int(result.exit_code)

        report = build_observation_report(
            project_root=Path(args.project_root),
            observation_root=Path(args.observation_root),
        )
        print("PHASE 7.4 CONSUMER WATCH REPORT: PASS")
        _emit(
            report,
            output=args.output,
            markdown=args.format == "markdown",
        )
        return 0
    except Exception as error:
        print("PHASE 7.4 CONSUMER WATCH: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
