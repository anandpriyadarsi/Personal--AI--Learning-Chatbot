from __future__ import annotations

from pathlib import Path

import pytest
from markupsafe import Markup

from personal_learning_assistant.domain.notes_studio_template_models import (
    NoteTemplate,
    NoteTemplateSection,
)
from personal_learning_assistant.services.notes_studio_template_service import (
    NotesStudioTemplateNotFoundError,
    NotesStudioTemplateService,
    build_notes_studio_template_service,
)


EXPECTED = {
    "concept": (
        "Key Points",
        "Intuition",
        "Core Explanation",
        "Visual",
        "Example",
        "Common Mistakes",
        "Summary",
        "Related Notes",
    ),
    "lecture": (
        "Lecture Details",
        "Topics Covered",
        "Notes",
        "Diagrams",
        "Questions / Doubts",
        "Takeaways",
    ),
    "revision": (
        "Must Remember",
        "Formulas / Facts",
        "Common Traps",
        "Quick Examples",
        "Self-Test",
    ),
    "formula-sheet": (
        "Definitions",
        "Formulas",
        "Conditions",
        "Compact Examples",
    ),
    "problem-solving": (
        "Problem",
        "Concepts Needed",
        "Approach",
        "Working",
        "Solution",
        "Mistakes",
        "Alternative Method",
    ),
}


def test_registry_has_exactly_five_stable_academic_templates():
    service = build_notes_studio_template_service()
    templates = service.list_templates()

    assert [item["id"] for item in templates] == list(EXPECTED)
    assert [item["name"] for item in templates] == [
        "Concept Note",
        "Lecture Note",
        "Revision Note",
        "Formula Sheet",
        "Problem-Solving Note",
    ]
    assert all(item["note_type"] for item in templates)
    assert all(item["description"] for item in templates)
    assert all(item["best_for"] for item in templates)


@pytest.mark.parametrize("template_id,sections", EXPECTED.items())
def test_each_template_preserves_master_spec_section_contract(template_id, sections):
    view = build_notes_studio_template_service().template_view(template_id)

    assert tuple(item["heading"] for item in view["sections"]) == sections
    assert view["markdown"].startswith("# ")
    for heading in sections:
        assert "## {}".format(heading) in view["markdown"]


def test_template_models_are_immutable_and_storage_neutral():
    section = NoteTemplateSection("Key Points", "Capture the essentials.")
    template = NoteTemplate(
        template_id="concept",
        name="Concept Note",
        note_type="concept",
        description="Understand one concept deeply.",
        best_for="Theory and intuition.",
        sections=(section,),
    )

    with pytest.raises(Exception):
        template.name = "Changed"
    with pytest.raises(Exception):
        section.heading = "Changed"

    source = (
        Path(__file__).resolve().parents[1]
        / "personal_learning_assistant/domain/notes_studio_template_models.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("sqlite", "json", "Path(", "open(", "write_", "read_"):
        assert forbidden not in source


def test_template_markdown_is_portable_scaffold_not_second_storage_format():
    service = build_notes_studio_template_service()
    view = service.template_view("concept")
    markdown = view["markdown"]

    assert "assistant_id:" not in markdown
    assert "source_hash" not in markdown
    assert "<script" not in markdown.lower()
    assert "[Add 2–5 concise points" in markdown
    assert view["defaults"] == {
        "note_type": "concept",
        "revision_status": "unreviewed",
    }


def test_template_preview_reuses_safe_markdown_renderer():
    calls = []

    def renderer(markdown, **kwargs):
        calls.append((markdown, kwargs))
        return Markup("<h1>Preview</h1>")

    service = NotesStudioTemplateService(renderer=renderer)
    view = service.template_view("revision")

    assert view["rendered_preview"] == Markup("<h1>Preview</h1>")
    assert calls and calls[0][0] == view["markdown"]


def test_template_lookup_is_exact_and_safe():
    service = build_notes_studio_template_service()

    with pytest.raises(NotesStudioTemplateNotFoundError):
        service.template_view("../concept")
    with pytest.raises(NotesStudioTemplateNotFoundError):
        service.template_view("unknown")
    with pytest.raises(NotesStudioTemplateNotFoundError):
        service.template_view("")


def test_template_service_has_no_writes_ai_tutor_or_storage_dependencies():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "personal_learning_assistant/services/notes_studio_template_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "personal_learning_assistant.tutor",
        "NotesStudioService",
        "sqlite3",
        "LegacyJson",
        "open(",
        ".read_text(",
        ".read_bytes(",
        ".write_text(",
        ".write_bytes(",
        "os.replace(",
        "requests",
        "httpx",
        "openai",
    ):
        assert forbidden not in source


class FakeTemplateService:
    def list_templates(self):
        return [
            {
                "id": "concept",
                "name": "Concept Note",
                "note_type": "concept",
                "description": "Understand one concept deeply.",
                "best_for": "Theory, definitions, and intuition.",
                "section_count": 8,
                "section_names": list(EXPECTED["concept"]),
            },
            {
                "id": "lecture",
                "name": "Lecture Note",
                "note_type": "lecture",
                "description": "Capture one class or lecture.",
                "best_for": "Classroom and video lectures.",
                "section_count": 6,
                "section_names": list(EXPECTED["lecture"]),
            },
        ]

    def template_view(self, template_id):
        if template_id != "concept":
            raise NotesStudioTemplateNotFoundError("missing")
        return {
            "id": "concept",
            "name": "Concept Note",
            "note_type": "concept",
            "description": "Understand one concept deeply.",
            "best_for": "Theory, definitions, and intuition.",
            "defaults": {
                "note_type": "concept",
                "revision_status": "unreviewed",
            },
            "sections": [
                {"heading": heading, "guidance": "Guidance for {}".format(heading)}
                for heading in EXPECTED["concept"]
            ],
            "markdown": "# Concept Note\n\n## Key Points\n",
            "rendered_preview": Markup(
                "<h1>Concept Note</h1><h2>Key Points</h2><p>Preview body.</p>"
            ),
        }


def _app(service):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "NOTES_STUDIO_TEMPLATE_SERVICE_FACTORY": lambda: service,
        }
    )


def test_template_gallery_route_renders_cards_without_write_controls():
    response = _app(FakeTemplateService()).test_client().get("/notes/templates")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Academic note templates",
        "Concept Note",
        "Lecture Note",
        "Theory, definitions, and intuition.",
        "Preview template",
    ):
        assert expected in html
    assert "<form" not in html.lower()
    assert "Save note" not in html
    assert "Create note" not in html


def test_template_preview_route_renders_sections_and_safe_preview():
    response = _app(FakeTemplateService()).test_client().get(
        "/notes/templates/concept"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Concept Note",
        "Template preview",
        "Key Points",
        "Core Explanation",
        "Preview body.",
        "Editor integration arrives in Phase 7.5.15.6",
    ):
        assert expected in html
    assert "<h1>Concept Note</h1>" in html
    assert "textarea" not in html.lower()


def test_template_preview_route_returns_safe_404():
    response = _app(FakeTemplateService()).test_client().get(
        "/notes/templates/missing"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 404
    assert "Template not found" in html
    assert "missing" not in html.lower()


def test_notes_library_exposes_template_gallery_link():
    root = Path(__file__).resolve().parents[1]
    template = (
        root / "personal_learning_assistant/ui/web/templates/notes_library.html"
    ).read_text(encoding="utf-8")

    assert "url_for('web.notes_templates')" in template
    assert "Browse templates" in template


def test_template_pages_are_responsive_and_do_not_use_unsafe_markup_filter():
    root = Path(__file__).resolve().parents[1]
    gallery = (
        root / "personal_learning_assistant/ui/web/templates/notes_templates.html"
    ).read_text(encoding="utf-8")
    preview = (
        root / "personal_learning_assistant/ui/web/templates/notes_template_preview.html"
    ).read_text(encoding="utf-8")
    css = (
        root / "personal_learning_assistant/ui/web/static/css/app.css"
    ).read_text(encoding="utf-8")

    assert "template-gallery-grid" in gallery
    assert "template-preview-layout" in preview
    assert "template.rendered_preview" in preview
    assert "|safe" not in preview
    assert ".template-gallery-grid" in css
    assert ".template-preview-layout" in css
    assert "@media (max-width: 900px)" in css


def test_routes_expose_template_get_endpoints_only():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "personal_learning_assistant/ui/web/routes.py"
    ).read_text(encoding="utf-8")

    assert '@web_blueprint.get("/notes/templates")' in source
    assert '@web_blueprint.get("/notes/templates/<template_id>")' in source
    assert '@web_blueprint.post("/notes/templates' not in source
    assert "NOTES_STUDIO_TEMPLATE_SERVICE_FACTORY" in source
