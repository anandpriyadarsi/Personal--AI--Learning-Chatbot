import importlib
import sys
from pathlib import Path


def _fresh_import(name):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_importing_config_does_not_create_directories(monkeypatch):
    calls = []

    def fail_mkdir(self, *args, **kwargs):
        calls.append(self)
        raise AssertionError(
            "config.py attempted to create a directory during import"
        )

    monkeypatch.setattr(
        Path,
        "mkdir",
        fail_mkdir,
    )

    module = _fresh_import("config")

    assert module.BASE_PATH.name
    assert calls == []


def test_config_preserves_legacy_string_constants():
    import config

    assert isinstance(config.BASE_DIR, str)
    assert isinstance(config.DATA_DIR, str)
    assert isinstance(config.BACKUP_DIR, str)
    assert isinstance(config.EXPORT_DIR, str)
    assert isinstance(config.NOTES_FILE, str)
    assert isinstance(config.RESOURCES_FILE, str)

    assert Path(config.NOTES_FILE).name == "notes.json"
    assert Path(config.RESOURCES_FILE).name == "resources.json"


def test_directory_creation_happens_only_when_explicitly_requested(
    tmp_path,
):
    import config

    first = tmp_path / "data"
    second = tmp_path / "exports"

    assert not first.exists()
    assert not second.exists()

    config.ensure_directories(
        [first, second]
    )

    assert first.is_dir()
    assert second.is_dir()


def test_knowledge_paths_reexports_canonical_project_root():
    import config
    import knowledge_paths

    assert knowledge_paths.BASE_DIR == config.BASE_DIR
    assert knowledge_paths.BASE_PATH == config.BASE_PATH
