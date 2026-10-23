"""Compare genuine GitHub Actions CI job snapshots without inventing speedups.

Inputs must be JSON responses from GET /repos/{owner}/{repo}/actions/runs/{id}/jobs.
A comparison is observational, NOT proof that a code change caused a difference.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

GROUPS = {
    "architecture": {
        "names": ("Synthetic development (ubuntu-latest)", "Synthetic development (windows-latest)",
                  "Cross-platform development acceptance"),
        "step": "Full validator (no deselections)",
    },
    "ui": {
        "names": ("UI V2 (ubuntu-latest)", "UI V2 (windows-latest)"),
        "step": "Full regression suite",
    },
}
FAST_NAME = "Change-aware Python and JavaScript smoke"


class InvalidEvidence(ValueError):
    """Evidence is missing, ambiguous, incomplete, or failed."""


def timestamp(value: str | None) -> datetime:
    if not isinstance(value, str) or not value:
        raise InvalidEvidence("Missing timestamp in GitHub Actions evidence")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidEvidence("Invalid timestamp") from exc
    if dt.tzinfo is None:
        raise InvalidEvidence("Timestamps must include time zone")
    return dt.astimezone(timezone.utc)


def seconds(start: str, end: str) -> int:
    delta = int((timestamp(end) - timestamp(start)).total_seconds())
    if delta < 0:
        raise InvalidEvidence("Negative duration")
    return delta


def inspect(jobs_response: dict, group: str) -> dict:
    """Only compare fully completed, passing and uniquely identified jobs."""
    jobs = jobs_response.get("jobs") if isinstance(jobs_response, dict) else None
    if not isinstance(jobs, list):
        raise InvalidEvidence("Expected a GitHub Actions jobs API JSON object")
    if group == "fast":
        names, step_name = (FAST_NAME,), "Change-aware fast feedback (not merge acceptance)"
    elif group in GROUPS:
        names = GROUPS[group]["names"]
        step_name = GROUPS[group]["step"]
    else:
        raise InvalidEvidence("Unknown workflow group")

    chosen = []
    for name in names:
        matches = [j for j in jobs if j.get("name") == name]
        if len(matches) != 1:
            raise InvalidEvidence(f"Expected exactly one job named {name!r}, got {len(matches)}")
        job = matches[0]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise InvalidEvidence(f"Job not successfully completed: {name}")
        chosen.append(job)
    overall_start = min(timestamp(j["started_at"]) for j in chosen)
    overall_end = max(timestamp(j["completed_at"]) for j in chosen)
    if overall_end < overall_start:
        raise InvalidEvidence("Invalid workflow time range")

    details = []
    for job in chosen:
        steps = [s for s in job.get("steps", []) if s.get("name") == step_name]
        if len(steps) > 1:
            raise InvalidEvidence(f"Duplicated named step in {job['name']}")
        if group == "architecture" and job["name"].startswith("Cross-platform"):
            step_status = "not-applicable"
            step_duration = None
        elif not steps:
            raise InvalidEvidence(f"Missing step {step_name!r} in {job['name']}")
        else:
            step = steps[0]
            step_status = step.get("conclusion")
            if step_status not in {"success", "skipped"}:
                raise InvalidEvidence(f"Unexpected step result in {job['name']}: {step_status}")
            step_duration = (seconds(step["started_at"], step["completed_at"])
                             if step_status == "success" else None)
        details.append({
            "name": job["name"],
            "job_seconds": seconds(job["started_at"], job["completed_at"]),
            "target_step": step_name,
            "target_step_result": step_status,
            "target_step_seconds": step_duration,
        })
    return {
        "group": group,
        "wall_seconds": int((overall_end - overall_start).total_seconds()),
        "started_at": overall_start.isoformat(),
        "completed_at": overall_end.isoformat(),
        "jobs": details,
    }


def comparison(before: dict, after: dict, *, before_run: str, after_run: str) -> dict:
    if before["group"] != after["group"]:
        raise InvalidEvidence("Cannot compare different workflow groups")
    duration_delta = after["wall_seconds"] - before["wall_seconds"]
    saved = -duration_delta
    pct = (saved / before["wall_seconds"] * 100) if before["wall_seconds"] else 0
    return {
        "group": before["group"],
        "baseline_run": before_run,
        "candidate_run": after_run,
        "baseline": before,
        "candidate": after,
        "change_seconds": duration_delta,
        "time_saved_seconds": saved,
        "relative_change_percent": round(pct, 1),
        "claim": "OBSERVATIONAL_ONLY_DIFFERENT_COMMITS_AND_RUNNER_CONDITIONS",
        "privacy": "CI metadata only; excludes student data, token values and raw logs",
        "warning": "Do not interpret time_saved_seconds as a causal or guaranteed optimization.",
    }


def markdown(result: dict) -> str:
    before = result["baseline"]
    after = result["candidate"]
    def mins(sec):
        return f"{sec // 60}m {sec % 60}s"
    lines = [
        "# ANVAYA Smart Verification timing evidence",
        "",
        "This is observational evidence from **successfully completed GitHub Actions runs**.",
        "It does not prove causation, guarantee future runtimes, or replace regression acceptance.",
        "",
        f"- Workflow group: **{result['group']}**",
        f"- Before: {result['baseline_run']} — {mins(before['wall_seconds'])}",
        f"- After: {result['candidate_run']} — {mins(after['wall_seconds'])}",
        f"- Change (after minus before): **{result['change_seconds']} seconds**",
        f"- Positive savings means faster: **{result['time_saved_seconds']} seconds**",
        "",
        "| Job | Before | After | Target-step before | Target-step after |",
        "| --- | --- | --- | --- | --- |",
    ]
    for old, new in zip(before["jobs"], after["jobs"]):
        def step(j):
            duration = j["target_step_seconds"]
            return (mins(duration) if duration is not None
                    else j["target_step_result"])
        lines.append(f"| {old['name']} | {mins(old['job_seconds'])} | "
                     f"{mins(new['job_seconds'])} | {step(old)} | {step(new)} |")
    lines += [
        "",
        "Important: comparisons involve different commits, workflows and runner conditions.",
        "The authoritative full cross-platform acceptance remains mandatory for merging.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True, help="GitHub Actions jobs API response")
    parser.add_argument("--after", type=Path, required=True, help="GitHub Actions jobs API response")
    parser.add_argument("--group", choices=(*GROUPS, "fast"), required=True)
    parser.add_argument("--before-run", required=True, help="Immutable GitHub Actions run URL")
    parser.add_argument("--after-run", required=True, help="Immutable GitHub Actions run URL")
    parser.add_argument("--output", type=Path, default=Path("verification-benchmark.json"))
    parser.add_argument("--markdown", type=Path, default=Path("verification-benchmark.md"))
    args = parser.parse_args(argv)
    try:
        before = inspect(json.loads(args.before.read_text(encoding="utf-8")), args.group)
        after = inspect(json.loads(args.after.read_text(encoding="utf-8")), args.group)
        result = comparison(before, after, before_run=args.before_run, after_run=args.after_run)
    except (InvalidEvidence, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Benchmark evidence REJECTED: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(result), encoding="utf-8")
    print(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
