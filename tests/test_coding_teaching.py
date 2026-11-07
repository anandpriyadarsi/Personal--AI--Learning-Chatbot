"""Shared teaching contracts, independent of either adapter's authority."""
import ast
from pathlib import Path
import pytest
from personal_learning_assistant.services.coding_teaching import ACTIONS, TeachingPolicy, teaching_system, SOLUTION_ACTIONS
from personal_learning_assistant.services.assessment_coding_helper import build_request, CodingHelperError


def test_core_has_no_execution_or_owner_dependencies():
    source = Path('personal_learning_assistant/services/coding_teaching.py').read_text(encoding='utf-8')
    tree=ast.parse(source)
    imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any('assessment' in m or 'repositories' in m or 'flask' in m for m in imports)
    assert len(ACTIONS)==12


@pytest.mark.parametrize('action',ACTIONS)
def test_action_policy_and_compatibility(action):
    from personal_learning_assistant.services.assessment_coding_helper import ACTIONS as facade
    assert facade is ACTIONS
    system=teaching_system(action,TeachingPolicy(allow_solution=True),solution=False)
    assert ACTIONS[action][1] in system
    assert 'Never claim to have run code' in system
    assert 'student explicitly requested' not in system
    assert ('student explicitly requested' in teaching_system(action,TeachingPolicy(allow_solution=True),solution=True)) == (action in SOLUTION_ACTIONS)


@pytest.mark.parametrize('mode,settings,allowed',[('practice',{},True),('assignment',{},True),('exam',{},False),('exam',{'ASSESSMENT_CODING_HELPER_EXAM_POLICY':'concepts'},False)])
def test_shared_extraction_preserves_assessment_restrictions(mode,settings,allowed):
    context={'course_code':'UC100N','mode':mode,'assessment_title':'Synthetic','question_text':'Visible text',
             'answer_key':'SECRET_ANSWER_KEY_DO_NOT_SEND','rubric':'SECRET_RUBRIC'}
    if allowed:
        request=build_request('s',context,{'action':'debug','code':'print(1)','full_solution':True},settings)
        assert 'SECRET_' not in str(request)
    else:
        with pytest.raises(CodingHelperError):
            build_request('s',context,{'action':'debug','code':'print(1)'},settings)
