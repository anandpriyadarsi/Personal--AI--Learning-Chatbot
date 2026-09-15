"""Legacy-authoritative read adapter for Phase 4.6 Learning Memory + Progress.

The public ``learning_memory.py`` and ``academic_progress.py`` modules remain
unchanged and continue to own application writes.  This adapter mirrors their
persisted read semantics without creating missing files, so Phase 4.6 parity
reads are observational and side-effect free.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union


MEMORY_VERSION = 2
HISTORY_VERSION = 1
COURSE_DATA_VERSION = 1
MAX_RECENT_ACTIVITY = 30
MAX_WEAK_TOPICS = 50
MAX_MASTERED_TOPICS = 50
MAX_NOTES = 30
VALID_TOPIC_STATUSES = {
    "not_started",
    "learning",
    "weak",
    "review",
    "practiced",
    "mastered",
}


def _default_memory() -> Dict[str, Any]:
    return {
        "version": MEMORY_VERSION,
        "weak_topics": [],
        "mastered_topics": [],
        "recent_activity": [],
        "notes": [],
        "course_memory": {},
    }


def _empty_scope() -> Dict[str, Any]:
    return {
        "weak_topics": [],
        "mastered_topics": [],
        "recent_activity": [],
        "notes": [],
    }


def _normalize_topic_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_note(item: Any) -> Dict[str, Any]:
    if isinstance(item, str):
        return {"text": item.strip(), "created_at": None}
    if isinstance(item, Mapping):
        return {
            "text": str(item.get("text", "")).strip(),
            "created_at": item.get("created_at"),
        }
    return {"text": "", "created_at": None}


def _normalize_activity(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, Mapping):
        return None
    question = str(item.get("question", "")).strip()
    if not question:
        return None
    return {
        "mode": str(item.get("mode", "Academic Study")).strip(),
        "question": question,
        "topic": str(item.get("topic", "")).strip(),
        "time": item.get("time"),
    }


def _normalize_scope(scope: Any) -> Dict[str, Any]:
    if not isinstance(scope, Mapping):
        scope = {}

    weak = []
    for value in scope.get("weak_topics", []):
        topic = _normalize_topic_text(value)
        if topic and topic.casefold() not in {item.casefold() for item in weak}:
            weak.append(topic)

    mastered = []
    for value in scope.get("mastered_topics", []):
        topic = _normalize_topic_text(value)
        if topic and topic.casefold() not in {item.casefold() for item in mastered}:
            mastered.append(topic)

    weak_names = {item.casefold() for item in weak}
    mastered = [item for item in mastered if item.casefold() not in weak_names]

    activities = []
    for item in scope.get("recent_activity", []):
        activity = _normalize_activity(item)
        if activity:
            activities.append(activity)

    notes = []
    for item in scope.get("notes", []):
        note = _normalize_note(item)
        if note["text"]:
            notes.append(note)

    return {
        "weak_topics": weak[-MAX_WEAK_TOPICS:],
        "mastered_topics": mastered[-MAX_MASTERED_TOPICS:],
        "recent_activity": activities[-MAX_RECENT_ACTIVITY:],
        "notes": notes[-MAX_NOTES:],
    }


def _normalize_memory(data: Any) -> Dict[str, Any]:
    if not isinstance(data, Mapping):
        return _default_memory()

    global_scope = _normalize_scope(data)
    course_memory: Dict[str, Any] = {}
    raw_course_memory = data.get("course_memory", {})
    if isinstance(raw_course_memory, Mapping):
        for course_id, scope in raw_course_memory.items():
            clean_id = str(course_id).strip()
            if clean_id:
                course_memory[clean_id] = _normalize_scope(scope)

    return {
        "version": MEMORY_VERSION,
        "weak_topics": global_scope["weak_topics"],
        "mastered_topics": global_scope["mastered_topics"],
        "recent_activity": global_scope["recent_activity"],
        "notes": global_scope["notes"],
        "course_memory": course_memory,
    }


def _normalize_status(value: Any) -> str:
    status = _normalize_topic_text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "in_progress": "learning",
        "incomplete": "not_started",
        "done": "mastered",
    }
    status = aliases.get(status, status)
    return status if status in VALID_TOPIC_STATUSES else "not_started"


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "course"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
    os.replace(str(temporary), str(path))


class LegacyJsonLearningProgressRepository:
    """Explicit legacy authority for Phase 4.6 persisted reads.

    Missing sources return the same default values as the current legacy APIs,
    but unlike ``learning_memory.load_memory`` this adapter never creates a
    missing file during a parity read.
    """

    def __init__(
        self,
        memory_path: Optional[Union[str, Path]] = None,
        progress_path: Optional[Union[str, Path]] = None,
        courses_path: Optional[Union[str, Path]] = None,
    ):
        self.memory_path = Path(memory_path or "data/learning_memory.json")
        self.progress_path = Path(progress_path or "data/course_progress_history.json")
        self.courses_path = Path(courses_path or "data/courses.json")

    def load_memory(self) -> Dict[str, Any]:
        data = _load_json(self.memory_path)
        return _normalize_memory(data)

    def load_progress_history(self) -> Dict[str, Any]:
        data = _load_json(self.progress_path)
        if not isinstance(data, Mapping):
            return {"version": HISTORY_VERSION, "courses": {}}
        courses = data.get("courses")
        if not isinstance(courses, Mapping):
            courses = {}
        return {
            "version": HISTORY_VERSION,
            "courses": deepcopy(dict(courses)),
        }

    def load_raw_memory_source(self) -> Any:
        return deepcopy(_load_json(self.memory_path))

    def load_raw_progress_source(self) -> Any:
        return deepcopy(_load_json(self.progress_path))

    def load_current_progress_state(self) -> Dict[str, Any]:
        """Mirror current course/topic progress semantics without writing.

        ``academic_progress`` gets current topic status/confidence through
        ``course_manager``.  Phase 4.6 reads the same persisted ``courses.json``
        shape directly so the parity path cannot trigger any writer.
        """
        data = _load_json(self.courses_path)
        if not isinstance(data, Mapping):
            data = {}

        used_ids = set()
        courses = []
        summaries: Dict[str, Any] = {}
        for raw_course in data.get("courses", []):
            if not isinstance(raw_course, Mapping):
                continue
            code = _normalize_topic_text(raw_course.get("code")).upper()
            name = _normalize_topic_text(raw_course.get("name"))
            course_id = _normalize_topic_text(raw_course.get("id")) or _slug(code or name)
            original_id = course_id
            suffix = 2
            while course_id in used_ids:
                course_id = "{}-{}".format(original_id, suffix)
                suffix += 1
            used_ids.add(course_id)

            topics = []
            seen = set()
            for raw_topic in raw_course.get("topics", []):
                if isinstance(raw_topic, str):
                    raw_topic = {"name": raw_topic}
                if not isinstance(raw_topic, Mapping):
                    continue
                topic_name = _normalize_topic_text(raw_topic.get("name"))
                key = topic_name.casefold()
                if not topic_name or key in seen:
                    continue
                seen.add(key)
                try:
                    confidence = int(raw_topic.get("confidence", 0))
                except (TypeError, ValueError):
                    confidence = 0
                confidence = max(0, min(5, confidence))
                topics.append(
                    {
                        "name": topic_name,
                        "status": _normalize_status(raw_topic.get("status")),
                        "confidence": confidence,
                        "last_updated": raw_topic.get("last_updated"),
                    }
                )

            course = {
                "id": course_id,
                "code": code,
                "name": name,
                "topics": topics,
            }
            courses.append(course)

            counts = {status: 0 for status in VALID_TOPIC_STATUSES}
            for topic in topics:
                counts[topic["status"]] += 1
            total = len(topics)
            mastered = counts["mastered"]
            summaries[course_id] = {
                "total_topics": total,
                "mastered_topics": mastered,
                "progress_percent": round((mastered / total) * 100) if total else 0,
                "counts": counts,
                "weak_topics": [item["name"] for item in topics if item["status"] == "weak"],
                "missing_topics": [
                    item["name"] for item in topics if item["status"] == "not_started"
                ],
            }

        return {
            "version": COURSE_DATA_VERSION,
            "courses": courses,
            "summaries": summaries,
        }

    def load_state(self) -> Dict[str, Any]:
        return {
            "memory": self.load_memory(),
            "progress_history": self.load_progress_history(),
            "current_progress": self.load_current_progress_state(),
        }

    def save_memory(self, memory: Mapping[str, Any]) -> None:
        _write_json_atomic(self.memory_path, _normalize_memory(memory))

    def save_progress_history(self, history: Mapping[str, Any]) -> None:
        courses = history.get("courses", {}) if isinstance(history, Mapping) else {}
        if not isinstance(courses, Mapping):
            courses = {}
        _write_json_atomic(
            self.progress_path,
            {"version": HISTORY_VERSION, "courses": deepcopy(dict(courses))},
        )


__all__ = ("LegacyJsonLearningProgressRepository",)
