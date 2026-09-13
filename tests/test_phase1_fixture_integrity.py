import builtins
import hashlib
import importlib
import os
import sys
from pathlib import Path

import pytest

import config


OPTIONAL_PACKAGES = {
    "requests",
    "fastembed",
    "numpy",
    "youtube_transcript_api",
    "fitz",
    "PIL",
    "dotenv",
}


FIXTURE_LOADERS = [
    ("notes.json", "notes", ("load_notes",)),
    ("resources.json", "resources", ("load_resources",)),
    ("courses.json", "course_manager", ("load_course_data",)),
    ("learning_memory.json", "learning_memory", ("load_memory",)),
    ("course_progress_history.json", "academic_progress", ("load_history",)),
    ("weekly_study_plans.json", "weekly_planner", ("load_store",)),
    (
        "multi_course_weekly_plans.json",
        "multi_course_planner",
        ("load_store",),
    ),
    ("assessments.json", "assignment_exam_assistant", ("load_store",)),
    (
        "assessment_workspace.json",
        "assessment_question_workspace",
        ("load_store",),
    ),
    ("obsidian_config.json", "obsidian_integration", ("load_config",)),
]


def _sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _data_manifest():
    data_dir = Path(config.DATA_DIR)

    return {
        path.relative_to(data_dir).as_posix(): (
            path.stat().st_size,
            _sha256(path),
        )
        for path in data_dir.rglob("*")
        if path.is_file()
    }


def _is_inside_data(path_value):
    try:
        path = Path(
            os.fspath(path_value)
        ).resolve()
    except (TypeError, ValueError):
        return False

    data_dir = Path(
        config.DATA_DIR
    ).resolve()

    try:
        path.relative_to(data_dir)
        return True
    except ValueError:
        return False


@pytest.fixture
def protect_data_writes(monkeypatch):
    """
    Fail immediately if a read-only fixture loader attempts
    to write, replace, remove, or rename a file under data/.
    """
    real_open = builtins.open
    real_replace = os.replace
    real_remove = os.remove
    real_unlink = os.unlink
    real_rename = os.rename

    def guarded_open(file, mode="r", *args, **kwargs):
        is_write_mode = any(
            flag in mode
            for flag in ("w", "a", "x", "+")
        )

        if (
            is_write_mode
            and _is_inside_data(file)
        ):
            raise AssertionError(
                f"Read-only test attempted data write: {file} ({mode})"
            )

        return real_open(
            file,
            mode,
            *args,
            **kwargs,
        )

    def guarded_replace(src, dst, *args, **kwargs):
        if _is_inside_data(src) or _is_inside_data(dst):
            raise AssertionError(
                f"Read-only test attempted data replace: {src} -> {dst}"
            )

        return real_replace(
            src,
            dst,
            *args,
            **kwargs,
        )

    def guarded_remove(path, *args, **kwargs):
        if _is_inside_data(path):
            raise AssertionError(
                f"Read-only test attempted data remove: {path}"
            )

        return real_remove(
            path,
            *args,
            **kwargs,
        )

    def guarded_unlink(path, *args, **kwargs):
        if _is_inside_data(path):
            raise AssertionError(
                f"Read-only test attempted data unlink: {path}"
            )

        return real_unlink(
            path,
            *args,
            **kwargs,
        )

    def guarded_rename(src, dst, *args, **kwargs):
        if _is_inside_data(src) or _is_inside_data(dst):
            raise AssertionError(
                f"Read-only test attempted data rename: {src} -> {dst}"
            )

        return real_rename(
            src,
            dst,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        builtins,
        "open",
        guarded_open,
    )
    monkeypatch.setattr(
        os,
        "replace",
        guarded_replace,
    )
    monkeypatch.setattr(
        os,
        "remove",
        guarded_remove,
    )
    monkeypatch.setattr(
        os,
        "unlink",
        guarded_unlink,
    )
    monkeypatch.setattr(
        os,
        "rename",
        guarded_rename,
    )


@pytest.mark.read_only
def test_core_notes_resources_courses_start_without_optional_ai_packages(
    monkeypatch,
):
    """
    Phase 1 gate:
    notes, resources and courses must import without optional
    semantic/RAG/vision/YouTube packages.
    """
    for name in (
        "notes",
        "resources",
        "course_manager",
    ):
        sys.modules.pop(
            name,
            None,
        )

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
            **kwargs,
        )

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )

    notes = importlib.import_module(
        "notes"
    )
    resources = importlib.import_module(
        "resources"
    )
    courses = importlib.import_module(
        "course_manager"
    )

    assert callable(
        getattr(notes, "load_notes")
    )
    assert callable(
        getattr(resources, "load_resources")
    )
    assert callable(
        getattr(courses, "load_course_data")
    )


@pytest.mark.read_only
@pytest.mark.parametrize(
    "file_name,module_name,loader_names",
    FIXTURE_LOADERS,
)
def test_existing_persisted_fixture_loads_without_data_write(
    file_name,
    module_name,
    loader_names,
    protect_data_writes,
):
    """
    Phase 1 gate:
    every supplied persisted fixture must load and the complete
    data/ file manifest must remain byte-for-byte unchanged.
    """
    data_dir = Path(
        config.DATA_DIR
    )
    fixture_path = (
        data_dir
        / file_name
    )

    assert fixture_path.exists(), (
        f"Required Phase 1 fixture is missing: {fixture_path}"
    )

    before = _data_manifest()

    module = importlib.import_module(
        module_name
    )

    loader = None

    for loader_name in loader_names:
        candidate = getattr(
            module,
            loader_name,
            None,
        )

        if callable(candidate):
            loader = candidate
            break

    assert loader is not None, (
        f"No expected fixture loader found in {module_name}: "
        f"{loader_names}"
    )

    loaded = loader()

    # Loading may legitimately normalize in memory or return an empty
    # collection (resources.json is known to be a zero-byte legacy input).
    assert loaded is not None

    after = _data_manifest()

    assert after == before, (
        f"Read-only loader changed data/ while loading {file_name}"
    )
