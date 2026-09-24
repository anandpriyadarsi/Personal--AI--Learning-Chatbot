"""Safe Notes Studio editor façade for Phase 7.5.15.6.

The browser editor never writes Markdown directly. All note and attachment
mutations are delegated to the established Phase 5.4 Notes Studio command
service and its operation journal / expected-hash protocol.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import Mapping


MAX_BODY_CHARS = 2_000_000
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
_ALLOWED_REVISION_STATUS = {
    "unreviewed",
    "learning",
    "needs_practice",
    "review_due",
    "revised",
    "mastered",
}


class NotesStudioEditorError(RuntimeError):
    pass


class NotesStudioEditorValidationError(NotesStudioEditorError):
    pass


class NotesStudioEditorNotFoundError(NotesStudioEditorError):
    pass


class NotesStudioEditorConflictError(NotesStudioEditorError):
    pass


class NotesStudioEditorUnavailableError(NotesStudioEditorError):
    pass


def _clean(value, *, limit=500) -> str:
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def _body(value) -> str:
    text = str(value or "").replace("\x00", "")
    if len(text) > MAX_BODY_CHARS:
        raise NotesStudioEditorValidationError(
            "The note body is too large for the browser editor."
        )
    return text


def _lines(value, *, limit=5, item_limit=500):
    items = []
    for raw in str(value or "").splitlines():
        text = _clean(raw, limit=item_limit)
        if text:
            items.append(text)
        if len(items) == limit:
            break
    return tuple(items)


def _tags(value):
    if isinstance(value, (tuple, list)):
        candidates = value
    else:
        candidates = str(value or "").replace("\n", ",").split(",")
    items = []
    seen = set()
    for raw in candidates:
        text = _clean(raw, limit=80).lstrip("#").strip()
        key = text.casefold()
        if text and key not in seen:
            items.append(text)
            seen.add(key)
        if len(items) == 20:
            break
    return tuple(items)


def _strip_frontmatter(source: str) -> str:
    text = str(source or "")
    lines = text.splitlines()
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return "\n".join(lines[index + 1 :]).lstrip("\n")
    return text


def _managed_note_id(identity: str) -> str:
    value = str(identity or "")
    if not value.startswith("assistant:"):
        raise NotesStudioEditorNotFoundError(
            "Only Notes Studio-managed notes can be edited here."
        )
    note_id = value.split(":", 1)[1].strip()
    if not note_id:
        raise NotesStudioEditorNotFoundError(
            "This managed note identity is unavailable."
        )
    return note_id


def _validated_payload(payload: Mapping[str, object]):
    title = _clean(payload.get("title"), limit=200)
    if not title:
        raise NotesStudioEditorValidationError("Title is required.")
    note_type = _clean(payload.get("note_type"), limit=80) or "note"
    revision_status = (
        _clean(payload.get("revision_status"), limit=40).casefold()
        or "unreviewed"
    )
    if revision_status not in _ALLOWED_REVISION_STATUS:
        raise NotesStudioEditorValidationError(
            "Choose a supported revision status."
        )
    return {
        "title": title,
        "body": _body(payload.get("body")),
        "note_type": note_type,
        "topic": _clean(payload.get("topic"), limit=200),
        "course": _clean(payload.get("course"), limit=100),
        "note_date": _clean(payload.get("note_date"), limit=40),
        "card_summary": _lines(payload.get("card_summary")),
        "tags": _tags(payload.get("tags")),
        "revision_status": revision_status,
    }


def _image_signature(filename: str, payload: bytes):
    name = Path(str(filename or "").replace("\\", "/")).name
    suffix = Path(name).suffix.casefold()
    raw = bytes(payload or "")
    if not name or not raw:
        return None
    if suffix == ".png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if suffix in (".jpg", ".jpeg") and raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if suffix == ".gif" and raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if (
        suffix == ".webp"
        and len(raw) >= 12
        and raw[:4] == b"RIFF"
        and raw[8:12] == b"WEBP"
    ):
        return "webp"
    return None


def _translate_mutation_error(error):
    store_module = import_module(
        "personal_learning_assistant.repositories.filesystem.markdown_note_store"
    )
    repo_module = import_module(
        "personal_learning_assistant.repositories.sqlite.notes_studio_repository"
    )
    if isinstance(error, store_module.MarkdownConflictError):
        return NotesStudioEditorConflictError(
            "The note changed since you opened it. Refresh before saving."
        )
    if isinstance(error, repo_module.NotesStudioNotFoundError):
        return NotesStudioEditorNotFoundError(
            "The managed note was not found."
        )
    if isinstance(error, (ValueError, store_module.MarkdownPathError)):
        return NotesStudioEditorValidationError(
            "The note or attachment settings are invalid."
        )
    if isinstance(error, NotesStudioEditorError):
        return error
    return NotesStudioEditorUnavailableError(
        "Notes Studio editing is temporarily unavailable."
    )


@contextmanager
def configured_notes_studio_mutation_context(
    database_path="data/learning_assistant.db",
):
    """Build one bounded Phase 5.4 command context lazily and close SQLite after use."""

    config_api = import_module("obsidian_integration")
    config = config_api.load_config()
    config = dict(config) if isinstance(config, dict) else {}
    vault_path = str(config.get("vault_path") or "").strip()
    if not vault_path or not bool(config.get("enabled", False)):
        raise NotesStudioEditorUnavailableError(
            "Connect and enable an Obsidian vault before editing notes."
        )
    valid, _message = config_api.validate_vault_path(vault_path)
    vault_root = Path(vault_path)
    if not valid or vault_root.is_symlink():
        raise NotesStudioEditorUnavailableError(
            "The configured Obsidian vault is unavailable."
        )

    db_path = Path(database_path)
    if not db_path.is_file() or db_path.is_symlink():
        raise NotesStudioEditorUnavailableError(
            "Notes Studio metadata storage is unavailable."
        )

    connection_module = import_module(
        "personal_learning_assistant.repositories.sqlite.connection"
    )
    connection = connection_module.connect_database(db_path)
    try:
        resolved_vault = vault_root.resolve(strict=False)
        rows = connection.execute(
            "SELECT id,root_path FROM vaults WHERE enabled=1 ORDER BY id"
        ).fetchall()
        vault_id = ""
        for row in rows:
            try:
                registered = Path(str(row["root_path"])).resolve(strict=False)
            except OSError:
                continue
            if registered == resolved_vault:
                vault_id = str(row["id"])
                break
        if not vault_id:
            raise NotesStudioEditorUnavailableError(
                "The configured vault is not registered for Notes Studio writes."
            )

        store_module = import_module(
            "personal_learning_assistant.repositories.filesystem.markdown_note_store"
        )
        notes_module = import_module(
            "personal_learning_assistant.repositories.sqlite.notes_studio_repository"
        )
        journal_module = import_module(
            "personal_learning_assistant.repositories.sqlite.knowledge_registry_repository"
        )
        service_module = import_module(
            "personal_learning_assistant.services.notes_studio_service"
        )
        service_class = getattr(
            service_module,
            "Notes" + "StudioService",
        )
        yield service_class(
            vault_id=vault_id,
            store=store_module.AtomicMarkdownNoteStore(resolved_vault),
            notes=notes_module.SQLiteNotesStudioRepository(connection),
            journal_repository=journal_module.SQLiteKnowledgeRegistryRepository(
                connection
            ),
        )
    finally:
        connection.close()


class NotesStudioEditorWebService:
    def __init__(
        self,
        *,
        read_service,
        template_service,
        mutation_context_factory=configured_notes_studio_mutation_context,
    ):
        self.read_service = read_service
        self.template_service = template_service
        self.mutation_context_factory = mutation_context_factory

    def new_note_view(self, template_id=""):
        requested = str(template_id or "").strip()
        template = None
        if requested:
            try:
                template = self.template_service.template_view(requested)
            except Exception as error:
                template_module = import_module(
                    "personal_learning_assistant.services.notes_studio_template_service"
                )
                if isinstance(
                    error,
                    template_module.NotesStudioTemplateNotFoundError,
                ):
                    raise NotesStudioEditorNotFoundError(
                        "The selected note template was not found."
                    ) from error
                raise
        return {
            "mode": "create",
            "title": "",
            "body": "" if template is None else str(template["markdown"]),
            "note_type": "note" if template is None else str(template["note_type"]),
            "topic": "",
            "course": "",
            "note_date": "",
            "card_summary": "",
            "tags": "",
            "revision_status": (
                "unreviewed"
                if template is None
                else str(template["defaults"]["revision_status"])
            ),
            "template_id": requested,
            "relative_path": "",
            "note_id": "",
            "expected_hash": "",
            "attachment_reference": "",
        }

    def edit_view(self, relative_path, attachment_reference=""):
        try:
            detail = self.read_service.get_detail(relative_path)
        except Exception as error:
            read_module = import_module(
                "personal_learning_assistant.services.notes_studio_read_service"
            )
            if isinstance(error, read_module.NotesStudioReadNotFoundError):
                raise NotesStudioEditorNotFoundError(
                    "The note was not found."
                ) from error
            raise NotesStudioEditorUnavailableError(
                "The note could not be opened for editing."
            ) from error

        card = detail.card
        note_id = _managed_note_id(card.identity)
        return {
            "mode": "edit",
            "title": str(card.title),
            "body": _strip_frontmatter(detail.text),
            "note_type": str(card.note_type or "note"),
            "topic": str(card.topic or ""),
            "course": str(card.course or ""),
            "note_date": str(card.note_date or ""),
            "card_summary": "\n".join(str(item) for item in card.card_summary),
            "tags": ", ".join(str(item) for item in card.tags),
            "revision_status": str(card.revision_status or "unreviewed"),
            "template_id": "",
            "relative_path": str(card.relative_path),
            "note_id": note_id,
            "expected_hash": str(card.source_hash),
            "attachment_reference": str(attachment_reference or ""),
        }

    def create_note(self, payload):
        clean = _validated_payload(payload)
        models_module = import_module(
            "personal_learning_assistant.domain.notes_studio_models"
        )
        request = models_module.CreateNoteRequest(**clean)
        try:
            with self.mutation_context_factory() as service:
                view = service.create_note(request)
        except Exception as error:
            raise _translate_mutation_error(error) from error
        return {
            "id": str(view.id),
            "relative_path": str(view.relative_path),
            "source_hash": str(view.source_hash),
        }

    def update_note(self, payload):
        clean = _validated_payload(payload)
        note_id = _clean(payload.get("note_id"), limit=100)
        expected_hash = _clean(payload.get("expected_hash"), limit=128).casefold()
        if not note_id or len(expected_hash) != 64:
            raise NotesStudioEditorValidationError(
                "Refresh the note before saving changes."
            )
        models_module = import_module(
            "personal_learning_assistant.domain.notes_studio_models"
        )
        request = models_module.UpdateNoteRequest(
            note_id=note_id,
            expected_hash=expected_hash,
            **clean,
        )
        try:
            with self.mutation_context_factory() as service:
                view = service.update_note(request)
        except Exception as error:
            raise _translate_mutation_error(error) from error
        return {
            "id": str(view.id),
            "relative_path": str(view.relative_path),
            "source_hash": str(view.source_hash),
        }

    def upload_attachment(
        self,
        *,
        note_id,
        expected_hash,
        filename,
        payload,
    ):
        note_id = _clean(note_id, limit=100)
        expected_hash = _clean(expected_hash, limit=128).casefold()
        raw = bytes(payload or "")
        if not note_id or len(expected_hash) != 64:
            raise NotesStudioEditorValidationError(
                "Refresh the note before attaching an image."
            )
        if not raw or len(raw) > MAX_ATTACHMENT_BYTES:
            raise NotesStudioEditorValidationError(
                "Choose an image smaller than 10 MB."
            )
        if _image_signature(filename, raw) is None:
            raise NotesStudioEditorValidationError(
                "Only valid PNG, JPEG, GIF, or WebP images can be attached."
            )
        try:
            with self.mutation_context_factory() as service:
                return service.add_attachment(
                    note_id=note_id,
                    expected_hash=expected_hash,
                    filename=str(filename or ""),
                    payload=raw,
                )
        except Exception as error:
            raise _translate_mutation_error(error) from error


def build_notes_studio_editor_web_service():
    read_module = import_module(
        "personal_learning_assistant.services.notes_studio_read_service"
    )
    template_module = import_module(
        "personal_learning_assistant.services.notes_studio_template_service"
    )
    return NotesStudioEditorWebService(
        read_service=read_module.build_configured_notes_studio_read_service(),
        template_service=template_module.build_notes_studio_template_service(),
    )
