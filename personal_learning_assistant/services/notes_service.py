"""Non-interactive service for the legacy Notes subsystem."""

from typing import Optional

from personal_learning_assistant.domain.note_models import (
    CreateNoteCommand,
    ListNotesQuery,
    NoteCountResult,
    NoteCreateResult,
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
    Phase 2 Notes service over the current JSON authority.

    Reads are side-effect free. Create-note is an explicit command routed to
    the legacy JSON repository; it does not introduce a second persistence
    format or migrate note bodies.
    """

    def __init__(
        self,
        repository: NoteRepository,
    ):
        self.repository = repository

    def create_note(
        self,
        command: CreateNoteCommand,
    ) -> NoteCreateResult:
        note = NoteView(
            title=str(command.title),
            topic=str(command.topic),
            difficulty=str(command.difficulty),
            content=str(command.content),
        )

        stored = self.repository.append_note(
            note.to_legacy_dict()
        )

        return NoteCreateResult(
            note=NoteView.from_legacy(
                stored
            )
        )

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
