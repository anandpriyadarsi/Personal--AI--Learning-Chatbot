"""Optional vault connections never become a second authority for native notes."""
import io
import stat
import zipfile

import pytest

from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import ObsidianWorkspaceReader
from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepository
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesValidationError, AnvayaNotesUnavailableError
from personal_learning_assistant.services.obsidian_workspace_service import ObsidianWorkspaceService


def archive(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        for name, value in entries:
            zip_file.writestr(name, value)
    return buffer.getvalue()


@pytest.fixture
def connected(tmp_path, monkeypatch):
    import obsidian_integration as config
    from personal_learning_assistant.services.obsidian_connection_service import ObsidianConnectionService
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(config, "CONFIG_FILE", str(tmp_path / "data" / "obsidian.json"))
    workspace = ObsidianWorkspaceService(config, ObsidianWorkspaceReader)
    notes = AnvayaNotesService(AnvayaNotesRepository(notes_path=tmp_path / "notes.json", assets_root=tmp_path / "assets"))
    service = ObsidianConnectionService(config, workspace, notes, tmp_path / "data" / "obsidian_snapshots")
    return service, config, notes


def test_snapshot_uses_existing_reader_and_copies_selected_markdown_independently(connected):
    service, config, notes = connected
    result = service.import_snapshot(archive([
        ("My Vault/.obsidian/app.json", "{}"),
        ("My Vault/Math/LU.md", "# LU\n\nA = LU\n[[Vector]]"),
        ("My Vault/Vector.md", "# Vector\n[[Math/LU]]"),
        ("My Vault/image.png", b"ignored attachment"),
    ]))
    assert result["markdown_files"] == 2
    assert service.status()["mode"] == "snapshot"
    assert service.workspace.workspace()["summary"]["markdown_files"] == 2
    assert service.workspace.note_preview("Math/LU.md")["backlinks"]
    copied = service.copy_notes(["Math/LU.md"])
    assert len(copied) == 1
    assert notes.repository.get_note(copied[0]["id"])["body"] == "# LU\n\nA = LU\n[[Vector]]"
    original = config.get_vault_path()
    service.disconnect()
    assert config.load_config()["vault_path"] == ""
    from pathlib import Path
    assert (Path(original) / "Math" / "LU.md").exists()
    assert notes.reader(copied[0]["id"])["title"] == "LU"


@pytest.mark.parametrize("bad_name", ["../escape.md", "/absolute.md", "C:/absolute.md", "Vault/../escape.md", "Vault\\escape.md"])
def test_snapshot_rejects_unsafe_paths_without_changing_connection(connected, bad_name):
    service, config, _ = connected
    before = config.load_config()
    with pytest.raises(ValueError):
        service.import_snapshot(archive([("Vault/.obsidian/", b""), (bad_name, "bad")]))
    assert config.load_config() == before
    assert not list(service.snapshots_root.glob("*"))


def test_snapshot_rejects_symlinks_and_missing_markers(connected):
    service, config, _ = connected
    entry = zipfile.ZipInfo("Vault/link.md")
    entry.create_system = 3
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    for entries in [[(".obsidian/", b""), (entry, "../../private")], [("Plain.md", "# Plain")],
                    [(".obsidian", "not a directory"), ("Plain.md", "# Plain")]]:
        with pytest.raises(ValueError):
            service.import_snapshot(archive(entries))
    assert not config.load_config()["enabled"]


def test_snapshot_rejects_expansion_bounds_and_preserves_old_snapshot(connected, monkeypatch):
    from personal_learning_assistant.services import obsidian_connection_service as module
    service, config, _ = connected
    service.import_snapshot(archive([(".obsidian/", b""), ("Good.md", "# Good")]))
    before = config.load_config()
    monkeypatch.setattr(module, "MAX_EXPANDED_BYTES", 5)
    with pytest.raises(ValueError):
        service.import_snapshot(archive([(".obsidian/", b""), ("Too big.md", "123456")]))
    assert config.load_config() == before
    assert service.workspace.note_preview("Good.md")["text"] == "# Good"


def test_failed_config_write_rolls_back_new_snapshot(connected, monkeypatch):
    service, config, _ = connected
    before = config.load_config()
    def fail(_):
        raise OSError("disk full")
    monkeypatch.setattr(config, "save_config", fail)
    with pytest.raises(OSError):
        service.import_snapshot(archive([(".obsidian/", b""), ("Good.md", "# Good")]))
    assert config.load_config() == before
    assert not list(service.snapshots_root.glob("*"))


def test_selection_validation_happens_before_any_note_is_created(connected):
    service, _, notes = connected
    service.import_snapshot(archive([(".obsidian/", b""), ("Good.md", "# Good")]))
    with pytest.raises(ValueError):
        service.copy_notes(["Good.md", "../outside.md"])
    assert notes.library()["cards"] == []


def test_note_and_archive_size_limits_are_enforced_before_any_write(connected, monkeypatch):
    from personal_learning_assistant.services import obsidian_connection_service as module
    service, config, _ = connected
    monkeypatch.setattr(module, "MAX_NOTE_BYTES", 5)
    with pytest.raises(ValueError):
        service.import_snapshot(archive([(".obsidian/", b""), ("Big.md", "123456")]))
    monkeypatch.setattr(module, "MAX_ARCHIVE_BYTES", 5)
    with pytest.raises(ValueError):
        service.import_snapshot(b"123456")
    assert not config.load_config()["enabled"]


def test_batch_native_copy_validates_all_payloads_before_one_atomic_save(connected, monkeypatch):
    _, _, notes = connected
    with pytest.raises(AnvayaNotesValidationError):
        notes.create_typed_notes([{"title": "First", "body": "First"}, {"title": ""}])
    assert notes.library()["cards"] == []
    original = notes.create_typed_note({"title": "Existing", "body": "Keep"})
    from personal_learning_assistant.repositories.json import anvaya_notes_repository as repository_module
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(repository_module.os, "replace", fail)
    with pytest.raises(AnvayaNotesUnavailableError):
        notes.create_typed_notes([{"title": "First", "body": "First"}, {"title": "Second"}])
    assert [card["id"] for card in notes.library()["cards"]] == [original["id"]]


def test_atomic_configuration_failure_preserves_previous_bytes(connected, monkeypatch):
    service, config, _ = connected
    service.import_snapshot(archive([(".obsidian/", b""), ("Good.md", "# Good")]))
    from pathlib import Path
    previous = Path(config.CONFIG_FILE).read_bytes()
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(config.os, "replace", fail)
    with pytest.raises(OSError):
        service.disconnect()
    assert Path(config.CONFIG_FILE).read_bytes() == previous
    assert sorted(p.name for p in Path(config.DATA_DIR).iterdir()) == ["obsidian.json", "obsidian_snapshots"]


def test_folder_connection_resets_snapshot_metadata_and_disconnect_preserves_source(connected, tmp_path):
    service, config, _ = connected
    service.import_snapshot(archive([(".obsidian/", b""), ("Good.md", "# Good")]))
    vault = tmp_path / "Desktop Vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Original.md").write_text("# Original")
    service.connect_folder(str(vault))
    assert service.status()["mode"] == "folder"
    assert not config.load_config().get("snapshot_name")
    service.disconnect()
    assert (vault / "Original.md").read_text() == "# Original"


def test_snapshot_is_restorable_at_a_new_runtime_root(connected, tmp_path, monkeypatch):
    from personal_learning_assistant.android_backup import export_backup, stage_restore, apply_pending_restore
    service, config, _ = connected
    service.import_snapshot(archive([("Vault/.obsidian/", b""), ("Vault/Keep.md", "# Keep")]))
    raw = export_backup(tmp_path)
    restored = tmp_path / "new-device"
    stage_restore(restored, raw)
    assert apply_pending_restore(restored)
    monkeypatch.setattr(config, "DATA_DIR", str(restored / "data"))
    monkeypatch.setattr(config, "CONFIG_FILE", str(restored / "data" / "obsidian.json"))
    assert str(restored) in config.get_vault_path()
    assert service.workspace.note_preview("Keep.md")["text"] == "# Keep"


def test_mobile_settings_upload_copy_disconnect_and_csrf(connected):
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.ui.web.obsidian_connections import register_obsidian_connections
    service, config, notes = connected
    app = create_app({"TESTING": True, "PRIVATE_MOBILE_MODE": True,
                      "OBSIDIAN_CONNECTION_SERVICE_FACTORY": lambda: service,
                      "OBSIDIAN_WORKSPACE_SERVICE_FACTORY": lambda: service.workspace})
    if "obsidian_connections" not in app.blueprints:
        register_obsidian_connections(app)
    client = app.test_client()
    page = client.get("/library/connected-sources/obsidian")
    assert page.status_code == 200
    assert b"ZIP snapshot" in page.data
    assert b'name="vault_path"' not in page.data
    assert client.post("/library/connected-sources/obsidian/disconnect").status_code == 403
    token = app.extensions["notes_media_csrf"]
    assert client.post("/library/connected-sources/obsidian/connect", data={"csrf_token": token, "vault_path": "/tmp"}).status_code == 400
    response = client.post("/library/connected-sources/obsidian/snapshot", data={
        "csrf_token": token,
        "snapshot": (io.BytesIO(archive([(".obsidian/", b""), ("Good.md", "# Good")])), "vault.zip"),
    })
    assert response.status_code == 303
    page = client.get("/obsidian")
    assert page.status_code == 200
    assert b"Snapshot" in page.data
    assert b'name="vault_path"' not in page.data
    assert b"Copy selected to ANVAYA Notes" in page.data
    response = client.post("/library/connected-sources/obsidian/import", data={"csrf_token": token, "paths": ["Good.md"]})
    assert response.status_code == 303
    assert notes.library()["cards"][0]["title"] == "Good"
    assert client.post("/library/connected-sources/obsidian/disconnect", data={"csrf_token": token}).status_code == 303
    assert not config.get_vault_path()


def test_stale_desktop_connection_on_android_offers_snapshot_reconnect(connected):
    from personal_learning_assistant.ui.web import create_app
    service, config, _ = connected
    config.save_config({"enabled": True, "vault_path": "C:\\Users\\student\\Vault"})
    app = create_app({"TESTING": True, "PRIVATE_MOBILE_MODE": True,
                      "OBSIDIAN_CONNECTION_SERVICE_FACTORY": lambda: service,
                      "OBSIDIAN_WORKSPACE_SERVICE_FACTORY": lambda: service.workspace})
    client = app.test_client()
    page = client.get("/obsidian")
    assert page.status_code == 200
    assert b"Unavailable" in page.data
    assert b"Connection settings" in page.data
    assert b'name="vault_path"' not in page.data
    settings = client.get("/library/connected-sources/obsidian")
    assert b"Import snapshot" in settings.data
    assert b'name="vault_path"' not in settings.data
