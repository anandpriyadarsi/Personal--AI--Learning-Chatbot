from __future__ import annotations

from pathlib import Path

import pytest

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesNotFoundError,
    AnvayaNotesRepository,
)
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService


NOW = "2026-09-26T12:00:00Z"
NEXT = "2026-09-26T12:05:00Z"
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 64
JPG = b"\xff\xd8\xff\xe0" + b"j" * 64
PDF = b"%PDF-1.4\nANVAYA\n%%EOF"


def _service(tmp_path):
    ticks = iter((NOW, NEXT, NEXT))
    repository = AnvayaNotesRepository(
        notes_path=tmp_path / "anvaya_notes.json",
        assets_root=tmp_path / "anvaya_notes_assets",
    )
    return AnvayaNotesService(repository, now=lambda: next(ticks)), repository


def test_iris_template_previews_use_correct_subject_codes_and_general_has_none():
    root = Path(__file__).resolve().parents[1]
    picker = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "anvaya_card_template_picker.html"
    ).read_text(encoding="utf-8")

    for value, code in (
        ("iris-indigo", "MA103N"),
        ("iris-emerald", "CY100N"),
        ("iris-cyan", "UC100N"),
        ("iris-amber", "UC103N"),
        ("iris-coral", "DE100N"),
    ):
        assert f"('{value}'" in picker
        assert code in picker

    violet_row = next(
        line for line in picker.splitlines() if "iris-violet" in line and "CSE / General" in line
    )
    assert "MA103N" not in violet_row
    assert "CY100N" not in violet_row
    assert "UC100N" not in violet_row
    assert "UC103N" not in violet_row
    assert "DE100N" not in violet_row


def test_preview_family_uses_six_polished_named_themes():
    root = Path(__file__).resolve().parents[1]
    picker = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "anvaya_card_template_picker.html"
    ).read_text(encoding="utf-8")
    css = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "static"
        / "css"
        / "app.css"
    ).read_text(encoding="utf-8")

    names = (
        "Lecture Split",
        "Notebook Hero",
        "Diagram Focus",
        "Study Strip",
        "Paper Snapshot",
        "Glass Banner",
    )
    ids = (
        "preview-left",
        "preview-top",
        "preview-split",
        "preview-film",
        "preview-polaroid",
        "preview-banner",
    )
    for name in names:
        assert name in picker
    for template in ids:
        assert f".anvaya-note-template--{template}" in css

    # Distinct theme tokens should be present, not one generic Preview style.
    for token in (
        "--preview-left-accent",
        "--preview-top-accent",
        "--preview-split-accent",
        "--preview-film-accent",
        "--preview-polaroid-accent",
        "--preview-banner-accent",
    ):
        assert token in css


def test_repository_can_remove_one_existing_asset_without_touching_another(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {"title": "Media", "body": "Body"},
        [("one.png", PNG), ("two.jpg", JPG)],
    )
    before = repository.get_note(created["id"])
    first, second = before["assets"]
    first_path = (
        repository.assets_root / created["id"] / first["stored_name"]
    )
    second_path = (
        repository.assets_root / created["id"] / second["stored_name"]
    )
    assert first_path.exists() and second_path.exists()

    updated = repository.update_note(
        created["id"],
        expected_updated_at=before["updated_at"],
        changes={"updated_at": NEXT},
        remove_asset_ids=(first["id"],),
    )

    assert [asset["id"] for asset in updated["assets"]] == [second["id"]]
    assert not first_path.exists()
    assert second_path.exists()


def test_service_deleting_inline_image_removes_directive_and_keeps_noninline_pdf(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {
            "title": "AAS",
            "body": (
                "Before\n\n"
                "[[anvaya-upload:0|width=70|rotate=0|crop=original|caption=Curve]]\n\n"
                "After"
            ),
        },
        [("curve.png", PNG), ("reference.pdf", PDF)],
    )
    before = repository.get_note(created["id"])
    image = next(x for x in before["assets"] if x["mimetype"] == "image/png")
    pdf = next(x for x in before["assets"] if x["mimetype"] == "application/pdf")

    service.update_note(
        created["id"],
        {
            "expected_updated_at": before["updated_at"],
            "title": before["title"],
            "course": "",
            "key_points": "",
            "card_style": before["card_style"],
            # Deliberately leave the directive in the submitted body; backend
            # must remove it when the referenced asset is deleted.
            "body": before["body"],
            "remove_asset_ids": [image["id"]],
        },
    )

    after = repository.get_note(created["id"])
    assert image["id"] not in after["body"]
    assert [x["id"] for x in after["assets"]] == [pdf["id"]]
    with pytest.raises(AnvayaNotesNotFoundError):
        repository.read_asset(created["id"], image["id"])

    reader = service.reader(created["id"])
    assert [x["id"] for x in reader["assets"]] == [pdf["id"]]


def test_reader_footer_only_contains_assets_not_used_inline(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {
            "title": "Inline once, footer once",
            "body": (
                "[[anvaya-upload:0|width=70|rotate=0|crop=original|caption=One]]\n\n"
                "[[anvaya-upload:0|width=40|rotate=90|crop=1:1|caption=One again]]"
            ),
        },
        [("inline.png", PNG), ("loose.jpg", JPG), ("appendix.pdf", PDF)],
    )
    row = repository.get_note(created["id"])
    inline_id = next(x["id"] for x in row["assets"] if x["filename"] == "inline.png")

    view = service.reader(created["id"])

    assert inline_id not in [x["id"] for x in view["assets"]]
    assert {x["filename"] for x in view["assets"]} == {"loose.jpg", "appendix.pdf"}


def test_editor_supports_delete_existing_and_remove_new_media_without_wrong_indices():
    root = Path(__file__).resolve().parents[1]
    editor = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "anvaya_notes_editor.html"
    ).read_text(encoding="utf-8")

    for token in (
        "Delete file",
        'name="remove_asset_ids"',
        "data-remove-existing",
        "data-remove-new-upload",
        "DataTransfer",
        "renumberUploadDirectives",
        "removeUploadDirectives",
    ):
        assert token in editor


def test_routes_collect_multiple_asset_ids_for_deletion():
    root = Path(__file__).resolve().parents[1]
    routes = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "routes.py"
    ).read_text(encoding="utf-8")

    assert 'request.form.getlist("remove_asset_ids")' in routes


def test_reader_labels_typed_footer_as_unplaced_attachments():
    root = Path(__file__).resolve().parents[1]
    reader = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "anvaya_notes_reader.html"
    ).read_text(encoding="utf-8")

    assert "Files not placed in the note" in reader
