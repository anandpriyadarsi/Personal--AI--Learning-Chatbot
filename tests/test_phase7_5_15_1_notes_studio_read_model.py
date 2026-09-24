from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from personal_learning_assistant.domain.notes_studio_read_models import NoteCard, NoteDetail
from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import ObsidianWorkspaceReader
from personal_learning_assistant.services.notes_studio_read_service import (
    NotesStudioReadService,
    NotesStudioReadUnavailableError,
)


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
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _service(vault: Path) -> NotesStudioReadService:
    return NotesStudioReadService(lambda: ObsidianWorkspaceReader(vault))


def test_note_card_and_detail_are_immutable_typed_models():
    card = NoteCard(
        identity="assistant:11111111-1111-4111-8111-111111111111",
        relative_path="Math/LU.md",
        source_hash="a" * 64,
        title="LU Factorization",
        topic="LU Factorization",
        course="MA103N",
        note_type="concept",
        note_date="2026-09-24",
        card_summary=("A = LU",),
        tags=("linear-algebra",),
        revision_status="learning",
    )
    detail = NoteDetail(card=card, text="# LU", wikilinks=(), backlinks=())
    assert detail.card.title == "LU Factorization"
    with pytest.raises(Exception):
        card.title = "changed"


def test_library_reads_explicit_card_metadata_without_writing_vault(tmp_path):
    vault = _vault(tmp_path)
    _write(
        vault / "Math" / "LU.md",
        """---
assistant_id: 11111111-1111-4111-8111-111111111111
title: LU Factorization
course: MA103N
topic: Matrix Factorization
note_type: concept
note_date: 2026-09-24
card_summary:
  - A = LU
  - L stores elimination multipliers
  - U is upper triangular
tags: [linear-algebra, lu]
revision_status: learning
---
# LU Factorization
Body remains authoritative Markdown.
""",
    )
    before = _hash_tree(vault)

    cards = _service(vault).list_cards()

    assert len(cards) == 1
    card = cards[0]
    assert card.identity == "assistant:11111111-1111-4111-8111-111111111111"
    assert card.course == "MA103N"
    assert card.topic == "Matrix Factorization"
    assert card.note_date == "2026-09-24"
    assert card.card_summary == (
        "A = LU",
        "L stores elimination multipliers",
        "U is upper triangular",
    )
    assert card.tags == ("linear-algebra", "lu")
    assert _hash_tree(vault) == before


def test_card_summary_is_explicit_bounded_and_never_generated_from_body(tmp_path):
    vault = _vault(tmp_path)
    _write(
        vault / "A.md",
        """---
title: A
card_summary:
  - one
  -
  - two
  - three
  - four
  - five
  - six
---
# A
This body contains an important sentence that must never become card metadata.
""",
    )
    _write(vault / "B.md", "# B\nBody-only key point candidate.\n")

    cards = {item.title: item for item in _service(vault).list_cards()}

    assert cards["A"].card_summary == ("one", "two", "three", "four", "five")
    assert cards["B"].card_summary == ()


def test_note_date_prefers_note_date_then_date_alias_and_never_mtime(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "A.md", "---\nnote_date: 2026-09-24\ndate: 2020-01-01\n---\n# A\n")
    _write(vault / "B.md", "---\ndate: 2026-09-23\n---\n# B\n")
    _write(vault / "C.md", "# C\n")

    cards = {item.title: item for item in _service(vault).list_cards()}

    assert cards["A"].note_date == "2026-09-24"
    assert cards["B"].note_date == "2026-09-23"
    assert cards["C"].note_date == ""


def test_unmanaged_identity_uses_path_and_hash_without_adopting_note(tmp_path):
    vault = _vault(tmp_path)
    path = vault / "Math" / "Rank.md"
    _write(path, "# Rank\n")
    before = path.read_bytes()

    card = _service(vault).list_cards()[0]

    assert card.identity.startswith("vault-note:")
    assert "Rank.md" in card.identity
    assert card.source_hash in card.identity
    assert path.read_bytes() == before
    assert "assistant_id" not in path.read_text(encoding="utf-8")


def test_duplicate_titles_remain_distinct_by_path_identity(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "A" / "Same.md", "# Same\n")
    _write(vault / "B" / "Same.md", "# Same\n")

    cards = _service(vault).list_cards()

    assert [item.title for item in cards] == ["Same", "Same"]
    assert len({item.identity for item in cards}) == 2
    assert len({item.relative_path for item in cards}) == 2


def test_detail_reuses_hash_checked_reader_and_exposes_live_links(tmp_path):
    vault = _vault(tmp_path)
    _write(vault / "A.md", "# A\nSee [[B]].\n")
    _write(vault / "B.md", "# B\nBack to [[A]].\n")
    service = _service(vault)

    detail = service.get_detail("A.md")

    assert detail.text.endswith("See [[B]].\n")
    assert detail.wikilinks[0]["resolved_path"] == "B.md"
    assert detail.backlinks[0]["relative_path"] == "B.md"


def test_detail_refuses_note_changed_after_scan(tmp_path):
    vault = _vault(tmp_path)
    path = vault / "A.md"
    _write(path, "# A\nold\n")

    class ChangingReader(ObsidianWorkspaceReader):
        def read_note(self, relative_path, *, expected_hash=""):
            _write(self.root / relative_path, "# A\nchanged\n")
            return super().read_note(relative_path, expected_hash=expected_hash)

    service = NotesStudioReadService(lambda: ChangingReader(vault))
    with pytest.raises(NotesStudioReadUnavailableError, match="changed"):
        service.get_detail("A.md")


def test_read_service_source_has_no_mutation_or_tutor_dependencies():
    root = Path(__file__).resolve().parents[1]
    source = (root / "personal_learning_assistant/services/notes_studio_read_service.py").read_text(encoding="utf-8")
    for token in (
        "personal_learning_assistant.tutor",
        "NotesStudioService",
        "KnowledgeReaderService",
        "LegacyJsonNoteRepository",
        "sqlite3",
        "write_text(",
        "write_bytes(",
        "os.replace(",
        "create_note(",
        "update_note(",
        "apply_snapshot(",
    ):
        assert token not in source
