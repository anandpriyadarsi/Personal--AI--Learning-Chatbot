from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pytest
from markupsafe import Markup

from personal_learning_assistant.domain.notes_studio_models import (
    CreateNoteRequest,
)
from personal_learning_assistant.domain.notes_studio_read_models import (
    NoteCard,
    NoteDetail,
)
from personal_learning_assistant.repositories.filesystem.markdown_note_store import (
    AtomicMarkdownNoteStore,
    MarkdownConflictError,
)
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    SQLiteKnowledgeRegistryRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.notes_studio_repository import (
    SQLiteNotesStudioRepository,
)
from personal_learning_assistant.services.notes_studio_lifecycle_service import (
    NotesStudioLifecycleConflictError,
    NotesStudioLifecycleNotFoundError,
    NotesStudioLifecycleService,
    NotesStudioLifecycleValidationError,
    derive_restore_target,
    read_lifecycle_snapshot,
)
from personal_learning_assistant.services.notes_studio_library_service import (
    NotesStudioLibraryWebService,
)
from personal_learning_assistant.services.notes_studio_read_service import (
    NotesStudioReadService,
)
from personal_learning_assistant.services.notes_studio_reader_service import (
    NotesStudioReaderWebService,
)
from personal_learning_assistant.services.notes_studio_service import NotesStudioService


NOW = "2026-09-24T16:20:00Z"


def _env(tmp_path):
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
    return vault, db, connection, notes, journal, service


def _card(
    title="LU Factorization",
    path="Math/LU.md",
    *,
    identity="assistant:11111111-1111-4111-8111-111111111111",
    pinned_at="",
    archived_at="",
    trashed_at="",
    status="learning",
):
    return NoteCard(
        identity=identity,
        relative_path=path,
        source_hash="a" * 64,
        title=title,
        topic="Matrix factorization",
        course="MA103N",
        note_type="concept",
        note_date="2026-09-24",
        card_summary=("A = LU",),
        tags=("linear-algebra",),
        revision_status=status,
        source="MIT 18.06",
        pinned_at=pinned_at,
        archived_at=archived_at,
        trashed_at=trashed_at,
    )


def test_lifecycle_snapshot_reads_existing_metadata_without_writing(tmp_path):
    vault, db, connection, notes, _journal, service = _env(tmp_path)
    created = service.create_note(CreateNoteRequest(title="Pinned"))
    service.pin(created.id)
    before = db.read_bytes()

    snapshot = read_lifecycle_snapshot(db, (created.id, "missing"))

    assert snapshot[created.id]["pinned_at"] == NOW
    assert snapshot[created.id]["archived_at"] == ""
    assert snapshot[created.id]["trashed_at"] == ""
    assert db.read_bytes() == before
    connection.close()


def test_canonical_read_model_overlays_managed_lifecycle_only(tmp_path):
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Managed.md").write_text(
        "---\nassistant_id: 11111111-1111-4111-8111-111111111111\n---\n# Managed\n",
        encoding="utf-8",
    )
    (vault / "Loose.md").write_text("# Loose\n", encoding="utf-8")

    from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import (
        ObsidianWorkspaceReader,
    )

    calls = []

    def lifecycle_provider(ids):
        calls.append(tuple(ids))
        return {
            "11111111-1111-4111-8111-111111111111": {
                "pinned_at": NOW,
                "archived_at": "",
                "trashed_at": "",
            }
        }

    cards = NotesStudioReadService(
        lambda: ObsidianWorkspaceReader(vault),
        lifecycle_provider=lifecycle_provider,
    ).list_cards()
    by_title = {card.title: card for card in cards}

    assert by_title["Managed"].pinned_at == NOW
    assert by_title["Managed"].managed is True
    assert by_title["Loose"].pinned_at == ""
    assert by_title["Loose"].managed is False
    assert calls == [("11111111-1111-4111-8111-111111111111",)]


def test_library_defaults_to_active_supports_archived_and_pinned_filters():
    cards = (
        _card("Pinned", "Pinned.md", pinned_at=NOW),
        _card("Normal", "Normal.md"),
        _card("Archived", "Archived.md", archived_at=NOW),
        _card(
            "Loose",
            "Loose.md",
            identity="vault-note:Loose.md@" + "b" * 64,
        ),
    )

    class ReadService:
        def list_cards(self):
            return cards

    service = NotesStudioLibraryWebService(ReadService())
    active = service.workspace()
    archived = service.workspace(view="archived")
    pinned = service.workspace(pinned="1")
    all_notes = service.workspace(view="all")

    assert [item["title"] for item in active["cards"]] == [
        "Pinned",
        "Loose",
        "Normal",
    ]
    assert [item["title"] for item in archived["cards"]] == ["Archived"]
    assert [item["title"] for item in pinned["cards"]] == ["Pinned"]
    assert {item["title"] for item in all_notes["cards"]} == {
        "Pinned",
        "Normal",
        "Archived",
        "Loose",
    }
    assert active["cards"][0]["pinned"] is True


def test_reader_exposes_lifecycle_state_for_managed_note():
    detail = NoteDetail(
        card=_card(pinned_at=NOW, archived_at=NOW),
        text="# LU\n",
        wikilinks=(),
        backlinks=(),
    )

    class ReadService:
        def get_detail(self, _path):
            return detail

    view = NotesStudioReaderWebService(
        ReadService(),
        renderer=lambda *_args, **_kwargs: Markup("<p>LU</p>"),
    ).reader_view("Math/LU.md")

    assert view["managed"] is True
    assert view["pinned"] is True
    assert view["archived"] is True
    assert view["lifecycle_state"] == "archived"


class FakeMutationService:
    def __init__(self):
        from personal_learning_assistant.domain.notes_studio_models import NoteStudioView

        self.view = NoteStudioView(
            id="11111111-1111-4111-8111-111111111111",
            relative_path="Math/LU.md",
            title="LU",
            note_type="concept",
            confidence=None,
            revision_status="learning",
            pinned_at=None,
            archived_at=None,
            trashed_at=None,
            source_hash="a" * 64,
            tags=("linear-algebra",),
        )
        self.calls = []

        class Repo:
            pass

        self.notes = Repo()
        self.notes.get = lambda note_id: self.view
        self.notes.list_trashed = lambda vault_id: ()

    def pin(self, note_id, pinned=True):
        self.calls.append(("pin", note_id, pinned))
        return self.view

    def archive(self, note_id, archived=True):
        self.calls.append(("archive", note_id, archived))
        return self.view

    def trash(self, note_id, expected_hash=None):
        self.calls.append(("trash", note_id, expected_hash))
        return self.view

    def restore(self, note_id, relative_path, expected_hash=None):
        self.calls.append(("restore", note_id, relative_path, expected_hash))
        return self.view

    def set_study_status(self, note_id, expected_hash, status):
        self.calls.append(("study", note_id, expected_hash, status))
        return self.view


def _lifecycle_service(mutation=None):
    mutation = mutation or FakeMutationService()
    return (
        NotesStudioLifecycleService(
            mutation_context_factory=lambda: nullcontext(mutation),
            trash_reader=lambda: (),
        ),
        mutation,
    )


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("pin", ("pin", True)),
        ("unpin", ("pin", False)),
        ("archive", ("archive", True)),
        ("unarchive", ("archive", False)),
    ),
)
def test_lifecycle_metadata_actions_delegate_to_phase5_service(action, expected):
    service, mutation = _lifecycle_service()

    result = service.apply_action(
        note_id=mutation.view.id,
        action=action,
        expected_hash="a" * 64,
    )

    assert result["relative_path"] == "Math/LU.md"
    assert mutation.calls[-1] == (expected[0], mutation.view.id, expected[1])


@pytest.mark.parametrize(
    ("action", "status"),
    (
        ("needs_practice", "needs_practice"),
        ("review_due", "review_due"),
        ("revised", "revised"),
        ("mastered", "mastered"),
    ),
)
def test_study_actions_are_bounded_revision_status_commands(action, status):
    service, mutation = _lifecycle_service()

    service.apply_action(
        note_id=mutation.view.id,
        action=action,
        expected_hash="a" * 64,
    )

    assert mutation.calls[-1] == (
        "study",
        mutation.view.id,
        "a" * 64,
        status,
    )


def test_unknown_lifecycle_action_is_rejected_before_mutation():
    service, mutation = _lifecycle_service()
    with pytest.raises(NotesStudioLifecycleValidationError):
        service.apply_action(
            note_id=mutation.view.id,
            action="delete_forever",
            expected_hash="a" * 64,
        )
    assert mutation.calls == []


def test_trash_requires_expected_hash_and_restore_requires_explicit_safe_target(tmp_path):
    vault, _db, connection, _notes, _journal, service = _env(tmp_path)
    created = service.create_note(CreateNoteRequest(title="LU", body="# LU\n"))
    path = vault / created.relative_path
    path.write_text(path.read_text(encoding="utf-8") + "external\n", encoding="utf-8")

    with pytest.raises(MarkdownConflictError):
        service.trash(created.id, expected_hash=created.source_hash)

    current_hash = service.store.read(created.relative_path)[1]
    trashed = service.trash(created.id, expected_hash=current_hash)
    assert trashed.trashed_at == NOW

    with pytest.raises(ValueError):
        service.restore(created.id, "", expected_hash=current_hash)

    restored = service.restore(
        created.id,
        "01 INBOX/Restored LU.md",
        expected_hash=current_hash,
    )
    assert restored.trashed_at is None
    assert restored.relative_path == "01 INBOX/Restored LU.md"
    connection.close()


def test_restore_target_derives_original_path_but_requires_user_submission():
    trashed = ".trash/Personal AI Learning Assistant/01 INBOX/LU.md"
    assert derive_restore_target(trashed) == "01 INBOX/LU.md"
    assert derive_restore_target("normal/LU.md") == ""


def test_trash_workspace_contains_no_note_body():
    rows = (
        {
            "id": "n1",
            "title": "LU",
            "relative_path": ".trash/Personal AI Learning Assistant/01 INBOX/LU.md",
            "source_hash": "a" * 64,
            "trashed_at": NOW,
        },
    )
    service = NotesStudioLifecycleService(
        mutation_context_factory=lambda: (_ for _ in ()).throw(
            AssertionError("trash listing must not open mutation context")
        ),
        trash_reader=lambda: rows,
    )

    workspace = service.trash_workspace()

    assert workspace["notes"][0]["restore_target"] == "01 INBOX/LU.md"
    assert "body" not in workspace["notes"][0]
    assert "text" not in workspace["notes"][0]


class FakeLifecycleWebService:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    def apply_action(self, **payload):
        self.calls.append(("action", payload))
        if self.error:
            raise self.error
        if payload["action"] == "trash":
            return {
                "relative_path": ".trash/Personal AI Learning Assistant/Math/LU.md",
                "trashed": True,
            }
        return {"relative_path": "Math/LU.md", "trashed": False}

    def trash_workspace(self):
        self.calls.append(("trash_workspace",))
        return {
            "notes": [
                {
                    "id": "n1",
                    "title": "LU",
                    "relative_path": ".trash/Personal AI Learning Assistant/Math/LU.md",
                    "restore_target": "Math/LU.md",
                    "source_hash": "a" * 64,
                    "trashed_at": NOW,
                }
            ]
        }

    def restore_note(self, **payload):
        self.calls.append(("restore", payload))
        if self.error:
            raise self.error
        return {"relative_path": payload["relative_path"]}


def _app(service, reader=None):
    from personal_learning_assistant.ui.web import create_app

    config = {
        "TESTING": True,
        "NOTES_STUDIO_LIFECYCLE_SERVICE_FACTORY": lambda: service,
    }
    if reader is not None:
        config["NOTES_STUDIO_READER_SERVICE_FACTORY"] = lambda: reader
    return create_app(config)


def test_lifecycle_routes_are_post_only_and_redirect_safely():
    service = FakeLifecycleWebService()
    client = _app(service).test_client()

    assert client.get("/notes/lifecycle").status_code == 405

    pin = client.post(
        "/notes/lifecycle",
        data={
            "note_id": "n1",
            "action": "pin",
            "expected_hash": "a" * 64,
            "path": "Math/LU.md",
        },
    )
    trash = client.post(
        "/notes/lifecycle",
        data={
            "note_id": "n1",
            "action": "trash",
            "expected_hash": "a" * 64,
            "path": "Math/LU.md",
        },
    )

    assert pin.status_code == 303
    assert "/notes/note?path=Math" in pin.headers["Location"]
    assert trash.status_code == 303
    assert trash.headers["Location"].endswith("/notes/trash")


def test_trash_page_and_restore_route_require_explicit_destination():
    service = FakeLifecycleWebService()
    client = _app(service).test_client()

    page = client.get("/notes/trash")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Notes Studio Trash" in html
    assert "Math/LU.md" in html
    assert 'name="relative_path"' in html

    restored = client.post(
        "/notes/restore",
        data={
            "note_id": "n1",
            "expected_hash": "a" * 64,
            "relative_path": "Math/LU.md",
        },
    )
    assert restored.status_code == 303
    assert "/notes/note?path=Math" in restored.headers["Location"]


def test_conflict_error_is_redacted_and_does_not_redirect():
    service = FakeLifecycleWebService(
        error=NotesStudioLifecycleConflictError("C:/SECRET/vault")
    )
    response = _app(service).test_client().post(
        "/notes/lifecycle",
        data={
            "note_id": "n1",
            "action": "mastered",
            "expected_hash": "a" * 64,
            "path": "Math/LU.md",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 409
    assert "changed" in html.casefold()
    assert "SECRET" not in html


def test_reader_and_library_templates_expose_lifecycle_without_permanent_delete():
    root = Path(__file__).resolve().parents[1]
    reader = (
        root / "personal_learning_assistant/ui/web/templates/notes_reader.html"
    ).read_text(encoding="utf-8")
    library = (
        root / "personal_learning_assistant/ui/web/templates/notes_library.html"
    ).read_text(encoding="utf-8")
    trash = (
        root / "personal_learning_assistant/ui/web/templates/notes_trash.html"
    ).read_text(encoding="utf-8")

    for expected in (
        "Pin note",
        "Archive note",
        "Move to trash",
        "Needs practice",
        "Review due",
        "Mastered",
    ):
        assert expected in reader
    assert "view=archived" in library or "view', 'archived" in library
    assert "Notes Studio Trash" in trash

    combined = (reader + library + trash).casefold()
    assert "delete forever" not in combined
    assert "permanent delete" not in combined


def test_lifecycle_service_has_no_tutor_ai_or_direct_markdown_write_path():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "personal_learning_assistant/services/notes_studio_lifecycle_service.py"
    ).read_text(encoding="utf-8").casefold()

    for forbidden in (
        "personal_learning_assistant.tutor",
        "openai",
        "requests",
        "httpx",
        ".write_text(",
        ".write_bytes(",
        "os.replace(",
    ):
        assert forbidden not in source
    assert "configured_notes_studio_mutation_context" in source
