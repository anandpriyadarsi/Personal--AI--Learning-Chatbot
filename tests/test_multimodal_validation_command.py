"""Truthful orchestration contracts; no recursive full validator invocation."""
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import pytest


def suite(name='unit', **updates):
    value=dict(name=name,requested=True,executed=True,returncode=0,passed=4,failed=0,errors=0,skipped=0,timed_out=False)
    value.update(updates)
    return value


def test_validation_help_is_read_only_and_portable(tmp_path):
    result=subprocess.run([sys.executable,'-m','scripts.multimodal_validate','--help'],capture_output=True,text=True,timeout=20)
    assert result.returncode==0
    for option in ('--output','--browser','--restore','--full-offline','--suite-timeout'):
        assert option in result.stdout


def test_unit_only_even_windows_string_is_not_release_verified():
    from scripts.multimodal_validate import report
    value=report('Windows',[suite()])
    assert value['report_version']==2
    assert value['passed'] and not value['offline_passed']
    assert not value['windows_runtime_verified'] and not value['windows_verified']
    assert value['release_readiness']=='not_ready'
    assert value['live_model_quality']=='unverified'
    assert value['gates']['live_model']['status']=='NOT_AUTHORIZED'


@pytest.mark.parametrize('update',[dict(errors=1),dict(skipped=1),dict(passed=0),dict(failed=1),dict(timed_out=True),dict(returncode=5)])
def test_requested_suite_cannot_pass_with_incomplete_evidence(update):
    from scripts.multimodal_validate import report
    assert not report('Linux',[suite(**update)])['passed']


def test_linux_full_offline_never_claims_windows_and_missing_browser_is_blocked():
    from scripts.multimodal_validate import report
    value=report('Linux',[suite(name) for name in ('unit','browser','restore','integrity')])
    assert value['offline_passed'] and not value['windows_runtime_verified']
    assert value['release_readiness']=='conditional'
    value=report('Linux',[suite(),suite('browser',executed=False,blocked_reason='Chromium missing')])
    assert not value['passed'] and value['gates']['browser']['status']=='BLOCKED_ENVIRONMENT'


def test_junit_counts_errors_skips_and_zero_collected(tmp_path):
    from scripts.multimodal_validate import junit_counts
    path=tmp_path/'junit.xml'
    path.write_text('<testsuites><testsuite tests="5" failures="1" errors="1" skipped="1"><testcase/><testcase/><testcase><failure/></testcase><testcase><error/></testcase><testcase><skipped/></testcase></testsuite></testsuites>')
    assert junit_counts(path)==dict(passed=2,failed=1,errors=1,skipped=1,collected=5)
    path.write_text('<testsuites><testsuite tests="0"/></testsuites>')
    assert junit_counts(path)['passed']==0


def test_unit_discovery_includes_new_files_without_recursive_or_browser_runs(tmp_path):
    from scripts.multimodal_validate import unit_files
    (tmp_path/'tests').mkdir()
    for name in ('test_multimodal_new.py','test_multimodal_browser.py','test_multimodal_browser_extra.py','test_multimodal_restore.py','test_other.py'):
        (tmp_path/'tests'/name).touch()
    assert unit_files(tmp_path)==['tests/test_multimodal_new.py']


def test_offline_environment_removes_credentials_and_zeroes_budget(monkeypatch):
    from scripts.multimodal_validate import offline_environment
    monkeypatch.setenv('OPENAI_API_KEY','do-not-report-me')
    monkeypatch.setenv('CUSTOM_PROVIDER_TOKEN','do-not-report-me-either')
    monkeypatch.setenv('ANVAYA_MM_MONTHLY_MICROS','100')
    env=offline_environment(Path.cwd(),Path('/tmp/screenshots'))
    assert not env.get('OPENAI_API_KEY') and not env.get('CUSTOM_PROVIDER_TOKEN')
    assert env['ANVAYA_MM_MONTHLY_MICROS']=='0'
    assert env['ANVAYA_OFFLINE_GUARD']=='1'


def test_logs_redact_environment_secrets(monkeypatch):
    from scripts.multimodal_validate import redact
    monkeypatch.setenv('OPENAI_API_KEY','secret-example-key')
    assert 'secret-example-key' not in redact('oops secret-example-key and Bearer abcdefgh')


def test_suite_deadline_is_failure_and_retains_junit_path(tmp_path):
    from scripts.multimodal_validate import run_suite
    item=run_suite('unit',[sys.executable,'-c','import time; time.sleep(10)'],Path.cwd(),dict(),tmp_path,0.1)
    assert item['timed_out'] and item['status']=='FAIL'
    assert item['executed'] and Path(item['log_path']).exists()


def test_missing_browser_prerequisite_has_no_execution(tmp_path,monkeypatch):
    import scripts.multimodal_validate as validator
    monkeypatch.setattr(validator,'browser_prerequisite',lambda env:'Chromium missing')
    monkeypatch.setattr(validator,'unit_files',lambda root:[])
    # No nested pytest: explicitly exercise the prerequisite classifier.
    value=validator.blocked_suite('browser','Chromium missing',30)
    assert value['status']=='BLOCKED_ENVIRONMENT' and not value['executed']
    assert not validator.report('Linux',[value])['passed']


def test_previous_junit_cannot_make_unexecuted_tests_pass(tmp_path):
    from scripts.multimodal_validate import run_suite
    (tmp_path/'unit.xml').write_text('<testsuites><testsuite><testcase/></testsuite></testsuites>')
    item=run_suite('unit',[sys.executable,'-c','pass'],Path.cwd(),dict(),tmp_path,5)
    assert item['status']=='FAIL' and item['passed']==0
    assert item['junit_path'] is None


def test_collection_error_attributes_are_counted_without_cases(tmp_path):
    from scripts.multimodal_validate import junit_counts
    path=tmp_path/'junit.xml';path.write_text('<testsuites><testsuite tests="0" errors="1" failures="0" skipped="0"/></testsuites>')
    assert junit_counts(path)['errors']==1


def test_junit_aggregate_count_cannot_invent_passed_cases(tmp_path):
    from scripts.multimodal_validate import junit_counts
    path=tmp_path/'junit.xml';path.write_text('<testsuites><testsuite tests="9"/></testsuites>')
    assert junit_counts(path)['passed']==0
