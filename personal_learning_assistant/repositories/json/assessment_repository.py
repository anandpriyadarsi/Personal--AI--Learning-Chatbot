"""Legacy JSON assessment repository for the Phase 4.2 storage seam.

The current application still uses ``assignment_exam_assistant.py`` directly.
This adapter intentionally mirrors that module's ``load_store``/``save_store``
shape without changing its public functions or authority.  Reads are kept
side-effect free so dual-read verification cannot create directories or files.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Optional

from config import BASE_PATH
from personal_learning_assistant.repositories.interfaces import AssessmentState


ASSESSMENT_VERSION = 2
MAX_ASSESSMENTS = 200


class LegacyJsonAssessmentRepository:
    """Read/write adapter for the existing ``data/assessments.json`` store."""

    def __init__(self, path: Optional[os.PathLike] = None):
        self.path = Path(
            path if path is not None else BASE_PATH / "data" / "assessments.json"
        )

    @staticmethod
    def default_state() -> AssessmentState:
        return {"version": ASSESSMENT_VERSION, "assessments": []}

    def load_state(self) -> AssessmentState:
        """Return the legacy application-visible store without mutating storage."""
        if not self.path.exists():
            return deepcopy(self.default_state())

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return deepcopy(self.default_state())

        if not isinstance(raw, dict):
            return deepcopy(self.default_state())

        assessments = raw.get("assessments", [])
        if not isinstance(assessments, list):
            assessments = []

        # Match assignment_exam_assistant.load_store exactly: the application
        # exposes the current store version and the last MAX_ASSESSMENTS raw
        # records without normalising the records themselves.
        return {
            "version": ASSESSMENT_VERSION,
            "assessments": deepcopy(assessments[-MAX_ASSESSMENTS:]),
        }

    def save_state(self, state: AssessmentState) -> AssessmentState:
        """Persist only through the legacy JSON authority."""
        payload = deepcopy(state)
        if not isinstance(payload, dict):
            raise TypeError("assessment state must be a dictionary")
        assessments = payload.get("assessments", [])
        if not isinstance(assessments, list):
            raise TypeError("assessment state field 'assessments' must be a list")
        payload = {
            "version": ASSESSMENT_VERSION,
            "assessments": deepcopy(assessments[-MAX_ASSESSMENTS:]),
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(temporary, self.path)
        return deepcopy(payload)


__all__ = (
    "ASSESSMENT_VERSION",
    "MAX_ASSESSMENTS",
    "LegacyJsonAssessmentRepository",
)
