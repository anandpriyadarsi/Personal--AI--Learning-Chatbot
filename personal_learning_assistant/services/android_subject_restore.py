"""Restore the existing first-year subject catalogue in the private Android app.

The original Learning Studio presentation lives in learning_studio.course_views.
This service restores missing course *records* from the already approved,
source-backed canonical topic catalogues. It does not fabricate lessons,
source documents, grades, instructor details or learning evidence.
"""
from __future__ import annotations

from personal_learning_assistant.domain import course_normalization
from personal_learning_assistant.domain.canonical_topic_catalogues import (
    COURSE_CATALOGUE_METADATA,
    canonical_names,
)
from personal_learning_assistant.repositories.routed_course_repository import (
    RoutedCourseRepository,
)

# Restore only the confirmed Semester 1 subjects; preserve original course codes.
SEMESTER_ONE_CODES = ("MA103N", "UC100N", "CY100N", "DE100N", "UC103N")
SEMESTER_ONE_LABEL = "Semester 1"


def restore_semester_one_subjects(*, only_when_empty: bool = False):
    """Add absent subject templates; never replace existing course records.

    Automatic phone-local onboarding happens only if the entire catalogue is
    empty. Explicit user action can add missing subjects to a partial catalogue.
    Existing status, confidence, module mappings, topic IDs and notes remain
    untouched. A present course with no topics may receive its original
    canonical outline; a nonempty outline is never rewritten.
    """
    repo = RoutedCourseRepository()
    state = repo.load_state()  # Read errors must not be mistaken for empty data.
    courses = state["courses"]
    if only_when_empty and courses:
        return ()
    used_ids = {item["id"] for item in courses}
    existing = {str(item.get("code") or "").strip().upper(): item
                for item in courses if item.get("code")}
    now = course_normalization._now()
    created = []
    changed = False
    for code in SEMESTER_ONE_CODES:
        names = canonical_names(code)
        assert names, "Subject restoration requires the original canonical outline."
        if code in existing:
            # A manually added placeholder can receive its missing course outline
            # without changing its identity, status, name or existing study data.
            course = existing[code]
            if not course.get("topics"):
                course["topics"] = [
                    course_normalization._normalise_topic({"name": name, "status": "not_started"})
                    for name in names
                ]
                course["updated_at"] = now
                changed = True
            continue
        item = course_normalization._normalise_course({
            "id": course_normalization._slug(code),
            "code": code,
            "name": COURSE_CATALOGUE_METADATA[code]["course_name"],
            "semester": SEMESTER_ONE_LABEL,
            "status": "active",
            "topics": [{"name": name, "status": "not_started"} for name in names],
            "created_at": now,
            "updated_at": now,
        }, used_ids)
        courses.append(item)
        existing[code] = item
        created.append(code)
        changed = True
    if changed:
        if not state.get("active_course_id"):
            state["active_course_id"] = courses[0]["id"]
        repo.save_state(state)
    return tuple(created)
