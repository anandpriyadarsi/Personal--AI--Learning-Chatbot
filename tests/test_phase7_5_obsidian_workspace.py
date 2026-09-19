from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import (
    ObsidianWorkspacePathError,
    ObsidianWorkspaceReadError,
    ObsidianWorkspaceReader,
)
from personal_learning_assistant.services.obsidian_workspace_service import (
    MAX_BROWSE_NOTES,
    MAX_QUERY_CHARS,
    MAX_SEARCH_RESULTS,
    ObsidianWorkspaceNotFoundError,
    ObsidianWorkspaceService,
    ObsidianWorkspaceUnavailableError,
    ObsidianWorkspaceValidationError,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-19T00:00:00Z"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


def _hash_tree(root: Path):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.md"))
        if not path.is_symlink()
    }


class FakeConfig:
    def __init__(self, config=None):
        self.config = dict(config or {"vault_path": "", "enabled": False})

    def load_config(self):
        return dict(self.config)

    def normalize_vault_path(self, value):
        return str(Path(str(value).strip().strip('"').strip("'")).expanduser().absolute())

    def validate_vault_path(self, value):
        path = Path(value)
        if not path.is_dir():
            return False, "missing"
        if not (path / ".obsidian").is_dir():
            return False, "not obsidian"
        return True, "valid"

    def set_vault_path(self, value):
        valid, message = self.validate_vault_path(value)
        if not valid:
            return False, message
        self.config["vault_path"] = str(Path(value).absolute())
        self.config["enabled"] = True
        return True, self.config["vault_path"]

    def enable_vault(self):
        valid, message = self.validate_vault_path(self.config.get("vault_path", ""))
        if not valid:
            return False, message
        self.config["enabled"] = True
        return True, self.config["vault_path"]

    def disable_vault(self):
        self.config["enabled"] = False


def _service(vault: Path, *, enabled=True):
    config = FakeConfig({"vault_path": str(vault), "enabled": enabled})
    return ObsidianWorkspaceService(config, ObsidianWorkspaceReader), config


def test_reader_browse_uses_phase53_scanner_and_excludes_internal_folders(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "Math" / "LU.md", "# LU\nA = LU\n")
    _write(vault / ".obsidian" / "ignored.md", "hidden")
    _write(vault / ".trash" / "ignored.md", "hidden")
    _write(vault / ".git" / "ignored.md", "hidden")
    _write(vault / "node_modules" / "ignored.md", "hidden")

    scan = ObsidianWorkspaceReader(vault).scan()

    assert [note.relative_path for note in scan.notes] == ["Math/LU.md"]
    assert scan.blocking_issue_count == 0


def test_reader_rejects_symlink_root_and_skips_symlink_children(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "Real.md", "# Real\n")
    outside = tmp_path / "Outside"
    outside.mkdir()
    _write(outside / "Secret.md", "secret")

    link_root = tmp_path / "VaultLink"
    try:
        link_root.symlink_to(vault, target_is_directory=True)
        (vault / "Linked.md").symlink_to(outside / "Secret.md")
        (vault / "LinkedFolder").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available in this environment")

    with pytest.raises(ObsidianWorkspacePathError):
        ObsidianWorkspaceReader(link_root)

    scan = ObsidianWorkspaceReader(vault).scan()
    assert [note.relative_path for note in scan.notes] == ["Real.md"]
    assert scan.ignored_symlinks >= 2


def test_reader_preview_rejects_escape_absolute_and_non_markdown(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "A.md", "# A\n")
    reader = ObsidianWorkspaceReader(vault)

    for value in ("../outside.md", str((tmp_path / "outside.md").resolve()), "A.txt", "C:\\secret.md"):
        with pytest.raises(ObsidianWorkspacePathError):
            reader.read_note(value)


def test_reader_preview_refuses_external_change_after_scan(tmp_path):
    vault = _vault(tmp_path)
    path = vault / "A.md"
    _write(path, "# A\nold\n")
    reader = ObsidianWorkspaceReader(vault)
    note = reader.scan().notes[0]
    _write(path, "# A\nchanged externally\n")

    with pytest.raises(ObsidianWorkspaceReadError, match="changed"):
        reader.read_note(note.relative_path, expected_hash=note.source_hash)


def test_reader_preview_rejects_note_swapped_to_in_vault_symlink_after_scan(tmp_path):
    vault = _vault(tmp_path)
    source = vault / "A.md"
    target = vault / "B.md"
    _write(source, "# Same\n")
    _write(target, "# Same\n")
    reader = ObsidianWorkspaceReader(vault)
    note = next(item for item in reader.scan().notes if item.relative_path == "A.md")
    source.unlink()
    try:
        source.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available in this environment")

    with pytest.raises(ObsidianWorkspacePathError, match="unavailable"):
        reader.read_note(note.relative_path, expected_hash=note.source_hash)


def test_reader_returns_plain_untrusted_markdown_text(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "Unsafe.md", '<script>alert("x")</script>\n<img src=x onerror=alert(1)>\n')
    reader = ObsidianWorkspaceReader(vault)
    note = reader.scan().notes[0]

    payload = reader.read_note(note.relative_path, expected_hash=note.source_hash)

    assert '<script>alert("x")</script>' in payload["text"]
    assert "onerror" in payload["text"]


def test_reader_search_matches_title_path_tag_and_body_deterministically(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "A" / "LU.md", "---\ntags: [matrix]\n---\n# LU Factorization\nElimination body\n")
    _write(vault / "B" / "Rank.md", "# Rank\nFactorization appears in body.\n")
    _write(vault / "C" / "Factorization-Path.md", "# Other\nNo keyword in content.\n")
    reader = ObsidianWorkspaceReader(vault)
    scan = reader.scan()

    title_results = reader.search(scan, "LU Factorization")
    assert title_results[0]["relative_path"] == "A/LU.md"
    assert title_results[0]["match_scope"] == "title"

    path_results = reader.search(scan, "Factorization-Path")
    assert path_results[0]["match_scope"] == "path"

    tag_results = reader.search(scan, "matrix")
    assert tag_results[0]["match_scope"] == "tag"

    body_results = reader.search(scan, "appears in body")
    assert body_results[0]["relative_path"] == "B/Rank.md"
    assert body_results[0]["match_scope"] == "body"
    assert "appears in body" in body_results[0]["excerpt"].casefold()


def test_reader_blank_search_does_not_read_bodies_and_limit_is_bounded(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    for index in range(4):
        _write(vault / ("Note{}.md".format(index)), "# Note {}\nkeyword\n".format(index))
    reader = ObsidianWorkspaceReader(vault)
    scan = reader.scan()

    def fail_read(*args, **kwargs):
        raise AssertionError("blank search must not read note bodies")

    monkeypatch.setattr(reader, "read_note", fail_read)
    assert reader.search(scan, "") == ()

    monkeypatch.undo()
    results = reader.search(scan, "note", limit=2)
    assert len(results) == 2


def test_reader_search_skips_note_that_changes_after_scan(tmp_path):
    vault = _vault(tmp_path)
    path = vault / "A.md"
    _write(path, "# A\nneedle\n")
    reader = ObsidianWorkspaceReader(vault)
    scan = reader.scan()
    _write(path, "# A\nchanged\n")

    assert reader.search(scan, "needle") == ()
    assert reader.search_warning_count == 1


def test_non_utf8_note_is_not_returned_and_scan_reports_issue(tmp_path):
    vault = _vault(tmp_path)
    (vault / "Bad.md").write_bytes(b"\xff\xfe\x00")
    _write(vault / "Good.md", "# Good\n")
    reader = ObsidianWorkspaceReader(vault)

    scan = reader.scan()

    assert [note.relative_path for note in scan.notes] == ["Good.md"]
    assert scan.blocking_issue_count == 1


def test_workspace_status_disconnected_disabled_and_connected(tmp_path):
    disconnected = ObsidianWorkspaceService(FakeConfig(), ObsidianWorkspaceReader).workspace()
    assert disconnected["configured"] is False
    assert disconnected["enabled"] is False
    assert disconnected["notes"] == []
    assert disconnected["summary"]["markdown_files"] == 0

    vault = _vault(tmp_path)
    _write(vault / "A.md", "# A\n")
    _write(vault / "B.md", "# B\n")

    class MustNotScan:
        def __init__(self, *args, **kwargs):
            raise AssertionError("disabled workspace must not scan")

    disabled_service = ObsidianWorkspaceService(
        FakeConfig({"vault_path": str(vault), "enabled": False}), MustNotScan
    )
    disabled = disabled_service.workspace()
    assert disabled["configured"] is True
    assert disabled["enabled"] is False
    assert disabled["valid"] is True

    connected, _ = _service(vault)
    workspace = connected.workspace()
    assert workspace["configured"] is True
    assert workspace["enabled"] is True
    assert workspace["valid"] is True
    assert workspace["vault_name"] == "Vault"
    assert workspace["summary"]["markdown_files"] == 2


def test_workspace_search_is_bounded_and_query_is_normalized(tmp_path):
    vault = _vault(tmp_path)
    for index in range(3):
        _write(vault / ("LU{}.md".format(index)), "# LU {}\nLU body\n".format(index))
    service, _ = _service(vault)

    workspace = service.workspace(search="  LU   ")

    assert workspace["query"] == "LU"
    assert workspace["searched"] is True
    assert workspace["summary"]["result_count"] == 3
    assert all(item["relative_path"].endswith(".md") for item in workspace["notes"])
    assert len(service.workspace(search="x" * (MAX_QUERY_CHARS + 50))["query"]) == MAX_QUERY_CHARS
    assert MAX_SEARCH_RESULTS == 100
    assert MAX_BROWSE_NOTES == 500


def test_workspace_browse_cap_sets_truncation_without_body_search():
    notes = tuple(
        SimpleNamespace(
            relative_path="N{:03}.md".format(index),
            title="N{}".format(index),
            tags=(),
            note_type="note",
            revision_status="unreviewed",
            source_hash="a" * 64,
        )
        for index in range(MAX_BROWSE_NOTES + 2)
    )
    scan = SimpleNamespace(
        notes=notes,
        note_count=len(notes),
        vault_name="Vault",
        blocking_issue_count=0,
        warning_count=0,
        ignored_symlinks=0,
    )

    class FakeReader:
        def __init__(self, *args, **kwargs):
            self.search_warning_count = 0
        def scan(self):
            return scan
        def search(self, *args, **kwargs):
            raise AssertionError("blank browse must not invoke search")

    config = FakeConfig({"vault_path": str(Path.cwd()), "enabled": True})
    config.validate_vault_path = lambda value: (True, "valid")
    service = ObsidianWorkspaceService(config, FakeReader)
    workspace = service.workspace()

    assert len(workspace["notes"]) == MAX_BROWSE_NOTES
    assert workspace["summary"]["truncated"] is True


def test_note_preview_scans_first_and_reads_with_expected_hash(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "Math" / "LU.md", "# LU\nA = LU\n")
    service, _ = _service(vault)

    preview = service.note_preview("Math/LU.md")

    assert preview["relative_path"] == "Math/LU.md"
    assert preview["title"] == "LU"
    assert "A = LU" in preview["text"]
    assert len(preview["source_hash"]) == 64


def test_note_preview_maps_traversal_missing_and_external_change_safely(tmp_path):
    vault = _vault(tmp_path)
    note = vault / "A.md"
    _write(note, "# A\nold\n")
    service, _ = _service(vault)

    with pytest.raises(ObsidianWorkspaceValidationError):
        service.note_preview("../secret.md")
    with pytest.raises(ObsidianWorkspaceNotFoundError):
        service.note_preview("Missing.md")

    class ChangingReader(ObsidianWorkspaceReader):
        def read_note(self, relative_path, *, expected_hash=""):
            (self.root / relative_path).write_text("# changed\n", encoding="utf-8")
            return super().read_note(relative_path, expected_hash=expected_hash)

    changing = ObsidianWorkspaceService(
        FakeConfig({"vault_path": str(vault), "enabled": True}), ChangingReader
    )
    with pytest.raises(ObsidianWorkspaceUnavailableError) as error:
        changing.note_preview("A.md")
    assert str(vault) not in str(error.value)


def test_connect_enable_disable_validate_and_touch_only_config(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "A.md", "# A\n")
    before = _hash_tree(vault)
    config = FakeConfig()
    service = ObsidianWorkspaceService(config, ObsidianWorkspaceReader)

    with pytest.raises(ObsidianWorkspaceValidationError):
        service.connect_vault("   ")
    with pytest.raises(ObsidianWorkspaceValidationError):
        service.connect_vault(str(tmp_path / "Missing"))

    result = service.connect_vault(str(vault))
    assert result["enabled"] is True
    assert config.config["enabled"] is True
    service.disable_vault()
    assert config.config["enabled"] is False
    service.enable_vault()
    assert config.config["enabled"] is True
    assert _hash_tree(vault) == before


def test_connect_rejects_symlink_vault_root(tmp_path):
    vault = _vault(tmp_path)
    link = tmp_path / "VaultLink"
    try:
        link.symlink_to(vault, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available in this environment")
    service = ObsidianWorkspaceService(FakeConfig(), ObsidianWorkspaceReader)
    with pytest.raises(ObsidianWorkspaceValidationError):
        service.connect_vault(str(link))


def test_backend_exceptions_are_redacted_from_service_errors(tmp_path):
    class BrokenConfig(FakeConfig):
        def load_config(self):
            raise RuntimeError("C:/SECRET/obsidian_config.json")

    service = ObsidianWorkspaceService(BrokenConfig(), ObsidianWorkspaceReader)
    with pytest.raises(ObsidianWorkspaceUnavailableError) as error:
        service.workspace()
    assert "SECRET" not in str(error.value)


def _app_with_service(service):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "OBSIDIAN_WORKSPACE_SERVICE_FACTORY": lambda: service,
        }
    )


class FakeWebService:
    def __init__(self):
        self.workspace_calls = []
        self.commands = []

    def workspace(self, search=""):
        self.workspace_calls.append(search)
        return {
            "available": True,
            "message": "",
            "configured": True,
            "enabled": True,
            "valid": True,
            "vault_path": "C:/Vault",
            "vault_name": "Vault",
            "query": search,
            "searched": bool(search),
            "notes": [
                {
                    "relative_path": "Math/LU.md",
                    "title": "LU Factorization",
                    "tags": ["linear-algebra", "lu"],
                    "note_type": "concept",
                    "revision_status": "needs_practice",
                    "source_hash": "a" * 64,
                    "excerpt": "LU factorization body" if search else "",
                    "match_scope": "title" if search else "",
                }
            ],
            "summary": {
                "markdown_files": 1,
                "result_count": 1,
                "displayed_count": 1,
                "truncated": False,
            },
            "issues": {
                "blocking": 0,
                "warnings": 0,
                "ignored_symlinks": 0,
                "search_skipped": 0,
            },
        }

    def note_preview(self, relative_path):
        if relative_path == "missing.md":
            raise ObsidianWorkspaceNotFoundError("missing")
        if relative_path.startswith(".."):
            raise ObsidianWorkspaceValidationError("bad")
        return {
            "title": "Unsafe",
            "relative_path": "Math/LU.md",
            "tags": ["linear-algebra"],
            "note_type": "concept",
            "revision_status": "needs_practice",
            "source_hash": "a" * 64,
            "size_bytes": 10,
            "text": '<script>alert("x")</script>\n<img src=x onerror=alert(1)>',
        }

    def connect_vault(self, value):
        if not str(value).strip():
            raise ObsidianWorkspaceValidationError("blank")
        self.commands.append(("connect", value))
        return {"enabled": True}

    def enable_vault(self):
        self.commands.append(("enable", ""))
        return {"enabled": True}

    def disable_vault(self):
        self.commands.append(("disable", ""))
        return {"enabled": False}


def test_obsidian_workspace_get_route_and_navigation_are_operational():
    service = FakeWebService()
    client = _app_with_service(service).test_client()
    response = client.get("/obsidian?q=LU")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert service.workspace_calls == ["LU"]
    assert "LU Factorization" in text
    assert "Live vault search" in text
    assert "semantic" not in text.casefold()

    base = (ROOT / "personal_learning_assistant/ui/web/templates/base.html").read_text(encoding="utf-8")
    assert "url_for('web.obsidian')" in base
    assert "active_page == 'obsidian'" in base
    assert 'Obsidian</span><span class="nav-status">Soon' not in base


def test_obsidian_preview_route_escapes_untrusted_markdown_and_maps_errors():
    service = FakeWebService()
    client = _app_with_service(service).test_client()

    response = client.get("/obsidian/note?path=Math%2FLU.md")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '&lt;script&gt;alert' in text
    assert '<script>alert("x")</script>' not in text
    assert "onerror=alert(1)&gt;" in text

    assert client.get("/obsidian/note?path=..%2Fsecret.md").status_code == 400
    assert client.get("/obsidian/note?path=missing.md").status_code == 404


def test_obsidian_configuration_posts_use_303_prg():
    service = FakeWebService()
    client = _app_with_service(service).test_client()

    response = client.post("/obsidian/connect", data={"vault_path": "C:/Vault"})
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/obsidian?connected=1")
    response = client.post("/obsidian/enable")
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/obsidian?enabled=1")
    response = client.post("/obsidian/disable")
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/obsidian?disabled=1")
    assert [item[0] for item in service.commands] == ["connect", "enable", "disable"]


def test_obsidian_configuration_validation_error_is_safe_400():
    service = FakeWebService()
    client = _app_with_service(service).test_client()
    response = client.post("/obsidian/connect", data={"vault_path": ""})
    assert response.status_code == 400
    assert "SECRET" not in response.get_data(as_text=True)


def test_get_routes_are_read_pure_against_real_temporary_vault(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "Math" / "LU.md", "# LU\nFactorization\n")
    service, config = _service(vault)
    before = _hash_tree(vault)
    config_before = dict(config.config)
    client = _app_with_service(service).test_client()

    assert client.get("/obsidian").status_code == 200
    assert client.get("/obsidian?q=LU").status_code == 200
    assert client.get("/obsidian/note?path=Math%2FLU.md").status_code == 200

    assert _hash_tree(vault) == before
    assert config.config == config_before


def test_web_app_startup_keeps_obsidian_config_scanner_and_reader_lazy(tmp_path):
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "obsidian_integration",
    "personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader",
    "personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner",
):
    assert name not in sys.modules, name
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_route_and_service_dependency_direction_stays_safe():
    routes = (ROOT / "personal_learning_assistant/ui/web/routes.py").read_text(encoding="utf-8")
    for token in (
        "obsidian_integration",
        "ObsidianVaultScanner",
        "SQLiteObsidianVaultRepository",
        "NotesStudioService",
        "AtomicMarkdownNoteStore",
        ".read_bytes(",
        ".read_text(",
    ):
        assert token not in routes

    service = (ROOT / "personal_learning_assistant/services/obsidian_workspace_service.py").read_text(encoding="utf-8")
    for token in (
        "obsidian_menu",
        "input(",
        "print(",
        "ObsidianVaultRegistryService.apply",
        "IndexBuilder",
        ".write_text(",
        ".write_bytes(",
        "os.replace(",
        "atomic_write(",
        "create_note(",
        "update_note(",
        "restore(",
    ):
        assert token not in service
