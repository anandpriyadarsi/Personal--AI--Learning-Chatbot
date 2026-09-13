"""Terminal adapter for the legacy Notes read commands.

Phase 2 Fix 7 keeps note creation on the legacy path for now. Only the
read-oriented terminal functions (view/search/count) are routed through the
non-interactive NotesService introduced in Fix 6.
"""

from typing import Callable

from personal_learning_assistant.domain.note_models import (
    SearchNotesQuery,
)


class NotesCLI:
    """Interactive renderer/controller for legacy Notes read commands."""

    def __init__(
        self,
        service,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ):
        self.service = service
        self.input = input_fn
        self.output = output_fn

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
