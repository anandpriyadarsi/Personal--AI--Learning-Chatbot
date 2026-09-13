import importlib
import os
import sys


def _fresh_knowledge_import(monkeypatch):
    sys.modules.pop("knowledge", None)

    calls = []
    real_makedirs = os.makedirs

    def tracked_makedirs(path, *args, **kwargs):
        calls.append(
            os.fspath(path)
        )
        return real_makedirs(
            path,
            *args,
            **kwargs
        )

    monkeypatch.setattr(
        os,
        "makedirs",
        tracked_makedirs,
    )

    module = importlib.import_module(
        "knowledge"
    )

    return module, calls


def test_importing_knowledge_does_not_create_directories(monkeypatch):
    module, calls = _fresh_knowledge_import(
        monkeypatch
    )

    assert hasattr(
        module,
        "find_documents",
    )
    assert calls == []


def test_read_only_document_discovery_does_not_create_missing_folders(
    monkeypatch,
    tmp_path,
):
    import knowledge

    first = tmp_path / "knowledge" / "obsidian"
    second = tmp_path / "knowledge" / "documents"

    monkeypatch.setattr(
        knowledge,
        "LOCAL_KNOWLEDGE_FOLDERS",
        [
            str(first),
            str(second),
        ],
    )
    monkeypatch.setattr(
        knowledge,
        "get_obsidian_markdown_files",
        lambda: [],
    )

    assert not first.exists()
    assert not second.exists()

    documents = knowledge.find_documents()

    assert documents == []
    assert not first.exists()
    assert not second.exists()


def test_explicit_knowledge_folder_setup_creates_directories(
    monkeypatch,
    tmp_path,
):
    import knowledge

    first = tmp_path / "knowledge" / "obsidian"
    second = tmp_path / "knowledge" / "documents"

    monkeypatch.setattr(
        knowledge,
        "LOCAL_KNOWLEDGE_FOLDERS",
        [
            str(first),
            str(second),
        ],
    )

    knowledge.ensure_local_knowledge_folders()

    assert first.is_dir()
    assert second.is_dir()


def test_missing_local_folders_do_not_break_obsidian_discovery(
    monkeypatch,
    tmp_path,
):
    import knowledge

    missing = tmp_path / "missing-local-knowledge"

    monkeypatch.setattr(
        knowledge,
        "LOCAL_KNOWLEDGE_FOLDERS",
        [
            str(missing),
        ],
    )
    monkeypatch.setattr(
        knowledge,
        "get_obsidian_markdown_files",
        lambda: [
            str(
                tmp_path
                / "vault"
                / "Linear Algebra.md"
            )
        ],
    )

    documents = knowledge.find_documents()

    assert documents == [
        os.path.abspath(
            tmp_path
            / "vault"
            / "Linear Algebra.md"
        )
    ]
    assert not missing.exists()
