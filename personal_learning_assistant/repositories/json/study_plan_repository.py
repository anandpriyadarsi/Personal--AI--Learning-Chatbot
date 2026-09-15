"""Legacy JSON authority for Phase 4.7 study-plan dual reads.

The existing V9.1/V9.2/V11 planner modules remain the application writers.
This adapter provides a side-effect-free observational seam over their three
JSON stores without creating missing files during reads.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)


DEFAULT_STORE = {"version": 1, "plans": []}


class LegacyJsonStudyPlanRepository:
    """Authoritative legacy study-plan store adapter.

    Reads never create directories or files.  Writes, when explicitly invoked,
    remain legacy-only and use the same temp-file + replace pattern as the
    existing planner modules.
    """

    def __init__(
        self,
        *,
        weekly_path: Union[str, Path] = "data/weekly_study_plans.json",
        multi_course_path: Union[str, Path] = "data/multi_course_weekly_plans.json",
        intelligent_path: Union[str, Path] = "data/intelligent_study_plans.json",
        authority_control_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.weekly_path = Path(weekly_path)
        self.multi_course_path = Path(multi_course_path)
        self.intelligent_path = Path(intelligent_path)
        self.authority_control_path = Path(
            authority_control_path
            if authority_control_path is not None
            else infer_authority_control_path(
                self.weekly_path, self.multi_course_path, self.intelligent_path
            )
        )

    @staticmethod
    def _read_store(path: Path, *, optional: bool = False) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None if optional else deepcopy(DEFAULT_STORE)
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None if optional else deepcopy(DEFAULT_STORE)
        if not isinstance(value, dict):
            return None if optional else deepcopy(DEFAULT_STORE)
        plans = value.get("plans", [])
        if not isinstance(plans, list):
            plans = []
        return {"version": value.get("version", 1), "plans": deepcopy(plans)}

    @staticmethod
    def _write_store(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": value.get("version", 1),
            "plans": deepcopy(value.get("plans", [])) if isinstance(value.get("plans", []), list) else [],
        }
        temporary = Path(str(path) + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(str(temporary), str(path))

    def load_weekly_store(self) -> Dict[str, Any]:
        return deepcopy(self._read_store(self.weekly_path) or DEFAULT_STORE)

    def load_multi_course_store(self) -> Dict[str, Any]:
        return deepcopy(self._read_store(self.multi_course_path) or DEFAULT_STORE)

    def load_intelligent_store(self) -> Optional[Dict[str, Any]]:
        value = self._read_store(self.intelligent_path, optional=True)
        return deepcopy(value) if value is not None else None

    def load_state(self) -> Dict[str, Any]:
        return {
            "weekly": self.load_weekly_store(),
            "multi_course": self.load_multi_course_store(),
            "intelligent": self.load_intelligent_store(),
        }

    def save_weekly_store(self, value: Mapping[str, Any]) -> None:
        guard_legacy_structured_write(self.authority_control_path)
        self._write_store(self.weekly_path, value)

    def save_multi_course_store(self, value: Mapping[str, Any]) -> None:
        guard_legacy_structured_write(self.authority_control_path)
        self._write_store(self.multi_course_path, value)

    def save_intelligent_store(self, value: Mapping[str, Any]) -> None:
        guard_legacy_structured_write(self.authority_control_path)
        self._write_store(self.intelligent_path, value)

    def save_state(self, state: Mapping[str, Any]) -> None:
        self.save_weekly_store(state.get("weekly", DEFAULT_STORE))
        self.save_multi_course_store(state.get("multi_course", DEFAULT_STORE))
        intelligent = state.get("intelligent")
        if intelligent is not None:
            self.save_intelligent_store(intelligent)


__all__ = ("LegacyJsonStudyPlanRepository",)
