from __future__ import annotations

import hashlib
from pathlib import Path

from markupsafe import Markup

from personal_learning_assistant.domain.notes_studio_read_models import (
    NoteCard,
    NoteDetail,
)
from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import (
    ObsidianWorkspaceReader,
)
from personal_learning_assistant.services.notes_studio_connections_service import (
    MAX_RELATED_NOTES,
    build_connection_context,
)
from personal_learning_assistant.services.notes_studio_library_service import (
    NotesStudioLibraryWebService,
)
from personal_learning_assistant.services.notes_studio_read_service import (
    NotesStudioReadService,
)
from personal_learning_assistant.services.notes_studio_reader_service import (
    NotesStudioReaderWebService,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


def _hash_tree(root: Path):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _card(
    title,
    path,
    *,
    course="",
    topic="",
    source="",
    tags=(),
    note_type="concept",
):
    return NoteCard(
        identity="vault-note:{}@{}".format(path, "a" * 64),
        relative_path=path,
        source_hash="a" * 64,
        title=title,
        topic=topic,
        course=course,
        note_type=note_type,
        note_date="",
        card_summary=(),
        tags=tuple(tags),
        revision_status="unreviewed",
        source=source,
    )


def test_note_card_reads_source_metadata_with_deterministic_precedence(tmp_path):
    vault = _vault(tmp_path)
    _write(
        vault / "A.md",
        """---
title: A
course: MA103N
topic: Matrix Factorization
source: MIT 18.06 Lecture 2
source_title: Ignored fallback
---
# A
""",
    )
    _write(
        vault / "B.md",
        """---
title: B
source_title: Engineering Mathematics Chapter 3
---
# B
""",
    )

    cards = {
        item.title: item
        for item in NotesStudioReadService(
            lambda: ObsidianWorkspaceReader(vault)
        ).list_cards()
    }

    assert cards["A"].source == "MIT 18.06 Lecture 2"
    assert cards["B"].source == "Engineering Mathematics Chapter 3"


def test_related_notes_are_ranked_by_explicit_links_and_shared_metadata():
    current = _card(
        "LU Factorization",
        "Math/LU.md",
        course="MA103N",
        topic="Matrix Factorization",
        source="MIT 18.06 Lecture 2",
        tags=("linear-algebra", "elimination"),
    )
    rank = _card(
        "Rank",
        "Math/Rank.md",
        course="MA103N",
        topic="Matrix Factorization",
        source="MIT 18.06 Lecture 2",
        tags=("linear-algebra",),
    )
    elimination = _card(
        "Gaussian Elimination",
        "Math/Elimination.md",
        course="MA103N",
        topic="Linear Systems",
        source="MIT 18.06 Lecture 2",
        tags=("linear-algebra", "elimination"),
    )
    unrelated = _card(
        "Data Cleaning",
        "DS/Cleaning.md",
        course="UC100N",
        topic="Missing Values",
        source="DSAI Week 3",
        tags=("data-science",),
    )

    context = build_connection_context(
        current,
        (current, rank, elimination, unrelated),
        wikilinks=(
            {
                "resolved_path": "Math/Rank.md",
                "resolved_title": "Rank",
                "label": "Rank",
            },
        ),
        backlinks=(
            {
                "relative_path": "Math/Elimination.md",
                "title": "Gaussian Elimination",
            },
        ),
    )

    assert [item["title"] for item in context["related_notes"]] == [
        "Rank",
        "Gaussian Elimination",
    ]
    rank_reasons = context["related_notes"][0]["reasons"]
    assert rank_reasons[:4] == (
        "Linked from this note",
        "Same course",
        "Same topic",
        "Same source",
    )
    assert "Shared tag: linear-algebra" in rank_reasons

    elimination_reasons = context["related_notes"][1]["reasons"]
    assert "Links to this note" in elimination_reasons
    assert "Same course" in elimination_reasons
    assert "Same source" in elimination_reasons
    assert "Data Cleaning" not in {
        item["title"] for item in context["related_notes"]
    }


def test_connection_facets_count_course_topic_and_source_peers():
    current = _card(
        "LU",
        "LU.md",
        course="MA103N",
        topic="Matrices",
        source="Lecture 4",
    )
    cards = (
        current,
        _card("Rank", "Rank.md", course="MA103N", topic="Matrices", source="Lecture 4"),
        _card("Inverse", "Inverse.md", course="MA103N", topic="Matrices", source="Book A"),
        _card("Python", "Python.md", course="UC100N", topic="Loops", source="Lecture 4"),
    )

    context = build_connection_context(
        current,
        cards,
        wikilinks=(),
        backlinks=(),
    )

    facets = {item["kind"]: item for item in context["facets"]}
    assert facets["course"] == {
        "kind": "course",
        "label": "MA103N",
        "peer_count": 2,
    }
    assert facets["topic"] == {
        "kind": "topic",
        "label": "Matrices",
        "peer_count": 2,
    }
    assert facets["source"] == {
        "kind": "source",
        "label": "Lecture 4",
        "peer_count": 2,
    }


def test_related_notes_are_bounded_deterministic_and_exclude_self():
    current = _card("Current", "Current.md", course="MA103N")
    peers = tuple(
        _card("Peer {:02}".format(index), "Peer{:02}.md".format(index), course="MA103N")
        for index in range(MAX_RELATED_NOTES + 4)
    )

    context = build_connection_context(
        current,
        (current,) + peers,
        wikilinks=(),
        backlinks=(),
    )

    assert len(context["related_notes"]) == MAX_RELATED_NOTES
    assert [item["title"] for item in context["related_notes"]] == [
        "Peer {:02}".format(index) for index in range(MAX_RELATED_NOTES)
    ]
    assert all(item["relative_path"] != "Current.md" for item in context["related_notes"])


def test_canonical_detail_composes_related_notes_without_mutating_vault(tmp_path):
    vault = _vault(tmp_path)
    _write(
        vault / "Math" / "LU.md",
        """---
course: MA103N
topic: Matrix Factorization
source: MIT 18.06
tags: [linear-algebra]
---
# LU Factorization
See [[Rank]].
""",
    )
    _write(
        vault / "Math" / "Rank.md",
        """---
course: MA103N
topic: Matrix Factorization
source: MIT 18.06
tags: [linear-algebra]
---
# Rank
""",
    )
    before = _hash_tree(vault)

    detail = NotesStudioReadService(
        lambda: ObsidianWorkspaceReader(vault)
    ).get_detail("Math/LU.md")

    assert detail.card.source == "MIT 18.06"
    assert detail.related_notes[0]["relative_path"] == "Math/Rank.md"
    assert detail.connection_facets == (
        {"kind": "course", "label": "MA103N", "peer_count": 1},
        {"kind": "topic", "label": "Matrix Factorization", "peer_count": 1},
        {"kind": "source", "label": "MIT 18.06", "peer_count": 1},
    )
    assert _hash_tree(vault) == before


def test_library_search_includes_source_metadata_without_opening_details():
    cards = (
        _card(
            "LU",
            "LU.md",
            course="MA103N",
            source="MIT 18.06 Lecture 2",
        ),
        _card(
            "Rank",
            "Rank.md",
            course="MA103N",
            source="Engineering Mathematics",
        ),
    )

    class ReadOnlyCards:
        def list_cards(self):
            return cards

        def get_detail(self, *_args, **_kwargs):
            raise AssertionError("library source search must stay card-only")

    workspace = NotesStudioLibraryWebService(
        ReadOnlyCards()
    ).workspace(search="18.06")

    assert [item["title"] for item in workspace["cards"]] == ["LU"]


def test_reader_view_exposes_related_notes_source_and_facets():
    detail = NoteDetail(
        card=_card(
            "LU",
            "Math/LU.md",
            course="MA103N",
            topic="Matrix Factorization",
            source="MIT 18.06",
        ),
        text="# LU\n",
        wikilinks=(),
        backlinks=(),
        related_notes=(
            {
                "relative_path": "Math/Rank.md",
                "title": "Rank",
                "course": "MA103N",
                "topic": "Matrix Factorization",
                "source": "MIT 18.06",
                "note_type": "concept",
                "reasons": (
                    "Same course",
                    "Same topic",
                    "Same source",
                ),
            },
        ),
        connection_facets=(
            {"kind": "course", "label": "MA103N", "peer_count": 2},
            {
                "kind": "topic",
                "label": "Matrix Factorization",
                "peer_count": 1,
            },
            {"kind": "source", "label": "MIT 18.06", "peer_count": 3},
        ),
    )

    class ReadService:
        def get_detail(self, path):
            assert path == "Math/LU.md"
            return detail

    view = NotesStudioReaderWebService(
        ReadService(),
        renderer=lambda *_args, **_kwargs: Markup("<p>LU</p>"),
    ).reader_view("Math/LU.md")

    assert view["source"] == "MIT 18.06"
    assert view["related_notes"][0]["title"] == "Rank"
    assert view["connection_facets"][2]["peer_count"] == 3


class FakeReaderWebService:
    def reader_view(self, _path):
        return {
            "title": "LU Factorization",
            "editable": False,
            "note_id": "",
            "topic": "Matrix Factorization",
            "course": "MA103N",
            "source": "MIT 18.06 Lecture 2",
            "note_type": "concept",
            "note_date": "",
            "note_date_label": "",
            "card_summary": [],
            "tags": ["linear-algebra"],
            "revision_status": "learning",
            "relative_path": "Math/LU.md",
            "source_hash": "a" * 64,
            "source_hash_short": "aaaaaaaaaaaa",
            "rendered_html": Markup("<p>LU body</p>"),
            "wikilinks": [],
            "backlinks": [],
            "related_notes": [
                {
                    "relative_path": "Math/Rank.md",
                    "title": "Rank",
                    "course": "MA103N",
                    "topic": "Matrix Factorization",
                    "source": "MIT 18.06 Lecture 2",
                    "note_type": "concept",
                    "reasons": [
                        "Same course",
                        "Same topic",
                        "Same source",
                        "Shared tag: linear-algebra",
                    ],
                }
            ],
            "connection_facets": [
                {"kind": "course", "label": "MA103N", "peer_count": 3},
                {
                    "kind": "topic",
                    "label": "Matrix Factorization",
                    "peer_count": 1,
                },
                {
                    "kind": "source",
                    "label": "MIT 18.06 Lecture 2",
                    "peer_count": 2,
                },
            ],
        }


def test_full_reader_renders_related_notes_and_study_context():
    from personal_learning_assistant.ui.web import create_app

    app = create_app(
        {
            "TESTING": True,
            "NOTES_STUDIO_READER_SERVICE_FACTORY": lambda: FakeReaderWebService(),
        }
    )
    response = app.test_client().get("/notes/note?path=Math%2FLU.md")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in (
        "Related notes",
        "Study context",
        "Rank",
        "Same course",
        "Same topic",
        "Same source",
        "MIT 18.06 Lecture 2",
        "3 related notes",
    ):
        assert expected in html
    assert "/notes/note?path=Math/Rank.md" in html or "/notes/note?path=Math%2FRank.md" in html
    assert "course=MA103N" in html
    assert "q=Matrix+Factorization" in html
    assert "q=MIT+18.06+Lecture+2" in html


def test_connections_service_is_pure_local_and_does_not_depend_on_tutor_or_indexes():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "personal_learning_assistant/services/notes_studio_connections_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "personal_learning_assistant.tutor",
        "sqlite3",
        "KnowledgeReaderService",
        "IndexBuilder",
        "apply_snapshot",
        "write_text(",
        "write_bytes(",
        "openai",
        "requests",
        "httpx",
    ):
        assert forbidden not in source


def test_connection_ui_is_responsive_and_reason_labels_are_not_hidden_scores():
    root = Path(__file__).resolve().parents[1]
    template = (
        root / "personal_learning_assistant/ui/web/templates/notes_reader.html"
    ).read_text(encoding="utf-8")
    css = (
        root / "personal_learning_assistant/ui/web/static/css/app.css"
    ).read_text(encoding="utf-8")

    assert "note.related_notes" in template
    assert "note.connection_facets" in template
    assert "relationship-score" not in template
    assert ".notes-related-list" in css
    assert ".notes-connection-facets" in css
    assert "@media (max-width: 680px)" in css
