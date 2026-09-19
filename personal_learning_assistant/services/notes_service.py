"""Non-interactive service for the legacy Notes subsystem."""

from typing import Optional

from personal_learning_assistant.domain.note_models import (
    CreateNoteCommand,
    ListNotesQuery,
    NoteCountResult,
    NoteCreateResult,
    NoteListResult,
    NoteSearchResult,
    NoteUpdateResult,
    NoteView,
    SearchNotesQuery,
    UpdateNoteCommand,
)
from personal_learning_assistant.repositories.interfaces import NoteRepository


class NotesService:
    """Application service over the legacy-compatible Notes repository."""

    def __init__(self, repository: NoteRepository):
        self.repository = repository

    def create_note(self, command: CreateNoteCommand) -> NoteCreateResult:
        note = NoteView(
            title=str(command.title),
            topic=str(command.topic),
            difficulty=str(command.difficulty),
            content=str(command.content),
        )
        stored = self.repository.append_note(note.to_legacy_dict())
        return NoteCreateResult(note=NoteView.from_legacy(stored))

    def list_notes(self, query: Optional[ListNotesQuery] = None) -> NoteListResult:
        query = query or ListNotesQuery()
        notes = [
            NoteView.from_legacy(item, position=position)
            for position, item in enumerate(self.repository.load_notes(), start=1)
        ]
        notes = self._apply_filters(notes, topic=query.topic, difficulty=query.difficulty)
        return NoteListResult(notes=tuple(notes))

    def get_note(self, position: int):
        if position < 1:
            return None
        notes = self.list_notes().notes
        if position > len(notes):
            return None
        return notes[position - 1]

    def update_note(self, command: UpdateNoteCommand) -> NoteUpdateResult:
        position = int(command.position)
        if self.get_note(position) is None:
            raise IndexError("Note position is out of range.")
        note = NoteView(
            title=str(command.title),
            topic=str(command.topic),
            difficulty=str(command.difficulty),
            content=str(command.content),
            position=position,
        )
        stored = self.repository.replace_note(position, note.to_legacy_dict())
        return NoteUpdateResult(note=NoteView.from_legacy(stored, position=position))

    def count_notes(self, query: Optional[ListNotesQuery] = None) -> NoteCountResult:
        result = self.list_notes(query)
        return NoteCountResult(count=len(result.notes))

    def search_notes(self, query: SearchNotesQuery) -> NoteSearchResult:
        search_text = query.text.strip().casefold()
        candidates = list(
            self.list_notes(
                ListNotesQuery(topic=query.topic, difficulty=query.difficulty)
            ).notes
        )
        if not search_text:
            return NoteSearchResult(query=query.text, notes=())
        matches = []
        for note in candidates:
            searchable = "\n".join((note.title, note.topic, note.content)).casefold()
            if search_text in searchable:
                matches.append(note)
        return NoteSearchResult(query=query.text, notes=tuple(matches))

    @staticmethod
    def _apply_filters(notes, topic=None, difficulty=None):
        filtered = list(notes)
        if topic is not None:
            wanted_topic = str(topic).strip().casefold()
            filtered = [
                note for note in filtered
                if note.topic.strip().casefold() == wanted_topic
            ]
        if difficulty is not None:
            wanted_difficulty = str(difficulty).strip().casefold()
            filtered = [
                note for note in filtered
                if note.difficulty.strip().casefold() == wanted_difficulty
            ]
        return filtered
