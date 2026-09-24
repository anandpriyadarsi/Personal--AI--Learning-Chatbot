"""Full Notes Studio reader boundary for Phase 7.5.15.3.

This service composes the canonical Notes Studio read model with the existing
safe Obsidian Markdown renderer. It never opens Markdown directly and never
persists reading, Companion, note, registry, retrieval, or Tutor state.
"""
from __future__ import annotations

from datetime import date

from markupsafe import Markup, escape

from personal_learning_assistant.services.notes_studio_read_service import (
    build_configured_notes_studio_read_service,
)
from personal_learning_assistant.services.obsidian_markdown_renderer import (
    render_markdown,
)


def _date_label(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return text
    return parsed.strftime("%d %b %Y").lstrip("0")


def _escaped_fallback(source: str) -> Markup:
    return Markup('<pre class="notes-reader-render-fallback">{}</pre>').format(
        escape(str(source or ""))
    )


class NotesStudioReaderWebService:
    """Render one canonical NoteDetail into a safe academic reader view."""

    def __init__(self, read_service, *, renderer=render_markdown):
        self.read_service = read_service
        self._renderer = renderer

    def reader_view(self, relative_path):
        detail = self.read_service.get_detail(relative_path)
        card = detail.card
        source = str(detail.text or "")
        try:
            rendered = self._renderer(
                source,
                wikilinks=tuple(detail.wikilinks or ()),
                note_route="/notes/note",
                note_path=str(card.relative_path),
                asset_route="/notes/asset",
            )
            if not isinstance(rendered, Markup):
                rendered = Markup(escape(str(rendered)))
        except Exception:
            rendered = _escaped_fallback(source)

        identity = str(card.identity)
        note_id = identity.split(":", 1)[1] if identity.startswith("assistant:") else ""
        return {
            "identity": identity,
            "note_id": note_id,
            "editable": bool(note_id),
            "title": str(card.title),
            "topic": str(card.topic),
            "course": str(card.course),
            "note_type": str(card.note_type or "note"),
            "note_date": str(card.note_date),
            "note_date_label": _date_label(card.note_date),
            "card_summary": [
                str(item) for item in tuple(card.card_summary or ())[:5]
            ],
            "tags": [str(item) for item in (card.tags or ())],
            "revision_status": str(card.revision_status or "unreviewed"),
            "source": str(getattr(card, "source", "") or ""),
            "relative_path": str(card.relative_path),
            "source_hash": str(card.source_hash),
            "source_hash_short": str(card.source_hash)[:12],
            "rendered_html": rendered,
            "wikilinks": tuple(dict(item) for item in (detail.wikilinks or ())),
            "backlinks": tuple(dict(item) for item in (detail.backlinks or ())),
            "related_notes": tuple(
                {
                    **dict(item),
                    "reasons": [str(reason) for reason in item.get("reasons", ())],
                }
                for item in (getattr(detail, "related_notes", ()) or ())
            ),
            "connection_facets": tuple(
                dict(item)
                for item in (getattr(detail, "connection_facets", ()) or ())
            ),
        }


def build_notes_studio_reader_web_service() -> NotesStudioReaderWebService:
    """Build the reader around the same configured canonical service as 15.1/15.2."""

    return NotesStudioReaderWebService(
        build_configured_notes_studio_read_service()
    )
