"""Disposable source identity regressions: originals remain external authority."""
import uuid
from types import SimpleNamespace

import pytest

from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import ObsidianWorkspaceReader
from personal_learning_assistant.services.obsidian_workspace_service import ObsidianWorkspaceService
from personal_learning_assistant.services.obsidian_study_companion_service import ObsidianStudyCompanionService, ObsidianStudyConflictError
from personal_learning_assistant.services.study_item_resolver import obsidian_identity


class Config:
    def __init__(self, root):
        self.value = {"vault_path": str(root), "enabled": True}
    def load_config(self): return dict(self.value)
    def save_config(self, value): self.value = dict(value)
    def validate_vault_path(self, path): return True, ""


def workspace(tmp_path, notes):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".obsidian").mkdir(exist_ok=True)
    for path, text in notes.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return ObsidianWorkspaceService(Config(tmp_path), ObsidianWorkspaceReader)


def test_same_external_uuid_is_connection_scoped(tmp_path):
    external = str(uuid.uuid4())
    text = f"---\nassistant_id: {external}\n---\n# A"
    a = workspace(tmp_path / "a", {"A.md": text}).note_preview("A.md")
    b = workspace(tmp_path / "b", {"A.md": text}).note_preview("A.md")
    assert ObsidianStudyCompanionService._identity(a)[1] != ObsidianStudyCompanionService._identity(b)[1]
    assert obsidian_identity(a).item_id == ObsidianStudyCompanionService._identity(a)[1]


def test_duplicate_uuid_readable_but_cannot_annotate(tmp_path):
    text = f"---\nassistant_id: {uuid.uuid4()}\n---\n# A"
    service = workspace(tmp_path, {"A.md": text, "B.md": text})
    note = service.note_preview("A.md")
    assert note["identity_conflict"] is True
    companion = ObsidianStudyCompanionService(service, None)
    with pytest.raises(ObsidianStudyConflictError):
        companion._current_note("A.md", note["source_hash"])


def test_explicit_manifest_keeps_identity_on_relocation_and_confirmed_rename(tmp_path):
    service = workspace(tmp_path / "original", {"A.md": "same", "Copy.md": "same"})
    service.refresh_manifest()
    a = service.note_preview("A.md")
    assert a["source_item_id"] != service.note_preview("Copy.md")["source_item_id"]
    (tmp_path / "original" / "A.md").rename(tmp_path / "original" / "Renamed.md")
    service.confirm_rename("A.md", "Renamed.md", expected_hash=a["source_hash"])
    assert service.note_preview("Renamed.md")["source_item_id"] == a["source_item_id"]
    import shutil
    shutil.copytree(tmp_path / "original", tmp_path / "relocated")
    config = service.config_api.load_config()
    config["vault_path"] = str(tmp_path / "relocated")
    service.config_api.save_config(config)
    assert service.note_preview("Renamed.md")["source_item_id"] == a["source_item_id"]


def test_snapshot_refresh_keeps_connection_and_source_identity(connected):
    from test_obsidian_connections import archive
    service, config, notes = connected
    service.import_snapshot(archive([(".obsidian/", ""), ("A.md", "# A")]))
    first = service.workspace.note_preview("A.md")
    service.import_snapshot(archive([(".obsidian/", ""), ("A.md", "# A changed"), ("B.md", "new")]), refresh=True)
    second = service.workspace.note_preview("A.md")
    assert first["connection_id"] == second["connection_id"]
    assert first["source_item_id"] == second["source_item_id"]
    assert first["source_hash"] != second["source_hash"]
    copied = service.copy_notes(["A.md"])
    record = notes.repository.get_note(copied[0]["id"])
    assert record["copied_from"]["sha256"] == second["source_hash"]
    assert record["copied_from"]["source_item_id"] == second["source_item_id"]


from test_obsidian_connections import connected


def test_legacy_reconciliation_is_explicit_hash_checked_and_replay_safe():
    import sqlite3
    from personal_learning_assistant.services.obsidian_source_identity_service import ObsidianSourceIdentityService
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE study_item_companion_entries(item_identity TEXT, item_kind TEXT)")
    db.execute("INSERT INTO study_item_companion_entries VALUES ('assistant:11111111-1111-4111-8111-111111111111', 'obsidian_note')")
    from pathlib import Path
    db.executescript((Path(__file__).parents[1] / "personal_learning_assistant/repositories/sqlite/optional_migrations/0019_obsidian_source_identity.sql").read_text())
    service = ObsidianSourceIdentityService(db)
    report = service.preview_identity_migration()
    assert report["unresolved_count"] == 1
    with pytest.raises(ValueError):
        service.apply_identity_migration("wrong")
    first = service.apply_identity_migration(report["report_hash"])
    assert first["unresolved_count"] == 1
    assert service.apply_identity_migration(report["report_hash"])["replayed"] is True
    assert db.execute("SELECT item_identity FROM study_item_companion_entries").fetchone()[0].startswith("assistant:")


def test_unified_repository_direct_legacy_uuid_calls_are_vault_scoped(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.repositories.sqlite.obsidian_study_repository_v2 import SQLiteObsidianStudyRepositoryV2
    db = tmp_path / "study.db"
    apply_migrations(db)
    repo = SQLiteObsidianStudyRepositoryV2(db)
    identity = "assistant:" + str(uuid.uuid4())
    repo.add_entry(entry_id=str(uuid.uuid4()), vault_identity="vault:" + "a" * 64, note_identity=identity, relative_path="A.md", entry_type="key_point", entry_text="Private to A", now="2026-11-12T12:00:00Z", source_hash="f" * 64)
    assert repo.list_entries(vault_identity="vault:" + "b" * 64, note_identity=identity) == ()
    assert len(repo.list_entries(vault_identity="vault:" + "a" * 64, note_identity=identity)) == 1


def test_first_manifest_keeps_qualified_path_history_accessible(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.repositories.sqlite.obsidian_study_repository_v2 import SQLiteObsidianStudyRepositoryV2
    source = workspace(tmp_path / 'vault', {'A.md': '# A'})
    path = tmp_path / 'academic.db'
    apply_migrations(path)
    repository = SQLiteObsidianStudyRepositoryV2(path)
    companion = ObsidianStudyCompanionService(source, repository)
    note = source.note_preview('A.md')
    companion.add_companion_entry(relative_path='A.md', source_hash=note['source_hash'], entry_type='key_point', entry_text='Keep this historical annotation')
    source.refresh_manifest()
    view = companion.reader_view('A.md')
    assert view['legacy_companion']['key_points'][0]['entry_text'] == 'Keep this historical annotation'
    # History remains immutable under its original qualified owner; current
    # annotations are separate and no bare external UUID is adopted.
    assert view['companion']['key_points'] == ()


def test_explicit_relocation_keeps_connection_and_rejects_changed_copy(tmp_path):
    import shutil
    source = workspace(tmp_path / 'old', {'A.md': '# A'})
    source.refresh_manifest()
    before = source.note_preview('A.md')
    shutil.copytree(tmp_path / 'old', tmp_path / 'new')
    source.relocate_connection(str(tmp_path / 'new'), expected_connection_id=before['connection_id'])
    assert source.note_preview('A.md')['source_item_id'] == before['source_item_id']
    assert source.note_preview('A.md')['connection_id'] == before['connection_id']
    (tmp_path / 'old' / 'A.md').write_text('Changed copy')
    with pytest.raises(Exception):
        source.relocate_connection(str(tmp_path / 'old'), expected_connection_id=before['connection_id'])
    assert source.config_api.load_config()['vault_path'] == str(tmp_path / 'new')
