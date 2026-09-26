from __future__ import annotations

from pathlib import Path

from personal_learning_assistant.services.anvaya_notes_service import (
    AnvayaNotesService,
    _card_family,
    _style,
)


def test_legacy_card_styles_map_to_new_default_templates():
    assert _style("iris") == "iris-indigo"
    assert _style("preview") == "preview-left"
    assert _style("square") == "square-clean"
    assert _style("") == "iris-indigo"


def test_each_template_maps_to_its_family():
    for value in (
        "iris-indigo",
        "iris-emerald",
        "iris-cyan",
        "iris-amber",
        "iris-coral",
        "iris-violet",
    ):
        assert _card_family(value) == "iris"
    for value in (
        "preview-left",
        "preview-top",
        "preview-split",
        "preview-film",
        "preview-polaroid",
        "preview-banner",
    ):
        assert _card_family(value) == "preview"
    for value in (
        "square-clean",
        "square-outline",
        "square-centered",
        "square-corner",
        "square-grid",
        "square-soft",
    ):
        assert _card_family(value) == "square"


def test_card_view_exposes_exact_template_and_family():
    service = object.__new__(AnvayaNotesService)
    service.timezone_name = "Asia/Kolkata"
    card = AnvayaNotesService._card(
        service,
        {
            "id": "n1",
            "title": "LU Factorization",
            "course": "MA103N",
            "note_kind": "typed",
            "card_style": "iris-indigo",
            "key_points": ["Multipliers"],
            "created_at": "2026-09-26T10:00:00Z",
            "updated_at": "2026-09-26T10:00:00Z",
            "assets": [],
        },
    )
    assert card["card_style"] == "iris-indigo"
    assert card["card_family"] == "iris"


def test_picker_has_three_families_and_six_templates_in_each():
    root = Path(__file__).resolve().parents[1]
    picker = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "anvaya_card_template_picker.html"
    ).read_text(encoding="utf-8")

    assert picker.count('data-card-family-tab=') == 3
    assert picker.count('data-card-family-panel=') == 3
    assert picker.count('name="card_style"') == 3
    # Each radio is emitted six times by its family loop at runtime; source
    # contains exactly six template tuples per family.
    assert picker.count("iris-") >= 6
    assert picker.count("preview-") >= 6
    assert picker.count("square-") >= 6

    for label in (
        "Indigo Matrix",
        "Emerald Lab",
        "Cyan Data",
        "Amber Heritage",
        "Coral Sketch",
        "Violet Code",
        "Left Preview",
        "Top Preview",
        "Balanced Split",
        "Film Strip",
        "Polaroid",
        "Banner",
        "Clean",
        "Outline",
        "Centered",
        "Corner Accent",
        "Grid",
        "Soft Tile",
    ):
        assert label in picker


def test_iris_family_contains_subject_specific_choices():
    root = Path(__file__).resolve().parents[1]
    picker = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "anvaya_card_template_picker.html"
    ).read_text(encoding="utf-8")

    for subject in (
        "Math / Linear Algebra",
        "Engineering Chemistry",
        "Data Science / AI",
        "Indian Knowledge System",
        "Design Thinking",
        "CSE / General",
    ):
        assert subject in picker


def test_library_uses_family_and_exact_template_classes():
    root = Path(__file__).resolve().parents[1]
    library = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "anvaya_notes_library.html"
    ).read_text(encoding="utf-8")

    assert "anvaya-note-card--{{ note.card_family }}" in library
    assert "anvaya-note-template--{{ note.card_style }}" in library
    assert "note.card_family == 'preview'" in library


def test_css_contains_all_eighteen_template_selectors():
    root = Path(__file__).resolve().parents[1]
    css = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "static"
        / "css"
        / "app.css"
    ).read_text(encoding="utf-8")

    templates = (
        "iris-indigo","iris-emerald","iris-cyan","iris-amber","iris-coral","iris-violet",
        "preview-left","preview-top","preview-split","preview-film","preview-polaroid","preview-banner",
        "square-clean","square-outline","square-centered","square-corner","square-grid","square-soft",
    )
    for template in templates:
        assert f".anvaya-note-template--{template}" in css


def test_typed_and_handwritten_forms_both_include_template_gallery():
    root = Path(__file__).resolve().parents[1]
    editor = (
        root / "personal_learning_assistant/ui/web/templates/anvaya_notes_editor.html"
    ).read_text(encoding="utf-8")
    upload = (
        root / "personal_learning_assistant/ui/web/templates/anvaya_notes_upload.html"
    ).read_text(encoding="utf-8")

    assert 'include "anvaya_card_template_picker.html"' in editor
    assert 'include "anvaya_card_template_picker.html"' in upload
