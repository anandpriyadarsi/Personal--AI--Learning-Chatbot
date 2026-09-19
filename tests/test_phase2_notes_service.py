import hashlib
import json

from personal_learning_assistant.domain.note_models import (
    ListNotesQuery,
    SearchNotesQuery,
    UpdateNoteCommand,
)
from personal_learning_assistant.repositories.json.note_repository import (
    LegacyJsonNoteRepository,
)
from personal_learning_assistant.services.notes_service import (
    NotesService,
)


FIXTURE = [
    {
        "title": "LU Factorization",
        "topic": "Linear Algebra",
        "difficulty": "Medium",
        "content": "A = LU separates elimination into lower and upper matrices.",
    },
    {
        "title": "Vector Spaces",
        "topic": "Linear Algebra",
        "difficulty": "Hard",
        "content": "",
    },
    {
        "title": "Atomic Structure",
        "topic": "Chemistry",
        "difficulty": "Easy",
        "content": "Basic chemistry note.",
    },
]


def _write_fixture(path):
    path.write_text(
        json.dumps(
            FIXTURE,
            indent=2,
        ),
        encoding="utf-8",
    )


def _hash(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _service(path):
    return NotesService(
        LegacyJsonNoteRepository(
            path
        )
    )


def test_repository_loads_flat_legacy_note_schema(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    notes = LegacyJsonNoteRepository(
        notes_file
    ).load_notes()

    assert notes == FIXTURE


def test_list_notes_preserves_order_and_legacy_shape(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    result = _service(
        notes_file
    ).list_notes()

    assert [
        note.to_legacy_dict()
        for note in result.notes
    ] == FIXTURE


def test_count_notes_is_non_interactive_and_correct(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    result = _service(
        notes_file
    ).count_notes()

    assert result.count == 3


def test_topic_filter_is_case_insensitive_exact_match(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    result = _service(
        notes_file
    ).list_notes(
        ListNotesQuery(
            topic="linear algebra"
        )
    )

    assert [
        note.title
        for note in result.notes
    ] == [
        "LU Factorization",
        "Vector Spaces",
    ]


def test_difficulty_filter_is_case_insensitive(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    result = _service(
        notes_file
    ).list_notes(
        ListNotesQuery(
            difficulty="hard"
        )
    )

    assert [
        note.title
        for note in result.notes
    ] == [
        "Vector Spaces"
    ]


def test_search_is_case_insensitive_over_title_topic_and_content(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )
    service = _service(
        notes_file
    )

    title_match = service.search_notes(
        SearchNotesQuery(
            text="lu factorization"
        )
    )
    topic_matches = service.search_notes(
        SearchNotesQuery(
            text="LINEAR ALGEBRA"
        )
    )
    content_match = service.search_notes(
        SearchNotesQuery(
            text="lower and upper"
        )
    )

    assert [
        note.title
        for note in title_match.notes
    ] == [
        "LU Factorization"
    ]

    assert [
        note.title
        for note in topic_matches.notes
    ] == [
        "LU Factorization",
        "Vector Spaces",
    ]

    assert [
        note.title
        for note in content_match.notes
    ] == [
        "LU Factorization"
    ]


def test_blank_search_returns_no_matches(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    result = _service(
        notes_file
    ).search_notes(
        SearchNotesQuery(
            text="   "
        )
    )

    assert result.notes == ()


def test_blank_content_is_preserved_not_dropped(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    result = _service(
        notes_file
    ).list_notes()

    vector_note = [
        note
        for note in result.notes
        if note.title == "Vector Spaces"
    ][0]

    assert vector_note.content == ""


def test_read_queries_leave_notes_json_hash_unchanged(
    tmp_path,
):
    notes_file = tmp_path / "notes.json"
    _write_fixture(
        notes_file
    )

    before = _hash(
        notes_file
    )

    service = _service(
        notes_file
    )
    service.list_notes()
    service.count_notes()
    service.search_notes(
        SearchNotesQuery(
            text="linear"
        )
    )

    after = _hash(
        notes_file
    )

    assert after == before


def test_missing_empty_invalid_and_non_list_stores_are_read_only_empty(
    tmp_path,
):
    cases = [
        ("missing.json", None),
        ("empty.json", ""),
        ("invalid.json", "{bad json"),
        ("object.json", "{}"),
    ]

    for name, content in cases:
        path = tmp_path / name

        if content is not None:
            path.write_text(
                content,
                encoding="utf-8",
            )

        repository = LegacyJsonNoteRepository(
            path
        )

        assert repository.load_notes() == []

        if content is None:
            assert not path.exists()



def test_list_notes_exposes_nonpersisted_one_based_positions(tmp_path):
    notes_file = tmp_path / "notes.json"
    _write_fixture(notes_file)

    result = _service(notes_file).list_notes()

    assert [note.position for note in result.notes] == [1, 2, 3]
    assert [note.to_legacy_dict() for note in result.notes] == FIXTURE


def test_get_note_uses_position_without_mutating_store(tmp_path):
    notes_file = tmp_path / "notes.json"
    _write_fixture(notes_file)
    service = _service(notes_file)
    before = _hash(notes_file)

    assert service.get_note(2).title == "Vector Spaces"
    assert service.get_note(0) is None
    assert service.get_note(99) is None
    assert _hash(notes_file) == before


def test_search_preserves_original_positions(tmp_path):
    notes_file = tmp_path / "notes.json"
    _write_fixture(notes_file)
    service = _service(notes_file)

    matches = service.search_notes(SearchNotesQuery(text="linear algebra"))

    assert [note.position for note in matches.notes] == [1, 2]


def test_update_note_replaces_exact_position_and_preserves_v1_shape(tmp_path):
    notes_file = tmp_path / "notes.json"
    _write_fixture(notes_file)
    service = _service(notes_file)

    result = service.update_note(
        UpdateNoteCommand(
            position=2,
            title="Vector Spaces revised",
            topic="Linear Algebra",
            difficulty="Medium",
            content="Updated body",
        )
    )

    assert result.note.position == 2
    stored = json.loads(notes_file.read_text(encoding="utf-8"))
    assert stored[1] == {
        "title": "Vector Spaces revised",
        "topic": "Linear Algebra",
        "difficulty": "Medium",
        "content": "Updated body",
    }
    assert "position" not in stored[1]


def test_update_note_targets_position_even_when_titles_are_duplicate(tmp_path):
    notes_file = tmp_path / "notes.json"
    notes_file.write_text(
        json.dumps(
            [
                {"title": "Same", "topic": "Math", "difficulty": "Easy", "content": "one"},
                {"title": "Same", "topic": "Math", "difficulty": "Hard", "content": "two"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    service = _service(notes_file)

    service.update_note(
        UpdateNoteCommand(
            position=2,
            title="Same",
            topic="Math",
            difficulty="Medium",
            content="updated",
        )
    )

    stored = json.loads(notes_file.read_text(encoding="utf-8"))
    assert stored[0]["content"] == "one"
    assert stored[1]["content"] == "updated"


def test_invalid_update_position_preserves_store_hash(tmp_path):
    import pytest

    notes_file = tmp_path / "notes.json"
    _write_fixture(notes_file)
    service = _service(notes_file)
    before = _hash(notes_file)

    with pytest.raises(IndexError, match="out of range"):
        service.update_note(
            UpdateNoteCommand(
                position=99,
                title="Nope",
                topic="Math",
                difficulty="Hard",
                content="No write",
            )
        )

    assert _hash(notes_file) == before
