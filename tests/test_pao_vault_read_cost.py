"""Read budgets and faithful rendering for external Markdown."""
import pytest
from test_pao_obsidian_identity import workspace
from personal_learning_assistant.services.obsidian_study_companion_service import ObsidianStudyCompanionService
from personal_learning_assistant.services.obsidian_markdown_renderer import render_markdown
from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import ObsidianWorkspaceReader, ObsidianWorkspaceReadError


def test_tracking_reads_only_selected_note(tmp_path, monkeypatch):
    service = workspace(tmp_path, {f"N{i}.md": f"# N{i}\n[[N1]]" for i in range(30)})
    note = service.note_preview("N0.md")
    calls = []
    original = ObsidianWorkspaceReader.read_note
    def counted(self, path, **kwargs):
        calls.append(path)
        return original(self, path, **kwargs)
    monkeypatch.setattr(ObsidianWorkspaceReader, "read_note", counted)
    companion = ObsidianStudyCompanionService(service, None)
    companion._current_note("N0.md", note["source_hash"])
    assert calls == ["N0.md"]


def test_wikilinks_leave_inline_and_fenced_code_unchanged():
    html = str(render_markdown("`[[Target]]`\n\n```python\n[[Target]]\n```\n\n[[Target#Section]]", wikilinks=[
        {"raw": "Target", "resolved_path": "Target.md", "label": "Target"},
        {"raw": "Target#Section", "resolved_path": "Target.md", "label": "Section", "heading": "Section"},
    ]))
    assert "<code>[[Target]]</code>" in html
    assert "[[Target]]\n</code>" in html
    assert 'Target.md#section' in html


def test_bounded_markdown_read(tmp_path, monkeypatch):
    service = workspace(tmp_path, {"Large.md": "x" * 100})
    import personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader as module
    monkeypatch.setattr(module, "MAX_NOTE_BYTES", 50)
    with pytest.raises(ObsidianWorkspaceReadError):
        ObsidianWorkspaceReader(tmp_path).read_note("Large.md")


def test_code_and_frontmatter_do_not_make_backlinks(tmp_path):
    service = workspace(tmp_path, {"A.md": "# A", "B.md": "---\nvalue: '[[A]]'\n---\n`[[A]]`\n\n```\n[[A]]\n```"})
    assert service.note_preview("A.md")["backlinks"] == ()


def test_legacy_ingestion_excludes_symlinks(tmp_path, monkeypatch):
    import obsidian_integration as config
    outside = tmp_path / "outside.md"
    outside.write_text("private")
    root = tmp_path / "vault"
    service = workspace(root, {"Inside.md": "safe"})
    (root / "Link.md").symlink_to(outside)
    monkeypatch.setattr(config, "get_vault_path", lambda: str(root))
    assert config.get_obsidian_markdown_files() == [str(root / "Inside.md")]


def test_persisted_manifest_tracking_never_scans_in_new_service(tmp_path, monkeypatch):
    service = workspace(tmp_path, {"A.md": "# A", "B.md": "# B"})
    service.refresh_manifest()
    note = service.note_preview("A.md")
    from personal_learning_assistant.services.obsidian_workspace_service import ObsidianWorkspaceService
    fresh = ObsidianWorkspaceService(service.config_api, ObsidianWorkspaceReader)
    def forbidden(*args, **kwargs):
        raise AssertionError("Tracking may not scan the vault")
    monkeypatch.setattr(ObsidianWorkspaceReader, "scan", forbidden)
    validated = ObsidianStudyCompanionService(fresh, None)._current_note("A.md", note["source_hash"])[0]
    assert validated["source_item_id"] == note["source_item_id"]


def test_reader_resolves_relative_markdown_aliases_and_heading(tmp_path):
    service = workspace(tmp_path, {"Root.md": "# Root\n\n## Section", "Folder/A.md": "[[../Root#Section|Back]]\n\n[More](../Root.md#Section)"})
    note = service.note_preview("Folder/A.md")
    html = str(render_markdown(note["text"], wikilinks=note["wikilinks"], note_path=note["relative_path"], asset_route="/assets"))
    assert '>Back</a>' in html
    assert 'path=Root.md#section' in html
    assert '../Root.md' not in html


def test_inline_remote_images_are_not_requested():
    html = str(render_markdown("Before ![track](https://example.com/pixel.png) after", note_path="A.md", asset_route="/assets"))
    assert 'src="https://' not in html
    assert 'unavailable' in html.lower()


def test_multibacktick_code_preserves_wikilinks():
    html = str(render_markdown("``code ` [[Target]]``", wikilinks=[{"raw": "Target", "resolved_path": "Target.md", "label": "Target"}]))
    assert '[[Target]]' in html
    assert '/obsidian/note' not in html


def test_unified_search_has_one_scan_for_all_results(tmp_path, monkeypatch):
    from personal_learning_assistant.services.unified_search_service import UnifiedSearchService
    from types import SimpleNamespace
    source = workspace(tmp_path, {f"Match{i}.md": f"# Match {i}" for i in range(12)})
    scans = []
    original = ObsidianWorkspaceReader.scan
    def counted(self):
        scans.append(1)
        return original(self)
    monkeypatch.setattr(ObsidianWorkspaceReader, "scan", counted)
    # Factory returns a fresh service, reproducing production request factories.
    from personal_learning_assistant.services.obsidian_workspace_service import ObsidianWorkspaceService
    service = UnifiedSearchService(runtime=object(), obsidian_workspace_factory=lambda: ObsidianWorkspaceService(source.config_api, ObsidianWorkspaceReader))
    interaction = SimpleNamespace(history=lambda identity: {"times_opened": 0, "total_active_seconds": 0, "last_read_at": None})
    assert len(service._obsidian_results("Match", interaction, limit=12)) == 12
    assert len(scans) == 1


def test_export_preserves_original_bom_and_unknown_frontmatter(connected):
    from test_obsidian_connections import archive
    from personal_learning_assistant.ui.web import create_app
    service, config, notes = connected
    raw = b'\xef\xbb\xbf---\nunknown: Keep me\n---\n# Source\n\n```\n[[A]]\n```\n'
    service.import_snapshot(archive([('.obsidian/', ''), ('A.md', raw)]))
    app = create_app({'TESTING': True, 'OBSIDIAN_CONNECTION_SERVICE_FACTORY': lambda: service})
    client = app.test_client()
    note = service.workspace.note_preview('A.md')
    response = client.get('/library/connected-sources/obsidian/export', query_string={'path': 'A.md', 'sha256': note['source_hash']})
    assert response.status_code == 200
    assert response.data == raw
    assert client.get('/library/connected-sources/obsidian/asset?path=../outside.png').status_code == 404
    assert client.get('/library/connected-sources/obsidian/export?path=A.md&sha256=' + 'a' * 64).status_code == 409


from test_obsidian_connections import connected
