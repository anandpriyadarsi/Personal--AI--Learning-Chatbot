"""Conservative, explainable ANVAYA change-aware test selection.

Fast feedback is never a replacement for cross-platform full regression.
Unknown/shared changes require the existing architecture validation workflow.
No personal fixtures, provider credentials or network services are accessed.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

# These files affect unrelated areas or the test environment. Never certify a
# scoped selection as sufficient when they change.
CRITICAL = (
    "requirements*.txt", "pytest.ini", "pyproject.toml", "setup.cfg",
    ".github/workflows/**", "tests/conftest.py", "tests/**/conftest.py",
    "tests/fixtures/**", "personal_learning_assistant/repositories/sqlite/migrations/**",
    "personal_learning_assistant/repositories/sqlite/connection.py",
    "personal_learning_assistant/repositories/sqlite/migration_runner.py",
    "scripts/architecture_validation.py", "scripts/validation_guard/**",
)
IGNORED = ("docs/**", "*.md", "*.rst", ".gitignore", "LICENSE", "*.png", "*.jpg", "*.svg")

# Patterns are deliberately conservative. Cross-component changes union all
# applicable suites; unclassified application paths require full regression.
SOURCES = {
    "tutor": ("personal_learning_assistant/tutor/**", "personal_learning_assistant/**/tutor_*.py",
              "personal_learning_assistant/**/grounded_tutor*.py", "personal_learning_assistant/**/learning_tutor_*.py"),
    "learning": ("personal_learning_assistant/learning_studio/**", "personal_learning_assistant/**/learning_*.py",
                 "personal_learning_assistant/**/note_draft*.py"),
    "assessment": ("personal_learning_assistant/**/assessment_*.py", "personal_learning_assistant/**/attempt_performance*.py"),
    "library": ("personal_learning_assistant/**/notes_*.py", "personal_learning_assistant/**/anvaya_notes*.py",
                "personal_learning_assistant/**/resources2_*.py", "personal_learning_assistant/**/retrieval_*.py",
                "personal_learning_assistant/retrieval/**"),
    "planning": ("personal_learning_assistant/**/planning_*.py", "personal_learning_assistant/**/planner_*.py",
                 "personal_learning_assistant/**/daily_agenda*.py", "personal_learning_assistant/**/study_plan*.py"),
    "ui": ("personal_learning_assistant/ui/web/**",),
    "verification": ("scripts/smart_verify.py", "tests/test_smart_verify.py"),
}
# Unit focused selection avoids the browser by default; browser coverage is
# included in the focused gate. Directly modified test files always run.
TESTS = {
    "tutor": ("tests/test_*tutor*.py", "tests/test_phase6_grounded*.py", "tests/learning_studio/test_*tutor*.py"),
    "learning": ("tests/learning_studio/test_*.py", "tests/test_learning_*.py", "tests/test_reader_v24.py",
                 "tests/test_reviewed_conversion_v24.py", "tests/test_note_draft_v24.py"),
    "assessment": ("tests/test_*assessment*.py", "tests/test_*topic_read_safety*.py"),
    "library": ("tests/test_*library*.py", "tests/test_*notes*.py", "tests/test_*resource*.py"),
    "planning": ("tests/test_*planning*.py", "tests/test_*planner*.py"),
    "ui": ("tests/test_ui_v2*.py", "tests/test_*browser.py"),
    "verification": ("tests/test_smart_verify.py",),
}
# One or two representative modules per area give early feedback; no cap on
# focused scope. These all exist on the V2.4 main baseline.
SMOKE = {
    "tutor": ("tests/test_tutor_grounding_v24.py", "tests/test_phase6_grounded_tutor_engine.py"),
    "learning": ("tests/test_learning_intelligence_v24.py", "tests/test_reader_v24.py"),
    "assessment": ("tests/test_assessment_pause_paper.py", "tests/test_assessment_studio_phase_e.py"),
    "library": ("tests/test_learning_library_read_model.py", "tests/test_learning_library_routes.py"),
    "planning": ("tests/test_architecture_planning_context.py", "tests/test_planning_v2_proposals.py"),
    "ui": ("tests/test_ui_v2_contract.py",),
    "verification": ("tests/test_smart_verify.py",),
}


def matching(path: str, patterns: Iterable[str]) -> bool:
    """Match slash-normalized paths; ** matches across nested directories."""
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def changed_paths(base: str, head: str, cwd: Path = ROOT) -> list[str]:
    if not base or not head:
        raise ValueError("Both base and head must be supplied; cannot guess a diff")
    command = ["git", "diff", "--name-only", "--diff-filter=ACMRD", "-z", f"{base}...{head}"]
    result = subprocess.run(command, cwd=cwd, capture_output=True, check=True)
    return sorted({p.decode("utf-8").replace("\\", "/") for p in result.stdout.split(b"\0") if p})


@dataclass
class Plan:
    mode: str
    changed: list[str]
    areas: list[str]
    selected: list[str]
    requires_full: bool
    reasons: list[str]
    status: str


def make_plan(files: Iterable[str], mode: str, root: Path = ROOT) -> Plan:
    if mode not in {"fast", "focused", "full"}:
        raise ValueError("Unsupported mode")
    changed = sorted(set(p.replace("\\", "/") for p in files))
    areas: set[str] = set()
    reasons: list[str] = []
    direct: set[str] = set()
    for path in changed:
        if path.startswith("/") or ".." in Path(path).parts:
            reasons.append(f"Unsafe path: {path}")
            continue
        if matching(path, CRITICAL):
            reasons.append(f"Shared or security-critical file: {path}")
        if path.startswith("tests/") and path.endswith(".py"):
            if (root / path).is_file():
                direct.add(path)
            # Changed tests need their related area, even if the implementation
            # file is unchanged. Existing regression modules can touch anything.
            categories = {area for area, patterns in TESTS.items() if matching(path, patterns)}
            if categories:
                areas.update(categories)
            elif path != "tests/test_smart_verify.py":
                reasons.append(f"Unmapped test module: {path}")
            continue
        if matching(path, IGNORED):
            continue
        found = {area for area, patterns in SOURCES.items() if matching(path, patterns)}
        if found:
            areas.update(found)
        elif path.endswith((".py", ".js", ".cjs", ".html", ".css", ".sql")) or path.startswith(("scripts/", ".github/", "personal_learning_assistant/")):
            reasons.append(f"Unmapped implementation/infrastructure: {path}")
    # Never allow an empty diff to be treated as coverage evidence.
    if not changed:
        reasons.append("No changed files supplied")
    requires_full = bool(reasons) or mode == "full"
    if mode == "full":
        selected = sorted(p.relative_to(root).as_posix() for p in (root / "tests").rglob("test_*.py"))
    else:
        chosen = set(direct)
        for area in areas:
            if mode == "fast":
                chosen.update(p for p in SMOKE[area] if (root / p).is_file())
            else:
                chosen.update(p.relative_to(root).as_posix() for p in (root / "tests").rglob("test_*.py")
                              if matching(p.relative_to(root).as_posix(), TESTS[area]))
        selected = sorted(p for p in chosen if (root / p).is_file())
    status = ("FULL_REQUIRED" if requires_full and mode != "full" else
              "DOCS_ONLY" if not selected and not requires_full else "SELECTED")
    return Plan(mode, changed, sorted(areas), selected, requires_full, reasons, status)


def execute(plan: Plan, root: Path, xml: str) -> int:
    if plan.mode == "full":
        # A full invocation is explicit and never hides missing tests.
        selected = ["tests"]
    elif plan.mode == "focused" and plan.requires_full:
        print("Focused coverage is insufficient; run the authoritative full gate.", file=sys.stderr)
        return 2
    else:
        selected = plan.selected
    if not selected:
        print("No test modules selected; running source whitespace check only.")
        return subprocess.call(["git", "diff", "--check"], cwd=root)
    command = [sys.executable, "-m", "pytest", "-q", *selected, f"--junitxml={xml}"]
    print("Executing", len(selected), "test module(s):", " ".join(command), flush=True)
    return subprocess.call(command, cwd=root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fast", "focused", "full"), default="fast")
    parser.add_argument("--base", help="PR base commit SHA; required without --changed-file")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[], help="Explicit path for local selection")
    parser.add_argument("--json", default="smart-verification.json", help="Write selection and actual result")
    parser.add_argument("--execute", action="store_true", help="Actually execute selected tests")
    args = parser.parse_args(argv)
    try:
        paths = args.changed_file or changed_paths(args.base, args.head)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Cannot establish changes safely: {exc}", file=sys.stderr)
        return 2
    plan = make_plan(paths, args.mode)
    report = {**asdict(plan), "head": args.head, "base": args.base, "executed": False}
    print(json.dumps(report, indent=2))
    status = 0
    if args.execute:
        start = time.monotonic()
        xml = "smart-verification.xml"
        status = execute(plan, ROOT, xml)
        report.update(executed=bool(plan.selected or args.mode == "full"), exit_code=status,
                      elapsed_seconds=round(time.monotonic() - start, 2), junit=xml if (ROOT / xml).is_file() else None)
    Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
