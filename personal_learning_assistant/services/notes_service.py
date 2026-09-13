"""Non-interactive read service for the legacy Notes subsystem."""

from typing import Optional

from personal_learning_assistant.domain.note_models import (
    ListNotesQuery,
    NoteCountResult,
    NoteListResult,
    NoteSearchResult,
    NoteView,
    SearchNotesQuery,
)
from personal_learning_assistant.repositories.interfaces import (
    NoteRepository,
)


class NotesService:
    """
    Read-only Notes service for Phase 2 Fix 6.

    The current JSON file remains the authority. No write/migration behavior is
    introduced here because legacy JSON notes will later be reviewed before
    Notes Studio moves authoritative note bodies to the Obsidian vault.
    """

    def __init__(
        self,
        repository: NoteRepository,
    ):
        self.repository = repository

    def list_notes(
        self,
        query: Optional[ListNotesQuery] = None,
    ) -> NoteListResult:
        query = query or ListNotesQuery()

        notes = [
            NoteView.from_legacy(item)
            for item in self.repository.load_notes()
        ]

        notes = self._apply_filters(
            notes,
            topic=query.topic,
            difficulty=query.difficulty,
        )

        return NoteListResult(
            notes=tuple(notes)
        )

    def count_notes(
        self,
        query: Optional[ListNotesQuery] = None,
    ) -> NoteCountResult:
        result = self.list_notes(
            query
        )

        return NoteCountResult(
            count=len(
                result.notes
            )
        )

    def search_notes(
        self,
        query: SearchNotesQuery,
    ) -> NoteSearchResult:
        search_text = (
            query.text
            .strip()
            .casefold()
        )

        candidates = list(
            self.list_notes(
                ListNotesQuery(
                    topic=query.topic,
                    difficulty=query.difficulty,
                )
            ).notes
        )

        if not search_text:
            return NoteSearchResult(
                query=query.text,
                notes=(),
            )

        matches = []

        for note in candidates:
            searchable = "\n".join(
                (
                    note.title,
                    note.topic,
                    note.content,
                )
            ).casefold()

            if search_text in searchable:
                matches.append(
                    note
                )

        return NoteSearchResult(
            query=query.text,
            notes=tuple(matches),
        )

    @staticmethod
    def _apply_filters(
        notes,
        topic=None,
        difficulty=None,
    ):
        filtered = list(notes)

        if topic is not None:
            wanted_topic = (
                str(topic)
                .strip()
                .casefold()
            )
            filtered = [
                note
                for note in filtered
                if (
                    note.topic
                    .strip()
                    .casefold()
                    == wanted_topic
                )
            ]

        if difficulty is not None:
            wanted_difficulty = (
                str(difficulty)
                .strip()
                .casefold()
            )
            filtered = [
                note
                for note in filtered
                if (
                    note.difficulty
                    .strip()
                    .casefold()
                    == wanted_difficulty
                )
            ]

        return filtered
