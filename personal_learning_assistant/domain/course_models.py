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
