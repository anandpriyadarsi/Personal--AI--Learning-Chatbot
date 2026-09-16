"""Read-only Calendar & Grades adapter for the local web interface.

Phase 7.5.6 projects existing academic-deadline and grade evidence into a
browser-friendly model. Grade/calendar repositories and course services are
imported only when the page is requested. This module performs no writes,
predictions, grade inference, calendar mutation, migration, or authority change.
"""

from __future__ import annotations

from datetime import date, datetime
from importlib import import_module
from typing import Any


CALENDAR_WINDOW_DAYS = 30


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_float(value: Any):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    return token in {"1", "true", "yes", "verified", "official"}


def _status_label(value: Any) -> str:
    text = str(value or "pending").strip().lower().replace("-", "_")
    return text.replace("_", " ").capitalize()


def _type_label(value: Any) -> str:
    text = str(value or "academic event").strip().lower().replace("-", "_")
    return text.replace("_", " ").title()


def _parse_date(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _course_index(course_result: Any) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for course in tuple(_value(course_result, "courses", ()) or ()):
        course_id = str(_value(course, "id", "") or "").strip()
        code = str(_value(course, "code", "") or "").strip()
        name = str(_value(course, "name", "") or "").strip()
        item = {
            "id": course_id,
            "code": code or course_id or "UNKNOWN",
            "name": name or "Unknown course",
        }
        if course_id:
            result[course_id] = item
            result[course_id.casefold()] = item
        if code:
            result[code] = item
            result[code.casefold()] = item
    return result


def _course_identity(raw_id: Any, courses: dict[str, dict[str, str]]) -> dict[str, str]:
    text = str(raw_id or "").strip()
    match = courses.get(text) or courses.get(text.casefold())
    if match:
        return match
    return {
        "id": text,
        "code": text or "UNKNOWN",
        "name": "Unknown course",
    }


def _normalize_scale(config: dict[str, Any]) -> dict[str, Any]:
    bands = []
    raw_bands = config.get("grade_scale", [])
    if isinstance(raw_bands, list):
        for raw in raw_bands:
            if not isinstance(raw, dict):
                continue
            letter = str(
                raw.get("letter", raw.get("letter_grade", raw.get("grade", ""))) or ""
            ).strip()
            minimum = _as_float(
                raw.get(
                    "min_score",
                    raw.get("minimum_score", raw.get("minimum_percent")),
                )
            )
            point = _as_float(raw.get("grade_point", raw.get("point", raw.get("gp"))))
            if not letter and minimum is None and point is None:
                continue
            bands.append(
                {
                    "letter": letter or "?",
                    "minimum_score": minimum,
                    "grade_point": point,
                }
            )

    bands.sort(
        key=lambda item: (
            item["minimum_score"] is None,
            -(item["minimum_score"] or 0.0),
            item["letter"],
        )
    )
    source = str(
        config.get("grade_scale_source", config.get("scale_source", "")) or ""
    ).strip()
    verified = _as_bool(
        config.get(
            "grade_scale_verified",
            config.get("scale_verified", config.get("verified", False)),
        )
    )
    return {
        "source": source,
        "verified": verified,
        "bands": bands,
    }


def _normalize_grade_course(
    raw: dict[str, Any],
    courses: dict[str, dict[str, str]],
) -> dict[str, Any]:
    raw_id = str(
        raw.get("course_id", raw.get("course_code", raw.get("code", ""))) or ""
    ).strip()
    course = _course_identity(raw_id, courses)
    credits = _as_float(raw.get("credits", raw.get("credit", raw.get("course_credits"))))
    score = _as_float(
        raw.get("manual_score", raw.get("score_percent", raw.get("score")))
    )
    letter = str(
        raw.get("manual_letter_grade", raw.get("letter_grade", "")) or ""
    ).strip() or None
    grade_point = _as_float(raw.get("manual_grade_point", raw.get("grade_point")))
    has_recorded = score is not None or letter is not None or grade_point is not None
    return {
        "id": raw_id,
        "course_id": course["id"] or raw_id,
        "code": course["code"],
        "name": course["name"],
        "credits": credits,
        "score": score,
        "letter_grade": letter,
        "grade_point": grade_point,
        "has_recorded_grade": has_recorded,
    }


def _normalize_semester_result(config: dict[str, Any]):
    raw = config.get("semester_result")
    if raw is None:
        raw = config.get("semester_results")
        if isinstance(raw, list):
            raw = raw[0] if len(raw) == 1 else None
    if not isinstance(raw, dict):
        return None

    sgpa = _as_float(raw.get("sgpa"))
    earned_credits = _as_float(raw.get("earned_credits", raw.get("credits_earned")))
    earned_points = _as_float(
        raw.get("earned_grade_points", raw.get("total_grade_points"))
    )
    source = str(raw.get("source") or "").strip()
    verified = _as_bool(raw.get("verified", False))

    if (
        sgpa is None
        and earned_credits is None
        and earned_points is None
        and not source
        and not verified
    ):
        return None
    return {
        "sgpa": sgpa,
        "earned_credits": earned_credits,
        "earned_grade_points": earned_points,
        "verified": verified,
        "source": source,
    }


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


def _normalize_event(
    raw: dict[str, Any],
    courses: dict[str, dict[str, str]],
    today: date,
) -> dict[str, Any]:
    course_id = str(raw.get("course_id") or "").strip()
    course = _course_identity(course_id, courses)
    status = str(raw.get("status") or "pending").strip().lower().replace("-", "_")
    due_date = str(raw.get("due_date", raw.get("due_on", "")) or "").strip()
    due_label, days_until = _due_details(due_date, today)
    event_type = raw.get("type", raw.get("assessment_type", "academic event"))
    weightage = _as_float(raw.get("weightage_percent", raw.get("weight")))
    return {
        "id": str(raw.get("id") or "").strip(),
        "course_id": course_id,
        "course_code": course["code"],
        "course_name": course["name"],
        "title": str(raw.get("title") or "Untitled academic event"),
        "type": str(event_type or "academic event"),
        "type_label": _type_label(event_type),
        "status": status,
        "status_label": _status_label(status),
        "due_date": due_date,
        "due_time": str(raw.get("due_time") or "").strip(),
        "due_label": due_label,
        "days_until": days_until,
        "weightage_percent": weightage,
    }


def _event_group(item: dict[str, Any]) -> str:
    if item["status"] == "completed":
        return "completed"
    days = item["days_until"]
    if days is not None and days < 0:
        return "overdue"
    if days is not None and days <= CALENDAR_WINDOW_DAYS:
        return "upcoming"
    return "later"


def build_calendar_grades_dashboard(
    grade_config: Any,
    assessment_state: Any,
    course_result: Any,
    *,
    today: date | None = None,
    grade_source_present: bool = True,
) -> dict[str, Any]:
    """Normalize existing grade and calendar evidence without any mutation."""
    today = today or date.today()
    courses = _course_index(course_result)

    config = grade_config if isinstance(grade_config, dict) else {}
    grade_courses = []
    scale = {"source": "", "verified": False, "bands": []}
    result = None
    semester_name = ""
    target_sgpa = None

    if grade_source_present:
        semester_name = str(
            config.get("semester_name", config.get("semester", "")) or ""
        ).strip()
        target_sgpa = _as_float(config.get("target_sgpa", config.get("sgpa_target")))
        scale = _normalize_scale(config)
        raw_courses = config.get("courses", [])
        if isinstance(raw_courses, list):
            grade_courses = [
                _normalize_grade_course(raw, courses)
                for raw in raw_courses
                if isinstance(raw, dict)
            ]
        result = _normalize_semester_result(config)

    groups: dict[str, list[dict[str, Any]]] = {
        "overdue": [],
        "upcoming": [],
        "later": [],
        "completed": [],
    }
    raw_assessments = _value(assessment_state, "assessments", [])
    if not isinstance(raw_assessments, (list, tuple)):
        raw_assessments = []
    for raw in raw_assessments:
        if not isinstance(raw, dict):
            continue
        item = _normalize_event(raw, courses, today)
        groups[_event_group(item)].append(item)

    groups["overdue"].sort(
        key=lambda item: (
            item["days_until"] if item["days_until"] is not None else 0,
            item["title"],
        )
    )
    groups["upcoming"].sort(
        key=lambda item: (
            item["days_until"] is None,
            item["days_until"] if item["days_until"] is not None else 10**9,
            item["title"],
        )
    )
    groups["later"].sort(
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

    calendar_events = sum(len(items) for items in groups.values())
    recorded_grades = sum(
        1 for item in grade_courses if item["has_recorded_grade"]
    )

    return {
        "available": True,
        "message": "",
        "date": today.isoformat(),
        "summary": {
            "calendar_events": calendar_events,
            "overdue": len(groups["overdue"]),
            "upcoming": len(groups["upcoming"]),
            "grade_courses": len(grade_courses),
            "recorded_grades": recorded_grades,
        },
        "calendar": {
            "window_days": CALENDAR_WINDOW_DAYS,
            "groups": groups,
        },
        "grades": {
            "source_present": bool(grade_source_present),
            "semester_name": semester_name,
            "target_sgpa": target_sgpa,
            "scale": scale,
            "courses": grade_courses,
            "semester_result": result,
        },
    }


def _load_course_result():
    service_module = import_module("personal_learning_assistant.services.course_service")
    repository_module = import_module(
        "personal_learning_assistant.repositories.routed_course_repository"
    )
    service = service_module.CourseService(repository_module.RoutedCourseRepository())
    return service.list_courses()


def _load_authoritative_state() -> tuple[dict[str, Any], dict[str, Any], bool]:
    legacy_module = import_module(
        "personal_learning_assistant.repositories.json.grade_calendar_repository"
    )
    router = import_module(
        "personal_learning_assistant.repositories.structured_authority_router"
    )

    legacy = legacy_module.LegacyJsonGradeCalendarRepository()

    grade_config = router.maybe_load_sqlite_structured_store(
        router.STORE_GRADE_CONFIG,
        legacy.grade_config_path,
    )
    if grade_config is None:
        grade_config = legacy.load_grade_config()

    assessment_state = router.maybe_load_sqlite_structured_store(
        router.STORE_ASSESSMENTS,
        legacy.assessments_path,
    )
    if assessment_state is None:
        assessment_state = legacy.load_assessment_store()

    return grade_config, assessment_state, legacy.grade_source_present()


def load_calendar_grades_dashboard() -> dict[str, Any]:
    """Read current authority-routed grades and deadlines without browser writes."""
    grade_config, assessment_state, grade_source_present = _load_authoritative_state()
    return build_calendar_grades_dashboard(
        grade_config,
        assessment_state,
        _load_course_result(),
        grade_source_present=grade_source_present,
    )


def unavailable_calendar_grades_dashboard() -> dict[str, Any]:
    """Return a safe degraded model when grade/calendar reads are unavailable."""
    return {
        "available": False,
        "message": (
            "Calendar and grades are temporarily unavailable. "
            "Your academic data was not changed."
        ),
        "date": None,
        "summary": {
            "calendar_events": 0,
            "overdue": 0,
            "upcoming": 0,
            "grade_courses": 0,
            "recorded_grades": 0,
        },
        "calendar": {
            "window_days": CALENDAR_WINDOW_DAYS,
            "groups": {
                "overdue": [],
                "upcoming": [],
                "later": [],
                "completed": [],
            },
        },
        "grades": {
            "source_present": False,
            "semester_name": "",
            "target_sgpa": None,
            "scale": {"source": "", "verified": False, "bands": []},
            "courses": [],
            "semester_result": None,
        },
    }


__all__ = (
    "CALENDAR_WINDOW_DAYS",
    "build_calendar_grades_dashboard",
    "load_calendar_grades_dashboard",
    "unavailable_calendar_grades_dashboard",
)
