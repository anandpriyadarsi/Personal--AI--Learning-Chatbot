"""Legacy adapter for the existing ``data/notes.json`` store.

Reads remain side-effect free. Phase 2 Fix 8 adds the explicit append command
needed by NotesService while keeping the legacy JSON list as the only
structured authority.
"""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Optional

from config import NOTES_FILE


class LegacyJsonNoteRepository:
    """
    Legacy Notes repository for Phase 2.

    Missing, empty, invalid, or non-list stores are represented as an empty
    note collection, matching the old loader behavior. Reads never create,
    rewrite, or normalize the source file.
    """

    def __init__(
        self,
        path: Optional[str] = None,
    ):
        self.path = Path(
            path
            if path is not None
            else NOTES_FILE
        )

    def load_notes(self):
        if not self.path.exists():
            return []

        try:
            raw_text = self.path.read_text(
                encoding="utf-8"
            )
        except OSError:
            return []

        if not raw_text.strip():
            return []

        try:
            data = json.loads(
                raw_text
            )
        except json.JSONDecodeError:
            return []

        if not isinstance(
            data,
            list,
        ):
            return []

        notes = []

        for item in data:
            if isinstance(
                item,
                dict,
            ):
                notes.append(
                    deepcopy(item)
                )

        return notes

    def append_note(
        self,
        note,
    ):
        """
        Append one legacy-shaped note and atomically replace the JSON file.

        The stored record stays exactly in the V1 shape:
        title/topic/difficulty/content.
        """
        notes = self.load_notes()
        stored_note = deepcopy(
            dict(note)
        )
        notes.append(
            stored_note
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.path.with_name(
            self.path.name + ".tmp"
        )

        try:
            payload = json.dumps(
                notes,
                indent=4,
            )

            temporary_path.write_text(
                payload,
                encoding="utf-8",
            )

            os.replace(
                temporary_path,
                self.path,
            )
        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

        return deepcopy(
            stored_note
        )
