"""Read-only adapter for the existing ``data/notes.json`` store."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Optional

from config import NOTES_FILE


class LegacyJsonNoteRepository:
    """
    Read-only legacy Notes repository for Phase 2 Fix 6.

    Missing, empty, invalid, or non-list stores are represented as an empty
    note collection. Reads never create, rewrite, or normalize the source file.
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
