"""Shared fast-feedback coordinator for ANVAYA's four concurrent development streams.

This is NOT merge, Android-device, private-fixture or release certification.
Unknown and shared changes always retain the full-gate requirement.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from pathlib import Path

import smart_verify

ROOT = Path(__file__).resolve().parents[1]
STREAMS = ("performance_reader", "handwritten_media", "native_documents", "assessment_review")

# Test modules are intentionally scoped and fail-closed. The selector preserves
# modified test paths and also reports when full regression remains required.
BASE_SMOKES = {
    "performance_reader": ("tests/test_reader_v24.py", "tests/test_ui_v2_contract.py"),
    "handwritten_media": ("tests/test_learning_library_read_model.py",),
    "native_documents": ("tests/test_learning_library_routes.py",),
    "assessment_review": ("tests/test_assessment_pause_paper.py", "tests/test_assessment_studio_phase_e.py"),
}
NEW_SMOKES = {
    "performance_reader": ("tests/test_navigation_asset_cache.py", "tests/test_library_document_rename.py",
                           "tests/learning_studio/test_mobile_reader_delivery.py"),
    "handwritten_media": ("tests/test_notes_media_service.py", "tests/test_notes_media_routes.py",
                          "tests/test_notes_media_browser.py", "tests/test_notes_media_android.py"),
    "native_documents": ("tests/test_native_document_library.py", "tests/test_native_library_routes.py",
                         "tests/test_native_library_browser.py"),
    "assessment_review": ("tests/test_assessment_two_modes.py", "tests/test_assessment_studio_authoring_ux.py",
                          "tests/test_assessment_execution_candidate.py"),
}
# Use path-specific signals, not PR titles or branch names as coverage authority.
SIGNALS = {
    "performance_reader": ("performance", "navigation", "asset_cache", "reader", "fullscreen",
                           "library_rename", "display_repository", "learning_studio",
                           "learning_mobile", "learning_mapping"),
    "handwritten_media": ("notes_media", "media_intent", "media_request", "media_file_provider",
                          "media_handoff", "media_paths", "handwritten_media", "attachment"),
    "native_documents": ("native_document", "native_library", "document_extraction", "pdf_renderer",
                         "document_search", "inside_document"),
    "assessment_review": ("assessment", "cbt", "question_quality", "question_review",
                          "test_results", "rubric"),
}
# Shared bridges can affect every feature and MUST require authoritative
# cross-feature / Android gates even when scoped smoke tests pass.
SHARED = (
    "requirements*.txt", "pyproject.toml", "pytest.ini", "setup.cfg",
    ".github/workflows/**", "tests/conftest.py", "tests/**/conftest.py",
    "personal_learning_assistant/ui/web/__init__.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/android_runtime.py",
    "personal_learning_assistant/repositories/sqlite/migrations/**",
    "android/app/build.gradle", "android/app/src/main/AndroidManifest.xml",
    "android/app/src/main/java/**/MainActivity.java",
    "scripts/smart_verify.py", "scripts/verification_coordinator.py",
    "tests/test_smart_verify.py", "tests/test_verification_coordinator.py",
)


def classify(paths: list[str]) -> tuple[list[str], list[str]]:
    streams: set[str] = set()
    warnings: list[str] = []
    for raw in paths:
        path = raw.replace("\\", "/")
        if not path or path.startswith("/") or ".." in Path(path).parts:
            warnings.append("Untrusted changed path: " + path)
            continue
        if path.startswith("docs/") or path.endswith((".md", ".rst", ".png", ".jpg", ".svg")):
            continue
        lower = path.lower()
        if any(fnmatch.fnmatchcase(path, pat) for pat in SHARED):
            streams.update(STREAMS)
            warnings.append("Shared integration or verification boundary: " + path)
            continue
        matches = {name for name, terms in SIGNALS.items() if any(term in lower for term in terms)}
        # Generic UI, native Android, or unclassified implementations can
        # change all four experiences. Never turn them into a false green.
        if not matches and (path.startswith(("personal_learning_assistant/", "android/", "tests/", "scripts/"))
                            or path.endswith((".js", ".css", ".java", ".py", ".json", ".toml", ".yml", ".yaml"))):
            streams.update(STREAMS)
            warnings.append("Unknown cross-feature coverage: " + path)
        else:
            streams.update(matches)
    if not paths:
        warnings.append("Empty diff: cannot establish changed source")
    return sorted(streams), warnings


def select_tests(paths: list[str], streams: list[str], root: Path) -> tuple[list[str], list[str], list[str]]:
    python_tests: set[str] = set()
    js_tests: set[str] = set()
    warnings: list[str] = []
    for stream in streams:
        for p in BASE_SMOKES[stream]:
            if (root / p).is_file():
                python_tests.add(p)
            else:
                warnings.append("Missing required smoke: " + p)
        for p in NEW_SMOKES[stream]:
            if (root / p).is_file():
                python_tests.add(p)
    for raw in paths:
        path = raw.replace("\\", "/")
        if path.startswith("tests/") and path.endswith(".py"):
            if (root / path).is_file():
                python_tests.add(path)
            else:
                warnings.append("Deleted Python test: " + path)
        if path.startswith("tests/js/") and path.endswith(".test.cjs"):
            if (root / path).is_file():
                js_tests.add(path)
            else:
                warnings.append("Deleted JS test: " + path)
    # Existing JS contracts are Assessment-specific. Do not run the same
    # complete Node suite on a document-only or navigation-only edit.
    if "assessment_review" in streams:
        js_tests.update(p.relative_to(root).as_posix() for p in (root / "tests/js").glob("*.test.cjs"))
        if not js_tests:
            warnings.append("Missing assessment JavaScript contracts")
    return sorted(python_tests), sorted(js_tests), warnings


def plan(paths: list[str], root: Path = ROOT) -> dict:
    paths = sorted(set(p.replace("\\", "/") for p in paths))
    streams, warnings = classify(paths)
    pytests, jstests, missing = select_tests(paths, streams, root)
    existing = smart_verify.make_plan(paths, "fast", root)
    reasons = sorted(set(warnings + missing + existing.reasons))
    # A scoped green is NEVER a merge gate, even for a single known component.
    return {
        "schema": "anvaya.shared-verification.v2",
        "stage": "fast",
        "streams": streams,
        "changed": paths,
        "python_tests": pytests,
        "javascript_tests": jstests,
        "requires_full_regression": True,
        "requires_android_installed_acceptance": any(
            p.startswith("android/") or p.startswith("personal_learning_assistant/android_")
            for p in paths),
        "reasons": reasons,
        "selector_requires_full": existing.requires_full,
        "outcome": "PENDING",
    }


def run(command: list[str], cwd: Path) -> int:
    print("RUN:", " ".join(command), flush=True)
    return subprocess.call(command, cwd=cwd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Exact PR base SHA")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--json", default="shared-verification.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = args.changed_file or smart_verify.changed_paths(args.base, args.head)
        head_sha = subprocess.check_output(["git", "rev-parse", args.head], cwd=ROOT, text=True).strip()
        data = plan(paths)
        data.update(source_sha=head_sha, base_sha=args.base, started_tests=False)
        exit_code = 0
        start = time.monotonic()
        if not paths:
            exit_code = 2
            data["outcome"] = "FAIL_EMPTY_DIFF"
        elif args.execute:
            data["started_tests"] = True
            commands = [
                [sys.executable, "-m", "pytest", "-q", *data["python_tests"], "--junitxml=shared-fast.xml"]
                if data["python_tests"] else ["git", "diff", "--check"],
            ]
            if data["javascript_tests"]:
                commands.append(["node", "--test", *data["javascript_tests"]])
            for command in commands:
                code = run(command, ROOT)
                if code:
                    exit_code = code
                    break
            data["outcome"] = "FAST_PASS_ONLY" if exit_code == 0 else "FAST_FAIL"
        else:
            data["outcome"] = "PLAN_ONLY"
        data.update(exit_code=exit_code, elapsed_seconds=round(time.monotonic() - start, 2))
    except (ValueError, subprocess.CalledProcessError, OSError) as exc:
        data = {"schema": "anvaya.shared-verification.v2", "stage": "fast",
                "outcome": "FAIL_CLOSED", "error": str(exc),
                "requires_full_regression": True}
        exit_code = 2
    Path(args.json).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
