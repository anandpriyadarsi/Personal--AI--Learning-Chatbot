import builtins
import importlib
import sys
import types

import pytest


OPTIONAL_PACKAGES = {
    "requests",
    "fastembed",
    "numpy",
    "youtube_transcript_api",
    "fitz",
    "PIL",
    "dotenv",
}


def _fresh_main_import(monkeypatch):
    sys.modules.pop("main", None)

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        root_name = name.split(".", 1)[0]

        if root_name in OPTIONAL_PACKAGES:
            raise ModuleNotFoundError(
                f"blocked optional package: {root_name}"
            )

        return real_import(
            name,
            *args,
            **kwargs
        )

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )

    return importlib.import_module(
        "main"
    )


def test_main_import_succeeds_without_optional_ai_packages(
    monkeypatch,
):
    module = _fresh_main_import(
        monkeypatch
    )

    assert hasattr(module, "run_chatbot")
    assert hasattr(module, "show_menu")
    assert len(module.FEATURE_ACTIONS) == 37


def test_main_import_does_not_eagerly_import_optional_feature_modules(
    monkeypatch,
):
    optional_feature_modules = {
        "semantic_retrieval",
        "hybrid_retrieval",
        "rag_answer",
        "youtube_ingestion",
        "youtube_analysis",
        "vision_math_reader",
    }

    for module_name in optional_feature_modules:
        sys.modules.pop(
            module_name,
            None
        )

    _fresh_main_import(
        monkeypatch
    )

    for module_name in optional_feature_modules:
        assert module_name not in sys.modules


def test_core_notes_resources_and_courses_remain_registered():
    import main

    assert main.FEATURE_ACTIONS["2"] == (
        "notes",
        "view_notes",
    )
    assert main.FEATURE_ACTIONS["6"] == (
        "resources",
        "view_resources",
    )
    assert main.FEATURE_ACTIONS["23"] == (
        "course_manager",
        "course_manager_menu",
    )


def test_feature_is_loaded_only_when_selected(monkeypatch):
    import main

    calls = []

    fake_module = types.ModuleType(
        "fake_feature"
    )

    def fake_action():
        calls.append("ran")
        return "ok"

    fake_module.fake_action = fake_action

    real_import_module = main.import_module

    def fake_import_module(name):
        if name == "fake_feature":
            calls.append("imported")
            return fake_module

        return real_import_module(name)

    monkeypatch.setattr(
        main,
        "import_module",
        fake_import_module,
    )

    result = main._run_feature(
        "fake_feature",
        "fake_action",
    )

    assert result == "ok"
    assert calls == [
        "imported",
        "ran",
    ]


def test_missing_optional_feature_does_not_crash_main(
    monkeypatch,
    capsys,
):
    import main

    def fail_import(name):
        raise ModuleNotFoundError(
            "optional dependency unavailable"
        )

    monkeypatch.setattr(
        main,
        "import_module",
        fail_import,
    )

    result = main._run_feature(
        "rag_answer",
        "rag_chat_loop",
    )

    assert result is None

    output = capsys.readouterr().out
    assert "Feature unavailable." in output
    assert "rag_answer.rag_chat_loop" in output


def test_all_legacy_v13_menu_choices_are_preserved():
    import main

    expected_choices = {
        str(number)
        for number in range(1, 39)
        if number != 16
    }

    assert set(
        main.FEATURE_ACTIONS
    ) == expected_choices
