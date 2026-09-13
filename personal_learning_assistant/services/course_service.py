"""Non-interactive CourseService for Phase 2.

Phase 2 keeps the existing JSON store authoritative while moving orchestration
behind typed service commands and repository interfaces.
"""

from typing import Callable, Optional

import course_manager

from personal_learning_assistant.domain.course_models import (
    AddTopicCommand,
    CourseCommandResult,
    CourseListResult,
    CourseLookupResult,
    CourseView,
    CreateCourseCommand,
    GetCourseQuery,
    ListCoursesQuery,
    SetActiveCourseCommand,
    TopicCommandResult,
    TopicView,
    UpdateCourseStatusCommand,
    UpdateTopicStatusCommand,
)
from personal_learning_assistant.repositories.interfaces import (
    CourseRepository,
)


class CourseService:
    """
    Non-interactive application service for course queries and commands.

    Read methods never persist state. Command methods write only through the
    injected repository. JSON remains the single structured authority in Phase 2.
    """

    def __init__(
        self,
        repository: CourseRepository,
        now: Optional[Callable[[], str]] = None,
    ):
        self.repository = repository
        self._now = now or course_manager._now

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

    def create_course(
        self,
        command: CreateCourseCommand,
    ) -> CourseCommandResult:
        code = course_manager._clean_text(
            command.code
        ).upper()
        name = course_manager._clean_text(
            command.name
        )

        if not code:
            raise ValueError(
                "Course code is required."
            )

        if not name:
            raise ValueError(
                "Course name is required."
            )

        if self.get_course(
            GetCourseQuery(
                identifier=code
            )
        ).course is not None:
            raise ValueError(
                f"A course with code {code} already exists."
            )

        state = self.repository.load_state()
        used_ids = {
            course["id"]
            for course in state["courses"]
        }

        timestamp = self._now()
        course = course_manager._normalise_course(
            {
                "id": course_manager._slug(code),
                "code": code,
                "name": name,
                "semester": command.semester,
                "status": command.status,
                "topics": list(command.topics),
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            used_ids,
        )

        state["courses"].append(course)

        if not state.get(
            "active_course_id"
        ):
            state["active_course_id"] = course["id"]

        saved = self.repository.save_state(
            state
        )
        persisted = self._course_by_id(
            saved,
            course["id"],
        )

        return CourseCommandResult(
            course=CourseView.from_legacy(
                persisted
            )
        )

    def set_active_course(
        self,
        command: SetActiveCourseCommand,
    ) -> CourseCommandResult:
        lookup = self.get_course(
            GetCourseQuery(
                identifier=command.identifier
            )
        )

        if lookup.course is None:
            raise ValueError(
                "Course not found."
            )

        state = self.repository.load_state()
        state["active_course_id"] = (
            lookup.course.id
        )

        saved = self.repository.save_state(
            state
        )
        persisted = self._course_by_id(
            saved,
            lookup.course.id,
        )

        return CourseCommandResult(
            course=CourseView.from_legacy(
                persisted
            )
        )

    def update_course_status(
        self,
        command: UpdateCourseStatusCommand,
    ) -> CourseCommandResult:
        lookup = self.get_course(
            GetCourseQuery(
                identifier=command.identifier
            )
        )

        if lookup.course is None:
            raise ValueError(
                "Course not found."
            )

        normalised_status = (
            course_manager._normalise_status(
                command.status,
                course_manager.VALID_COURSE_STATUSES,
                "",
            )
        )

        if not normalised_status:
            raise ValueError(
                "Invalid course status."
            )

        state = self.repository.load_state()

        for course in state["courses"]:
            if course["id"] == lookup.course.id:
                course["status"] = (
                    normalised_status
                )
                course["updated_at"] = (
                    self._now()
                )
                break

        saved = self.repository.save_state(
            state
        )
        persisted = self._course_by_id(
            saved,
            lookup.course.id,
        )

        return CourseCommandResult(
            course=CourseView.from_legacy(
                persisted
            )
        )

    def add_topic(
        self,
        command: AddTopicCommand,
    ) -> TopicCommandResult:
        lookup = self.get_course(
            GetCourseQuery(
                identifier=command.course_identifier
            )
        )

        if lookup.course is None:
            raise ValueError(
                "Course not found."
            )

        topic_name = course_manager._clean_text(
            command.topic_name
        )

        if not topic_name:
            raise ValueError(
                "Topic name is required."
            )

        state = self.repository.load_state()

        for course in state["courses"]:
            if course["id"] != lookup.course.id:
                continue

            for topic in course["topics"]:
                if (
                    topic["name"].lower()
                    == topic_name.lower()
                ):
                    return TopicCommandResult(
                        topic=TopicView.from_legacy(
                            topic
                        ),
                        created=False,
                    )

            topic = course_manager._normalise_topic(
                {
                    "name": topic_name,
                    "status": command.status,
                    "last_updated": self._now(),
                }
            )
            course["topics"].append(topic)
            course["updated_at"] = self._now()

            saved = self.repository.save_state(
                state
            )
            persisted_course = (
                self._course_by_id(
                    saved,
                    lookup.course.id,
                )
            )
            persisted_topic = (
                self._topic_by_name(
                    persisted_course,
                    topic_name,
                )
            )

            return TopicCommandResult(
                topic=TopicView.from_legacy(
                    persisted_topic
                ),
                created=True,
            )

        raise ValueError(
            "Course not found."
        )

    def update_topic_status(
        self,
        command: UpdateTopicStatusCommand,
    ) -> TopicCommandResult:
        lookup = self.get_course(
            GetCourseQuery(
                identifier=command.course_identifier
            )
        )

        if lookup.course is None:
            raise ValueError(
                "Course not found."
            )

        normalised_status = (
            course_manager._normalise_status(
                command.status,
                course_manager.VALID_TOPIC_STATUSES,
                "",
            )
        )

        if not normalised_status:
            raise ValueError(
                "Invalid topic status."
            )

        topic_name = course_manager._clean_text(
            command.topic_name
        )

        if not topic_name:
            raise ValueError(
                "Topic name is required."
            )

        state = self.repository.load_state()

        for course in state["courses"]:
            if course["id"] != lookup.course.id:
                continue

            selected = None

            for topic in course["topics"]:
                if (
                    topic["name"].lower()
                    == topic_name.lower()
                ):
                    selected = topic
                    break

            if selected is None:
                selected = (
                    course_manager._normalise_topic(
                        {
                            "name": topic_name
                        }
                    )
                )
                course["topics"].append(
                    selected
                )

            selected["status"] = (
                normalised_status
            )
            selected["last_updated"] = (
                self._now()
            )

            if command.confidence is not None:
                try:
                    selected["confidence"] = max(
                        0,
                        min(
                            5,
                            int(
                                command.confidence
                            ),
                        ),
                    )
                except (
                    TypeError,
                    ValueError,
                ) as error:
                    raise ValueError(
                        "Confidence must be a number from 0 to 5."
                    ) from error

            course["updated_at"] = self._now()

            saved = self.repository.save_state(
                state
            )
            persisted_course = (
                self._course_by_id(
                    saved,
                    lookup.course.id,
                )
            )
            persisted_topic = (
                self._topic_by_name(
                    persisted_course,
                    topic_name,
                )
            )

            return TopicCommandResult(
                topic=TopicView.from_legacy(
                    persisted_topic
                ),
                created=None,
            )

        raise ValueError(
            "Course not found."
        )

    @staticmethod
    def _course_by_id(
        state,
        course_id,
    ):
        for course in state.get(
            "courses",
            [],
        ):
            if course.get("id") == course_id:
                return course

        raise ValueError(
            "Course not found after save."
        )

    @staticmethod
    def _topic_by_name(
        course,
        topic_name,
    ):
        wanted = topic_name.lower()

        for topic in course.get(
            "topics",
            [],
        ):
            if (
                topic.get(
                    "name",
                    "",
                ).lower()
                == wanted
            ):
                return topic

        raise ValueError(
            "Topic not found after save."
        )
