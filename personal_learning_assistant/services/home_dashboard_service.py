"""Read-only Home dashboard adapter for the local web interface.

Phase 7.5.2 deliberately keeps the browser layer away from storage.  The
adapter lazily loads the existing Daily Academic Brief read model and converts
its output into a small template-friendly structure.  Importing this module has
no academic-data side effects.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


def _unique_text(values, *, limit: int) -> list[str]:
    result: list[str] = []
    for value in values or ():
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _course_code(brief: Any, item: dict[str, Any]) -> str:
    value = brief._course_code(item)
    return str(value or "COURSE")


def build_home_dashboard_from_brief(brief: Any) -> dict[str, Any]:
    """Normalize the existing Daily Academic Brief into a web read model."""
    urgent = list(brief._urgent_assessments())
    blocks = list(brief._today_blocks())
    risks = list(brief._top_risks(limit=3))
    tasks = list(brief._brief_actions())

    deadlines = []
    for item in urgent[:5]:
        weightage = _as_float(brief.assessment_weightage_percent(item))
        deadlines.append(
            {
                "course_code": _course_code(brief, item),
                "title": str(item.get("title") or "Untitled assessment"),
                "due_label": str(brief._due_label(item)),
                "weightage_percent": weightage,
            }
        )

    study_blocks = []
    study_minutes_by_course = {}
    for block in blocks:
        code = _course_code(brief, dict(block.get("assessment") or {}))
        study_minutes_by_course[code] = (
            study_minutes_by_course.get(code, 0) + int(block.get("minutes") or 0)
        )
    for block in blocks[:6]:
        item = dict(block.get("assessment") or {})
        minutes = int(block.get("minutes") or 0)
        study_blocks.append(
            {
                "course_code": _course_code(brief, item),
                "title": str(item.get("title") or "Untitled assessment"),
                "minutes": minutes,
                "label": str(block.get("label") or "Study block"),
                "due_label": str(brief._due_label(item)),
            }
        )

    priorities = []
    for task in tasks[:5]:
        performance = task.get("performance") or None
        priorities.append(
            {
                "course_code": str(task.get("course_code") or "COURSE"),
                "topic": str(task.get("topic") or "Study priority"),
                "score": _as_float(task.get("score")) or 0.0,
                "reasons": _unique_text(task.get("reasons"), limit=3),
                "performance": dict(performance) if isinstance(performance, dict) else None,
            }
        )

    meaningful_risks = []
    for row in risks:
        score = _as_float(row.get("score")) or 0.0
        if score <= 0:
            continue
        course = dict(row.get("course") or {})
        evidence_topics = [
            item.get("topic")
            for item in (row.get("evidence") or [])
            if isinstance(item, dict)
        ]
        meaningful_risks.append(
            {
                "course_code": str(course.get("code") or "COURSE"),
                "course_name": str(course.get("name") or "Course"),
                "score": score,
                "weak_topics": _unique_text(row.get("weak_topics"), limit=2),
                "evidence_topics": _unique_text(evidence_topics, limit=2),
                "urgent_count": len(row.get("urgent") or []),
            }
        )

    best_next_action = None
    if priorities:
        top = priorities[0]
        reason = (
            "; ".join(top["reasons"])
            if top["reasons"]
            else "Highest combined academic priority."
        )
        best_next_action = {
            "kind": "priority",
            "title": f"{top['course_code']} · {top['topic']}",
            "reason": reason,
        }
    elif study_blocks:
        top = study_blocks[0]
        best_next_action = {
            "kind": "study_block",
            "title": f"{top['course_code']} · {top['title']}",
            "reason": top["label"],
        }

    return {
        "available": True,
        "message": "",
        "date": brief._today().isoformat(),
        "summary": {
            "urgent_deadlines": len(urgent),
            "scheduled_minutes": sum(study_minutes_by_course.values()),
            "priority_topics": len(priorities),
            "risk_courses": len(meaningful_risks),
        },
        "deadlines": deadlines,
        "study_blocks": study_blocks,
        "study_minutes_by_course": study_minutes_by_course,
        "priorities": priorities,
        "risks": meaningful_risks,
        "best_next_action": best_next_action,
    }


def load_home_dashboard() -> dict[str, Any]:
    """Load the existing Daily Academic Brief only when Home is requested."""
    brief = import_module("daily_academic_brief")
    return build_home_dashboard_from_brief(brief)


def unavailable_home_dashboard() -> dict[str, Any]:
    """Return a safe degraded read model when academic reads are unavailable."""
    return {
        "available": False,
        "message": (
            "Academic brief is temporarily unavailable. Your academic data was not changed."
        ),
        "date": None,
        "summary": {
            "urgent_deadlines": 0,
            "scheduled_minutes": 0,
            "priority_topics": 0,
            "risk_courses": 0,
        },
        "deadlines": [],
        "study_blocks": [],
        "study_minutes_by_course": {},
        "priorities": [],
        "risks": [],
        "best_next_action": None,
    }
