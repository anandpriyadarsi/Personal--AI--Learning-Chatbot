"""Bounded authoring-archive and source-identity safety tests (synthetic only)."""
import io
import sqlite3
import zipfile

import pytest

from personal_learning_assistant.learning_studio.archive import read_zip
from personal_learning_assistant.learning_studio.portable_vedic_import import (
    TEMPLATE,
    _registered_source,
    bind_vedic_work_zip,
    is_vedic_authoring_archive,
)
from personal_learning_assistant.learning_studio.validation import PackageError


def archive(members):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path, content in members.items():
            zip_file.writestr(path, content)
    return out.getvalue()


def test_ordinary_canonical_archives_are_not_mistaken_for_portable_work(tmp_path):
    raw = archive({"module.json": b'{"schema":"anvaya.learning-module.v2"}'})
    assert not is_vedic_authoring_archive(read_zip(raw, pilot=True))


def test_work_zip_without_original_pdf_cannot_bind_or_stage(tmp_path):
    raw = archive({TEMPLATE: b'{"schema":"anvaya.learning-module.v2"}'})
    assert is_vedic_authoring_archive(read_zip(raw, pilot=True))
    with pytest.raises(PackageError, match="incomplete"):
        bind_vedic_work_zip(raw, database=tmp_path / "nonexistent.sqlite3", roots={})


def test_portable_zip_cannot_escape_archive_boundary(tmp_path):
    raw = archive({
        TEMPLATE: b'{"schema":"anvaya.learning-module.v2"}',
        "../../outside.py": b"raise RuntimeError('uploaded code should not run')",
    })
    with pytest.raises(PackageError, match="Unsafe archive path"):
        bind_vedic_work_zip(raw, database=tmp_path / "nonexistent.sqlite3", roots={})


def test_registry_binding_refuses_unregistered_or_invented_source_id(tmp_path, monkeypatch):
    import hashlib
    from personal_learning_assistant.learning_studio import portable_vedic_import as adapter

    source = b"%PDF-1.7\nsynthetic academic fixture"
    monkeypatch.setattr(adapter, "SOURCE_SHA", hashlib.sha256(source).hexdigest())
    db = tmp_path / "registry.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TABLE knowledge_documents (id TEXT PRIMARY KEY, "
            "content_hash TEXT, mime_type TEXT)"
        )
        connection.execute(
            "INSERT INTO knowledge_documents VALUES (?,?,?)",
            ("real-id", hashlib.sha256(source).hexdigest(), "application/pdf"),
        )
    class Loader:
        def __init__(self, db_path, roots):
            self.db_path = db_path
            self.roots = roots
        def __call__(self, source_id):
            assert source_id == "real-id"
            return source
    monkeypatch.setattr(adapter, "RegisteredSources", Loader)
    assert _registered_source(source, database=db, roots={},
                              requested_id="") == "real-id"
    with pytest.raises(PackageError, match="not registered"):
        _registered_source(source, database=db, roots={}, requested_id="invented-id")
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO knowledge_documents VALUES (?,?,?)",
            ("duplicate-id", hashlib.sha256(source).hexdigest(), "application/pdf"),
        )
    with pytest.raises(PackageError, match="several identical"):
        _registered_source(source, database=db, roots={}, requested_id="")
