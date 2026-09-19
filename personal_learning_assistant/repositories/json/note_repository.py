"""Legacy adapter for the existing ``data/notes.json`` store.

Reads remain side-effect free. Explicit commands use atomic replacement while
preserving the four-field legacy note shape.
"""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Optional

from config import NOTES_FILE


class LegacyJsonNoteRepository:
    """Repository over the current V1 notes JSON list."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path if path is not None else NOTES_FILE)

    def load_notes(self):
        if not self.path.exists():
            return []
        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        if not raw_text.strip():
            return []
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [deepcopy(item) for item in data if isinstance(item, dict)]

    def _save_notes(self, notes):
        payload = [deepcopy(dict(note)) for note in notes]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary_path.write_text(
                json.dumps(payload, indent=4),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
        return [deepcopy(item) for item in payload]

    def append_note(self, note):
        notes = self.load_notes()
        stored_note = deepcopy(dict(note))
        notes.append(stored_note)
        self._save_notes(notes)
        return deepcopy(stored_note)

    def replace_note(self, position: int, note):
        notes = self.load_notes()
        if position < 1 or position > len(notes):
            raise IndexError("Note position is out of range.")
        stored_note = deepcopy(dict(note))
        notes[position - 1] = stored_note
        self._save_notes(notes)
        return deepcopy(stored_note)
