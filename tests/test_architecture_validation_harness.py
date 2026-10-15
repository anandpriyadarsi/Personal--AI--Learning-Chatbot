import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def harness():
    path = ROOT / 'scripts/architecture_validation.py'
    assert path.is_file(), 'Cross-platform validator is not implemented'
    spec = importlib.util.spec_from_file_location('architecture_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_refuses_repo_nonempty_and_symlink_roots(tmp_path):
    module = harness()
    with pytest.raises(ValueError):
        module.prepare_output(ROOT, ROOT)
    occupied = tmp_path / 'occupied'
    occupied.mkdir()
    (occupied / 'personal.txt').write_text('private', encoding='utf-8')
    with pytest.raises(ValueError):
        module.prepare_output(occupied, ROOT)
    assert (occupied / 'personal.txt').read_text() == 'private'
    # Symlink creation on Windows may require privileges; the containment case
    # above runs on every platform, and symlink inspection is tested when supported.
    link = tmp_path / 'link'
    try:
        link.symlink_to(occupied, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(ValueError):
        module.prepare_output(link, ROOT)


def test_repeat_output_keeps_previous_run_and_allocates_new_disposable_root(tmp_path):
    module = harness()
    output = tmp_path / 'results'
    first = module.prepare_output(output, ROOT)
    (first / 'previous.log').write_text('preserve', encoding='utf-8')
    second = module.prepare_output(output, ROOT)
    assert first != second and first.parent == second.parent == output
    assert (first / 'previous.log').read_text() == 'preserve'


def test_export_omits_personal_environment_and_rejects_source_symlinks(tmp_path):
    module = harness()
    source = tmp_path / 'source'
    source.mkdir()
    def git(*args):
        subprocess.run(['git', '-C', str(source), *args], check=True, capture_output=True)
    git('init')
    (source / 'config.py').write_text('VALUE = 1\n', encoding='utf-8')
    fixture = source / 'tests/fixtures/synthetic/obsidian_config.json'
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"synthetic": true}', encoding='utf-8')
    (source / '.env').write_text('SECRET=never-export', encoding='utf-8')
    (source / 'data').mkdir()
    (source / 'data/learning_assistant.db').write_bytes(b'personal')
    for directory in ('tests', 'docs', 'scripts', 'personal_learning_assistant', 'schemas', '.github/workflows'):
        private = source / directory / 'credentials.txt'
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text('PRIVATE-MUST-NOT-BE-EXPORTED', encoding='utf-8')
    git('add', 'config.py', 'tests/fixtures/synthetic/obsidian_config.json')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'synthetic')
    with pytest.raises(ValueError, match='clean'):
        module.require_clean_source(source)
    target = tmp_path / 'export'
    manifest = module.export_source(source, target)
    assert (target / 'config.py').read_text() == 'VALUE = 1\n'
    assert not (target / '.env').exists() and not (target / 'data').exists()
    assert (target / 'tests/fixtures/synthetic/obsidian_config.json').read_text() == '{"synthetic": true}'
    assert manifest['sha'] and set(manifest['files']) == {'config.py', 'tests/fixtures/synthetic/obsidian_config.json'}


@pytest.mark.parametrize('exit_code,xml,status', [
    (1, '<testsuites/>', 'FAIL'),
    (0, '<testsuites><testsuite tests="1" skipped="1"><testcase name="browser"><skipped/></testcase></testsuite></testsuites>', 'BLOCKED'),
    (0, '<testsuites><testsuite tests="1" failures="0"><testcase name="ok"/></testsuite></testsuites>', 'PASS'),
    (0, '<testsuites/>', 'BLOCKED'),
])
def test_test_result_cannot_turn_failure_skip_or_empty_execution_green(tmp_path, exit_code, xml, status):
    path = tmp_path / 'result.xml'
    path.write_text(xml, encoding='utf-8')
    assert harness().test_status(exit_code, path)['status'] == status


def test_summary_keeps_production_and_known_product_defects_separate(tmp_path):
    module = harness()
    report = {'source': {'sha': 'synthetic'}, 'categories': {'full_pytest': {'status': 'PASS'}},
              'GATE_A_DEV_AUTOMATED': 'PASS', 'GATE_A_LOCAL_PRODUCTION_AUTHORITY': 'BLOCKED',
              'known_product_behaviour': {'A': 'FAIL'}}
    module.write_summary(tmp_path, report)
    saved = json.loads((tmp_path / 'VALIDATION_SUMMARY.json').read_text())
    assert saved['GATE_A_LOCAL_PRODUCTION_AUTHORITY'] == 'BLOCKED'
    assert saved['known_product_behaviour']['A'] == 'FAIL'
    assert 'BLOCKED' in (tmp_path / 'VALIDATION_SUMMARY.md').read_text()


def test_workflow_job_environment_uses_available_github_contexts():
    import yaml
    workflow = yaml.safe_load((ROOT / '.github/workflows/architecture-validation.yml').read_text(encoding='utf-8'))
    # GitHub's job-level env is evaluated before a runner exists. Runtime
    # paths must be initialized in steps, not in this restricted context.
    available = {'github', 'needs', 'strategy', 'matrix', 'vars', 'secrets', 'inputs'}
    for job in workflow['jobs'].values():
        for value in job.get('env', {}).values():
            for expression in re.findall(r'\$\{\{(.*?)\}\}', str(value)):
                contexts = re.findall(r'\b([A-Za-z_]\w*)\.', expression)
                assert set(contexts) <= available, expression


def test_command_can_finish_with_an_explicit_bounded_deadline(tmp_path):
    module = harness()
    result = module.run_command('bounded',
        [sys.executable, '-c', 'import time; time.sleep(0.05); print("completed")'],
        tmp_path, tmp_path, module.clean_environment(tmp_path, ROOT), timeout=2)
    assert result['status'] == 'PASS' and result['exit_code'] == 0
    assert 'completed' in (tmp_path / 'bounded.log').read_text()


def test_expired_command_deadline_fails_and_retains_output(tmp_path):
    module = harness()
    result = module.run_command('expired',
        [sys.executable, '-c', 'import time; print("started", flush=True); time.sleep(10)'],
        tmp_path, tmp_path, module.clean_environment(tmp_path, ROOT), timeout=2)
    assert result['status'] == 'FAIL' and result['exit_code'] == 124
    log = (tmp_path / 'expired.log').read_text()
    assert 'started' in log and 'TimeoutExpired' in log
