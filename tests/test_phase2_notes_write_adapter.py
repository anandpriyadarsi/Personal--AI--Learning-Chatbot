import ast
import hashlib
import json

import notes

from personal_learning_assistant.domain.note_models import (
    CreateNoteCommand,
    UpdateNoteCommand,
)
from personal_learning_assistant.repositories.json.note_repository import (
    LegacyJsonNoteRepository,
)
from personal_learning_assistant.services.notes_service import (
    NotesService,
)
from personal_learning_assistant.ui.cli.notes_cli import (
    NotesCLI,
)


def _scripted_input(values):
    iterator = iter(values)

    def input_fn(prompt=""):
        return next(iterator)

    return input_fn


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeCreatedNote:
    def __init__(self, title, topic, difficulty, content):
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


class FakeCreateResult:
    def __init__(self, note):
        self.note = note


class FakeWriteService:
    def __init__(self):
        self.commands = []

    def create_note(self, command):
        self.commands.append(command)
        return FakeCreateResult(
            FakeCreatedNote(
                command.title,
                command.topic,
                command.difficulty,
                command.content,
            )
        )


def test_notes_cli_add_preserves_legacy_prompts_and_multiline_content():
    service = FakeWriteService()
    output = []

    result = NotesCLI(
        service,
        input_fn=_scripted_input(
            [
                "LU Factorization",
                "Linear Algebra",
                "Medium",
                "A = LU",
                "L is lower triangular",
                "END",
            ]
        ),
        output_fn=output.append,
    ).add_note()

    assert len(service.commands) == 1
    command = service.commands[0]
    assert command.title == "LU Factorization"
    assert command.topic == "Linear Algebra"
    assert command.difficulty == "Medium"
    assert command.content == "A = LU\nL is lower triangular"
    assert result == {
        "title": "LU Factorization",
        "topic": "Linear Algebra",
        "difficulty": "Medium",
        "content": "A = LU\nL is lower triangular",
    }
    assert any("ADD NEW NOTE" in line for line in output)
    assert any("Note saved successfully" in line for line in output)


def test_service_create_note_is_non_interactive_and_preserves_values(tmp_path, monkeypatch):
    path = tmp_path / "notes.json"

    def fail_input(*args, **kwargs):
        raise AssertionError("NotesService called input().")

    monkeypatch.setattr("builtins.input", fail_input)
    service = NotesService(LegacyJsonNoteRepository(path))
    result = service.create_note(
        CreateNoteCommand(
            title="  Keep spaces  ",
            topic="Linear Algebra",
            difficulty="Medium",
            content="line 1\nline 2",
        )
    )

    assert result.note.title == "  Keep spaces  "
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == [
        {
            "title": "  Keep spaces  ",
            "topic": "Linear Algebra",
            "difficulty": "Medium",
            "content": "line 1\nline 2",
        }
    ]


def test_repository_append_keeps_existing_notes_and_v1_shape(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text(
        json.dumps(
            [
                {
                    "title": "Old",
                    "topic": "Math",
                    "difficulty": "Easy",
                    "content": "old content",
                }
            ],
            indent=4,
        ),
        encoding="utf-8",
    )
    repository = LegacyJsonNoteRepository(path)
    repository.append_note(
        {
            "title": "New",
            "topic": "C",
            "difficulty": "Hard",
            "content": "new content",
        }
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == [
        {"title": "Old", "topic": "Math", "difficulty": "Easy", "content": "old content"},
        {"title": "New", "topic": "C", "difficulty": "Hard", "content": "new content"},
    ]
    assert not path.with_name(path.name + ".tmp").exists()


def test_repository_invalid_legacy_json_matches_old_add_behavior(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text("{broken", encoding="utf-8")
    repository = LegacyJsonNoteRepository(path)
    repository.append_note(
        {"title": "Recovered", "topic": "Test", "difficulty": "Easy", "content": ""}
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == [
        {"title": "Recovered", "topic": "Test", "difficulty": "Easy", "content": ""}
    ]


def test_read_queries_still_leave_file_hash_unchanged(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text(
        json.dumps(
            [{"title": "LU", "topic": "Linear Algebra", "difficulty": "Medium", "content": "A = LU"}],
            indent=4,
        ),
        encoding="utf-8",
    )
    before = _sha256(path)
    service = NotesService(LegacyJsonNoteRepository(path))
    service.list_notes()
    service.count_notes()
    assert _sha256(path) == before


def test_repository_replace_note_is_atomic_and_cleans_temp_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "notes.json"
    path.write_text(
        json.dumps(
            [
                {"title": "One", "topic": "Math", "difficulty": "Easy", "content": "1"},
                {"title": "Two", "topic": "Math", "difficulty": "Hard", "content": "2"},
            ],
            indent=4,
        ),
        encoding="utf-8",
    )
    repository = LegacyJsonNoteRepository(path)
    before = _sha256(path)

    import personal_learning_assistant.repositories.json.note_repository as module

    def fail_replace(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    try:
        repository.replace_note(
            1,
            {"title": "Changed", "topic": "Math", "difficulty": "Easy", "content": "x"},
        )
    except OSError:
        pass
    else:
        raise AssertionError("Expected replace failure.")

    assert _sha256(path) == before
    assert not path.with_name(path.name + ".tmp").exists()


def test_repository_replace_note_updates_exact_position_and_v1_shape(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text(
        json.dumps(
            [
                {"title": "Same", "topic": "Math", "difficulty": "Easy", "content": "one"},
                {"title": "Same", "topic": "Math", "difficulty": "Hard", "content": "two"},
            ],
            indent=4,
        ),
        encoding="utf-8",
    )
    service = NotesService(LegacyJsonNoteRepository(path))
    service.update_note(
        UpdateNoteCommand(
            position=2,
            title="Same",
            topic="Math",
            difficulty="Medium",
            content="updated",
        )
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored[0]["content"] == "one"
    assert stored[1] == {
        "title": "Same",
        "topic": "Math",
        "difficulty": "Medium",
        "content": "updated",
    }
    assert not path.with_name(path.name + ".tmp").exists()


def test_root_add_note_delegates_to_extracted_cli(monkeypatch):
    calls = []

    class FakeCLI:
        def add_note(self):
            calls.append("add")
            return {"title": "x"}

    monkeypatch.setattr(notes, "_build_notes_cli", lambda: FakeCLI())
    assert notes.add_note() == {"title": "x"}
    assert calls == ["add"]


def test_all_routed_root_note_commands_have_no_direct_input_or_print_calls():
    source = open(notes.__file__, "r", encoding="utf-8").read()
    tree = ast.parse(source)
    targets = {"add_note", "view_notes", "search_notes", "count_notes"}
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    for name in targets:
        direct_calls = []
        for node in ast.walk(functions[name]):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in {"input", "print"}
            ):
                direct_calls.append(node.func.id)
        assert direct_calls == []
