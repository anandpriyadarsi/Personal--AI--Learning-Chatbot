"""Behavioral safety tests for the shared verifier, with real synthetic Git DAGs."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def policy():
    return importlib.import_module('verification_policy')


@pytest.mark.parametrize(('path', 'expected'), [
    ('personal_learning_assistant/services/native_document_search.py', {'library', 'learning', 'tutor'}),
    ('personal_learning_assistant/ui/web/routes.py', {'core', 'assessment', 'media', 'tutor', 'planning', 'ui'}),
    ('android/app/src/main/java/in/anvaya/privateapp/MediaFileProvider.java', {'android', 'media', 'library'}),
    ('personal_learning_assistant/ui/web/static/js/assessment_runner.js', {'assessment', 'ui', 'security'}),
    ('personal_learning_assistant/repositories/sqlite/migrations/099.sql', {'persistence', 'assessment', 'learning', 'library', 'planning'}),
    ('personal_learning_assistant/security/csrf.py', {'security', 'assessment', 'library', 'tutor'}),
    ('personal_learning_assistant/services/notes_media_service.py', {'media', 'library', 'android'}),
    ('.github/workflows/test.yml', {'ci', 'core', 'android'}),
    ('new.unknown', {'core', 'android', 'security'}),
])
def test_dependency_closure(path, expected):
    actual = policy().affected([path])
    assert expected <= set(actual['components'])
    assert actual['reasons']


def test_single_and_multi_component_changes():
    p = policy()
    assert set(p.affected(['personal_learning_assistant/tutor/policy.py'])['components']) == {'tutor'}
    assert {'tutor', 'planning'} <= set(p.affected([
        'personal_learning_assistant/tutor/policy.py',
        'personal_learning_assistant/services/planning_service.py'])['components'])


def test_test_changes_and_docs_are_distinct():
    p = policy()
    assert 'assessment' in p.affected(['tests/test_assessment_pause_paper.py'])['components']
    assert not p.affected(['docs/verification/readme.md'])['components']
    assert p.affected(['personal_learning_assistant/ui/web/static/logo.svg'])['components']
    assert p.affected(['ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md'])['components']


@pytest.mark.parametrize('path', ['docs/academic_source.md', 'docs/assessment_authoring_prompt.md', 'docs/fixtures/source.json'])
def test_docs_directory_cannot_hide_academic_or_executable_inputs(path):
    assert policy().affected([path])['components']


def test_unknown_and_empty_are_broad():
    p = policy()
    for paths in ([], ['../escape.py'], ['runtime.bin']):
        r = p.affected(paths)
        assert r['broad']
        assert set(r['components']) == set(p.COMPONENTS)


def test_inventory_missing_is_blocked(tmp_path):
    p = policy()
    result = p.selection(['personal_learning_assistant/tutor/policy.py'], tmp_path, 'fast')
    assert result['blockers']
    assert result['outcome'] == 'BLOCKED'


def test_affected_feature_includes_all_related_tests(tmp_path):
    p = policy()
    for name in ['tests/test_native_document_search.py', 'tests/test_native_library_storage.py',
                 'tests/test_library_document_rename.py', 'tests/test_notes_media_android_contract.py']:
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('def test_example(): pass\n')
    r = p.selection(['personal_learning_assistant/services/native_document_search.py'], tmp_path, 'feature')
    assert {'tests/test_native_document_search.py', 'tests/test_native_library_storage.py',
            'tests/test_library_document_rename.py'} <= set(r['python_tests'])


def test_evidence_rejects_stale_tree_environment_and_user_json():
    e = importlib.import_module('verification_evidence')
    identity = dict(source_sha='a'*40, tree_sha='b'*40, workflow_fingerprint='c',
                    inventory_fingerprint='d', environment_fingerprint='e', stage='feature')
    record = dict(identity=identity, outcome='PASS', blockers=[], run_id=123, artifact_id=456)
    proof = dict(authenticated=True, run_id=123, artifact_id=456, head_sha='a'*40,
                 conclusion='success', expired=False, workflow_trusted=True, artifact_digest_verified=True)
    assert e.reusable(record, identity, proof)
    assert not e.reusable(record, identity, {})
    for key in ('source_sha', 'tree_sha', 'workflow_fingerprint', 'inventory_fingerprint', 'environment_fingerprint', 'stage'):
        assert not e.reusable(record, {**identity, key:'different'}, proof)
    for key, value in [('conclusion','skipped'), ('expired',True), ('workflow_trusted',False), ('artifact_digest_verified',False)]:
        assert not e.reusable(record, identity, {**proof, key:value})
    assert not e.reusable({**record, 'blockers':['Missing fixture']}, identity, proof)


@pytest.mark.parametrize('state', ['failure', 'skipped', 'cancelled', 'not_verified', None])
def test_release_gate_never_accepts_missing_mandatory_evidence(state):
    e = importlib.import_module('verification_evidence')
    assert e.gate({'python': 'success', 'android': state}, ['python','android']) != 'PASS'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, 'init', '-b', 'main')
    git(tmp_path, 'config', 'user.name', 'Synthetic')
    git(tmp_path, 'config', 'user.email', 'synthetic@example.invalid')
    (tmp_path/'original.txt').write_text('base\n')
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-m', 'base')
    return tmp_path


def commit(root, path, text):
    (root/path).write_text(text)
    git(root, 'add', '.')
    git(root, 'commit', '-m', path)
    return git(root, 'rev-parse', 'HEAD')


def test_stacked_integration_preview_preserves_refs(repo):
    i = importlib.import_module('verification_integration')
    base = git(repo,'rev-parse','HEAD')
    git(repo, 'checkout', '-b', 'one')
    a = commit(repo, 'one.txt', 'one\n')
    git(repo,'checkout','-b','two')
    b = commit(repo,'two.txt','two\n')
    before = git(repo,'show-ref')
    r = i.preview(repo, base, {'one':a, 'two':b})
    assert r['status'] == 'PREPARED_NOT_VERIFIED'
    assert r['included_by']['one'] == 'two'
    assert git(repo,'show-ref') == before
    assert git(repo,'ls-tree','--name-only',r['candidate_commit']).splitlines() == ['one.txt','original.txt','two.txt']


def test_conflicting_integration_never_claims_ready(repo):
    i = importlib.import_module('verification_integration')
    base = git(repo,'rev-parse','HEAD')
    git(repo,'checkout','-b','one')
    a = commit(repo,'original.txt','one\n')
    git(repo,'checkout','-b','two',base)
    b = commit(repo,'original.txt','two\n')
    r = i.preview(repo,base,{'one':a,'two':b})
    assert r['status'] == 'CONFLICT'
    assert r['overlaps']
    assert 'original.txt' in r['conflicting_files']
    assert not r.get('candidate_commit')


def test_bad_merge_base_is_blocked(repo):
    i = importlib.import_module('verification_integration')
    r = i.preview(repo, '0'*40, {'one':git(repo,'rev-parse','HEAD')})
    assert r['status'] == 'BLOCKED'


@pytest.mark.parametrize(('log','category'), [
    ('ModuleNotFoundError: dependency', 'missing_dependency'),
    ('AssertionError: wrong output', 'test_assertion'),
    ('INSTALL_FAILED_UPDATE_INCOMPATIBLE', 'android_build'),
    ('private fixture unavailable', 'missing_private_fixture'),
    ('TimeoutError: page.wait_for_selector', 'browser_ui'),
    ('runner lost communication', 'infrastructure'),
    ('mystery', 'indeterminate'),
])
def test_failure_diagnosis(log, category):
    e = importlib.import_module('verification_evidence')
    r = e.diagnose(['python','-m','pytest','tests/test_x.py'], 1, log)
    assert r['category'] == category
    assert r['reproduce']
    assert not r['flaky']


def test_diff_failure_writes_blocked_broad_plan(tmp_path, monkeypatch):
    c = importlib.import_module('verification_coordinator')
    monkeypatch.setattr(c.smart_verify, 'changed_paths', lambda *a: (_ for _ in ()).throw(ValueError('bad merge base')))
    output = tmp_path/'report.json'
    assert c.main(['--base','missing','--json',str(output),'--execute']) == 2
    report = json.loads(output.read_text())
    assert report['outcome'] == 'BLOCKED'
    assert set(report['components']) == set(policy().COMPONENTS)
    assert not report['started_tests']


def test_unsafe_test_path_cannot_be_executed(tmp_path):
    p = policy().selection(['tests/../../escape.py'], tmp_path)
    assert p['blockers']
    assert 'tests/../../escape.py' not in p['python_tests']


def test_live_resolution_retrieves_new_heads_and_preserves_missing_evidence():
    i = importlib.import_module('verification_integration')
    calls=[]
    head=['a'*40]
    def api(path):
        calls.append(path)
        if path == 'branches/main': return {'commit':{'sha':'b'*40}, 'protected':False}
        if path.startswith('branches/'): return {'commit':{'sha':head[0]}}
        if path.startswith('compare/'): return {'files':[{'filename':'document.py'}]}
        if path.startswith('actions/runs'): return {'workflow_runs':[]}
        raise AssertionError(path)
    config={'repository':i.REPOSITORY, 'streams':[{'name':'example','source_branch':'feature/new','related_pull_requests':[]}]}
    first=i.resolve(config,api);head[0]='c'*40;second=i.resolve(config,api)
    assert first['streams'][0]['source_sha'] != second['streams'][0]['source_sha']
    assert second['streams'][0]['verification_state'] == 'NOT_VERIFIED'
    assert second['streams'][0]['outstanding_blockers']
    assert any('branches/feature' in call for call in calls)


def test_workflow_security_and_cancellation_contract():
    import yaml
    root=Path(__file__).resolve().parents[1]
    def workflow(name): return yaml.load((root/'.github/workflows'/name).read_text(),Loader=yaml.BaseLoader)
    smart=workflow('smart-verification.yml')
    assert 'pull_request_target' not in smart['on']
    assert 'pull_request' in smart['concurrency']['cancel-in-progress']
    assert 'inputs.stage' in smart['concurrency']['group']
    assert 'push' not in smart['on'] or smart['on']['push']['branches'] == ['integration/**']
    for file in ('smart-verification.yml','architecture-validation.yml'):
        wf=workflow(file)
        assert wf['permissions']['contents'] == 'read'
        for job in wf['jobs'].values():
            for step in job.get('steps',[]):
                if step.get('uses','').startswith('actions/checkout@'):
                    assert step['with']['persist-credentials'] == 'false'
                if step.get('uses','').startswith('actions/cache/save@'):
                    assert "github.event_name == 'push'" in step['if']
                    assert "refs/heads/main" in step['if']


def test_release_rejects_skipped_job_in_successful_run():
    release=importlib.import_module('verification_release')
    sha='a'*40
    def api(path):
        if path.endswith('/jobs?per_page=100&page=1'):
            return {'total_count':1,'jobs':[{'name':'installed','head_sha':sha,'status':'completed','conclusion':'skipped'}]}
        return {'id':123,'head_sha':sha,'status':'completed','conclusion':'success',
                'path':'.github/workflows/android.yml','head_repository':{'full_name':'owner/repo'}}
    result=release.inspect_run(123,sha,'.github/workflows/android.yml',['installed'],'owner/repo',api)
    assert result['state'] == 'BLOCKED'


def test_release_rejects_stale_or_untrusted_source():
    release=importlib.import_module('verification_release')
    def api(path):
        return {'head_sha':'a'*40,'status':'completed','conclusion':'success',
                'path':'.github/workflows/test.yml','head_repository':{'full_name':'fork/repo'}}
    result=release.inspect_run(123,'a'*40,'.github/workflows/test.yml',['required'],'owner/repo',api)
    assert result['state'] == 'BLOCKED'


@pytest.mark.parametrize('body', ["require('node:test').skip('required',()=>{});", "require('node:test').todo('required');", '// no tests'])
def test_node_skips_todo_and_empty_inventory_block_pass(repo, body):
    c=importlib.import_module('verification_coordinator')
    script=repo/'required.test.cjs';script.write_text(body)
    data={'python_tests':[], 'javascript_tests':[script.name], 'blockers':[], 'stage':'feature'}
    assert c.execute(data,repo,repo/'reports') == 2
    assert data['outcome'] == 'BLOCKED'
    assert data['javascript_results']


def test_manifest_resolution_outage_is_not_success():
    i=importlib.import_module('verification_integration')
    def api(path):
        if path.startswith('branches/'):
            return {'commit':{'sha':'a'*40}}
        raise OSError('unavailable')
    config={'repository':i.REPOSITORY,'streams':[{'name':'example','source_branch':'feature/example'}]}
    result=i.resolve(config,api)
    assert result['blockers']


def test_deleted_javascript_contract_blocks_verification(tmp_path):
    p=policy().selection(['tests/js/deleted_contract.test.cjs'],tmp_path)
    assert any('deleted_contract.test.cjs' in b for b in p['blockers'])


def test_native_pr_job_invokes_real_android_checks():
    import yaml
    root=Path(__file__).resolve().parents[1]
    wf=yaml.load((root/'.github/workflows/smart-verification.yml').read_text(),Loader=yaml.BaseLoader)
    native=[job for job in wf['jobs'].values() if job.get('uses')=='./.github/workflows/verification-android.yml']
    assert native
    assert 'native_needed' in native[0]['if']


def test_untracked_runtime_source_disables_evidence_reuse(repo):
    e=importlib.import_module('verification_evidence')
    (repo/'unexpected_runtime.py').write_text('unexpected = True\n')
    plan={'python_tests':[],'javascript_tests':[],'stage':'fast'}
    assert e.identity(repo,plan)['dirty']


def test_diagnostic_output_does_not_change_source_identity(repo):
    e=importlib.import_module('verification_evidence')
    (repo/'shared-selector.xml').write_text('<testsuites/>')
    (repo/'shared-verification.json').write_text('{}')
    plan={'python_tests':[],'javascript_tests':[],'stage':'fast'}
    assert not e.identity(repo,plan)['dirty']


def test_changed_javascript_source_is_syntax_checked(repo):
    c=importlib.import_module('verification_coordinator')
    (repo/'broken.js').write_text('function { invalid syntax')
    data={'python_tests':[],'javascript_tests':[],'changed':['broken.js'],'blockers':[],'stage':'fast'}
    assert c.execute(data,repo,repo/'reports') == 1
    assert any('broken.js' in check['command'] for check in data['checks'])
