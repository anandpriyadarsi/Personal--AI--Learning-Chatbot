from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner import (
    ObsidianVaultScanner,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.obsidian_vault_repository import (
    ObsidianVaultConflictError,
    SQLiteObsidianVaultRepository,
)
from personal_learning_assistant.services.obsidian_vault_registry_service import (
    ObsidianVaultRegistryService,
)


NOW = "2026-09-16T00:00:00Z"


def _db(tmp_path: Path):
    db = tmp_path / "notes.db"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    repo = SQLiteObsidianVaultRepository(connection)
    service = ObsidianVaultRegistryService(repo, now=lambda: NOW)
    return db, connection, repo, service


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_read_only_scan_discovers_notes_without_frontmatter(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "A.md", "# Alpha\nBody\n")
    _write(vault / "Folder" / "B.md", "No frontmatter\n")
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    scan = ObsidianVaultScanner("vault", vault).scan()
    assert scan.note_count == 2
    assert scan.blocking_issue_count == 0
    assert [note.title for note in scan.notes] == ["Alpha", "B"]
    assert {path: path.read_bytes() for path in vault.rglob("*.md")} == before


def test_frontmatter_metadata_and_tags_are_parsed_without_rewrite(tmp_path):
    vault = tmp_path / "Vault"
    _write(
        vault / "Concept.md",
        "---\n"
        "assistant_id: 7c6e3eb4-0c5c-4d39-b1ef-2d99ef9d9354\n"
        "title: LU Factorization\n"
        "tags:\n"
        "  - linear-algebra\n"
        "  - matrices\n"
        "note_type: concept\n"
        "confidence: 3\n"
        "revision_status: needs-review\n"
        "custom_field: keep-me\n"
        "---\n"
        "Text #exam\n",
    )
    raw_before = (vault / "Concept.md").read_bytes()
    note = ObsidianVaultScanner("vault", vault).scan().notes[0]
    assert note.assistant_id == "7c6e3eb4-0c5c-4d39-b1ef-2d99ef9d9354"
    assert note.title == "LU Factorization"
    assert note.note_type == "concept"
    assert note.confidence == 3
    assert note.revision_status == "needs_practice"
    assert note.tags == ("exam", "linear-algebra", "matrices")
    assert "custom_field: keep-me" in note.frontmatter_extra["raw_frontmatter"]
    assert (vault / "Concept.md").read_bytes() == raw_before


def test_wiki_links_resolve_exact_path_before_duplicate_basename(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "A" / "Topic.md", "# A\n")
    _write(vault / "B" / "Topic.md", "# B\n")
    _write(vault / "Source.md", "[[A/Topic]]\n")
    _db_path, connection, repo, service = _db(tmp_path)
    scan = ObsidianVaultScanner("vault", vault).scan()
    plan = service.preview(scan)
    assert plan.resolved_link_count == 1
    assert plan.ambiguous_link_count == 0
    result = service.apply(scan)
    source = next(item for item in repo.list_notes(result.vault_id) if item.relative_path == "Source.md")
    links = repo.list_links_for_note(source.id)
    assert len(links) == 1
    assert links[0].target_note_id is not None
    assert links[0].link_type == "wiki"
    connection.close()


def test_duplicate_basename_without_path_is_ambiguous_not_guessed(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "A" / "Topic.md", "# A\n")
    _write(vault / "B" / "Topic.md", "# B\n")
    _write(vault / "Source.md", "[[Topic]]\n")
    _db_path, connection, repo, service = _db(tmp_path)
    result = service.apply(ObsidianVaultScanner("vault", vault).scan())
    assert result.ambiguous_link_count == 1
    source = next(item for item in repo.list_notes(result.vault_id) if item.relative_path == "Source.md")
    link = repo.list_links_for_note(source.id)[0]
    assert link.target_note_id is None
    assert link.unresolved_target == "Topic"
    assert link.link_type == "wiki_ambiguous"
    connection.close()


def test_heading_block_and_alias_are_preserved_in_link_graph(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "Target.md", "# Target\n")
    _write(
        vault / "Source.md",
        "[[Target#Section|label]]\n[[Target^block-1]]\n",
    )
    _db_path, connection, repo, service = _db(tmp_path)
    result = service.apply(ObsidianVaultScanner("vault", vault).scan())
    source = next(item for item in repo.list_notes(result.vault_id) if item.relative_path == "Source.md")
    links = repo.list_links_for_note(source.id)
    assert len(links) == 2
    assert links[0].heading == "Section"
    assert links[1].block_id == "block-1"
    assert all(link.target_note_id is not None for link in links)
    connection.close()


def test_markdown_relative_link_resolves_and_backlink_query_works(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "Folder" / "Target.md", "# Target\n")
    _write(vault / "Folder" / "Source.md", "[Target](Target.md#Part)\n")
    _db_path, connection, repo, service = _db(tmp_path)
    result = service.apply(ObsidianVaultScanner("vault", vault).scan())
    notes = repo.list_notes(result.vault_id)
    source = next(item for item in notes if item.relative_path.endswith("Source.md"))
    target = next(item for item in notes if item.relative_path.endswith("Target.md"))
    link = repo.list_links_for_note(source.id)[0]
    assert link.target_note_id == target.id
    assert link.heading == "Part"
    backlinks = repo.get_backlinks(target.id)
    assert len(backlinks) == 1
    assert backlinks[0].source_note_id == source.id
    connection.close()


def test_external_urls_are_preserved_as_non_note_links(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "Source.md", "[Lecture](https://example.edu/a)\nhttps://example.edu/b\n")
    _db_path, connection, repo, service = _db(tmp_path)
    result = service.apply(ObsidianVaultScanner("vault", vault).scan())
    assert result.external_link_count == 2
    source = repo.list_notes(result.vault_id)[0]
    links = repo.list_links_for_note(source.id)
    assert all(link.target_note_id is None for link in links)
    assert all(link.unresolved_target.startswith("https://") for link in links)
    connection.close()


def test_code_fences_and_inline_code_do_not_create_links_or_tags(tmp_path):
    vault = tmp_path / "Vault"
    _write(
        vault / "Source.md",
        "```md\n[[Fake]] #fake\n```\n"
        "`[[InlineFake]] #inlinefake`\n"
        "[[Real]] #real\n",
    )
    _write(vault / "Real.md", "# Real\n")
    scan = ObsidianVaultScanner("vault", vault).scan()
    source = next(note for note in scan.notes if note.relative_path == "Source.md")
    assert len(source.links) == 1
    assert source.links[0].raw_target == "Real"
    assert source.tags == ("real",)


def test_apply_is_idempotent_and_never_modifies_markdown(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "A.md", "# A\n[[B]] #tag\n")
    _write(vault / "B.md", "# B\n")
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    _db_path, connection, repo, service = _db(tmp_path)
    first = service.apply(ObsidianVaultScanner("vault", vault).scan())
    second = service.apply(ObsidianVaultScanner("vault", vault).scan())
    assert first.created == 2
    assert second.matched == 2
    assert len(repo.list_notes(first.vault_id)) == 2
    assert {path: path.read_bytes() for path in vault.rglob("*.md")} == before
    connection.close()


def test_source_hash_change_updates_metadata_same_note_id(tmp_path):
    vault = tmp_path / "Vault"
    note_path = vault / "A.md"
    _write(note_path, "# A\n")
    _db_path, connection, repo, service = _db(tmp_path)
    first = service.apply(ObsidianVaultScanner("vault", vault).scan())
    first_id = repo.list_notes(first.vault_id)[0].id
    _write(note_path, "# A\nchanged\n")
    second = service.apply(ObsidianVaultScanner("vault", vault).scan())
    second_id = repo.list_notes(first.vault_id)[0].id
    assert second.updated == 1
    assert second_id == first_id
    connection.close()


def test_assistant_id_preserves_identity_across_move(tmp_path):
    vault = tmp_path / "Vault"
    assistant_id = "7c6e3eb4-0c5c-4d39-b1ef-2d99ef9d9354"
    first_path = vault / "Old.md"
    _write(first_path, "---\nassistant_id: {}\n---\n# A\n".format(assistant_id))
    _db_path, connection, repo, service = _db(tmp_path)
    first = service.apply(ObsidianVaultScanner("vault", vault).scan())
    assert repo.list_notes(first.vault_id)[0].id == assistant_id
    first_path.rename(vault / "New.md")
    second = service.apply(ObsidianVaultScanner("vault", vault).scan())
    notes = repo.list_notes(first.vault_id)
    assert len(notes) == 1
    assert notes[0].id == assistant_id
    assert notes[0].relative_path == "New.md"
    assert second.updated == 1
    connection.close()


def test_duplicate_assistant_id_blocks_apply_without_db_changes(tmp_path):
    vault = tmp_path / "Vault"
    assistant_id = "7c6e3eb4-0c5c-4d39-b1ef-2d99ef9d9354"
    front = "---\nassistant_id: {}\n---\n".format(assistant_id)
    _write(vault / "A.md", front + "# A\n")
    _write(vault / "B.md", front + "# B\n")
    _db_path, connection, repo, service = _db(tmp_path)
    scan = ObsidianVaultScanner("vault", vault).scan()
    assert scan.blocking_issue_count >= 1
    before = connection.total_changes
    with pytest.raises(ObsidianVaultConflictError):
        service.apply(scan)
    assert connection.total_changes == before
    assert repo.get_vault_by_key("vault") is None
    connection.close()


def test_missing_note_is_reported_not_deleted(tmp_path):
    vault = tmp_path / "Vault"
    a = vault / "A.md"
    _write(a, "# A\n")
    _db_path, connection, repo, service = _db(tmp_path)
    first = service.apply(ObsidianVaultScanner("vault", vault).scan())
    note_id = repo.list_notes(first.vault_id)[0].id
    a.unlink()
    plan = service.preview(ObsidianVaultScanner("vault", vault).scan())
    assert plan.missing_registry_count == 1
    assert repo.get_note(note_id) is not None
    connection.close()


def test_preview_performs_zero_sqlite_writes(tmp_path):
    vault = tmp_path / "Vault"
    _write(vault / "A.md", "# A\n")
    db, connection, repo, service = _db(tmp_path)
    before_changes = connection.total_changes
    before_bytes = db.read_bytes()
    plan = service.preview(ObsidianVaultScanner("vault", vault).scan())
    assert plan.note_count == 1
    assert connection.total_changes == before_changes
    connection.close()
    assert db.read_bytes() == before_bytes


def test_schema_is_existing_phase3_schema_no_new_migration_needed(tmp_path):
    _db_path, connection, repo, _service = _db(tmp_path)
    repo.validate_schema()
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert integrity == "ok"
    assert foreign_keys == []
    connection.close()
