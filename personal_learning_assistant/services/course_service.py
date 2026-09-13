"""Non-interactive CourseService read queries for Phase 2 Fix 1."""

from typing import Optional

import course_manager

from personal_learning_assistant.domain.course_models import (
    CourseListResult,
    CourseLookupResult,
    CourseView,
    GetCourseQuery,
    ListCoursesQuery,
)
from personal_learning_assistant.repositories.interfaces import (
    CourseRepository,
)


class CourseService:
    """
    Application-facing course query service.

    It never calls ``input()`` or ``print()`` and read queries never persist
    state. During Phase 2, the injected repository still reads the existing
    JSON authority.
    """

    def __init__(
        self,
        repository: CourseRepository,
    ):
        self.repository = repository

    def list_courses(
        self,
        query: Optional[ListCoursesQuery] = None,
    ) -> CourseListResult:
        query = query or ListCoursesQuery()
        state = self.repository.load_state()
        courses = list(
            state.get(
                "courses",
                [],
            )
        )

        if query.status is not None:
            wanted = course_manager._normalise_status(
                query.status,
                course_manager.VALID_COURSE_STATUSES,
                "active",
            )
            courses = [
                course
                for course in courses
                if course.get("status") == wanted
            ]

        return CourseListResult(
            courses=tuple(
                CourseView.from_legacy(course)
                for course in courses
            ),
            active_course_id=state.get(
                "active_course_id"
            ),
        )

    def get_course(
        self,
        query: GetCourseQuery,
    ) -> CourseLookupResult:
        wanted = course_manager._clean_text(
            query.identifier
        ).lower()

        if not wanted:
            return CourseLookupResult(
                course=None
            )

        for course in self.list_courses().courses:
            if wanted in {
                course.id.lower(),
                course.code.lower(),
                course.name.lower(),
            }:
                return CourseLookupResult(
                    course=course
                )

        return CourseLookupResult(
            course=None
        )

    def get_active_course(
        self,
    ) -> CourseLookupResult:
        state = self.repository.load_state()
        active_id = state.get(
            "active_course_id"
        )

        if not active_id:
            return CourseLookupResult(
                course=None
            )

        return self.get_course(
            GetCourseQuery(
                identifier=active_id
            )
        )
