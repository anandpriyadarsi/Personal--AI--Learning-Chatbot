from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from markupsafe import Markup

from personal_learning_assistant.domain.notes_studio_read_models import (
    NoteCard,
    NoteDetail,
)
from personal_learning_assistant.repositories.filesystem.markdown_note_store import (
    AtomicMarkdownNoteStore,
)
from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import (
    ObsidianWorkspaceReader,
)
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    SQLiteKnowledgeRegistryRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.notes_studio_repository import (
    SQLiteNotesStudioRepository,
)
from personal_learning_assistant.services.notes_studio_lifecycle_service import (
    read_lifecycle_snapshot,
)
from personal_learning_assistant.services.notes_studio_read_service import (
    NotesStudioReadService,
)
from personal_learning_assistant.services.notes_studio_reconciliation_service import (
    CUTOVER_DECISION,
    NotesStudioReconciliationService,
)
from personal_learning_assistant.services.notes_studio_service import (
    NotesStudioService,
)


NOW = "2026-09-24T17:15:00Z"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _card(title, path, *, identity=None, body_hash="a" * 64):
    identity = identity or "vault-note:{}@{}".format(path, body_hash)
    return NoteCard(
        identity=identity,
        relative_path=path,
        source_hash=body_hash,
        title=title,
        topic="",
        course="",
        note_type="note",
        note_date="",
        card_summary=(),
        tags=(),
        revision_status="unreviewed",
    )


def _detail(card, body):
    return NoteDetail(
        card=card,
        text=body,
        wikilinks=(),
        backlinks=(),
    )


class FakeReadService:
    def __init__(self, cards, bodies):
        self.cards = tuple(cards)
        self.bodies = dict(bodies)
        self.detail_calls = []

    def list_cards(self):
        return self.cards

    def get_detail(self, relative_path):
        self.detail_calls.append(relative_path)
        card = next(item for item in self.cards if item.relative_path == relative_path)
        return _detail(card, self.bodies[relative_path])


def test_reconciliation_preview_classifies_exact_title_body_match_review_and_create(tmp_path):
    legacy = tmp_path / "notes.json"
    legacy.write_text(
        json.dumps(
            [
                {
                    "title": "LU Factorization",
                    "topic": "Math",
                    "difficulty": "Hard",
                    "content": "# LU\n\nExact body\n",
                },
                {
                    "title": "Rank",
                    "topic": "Math",
                    "difficulty": "Medium",
                    "content": "Legacy rank body",
                },
                {
                    "title": "Data Cleaning",
                    "topic": "DS",
                    "difficulty": "Medium",
                    "content": "Legacy only",
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    cards = (
        _card("LU Factorization", "Math/LU.md"),
        _card("Rank", "Math/Rank.md"),
    )
    reader = FakeReadService(
        cards,
        {
            "Math/LU.md": (
                "---\nassistant_id: 11111111-1111-4111-8111-111111111111\n---\n\n"
                "# LU\n\nExact body\n"
            ),
            "Math/Rank.md": "# Rank\n\nDifferent body\n",
        },
    )
    before = _hash(legacy)

    report = NotesStudioReconciliationService(
        read_service=reader,
        legacy_path=legacy,
    ).report()

    assert report["cutover_decision"] == CUTOVER_DECISION
    assert report["automatic_migration"] is False
    assert report["legacy_write_compatibility"] == "preserved"
    assert report["default_note_authority"] == "obsidian_markdown"
    assert report["legacy_record_count"] == 3
    assert report["rich_note_count"] == 2
    assert report["decision_counts"] == {
        "match_existing": 1,
        "needs_review": 1,
        "create_markdown": 1,
    }
    assert [item["decision"] for item in report["items"]] == [
        "match_existing",
        "needs_review",
        "create_markdown",
    ]
    assert _hash(legacy) == before


def test_reconciliation_only_reads_bodies_for_same_title_candidates(tmp_path):
    legacy = tmp_path / "notes.json"
    legacy.write_text(
        json.dumps(
            [
                {
                    "title": "Rank",
                    "topic": "Math",
                    "difficulty": "Hard",
                    "content": "legacy",
                }
            ]
        ),
        encoding="utf-8",
    )
    cards = (
        _card("Rank", "Rank.md"),
        _card("Unrelated", "Unrelated.md"),
    )
    reader = FakeReadService(
        cards,
        {
            "Rank.md": "# Rank\n",
            "Unrelated.md": "# Unrelated\n",
        },
    )

    NotesStudioReconciliationService(
        read_service=reader,
        legacy_path=legacy,
    ).report()

    assert reader.detail_calls == ["Rank.md"]


def test_invalid_legacy_json_is_never_silently_migrated(tmp_path):
    legacy = tmp_path / "notes.json"
    legacy.write_text("{not valid json", encoding="utf-8")

    report = NotesStudioReconciliationService(
        read_service=FakeReadService((), {}),
        legacy_path=legacy,
    ).report()

    assert report["legacy_status"] == "invalid"
    assert report["automatic_migration"] is False
    assert report["decision_counts"]["needs_review"] == 1
    assert report["items"][0]["legacy_index"] == -1


def test_missing_legacy_json_is_valid_zero_record_compatibility_state(tmp_path):
    report = NotesStudioReconciliationService(
        read_service=FakeReadService((), {}),
        legacy_path=tmp_path / "missing.json",
    ).report()

    assert report["legacy_status"] == "missing"
    assert report["legacy_record_count"] == 0
    assert report["items"] == []


def _temp_notes_environment(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    db = tmp_path / "db.sqlite"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "INSERT INTO vaults(id,name,root_path,path_key,enabled,last_scanned_at,created_at,updated_at) "
        "VALUES ('v1','Vault',?,'vault',1,NULL,?,?)",
        (str(vault), NOW, NOW),
    )
    notes = SQLiteNotesStudioRepository(connection)
    journal = SQLiteKnowledgeRegistryRepository(connection)
    service = NotesStudioService(
        vault_id="v1",
        store=AtomicMarkdownNoteStore(vault),
        notes=notes,
        journal_repository=journal,
        now=lambda: NOW,
    )
    return vault, db, connection, service


def test_final_stack_round_trip_keeps_markdown_authority_and_lifecycle_overlay(tmp_path):
    from personal_learning_assistant.domain.notes_studio_models import CreateNoteRequest

    vault, db, connection, mutation = _temp_notes_environment(tmp_path)
    created = mutation.create_note(
        CreateNoteRequest(
            title="Vector Spaces",
            body="# Vector Spaces\n\n> [!IMPORTANT] Closure\n",
            course="MA103N",
            topic="Vector Spaces",
            note_type="concept",
            card_summary=("Closure", "Zero vector"),
            tags=("linear-algebra",),
        )
    )
    mutation.pin(created.id, True)

    reader = NotesStudioReadService(
        lambda: ObsidianWorkspaceReader(vault),
        lifecycle_provider=lambda ids: read_lifecycle_snapshot(db, ids),
    )
    cards = reader.list_cards()
    assert len(cards) == 1
    assert cards[0].title == "Vector Spaces"
    assert cards[0].course == "MA103N"
    assert cards[0].card_summary == ("Closure", "Zero vector")
    assert cards[0].pinned_at == NOW
    assert (vault / cards[0].relative_path).is_file()

    detail = reader.get_detail(cards[0].relative_path)
    assert "> [!IMPORTANT] Closure" in detail.text
    connection.close()


class FakeReconciliationWebService:
    def report(self):
        return {
            "cutover_decision": CUTOVER_DECISION,
            "automatic_migration": False,
            "legacy_write_compatibility": "preserved",
            "default_note_authority": "obsidian_markdown",
            "legacy_status": "valid",
            "legacy_record_count": 2,
            "rich_note_count": 5,
            "managed_note_count": 4,
            "unmanaged_note_count": 1,
            "decision_counts": {
                "match_existing": 1,
                "needs_review": 1,
                "create_markdown": 0,
            },
            "items": [
                {
                    "legacy_index": 0,
                    "legacy_title": "LU",
                    "decision": "match_existing",
                    "candidate_note_ids": [
                        "assistant:11111111-1111-4111-8111-111111111111"
                    ],
                    "reason": "normalized title and body hash match",
                },
                {
                    "legacy_index": 1,
                    "legacy_title": "Rank",
                    "decision": "needs_review",
                    "candidate_note_ids": ["vault-note:Rank.md@" + "a" * 64],
                    "reason": "title candidate exists but exact body match is not proven",
                },
            ],
        }


def test_reconciliation_route_is_read_only_and_explains_no_automatic_migration():
    from personal_learning_assistant.ui.web import create_app

    app = create_app(
        {
            "TESTING": True,
            "NOTES_STUDIO_RECONCILIATION_SERVICE_FACTORY": (
                lambda: FakeReconciliationWebService()
            ),
        }
    )
    client = app.test_client()

    response = client.get("/notes/reconciliation")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Notes Studio Reconciliation",
        "Obsidian Markdown remains authoritative",
        "Legacy JSON remains preserved",
        "No automatic migration",
        "LU",
        "Rank",
        "Match existing",
        "Needs review",
    ):
        assert expected in html
    assert "<form" not in html.casefold()
    assert "migrate now" not in html.casefold()
    assert client.post("/notes/reconciliation").status_code == 405


def test_default_library_links_to_reconciliation_without_legacy_write_form():
    root = Path(__file__).resolve().parents[1]
    library = (
        root / "personal_learning_assistant/ui/web/templates/notes_library.html"
    ).read_text(encoding="utf-8")

    assert "url_for('web.notes_reconciliation')" in library
    assert "Review reconciliation" in library
    assert 'action="/notes"' not in library
    assert "name=\"content\"" not in library


def test_routes_keep_legacy_post_compatibility_but_default_get_is_rich_library():
    root = Path(__file__).resolve().parents[1]
    routes = (
        root / "personal_learning_assistant/ui/web/routes.py"
    ).read_text(encoding="utf-8")

    assert '@web_blueprint.get("/notes")' in routes
    assert "notes_library.html" in routes
    assert '@web_blueprint.post("/notes")' in routes
    assert '@web_blueprint.post("/notes/<int:position>")' in routes
    assert "Preserve explicit Phase 7.5.11 test/host overrides" in routes


def test_reconciliation_service_has_no_write_ai_tutor_or_migration_execution():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "personal_learning_assistant/services/notes_studio_reconciliation_service.py"
    ).read_text(encoding="utf-8").casefold()

    for forbidden in (
        "personal_learning_assistant.tutor",
        "openai",
        "requests",
        "httpx",
        ".write_text(",
        ".write_bytes(",
        "os.replace(",
        "apply_migrations(",
        "create_note(",
        "update_note(",
    ):
        assert forbidden not in source


def test_reconciliation_decision_document_freezes_non_destructive_cutover():
    root = Path(__file__).resolve().parents[1]
    decision = (
        root / "PHASE7_5_15_9_RECONCILIATION_DECISION.md"
    ).read_text(encoding="utf-8")

    for expected in (
        "NO AUTOMATIC LEGACY MIGRATION",
        "Obsidian Markdown",
        "data/notes.json",
        "compatibility",
        "separate reviewed migration",
        "no SQLite migration",
        "Tutor",
    ):
        assert expected in decision
