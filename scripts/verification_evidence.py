"""Exact-input evidence identities and honest failure/gate reporting.

Reports are diagnostic, not trust roots. Reuse requires independently verified
GitHub run + immutable artifact digest provenance supplied by a trusted caller.
The workflows currently always execute; automatic remote evidence reuse is off.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def command(root, args):
    try:
        return subprocess.check_output(args, cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return 'NOT_AVAILABLE'


def identity(root, plan):
    root = Path(root)
    # Include actual test bytes and workflow implementation, not only names.
    def hashes(paths):
        return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() if (root/p).is_file() else 'MISSING' for p in sorted(paths)}
    workflows = [p.relative_to(root).as_posix() for folder in ('scripts','.github/workflows')
                 for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.yml','.yaml','.json')]
    dependencies = [p.name for p in root.glob('requirements*.txt')]
    config = {k:v for k,v in os.environ.items() if k in (
        'ANVAYA_BROWSER_TESTS','ANVAYA_PRIVATE_FIXTURES_REQUIRED','JAVA_HOME','ANDROID_API_LEVEL')}
    environment = {'os':platform.platform(), 'machine':platform.machine(), 'python':sys.version,
                   'packages':command(root,[sys.executable,'-m','pip','freeze']),
                   'node':command(root,['node','--version']), 'javac':command(root,['javac','-version']),
                   'gradle':command(root,['gradle','--version']),
                   'android_sdk':command(root,['sdkmanager','--version']),
                   'dependencies':hashes(dependencies), 'config':config}
    # Reports generated before selection are not application source. Every
    # tracked modification and every other untracked file disables reuse.
    # Never exclude source extensions under the diagnostics directory.
    untracked = command(root,['git','ls-files','--others','--exclude-standard','-z']).split('\0')
    diagnostics = {'shared-verification.json','shared-selector.xml','scheduling.json'}
    unexpected = [p for p in untracked if p and p not in diagnostics and not (
        p.startswith('verification-results/') and Path(p).suffix in ('.json','.xml','.log','.png'))]
    dirty = bool(command(root,['git','diff','HEAD','--name-only'])) or bool(unexpected)
    return {'source_sha':command(root,['git','rev-parse','HEAD']),
            'tree_sha':command(root,['git','rev-parse','HEAD^{tree}']),
            'dirty':dirty,
            'workflow_fingerprint':digest(hashes(workflows)),
            'inventory_fingerprint':digest(hashes(plan['python_tests']+plan['javascript_tests'])),
            'environment_fingerprint':digest(environment), 'environment':environment, 'stage':plan['stage']}


def reusable(record, requested, provenance):
    required = ('source_sha','tree_sha','workflow_fingerprint','inventory_fingerprint','environment_fingerprint','stage')
    return bool(
        record.get('outcome') == 'PASS' and not record.get('blockers')
        and not requested.get('dirty') and not record.get('identity',{}).get('dirty')
        and all(requested.get(k) and record.get('identity',{}).get(k) == requested[k] for k in required)
        and provenance.get('authenticated') is True and provenance.get('workflow_trusted') is True
        and provenance.get('artifact_digest_verified') is True
        and provenance.get('expired') is False and provenance.get('conclusion') == 'success'
        and provenance.get('head_sha') == requested['source_sha']
        and record.get('run_id') and record.get('artifact_id')
        and provenance.get('run_id') == record['run_id'] and provenance.get('artifact_id') == record['artifact_id'])


def gate(results, required):
    states = [results.get(name) for name in required]
    if any(s in ('failure','cancelled','timed_out') for s in states):
        return 'FAIL'
    return 'PASS' if states and all(s == 'success' for s in states) else 'BLOCKED'


def diagnose(argv, exit_code, log):
    patterns = [
        ('missing_private_fixture', ('private fixture','private-fixture'), 'protected private fixture provisioning'),
        ('missing_dependency', ('modulenotfounderror','no module named','command not found'), 'tracked dependency installation'),
        ('android_build', ('install_failed','gradle','execution failed for task'), 'Android compiler/build/update identity'),
        ('browser_ui', ('page.wait_for','playwright','browserclosed'), 'browser logs, selector and viewport'),
        ('infrastructure', ('runner lost','no space left','connection reset'), 'runner and network availability'),
        ('integration_conflict', ('merge conflict','conflict ('), 'stream ancestry and overlapping changes'),
        ('test_assertion', ('assertionerror','assert '), 'failed assertion and changed implementation'),
        ('source_regression', ('syntaxerror','indentationerror'), 'source compilation'),
        ('missing_verification', ('not verified','missing required'), 'mandatory evidence inventory'),
    ]
    category, area = next(((c,a) for c,terms,a in patterns if any(t in log.lower() for t in terms)),
                          ('indeterminate','first failing command and its log'))
    return {'category':category, 'command':argv, 'exit_code':exit_code,
            'reproduce':shlex.join(argv), 'investigate':area,
            'flaky':False, 'retry_policy':'No automatic retry; compare attempts before diagnosing flakiness'}
