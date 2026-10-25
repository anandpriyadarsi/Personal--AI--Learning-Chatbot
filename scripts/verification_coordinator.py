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
import os
import re
import concurrent.futures
import xml.etree.ElementTree as ET
from pathlib import Path

import smart_verify
from verification_evidence import identity, diagnose

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
                           "tests/learning_studio/test_reader_payload_performance.py"),
    "handwritten_media": ("tests/test_notes_media.py", "tests/test_notes_media_android_contract.py"),
    "native_documents": ("tests/test_native_document_library.py", "tests/test_native_library_routes.py"),
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
        lower = path.lower()
        if path.startswith("docs/"):
            continue
        # The Assessment authoring instructions are tracked Markdown but are
        # executable educational policy, not ordinary documentation.
        if lower.endswith((".md", ".rst")):
            if "assessment" in lower and ("prompt" in lower or "question" in lower):
                streams.add("assessment_review")
                warnings.append("Academic question-authoring policy changed: " + path)
            continue
        if lower.endswith((".png", ".jpg", ".svg")):
            continue
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


def plan(paths: list[str], root: Path = ROOT, stage: str = 'fast') -> dict:
    paths = sorted(set(p.replace("\\", "/") for p in paths))
    streams, warnings = classify(paths)
    pytests, jstests, missing = select_tests(paths, streams, root)
    existing = smart_verify.make_plan(paths, "fast", root)
    reasons = sorted(set(warnings + missing + existing.reasons))
    graph = smart_verify.make_v2_plan(paths, stage, root)
    # Keep V2's original stream labels for compatible downstream reports. The
    # graph's components, rather than those labels, now govern test execution.
    return {
        "schema": "anvaya.shared-verification.v2",
        **graph,
        "streams": streams,
        "changed": paths,
        "python_tests": sorted(set(pytests) | set(graph['python_tests'])),
        "javascript_tests": sorted(set(jstests) | set(graph['javascript_tests'])),
        "requires_full_regression": True,
        "requires_android_installed_acceptance": any(
            p.startswith("android/") or p.startswith("personal_learning_assistant/android_")
            for p in paths),
        "reasons": sorted(set(reasons + graph['reasons'])),
        "selector_requires_full": existing.requires_full,
        "outcome": graph['outcome'],
    }


def run_check(command: list[str], cwd: Path, name: str, output: Path) -> dict:
    print("RUN:", " ".join(command), flush=True)
    start = time.monotonic()
    # Never pass private academic fixture paths/provider secrets into a public
    # development verifier. Private acceptance uses its existing protected job.
    env = {k:v for k,v in os.environ.items() if not k.startswith(('ANVAYA_', 'OPENAI_', 'ANTHROPIC_'))}
    env.update(PYTHONDONTWRITEBYTECODE='1', ANVAYA_BROWSER_TESTS=os.environ.get('ANVAYA_BROWSER_TESTS','0'))
    log = output / (name + '.log')
    try:
        with log.open('w',encoding='utf-8') as stream:
            result = subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1200)
        code = result.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write_text(type(exc).__name__+': command unavailable or timed out',encoding='utf-8')
        code = 2
    report = {'name':name,'command':command,'exit_code':code,
              'duration_seconds':round(time.monotonic()-start,3),'log':str(log)}
    if code:
        report['diagnosis'] = diagnose(command,code,log.read_text(encoding='utf-8',errors='replace'))
    return report


def execute(data: dict, root: Path, output: Path, workers: int = 4) -> int:
    output.mkdir(parents=True,exist_ok=True)
    if data['blockers']:
        data['outcome'] = 'BLOCKED'
        return 2
    xml = output/'python.xml'
    commands = [('syntax', [sys.executable,'-m','compileall','-q','personal_learning_assistant','scripts']),
                ('whitespace', ['git','diff','--check'])]
    for index,path in enumerate(data.get('changed',[])):
        if path.endswith(('.js','.cjs','.mjs')) and not path.startswith('/') and '..' not in Path(path).parts and (root/path).is_file():
            commands.append(('javascript-syntax-'+str(index),['node','--check',path]))
    if data['python_tests']:
        commands.append(('python',[sys.executable,'-m','pytest','-q',*data['python_tests'],'--junitxml='+str(xml.resolve())]))
    if data['javascript_tests']:
        commands.append(('javascript',['node','--test','--test-reporter=tap',*data['javascript_tests']]))
    data['started_tests'] = bool(data['python_tests'] or data['javascript_tests'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_check,argv,root,name,output) for name,argv in commands]
        data['checks'] = [future.result() for future in futures]
    code = max((r['exit_code'] != 0 for r in data['checks']),default=False)
    if data['javascript_tests']:
        log = (output/'javascript.log').read_text(encoding='utf-8',errors='replace')
        counts = {name:int(value) for name,value in re.findall(
            r'^# (tests|pass|fail|cancelled|skipped|todo) (\d+)\s*$',log,re.MULTILINE)}
        data['javascript_results'] = counts or {'inventory':'MISSING'}
        file_names = {p for path in data['javascript_tests'] for p in (path, Path(path).name, str((root/path).resolve()))}
        empty_files = set(re.findall(r'^# Subtest: (.+)$',log,re.MULTILINE)) & file_names
        if (not counts.get('tests') or counts.get('pass') != counts.get('tests')
                or empty_files or any(counts.get(k,1) != 0 for k in ('fail','cancelled','skipped','todo'))):
            data['blockers'].append('JavaScript contracts missing, failed, skipped, cancelled or TODO')
    if data['python_tests']:
        if not xml.is_file():
            data['blockers'].append('Missing Python JUnit evidence')
        else:
            cases = ET.parse(xml).findall('.//testcase')
            skipped = [c.get('classname','')+'::'+c.get('name','') for c in cases if c.find('skipped') is not None]
            data['test_results'] = {'cases':len(cases),'skips':skipped,
                                    'failures':sum(c.find('failure') is not None or c.find('error') is not None for c in cases)}
            # The canonical validator alone owns its four named private skips.
            # Scoped execution accepts no skipped test as successful coverage.
            if skipped or not cases:
                data['blockers'].append('Selected tests were skipped or no cases executed; use canonical acceptance for private fixture omissions')
    data['outcome'] = 'FAIL' if code else 'BLOCKED' if data['blockers'] else (
        'FAST FEEDBACK PASS — NOT RELEASE CERTIFICATION' if data['stage'] == 'fast' else 'FEATURE PASS — NOT RELEASE CERTIFICATION')
    return 1 if code else 2 if data['blockers'] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Exact PR base SHA")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--json", default="shared-verification.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument('--stage', choices=('fast','feature'), default='fast')
    parser.add_argument('--output', default='verification-results')
    parser.add_argument('--workers', type=int, choices=(1,4), default=4,
                        help='1 is the sequential reference for equivalent-scope benchmarks')
    args = parser.parse_args(argv)
    try:
        diff_error = None
        try:
            paths = args.changed_file or smart_verify.changed_paths(args.base, args.head)
        except (ValueError, subprocess.CalledProcessError, OSError) as exc:
            paths = ['__unreliable_git_diff__']
            diff_error = type(exc).__name__ + ': cannot establish diff; broad validation required'
        head_sha = subprocess.check_output(["git", "rev-parse", args.head], cwd=ROOT, text=True).strip()
        actual_sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        data = plan(paths, stage=args.stage)
        data.update(source_sha=head_sha, base_sha=args.base, started_tests=False)
        if head_sha != actual_sha:
            data['blockers'].append('Requested head differs from checked-out source')
        if diff_error:
            data['reasons'].append(diff_error)
            data['blockers'].append('Diff unreliable: canonical full acceptance required')
        data['identity'] = identity(ROOT, data)
        data['run_id'] = os.environ.get('GITHUB_RUN_ID')
        data['run_attempt'] = os.environ.get('GITHUB_RUN_ATTEMPT')
        data['workflow_ref'] = os.environ.get('GITHUB_WORKFLOW_REF')
        data['limitations'] = ['Not release certification', 'Android installed/device and private fixtures NOT VERIFIED',
                              'Remote evidence reuse disabled pending authenticated immutable artifact verification']
        exit_code = 0
        start = time.monotonic()
        if not paths:
            exit_code = 2
            data["outcome"] = "FAIL_EMPTY_DIFF"
        elif args.execute:
            exit_code = execute(data, ROOT, Path(args.output), args.workers)
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
