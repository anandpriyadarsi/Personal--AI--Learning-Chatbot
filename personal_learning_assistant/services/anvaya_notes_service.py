"""Independent ANVAYA Notes application service.

ANVAYA Notes is intentionally separate from the Obsidian workspace. It owns
personal typed/handwritten notes and app-managed uploads only.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesConflictError,
    AnvayaNotesNotFoundError,
    AnvayaNotesRepository,
    AnvayaNotesRepositoryError,
)


MAX_ASSET_BYTES = 25 * 1024 * 1024
MAX_UPLOADS = 20
CARD_STYLES = {"iris", "preview", "square"}
NOTE_KINDS = {"typed", "handwritten"}
_ALLOWED = {
    ".pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    ".png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
}


class AnvayaNotesError(RuntimeError):
    pass


class AnvayaNotesValidationError(AnvayaNotesError, ValueError):
    pass


class AnvayaNotesUnavailableError(AnvayaNotesError):
    pass


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value, *, limit):
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def _body(value, *, limit=500_000):
    return str(value or "").replace("\x00", "")[:limit]


def _points(value):
    if isinstance(value, (list, tuple)):
        source = value
    else:
        source = str(value or "").splitlines()
    clean = []
    for item in source:
        point = _text(item, limit=240)
        if point and point not in clean:
            clean.append(point)
        if len(clean) == 5:
            break
    return clean


def _style(value):
    style = _text(value, limit=30).casefold() or "iris"
    return style if style in CARD_STYLES else "iris"


def _validated_uploads(uploads):
    clean = []
    for filename, payload in tuple(uploads or ()):
        if len(clean) >= MAX_UPLOADS:
            raise AnvayaNotesValidationError("Too many files were selected.")
        raw = bytes(payload or "")
        if not raw or len(raw) > MAX_ASSET_BYTES:
            raise AnvayaNotesValidationError("Each file must be between 1 byte and 25 MB.")
        suffix = Path(str(filename or "")).suffix.casefold()
        rule = _ALLOWED.get(suffix)
        if rule is None or not rule[1](raw):
            raise AnvayaNotesValidationError("Only valid PDF, PNG, JPG, or JPEG files are allowed.")
        safe_name = Path(str(filename or "")).name[:220] or ("note" + suffix)
        clean.append(
            {
                "filename": safe_name,
                "bytes": raw,
                "suffix": suffix,
                "mimetype": rule[0],
            }
        )
    return tuple(clean)


def _label(value, timezone_name):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        local = parsed.astimezone(ZoneInfo(timezone_name))
        return local.strftime("%d %b %Y · %I:%M %p").replace(" 0", " ")
    except (ValueError, TypeError):
        return text


class AnvayaNotesService:
    def __init__(
        self,
        repository=None,
        *,
        now=_utc_now,
        timezone_name="Asia/Kolkata",
        renderer=None,
    ):
        self.repository = repository or AnvayaNotesRepository()
        self.now = now
        self.timezone_name = timezone_name
        if renderer is None:
            renderer = import_module(
                "personal_learning_assistant.services.obsidian_markdown_renderer"
            ).render_markdown
        self.renderer = renderer

    def _card(self, row):
        assets = list(row.get("assets") or [])
        image = next(
            (item for item in assets if str(item.get("mimetype") or "").startswith("image/")),
            None,
        )
        return {
            "id": str(row.get("id") or ""),
            "title": str(row.get("title") or "Untitled"),
            "course": str(row.get("course") or ""),
            "note_kind": str(row.get("note_kind") or "typed"),
            "card_style": _style(row.get("card_style")),
            "key_points": list(row.get("key_points") or [])[:3],
            "created_at": str(row.get("created_at") or ""),
            "created_label": _label(row.get("created_at"), self.timezone_name),
            "updated_label": _label(row.get("updated_at"), self.timezone_name),
            "thumbnail_url": (
                "/notes/file/{}/{}".format(row.get("id"), image.get("id"))
                if image is not None
                else ""
            ),
        }

    def library(self, *, search="", course="", kind=""):
        try:
            rows = self.repository.list_notes()
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("Notes are temporarily unavailable.") from error
        search_key = _text(search, limit=300).casefold()
        course_key = _text(course, limit=100).casefold()
        kind_key = _text(kind, limit=30).casefold()
        cards = []
        for row in rows:
            if str(row.get("status") or "active") != "active":
                continue
            haystack = " ".join(
                [
                    str(row.get("title") or ""),
                    str(row.get("course") or ""),
                    " ".join(str(x) for x in list(row.get("key_points") or [])),
                ]
            ).casefold()
            if search_key and search_key not in haystack:
                continue
            if course_key and str(row.get("course") or "").casefold() != course_key:
                continue
            if kind_key and str(row.get("note_kind") or "").casefold() != kind_key:
                continue
            cards.append(self._card(row))
        cards.sort(key=lambda item: str(item["created_at"]), reverse=True)
        all_active = [row for row in rows if str(row.get("status") or "active") == "active"]
        courses = sorted(
            {str(row.get("course") or "") for row in all_active if str(row.get("course") or "")},
            key=str.casefold,
        )
        kinds = sorted(
            {str(row.get("note_kind") or "") for row in all_active if str(row.get("note_kind") or "")}
        )
        return {
            "available": True,
            "cards": cards,
            "summary": {
                "total": len(all_active),
                "typed": sum(1 for row in all_active if row.get("note_kind") == "typed"),
                "handwritten": sum(1 for row in all_active if row.get("note_kind") == "handwritten"),
            },
            "query": {
                "search": str(search or ""),
                "course": str(course or ""),
                "kind": str(kind or ""),
            },
            "filter_options": {"courses": courses, "kinds": kinds},
        }

    def _base_record(self, payload, *, note_kind):
        title = _text(payload.get("title"), limit=200)
        if not title:
            raise AnvayaNotesValidationError("Note name is required.")
        now = str(self.now())
        return {
            "id": uuid4().hex,
            "title": title,
            "course": _text(payload.get("course"), limit=100),
            "key_points": _points(payload.get("key_points")),
            "note_kind": note_kind,
            "card_style": _style(payload.get("card_style")),
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "body": "",
            "assets": [],
        }

    def create_typed_note(self, payload, uploads=()):
        record = self._base_record(payload, note_kind="typed")
        record["body"] = _body(payload.get("body"))
        clean_uploads = _validated_uploads(uploads)
        try:
            stored = self.repository.create_note(record, clean_uploads)
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("The note could not be saved.") from error
        return {"id": stored["id"]}

    def create_handwritten_note(self, payload, uploads):
        record = self._base_record(payload, note_kind="handwritten")
        clean_uploads = _validated_uploads(uploads)
        if not clean_uploads:
            raise AnvayaNotesValidationError("Choose at least one handwritten note file.")
        try:
            stored = self.repository.create_note(record, clean_uploads)
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("The note could not be saved.") from error
        return {"id": stored["id"]}

    def reader(self, note_id):
        try:
            row = self.repository.get_note(note_id)
        except AnvayaNotesNotFoundError:
            raise
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("The note could not be read.") from error
        view = self._card(row)
        view["key_points"] = list(row.get("key_points") or [])
        view["updated_at"] = str(row.get("updated_at") or "")
        view["created_at"] = str(row.get("created_at") or "")
        view["created_label"] = _label(row.get("created_at"), self.timezone_name)
        view["updated_label"] = _label(row.get("updated_at"), self.timezone_name)
        view["assets"] = [
            {
                **{key: value for key, value in asset.items() if key != "stored_name"},
                "url": "/notes/file/{}/{}".format(row["id"], asset["id"]),
            }
            for asset in list(row.get("assets") or [])
        ]
        if row.get("note_kind") == "typed":
            try:
                view["rendered_html"] = self.renderer(
                    str(row.get("body") or ""),
                    wikilinks=(),
                    note_route="/notes/view",
                    note_path="",
                    asset_route="",
                )
            except Exception:
                view["rendered_html"] = Markup("<pre>{}</pre>").format(
                    escape(str(row.get("body") or ""))
                )
        return view

    def edit_view(self, note_id):
        row = self.repository.get_note(note_id)
        return {
            "id": row["id"],
            "title": str(row.get("title") or ""),
            "course": str(row.get("course") or ""),
            "note_kind": str(row.get("note_kind") or "typed"),
            "card_style": _style(row.get("card_style")),
            "key_points_text": "\n".join(str(x) for x in list(row.get("key_points") or [])),
            "body": str(row.get("body") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "assets": list(row.get("assets") or []),
        }

    def update_note(self, note_id, payload, uploads=()):
        current = self.repository.get_note(note_id)
        title = _text(payload.get("title"), limit=200)
        if not title:
            raise AnvayaNotesValidationError("Note name is required.")
        changes = {
            "title": title,
            "course": _text(payload.get("course"), limit=100),
            "key_points": _points(payload.get("key_points")),
            "card_style": _style(payload.get("card_style")),
            "updated_at": str(self.now()),
        }
        if current.get("note_kind") == "typed":
            changes["body"] = _body(payload.get("body"))
        clean_uploads = _validated_uploads(uploads)
        try:
            updated = self.repository.update_note(
                note_id,
                expected_updated_at=str(payload.get("expected_updated_at") or ""),
                changes=changes,
                uploads=clean_uploads,
            )
        except (AnvayaNotesNotFoundError, AnvayaNotesConflictError):
            raise
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("The note could not be saved.") from error
        return {"id": updated["id"]}

    def read_asset(self, note_id, asset_id):
        try:
            asset = self.repository.read_asset(note_id, asset_id)
        except AnvayaNotesNotFoundError:
            raise
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("The file could not be read.") from error
        return {
            "bytes": asset["bytes"],
            "mimetype": asset["mimetype"],
            "filename": asset["filename"],
        }


def build_anvaya_notes_service():
    return AnvayaNotesService()
