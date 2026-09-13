"""Non-interactive CourseService for Phase 2.

Phase 2 keeps the existing JSON store authoritative while moving orchestration
behind typed service commands and repository interfaces.
"""

from typing import Callable, Optional

import course_manager

from personal_learning_assistant.domain.course_models import (
    AddTopicCommand,
    CourseCommandResult,
    CourseDocumentQuery,
    CourseListResult,
    CourseLookupResult,
    CourseView,
    CreateCourseCommand,
    DocumentCourseMatchQuery,
    DocumentCourseMatchResult,
    DocumentCourseResult,
    DocumentLinkResult,
    DocumentLinkView,
    DocumentMetadataResult,
    DocumentMetadataView,
    DocumentQuery,
    DocumentUnlinkResult,
    GetCourseQuery,
    LinkedDocumentsResult,
    LinkDocumentCommand,
    ListCoursesQuery,
    SetActiveCourseCommand,
    TopicCommandResult,
    TopicView,
    UnlinkDocumentCommand,
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


    def link_document(
        self,
        command: LinkDocumentCommand,
    ) -> DocumentLinkResult:
        course_result = self.get_course(
            GetCourseQuery(
                identifier=(
                    command.course_identifier
                )
            )
        )

        if course_result.course is None:
            raise ValueError(
                "Course not found."
            )

        source_type = (
            command.source_type
            or course_manager.infer_source_type(
                command.file_path
            )
        )
        source_type = (
            course_manager._normalise_status(
                source_type,
                course_manager.VALID_SOURCE_TYPES,
                "document",
            )
        )

        document_key = (
            course_manager.canonical_document_key(
                command.file_path
            )
        )

        link = {
            "course_id": (
                course_result.course.id
            ),
            "topic": (
                course_manager._clean_text(
                    command.topic
                )
            ),
            "source_type": source_type,
            "display_path": str(
                command.file_path
            ),
            "linked_at": self._now(),
        }

        saved = (
            self.repository.upsert_document_link(
                document_key,
                link,
            )
        )

        return DocumentLinkResult(
            link=DocumentLinkView.from_legacy(
                saved,
                document_key=document_key,
            )
        )

    def unlink_document(
        self,
        command: UnlinkDocumentCommand,
    ) -> DocumentUnlinkResult:
        document_key = (
            course_manager.canonical_document_key(
                command.file_path
            )
        )

        removed = (
            self.repository.delete_document_link(
                document_key
            )
        )

        return DocumentUnlinkResult(
            removed=removed
        )

    def get_document_link(
        self,
        query: DocumentQuery,
    ) -> DocumentLinkResult:
        document_key = (
            course_manager.canonical_document_key(
                query.file_path
            )
        )
        link = (
            self.repository.get_document_link(
                document_key
            )
        )

        if link is None:
            return DocumentLinkResult(
                link=None
            )

        return DocumentLinkResult(
            link=DocumentLinkView.from_legacy(
                link,
                document_key=document_key,
            )
        )

    def identify_course_for_document(
        self,
        query: DocumentQuery,
    ) -> DocumentCourseResult:
        link_result = self.get_document_link(
            query
        )

        if link_result.link is not None:
            lookup = self.get_course(
                GetCourseQuery(
                    identifier=(
                        link_result.link.course_id
                    )
                )
            )
            return DocumentCourseResult(
                course=lookup.course
            )

        content = query.content

        if content is None:
            content = (
                course_manager._read_tag_header(
                    query.file_path
                )
            )

        courses = self.list_courses().courses
        legacy_courses = [
            course.to_legacy_dict()
            for course in courses
        ]

        tagged = (
            course_manager._tagged_course_from_content(
                content,
                legacy_courses,
            )
        )

        if tagged:
            return DocumentCourseResult(
                course=CourseView.from_legacy(
                    tagged
                )
            )

        import re

        searchable_path = re.sub(
            r"[^a-z0-9]+",
            " ",
            str(
                query.file_path
            ).lower(),
        )
        padded_path = (
            " "
            + searchable_path
            + " "
        )

        for course in courses:
            code = re.sub(
                r"[^a-z0-9]+",
                " ",
                course.code.lower(),
            ).strip()
            name = re.sub(
                r"[^a-z0-9]+",
                " ",
                course.name.lower(),
            ).strip()

            if (
                code
                and f" {code} "
                in padded_path
            ):
                return DocumentCourseResult(
                    course=course
                )

            if (
                name
                and f" {name} "
                in padded_path
            ):
                return DocumentCourseResult(
                    course=course
                )

        return DocumentCourseResult(
            course=None
        )

    def get_document_metadata(
        self,
        query: DocumentQuery,
    ) -> DocumentMetadataResult:
        link_result = self.get_document_link(
            query
        )
        link = link_result.link

        content = query.content

        if content is None:
            content = (
                course_manager._read_tag_header(
                    query.file_path
                )
            )

        course_result = (
            self.identify_course_for_document(
                DocumentQuery(
                    file_path=query.file_path,
                    content=content,
                )
            )
        )
        course = course_result.course

        topic = (
            link.topic
            if (
                link is not None
                and link.topic
            )
            else (
                course_manager._tagged_topic_from_content(
                    content
                )
            )
        )

        source_type = (
            link.source_type
            if link is not None
            else (
                course_manager.infer_source_type(
                    query.file_path
                )
            )
        )

        metadata = DocumentMetadataView(
            course_id=(
                course.id
                if course
                else None
            ),
            course_code=(
                course.code
                if course
                else None
            ),
            course_name=(
                course.name
                if course
                else None
            ),
            topic=topic,
            source_type=source_type,
            document_key=(
                course_manager.canonical_document_key(
                    query.file_path
                )
            ),
        )

        return DocumentMetadataResult(
            metadata=metadata
        )

    def document_matches_course(
        self,
        query: DocumentCourseMatchQuery,
    ) -> DocumentCourseMatchResult:
        target = self.get_course(
            GetCourseQuery(
                identifier=(
                    query.course_identifier
                )
            )
        )

        if target.course is None:
            return DocumentCourseMatchResult(
                matches=False
            )

        identified = (
            self.identify_course_for_document(
                DocumentQuery(
                    file_path=query.file_path,
                    content=query.content,
                )
            )
        )

        matches = bool(
            identified.course
            and (
                identified.course.id
                == target.course.id
            )
        )

        return DocumentCourseMatchResult(
            matches=matches
        )

    def linked_documents_for_course(
        self,
        query: CourseDocumentQuery,
    ) -> LinkedDocumentsResult:
        course_result = self.get_course(
            GetCourseQuery(
                identifier=(
                    query.course_identifier
                )
            )
        )

        if course_result.course is None:
            return LinkedDocumentsResult(
                links=()
            )

        matches = []

        for (
            document_key,
            link,
        ) in (
            self.repository
            .list_document_links()
            .items()
        ):
            if (
                link.get(
                    "course_id"
                )
                != course_result.course.id
            ):
                continue

            matches.append(
                DocumentLinkView.from_legacy(
                    link,
                    document_key=(
                        document_key
                    ),
                )
            )

        matches.sort(
            key=lambda item: (
                item.display_path.lower()
            )
        )

        return LinkedDocumentsResult(
            links=tuple(matches)
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
