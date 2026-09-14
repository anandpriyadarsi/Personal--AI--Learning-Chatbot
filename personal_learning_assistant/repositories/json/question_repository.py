"""Legacy JSON question-workspace repository for the Phase 4.3 storage seam.

The current application still uses ``assessment_question_workspace.py``
directly.  This adapter mirrors that module's ``load_store``/``save_store``
shape without changing its public functions or authority.  Reads are strictly
side-effect free so parity observation cannot create directories or files.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Optional

from config import BASE_PATH
from personal_learning_assistant.repositories.interfaces import QuestionState


WORKSPACE_VERSION = 1


class LegacyJsonQuestionRepository:
    """Read/write adapter for ``data/assessment_workspace.json``."""

    def __init__(self, path: Optional[os.PathLike] = None):
        self.path = Path(
            path
            if path is not None
            else BASE_PATH / "data" / "assessment_workspace.json"
        )

    @staticmethod
    def default_state() -> QuestionState:
        return {"version": WORKSPACE_VERSION, "workspaces": {}}

    def load_state(self) -> QuestionState:
        """Return the legacy application-visible store without writing."""
        if not self.path.exists():
            return deepcopy(self.default_state())

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return deepcopy(self.default_state())

        if not isinstance(raw, dict):
            return deepcopy(self.default_state())

        workspaces = raw.get("workspaces", {})
        if not isinstance(workspaces, dict):
            workspaces = {}

        # Match assessment_question_workspace.load_store exactly: current store
        # version plus the raw workspace dictionary, without normalizing nested
        # records and without creating a missing data directory during reads.
        return {
            "version": WORKSPACE_VERSION,
            "workspaces": deepcopy(workspaces),
        }

    def save_state(self, state: QuestionState) -> QuestionState:
        """Persist only through the legacy JSON authority."""
        payload = deepcopy(state)
        if not isinstance(payload, dict):
            raise TypeError("question workspace state must be a dictionary")
        workspaces = payload.get("workspaces", {})
        if not isinstance(workspaces, dict):
            raise TypeError("question workspace field 'workspaces' must be a dictionary")
        payload = {
            "version": WORKSPACE_VERSION,
            "workspaces": deepcopy(workspaces),
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(temporary, self.path)
        return deepcopy(payload)


__all__ = (
    "WORKSPACE_VERSION",
    "LegacyJsonQuestionRepository",
)
