import ast
import json

import notes

from personal_learning_assistant.ui.cli.notes_cli import (
    NotesCLI,
)


class FakeNote:
    def __init__(
        self,
        title,
        topic,
        difficulty,
        content,
    ):
        self.title = title
        self.topic = topic
        self.difficulty = difficulty
        self.content = content

    def to_legacy_dict(self):
        return {
            "title": self.title,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "content": self.content,
        }


class FakeResult:
    def __init__(
        self,
        notes=(),
        count=None,
    ):
        self.notes = tuple(
            notes
        )
        self.count = (
            len(self.notes)
            if count is None
            else count
        )


class FakeNotesService:
    def __init__(self):
        self.notes = [
            FakeNote(
                "LU Factorization",
                "Linear Algebra",
                "Medium",
                "A = LU",
            ),
            FakeNote(
                "Vector Spaces",
                "Linear Algebra",
                "Hard",
                "",
            ),
        ]
        self.search_queries = []

    def list_notes(self):
        return FakeResult(
            self.notes
        )

    def count_notes(self):
        return FakeResult(
            count=len(
                self.notes
            )
        )

    def search_notes(
        self,
        query,
    ):
        self.search_queries.append(
            query.text
        )
        wanted = (
            query.text
            .strip()
            .casefold()
        )

        matches = [
            note
            for note in self.notes
            if wanted
            and wanted in (
                note.title
                + "\n"
                + note.topic
                + "\n"
                + note.content
            ).casefold()
        ]

        return FakeResult(
            matches
        )


def _scripted_input(values):
    iterator = iter(
        values
    )

    def input_fn(prompt):
        return next(
            iterator
        )

    return input_fn


def test_notes_cli_view_is_read_only_renderer():
    service = FakeNotesService()
    output = []

    before = json.dumps(
        [
            note.to_legacy_dict()
            for note in service.notes
        ],
        sort_keys=True,
    )

    result = NotesCLI(
        service,
        output_fn=output.append,
    ).view_notes()

    after = json.dumps(
        [
            note.to_legacy_dict()
            for note in service.notes
        ],
        sort_keys=True,
    )

    assert before == after
    assert result[0]["title"] == "LU Factorization"
    assert any(
        "LU Factorization"
        in line
        for line in output
    )


def test_notes_cli_search_uses_non_interactive_service_query():
    service = FakeNotesService()
    output = []

    result = NotesCLI(
        service,
        input_fn=_scripted_input(
            ["vector"]
        ),
        output_fn=output.append,
    ).search_notes()

    assert service.search_queries == [
        "vector"
    ]
    assert [
        item["title"]
        for item in result
    ] == [
        "Vector Spaces"
    ]


def test_notes_cli_count_returns_service_count():
    service = FakeNotesService()
    output = []

    count = NotesCLI(
        service,
        output_fn=output.append,
    ).count_notes()

    assert count == 2
    assert any(
        "Total Notes: 2"
        in line
        for line in output
    )


def test_root_view_notes_delegates_to_extracted_cli(
    monkeypatch,
):
    calls = []

    class FakeCLI:
        def view_notes(self):
            calls.append(
                "view"
            )
            return [
                {
                    "title": "x"
                }
            ]

    monkeypatch.setattr(
        notes,
        "_build_notes_cli",
        lambda: FakeCLI(),
    )

    result = notes.view_notes()

    assert calls == [
        "view"
    ]
    assert result == [
        {
            "title": "x"
        }
    ]


def test_root_search_notes_delegates_to_extracted_cli(
    monkeypatch,
):
    calls = []

    class FakeCLI:
        def search_notes(self):
            calls.append(
                "search"
            )
            return []

    monkeypatch.setattr(
        notes,
        "_build_notes_cli",
        lambda: FakeCLI(),
    )

    assert notes.search_notes() == []
    assert calls == [
        "search"
    ]


def test_root_count_notes_delegates_to_extracted_cli(
    monkeypatch,
):
    calls = []

    class FakeCLI:
        def count_notes(self):
            calls.append(
                "count"
            )
            return 7

    monkeypatch.setattr(
        notes,
        "_build_notes_cli",
        lambda: FakeCLI(),
    )

    assert notes.count_notes() == 7
    assert calls == [
        "count"
    ]


def test_routed_root_functions_have_no_direct_input_or_print_calls():
    source = open(
        notes.__file__,
        "r",
        encoding="utf-8",
    ).read()
    tree = ast.parse(
        source
    )

    targets = {
        "view_notes",
        "search_notes",
        "count_notes",
    }

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
    }

    for name in targets:
        direct_calls = []

        for node in ast.walk(
            functions[name]
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if (
                isinstance(
                    node.func,
                    ast.Name,
                )
                and node.func.id
                in {
                    "input",
                    "print",
                }
            ):
                direct_calls.append(
                    node.func.id
                )

        assert direct_calls == []


def test_add_note_still_exists_for_legacy_write_path():
    assert callable(
        notes.add_note
    )
