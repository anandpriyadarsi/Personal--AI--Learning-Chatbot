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
    subprocess.run(['git', '-C', str(target), 'add', '.'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(target), '-c', 'user.name=Synthetic validator',
                    '-c', 'user.email=synthetic@example.invalid', 'commit', '-m', 'Disposable source snapshot'], check=True, capture_output=True)
    return {'sha': _git(repo, 'rev-parse', 'HEAD'), 'branch': _git(repo, 'branch', '--show-current'),
            'dirty': bool(_git(repo, 'status', '--porcelain=v1', '-uall')),
            'snapshot_sha': _git(target, 'rev-parse', 'HEAD'), 'files': hashes,
            'snapshot_fingerprint': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def test_status(exit_code: int, xml: Path) -> dict:
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
        if exit_code or result['failures'] or result['errors']:
            result['status'] = 'FAIL'
        elif cases and not result['skips']:
            result['status'] = 'PASS'
    return result


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
    lines += ['', f"GATE_A_DEV_PLATFORM: **{report.get('GATE_A_DEV_PLATFORM', 'NOT RUN')}**",
              f"GATE_A_DEV_AUTOMATED: **{report['GATE_A_DEV_AUTOMATED']}** (requires matching Ubuntu and Windows jobs)",
              f"GATE_A_LOCAL_PRODUCTION_AUTHORITY: **{report['GATE_A_LOCAL_PRODUCTION_AUTHORITY']}**",
              '', 'Known desired product behavior (a reproduced defect is not fixed):',
              json.dumps(report.get('known_product_behaviour', {}), sort_keys=True), '',
              'No production database, authority file, vault or configured provider is included.']
    (directory / 'VALIDATION_SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def clean_environment(directory: Path, source: Path) -> dict:
    # Preserve runtime essentials, never provider credentials or a user dotenv.
    names = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
             'TMPDIR', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH', 'PLAYWRIGHT_BROWSERS_PATH'}
    env = {name: value for name, value in os.environ.items() if name.upper() in names}
    env.update({'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8',
                'PYTHONPATH': os.pathsep.join([str(source / 'scripts/validation_guard'), str(source), str(source / 'tests')]),
                'MPLBACKEND': 'Agg', 'MPLCONFIGDIR': str(directory / 'matplotlib'),
                'ANVAYA_VALIDATION_ARTIFACTS': str(directory / 'screenshots'),
                'TZ': 'Asia/Kolkata'})
    return env


def run_command(name: str, command: list[str], source: Path, run: Path, env: dict, *, xml=None) -> dict:
    log = run / (name + '.log')
    started = time.monotonic()
    try:
        with log.open('w', encoding='utf-8') as stream:
            process = subprocess.run(command, cwd=source, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, timeout=900, check=False)
        code = process.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        with log.open('a', encoding='utf-8') as stream:
            stream.write(type(error).__name__ + ': ' + str(error))
        code = 124 if isinstance(error, subprocess.TimeoutExpired) else 127
    result = test_status(code, xml) if xml else {'status': 'PASS' if code == 0 else 'FAIL', 'exit_code': code}
    result.update({'command': command, 'reproduce': subprocess.list2cmdline(command),
                   'cwd': str(source), 'environment_policy': 'clean_environment: runtime whitelist, provider credentials removed, loopback-only Python sockets',
                   'seconds': round(time.monotonic() - started, 3), 'log': log.name})
    print(name + ': ' + result['status'], flush=True)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    run = prepare_output(args.output, ROOT)
    report = {'source': {}, 'categories': {}, 'GATE_A_DEV_PLATFORM': 'BLOCKED',
              'GATE_A_DEV_AUTOMATED': 'BLOCKED',
              'validation_scope': 'Single platform. Cross-platform acceptance is emitted by the CI aggregate job only after both matrix jobs pass.',
              'GATE_A_LOCAL_PRODUCTION_AUTHORITY': 'BLOCKED',
              'known_product_behaviour': {key: 'FAIL' for key in ['A', 'B', 'C', 'D', *['P%02d' % n for n in range(1, 9)]]}}
    source = run / 'source'
    try:
        report['source'] = export_source(ROOT, source)
        env = clean_environment(run, source)
        report['environment'] = {'python': sys.version, 'platform': platform.platform(),
                                 'sqlite': sqlite3.sqlite_version, 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                                 'packages': {name: importlib.metadata.version(name) for name in ['Flask', 'pytest', 'numpy', 'pandas', 'matplotlib', 'playwright', 'tzdata']}}
        (run / 'source-manifest.json').write_text(json.dumps(report['source'], indent=2), encoding='utf-8')
        def command(name, args, **kwargs):
            report['categories'][name] = run_command(name, args, source, run, env, **kwargs)
        def pytest(name, files=()):
            xml = run / (name + '.xml')
            command(name, [sys.executable, '-m', 'pytest', '-q', *files, '--junitxml=' + str(xml)], xml=xml)
        # Full unchanged suite, including existing browser tests; no selection flags.
        pytest('full_pytest')
        pytest('focused', ['tests/test_phase7_5_progress_planning.py', 'tests/test_phase7_5_operational_planner_routes.py',
                          'tests/test_assessment_studio_phase_e.py', 'tests/test_assessment_studio_phase_f.py', 'tests/test_phase7_5_15_14_focus_companion_analysis.py'])
        order = ['tests/test_phase7_5_academic_agent_web.py', 'tests/test_phase7_5_anvaya_shell.py', 'tests/test_phase2_closure_architecture.py']
        pytest('fixture_order_agent_first', order)
        pytest('fixture_order_phase2_first', list(reversed(order)))
        pytest('characterization', ['tests/test_architecture_characterization.py'])
        pytest('headless_browser', ['tests/test_assessment_live_browser.py', 'tests/test_architecture_live_browser.py'])
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
        report['GATE_A_DEV_PLATFORM'] = 'PASS' if all(r['status'] == 'PASS' for r in report['categories'].values()) else 'FAIL'
    except Exception as error:
        report['categories']['setup'] = {'status': 'BLOCKED', 'error': type(error).__name__ + ': ' + str(error)}
        report['GATE_A_DEV_PLATFORM'] = 'BLOCKED'
    finally:
        write_summary(run, report)
        print('RESULTS: ' + str(run), flush=True)
    return 0 if report['GATE_A_DEV_PLATFORM'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
