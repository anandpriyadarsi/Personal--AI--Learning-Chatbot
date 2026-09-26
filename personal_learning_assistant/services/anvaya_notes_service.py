"""Independent ANVAYA Notes application service.

ANVAYA Notes is intentionally separate from the Obsidian workspace. It owns
personal typed/handwritten notes and app-managed uploads only.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from markupsafe import Markup, escape

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesConflictError,
    AnvayaNotesNotFoundError,
    AnvayaNotesRepository,
    AnvayaNotesRepositoryError,
)


MAX_ASSET_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_UPLOADS = 20
MAX_EXPANDED_FILES = 60
CARD_TEMPLATE_FAMILIES = {
    "iris": (
        "iris-indigo",
        "iris-emerald",
        "iris-cyan",
        "iris-amber",
        "iris-coral",
        "iris-violet",
    ),
    "preview": (
        "preview-left",
        "preview-top",
        "preview-split",
        "preview-film",
        "preview-polaroid",
        "preview-banner",
    ),
    "square": (
        "square-clean",
        "square-outline",
        "square-centered",
        "square-corner",
        "square-grid",
        "square-soft",
    ),
}
CARD_TEMPLATES = {
    template
    for templates in CARD_TEMPLATE_FAMILIES.values()
    for template in templates
}
LEGACY_CARD_STYLE_MAP = {
    "iris": "iris-indigo",
    "preview": "preview-left",
    "square": "square-clean",
}
NOTE_KINDS = {"typed", "handwritten"}
_ALLOWED = {
    ".pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    ".png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
}
_MEDIA_WIDTHS = (25, 40, 55, 70, 85, 100)
_MEDIA_ROTATIONS = (0, 90, 180, 270)
_MEDIA_CROPS = {"original", "1:1", "4:3", "3:4", "16:9"}
_UPLOAD_DIRECTIVE = re.compile(
    r"(?m)^\[\[anvaya-upload:(?P<index>\d+)(?P<options>(?:\|[^\]\r\n]*)?)\]\]\s*$"
)
_IMAGE_DIRECTIVE = re.compile(
    r"(?m)^\[\[anvaya-image:(?P<asset>[A-Za-z0-9_-]+)(?P<options>(?:\|[^\]\r\n]*)?)\]\]\s*$"
)


class AnvayaNotesError(RuntimeError):
    pass


class AnvayaNotesValidationError(AnvayaNotesError, ValueError):
    pass


class AnvayaNotesUnavailableError(AnvayaNotesError):
    pass


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


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
    style = _text(value, limit=40).casefold() or "iris-indigo"
    style = LEGACY_CARD_STYLE_MAP.get(style, style)
    return style if style in CARD_TEMPLATES else "iris-indigo"


def _card_family(style):
    value = _style(style)
    return value.split("-", 1)[0]


def _stored_style(value, *, fallback="iris"):
    raw = _text(value, limit=40).casefold()
    if not raw:
        return str(fallback or "iris")
    if raw in LEGACY_CARD_STYLE_MAP or raw in CARD_TEMPLATES:
        return raw
    return "iris-indigo"


def _safe_upload_name(filename, suffix):
    safe_name = Path(str(filename or "")).name
    safe_name = re.sub(r"[^A-Za-z0-9._() \-]+", "_", safe_name).strip(" .")[:220]
    return safe_name or ("note" + suffix)


def _validated_single_upload(filename, raw, *, source_index):
    suffix = Path(str(filename or "")).suffix.casefold()
    rule = _ALLOWED.get(suffix)
    if rule is None or not rule[1](raw):
        raise AnvayaNotesValidationError(
            "Only valid PDF, PNG, JPG, or JPEG files are allowed."
        )
    return {
        "id": uuid4().hex,
        "filename": _safe_upload_name(filename, suffix),
        "bytes": raw,
        "suffix": suffix,
        "mimetype": rule[0],
        "source_index": int(source_index),
    }


def _zip_entry_is_metadata(name):
    parts = [part for part in str(name or "").replace("\\", "/").split("/") if part]
    if not parts:
        return True
    return parts[0] == "__MACOSX" or parts[-1] in {".DS_Store", "Thumbs.db"}


def _expand_zip(filename, raw, *, source_index):
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise AnvayaNotesValidationError("ZIP files must be 50 MB or smaller.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as error:
        raise AnvayaNotesValidationError("The ZIP file is invalid.") from error

    clean = []
    expanded_bytes = 0
    try:
        for info in archive.infolist():
            if info.is_dir() or _zip_entry_is_metadata(info.filename):
                continue
            name = str(info.filename or "").replace("\\", "/")
            path = PurePosixPath(name)
            if (
                not name
                or name.startswith("/")
                or any(part == ".." for part in path.parts)
                or (path.parts and ":" in path.parts[0])
            ):
                raise AnvayaNotesValidationError("ZIP contains an unsafe file path.")
            suffix = path.suffix.casefold()
            if suffix == ".zip":
                raise AnvayaNotesValidationError("Nested ZIP files are not allowed.")
            if suffix not in _ALLOWED:
                raise AnvayaNotesValidationError(
                    "ZIP may contain only PDF, PNG, JPG, or JPEG files."
                )
            if info.flag_bits & 0x1:
                raise AnvayaNotesValidationError("Encrypted ZIP entries are not allowed.")
            if info.file_size <= 0 or info.file_size > MAX_ASSET_BYTES:
                raise AnvayaNotesValidationError(
                    "Each extracted ZIP file must be between 1 byte and 25 MB."
                )
            if info.compress_size > 0 and info.file_size > info.compress_size * 200:
                raise AnvayaNotesValidationError("ZIP expansion ratio is unsafe.")
            expanded_bytes += info.file_size
            if expanded_bytes > MAX_EXPANDED_BYTES:
                raise AnvayaNotesValidationError(
                    "ZIP expands beyond the 100 MB note import limit."
                )
            if len(clean) >= MAX_EXPANDED_FILES:
                raise AnvayaNotesValidationError(
                    "ZIP contains too many files for one note."
                )
            try:
                payload = archive.read(info)
            except (RuntimeError, OSError, EOFError, zipfile.BadZipFile) as error:
                raise AnvayaNotesValidationError(
                    "A ZIP entry could not be read safely."
                ) from error
            if len(payload) != info.file_size:
                raise AnvayaNotesValidationError("ZIP entry size is inconsistent.")
            clean.append(
                _validated_single_upload(
                    path.name,
                    payload,
                    source_index=source_index,
                )
            )
    finally:
        archive.close()

    if not clean:
        raise AnvayaNotesValidationError("ZIP contains no supported note files.")
    return clean


def _validated_uploads(uploads):
    clean = []
    originals = tuple(uploads or ())
    if len(originals) > MAX_UPLOADS:
        raise AnvayaNotesValidationError("Too many files were selected.")
    for source_index, (filename, payload) in enumerate(originals):
        raw = bytes(payload or "")
        suffix = Path(str(filename or "")).suffix.casefold()
        if suffix == ".zip":
            clean.extend(
                _expand_zip(filename, raw, source_index=source_index)
            )
            if len(clean) > MAX_EXPANDED_FILES:
                raise AnvayaNotesValidationError(
                    "Too many note files were imported."
                )
            continue
        if not raw or len(raw) > MAX_ASSET_BYTES:
            raise AnvayaNotesValidationError(
                "Each file must be between 1 byte and 25 MB."
            )
        clean.append(
            _validated_single_upload(
                filename,
                raw,
                source_index=source_index,
            )
        )
        if len(clean) > MAX_EXPANDED_FILES:
            raise AnvayaNotesValidationError("Too many note files were imported.")
    return tuple(clean)


def _parse_media_options(raw_options):
    values = {}
    for token in str(raw_options or "").split("|"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key.strip().casefold()] = value.strip()

    try:
        requested_width = int(values.get("width", "70"))
    except ValueError:
        requested_width = 70
    width = min(_MEDIA_WIDTHS, key=lambda item: abs(item - requested_width))

    try:
        requested_rotation = int(values.get("rotate", "0"))
    except ValueError:
        requested_rotation = 0
    rotation = (
        requested_rotation
        if requested_rotation in _MEDIA_ROTATIONS
        else 0
    )

    crop = values.get("crop", "original").casefold()
    if crop not in _MEDIA_CROPS:
        crop = "original"

    caption = _text(values.get("caption", ""), limit=160)
    caption = caption.replace("|", " ").replace("]", " ").strip()
    return {
        "width": width,
        "rotate": rotation,
        "crop": crop,
        "caption": caption,
    }


def _media_directive(asset_id, options):
    return (
        "[[anvaya-image:{asset}|width={width}|rotate={rotate}|crop={crop}|caption={caption}]]"
    ).format(
        asset=str(asset_id),
        width=options["width"],
        rotate=options["rotate"],
        crop=options["crop"],
        caption=options["caption"],
    )


def _normalize_image_directives(body):
    def replace(match):
        return _media_directive(
            match.group("asset"),
            _parse_media_options(match.group("options")),
        )
    return _IMAGE_DIRECTIVE.sub(replace, str(body or ""))


def _resolve_upload_directives(body, uploads):
    by_source = {}
    for item in tuple(uploads or ()):
        by_source.setdefault(int(item.get("source_index", -1)), []).append(item)

    def replace(match):
        source_index = int(match.group("index"))
        options = _parse_media_options(match.group("options"))
        images = [
            item
            for item in by_source.get(source_index, ())
            if str(item.get("mimetype") or "").startswith("image/")
        ]
        return "\n\n".join(
            _media_directive(item["id"], options)
            for item in images
        )

    resolved = _UPLOAD_DIRECTIVE.sub(replace, str(body or ""))
    return _normalize_image_directives(resolved)


def _media_crop_class(value):
    return {
        "original": "original",
        "1:1": "1x1",
        "4:3": "4x3",
        "3:4": "3x4",
        "16:9": "16x9",
    }[value]


def _remove_image_directives(body, asset_ids):
    remove_ids = {str(value or "").strip() for value in tuple(asset_ids or ()) if str(value or "").strip()}

    def replace(match):
        return "" if match.group("asset") in remove_ids else match.group(0)

    cleaned = _IMAGE_DIRECTIVE.sub(replace, str(body or ""))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _inline_asset_ids(body, assets):
    owned = {
        str(item.get("id") or "")
        for item in tuple(assets or ())
        if str(item.get("mimetype") or "").startswith("image/")
    }
    return {
        match.group("asset")
        for match in _IMAGE_DIRECTIVE.finditer(str(body or ""))
        if match.group("asset") in owned
    }


def _render_typed_body(renderer, note_id, body, assets):
    asset_map = {
        str(item.get("id") or ""): item
        for item in tuple(assets or ())
    }
    placeholders = []
    used_ids = set()

    def replace(match):
        asset_id = str(match.group("asset") or "")
        options = _parse_media_options(match.group("options"))
        asset = asset_map.get(asset_id)
        token = "ANVAYANATIVEMEDIA{}TOKEN".format(len(placeholders))
        if asset is None or not str(asset.get("mimetype") or "").startswith("image/"):
            html = Markup(
                '<div class="anvaya-inline-media-unavailable" role="note">'
                'Image unavailable</div>'
            )
        else:
            used_ids.add(asset_id)
            caption = options["caption"] or str(asset.get("filename") or "")
            url = "/notes/file/{}/{}".format(note_id, asset_id)
            html = Markup(
                '<figure class="anvaya-inline-media anvaya-media-width-{} '
                'anvaya-media-crop-{}">'
                '<div class="anvaya-inline-media-frame">'
                '<img class="anvaya-media-rotate-{}" src="{}" alt="{}" '
                'loading="lazy" decoding="async" referrerpolicy="no-referrer">'
                '</div>{}</figure>'
            ).format(
                options["width"],
                escape(_media_crop_class(options["crop"])),
                options["rotate"],
                escape(url),
                escape(caption),
                (
                    Markup("<figcaption>{}</figcaption>").format(escape(caption))
                    if caption
                    else Markup("")
                ),
            )
        placeholders.append((token, str(html)))
        return token

    source = _IMAGE_DIRECTIVE.sub(replace, str(body or ""))
    rendered = str(
        renderer(
            source,
            wikilinks=(),
            note_route="/notes/view",
            note_path="",
            asset_route="",
        )
    )
    for token, html in placeholders:
        rendered = rendered.replace("<p>{}</p>\n".format(token), html + "\n")
        rendered = rendered.replace("<p>{}</p>".format(token), html)
        rendered = rendered.replace(token, html)
    return Markup(rendered), used_ids


def _display_timezone(timezone_name):
    name = str(timezone_name or "").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # Windows/Python installations may not ship the optional IANA tzdata
        # database. ANVAYA's configured personal timezone is Asia/Kolkata,
        # which has a stable UTC+05:30 offset and no daylight-saving changes.
        if name.casefold() == "asia/kolkata":
            return timezone(timedelta(hours=5, minutes=30))
        return timezone.utc


def _label(value, timezone_name):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        local = parsed.astimezone(_display_timezone(timezone_name))
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
            "card_family": _card_family(row.get("card_style")),
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
            # Store legacy ids unchanged for backward compatibility; rendering
            # maps them to their new default template. New web forms submit an
            # exact 15.12 template id which is stored unchanged per note.
            "card_style": _stored_style(payload.get("card_style"), fallback="iris"),
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "body": "",
            "assets": [],
        }

    def create_typed_note(self, payload, uploads=()):
        record = self._base_record(payload, note_kind="typed")
        clean_uploads = _validated_uploads(uploads)
        record["body"] = _resolve_upload_directives(
            _body(payload.get("body")),
            clean_uploads,
        )
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
        all_assets = [
            {
                **{key: value for key, value in asset.items() if key != "stored_name"},
                "url": "/notes/file/{}/{}".format(row["id"], asset["id"]),
            }
            for asset in list(row.get("assets") or [])
        ]
        used_inline_ids = set()
        if row.get("note_kind") == "typed":
            used_inline_ids = _inline_asset_ids(
                row.get("body") or "",
                row.get("assets") or (),
            )
            try:
                view["rendered_html"], rendered_inline_ids = _render_typed_body(
                    self.renderer,
                    row["id"],
                    str(row.get("body") or ""),
                    row.get("assets") or (),
                )
                used_inline_ids.update(rendered_inline_ids)
            except Exception:
                view["rendered_html"] = Markup("<pre>{}</pre>").format(
                    escape(str(row.get("body") or ""))
                )
        view["assets"] = [
            asset
            for asset in all_assets
            if str(asset.get("id") or "") not in used_inline_ids
        ]
        return view

    def edit_view(self, note_id):
        try:
            row = self.repository.get_note(note_id)
        except AnvayaNotesNotFoundError:
            raise
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("The note could not be opened.") from error
        return {
            "id": row["id"],
            "title": str(row.get("title") or ""),
            "course": str(row.get("course") or ""),
            "note_kind": str(row.get("note_kind") or "typed"),
            "card_style": _style(row.get("card_style")),
            "key_points_text": "\n".join(str(x) for x in list(row.get("key_points") or [])),
            "body": str(row.get("body") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "assets": [
                {
                    **{key: value for key, value in asset.items() if key != "stored_name"},
                    "url": "/notes/file/{}/{}".format(row["id"], asset["id"]),
                    "is_image": str(asset.get("mimetype") or "").startswith("image/"),
                    "is_inline": (
                        str(asset.get("id") or "") in _inline_asset_ids(
                            row.get("body") or "",
                            row.get("assets") or (),
                        )
                    ),
                }
                for asset in list(row.get("assets") or [])
            ],
        }

    def update_note(self, note_id, payload, uploads=()):
        try:
            current = self.repository.get_note(note_id)
        except AnvayaNotesNotFoundError:
            raise
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError("The note could not be opened.") from error
        title = _text(payload.get("title"), limit=200)
        if not title:
            raise AnvayaNotesValidationError("Note name is required.")
        changes = {
            "title": title,
            "course": _text(payload.get("course"), limit=100),
            "key_points": _points(payload.get("key_points")),
            "card_style": _stored_style(
                payload.get("card_style"),
                fallback=current.get("card_style") or "iris",
            ),
            "updated_at": str(self.now()),
        }
        clean_uploads = _validated_uploads(uploads)
        remove_asset_ids = [
            str(value or "").strip()
            for value in list(payload.get("remove_asset_ids") or [])
            if str(value or "").strip()
        ]
        if current.get("note_kind") == "typed":
            resolved_body = _resolve_upload_directives(
                _body(payload.get("body")),
                clean_uploads,
            )
            changes["body"] = _remove_image_directives(
                resolved_body,
                remove_asset_ids,
            )
        try:
            updated = self.repository.update_note(
                note_id,
                expected_updated_at=str(payload.get("expected_updated_at") or ""),
                changes=changes,
                uploads=clean_uploads,
                remove_asset_ids=remove_asset_ids,
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
