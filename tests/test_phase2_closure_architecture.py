"""Phase 2 closure architecture checks.

These tests verify the structural guarantees required before Phase 3 begins.
They do not implement Phase 3 and they do not touch the user's real data.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CORE_SERVICE_FILES = {
    "course": ROOT / "personal_learning_assistant" / "services" / "course_service.py",
    "notes": ROOT / "personal_learning_assistant" / "services" / "notes_service.py",
    "resources": ROOT / "personal_learning_assistant" / "services" / "resource_service.py",
    "knowledge": ROOT / "personal_learning_assistant" / "services" / "knowledge_service.py",
    "agent": ROOT / "personal_learning_assistant" / "services" / "academic_agent_service.py",
}

REPOSITORY_FILES = {
    "course": ROOT / "personal_learning_assistant" / "repositories" / "json" / "course_repository.py",
    "notes": ROOT / "personal_learning_assistant" / "repositories" / "json" / "note_repository.py",
    "resources": ROOT / "personal_learning_assistant" / "repositories" / "json" / "resource_repository.py",
    "knowledge_course_context": (
        ROOT
        / "personal_learning_assistant"
        / "repositories"
        / "json"
        / "knowledge_course_context.py"
    ),
    "knowledge_filesystem": (
        ROOT
        / "personal_learning_assistant"
        / "repositories"
        / "filesystem"
        / "knowledge_repository.py"
    ),
}

INTERFACES = (
    ROOT
    / "personal_learning_assistant"
    / "repositories"
    / "interfaces.py"
)

OPTIONAL_PROVIDER_ROOTS = {
    "requests",
    "fastembed",
    "numpy",
    "youtube_transcript_api",
    "fitz",
    "PIL",
    "dotenv",
}

AGENT_TERMINAL_WORKFLOW_MODULES = {
    "course_manager",
    "daily_academic_brief",
    "intelligent_study_planner",
    "academic_intelligence_dashboard",
    "academic_calendar_planner",
    "semester_grade_intelligence",
    "rag_answer",
    "assignment_exam_assistant",
}


def _read(path: Path) -> str:
    assert path.exists(), f"Required Phase 2 file missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.AST:
    return ast.parse(
        _read(path),
        filename=str(path),
    )


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    return modules


def _imports_module(path: Path, wanted: str) -> bool:
    return any(
        module == wanted or module.startswith(wanted + ".")
        for module in _imported_modules(path)
    )


def _called_builtin_names(path: Path) -> set[str]:
    names: set[str] = set()

    for node in ast.walk(_tree(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        ):
            names.add(node.func.id)

    return names


def _top_level_function_names(path: Path) -> set[str]:
    return {
        node.name
        for node in _tree(path).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _top_level_class_names(path: Path) -> set[str]:
    return {
        node.name
        for node in _tree(path).body
        if isinstance(node, ast.ClassDef)
    }


def test_phase2_core_service_and_repository_files_exist():
    missing = [
        str(path.relative_to(ROOT))
        for path in (
            list(CORE_SERVICE_FILES.values())
            + list(REPOSITORY_FILES.values())
        )
        if not path.exists()
    ]

    assert not missing, (
        "Phase 2 closure requires these service/repository boundaries: "
        + ", ".join(missing)
    )


def test_required_repository_protocols_exist():
    classes = _top_level_class_names(INTERFACES)

    required = {
        "CourseRepository",
        "NoteRepository",
        "ResourceRepository",
        "KnowledgeRepository",
        "CourseKnowledgeContext",
    }

    assert required.issubset(classes), (
        "Missing Phase 2 repository protocols: "
        + ", ".join(sorted(required - classes))
    )


def test_application_services_are_non_interactive():
    for name, path in CORE_SERVICE_FILES.items():
        calls = _called_builtin_names(path)

        assert "input" not in calls, (
            f"{name} service must not call input(); terminal input belongs in CLI adapters"
        )
        assert "print" not in calls, (
            f"{name} service must not call print(); rendering belongs in CLI adapters"
        )

        assert not any(
            module.startswith("personal_learning_assistant.ui")
            for module in _imported_modules(path)
        ), f"{name} service imports a UI/CLI module"


def test_application_services_do_not_eagerly_import_optional_ai_providers():
    for name, path in CORE_SERVICE_FILES.items():
        imported = {
            module.split(".", 1)[0]
            for module in _imported_modules(path)
        }
        forbidden = imported & OPTIONAL_PROVIDER_ROOTS

        assert not forbidden, (
            f"{name} service eagerly imports optional provider packages: "
            + ", ".join(sorted(forbidden))
        )


def test_course_service_and_repository_do_not_depend_on_legacy_course_manager():
    for path in (
        CORE_SERVICE_FILES["course"],
        REPOSITORY_FILES["course"],
    ):
        assert not _imports_module(path, "course_manager"), (
            f"{path.relative_to(ROOT)} still imports course_manager"
        )


def test_course_knowledge_cycle_is_broken():
    knowledge_root = ROOT / "knowledge.py"
    course_cli = (
        ROOT
        / "personal_learning_assistant"
        / "ui"
        / "cli"
        / "course_cli.py"
    )

    assert not _imports_module(
        knowledge_root,
        "course_manager",
    ), "knowledge.py still imports course_manager"

    assert not _imports_module(
        course_cli,
        "knowledge",
    ), "CourseCLI still imports legacy knowledge.py"

    assert not _imports_module(
        REPOSITORY_FILES["knowledge_course_context"],
        "course_manager",
    ), "Knowledge course context still imports course_manager"


def test_academic_agent_routing_service_is_view_neutral():
    path = CORE_SERVICE_FILES["agent"]

    imported_roots = {
        module.split(".", 1)[0]
        for module in _imported_modules(path)
    }

    forbidden = (
        imported_roots
        & AGENT_TERMINAL_WORKFLOW_MODULES
    )

    assert not forbidden, (
        "AcademicAgentService imports terminal feature workflows: "
        + ", ".join(sorted(forbidden))
    )

    calls = _called_builtin_names(path)
    assert "input" not in calls
    assert "print" not in calls


def test_legacy_compatibility_facades_remain_present():
    expected_functions = {
        ROOT / "course_manager.py": {
            "_build_course_cli",
            "_link_document_interactive",
        },
        ROOT / "notes.py": {
            "_build_notes_cli",
        },
        ROOT / "resources.py": {
            "_build_resources_cli",
        },
        ROOT / "knowledge.py": {
            "_build_knowledge_service",
            "_build_course_knowledge_context",
            "find_documents",
            "describe_source",
        },
        ROOT / "personal_academic_agent.py": {
            "route_request",
            "classify_intent",
        },
    }

    for path, expected in expected_functions.items():
        actual = _top_level_function_names(path)
        missing = expected - actual

        assert not missing, (
            f"{path.name} lost compatibility facade functions: "
            + ", ".join(sorted(missing))
        )


def test_phase2_package_has_not_started_sqlite_cutover():
    checked = (
        list(CORE_SERVICE_FILES.values())
        + list(REPOSITORY_FILES.values())
    )

    offenders = [
        str(path.relative_to(ROOT))
        for path in checked
        if _imports_module(path, "sqlite3")
    ]

    assert not offenders, (
        "Phase 2 must keep JSON/current files authoritative; "
        "SQLite imports found in: "
        + ", ".join(offenders)
    )


def test_phase2_root_has_no_production_learning_assistant_database():
    db_path = ROOT / "data" / "learning_assistant.db"

    assert not db_path.exists(), (
        "data/learning_assistant.db already exists. "
        "Phase 3 must begin only after Phase 2 closure and migration tooling review."
    )
