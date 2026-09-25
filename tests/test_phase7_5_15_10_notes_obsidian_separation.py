from __future__ import annotations

import json
from pathlib import Path

import pytest
from markupsafe import Markup

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesConflictError,
    AnvayaNotesRepository,
)
from personal_learning_assistant.services.anvaya_notes_service import (
    AnvayaNotesService,
    AnvayaNotesValidationError,
)


NOW = "2026-09-25T09:58:00Z"


def _service(tmp_path):
    repository = AnvayaNotesRepository(
        notes_path=tmp_path / "anvaya_notes.json",
        assets_root=tmp_path / "anvaya_notes_assets",
    )
    return AnvayaNotesService(repository, now=lambda: NOW), repository


def test_native_notes_are_independent_from_obsidian_vault(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "Obsidian Only.md").write_text("# Obsidian Only\n", encoding="utf-8")
    service, repository = _service(tmp_path)

    created = service.create_typed_note(
        {
            "title": "LU Factorization",
            "course": "MA103N",
            "key_points": "Elimination multipliers\nConstruct L and U",
            "card_style": "iris",
            "body": "# LU Factorization\n\nA = LU",
        }
    )

    workspace = service.library()
    assert [card["title"] for card in workspace["cards"]] == ["LU Factorization"]
    assert "Obsidian Only" not in json.dumps(workspace)
    assert created["id"] in repository.get_note(created["id"])["id"]
    assert list(vault.iterdir()) == [vault / "Obsidian Only.md"]


def test_typed_note_uses_automatic_timestamps_and_iris_card_by_default(tmp_path):
    service, repository = _service(tmp_path)

    created = service.create_typed_note(
        {
            "title": "Vector Spaces",
            "key_points": "Closure\nZero vector\nScalar multiplication",
            "body": "# Vector Spaces",
        }
    )
    row = repository.get_note(created["id"])

    assert row["created_at"] == NOW
    assert row["updated_at"] == NOW
    assert row["card_style"] == "iris"
    assert row["note_kind"] == "typed"
    assert row["key_points"] == ["Closure", "Zero vector", "Scalar multiplication"]


def test_key_points_are_trimmed_and_capped_at_five(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note(
        {
            "title": "Rank",
            "key_points": " one \n\n two\nthree\nfour\nfive\nsix ",
            "body": "Rank",
        }
    )
    assert repository.get_note(created["id"])["key_points"] == [
        "one", "two", "three", "four", "five"
    ]


def test_handwritten_note_accepts_pdf_and_images_and_preserves_original_bytes(tmp_path):
    service, repository = _service(tmp_path)
    pdf = b"%PDF-1.4\nANVAYA\n%%EOF"
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 32

    created = service.create_handwritten_note(
        {
            "title": "Chemistry AAS",
            "course": "CY100N",
            "key_points": "Principle\nInstrumentation",
            "card_style": "preview",
        },
        [
            ("aas.pdf", pdf),
            ("diagram.png", png),
        ],
    )

    note = repository.get_note(created["id"])
    assert note["note_kind"] == "handwritten"
    assert len(note["assets"]) == 2
    assert note["assets"][0]["filename"] == "aas.pdf"
    assert repository.read_asset(note["id"], note["assets"][0]["id"])["bytes"] == pdf
    assert repository.read_asset(note["id"], note["assets"][1]["id"])["bytes"] == png


@pytest.mark.parametrize(
    ("filename", "payload"),
    (
        ("notes.exe", b"MZdanger"),
        ("fake.pdf", b"not a pdf"),
        ("fake.png", b"not png"),
    ),
)
def test_handwritten_note_rejects_unsafe_or_fake_uploads(tmp_path, filename, payload):
    service, _repository = _service(tmp_path)
    with pytest.raises(AnvayaNotesValidationError):
        service.create_handwritten_note(
            {"title": "Unsafe"},
            [(filename, payload)],
        )


def test_reader_returns_typed_body_or_handwritten_assets_without_obsidian_path(tmp_path):
    service, _repository = _service(tmp_path)
    typed = service.create_typed_note(
        {"title": "LU", "body": "# LU\n\n> [!IMPORTANT] Pivot carefully"}
    )
    handwritten = service.create_handwritten_note(
        {"title": "AAS"},
        [("aas.pdf", b"%PDF-1.4\n%%EOF")],
    )

    typed_view = service.reader(typed["id"])
    handwritten_view = service.reader(handwritten["id"])

    assert typed_view["note_kind"] == "typed"
    assert "rendered_html" in typed_view
    assert "Pivot carefully" in str(typed_view["rendered_html"])
    assert "relative_path" not in typed_view
    assert handwritten_view["note_kind"] == "handwritten"
    assert handwritten_view["assets"][0]["url"].startswith(
        "/notes/file/{}/".format(handwritten["id"])
    )


def test_update_uses_optimistic_updated_at_and_keeps_created_at(tmp_path):
    service, repository = _service(tmp_path)
    created = service.create_typed_note({"title": "Old", "body": "old"})
    before = repository.get_note(created["id"])

    updated = service.update_note(
        created["id"],
        {
            "expected_updated_at": before["updated_at"],
            "title": "New",
            "course": "MA103N",
            "key_points": "A\nB",
            "card_style": "square",
            "body": "new",
        },
    )
    after = repository.get_note(created["id"])

    assert updated["id"] == created["id"]
    assert after["created_at"] == before["created_at"]
    assert after["title"] == "New"
    assert after["card_style"] == "square"

    with pytest.raises(AnvayaNotesConflictError):
        repository.update_note(
            created["id"],
            expected_updated_at="stale",
            changes={"title": "bad", "updated_at": NOW},
        )


class FakeNativeNotesService:
    def __init__(self):
        self.calls = []

    def library(self, **query):
        self.calls.append(("library", query))
        return {
            "available": True,
            "cards": [
                {
                    "id": "n1",
                    "title": "LU Factorization",
                    "course": "MA103N",
                    "note_kind": "typed",
                    "card_style": "iris",
                    "key_points": ["Multipliers", "Build L and U", "Verify LU=A"],
                    "created_label": "25 Sep 2026 · 3:28 PM",
                    "thumbnail_url": "",
                }
            ],
            "summary": {"total": 1, "typed": 1, "handwritten": 0},
            "query": query,
            "filter_options": {"courses": ["MA103N"], "kinds": ["typed"]},
        }

    def reader(self, note_id):
        self.calls.append(("reader", note_id))
        return {
            "id": note_id,
            "title": "LU Factorization",
            "course": "MA103N",
            "note_kind": "typed",
            "card_style": "iris",
            "key_points": ["Multipliers", "Build L and U"],
            "created_label": "25 Sep 2026 · 3:28 PM",
            "updated_label": "25 Sep 2026 · 3:28 PM",
            "updated_at": NOW,
            "rendered_html": Markup("<h1>LU</h1><p>Body</p>"),
            "assets": [],
        }

    def create_typed_note(self, payload, uploads=()):
        self.calls.append(("typed", dict(payload), tuple(uploads)))
        return {"id": "typed-1"}

    def create_handwritten_note(self, payload, uploads):
        self.calls.append(("handwritten", dict(payload), tuple(uploads)))
        return {"id": "hand-1"}

    def edit_view(self, note_id):
        self.calls.append(("edit", note_id))
        return {
            "id": note_id,
            "title": "LU Factorization",
            "course": "MA103N",
            "note_kind": "typed",
            "card_style": "iris",
            "key_points_text": "Multipliers\nBuild L and U",
            "body": "# LU",
            "updated_at": NOW,
            "assets": [],
        }

    def update_note(self, note_id, payload, uploads=()):
        self.calls.append(("update", note_id, dict(payload), tuple(uploads)))
        return {"id": note_id}

    def read_asset(self, note_id, asset_id):
        self.calls.append(("asset", note_id, asset_id))
        return {
            "bytes": b"asset",
            "mimetype": "image/png",
            "filename": "page.png",
        }


def _app(service):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "ANVAYA_NOTES_SERVICE_FACTORY": lambda: service,
        }
    )


def test_default_notes_route_uses_native_cards_and_not_obsidian_library():
    service = FakeNativeNotesService()
    response = _app(service).test_client().get("/notes?q=LU&course=MA103N&kind=typed")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert service.calls == [
        (
            "library",
            {"search": "LU", "course": "MA103N", "kind": "typed"},
        )
    ]
    for expected in (
        "My Notes",
        "LU Factorization",
        "Multipliers",
        "25 Sep 2026",
        "3:28 PM",
        "MA103N",
        "Create note",
    ):
        assert expected in html
    assert "Open Obsidian workspace" not in html
    assert "/notes/view/n1" in html


def test_notes_cards_are_entire_click_targets_and_offer_three_visual_styles():
    root = Path(__file__).resolve().parents[1]
    library = (
        root / "personal_learning_assistant/ui/web/templates/anvaya_notes_library.html"
    ).read_text(encoding="utf-8")
    create = (
        root / "personal_learning_assistant/ui/web/templates/anvaya_notes_create.html"
    ).read_text(encoding="utf-8")
    css = (
        root / "personal_learning_assistant/ui/web/static/css/app.css"
    ).read_text(encoding="utf-8")

    assert 'class="anvaya-note-card-link"' in library
    assert "url_for('web.anvaya_note_reader'" in library
    for token in ("IRIS Academic", "Preview Card", "Minimal Square"):
        assert token in create
    assert "date" not in create.casefold() or 'name="note_date"' not in create
    assert ".anvaya-notes-grid" in css
    assert ".anvaya-note-card--iris" in css


def test_create_flow_separates_handwritten_upload_and_typed_note():
    client = _app(FakeNativeNotesService()).test_client()
    page = client.get("/notes/create").get_data(as_text=True)

    assert "Upload handwritten note" in page
    assert "Create typed note" in page
    assert "/notes/create/upload" in page
    assert "/notes/create/typed" in page


def test_typed_create_route_does_not_accept_user_date_field():
    service = FakeNativeNotesService()
    client = _app(service).test_client()
    response = client.post(
        "/notes/create/typed",
        data={
            "title": "LU",
            "key_points": "A\nB",
            "card_style": "iris",
            "body": "# LU",
            "note_date": "1999-01-01",
        },
    )

    assert response.status_code == 303
    payload = service.calls[-1][1]
    assert "note_date" not in payload
    assert response.headers["Location"].endswith("/notes/view/typed-1")


def test_handwritten_upload_route_accepts_multiple_pages():
    service = FakeNativeNotesService()
    client = _app(service).test_client()
    response = client.post(
        "/notes/create/upload",
        data={
            "title": "AAS",
            "key_points": "Principle",
            "card_style": "preview",
            "files": [
                (pytest.importorskip("io").BytesIO(b"%PDF-1.4\n%%EOF"), "aas.pdf"),
                (pytest.importorskip("io").BytesIO(b"\x89PNG\r\n\x1a\n123"), "p2.png"),
            ],
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 303
    assert service.calls[-1][0] == "handwritten"
    assert len(service.calls[-1][2]) == 2


def test_native_reader_route_does_not_use_obsidian_path_parameter():
    service = FakeNativeNotesService()
    response = _app(service).test_client().get("/notes/view/n1")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert service.calls == [("reader", "n1")]
    assert "Full note" in html
    assert "LU Factorization" in html
    assert "Obsidian" not in html


def test_native_asset_route_is_id_scoped():
    service = FakeNativeNotesService()
    response = _app(service).test_client().get("/notes/file/n1/a1")

    assert response.status_code == 200
    assert response.data == b"asset"
    assert response.mimetype == "image/png"
    assert service.calls == [("asset", "n1", "a1")]


def test_native_notes_source_has_no_obsidian_scanner_or_tutor_dependency():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "personal_learning_assistant/services/anvaya_notes_service.py"
    ).read_text(encoding="utf-8").casefold()
    repository = (
        root / "personal_learning_assistant/repositories/json/anvaya_notes_repository.py"
    ).read_text(encoding="utf-8").casefold()

    for forbidden in (
        "obsidian_workspace_reader",
        "build_configured_notes_studio_read_service",
        "personal_learning_assistant.tutor",
    ):
        assert forbidden not in source
        assert forbidden not in repository
