"""Offline benchmark mechanics, never a live educational-quality claim."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('multimodal_evaluate', ROOT/'scripts/multimodal_evaluate.py')


def harness():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def test_benchmark_has_balanced_natural_inputs_and_separate_gold():
    h = harness()
    manifest = h.load_manifest()
    positives = [c for c in manifest['cases'] if c['id'].startswith('P')]
    negatives = [c for c in manifest['cases'] if c['id'].startswith('N')]
    assert len(positives) == 30 and len(negatives) == 15
    assert {s: sum(c['subject'] == s for c in positives) for s in ('MA103N','UC100N','CY100N')} == dict(MA103N=10,UC100N=10,CY100N=10)
    assert len({c['modality'] for c in positives}) == 5
    for case in manifest['cases']:
        text = h.source_text(case)
        assert case['id'] not in text
        assert 'gold' not in text.lower()
        assert not {'answer','expected','rubric'} & case.keys()
    assert h.check_reference_gold()['status'] == 'PASS'
    assert len(manifest['reserved_held_out']) == 9


def test_independent_gold_detects_corruption(tmp_path):
    h = harness()
    gold = json.loads((h.FIXTURES/'gold/answers.json').read_text())
    gold['P01']['reference'] = {'rref': [[1,2],[0,1]], 'rank': 2}
    assert h.check_reference_gold(gold)['status'] == 'FAIL'


def test_offline_run_exercises_actual_app_paths_without_model_claim(tmp_path):
    h = harness()
    report = h.evaluate(tmp_path/'run')
    assert report['model_quality'] == 'not_run'
    assert report['network_attempts'] == 0 and report['paid_cost_micros'] == 0
    assert len(report['positive_cases']) == 30 and len(report['negative_cases']) == 15
    assert report['reference_checks']['status'] == 'PASS'
    for row in report['positive_cases']:
        assert row['C']['status'] == 'NOT_AUTHORIZED'
        assert row['B']['status'] in ('PASS','UNSUPPORTED','FAIL')
        assert row['B']['model_answer_score'] is None
        assert row['B']['production_path_executed']
    assert all(r['B']['status'] == 'PASS' for r in report['positive_cases'])
    assert all(r['status'] in ('PASS','UNSUPPORTED') for r in report['negative_cases'])
    assert (tmp_path/'run/report.json').is_file()
    assert (tmp_path/'run/tasks.csv').is_file()
    assert len(report['follow_ups']) == 6


def test_scoring_rejects_wrong_source_and_never_scores_fake_quality():
    h = harness()
    expected = {'native_document_id':'one','content_hash':'a','mm_locator':{'kind':'image'}}
    assert not h.locator_matches(dict(expected,native_document_id='two'),expected)
    assert not h.locator_matches(dict(expected,content_hash='b'),expected)
    assert h.locator_matches(expected, expected)
    assert h.score_response('fabricated [S9]', {'S1'}, fake=True)['answer_score'] is None
    assert h.score_response('fabricated [S9]', {'S1'}, fake=True)['invented_citation_labels'] == ['S9']


def test_no_live_mode_or_gold_parameter_on_adapter(tmp_path):
    import inspect
    h = harness()
    assert 'gold' not in inspect.signature(h.run_positive).parameters
    with pytest.raises(ValueError, match='not authorized'):
        h.evaluate(tmp_path/'live', live=True)


def test_fake_math_envelope_uses_only_visible_input_not_expected_solution():
    from types import SimpleNamespace
    h = harness()
    fake = h.RecordingFakeProvider()
    req = SimpleNamespace(metadata={'evidence_labels':['S1']}, messages=({'role':'user','content':
        'CURRENT QUESTION\nCompute the final matrix.\n\nACADEMIC EVIDENCE\n<academic_evidence>\n[S1]\nBefore: [[8,3],[2,9]]\n</academic_evidence>'},))
    result = fake.complete(req)
    assert 'ANVAYA_MATH' in result.content
    assert '[[8, 3], [2, 9]]' in result.content
    assert 'offline' in result.content.lower()
    assert h.score_response(result.content,{'S1'},fake=True)['answer_score'] is None
