"""Current Gate A development validation. Never launch a production application.

python scripts/architecture_validation.py --output <outside-repository-directory>
Repeat runs retain earlier evidence in distinct owned run directories.
Install tracked requirements and fresh Chromium before invoking this command.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.architecture_private_fixtures import FIXTURES, PrivateFixtureStage, private_temporary_directory, redact, validate_pair

EXTERNAL_TEST_IDS = {
    ('tests.learning_studio.test_browser', 'test_external_recovered_pilot_real_browser'),
    ('tests.learning_studio.test_pilot', 'test_external_bad_v3_source_is_rejected'),
    ('tests.learning_studio.test_recovered_pilot', 'test_external_recovered_pilot_strict_import_and_durable_evidence'),
    ('tests.learning_studio.test_recovered_pilot', 'test_external_pilot_demo_does_not_fabricate_course_mappings'),
}
MARKER = '.anvaya-validation-output.json'
PURPOSE = {'schema': 'anvaya.synthetic-validation-output', 'version': 1}


def prepare_output(output: Path, repo: Path) -> Path:
    output = output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('Output and parents must not be symlinks')
    output, repo = output.resolve(), repo.resolve()
    if output == repo or output.is_relative_to(repo) or repo.is_relative_to(output):
        raise ValueError('Output must be outside and separate from the source repository')
    if output.exists():
        marker = output / MARKER
        if not output.is_dir() or not marker.is_file() or marker.is_symlink():
            raise ValueError('Existing output must be owned by this validator')
        if json.loads(marker.read_text(encoding='utf-8')) != PURPOSE:
            raise ValueError('Ambiguous output ownership')
    else:
        output.mkdir(parents=True)
        (output / MARKER).write_text(json.dumps(PURPOSE), encoding='utf-8')
    return Path(tempfile.mkdtemp(prefix='run-', dir=output))


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def require_clean_source(repo: Path) -> None:
    if _git(repo, 'status', '--porcelain=v1', '-uall'):
        raise ValueError('Committed CI source checkout must be clean')


def export_source(repo: Path, target: Path) -> dict:
    """Only Git's tracked/staged inventory; never copy untracked user files.

    Stage explicitly reviewed new feature files before precommit validation.
    Working bytes and dirtiness are hashed so unstaged edits are visible.
    """
    names = set(_git(repo, 'ls-files', '-z').split('\0')) - {''}
    target.mkdir()
    hashes = {}
    for name in sorted(names):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe tracked source path')
        if relative.parts[0] in {'data', '.phase5_retrieval', '.git', '.venv'} or relative.name in {'.env', '.phase4_authority.json'} or relative.name.startswith('.env.'):
            continue
        source = repo / relative
        if any(p.is_symlink() for p in (source, *source.parents) if p != repo.parent):
            raise ValueError('Source export refuses symlinks')
        if not source.is_file():
            raise ValueError('Tracked source is missing: ' + name)
        content = source.read_bytes()
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    # A clean source snapshot gives Git-dependent architecture tests a real tree.
    subprocess.run(['git', 'init', str(target)], check=True, capture_output=True)
    info = target / '.git/info/attributes'
    info.write_text('backup.py -text\ndashboard.py -text\n', encoding='utf-8')
    # Auto-maintenance may outlive commit and mutate .git during read audits or
    # Windows cleanup. Disable it only for this disposable snapshot preparation.
    snapshot_git = ['git', '-C', str(target), '-c', 'gc.auto=0', '-c', 'maintenance.auto=false']
    subprocess.run([*snapshot_git, 'add', '.'], check=True, capture_output=True)
    subprocess.run([*snapshot_git, '-c', 'user.name=Synthetic validator',
                    '-c', 'user.email=synthetic@example.invalid', 'commit', '-m', 'Disposable source snapshot'], check=True, capture_output=True)
    return {'sha': _git(repo, 'rev-parse', 'HEAD'), 'branch': _git(repo, 'branch', '--show-current'),
            'dirty': bool(_git(repo, 'status', '--porcelain=v1', '-uall')),
            'snapshot_sha': _git(target, 'rev-parse', 'HEAD'), 'files': hashes,
            'snapshot_fingerprint': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def test_status(exit_code: int, xml: Path, *, allow_external_skips: bool = False) -> dict:
    result = {'status': 'FAIL' if exit_code else 'BLOCKED', 'exit_code': exit_code,
              'tests': 0, 'failures': [], 'errors': [], 'skips': []}
    if xml.exists():
        tree = ET.parse(xml)
        cases = tree.findall('.//testcase')
        result['tests'] = len(cases)
        for case in cases:
            name = case.get('classname', '') + '::' + case.get('name', '')
            for tag, field in [('failure', 'failures'), ('error', 'errors'), ('skipped', 'skips')]:
                element = case.find(tag)
                if element is not None:
                    result[field].append({'id': name, 'message': element.get('message', '')})
        approved = {'::'.join(parts) for parts in EXTERNAL_TEST_IDS} if allow_external_skips else set()
        result['unexpected_skips'] = [s for s in result['skips'] if s['id'] not in approved]
        if exit_code or result['failures'] or result['errors']:
            result['status'] = 'FAIL'
        elif result['unexpected_skips']:
            # Preserve the original harness contract: an ordinary omitted
            # test is BLOCKED, never passed. Public full-suite validation
            # treats any non-approved skip as a hard merge-gate failure.
            result['status'] = 'FAIL' if allow_external_skips else 'BLOCKED'
        elif cases:
            result['status'] = 'PASS'
    return result


def development_gate_status(categories: dict, *, private_fixtures: bool = False) -> str:
    """Allow ONLY explicitly recorded private skips in public synthetic CI.

    A genuine failure, an unexpected skip, a missing original test identity, or
    a failed runnable category still rejects the development gate. Private
    certification is stricter: every original IKS case must actually pass.
    """
    pilot = categories.get('external_pilots', {})
    outcomes = pilot.get('outcomes', {})
    expected = {'::'.join(identity) for identity in EXTERNAL_TEST_IDS}
    if set(outcomes) != expected or any(value not in ('PASS', 'SKIP') for value in outcomes.values()):
        return 'FAIL'
    if private_fixtures and pilot.get('status') != 'PASS':
        return 'FAIL'
    tested = {name: result for name, result in categories.items() if name != 'external_pilots'}
    return 'PASS' if tested and all(result.get('status') == 'PASS' for result in tested.values()) else 'FAIL'


def external_pilot_acceptance(xml: Path) -> dict:
    outcomes = {'::'.join(identity): 'NOT_RUN' for identity in sorted(EXTERNAL_TEST_IDS)}
    if xml.exists():
        for case in ET.parse(xml).findall('.//testcase'):
            identity = (case.get('classname', ''), case.get('name', ''))
            key = '::'.join(identity)
            if identity not in EXTERNAL_TEST_IDS:
                continue
            if outcomes[key] != 'NOT_RUN':
                outcomes[key] = 'DUPLICATE'
            else:
                outcomes[key] = ('FAIL' if case.find('failure') is not None or case.find('error') is not None
                                 else 'SKIP' if case.find('skipped') is not None else 'PASS')
    values = set(outcomes.values())
    status = 'FAIL' if values & {'FAIL', 'DUPLICATE'} else 'PASS' if values == {'PASS'} else 'BLOCKED'
    return {'status': status, 'outcomes': outcomes, 'scope': 'This platform only; installed authority remains BLOCKED'}


def write_summary(directory: Path, report: dict) -> None:
    (directory / 'VALIDATION_SUMMARY.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# ANVAYA automated validation', '',
             f"Source: `{report['source'].get('sha', 'unavailable')}`. Synthetic development validation; production authority is separate.", '',
             'Re-run the whole validator from the feature checkout with its installed test interpreter:',
             '`python scripts/architecture_validation.py --output <new-or-validator-owned-directory-outside-repo>`', '',
             'Category commands ran in the disposable source checkout with the sanitized environment recorded by this harness. Bare argv below requires that same cwd/environment.', '',
             '| Category | Status | Exit | Reproduce |', '|---|---|---:|---|']
    for name, value in report['categories'].items():
        lines.append(f"| {name} | {value['status']} | {value.get('exit_code', '')} | `{value.get('reproduce', '')}` |")
    lines += ['', 'Public synthetic CI may PASS when the four *named* private tests SKIP, but those cases remain BLOCKED and are never certified.',
              'Unexpected skips, missing private-test identities, or any test failure still FAIL. Private certification requires all four real tests PASS.',
              f"EXTERNAL_IKS_CERTIFICATION: **{report.get('EXTERNAL_IKS_CERTIFICATION', 'BLOCKED')}**",
              f"GATE_A_DEV_PLATFORM: **{report.get('GATE_A_DEV_PLATFORM', 'NOT RUN')}**",
              f"GATE_A_DEV_AUTOMATED: **{report['GATE_A_DEV_AUTOMATED']}** (requires matching Ubuntu and Windows jobs)",
              f"GATE_A_LOCAL_PRODUCTION_AUTHORITY: **{report['GATE_A_LOCAL_PRODUCTION_AUTHORITY']}**",
              '', 'Known desired product behavior (a reproduced defect is not fixed):',
              json.dumps(report.get('known_product_behaviour', {}), sort_keys=True), '',
              'No production database, authority file, vault or configured provider is included.']
    (directory / 'VALIDATION_SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def clean_environment(directory: Path, source: Path, *, allow_private_fixtures=False, fixture_environment=None) -> dict:
    # Preserve runtime essentials, never provider credentials or a user dotenv.
    names = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
             'TMPDIR', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH', 'PLAYWRIGHT_BROWSERS_PATH'}
    env = {name: value for name, value in os.environ.items() if name.upper() in names}
    env.update({'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8',
                'PYTHONPATH': os.pathsep.join([str(source / 'scripts/validation_guard'), str(source), str(source / 'tests')]),
                'MPLBACKEND': 'Agg', 'MPLCONFIGDIR': str(directory / 'matplotlib'),
                'ANVAYA_VALIDATION_ARTIFACTS': str(directory / 'screenshots'),
                # Run all existing Chromium learning regressions in the architecture
                # full-suite gate; unavailable external pilot sources remain explicit
                # skips until their verified user-owned files are supplied.
                'ANVAYA_BROWSER_TESTS': '1',
                'ANVAYA_BROWSER_ARTIFACTS': str(directory / 'screenshots'),
                'TZ': 'Asia/Kolkata'})
    if allow_private_fixtures:
        validated = validate_pair(fixture_environment if fixture_environment is not None else os.environ, repo=ROOT, output=directory)
        env.update({row['environment']: row['path'] for row in validated.values()})
        # The unchanged external browser acceptance captures genuine slides when
        # this optional variable exists. Keep it unset for private certification.
        env.pop('ANVAYA_BROWSER_ARTIFACTS', None)
    return env


def run_command(name: str, command: list[str], source: Path, run: Path, env: dict, *, xml=None, timeout=900) -> dict:
    log = run / (name + '.log')
    started = time.monotonic()
    private = any(spec['environment'] in env for spec in FIXTURES.values())
    # Private raw output never touches the public evidence directory, even if
    # interrupted or a child writes malformed/non-UTF8 JUnit.
    private_directory = private_temporary_directory(prefix='anvaya-private-diagnostic-', repo=source, output=run) if private else None
    raw_log = Path(private_directory.name) / 'stdout.log' if private else log
    raw_xml = Path(private_directory.name) / 'junit.xml' if private and xml else xml
    actual_command = [arg.replace(str(xml), str(raw_xml)) if private and xml else arg for arg in command]
    code = 127
    try:
        try:
            with raw_log.open('w', encoding='utf-8', errors='replace') as stream:
                process = subprocess.run(actual_command, cwd=source, env=env, stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=timeout, check=False)
            code = process.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            if not private:
                with log.open('a', encoding='utf-8') as stream:
                    stream.write(type(error).__name__ + ': ' + str(error))
            code = 124 if isinstance(error, subprocess.TimeoutExpired) else 127
        if private and raw_xml and raw_xml.exists():
            try:
                # Rebuild only the outcome-bearing JUnit structure. Never copy
                # unrecognised elements/attributes or source-bearing diagnostics.
                original = ET.parse(raw_xml)
                safe_root = ET.Element('testsuites')
                suite = ET.SubElement(safe_root, 'testsuite', name=name)
                for index, case in enumerate(original.findall('.//testcase'), 1):
                    identity = (case.get('classname', ''), case.get('name', ''))
                    classname, testname = identity if identity in EXTERNAL_TEST_IDS else ('private_validation', 'case-%06d' % index)
                    clean_case = ET.SubElement(suite, 'testcase', {'classname': classname, 'name': testname})
                    for tag in ('failure', 'error', 'skipped'):
                        if case.find(tag) is not None:
                            ET.SubElement(clean_case, tag, message='Private-source diagnostic withheld; outcome retained')
                suite.set('tests', str(len(list(suite))))
                for tag, attribute in [('failure', 'failures'), ('error', 'errors'), ('skipped', 'skipped')]:
                    suite.set(attribute, str(len(suite.findall('testcase/' + tag))))
                ET.ElementTree(safe_root).write(xml, encoding='utf-8', xml_declaration=True)
            except (ET.ParseError, OSError, UnicodeError):
                code = code or 125
    finally:
        if private:
            log.write_text('Private-fixture run: stdout withheld to protect source payloads.\n'
                           + 'Exit code: ' + str(code) + '\n', encoding='utf-8')
            private_directory.cleanup()
    result = test_status(code, xml, allow_external_skips=(name == 'full_pytest' and not private)) if xml else {'status': 'PASS' if code == 0 else 'FAIL', 'exit_code': code}
    public_command = list(command)
    if private and '-c' in public_command:
        index = public_command.index('-c') + 1
        if index < len(public_command):
            public_command[index] = '<inline command withheld>'
    result.update({'command': public_command, 'reproduce': subprocess.list2cmdline(public_command),
                   'cwd': str(source), 'environment_policy': 'clean_environment: runtime whitelist, provider credentials removed, loopback-only Python sockets',
                   'seconds': round(time.monotonic() - started, 3), 'timeout_seconds': timeout, 'log': log.name})
    print(name + ': ' + result['status'], flush=True)
    return json.loads(redact(json.dumps(result), env))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-clean', action='store_true', help='Require a clean committed source tree (CI)')
    parser.add_argument('--private-fixtures', action='store_true', help='Opt in to both pinned originals on an authorised private runner; paths must be outside source/artifacts')
    args = parser.parse_args(argv)
    run = prepare_output(args.output, ROOT)
    report = {'source': {}, 'categories': {}, 'GATE_A_DEV_PLATFORM': 'BLOCKED',
              'GATE_A_DEV_AUTOMATED': 'BLOCKED',
              'validation_scope': 'Single platform. Cross-platform acceptance is emitted by the CI aggregate job only after both matrix jobs pass.',
              'require_clean_source': args.require_clean,
              'GATE_A_LOCAL_PRODUCTION_AUTHORITY': 'BLOCKED',
              'EXTERNAL_IKS_CERTIFICATION': 'BLOCKED',
              'known_product_behaviour': {key: 'FAIL' for key in ['A', 'B', 'C', 'D', *['P%02d' % n for n in range(1, 9)]]}}
    source = run / 'source'
    staging = None
    try:
        if args.require_clean:
            require_clean_source(ROOT)
        report['source'] = export_source(ROOT, source)
        if args.private_fixtures:
            staging = PrivateFixtureStage(os.environ, repo=ROOT, output=args.output)
        env = clean_environment(run, source, allow_private_fixtures=args.private_fixtures,
                                fixture_environment=staging.environment if staging else None)
        report['external_fixtures'] = staging.manifest if staging else {'status': 'BLOCKED', 'reason': 'Private fixture opt-in not enabled'}
        report['environment'] = {'python': sys.version, 'platform': platform.platform(),
                                 'sqlite': sqlite3.sqlite_version, 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                                 'packages': {name: importlib.metadata.version(name) for name in ['Flask', 'pytest', 'numpy', 'pandas', 'matplotlib', 'playwright', 'tzdata']}}
        (run / 'source-manifest.json').write_text(json.dumps(report['source'], indent=2), encoding='utf-8')
        def command(name, args, **kwargs):
            report['categories'][name] = run_command(name, args, source, run, env, **kwargs)
        def pytest(name, files=(), *, timeout=900):
            xml = run / (name + '.xml')
            command(name, [sys.executable, '-m', 'pytest', '-q', '--durations=25', *files, '--junitxml=' + str(xml)], xml=xml, timeout=timeout)
        # Full unchanged suite, including existing browser tests; no selection flags.
        # Windows full-suite evidence on 22 Oct reached 94% before the 1800s
        # subprocess deadline. Allow bounded completion without weakening
        # selection, assertions, skip policy or exit handling.
        # The consolidated suite contains over 3,700 cases. Windows reached
        # 89% without assertion failures at the old 35-minute process deadline.
        # Keep every case and fail-closed timeout handling; allow its full run.
        pytest('full_pytest', timeout=4200)
        report['categories']['external_pilots'] = external_pilot_acceptance(run / 'full_pytest.xml')
        report['EXTERNAL_IKS_CERTIFICATION'] = report['categories']['external_pilots']['status']
        pytest('focused', ['tests/test_phase7_5_progress_planning.py', 'tests/test_phase7_5_operational_planner_routes.py',
                          'tests/test_assessment_studio_phase_e.py', 'tests/test_assessment_studio_phase_f.py', 'tests/test_phase7_5_15_14_focus_companion_analysis.py'])
        order = ['tests/test_phase7_5_academic_agent_web.py', 'tests/test_phase7_5_anvaya_shell.py', 'tests/test_phase2_closure_architecture.py']
        pytest('fixture_order_agent_first', order)
        pytest('fixture_order_phase2_first', list(reversed(order)))
        pytest('characterization', ['tests/test_architecture_characterization.py'])
        # Desired regressions are distinguished from the remaining defect witnesses.
        for repaired in ('A', 'B', 'C', 'D', 'P01', 'P02', 'P03', 'P04', 'P05', 'P06', 'P07', 'P08'):
            report['known_product_behaviour'][repaired] = report['categories']['characterization']['status']
        pytest('headless_browser', ['tests/test_assessment_live_browser.py', 'tests/test_architecture_live_browser.py', 'tests/test_topic_read_safety_browser.py'])
        command('node', ['node', '--test', *[str(p.relative_to(source)) for p in sorted((source / 'tests/js').glob('*.test.cjs'))]])
        command('pip_check', [sys.executable, '-m', 'pip', 'check'])
        command('pip_freeze', [sys.executable, '-m', 'pip', 'freeze'])
        command('compile', [sys.executable, '-m', 'compileall', '-q', 'personal_learning_assistant', 'tests', 'scripts'])
        command('migration_fixture', [sys.executable, 'scripts/architecture_validation_fixture.py', '--output', str(run / 'fixtures')])
        command('source_diff_check', ['git', 'diff', '--check'])
        command('source_cached_diff_check', ['git', 'diff', '--cached', '--check'])
        # Also check the actual feature delta; export cleanliness cannot hide whitespace errors.
        report['categories']['feature_diff_check'] = run_command('feature_diff_check', ['git', 'diff', '--check'], ROOT, run, env)
        report['categories']['feature_cached_diff_check'] = run_command('feature_cached_diff_check', ['git', 'diff', '--cached', '--check'], ROOT, run, env)
        report['GATE_A_DEV_PLATFORM'] = development_gate_status(
            report['categories'], private_fixtures=args.private_fixtures)
    except Exception as error:
        report['categories']['setup'] = {'status': 'BLOCKED', 'error': type(error).__name__ + ': ' + str(error)}
        report['GATE_A_DEV_PLATFORM'] = 'BLOCKED'
    finally:
        if staging:
            staging.close()
        write_summary(run, report)
        print('RESULTS: ' + str(run), flush=True)
    return 0 if report['GATE_A_DEV_PLATFORM'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
