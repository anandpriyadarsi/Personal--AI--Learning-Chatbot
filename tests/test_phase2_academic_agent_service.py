import ast
from pathlib import Path

import personal_academic_agent

from personal_learning_assistant.domain.agent_models import AgentRoute
from personal_learning_assistant.services.academic_agent_service import (
    AcademicAgentService,
    INTENT_LABELS,
)


def _module_tree(module):
    path = Path(module.__file__)
    return ast.parse(path.read_text(encoding="utf-8"))


def test_agent_service_route_is_typed_and_view_neutral():
    service = AcademicAgentService()

    result = service.route("  Project   course score  ")

    assert isinstance(result, AgentRoute)
    assert result.original_text == "  Project   course score  "
    assert result.normalized_text == "project course score"
    assert result.intent == "COURSE_PROJECTION"
    assert result.label == INTENT_LABELS["COURSE_PROJECTION"]
    assert result.should_exit is False


def test_agent_service_back_route_exposes_exit_flag():
    result = AcademicAgentService().route("back")

    assert result.intent == "BACK"
    assert result.should_exit is True


def test_agent_service_is_non_interactive():
    from personal_learning_assistant.services import academic_agent_service

    tree = _module_tree(academic_agent_service)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            assert node.func.id not in {"input", "print"}


def test_agent_service_does_not_import_terminal_feature_modules():
    from personal_learning_assistant.services import academic_agent_service

    forbidden = {
        "course_manager",
        "daily_academic_brief",
        "intelligent_study_planner",
        "academic_intelligence_dashboard",
        "academic_calendar_planner",
        "semester_grade_intelligence",
        "rag_answer",
        "assignment_exam_assistant",
    }

    tree = _module_tree(academic_agent_service)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert forbidden.isdisjoint(imported)


def test_root_classification_api_delegates_to_service():
    service = AcademicAgentService()

    examples = [
        "",
        "What should I do now?",
        "Plan my week",
        "Show my deadlines",
        "How am I doing in MA103N?",
        "Show course grade",
        "Project course score",
        "How much do I need in the remaining assessments?",
        "Project my SGPA",
        "Add a quiz",
        "back",
    ]

    for text in examples:
        assert (
            personal_academic_agent.classify_intent(text)
            == service.classify_intent(text)
        )


def test_root_route_request_returns_typed_result():
    result = personal_academic_agent.route_request(
        "What should I study tonight?"
    )

    assert isinstance(result, AgentRoute)
    assert result.intent == "TODAY_PLAN"


def test_project_course_score_regression_is_preserved():
    service = AcademicAgentService()

    for text in (
        "Project course score",
        "Project my final course score",
        "Predict final score",
        "Course score projection",
    ):
        assert service.classify_intent(text) == "COURSE_PROJECTION"


def test_plain_course_score_still_means_current_grade_intelligence():
    service = AcademicAgentService()

    assert service.classify_intent("Show course score") == "COURSE_GRADE"
    assert service.classify_intent("Show course grade") == "COURSE_GRADE"


def test_agent_model_is_immutable():
    result = AcademicAgentService().route("help")

    try:
        result.intent = "NOW"
    except Exception:
        pass
    else:
        raise AssertionError("AgentRoute must be immutable")

    assert result.intent == "HELP"


def test_root_classify_intent_is_service_delegation():
    path = Path(personal_academic_agent.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))

    classify = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "classify_intent"
    )

    calls = [
        child
        for child in ast.walk(classify)
        if isinstance(child, ast.Call)
    ]

    assert any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "classify_intent"
        for call in calls
    )
