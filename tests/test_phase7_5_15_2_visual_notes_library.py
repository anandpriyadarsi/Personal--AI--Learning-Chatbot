from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from personal_learning_assistant.domain.notes_studio_read_models import NoteCard
from personal_learning_assistant.services.notes_studio_library_service import (
    NotesStudioLibraryWebService,
)


def _card(
    title,
    *,
    path,
    topic="",
    course="",
    note_type="note",
    note_date="",
    summary=(),
    tags=(),
    revision_status="unreviewed",
):
    return NoteCard(
        identity="vault-note:{}@{}".format(path, "a" * 64),
        relative_path=path,
        source_hash="a" * 64,
        title=title,
        topic=topic,
        course=course,
        note_type=note_type,
        note_date=note_date,
        card_summary=tuple(summary),
        tags=tuple(tags),
        revision_status=revision_status,
    )


class FakeReadService:
    def __init__(self, cards):
        self.cards = tuple(cards)
        self.calls = 0

    def list_cards(self):
        self.calls += 1
        return self.cards


class FakeLegacyService:
    def __init__(self):
        self.calls = 0

    def notes_workspace(self):
        self.calls += 1
        return {
            "notes": [
                {
                    "position": 1,
                    "title": "Old LU note",
                    "topic": "Linear Algebra",
                    "difficulty": "Hard",
                    "content": "THIS LEGACY BODY MUST NOT RENDER",
                }
            ],
            "summary": {"total": 1, "topics": 1, "difficulties": 1},
        }


def _service():
    cards = (
        _card(
            "LU Factorization",
            path="Math/LU.md",
            topic="Matrix factorization",
            course="MA103N",
            note_type="concept",
            note_date="2026-09-24",
            summary=("A = LU", "L stores elimination multipliers"),
            tags=("linear-algebra", "exam"),
            revision_status="learning",
        ),
        _card(
            "Data Cleaning",
            path="DS/Data Cleaning.md",
            topic="Missing values",
            course="UC100N",
            note_type="lecture",
            note_date="2026-09-22",
            summary=("Inspect missingness first",),
            tags=("data-science",),
        ),
        _card(
            "Rank",
            path="Math/Rank.md",
            topic="Matrix rank",
            course="MA103N",
            note_type="revision",
            summary=(),
            tags=("linear-algebra",),
        ),
    )
    legacy = FakeLegacyService()
    return NotesStudioLibraryWebService(FakeReadService(cards), legacy), legacy


def test_library_workspace_builds_compact_cards_without_body_field():
    service, legacy = _service()

    workspace = service.workspace()

    assert workspace["available"] is True
    assert workspace["summary"] == {
        "total": 3,
        "displayed": 3,
        "courses": 2,
        "types": 3,
        "legacy": 1,
        "pinned": 0,
        "archived": 0,
    }
    assert workspace["cards"][0]["title"] == "LU Factorization"
    assert workspace["cards"][0]["card_summary"] == [
        "A = LU",
        "L stores elimination multipliers",
    ]
    assert all("body" not in card and "text" not in card and "content" not in card for card in workspace["cards"])
    assert workspace["legacy_notes"] == [
        {
            "position": 1,
            "title": "Old LU note",
            "topic": "Linear Algebra",
            "difficulty": "Hard",
        }
    ]
    assert legacy.calls == 1


def test_library_filters_are_case_insensitive_and_metadata_only():
    service, _legacy = _service()

    workspace = service.workspace(search="ELIMINATION", course="ma103n", note_type="CONCEPT", tag="EXAM")

    assert [card["title"] for card in workspace["cards"]] == ["LU Factorization"]
    assert workspace["query"] == {
        "search": "ELIMINATION",
        "course": "ma103n",
        "note_type": "CONCEPT",
        "tag": "EXAM",
        "view": "active",
        "pinned": "",
    }


def test_library_filter_options_are_deterministic_and_empty_summary_is_preserved():
    service, _legacy = _service()

    workspace = service.workspace()

    assert workspace["filter_options"] == {
        "courses": ["MA103N", "UC100N"],
        "note_types": ["concept", "lecture", "revision"],
        "tags": ["data-science", "exam", "linear-algebra"],
    }
    rank = next(card for card in workspace["cards"] if card["title"] == "Rank")
    assert rank["card_summary"] == []


def test_library_search_does_not_open_note_details_or_generate_summary():
    class ReadOnlyCards:
        def list_cards(self):
            return (
                _card(
                    "Vector Spaces",
                    path="Math/Vector Spaces.md",
                    topic="Subspaces",
                    summary=(),
                ),
            )

        def get_detail(self, *_args, **_kwargs):
            raise AssertionError("library listing must not read full note details")

    workspace = NotesStudioLibraryWebService(ReadOnlyCards()).workspace(search="vector")
    assert workspace["cards"][0]["card_summary"] == []


def test_library_legacy_failure_does_not_hide_rich_cards():
    class BrokenLegacy:
        def notes_workspace(self):
            raise RuntimeError("SECRET-LEGACY-PATH")

    rich = FakeReadService((_card("Rank", path="Rank.md"),))
    workspace = NotesStudioLibraryWebService(rich, BrokenLegacy()).workspace()

    assert workspace["available"] is True
    assert [card["title"] for card in workspace["cards"]] == ["Rank"]
    assert workspace["summary"]["legacy"] == 0


class FakeLibraryWebService:
    def __init__(self, workspace=None):
        self.calls = []
        self.workspace_value = workspace or {
            "available": True,
            "message": "",
            "cards": [
                {
                    "identity": "assistant:1",
                    "relative_path": "Math/LU.md",
                    "source_hash": "b" * 64,
                    "title": "LU Factorization",
                    "topic": "Matrix factorization",
                    "course": "MA103N",
                    "note_type": "concept",
                    "note_date": "2026-09-24",
                    "note_date_label": "24 Sep 2026",
                    "card_summary": ["A = LU", "L stores elimination multipliers"],
                    "tags": ["linear-algebra", "exam"],
                    "revision_status": "learning",
                },
                {
                    "identity": "vault-note:Math/Rank.md@" + "c" * 64,
                    "relative_path": "Math/Rank.md",
                    "source_hash": "c" * 64,
                    "title": "Rank",
                    "topic": "",
                    "course": "MA103N",
                    "note_type": "revision",
                    "note_date": "",
                    "note_date_label": "",
                    "card_summary": [],
                    "tags": [],
                    "revision_status": "unreviewed",
                },
            ],
            "legacy_notes": [
                {
                    "position": 1,
                    "title": "Old JSON note",
                    "topic": "Legacy",
                    "difficulty": "Medium",
                }
            ],
            "summary": {
                "total": 2,
                "displayed": 2,
                "courses": 1,
                "types": 2,
                "legacy": 1,
                "pinned": 0,
                "archived": 0,
            },
            "query": {
                "search": "",
                "course": "",
                "note_type": "",
                "tag": "",
                "view": "active",
                "pinned": "",
            },
            "filter_options": {
                "courses": ["MA103N"],
                "note_types": ["concept", "revision"],
                "tags": ["exam", "linear-algebra"],
            },
        }

    def workspace(self, **kwargs):
        self.calls.append(kwargs)
        value = dict(self.workspace_value)
        value["query"] = {
            "search": kwargs.get("search", ""),
            "course": kwargs.get("course", ""),
            "note_type": kwargs.get("note_type", ""),
            "tag": kwargs.get("tag", ""),
            "view": kwargs.get("view", "active"),
            "pinned": kwargs.get("pinned", ""),
        }
        return value


def _app_with_library(service):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "NOTES_STUDIO_LIBRARY_SERVICE_FACTORY": lambda: service,
        }
    )


def test_notes_route_renders_visual_cards_and_never_full_body():
    service = FakeLibraryWebService()
    response = _app_with_library(service).test_client().get(
        "/notes?q=LU&course=MA103N&type=concept&tag=exam"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert service.calls == [
        {
            "search": "LU",
            "course": "MA103N",
            "note_type": "concept",
            "tag": "exam",
            "view": "active",
            "pinned": "",
        }
    ]
    for expected in (
        "Notes Studio",
        "LU Factorization",
        "Matrix factorization",
        "MA103N",
        "Concept",
        "24 Sep 2026",
        "A = LU",
        "L stores elimination multipliers",
        "linear-algebra",
        "Open note",
        "Old JSON note",
        "Legacy notes preserved",
    ):
        assert expected in text
    assert "THIS LEGACY BODY MUST NOT RENDER" not in text
    assert "note-content" not in text


def test_visual_library_card_links_to_full_notes_studio_reader():
    response = _app_with_library(FakeLibraryWebService()).test_client().get("/notes")
    text = response.get_data(as_text=True)

    assert "/notes/note?path=Math/LU.md" in text or "/notes/note?path=Math%2FLU.md" in text
    assert "Edit note" not in text
    assert "New note" in text
    assert "/notes/new" in text


def test_visual_library_empty_and_unavailable_states_are_safe():
    empty = FakeLibraryWebService(
        {
            "available": True,
            "message": "",
            "cards": [],
            "legacy_notes": [],
            "summary": {
                "total": 0,
                "displayed": 0,
                "courses": 0,
                "types": 0,
                "legacy": 0,
                "pinned": 0,
                "archived": 0,
            },
            "query": {
                "search": "",
                "course": "",
                "note_type": "",
                "tag": "",
                "view": "active",
                "pinned": "",
            },
            "filter_options": {"courses": [], "note_types": [], "tags": []},
        }
    )
    text = _app_with_library(empty).test_client().get("/notes").get_data(as_text=True)
    assert "No matching notes" in text

    class Broken:
        def workspace(self, **_kwargs):
            raise RuntimeError("C:/SECRET/vault")

    response = _app_with_library(Broken()).test_client().get("/notes")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Notes Studio is temporarily unavailable" in text
    assert "SECRET" not in text


def test_notes_library_template_is_compact_accessible_and_responsive():
    root = Path(__file__).resolve().parents[1]
    template = (root / "personal_learning_assistant/ui/web/templates/notes_library.html").read_text(encoding="utf-8")
    css = (root / "personal_learning_assistant/ui/web/static/css/app.css").read_text(encoding="utf-8")

    for token in (
        "notes-studio-grid",
        "notes-studio-card",
        "note-key-points",
        "aria-labelledby",
        "card_summary",
    ):
        assert token in template
    assert "note.content" not in template
    assert "note.text" not in template
    assert "@media (max-width: 900px)" in css
    assert ".notes-studio-grid" in css


def test_phase15_2_routes_do_not_import_tutor_or_note_write_service():
    root = Path(__file__).resolve().parents[1]
    route_source = (root / "personal_learning_assistant/ui/web/routes.py").read_text(encoding="utf-8")
    library_source = (root / "personal_learning_assistant/services/notes_studio_library_service.py").read_text(encoding="utf-8")
    combined = route_source + "\n" + library_source

    assert "personal_learning_assistant.tutor" not in library_source
    assert "NotesStudioService" not in library_source
    assert ".create_note(" not in library_source
    assert ".update_note(" not in library_source
    assert "NOTES_STUDIO_LIBRARY_SERVICE_FACTORY" in route_source
