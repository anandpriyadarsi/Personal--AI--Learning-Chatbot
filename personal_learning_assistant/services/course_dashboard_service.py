"""Read-only Courses/Topics adapter for the local web interface.

Phase 7.5.3 keeps the browser layer behind the existing CourseService and
RoutedCourseRepository boundaries. Heavy course/storage modules are imported
only when the Courses page is actually requested.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _confidence(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(5, parsed))


def _status_label(value: Any) -> str:
    text = str(value or "not_started").strip().lower().replace("-", "_")
    return text.replace("_", " ").capitalize()


def build_course_catalogue_from_result(result: Any) -> dict[str, Any]:
    """Normalize CourseService.list_courses() output for Jinja rendering."""
    active_course_id = _value(result, "active_course_id")
    courses = []
    total_topics = 0
    mastered_topics = 0
    weak_topics = 0

    for course in tuple(_value(result, "courses", ()) or ()):
        topics = []
        course_mastered = 0
        for topic in tuple(_value(course, "topics", ()) or ()):
            status = str(_value(topic, "status", "not_started") or "not_started")
            if status == "mastered":
                mastered_topics += 1
                course_mastered += 1
            if status == "weak":
                weak_topics += 1
            topics.append(
                {
                    "name": str(_value(topic, "name", "") or "Untitled topic"),
                    "status": status,
                    "status_label": _status_label(status),
                    "confidence": _confidence(_value(topic, "confidence", 0)),
                    "last_updated": _value(topic, "last_updated"),
                }
            )

        topic_count = len(topics)
        total_topics += topic_count
        progress_percent = round((course_mastered / topic_count) * 100) if topic_count else 0
        course_id = str(_value(course, "id", "") or "")
        course_status = str(_value(course, "status", "active") or "active")
        courses.append(
            {
                "id": course_id,
                "code": str(_value(course, "code", "") or "COURSE"),
                "name": str(_value(course, "name", "") or "Unnamed course"),
                "semester": str(_value(course, "semester", "") or ""),
                "status": course_status,
                "status_label": _status_label(course_status),
                "is_active": bool(active_course_id and course_id == str(active_course_id)),
                "topic_count": topic_count,
                "mastered_count": course_mastered,
                "progress_percent": progress_percent,
                "topics": topics,
            }
        )

    return {
        "available": True,
        "message": "",
        "active_course_id": active_course_id,
        "summary": {
            "courses": len(courses),
            "topics": total_topics,
            "mastered_topics": mastered_topics,
            "weak_topics": weak_topics,
        },
        "courses": courses,
    }


def load_course_catalogue() -> dict[str, Any]:
    """Read the current course catalogue through existing service boundaries."""
    service_module = import_module("personal_learning_assistant.services.course_service")
    repository_module = import_module(
        "personal_learning_assistant.repositories.routed_course_repository"
    )
    service = service_module.CourseService(repository_module.RoutedCourseRepository())
    return build_course_catalogue_from_result(service.list_courses())


def unavailable_course_catalogue() -> dict[str, Any]:
    """Return a safe degraded model when the course read cannot be completed."""
    return {
        "available": False,
        "message": "Courses are temporarily unavailable. Your academic data was not changed.",
        "active_course_id": None,
        "summary": {
            "courses": 0,
            "topics": 0,
            "mastered_topics": 0,
            "weak_topics": 0,
        },
        "courses": [],
    }
