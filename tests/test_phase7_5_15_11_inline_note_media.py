from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesRepository,
)
from personal_learning_assistant.services.anvaya_notes_service import (
    AnvayaNotesService,
    AnvayaNotesValidationError,
)


NOW = "2026-09-26T10:30:00Z"
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 64
JPG = b"\xff\xd8\xff\xe0" + b"j" * 64
PDF = b"%PDF-1.4\nANVAYA\n%%EOF"


def _service(tmp_path):
    repository = AnvayaNotesRepository(
        notes_path=tmp_path / "anvaya_notes.json",
        assets_root=tmp_path / "anvaya_notes_assets",
    )
    return AnvayaNotesService(repository, now=lambda: NOW), repository


def _zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_typed_note_accepts_multiple_images_and_resolves_inline_upload_positions(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {
            "title": "LU Factorization",
            "body": (
                "Before image\n\n"
                "[[anvaya-upload:0|width=55|rotate=90|crop=4:3|caption=Elimination]]\n\n"
                "Middle text\n\n"
                "[[anvaya-upload:1|width=85|rotate=0|crop=original|caption=Verification]]\n\n"
                "After image"
            ),
        },
        [("elim.png", PNG), ("verify.jpg", JPG)],
    )

    row = repository.get_note(created["id"])
    assert len(row["assets"]) == 2
    assert "[[anvaya-upload:" not in row["body"]
    assert row["body"].count("[[anvaya-image:") == 2
    assert "|width=55|rotate=90|crop=4:3|caption=Elimination]]" in row["body"]
    assert "|width=85|rotate=0|crop=original|caption=Verification]]" in row["body"]


def test_reader_renders_inline_images_between_text_and_does_not_duplicate_them_at_bottom(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {
            "title": "Rank",
            "body": (
                "Paragraph before.\n\n"
                "[[anvaya-upload:0|width=70|rotate=270|crop=1:1|caption=Rank diagram]]\n\n"
                "Paragraph after."
            ),
        },
        [("rank.png", PNG), ("appendix.pdf", PDF)],
    )
    row = repository.get_note(created["id"])
    image_id = next(x["id"] for x in row["assets"] if x["mimetype"] == "image/png")

    view = service.reader(created["id"])
    html = str(view["rendered_html"])

    assert html.index("Paragraph before") < html.index("anvaya-inline-media") < html.index("Paragraph after")
    assert f"/notes/file/{created['id']}/{image_id}" in html
    assert "anvaya-media-width-70" in html
    assert "anvaya-media-rotate-270" in html
    assert "anvaya-media-crop-1x1" in html
    assert "Rank diagram" in html

    assert len(view["assets"]) == 1
    assert view["assets"][0]["mimetype"] == "application/pdf"


def test_inline_image_presentation_never_changes_original_bytes(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {
            "title": "AAS",
            "body": "[[anvaya-upload:0|width=25|rotate=180|crop=16:9|caption=Lamp]]",
        },
        [("lamp.png", PNG)],
    )
    row = repository.get_note(created["id"])
    asset = row["assets"][0]

    service.reader(created["id"])

    assert repository.read_asset(created["id"], asset["id"])["bytes"] == PNG


def test_safe_zip_import_expands_multiple_images_and_pdf(tmp_path):
    service, repository = _service(tmp_path)
    archive = _zip(
        [
            ("page-1.png", PNG),
            ("folder/page-2.jpg", JPG),
            ("appendix.pdf", PDF),
        ]
    )

    created = service.create_handwritten_note(
        {"title": "Handwritten Linear Algebra"},
        [("week4.zip", archive)],
    )
    row = repository.get_note(created["id"])

    assert [x["filename"] for x in row["assets"]] == [
        "page-1.png",
        "page-2.jpg",
        "appendix.pdf",
    ]


def test_zip_placeholder_expands_all_safe_images_at_the_selected_text_position(tmp_path):
    service, repository = _service(tmp_path)
    archive = _zip(
        [
            ("one.png", PNG),
            ("two.jpg", JPG),
            ("reference.pdf", PDF),
        ]
    )

    created = service.create_typed_note(
        {
            "title": "Data Cleaning",
            "body": (
                "Before batch\n\n"
                "[[anvaya-upload:0|width=40|rotate=0|crop=3:4|caption=Lab image]]\n\n"
                "After batch"
            ),
        },
        [("lab-images.zip", archive)],
    )
    row = repository.get_note(created["id"])

    assert row["body"].count("[[anvaya-image:") == 2
    assert row["body"].index("Before batch") < row["body"].index("[[anvaya-image:")
    assert row["body"].rindex("[[anvaya-image:") < row["body"].index("After batch")
    assert "reference.pdf" in [x["filename"] for x in row["assets"]]


@pytest.mark.parametrize(
    "entry_name",
    (
        "../escape.png",
        "/absolute.png",
        "nested/../../escape.jpg",
        "payload.zip",
    ),
)
def test_zip_import_rejects_unsafe_paths_and_nested_archives(tmp_path, entry_name):
    service, _repository = _service(tmp_path)
    payload = _zip([(entry_name, PNG)])

    with pytest.raises(AnvayaNotesValidationError):
        service.create_handwritten_note(
            {"title": "Unsafe archive"},
            [("unsafe.zip", payload)],
        )


def test_invalid_inline_settings_are_normalized_and_unknown_asset_is_not_rendered(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {
            "title": "Safe image settings",
            "body": (
                "[[anvaya-upload:0|width=999|rotate=45|crop=evil|caption=Safe]]\n\n"
                "[[anvaya-image:not-owned|width=70|rotate=0|crop=original|caption=Bad]]"
            ),
        },
        [("safe.png", PNG)],
    )

    row = repository.get_note(created["id"])
    assert "|width=100|rotate=0|crop=original|caption=Safe]]" in row["body"]

    html = str(service.reader(created["id"])["rendered_html"])
    assert "anvaya-media-width-100" in html
    assert "not-owned" not in html
    assert "Image unavailable" in html


def test_edit_view_exposes_existing_image_assets_for_reinsertion(tmp_path):
    service, _repository = _service(tmp_path)
    created = service.create_typed_note(
        {"title": "Editable", "body": "Body"},
        [("diagram.png", PNG)],
    )

    editor = service.edit_view(created["id"])

    assert len(editor["assets"]) == 1
    assert editor["assets"][0]["mimetype"] == "image/png"
    assert editor["assets"][0]["url"].startswith(
        f"/notes/file/{created['id']}/"
    )


def test_editor_exposes_inline_media_controls_and_zip_upload():
    root = Path(__file__).resolve().parents[1]
    editor = (
        root / "personal_learning_assistant/ui/web/templates/anvaya_notes_editor.html"
    ).read_text(encoding="utf-8")
    upload = (
        root / "personal_learning_assistant/ui/web/templates/anvaya_notes_upload.html"
    ).read_text(encoding="utf-8")
    css = (
        root / "personal_learning_assistant/ui/web/static/css/app.css"
    ).read_text(encoding="utf-8")

    for token in (
        "Insert at cursor",
        "data-media-width",
        "data-media-rotate",
        "data-media-crop",
        'mediaDirective("upload"',
        "anvaya-${kind}",
        ".zip",
    ):
        assert token in editor

    assert ".zip" in upload

    for token in (
        ".anvaya-inline-media",
        ".anvaya-media-crop-1x1",
        ".anvaya-media-rotate-90",
        ".anvaya-media-width-70",
    ):
        assert token in css


def test_inline_media_service_does_not_depend_on_obsidian_or_tutor_authority():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "personal_learning_assistant/services/anvaya_notes_service.py"
    ).read_text(encoding="utf-8").casefold()

    assert "obsidian_workspace_reader" not in source
    assert "personal_learning_assistant.tutor" not in source
