from __future__ import annotations

import io
import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pytest

from personal_learning_assistant.domain.notes_studio_models import (
    CreateNoteRequest,
    UpdateNoteRequest,
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
from personal_learning_assistant.services.notes_studio_editor_service import (
    NotesStudioEditorConflictError,
    NotesStudioEditorNotFoundError,
    NotesStudioEditorValidationError,
    NotesStudioEditorWebService,
)
from personal_learning_assistant.services.notes_studio_service import NotesStudioService
from personal_learning_assistant.services.notes_studio_template_service import (
    build_notes_studio_template_service,
)


NOW = "2026-09-24T15:30:00Z"


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
    return vault, connection, notes, journal, service


def test_phase5_write_protocol_accepts_rich_metadata_and_preserves_unknown_frontmatter(tmp_path):
    vault, connection, _notes, journal, service = _env(tmp_path)
    created = service.create_note(
        CreateNoteRequest(
            title="LU Factorization",
            body="# LU Factorization\n\nBody\n",
            note_type="concept",
            revision_status="learning",
            tags=("linear-algebra", "exam"),
            topic="Matrix factorization",
            course="MA103N",
            note_date="2026-09-24",
            card_summary=("A = LU", "L stores elimination multipliers"),
        )
    )
    path = vault / created.relative_path
    original = path.read_text(encoding="utf-8")
    for expected in (
        "assistant_id:",
        "topic: Matrix factorization",
        "course: MA103N",
        "note_date: 2026-09-24",
        "card_summary:",
        "  - A = LU",
        "  - L stores elimination multipliers",
    ):
        assert expected in original

    injected = original.replace(
        "---\n\n# LU",
        "custom_field: keep-me\ncustom_list:\n  - alpha\n---\n\n# LU",
        1,
    )
    path.write_text(injected, encoding="utf-8")
    external_hash = service.store.read(created.relative_path)[1]

    updated = service.update_note(
        UpdateNoteRequest(
            note_id=created.id,
            expected_hash=external_hash,
            body="# LU Factorization\n\nUpdated body\n",
            topic="Elimination matrices",
            course="MA103N",
            note_date="2026-09-25",
            card_summary=("Factor A into L and U",),
        )
    )
    text = path.read_text(encoding="utf-8")
    assert updated.id == created.id
    assert "custom_field: keep-me" in text
    assert "custom_list:\n  - alpha" in text
    assert "topic: Elimination matrices" in text
    assert "note_date: 2026-09-25" in text
    assert "Updated body" in text
    assert journal.list_open_journal_entries() == ()
    connection.close()


def test_rich_update_refuses_stale_hash_without_overwrite(tmp_path):
    vault, connection, _notes, _journal, service = _env(tmp_path)
    created = service.create_note(
        CreateNoteRequest(title="Rank", body="# Rank\n")
    )
    path = vault / created.relative_path
    path.write_text(
        path.read_text(encoding="utf-8") + "\nExternal edit\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(MarkdownConflictError):
        service.update_note(
            UpdateNoteRequest(
                note_id=created.id,
                expected_hash=created.source_hash,
                body="# Rank\n\nMine\n",
                course="MA103N",
            )
        )

    assert path.read_bytes() == before
    connection.close()


def test_attachment_write_reuses_note_hash_and_operation_journal(tmp_path):
    vault, connection, _notes, journal, service = _env(tmp_path)
    created = service.create_note(
        CreateNoteRequest(title="LU Factorization", body="# LU\n")
    )
    result = service.add_attachment(
        note_id=created.id,
        expected_hash=created.source_hash,
        filename="LU diagram.png",
        payload=b"\x89PNG\r\n\x1a\nANVAYA",
    )

    asset = vault / result["relative_path"]
    assert asset.is_file()
    assert asset.read_bytes().startswith(b"\x89PNG")
    assert result["markdown_reference"].startswith("![LU diagram](")
    assert "_attachments/" in result["markdown_reference"]
    assert journal.list_open_journal_entries() == ()
    connection.close()


def test_attachment_write_refuses_stale_note_hash(tmp_path):
    vault, connection, _notes, _journal, service = _env(tmp_path)
    created = service.create_note(
        CreateNoteRequest(title="LU", body="# LU\n")
    )
    path = vault / created.relative_path
    path.write_text(path.read_text(encoding="utf-8") + "external", encoding="utf-8")

    with pytest.raises(MarkdownConflictError):
        service.add_attachment(
            note_id=created.id,
            expected_hash=created.source_hash,
            filename="diagram.png",
            payload=b"\x89PNG\r\n\x1a\nANVAYA",
        )

    assert list(vault.rglob("diagram.png")) == []
    connection.close()


class FakeReadService:
    def __init__(self, detail):
        self.detail = detail

    def get_detail(self, path):
        assert path == self.detail.card.relative_path
        return self.detail


def _detail(note_id="11111111-1111-4111-8111-111111111111"):
    from personal_learning_assistant.domain.notes_studio_read_models import NoteCard, NoteDetail

    card = NoteCard(
        identity="assistant:" + note_id,
        relative_path="01 INBOX/LU Factorization.md",
        source_hash="a" * 64,
        title="LU Factorization",
        topic="Matrix factorization",
        course="MA103N",
        note_type="concept",
        note_date="2026-09-24",
        card_summary=("A = LU",),
        tags=("linear-algebra",),
        revision_status="learning",
    )
    return NoteDetail(
        card=card,
        text=(
            "---\n"
            "assistant_id: {}\n"
            "title: LU Factorization\n"
            "custom_field: preserve\n"
            "---\n"
            "# LU Factorization\n\nBody\n"
        ).format(note_id),
        wikilinks=(),
        backlinks=(),
    )


class FakeNotesRepository:
    def __init__(self, view):
        self.view = view

    def get(self, note_id):
        if note_id != self.view.id:
            raise RuntimeError("unknown")
        return self.view


class FakeMutationService:
    def __init__(self, view):
        self.notes = FakeNotesRepository(view)
        self.created = []
        self.updated = []
        self.attachments = []

    def create_note(self, request):
        self.created.append(request)
        return self.notes.view

    def update_note(self, request):
        self.updated.append(request)
        return self.notes.view

    def add_attachment(self, **kwargs):
        self.attachments.append(kwargs)
        return {
            "relative_path": "01 INBOX/_attachments/{}/diagram.png".format(
                self.notes.view.id
            ),
            "markdown_reference": "![diagram](_attachments/{}/diagram.png)".format(
                self.notes.view.id
            ),
            "source_hash": "b" * 64,
        }


def _editor_service():
    from personal_learning_assistant.domain.notes_studio_models import NoteStudioView

    note_id = "11111111-1111-4111-8111-111111111111"
    view = NoteStudioView(
        id=note_id,
        relative_path="01 INBOX/LU Factorization.md",
        title="LU Factorization",
        note_type="concept",
        confidence=None,
        revision_status="learning",
        pinned_at=None,
        archived_at=None,
        trashed_at=None,
        source_hash="a" * 64,
        tags=("linear-algebra",),
    )
    mutation = FakeMutationService(view)
    service = NotesStudioEditorWebService(
        read_service=FakeReadService(_detail(note_id)),
        template_service=build_notes_studio_template_service(),
        mutation_context_factory=lambda: nullcontext(mutation),
    )
    return service, mutation


def test_editor_prefills_template_without_writing():
    service, mutation = _editor_service()
    view = service.new_note_view("concept")

    assert view["mode"] == "create"
    assert view["note_type"] == "concept"
    assert "## Key Points" in view["body"]
    assert mutation.created == []
    assert mutation.updated == []


def test_editor_view_exposes_body_without_frontmatter_and_expected_hash():
    service, _mutation = _editor_service()
    view = service.edit_view("01 INBOX/LU Factorization.md")

    assert view["mode"] == "edit"
    assert view["note_id"].startswith("11111111")
    assert view["expected_hash"] == "a" * 64
    assert view["body"].startswith("# LU Factorization")
    assert "assistant_id:" not in view["body"]
    assert view["course"] == "MA103N"
    assert view["card_summary"] == "A = LU"


def test_editor_rejects_unmanaged_note():
    detail = _detail()
    unmanaged_card = detail.card.__class__(
        identity="vault-note:Loose.md@" + "a" * 64,
        relative_path="Loose.md",
        source_hash="a" * 64,
        title="Loose",
        topic="",
        course="",
        note_type="note",
        note_date="",
        card_summary=(),
        tags=(),
        revision_status="unreviewed",
    )
    unmanaged = detail.__class__(
        card=unmanaged_card,
        text="# Loose\n",
        wikilinks=(),
        backlinks=(),
    )
    service = NotesStudioEditorWebService(
        read_service=FakeReadService(unmanaged),
        template_service=build_notes_studio_template_service(),
        mutation_context_factory=lambda: (_ for _ in ()).throw(AssertionError("no write")),
    )

    with pytest.raises(NotesStudioEditorNotFoundError):
        service.edit_view("Loose.md")


def test_editor_create_and_update_delegate_only_to_notes_studio_service():
    service, mutation = _editor_service()

    created = service.create_note(
        {
            "title": "Vector Spaces",
            "body": "# Vector Spaces\n",
            "note_type": "concept",
            "topic": "Vector spaces",
            "course": "MA103N",
            "note_date": "2026-09-24",
            "card_summary": "Closure under addition\nContains zero vector",
            "tags": "linear-algebra, exam",
            "revision_status": "learning",
        }
    )
    assert created["relative_path"].endswith("LU Factorization.md")
    request = mutation.created[-1]
    assert request.course == "MA103N"
    assert request.card_summary == (
        "Closure under addition",
        "Contains zero vector",
    )
    assert request.tags == ("linear-algebra", "exam")

    service.update_note(
        {
            "note_id": mutation.notes.view.id,
            "expected_hash": "a" * 64,
            "title": "LU Factorization",
            "body": "# LU\n",
            "note_type": "concept",
            "topic": "Matrices",
            "course": "MA103N",
            "note_date": "2026-09-25",
            "card_summary": "A = LU",
            "tags": "linear-algebra",
            "revision_status": "revised",
        }
    )
    update = mutation.updated[-1]
    assert update.expected_hash == "a" * 64
    assert update.topic == "Matrices"
    assert update.card_summary == ("A = LU",)


@pytest.mark.parametrize(
    ("filename", "payload"),
    (
        ("diagram.svg", b"<svg></svg>"),
        ("diagram.png", b"not-a-png"),
        ("diagram.exe", b"MZ"),
        ("", b"\x89PNG\r\n\x1a\n"),
    ),
)
def test_editor_rejects_unsafe_attachment_types(filename, payload):
    service, _mutation = _editor_service()
    with pytest.raises(NotesStudioEditorValidationError):
        service.upload_attachment(
            note_id="11111111-1111-4111-8111-111111111111",
            expected_hash="a" * 64,
            filename=filename,
            payload=payload,
        )


def test_editor_accepts_png_attachment_and_returns_markdown_reference():
    service, mutation = _editor_service()
    result = service.upload_attachment(
        note_id="11111111-1111-4111-8111-111111111111",
        expected_hash="a" * 64,
        filename="diagram.png",
        payload=b"\x89PNG\r\n\x1a\nANVAYA",
    )

    assert result["markdown_reference"].startswith("![diagram]")
    assert mutation.attachments[-1]["filename"] == "diagram.png"


class FakeEditorWebService:
    def __init__(self):
        self.calls = []

    def new_note_view(self, template_id=""):
        self.calls.append(("new", template_id))
        return {
            "mode": "create",
            "title": "",
            "body": "## Key Points\n",
            "note_type": "concept",
            "topic": "",
            "course": "",
            "note_date": "",
            "card_summary": "",
            "tags": "",
            "revision_status": "unreviewed",
            "template_id": template_id,
            "relative_path": "",
            "note_id": "",
            "expected_hash": "",
            "attachment_reference": "",
        }

    def edit_view(self, path, attachment_reference=""):
        self.calls.append(("edit", path, attachment_reference))
        view = self.new_note_view("")
        view.update(
            {
                "mode": "edit",
                "title": "LU Factorization",
                "body": "# LU\n",
                "note_type": "concept",
                "course": "MA103N",
                "relative_path": path,
                "note_id": "11111111-1111-4111-8111-111111111111",
                "expected_hash": "a" * 64,
                "attachment_reference": attachment_reference,
            }
        )
        return view

    def create_note(self, payload):
        self.calls.append(("create", payload))
        return {
            "relative_path": "01 INBOX/New Note.md",
            "source_hash": "b" * 64,
        }

    def update_note(self, payload):
        self.calls.append(("update", payload))
        return {
            "relative_path": "01 INBOX/LU Factorization.md",
            "source_hash": "c" * 64,
        }

    def upload_attachment(self, **payload):
        self.calls.append(("attachment", payload))
        return {
            "relative_path": "01 INBOX/_attachments/id/diagram.png",
            "markdown_reference": "![diagram](_attachments/id/diagram.png)",
            "source_hash": "d" * 64,
            "note_relative_path": "01 INBOX/LU Factorization.md",
        }


def _app(service):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "NOTES_STUDIO_EDITOR_SERVICE_FACTORY": lambda: service,
        }
    )


def test_editor_routes_render_create_and_edit_forms():
    service = FakeEditorWebService()
    client = _app(service).test_client()

    create = client.get("/notes/new?template=concept")
    edit = client.get("/notes/edit?path=01%20INBOX%2FLU%20Factorization.md")

    assert create.status_code == 200
    assert edit.status_code == 200
    create_html = create.get_data(as_text=True)
    edit_html = edit.get_data(as_text=True)
    assert "Safe Note Editor" in create_html
    assert "Create note" in create_html
    assert "Save changes" in edit_html
    assert "Expected hash" not in edit_html
    assert 'enctype="multipart/form-data"' in edit_html


def test_editor_post_routes_redirect_to_full_reader():
    service = FakeEditorWebService()
    client = _app(service).test_client()

    created = client.post(
        "/notes/new",
        data={
            "title": "New Note",
            "body": "# New Note",
            "note_type": "concept",
            "revision_status": "unreviewed",
        },
    )
    updated = client.post(
        "/notes/edit",
        data={
            "note_id": "11111111-1111-4111-8111-111111111111",
            "expected_hash": "a" * 64,
            "title": "LU Factorization",
            "body": "# LU",
            "note_type": "concept",
            "revision_status": "revised",
        },
    )

    assert created.status_code == 303
    assert "/notes/note?path=" in created.headers["Location"]
    assert (
        "New+Note.md" in created.headers["Location"]
        or "New%20Note.md" in created.headers["Location"]
    )
    assert updated.status_code == 303
    assert (
        "LU+Factorization.md" in updated.headers["Location"]
        or "LU%20Factorization.md" in updated.headers["Location"]
    )


def test_attachment_route_uploads_and_returns_to_editor_with_reference():
    service = FakeEditorWebService()
    client = _app(service).test_client()

    response = client.post(
        "/notes/attachments",
        data={
            "note_id": "11111111-1111-4111-8111-111111111111",
            "expected_hash": "a" * 64,
            "file": (io.BytesIO(b"\x89PNG\r\n\x1a\nANVAYA"), "diagram.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 303
    assert "/notes/edit?" in response.headers["Location"]
    assert "attachment=" in response.headers["Location"]


def test_editor_conflict_is_safe_and_does_not_redirect():
    class ConflictEditor(FakeEditorWebService):
        def update_note(self, payload):
            raise NotesStudioEditorConflictError("C:/SECRET/vault")

    response = _app(ConflictEditor()).test_client().post(
        "/notes/edit",
        data={
            "note_id": "11111111-1111-4111-8111-111111111111",
            "expected_hash": "a" * 64,
            "title": "LU",
            "body": "# LU",
            "note_type": "concept",
            "revision_status": "learning",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 409
    assert "changed since you opened it" in html
    assert "SECRET" not in html


def test_templates_and_reader_expose_safe_editor_entry_points():
    root = Path(__file__).resolve().parents[1]
    template_preview = (
        root / "personal_learning_assistant/ui/web/templates/notes_template_preview.html"
    ).read_text(encoding="utf-8")
    reader = (
        root / "personal_learning_assistant/ui/web/templates/notes_reader.html"
    ).read_text(encoding="utf-8")
    library = (
        root / "personal_learning_assistant/ui/web/templates/notes_library.html"
    ).read_text(encoding="utf-8")

    assert "url_for('web.notes_new'" in template_preview
    assert "Use this template" in template_preview
    assert "url_for('web.notes_edit'" in reader
    assert "Edit note" in reader
    assert "url_for('web.notes_new')" in library
    assert "New note" in library


def test_editor_service_does_not_bypass_notes_studio_write_protocol():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "personal_learning_assistant/services/notes_studio_editor_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        ".write_text(",
        ".write_bytes(",
        "os.replace(",
        "open(",
        "sqlite3.connect(",
        "personal_learning_assistant.tutor",
        "openai",
        "requests",
        "httpx",
    ):
        assert forbidden not in source
    assert "NotesStudioService" not in source
    assert "notes_studio_service" in source


def test_attachment_store_is_scoped_to_note_attachment_directory():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "personal_learning_assistant/repositories/filesystem/markdown_note_store.py"
    ).read_text(encoding="utf-8")

    assert "_attachments" in source
    assert "expected_note_hash" in source
    assert "safe_attachment_filename" in source
