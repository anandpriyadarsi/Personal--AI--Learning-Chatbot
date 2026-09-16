"""Read-only Assessments adapter for the local web interface.

Phase 7.5.4 keeps browser reads behind the existing structured-authority
repository boundary. Assessment and course storage modules are imported only
when the Assessments page is actually requested.
"""

from __future__ import annotations

from datetime import date, datetime
from importlib import import_module
from typing import Any


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_float(value: Any):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status_label(value: Any) -> str:
    text = str(value or "pending").strip().lower().replace("-", "_")
    return text.replace("_", " ").capitalize()


def _type_label(value: Any) -> str:
    text = str(value or "assessment").strip().lower().replace("-", "_")
    return text.replace("_", " ").title()


def _parse_date(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _due_details(value: Any, today: date) -> tuple[str, int | None]:
    parsed = _parse_date(value)
    if parsed is None:
        return "Date not set", None
    days = (parsed - today).days
    if days < 0:
        count = abs(days)
        return f"Overdue by {count} day" + ("s" if count != 1 else ""), days
    if days == 0:
        return "Due today", 0
    if days == 1:
        return "Due tomorrow", 1
    return f"Due in {days} days", days


def _course_index(course_result: Any) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for course in tuple(_value(course_result, "courses", ()) or ()):
        course_id = str(_value(course, "id", "") or "")
        if not course_id:
            continue
        result[course_id] = {
            "code": str(_value(course, "code", "") or "UNKNOWN"),
            "name": str(_value(course, "name", "") or "Unknown course"),
        }
    return result


def build_assessment_catalogue(
    state: Any,
    course_result: Any,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Normalize authoritative assessment state into a template read model."""
    today = today or date.today()
    courses = _course_index(course_result)
    groups: dict[str, list[dict[str, Any]]] = {
        "overdue": [],
        "upcoming": [],
        "completed": [],
    }

    raw_items = _value(state, "assessments", [])
    if not isinstance(raw_items, (list, tuple)):
        raw_items = []

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        assessment_id = str(raw.get("id", "") or "")
        course_id = str(raw.get("course_id", "") or "")
        course = courses.get(course_id, {"code": "UNKNOWN", "name": "Unknown course"})
        status = str(raw.get("status") or "pending").strip().lower().replace("-", "_")
        due_date = raw.get("due_date", raw.get("due_on", ""))
        due_label, days_until = _due_details(due_date, today)
        assessment_type = raw.get("type", raw.get("assessment_type", "assessment"))
        weightage = _as_float(raw.get("weightage_percent", raw.get("weight")))
        topics_value = raw.get("topics", [])
        topics = (
            [str(item).strip() for item in topics_value if str(item).strip()]
            if isinstance(topics_value, list)
            else []
        )

        item = {
            "id": assessment_id,
            "course_id": course_id,
            "course_code": course["code"],
            "course_name": course["name"],
            "type": str(assessment_type or "assessment"),
            "type_label": _type_label(assessment_type),
            "title": str(raw.get("title") or "Untitled assessment"),
            "status": status,
            "status_label": _status_label(status),
            "due_date": str(due_date or ""),
            "due_time": str(raw.get("due_time") or ""),
            "due_label": due_label,
            "days_until": days_until,
            "weightage_percent": weightage,
            "weightage_label": f"{weightage:g}" if weightage is not None else None,
            "total_marks": _as_float(raw.get("total_marks", raw.get("max_score"))),
            "obtained_marks": _as_float(raw.get("obtained_marks", raw.get("score"))),
            "topics": topics,
        }

        if status == "completed":
            groups["completed"].append(item)
        elif days_until is not None and days_until < 0:
            groups["overdue"].append(item)
        else:
            groups["upcoming"].append(item)

    groups["overdue"].sort(
        key=lambda item: (item["days_until"] if item["days_until"] is not None else 0, item["title"])
    )
    groups["upcoming"].sort(
        key=lambda item: (
            item["days_until"] is None,
            item["days_until"] if item["days_until"] is not None else 10**9,
            item["title"],
        )
    )
    groups["completed"].sort(
        key=lambda item: (item["due_date"] or "0000-00-00", item["title"]),
        reverse=True,
    )

    total = sum(len(items) for items in groups.values())
    completed = len(groups["completed"])
    return {
        "available": True,
        "message": "",
        "date": today.isoformat(),
        "summary": {
            "total": total,
            "active": total - completed,
            "overdue": len(groups["overdue"]),
            "completed": completed,
        },
        "groups": groups,
    }


def _load_authoritative_assessment_state() -> dict[str, Any]:
    """Read assessments through the existing Phase 4.11 authority router."""
    legacy_module = import_module(
        "personal_learning_assistant.repositories.json.assessment_repository"
    )
    router = import_module(
        "personal_learning_assistant.repositories.structured_authority_router"
    )
    legacy = legacy_module.LegacyJsonAssessmentRepository()
    routed = router.maybe_load_sqlite_structured_store(
        router.STORE_ASSESSMENTS,
        legacy.path,
    )
    return routed if routed is not None else legacy.load_state()


def _load_course_result():
    service_module = import_module("personal_learning_assistant.services.course_service")
    repository_module = import_module(
        "personal_learning_assistant.repositories.routed_course_repository"
    )
    service = service_module.CourseService(repository_module.RoutedCourseRepository())
    return service.list_courses()


def load_assessment_catalogue() -> dict[str, Any]:
    """Read current assessments and course identities without browser writes."""
    return build_assessment_catalogue(
        _load_authoritative_assessment_state(),
        _load_course_result(),
    )


def unavailable_assessment_catalogue() -> dict[str, Any]:
    """Return a safe degraded model when assessment reads are unavailable."""
    return {
        "available": False,
        "message": "Assessments are temporarily unavailable. Your academic data was not changed.",
        "date": None,
        "summary": {
            "total": 0,
            "active": 0,
            "overdue": 0,
            "completed": 0,
        },
        "groups": {
            "overdue": [],
            "upcoming": [],
            "completed": [],
        },
    }
