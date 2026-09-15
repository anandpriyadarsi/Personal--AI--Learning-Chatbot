"""Legacy authority for Phase 4.8 Grades + Academic Calendar dual reads.

The existing ``semester_grade_intelligence.py`` and assessment/calendar modules
remain authoritative.  This adapter exposes side-effect-free reads over the
legacy grade configuration and assessment deadline store without creating files.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union


GRADE_CONFIG_VERSION = 1
ASSESSMENT_VERSION = 2
MAX_ASSESSMENTS = 200

DEFAULT_GRADE_SCALE = [
    {"letter": "A+", "min_score": 90.0, "grade_point": 10.0},
    {"letter": "A", "min_score": 80.0, "grade_point": 9.0},
    {"letter": "B+", "min_score": 70.0, "grade_point": 8.0},
    {"letter": "B", "min_score": 60.0, "grade_point": 7.0},
    {"letter": "C", "min_score": 50.0, "grade_point": 6.0},
    {"letter": "D", "min_score": 40.0, "grade_point": 5.0},
    {"letter": "F", "min_score": 0.0, "grade_point": 0.0},
]


def default_grade_config() -> Dict[str, Any]:
    return {
        "version": GRADE_CONFIG_VERSION,
        "semester_name": "Semester 1",
        "target_sgpa": None,
        "courses": [],
        "grade_scale": deepcopy(DEFAULT_GRADE_SCALE),
    }


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _assessment_event_status(value: Any) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token in {"completed", "done"}:
        return "completed"
    if token in {"cancelled", "canceled", "archived"}:
        return "cancelled"
    return "scheduled"


class LegacyJsonGradeCalendarRepository:
    """Authoritative legacy read/write adapter used by the Phase 4.8 seam."""

    def __init__(
        self,
        *,
        grade_config_path: Union[str, Path] = "data/semester_grade_config.json",
        assessments_path: Union[str, Path] = "data/assessments.json",
    ) -> None:
        self.grade_config_path = Path(grade_config_path)
        self.assessments_path = Path(assessments_path)

    def grade_source_present(self) -> bool:
        return self.grade_config_path.exists()

    def load_grade_config(self) -> Dict[str, Any]:
        raw = _read_json(self.grade_config_path)
        if not isinstance(raw, dict):
            return default_grade_config()

        config = default_grade_config()
        config.update(deepcopy(raw))
        if not isinstance(config.get("courses"), list):
            config["courses"] = []
        if not isinstance(config.get("grade_scale"), list) or not config["grade_scale"]:
            config["grade_scale"] = deepcopy(DEFAULT_GRADE_SCALE)
        return config

    def load_assessment_store(self) -> Dict[str, Any]:
        raw = _read_json(self.assessments_path)
        if not isinstance(raw, dict):
            return {"version": ASSESSMENT_VERSION, "assessments": []}
        assessments = raw.get("assessments", [])
        if not isinstance(assessments, list):
            assessments = []
        return {
            "version": ASSESSMENT_VERSION,
            "assessments": deepcopy(assessments[-MAX_ASSESSMENTS:]),
        }

    def load_calendar_deadlines(self):
        """Project the authoritative assessment deadlines without any write."""
        rows = []
        for assessment in self.load_assessment_store()["assessments"]:
            if not isinstance(assessment, dict):
                continue
            due_on = assessment.get("due_date") or assessment.get("due_on")
            if not isinstance(due_on, str) or not due_on.strip():
                continue
            due_on = due_on.strip()
            due_time = assessment.get("due_time")
            due_time = due_time.strip() if isinstance(due_time, str) and due_time.strip() else None
            assessment_id = str(assessment.get("id") or "").strip()
            rows.append(
                {
                    "assessment_id": assessment_id,
                    "course_id": str(assessment.get("course_id") or "").strip(),
                    "title": str(assessment.get("title") or "").strip(),
                    "starts_at": due_on if due_time is None else f"{due_on}T{due_time}",
                    "all_day": 1 if due_time is None else 0,
                    "status": _assessment_event_status(assessment.get("status")),
                    "raw_due_date": due_on,
                    "raw_due_time": due_time,
                }
            )
        return rows

    def load_state(self) -> Dict[str, Any]:
        return {
            "grade_source_present": self.grade_source_present(),
            "grade_config": self.load_grade_config(),
            "calendar_deadlines": self.load_calendar_deadlines(),
        }

    def save_grade_config(self, config: Mapping[str, Any]) -> Dict[str, Any]:
        payload = deepcopy(dict(config))
        self.grade_config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(str(self.grade_config_path) + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(str(temporary), str(self.grade_config_path))
        return self.load_grade_config()


__all__ = (
    "ASSESSMENT_VERSION",
    "DEFAULT_GRADE_SCALE",
    "GRADE_CONFIG_VERSION",
    "LegacyJsonGradeCalendarRepository",
    "default_grade_config",
)
