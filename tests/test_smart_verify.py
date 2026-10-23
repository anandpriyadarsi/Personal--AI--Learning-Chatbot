"""Independent characterization of smart test selection (no app dependencies)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'smart_verify.py'
spec = importlib.util.spec_from_file_location('smart_verify', SCRIPT)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def build(tmp_path):
    paths = [
        'tests/test_smart_verify.py', 'tests/test_tutor_grounding_v24.py',
        'tests/test_phase6_grounded_tutor_engine.py',
        'tests/test_assessment_pause_paper.py',
        'tests/test_assessment_studio_phase_e.py',
        'tests/test_learning_intelligence_v24.py', 'tests/test_reader_v24.py',
        'tests/test_ui_v2_contract.py',
        'tests/learning_studio/test_reader_completion_v24.py',
    ]
    for path in paths:
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('# fixture\n')
    return tmp_path


def test_tutor_change_selects_just_tutor(tmp_path):
    root = build(tmp_path)
    plan = module.make_plan(['personal_learning_assistant/tutor/policy.py'], 'fast', root)
    assert plan.areas == ['tutor']
    assert set(plan.selected) == {'tests/test_tutor_grounding_v24.py', 'tests/test_phase6_grounded_tutor_engine.py'}
    assert not plan.requires_full


def test_multi_area_union_in_focused_mode(tmp_path):
    root = build(tmp_path)
    plan = module.make_plan(['personal_learning_assistant/learning_studio/reader.py',
                             'personal_learning_assistant/tutor/provider.py'], 'focused', root)
    assert {'learning', 'tutor'} == set(plan.areas)
    assert 'tests/learning_studio/test_reader_completion_v24.py' in plan.selected
    assert 'tests/test_tutor_grounding_v24.py' in plan.selected


def test_shared_migration_always_requires_full(tmp_path):
    plan = module.make_plan(['personal_learning_assistant/repositories/sqlite/migrations/0002_academic_schema.sql'], 'fast', build(tmp_path))
    assert plan.requires_full
    assert plan.status == 'FULL_REQUIRED'


def test_dependencies_require_full(tmp_path):
    for path in ['requirements.txt', 'pytest.ini', '.github/workflows/ui-v2.yml', 'tests/conftest.py']:
        assert module.make_plan([path], 'focused', build(tmp_path)).requires_full


def test_unmapped_python_fails_closed(tmp_path):
    plan = module.make_plan(['personal_learning_assistant/services/brand_new_engine.py'], 'fast', build(tmp_path))
    assert plan.requires_full


def test_docs_only_does_not_run_everything(tmp_path):
    plan = module.make_plan(['docs/verification/README.md'], 'fast', build(tmp_path))
    assert plan.status == 'DOCS_ONLY'
    assert plan.selected == []


def test_changed_test_is_included_even_if_outside_fast_smoke(tmp_path):
    root = build(tmp_path)
    plan = module.make_plan(['tests/learning_studio/test_reader_completion_v24.py'], 'fast', root)
    assert 'tests/learning_studio/test_reader_completion_v24.py' in plan.selected


def test_unknown_test_never_claims_focused_sufficiency(tmp_path):
    root = build(tmp_path)
    path = root / 'tests/test_unclassified_runtime.py'
    path.write_text('def test_demo(): pass\n')
    plan = module.make_plan(['tests/test_unclassified_runtime.py'], 'focused', root)
    assert plan.requires_full
    assert plan.selected == ['tests/test_unclassified_runtime.py']


def test_empty_changes_fail_closed(tmp_path):
    assert module.make_plan([], 'fast', build(tmp_path)).requires_full


def test_no_base_fails_closed():
    try:
        module.changed_paths('', 'HEAD')
    except ValueError:
        pass
    else:
        raise AssertionError('Missing base was silently accepted')


def test_focused_requires_full_cannot_execute_subset(tmp_path):
    root = build(tmp_path)
    plan = module.make_plan(['pytest.ini'], 'focused', root)
    with patch.object(subprocess, 'call') as call:
        assert module.execute(plan, root, 'results.xml') == 2
        call.assert_not_called()


def test_windows_paths_are_normalized(tmp_path):
    root = build(tmp_path)
    plan = module.make_plan([r'personal_learning_assistant\tutor\provider.py'], 'fast', root)
    assert plan.areas == ['tutor']
