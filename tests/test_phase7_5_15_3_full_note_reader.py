from __future__ import annotations

from pathlib import Path

import pytest
from markupsafe import Markup

from personal_learning_assistant.domain.notes_studio_read_models import NoteCard, NoteDetail
from personal_learning_assistant.services.notes_studio_read_service import (
    NotesStudioReadNotFoundError,
    NotesStudioReadUnavailableError,
)
from personal_learning_assistant.services.notes_studio_reader_service import (
    NotesStudioReaderWebService,
)


def _card(**overrides):
    values = {
        "identity": "assistant:11111111-1111-4111-8111-111111111111",
        "relative_path": "Math/LU.md",
        "source_hash": "a" * 64,
        "title": "LU Factorization",
        "topic": "Matrix factorization",
        "course": "MA103N",
        "note_type": "concept",
        "note_date": "2026-09-24",
        "card_summary": ("A = LU", "L stores elimination multipliers"),
        "tags": ("linear-algebra", "exam"),
        "revision_status": "learning",
    }
    values.update(overrides)
    return NoteCard(**values)


def _detail(**card_overrides):
    return NoteDetail(
        card=_card(**card_overrides),
        text=(
            "---\n"
            "title: LU Factorization\n"
            "course: MA103N\n"
            "---\n"
            "# LU Factorization\n\n"
            "Elimination produces **L** and **U**.\n\n"
            "See [[Rank]].\n"
        ),
        wikilinks=(
            {
                "raw": "Rank",
                "target": "Rank",
                "heading": "",
                "label": "Rank",
                "resolved_path": "Math/Rank.md",
                "resolved_title": "Rank",
                "ambiguous": False,
            },
        ),
        backlinks=(
            {"relative_path": "Math/Elimination.md", "title": "Elimination"},
        ),
    )


class FakeReadService:
    def __init__(self, detail=None, error=None):
        self.detail = detail or _detail()
        self.error = error
        self.paths = []

    def get_detail(self, path):
        self.paths.append(path)
        if self.error:
            raise self.error
        return self.detail


def test_reader_view_renders_full_markdown_but_does_not_expose_raw_body():
    calls = []

    def renderer(source, *, wikilinks=(), note_route="/obsidian/note", note_path="", asset_route=""):
        calls.append((source, wikilinks, note_route, note_path, asset_route))
        return Markup("<h1>LU Factorization</h1><p>Rendered body</p>")

    read = FakeReadService()
    view = NotesStudioReaderWebService(read, renderer=renderer).reader_view("Math/LU.md")

    assert read.paths == ["Math/LU.md"]
    assert calls[0][0].startswith("---\ntitle:")
    assert calls[0][2] == "/notes/note"
    assert calls[0][3] == "Math/LU.md"
    assert calls[0][4] == "/notes/asset"
    assert "text" not in view
    assert "body" not in view
    assert view["rendered_html"] == Markup(
        "<h1>LU Factorization</h1><p>Rendered body</p>"
    )
    assert view["title"] == "LU Factorization"
    assert view["course"] == "MA103N"
    assert view["note_date_label"] == "24 Sep 2026"
    assert view["backlinks"][0]["title"] == "Elimination"


def test_reader_renderer_failure_falls_back_to_escaped_source():
    source = '<script>alert("x")</script>\n# Safe heading\n'
    detail = NoteDetail(card=_card(), text=source, wikilinks=(), backlinks=())

    def broken_renderer(*_args, **_kwargs):
        raise RuntimeError("renderer internals")

    view = NotesStudioReaderWebService(
        FakeReadService(detail),
        renderer=broken_renderer,
    ).reader_view("Math/LU.md")

    html = str(view["rendered_html"])
    assert "<script>" not in html
    assert "&lt;script&gt;alert" in html
    assert "Safe heading" in html


def test_reader_preserves_canonical_not_found_and_unavailable_errors():
    for error in (
        NotesStudioReadNotFoundError("missing"),
        NotesStudioReadUnavailableError("unavailable"),
    ):
        service = NotesStudioReaderWebService(FakeReadService(error=error))
        with pytest.raises(type(error)):
            service.reader_view("Math/Missing.md")


def test_reader_view_formats_invalid_or_absent_date_without_inventing_one():
    invalid = NotesStudioReaderWebService(
        FakeReadService(_detail(note_date="Semester 1"))
    ).reader_view("Math/LU.md")
    missing = NotesStudioReaderWebService(
        FakeReadService(_detail(note_date=""))
    ).reader_view("Math/LU.md")

    assert invalid["note_date_label"] == "Semester 1"
    assert missing["note_date_label"] == ""


class FakeReaderWebService:
    def __init__(self, *, error=None):
        self.error = error
        self.paths = []

    def reader_view(self, path):
        self.paths.append(path)
        if self.error:
            raise self.error
        return {
            "title": "LU Factorization",
            "topic": "Matrix factorization",
            "course": "MA103N",
            "note_type": "concept",
            "note_date": "2026-09-24",
            "note_date_label": "24 Sep 2026",
            "card_summary": ["A = LU", "L stores elimination multipliers"],
            "tags": ["linear-algebra", "exam"],
            "revision_status": "learning",
            "relative_path": "Math/LU.md",
            "source_hash": "a" * 64,
            "source_hash_short": "aaaaaaaaaaaa",
            "rendered_html": Markup(
                "<h1>LU Factorization</h1>"
                "<p>Elimination produces <strong>L</strong> and <strong>U</strong>.</p>"
            ),
            "wikilinks": [
                {
                    "label": "Rank",
                    "resolved_path": "Math/Rank.md",
                    "resolved_title": "Rank",
                    "ambiguous": False,
                }
            ],
            "backlinks": [
                {"relative_path": "Math/Elimination.md", "title": "Elimination"}
            ],
        }


def _app(service):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "NOTES_STUDIO_READER_SERVICE_FACTORY": lambda: service,
        }
    )


def test_notes_reader_route_renders_academic_layout_and_connections():
    service = FakeReaderWebService()
    response = _app(service).test_client().get("/notes/note?path=Math%2FLU.md")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert service.paths == ["Math/LU.md"]
    for expected in (
        "Full Note Reader",
        "LU Factorization",
        "Matrix factorization",
        "MA103N",
        "Concept",
        "24 Sep 2026",
        "A = LU",
        "L stores elimination multipliers",
        "Elimination produces",
        "<strong>L</strong>",
        "Backlinks",
        "Elimination",
        "Linked notes",
        "Rank",
        "Math/LU.md",
    ):
        assert expected in html
    assert "Edit note" not in html
    assert "textarea" not in html.lower()


def test_notes_reader_route_maps_missing_and_unavailable_safely():
    missing = _app(
        FakeReaderWebService(error=NotesStudioReadNotFoundError("C:/SECRET"))
    ).test_client().get("/notes/note?path=Missing.md")
    unavailable = _app(
        FakeReaderWebService(error=NotesStudioReadUnavailableError("C:/SECRET"))
    ).test_client().get("/notes/note?path=Math%2FLU.md")

    assert missing.status_code == 404
    assert unavailable.status_code == 503
    assert "SECRET" not in missing.get_data(as_text=True)
    assert "SECRET" not in unavailable.get_data(as_text=True)


def test_notes_library_cards_now_open_notes_studio_reader():
    root = Path(__file__).resolve().parents[1]
    template = (
        root / "personal_learning_assistant/ui/web/templates/notes_library.html"
    ).read_text(encoding="utf-8")

    assert "url_for('web.notes_reader'" in template
    assert "url_for('web.obsidian_note', path=note.relative_path)" not in template


def test_reader_template_uses_safe_markup_without_raw_markdown_or_script_tracking():
    root = Path(__file__).resolve().parents[1]
    template = (
        root / "personal_learning_assistant/ui/web/templates/notes_reader.html"
    ).read_text(encoding="utf-8")
    css = (
        root / "personal_learning_assistant/ui/web/static/css/app.css"
    ).read_text(encoding="utf-8")

    assert "note.rendered_html" in template
    assert "|safe" not in template
    assert "note.text" not in template
    assert "note.body" not in template
    assert "obsidian_reader.js" not in template
    assert "notes-reader-layout" in template
    assert ".notes-reader-layout" in css
    assert "@media (max-width: 900px)" in css


def test_notes_reader_uses_existing_renderer_and_canonical_read_service_only():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "personal_learning_assistant/services/notes_studio_reader_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "personal_learning_assistant.tutor",
        "NotesStudioService",
        "sqlite3",
        ".read_text(",
        ".read_bytes(",
        ".write_text(",
        ".write_bytes(",
        "os.replace(",
        "apply_snapshot(",
    ):
        assert forbidden not in source
    assert "notes_studio_read_service" in source
    assert "obsidian_markdown_renderer" in source
