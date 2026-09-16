"""Read-only Progress & Planning adapter for the local web interface.

Phase 7.5.5 projects existing course-progress evidence and saved study plans
into a browser-friendly model. Heavy progress/planner modules are imported only
when the Planning page is requested, and this adapter never records snapshots
or generates/stores plans.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Mapping


PLAN_SPECS = (
    ("weekly", "Latest course weekly plan"),
    ("multi", "Latest multi-course plan"),
    ("intelligent", "Latest intelligent study plan"),
)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _status_label(value: Any) -> str:
    text = str(value or "not_started").strip().lower().replace("-", "_")
    return text.replace("_", " ").capitalize()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_priority(raw: Any) -> dict[str, Any]:
    reasons = _string_list(_value(raw, "priority_reasons", []))
    status = str(_value(raw, "status", "not_started") or "not_started")
    return {
        "name": str(_value(raw, "name", "Unnamed topic") or "Unnamed topic"),
        "status": status,
        "status_label": _status_label(status),
        "confidence": max(0, min(_integer(_value(raw, "confidence", 0)), 5)),
        "score": _number(_value(raw, "priority_score", 0)),
        "reasons": reasons,
    }


def _normalize_course(
    raw_course: Any,
    trend_provider: Callable[[str], Any],
    priority_provider: Callable[..., Any],
) -> dict[str, Any]:
    course_id = str(_value(raw_course, "id", "") or "")
    trend = trend_provider(course_id) or {}
    current = _value(trend, "current", {}) or {}
    priorities = priority_provider(course_id, limit=5) or []

    return {
        "id": course_id,
        "code": str(_value(raw_course, "code", "") or "UNKNOWN"),
        "name": str(_value(raw_course, "name", "") or "Unknown course"),
        "progress_percent": round(_number(_value(current, "progress_percent", 0)), 1),
        "mastered_topics": _integer(_value(current, "mastered_topics", 0)),
        "total_topics": _integer(_value(current, "total_topics", 0)),
        "average_confidence": round(_number(_value(current, "average_confidence", 0)), 2),
        "weak_topics": _string_list(_value(current, "weak_topics", [])),
        "missing_topics": _string_list(_value(current, "missing_topics", [])),
        "delta_progress": round(_number(_value(trend, "delta_progress", 0)), 1),
        "delta_mastered": _integer(_value(trend, "delta_mastered", 0)),
        "has_history": _value(trend, "previous") is not None,
        "priorities": [_normalize_priority(item) for item in priorities[:5]],
    }


def _extract_sessions(plan: Mapping[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    days = plan.get("days", [])
    if isinstance(days, list):
        for day in days:
            if not isinstance(day, dict):
                continue
            day_date = str(day.get("date") or "")
            raw_sessions = day.get("sessions", [])
            if not isinstance(raw_sessions, list):
                continue
            for raw in raw_sessions:
                if not isinstance(raw, dict):
                    continue
                sessions.append(
                    {
                        "date": day_date,
                        "course_code": str(raw.get("course_code") or ""),
                        "course_name": str(raw.get("course_name") or ""),
                        "topic": str(raw.get("topic") or "Study session"),
                        "status_label": _status_label(raw.get("status")) if raw.get("status") else "",
                        "minutes": max(0, _integer(raw.get("minutes"), 0)),
                    }
                )
                if len(sessions) >= limit:
                    return sessions

    if sessions:
        return sessions

    raw_sessions = plan.get("sessions", [])
    if isinstance(raw_sessions, list):
        for raw in raw_sessions:
            if not isinstance(raw, dict):
                continue
            sessions.append(
                {
                    "date": str(raw.get("date") or ""),
                    "course_code": str(raw.get("course_code") or ""),
                    "course_name": str(raw.get("course_name") or ""),
                    "topic": str(raw.get("topic") or "Study session"),
                    "status_label": _status_label(raw.get("status")) if raw.get("status") else "",
                    "minutes": max(0, _integer(raw.get("minutes"), 0)),
                }
            )
            if len(sessions) >= limit:
                break
    return sessions


def _total_minutes(plan: Mapping[str, Any], sessions: list[dict[str, Any]]) -> int:
    for key in ("total_minutes", "weekly_minutes"):
        value = _integer(plan.get(key), -1)
        if value >= 0:
            return value

    days = plan.get("days", [])
    if isinstance(days, list):
        totals = [
            max(0, _integer(day.get("total_minutes"), 0))
            for day in days
            if isinstance(day, dict) and day.get("total_minutes") not in (None, "")
        ]
        if totals:
            return sum(totals)

    return sum(item["minutes"] for item in sessions)


def _course_label(plan: Mapping[str, Any], sessions: list[dict[str, Any]]) -> str:
    code = str(plan.get("course_code") or "").strip()
    name = str(plan.get("course_name") or "").strip()
    if code and name:
        return f"{code} · {name}"
    if code or name:
        return code or name

    codes: list[str] = []
    for session in sessions:
        value = session.get("course_code", "")
        if value and value not in codes:
            codes.append(value)
    return " + ".join(codes) if codes else "Multiple courses"


def _normalize_plan(key: str, title: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        return {
            "key": key,
            "title": title,
            "exists": False,
            "created_at": "",
            "start_date": "",
            "course_label": "",
            "total_minutes": 0,
            "study_days": 0,
            "message": "",
            "sessions": [],
        }

    sessions = _extract_sessions(raw)
    days = raw.get("days", [])
    day_count = len(days) if isinstance(days, list) else 0
    study_days = _integer(raw.get("study_days"), day_count)

    return {
        "key": key,
        "title": title,
        "exists": True,
        "created_at": str(raw.get("created_at") or ""),
        "start_date": str(raw.get("start_date") or ""),
        "course_label": _course_label(raw, sessions),
        "total_minutes": _total_minutes(raw, sessions),
        "study_days": max(0, study_days),
        "message": str(raw.get("message") or ""),
        "sessions": sessions,
    }


def build_planning_dashboard(
    course_result: Any,
    trend_provider: Callable[[str], Any],
    priority_provider: Callable[..., Any],
    saved_plans: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Normalize read-only progress evidence and already-saved plans."""
    courses = [
        _normalize_course(course, trend_provider, priority_provider)
        for course in tuple(_value(course_result, "courses", ()) or ())
    ]
    plan_source = saved_plans or {}
    plans = [
        _normalize_plan(key, title, plan_source.get(key))
        for key, title in PLAN_SPECS
    ]

    average_progress = 0.0
    if courses:
        average_progress = round(
            sum(course["progress_percent"] for course in courses) / len(courses),
            1,
        )

    return {
        "available": True,
        "message": "",
        "summary": {
            "courses": len(courses),
            "average_progress": average_progress,
            "mastered_topics": sum(course["mastered_topics"] for course in courses),
            "weak_topics": sum(len(course["weak_topics"]) for course in courses),
            "missing_topics": sum(len(course["missing_topics"]) for course in courses),
            "saved_plans": sum(1 for plan in plans if plan["exists"]),
        },
        "courses": courses,
        "plans": plans,
    }


def _load_course_result():
    service_module = import_module("personal_learning_assistant.services.course_service")
    repository_module = import_module(
        "personal_learning_assistant.repositories.routed_course_repository"
    )
    service = service_module.CourseService(repository_module.RoutedCourseRepository())
    return service.list_courses()


def _load_saved_plans() -> dict[str, Any]:
    weekly_module = import_module("weekly_planner")
    multi_module = import_module("multi_course_planner")
    intelligent_module = import_module("intelligent_study_planner")

    weekly_plans = weekly_module.get_saved_plans()
    latest_weekly = weekly_plans[-1] if isinstance(weekly_plans, list) and weekly_plans else None

    return {
        "weekly": latest_weekly,
        "multi": multi_module.latest_plan(),
        "intelligent": intelligent_module.latest_plan(),
    }


def load_planning_dashboard() -> dict[str, Any]:
    """Read current progress and saved plans without generating or recording data."""
    progress_module = import_module("academic_progress")
    return build_planning_dashboard(
        _load_course_result(),
        progress_module.get_progress_trend,
        progress_module.rank_course_topics,
        _load_saved_plans(),
    )


def unavailable_planning_dashboard() -> dict[str, Any]:
    """Return a safe degraded model when planning reads are unavailable."""
    return {
        "available": False,
        "message": (
            "Progress and planning are temporarily unavailable. "
            "Your academic data was not changed."
        ),
        "summary": {
            "courses": 0,
            "average_progress": 0.0,
            "mastered_topics": 0,
            "weak_topics": 0,
            "missing_topics": 0,
            "saved_plans": 0,
        },
        "courses": [],
        "plans": [],
    }
