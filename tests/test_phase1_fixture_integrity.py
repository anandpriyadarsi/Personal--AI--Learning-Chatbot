import builtins
import hashlib
import importlib
import os
import shutil
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

FIXTURE_NAMES = {
    file_name
    for file_name, _module, _loaders
    in FIXTURE_LOADERS
}

TESTS_DIR = Path(__file__).resolve().parent
SANITIZED_FIXTURE_DIR = (
    TESTS_DIR
    / "fixtures"
    / "phase1"
)

# Capture the real configured data directory before tests monkeypatch config.
REAL_DATA_DIR = Path(
    config.DATA_DIR
).resolve()


def _sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _manifest(root):
    root = Path(root)

    if not root.exists():
        return {}

    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_size,
            _sha256(path),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _is_inside(path_value, root):
    try:
        path = Path(
            os.fspath(path_value)
        ).resolve()
        root = Path(root).resolve()
    except (
        TypeError,
        ValueError,
    ):
        return False

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_basename(value):
    try:
        return Path(
            os.fspath(value)
        ).name
    except (
        TypeError,
        ValueError,
    ):
        return None


def _redirect_config_paths(
    monkeypatch,
    isolated_data_dir,
):
    monkeypatch.setattr(
        config,
        "DATA_DIR",
        str(isolated_data_dir),
        raising=False,
    )

    for name, value in list(
        vars(config).items()
    ):
        basename = _path_basename(
            value
        )

        if basename in FIXTURE_NAMES:
            monkeypatch.setattr(
                config,
                name,
                str(
                    isolated_data_dir
                    / basename
                ),
                raising=False,
            )


def _redirect_module_paths(
    monkeypatch,
    module,
    isolated_data_dir,
):
    """
    Redirect legacy module-level file constants without hard-coding every
    historical constant name.

    Phase 1/2 modules use names such as NOTES_FILE, RESOURCES_FILE, HISTORY_FILE,
    STORE_FILE, CONFIG_FILE, etc.  Matching by the known fixture basename keeps
    this test compatible with those legacy names while guaranteeing no loader
    reaches the developer's private data directory.
    """
    for name, value in list(
        vars(module).items()
    ):
        if name == "DATA_DIR":
            monkeypatch.setattr(
                module,
                name,
                str(isolated_data_dir),
                raising=False,
            )
            continue

        basename = _path_basename(
            value
        )

        if basename in FIXTURE_NAMES:
            monkeypatch.setattr(
                module,
                name,
                str(
                    isolated_data_dir
                    / basename
                ),
                raising=False,
            )


@pytest.fixture
def isolated_data_dir(
    tmp_path,
    monkeypatch,
):
    assert SANITIZED_FIXTURE_DIR.is_dir(), (
        "Tracked sanitized fixture directory is missing: "
        f"{SANITIZED_FIXTURE_DIR}"
    )

    isolated = (
        tmp_path
        / "data"
    )

    shutil.copytree(
        SANITIZED_FIXTURE_DIR,
        isolated,
    )

    _redirect_config_paths(
        monkeypatch,
        isolated,
    )

    return isolated


@pytest.fixture
def protect_data_writes(
    monkeypatch,
    isolated_data_dir,
):
    """
    Fail immediately if a read-only loader attempts to mutate either the
    temporary fixture store or the developer's real configured data directory.
    """
    protected_roots = {
        Path(
            isolated_data_dir
        ).resolve(),
        REAL_DATA_DIR,
    }

    real_open = builtins.open
    real_replace = os.replace
    real_remove = os.remove
    real_unlink = os.unlink
    real_rename = os.rename

    def protected(path):
        return any(
            _is_inside(
                path,
                root,
            )
            for root in protected_roots
        )

    def guarded_open(
        file,
        mode="r",
        *args,
        **kwargs,
    ):
        is_write_mode = any(
            flag in mode
            for flag in (
                "w",
                "a",
                "x",
                "+",
            )
        )

        if (
            is_write_mode
            and protected(file)
        ):
            raise AssertionError(
                "Read-only test attempted data write: "
                f"{file} ({mode})"
            )

        return real_open(
            file,
            mode,
            *args,
            **kwargs,
        )

    def guarded_replace(
        src,
        dst,
        *args,
        **kwargs,
    ):
        if (
            protected(src)
            or protected(dst)
        ):
            raise AssertionError(
                "Read-only test attempted data replace: "
                f"{src} -> {dst}"
            )

        return real_replace(
            src,
            dst,
            *args,
            **kwargs,
        )

    def guarded_remove(
        path,
        *args,
        **kwargs,
    ):
        if protected(path):
            raise AssertionError(
                "Read-only test attempted data remove: "
                f"{path}"
            )

        return real_remove(
            path,
            *args,
            **kwargs,
        )

    def guarded_unlink(
        path,
        *args,
        **kwargs,
    ):
        if protected(path):
            raise AssertionError(
                "Read-only test attempted data unlink: "
                f"{path}"
            )

        return real_unlink(
            path,
            *args,
            **kwargs,
        )

    def guarded_rename(
        src,
        dst,
        *args,
        **kwargs,
    ):
        if (
            protected(src)
            or protected(dst)
        ):
            raise AssertionError(
                "Read-only test attempted data rename: "
                f"{src} -> {dst}"
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
    Core notes/resources/courses must import without optional semantic,
    RAG, vision, or YouTube packages.
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

    def guarded_import(
        name,
        *args,
        **kwargs,
    ):
        root_name = name.split(
            ".",
            1,
        )[0]

        if root_name in OPTIONAL_PACKAGES:
            raise ModuleNotFoundError(
                "blocked optional package: "
                f"{root_name}"
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
        getattr(
            notes,
            "load_notes",
        )
    )
    assert callable(
        getattr(
            resources,
            "load_resources",
        )
    )
    assert callable(
        getattr(
            courses,
            "load_course_data",
        )
    )


@pytest.mark.read_only
def test_sanitized_fixture_set_is_complete_and_private_data_free():
    names = {
        path.name
        for path in SANITIZED_FIXTURE_DIR.iterdir()
        if path.is_file()
        and path.suffix == ".json"
    }

    assert names == FIXTURE_NAMES

    resources_path = (
        SANITIZED_FIXTURE_DIR
        / "resources.json"
    )
    assert resources_path.stat().st_size == 0

    # The tracked fixture policy deliberately forbids obvious machine-private
    # paths/secrets.  Fixtures use synthetic values only.
    combined = "\n".join(
        path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        for path in SANITIZED_FIXTURE_DIR.iterdir()
        if path.is_file()
    ).casefold()

    forbidden = (
        "\\users\\",
        "/users/",
        "api_key",
        "api-key",
        "sk-",
        ".env",
    )

    assert not any(
        token in combined
        for token in forbidden
    )


@pytest.mark.read_only
@pytest.mark.parametrize(
    "file_name,module_name,loader_names",
    FIXTURE_LOADERS,
)
def test_sanitized_persisted_fixture_loads_without_data_write(
    file_name,
    module_name,
    loader_names,
    isolated_data_dir,
    protect_data_writes,
    monkeypatch,
):
    """
    Every legacy loader must read a tracked synthetic fixture without requiring
    the ignored/private project data directory and without mutating either copy.
    """
    fixture_path = (
        isolated_data_dir
        / file_name
    )

    assert fixture_path.exists(), (
        "Required sanitized fixture is missing: "
        f"{fixture_path}"
    )

    real_before = _manifest(
        REAL_DATA_DIR
    )
    isolated_before = _manifest(
        isolated_data_dir
    )

    module = importlib.import_module(
        module_name
    )

    _redirect_module_paths(
        monkeypatch,
        module,
        isolated_data_dir,
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
        "No expected fixture loader found in "
        f"{module_name}: {loader_names}"
    )

    loaded = loader()

    # Loading may legitimately normalize in memory or return an empty
    # collection. resources.json is intentionally a zero-byte legacy input.
    assert loaded is not None

    assert _manifest(
        isolated_data_dir
    ) == isolated_before, (
        "Read-only loader changed isolated sanitized data "
        f"while loading {file_name}"
    )

    assert _manifest(
        REAL_DATA_DIR
    ) == real_before, (
        "Read-only loader touched the developer's real data "
        f"while loading {file_name}"
    )
