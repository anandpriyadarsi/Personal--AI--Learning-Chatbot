import ast
import builtins
from copy import deepcopy
import importlib
from pathlib import Path
import sys

import course_manager

from personal_learning_assistant.domain import course_normalization
from personal_learning_assistant.services import course_service
from personal_learning_assistant.repositories.json import course_repository


def _imports_legacy_course_manager(module):
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "course_manager":
            return True

        if isinstance(node, ast.Import):
            if any(alias.name == "course_manager" for alias in node.names):
                return True

    return False


def test_course_service_no_longer_imports_legacy_course_manager():
    assert not _imports_legacy_course_manager(course_service)


def test_course_repository_no_longer_imports_legacy_course_manager():
    assert not _imports_legacy_course_manager(course_repository)


def test_new_course_layer_imports_when_legacy_course_manager_is_blocked(monkeypatch):
    module_names = (
        "personal_learning_assistant.domain.course_normalization",
        "personal_learning_assistant.services.course_service",
        "personal_learning_assistant.repositories.json.course_repository",
    )

    saved = {
        name: sys.modules.get(name)
        for name in module_names
    }

    for name in module_names:
        sys.modules.pop(name, None)

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "course_manager" or name.startswith("course_manager."):
            raise ModuleNotFoundError(
                "legacy course_manager blocked by Fix 13 test"
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )

    try:
        normalization = importlib.import_module(module_names[0])
        service = importlib.import_module(module_names[1])
        repository = importlib.import_module(module_names[2])

        assert normalization is not None
        assert service is not None
        assert repository is not None
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
            if saved[name] is not None:
                sys.modules[name] = saved[name]


def test_course_normalization_status_sets_match_compatibility_facade():
    for constant_name in (
        "VALID_COURSE_STATUSES",
        "VALID_TOPIC_STATUSES",
        "VALID_SOURCE_TYPES",
    ):
        if hasattr(course_normalization, constant_name):
            assert (
                getattr(course_normalization, constant_name)
                == getattr(course_manager, constant_name)
            )


def test_topic_normalization_matches_legacy_facade():
    if not hasattr(course_normalization, "_normalise_topic"):
        return

    cases = [
        "Linear Systems",
        {
            "name": "  LU   Factorization ",
            "status": "in progress",
            "confidence": "4",
            "last_updated": "2026-09-14T04:00:00",
        },
        {
            "name": "Vector Spaces",
            "status": "practiced",
            "confidence": 9,
            "last_updated": "2026-09-14T04:01:00",
        },
        {
            "name": "Rank",
            "status": "unknown-status",
            "confidence": "bad",
            "last_updated": None,
        },
    ]

    for raw in cases:
        assert (
            course_normalization._normalise_topic(deepcopy(raw))
            == course_manager._normalise_topic(deepcopy(raw))
        )


def test_course_data_normalization_matches_legacy_facade():
    if not hasattr(course_normalization, "_normalise_data"):
        return

    raw = {
        "version": 1,
        "active_course_id": "ma103n",
        "courses": [
            {
                "id": "ma103n",
                "code": " ma103n ",
                "name": " Linear   Algebra ",
                "semester": "1",
                "status": "active",
                "created_at": "2026-08-20T10:00:00",
                "updated_at": "2026-09-14T04:00:00",
                "topics": [
                    {
                        "name": "LU Factorization",
                        "status": "practiced",
                        "confidence": 3,
                        "last_updated": "2026-09-13T20:00:00",
                    }
                ],
            }
        ],
        "document_links": {
            "base:knowledge/example.md": {
                "course_id": "ma103n",
                "topic": "LU Factorization",
                "source_type": "document",
                "display_path": "knowledge/example.md",
                "linked_at": "2026-09-13T21:00:00",
            }
        },
    }

    assert (
        course_normalization._normalise_data(deepcopy(raw))
        == course_manager._normalise_data(deepcopy(raw))
    )


def test_fix13_keeps_root_course_manager_compatibility_surface():
    for name in (
        "load_course_data",
        "list_courses",
        "find_course",
        "get_active_course",
        "create_course",
        "add_topic",
        "update_topic_status",
        "get_course_progress",
    ):
        assert callable(getattr(course_manager, name, None))
