"""Fail-closed evidence reporting: missing cases and new skips are regressions."""
from scripts.learning_studio_regression_gate import compare_results
from scripts.learning_studio_junit_gate import inspect_report


def test_delta_rejects_new_skips_missing_cases_and_new_failures():
    baseline=[('suite::stable','passed'),('suite::legacy','failure')]
    assert compare_results(baseline,baseline)['regression_delta_green']
    for feature in ([('suite::stable','skipped'),baseline[1]],
                    [baseline[1]],
                    [baseline[0],baseline[1],('suite::added','failure')]):
        assert not compare_results(baseline,feature)['regression_delta_green']
    result=compare_results(baseline,baseline+[('suite::new_builtin','skipped')])
    assert result['new_skips']==['suite::new_builtin']
    assert not result['regression_delta_green']
    for kind in ('passed', 'failure', 'error'):
        assert not compare_results([('suite::test_external_old',kind)],
                                   [('suite::test_external_old','skipped')])['regression_delta_green']
    result=compare_results(baseline,baseline+[('suite::test_external_recovered','skipped')])
    assert result['regression_delta_green'] and result['external_skips']==['suite::test_external_recovered']


def test_junit_gate_counts_and_rejects_builtin_skip(tmp_path):
    path=tmp_path/'report.xml'
    path.write_text('<testsuite><testcase name="ok"/><testcase name="browser"><skipped/></testcase>'
                    '<testcase name="test_external_candidate"><skipped/></testcase></testsuite>')
    report=inspect_report(path)
    assert report['passed']==1 and report['cases']==3
    assert report['forbidden_skips']==['browser']
