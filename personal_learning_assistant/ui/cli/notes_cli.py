"""Terminal adapter for the legacy Notes commands.

Phase 2 Fix 8 routes both legacy reads and note creation through the
non-interactive NotesService. ``input``/``print`` stay in this adapter.
"""

from typing import Callable

from personal_learning_assistant.domain.note_models import (
    CreateNoteCommand,
    SearchNotesQuery,
)


class NotesCLI:
    """Interactive renderer/controller for legacy Notes commands."""

    def __init__(
        self,
        service,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ):
        self.service = service
        self.input = input_fn
        self.output = output_fn

    def add_note(self):
        self.output(
            "\n========== ADD NEW NOTE ==========\n"
        )

        title = self.input(
            "Title : "
        )
        topic = self.input(
            "Topic : "
        )
        difficulty = self.input(
            "Difficulty (Easy/Medium/Hard): "
        )

        self.output(
            "\nEnter your note."
        )
        self.output(
            "Type END on a new line when finished.\n"
        )

        lines = []

        while True:
            line = self.input(
                ""
            )

            if line.upper() == "END":
                break

            lines.append(
                line
            )

        result = self.service.create_note(
            CreateNoteCommand(
                title=title,
                topic=topic,
                difficulty=difficulty,
                content="\n".join(
                    lines
                ),
            )
        )

        self.output(
            "\n✅ Note saved successfully!"
        )

        return result.note.to_legacy_dict()

    def view_notes(self):
        result = self.service.list_notes()

        self.output(
            "\n========== NOTES =========="
        )

        if not result.notes:
            self.output(
                "\nNo notes found."
            )
            return []

        for number, note in enumerate(
            result.notes,
            start=1,
        ):
            self.output(
                f"\nNote {number}"
            )
            self.output(
                f"Title      : {note.title}"
            )
            self.output(
                f"Topic      : {note.topic}"
            )
            self.output(
                f"Difficulty : {note.difficulty}"
            )
            self.output(
                f"Content    : {note.content}"
            )
            self.output(
                "-" * 45
            )

        return [
            note.to_legacy_dict()
            for note in result.notes
        ]

    def search_notes(self):
        query = self.input(
            "\nEnter search text: "
        ).strip()

        result = self.service.search_notes(
            SearchNotesQuery(
                text=query
            )
        )

        self.output(
            "\n========== SEARCH RESULTS =========="
        )

        if not query:
            self.output(
                "\nPlease enter a search term."
            )
            return []

        if not result.notes:
            self.output(
                "\nNo matching notes found."
            )
            return []

        for number, note in enumerate(
            result.notes,
            start=1,
        ):
            self.output(
                f"\nResult {number}"
            )
            self.output(
                f"Title      : {note.title}"
            )
            self.output(
                f"Topic      : {note.topic}"
            )
            self.output(
                f"Difficulty : {note.difficulty}"
            )
            self.output(
                f"Content    : {note.content}"
            )
            self.output(
                "-" * 45
            )

        return [
            note.to_legacy_dict()
            for note in result.notes
        ]

    def count_notes(self):
        result = self.service.count_notes()

        self.output(
            f"\nTotal Notes: {result.count}"
        )

        return result.count
