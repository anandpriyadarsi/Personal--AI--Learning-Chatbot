"""Typed course queries and read models.

Phase 2 keeps ``data/courses.json`` authoritative. These dataclasses are
application-facing views only; they are not a new persistence format.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class TopicView:
    name: str
    status: str
    confidence: int
    last_updated: Optional[str] = None

    @classmethod
    def from_legacy(cls, data):
        return cls(
            name=str(data.get("name", "")),
            status=str(data.get("status", "not_started")),
            confidence=int(data.get("confidence", 0)),
            last_updated=data.get("last_updated"),
        )

    def to_legacy_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "confidence": self.confidence,
            "last_updated": self.last_updated,
        }


@dataclass(frozen=True)
class CourseView:
    id: str
    code: str
    name: str
    semester: str
    status: str
    topics: Tuple[TopicView, ...]
    created_at: Optional[str]
    updated_at: Optional[str]

    @classmethod
    def from_legacy(cls, data):
        return cls(
            id=str(data.get("id", "")),
            code=str(data.get("code", "")),
            name=str(data.get("name", "")),
            semester=str(data.get("semester", "")),
            status=str(data.get("status", "active")),
            topics=tuple(
                TopicView.from_legacy(topic)
                for topic in data.get("topics", [])
            ),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def to_legacy_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "semester": self.semester,
            "status": self.status,
            "topics": [
                topic.to_legacy_dict()
                for topic in self.topics
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ListCoursesQuery:
    status: Optional[str] = None


@dataclass(frozen=True)
class GetCourseQuery:
    identifier: str


@dataclass(frozen=True)
class CourseListResult:
    courses: Tuple[CourseView, ...]
    active_course_id: Optional[str]


@dataclass(frozen=True)
class CourseLookupResult:
    course: Optional[CourseView]


@dataclass(frozen=True)
class CreateCourseCommand:
    code: str
    name: str
    semester: str = ""
    status: str = "active"
    topics: Tuple[dict, ...] = ()


@dataclass(frozen=True)
class SetActiveCourseCommand:
    identifier: str


@dataclass(frozen=True)
class UpdateCourseStatusCommand:
    identifier: str
    status: str


@dataclass(frozen=True)
class AddTopicCommand:
    course_identifier: str
    topic_name: str
    status: str = "not_started"


@dataclass(frozen=True)
class UpdateTopicStatusCommand:
    course_identifier: str
    topic_name: str
    status: str
    confidence: Optional[int] = None


@dataclass(frozen=True)
class CourseCommandResult:
    course: CourseView


@dataclass(frozen=True)
class TopicCommandResult:
    topic: TopicView
    created: Optional[bool] = None


@dataclass(frozen=True)
class LinkDocumentCommand:
    file_path: str
    course_identifier: str
    topic: str = ""
    source_type: Optional[str] = None


@dataclass(frozen=True)
class UnlinkDocumentCommand:
    file_path: str


@dataclass(frozen=True)
class DocumentQuery:
    file_path: str
    content: Optional[str] = None


@dataclass(frozen=True)
class CourseDocumentQuery:
    course_identifier: str


@dataclass(frozen=True)
class DocumentCourseMatchQuery:
    file_path: str
    course_identifier: str
    content: Optional[str] = None


@dataclass(frozen=True)
class DocumentLinkView:
    course_id: str
    topic: str
    source_type: str
    display_path: str
    linked_at: Optional[str]
    document_key: Optional[str] = None

    @classmethod
    def from_legacy(
        cls,
        data,
        document_key=None,
    ):
        return cls(
            course_id=str(
                data.get(
                    "course_id",
                    "",
                )
            ),
            topic=str(
                data.get(
                    "topic",
                    "",
                )
            ),
            source_type=str(
                data.get(
                    "source_type",
                    "document",
                )
            ),
            display_path=str(
                data.get(
                    "display_path",
                    "",
                )
            ),
            linked_at=data.get(
                "linked_at"
            ),
            document_key=document_key,
        )

    def to_legacy_dict(
        self,
        include_document_key=False,
    ):
        data = {
            "course_id": self.course_id,
            "topic": self.topic,
            "source_type": self.source_type,
            "display_path": self.display_path,
            "linked_at": self.linked_at,
        }

        if include_document_key:
            data["document_key"] = (
                self.document_key
            )

        return data


@dataclass(frozen=True)
class DocumentMetadataView:
    course_id: Optional[str]
    course_code: Optional[str]
    course_name: Optional[str]
    topic: str
    source_type: str
    document_key: str

    def to_legacy_dict(self):
        return {
            "course_id": self.course_id,
            "course_code": self.course_code,
            "course_name": self.course_name,
            "topic": self.topic,
            "source_type": self.source_type,
            "document_key": self.document_key,
        }


@dataclass(frozen=True)
class DocumentLinkResult:
    link: Optional[DocumentLinkView]


@dataclass(frozen=True)
class DocumentUnlinkResult:
    removed: bool


@dataclass(frozen=True)
class LinkedDocumentsResult:
    links: Tuple[DocumentLinkView, ...]


@dataclass(frozen=True)
class DocumentMetadataResult:
    metadata: DocumentMetadataView


@dataclass(frozen=True)
class DocumentCourseResult:
    course: Optional[CourseView]


@dataclass(frozen=True)
class DocumentCourseMatchResult:
    matches: bool
