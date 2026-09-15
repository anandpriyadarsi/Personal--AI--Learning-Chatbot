"""Course catalogue, topic progress, and knowledge-source tagging for V8.

This module deliberately uses only the Python standard library so it works with
the existing Windows command-line project.  Course data is stored in
``data/courses.json`` and is created automatically on first use.
"""

import json
import os
import re
from datetime import datetime

from knowledge_paths import BASE_DIR
from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)


DATA_DIR = os.path.join(BASE_DIR, "data")
COURSES_FILE = os.path.join(DATA_DIR, "courses.json")

COURSE_DATA_VERSION = 1
VALID_COURSE_STATUSES = {
    "active",
    "planned",
    "completed",
    "archived"
}
VALID_TOPIC_STATUSES = {
    "not_started",
    "learning",
    "weak",
    "review",
    "practiced",
    "mastered"
}
VALID_SOURCE_TYPES = {
    "document",
    "obsidian_note",
    "youtube_lecture",
    "course_pdf",
    "text_note",
    "other"
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def default_course_data():
    return {
        "version": COURSE_DATA_VERSION,
        "active_course_id": None,
        "courses": [],
        "document_links": {}
    }


def _clean_text(value):
    return " ".join(str(value or "").strip().split())


def _normalise_status(value, valid_values, default):
    status = _clean_text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "in_progress": "learning",
        "incomplete": "not_started",
        "done": "mastered"
    }
    status = aliases.get(status, status)
    return status if status in valid_values else default


def _slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "course"


def _normalise_topic(topic):
    if isinstance(topic, str):
        topic = {"name": topic}
    elif not isinstance(topic, dict):
        topic = {}

    name = _clean_text(topic.get("name"))
    status = _normalise_status(
        topic.get("status"),
        VALID_TOPIC_STATUSES,
        "not_started"
    )

    try:
        confidence = int(topic.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0

    confidence = max(0, min(5, confidence))

    return {
        "name": name,
        "status": status,
        "confidence": confidence,
        "last_updated": topic.get("last_updated")
    }


def _normalise_course(course, used_ids):
    code = _clean_text(course.get("code")).upper()
    name = _clean_text(course.get("name"))
    course_id = _clean_text(course.get("id")) or _slug(code or name)
    original_id = course_id
    suffix = 2

    while course_id in used_ids:
        course_id = f"{original_id}-{suffix}"
        suffix += 1

    used_ids.add(course_id)

    topics = []
    seen_topics = set()
    for raw_topic in course.get("topics", []):
        topic = _normalise_topic(raw_topic)
        key = topic["name"].lower()
        if topic["name"] and key not in seen_topics:
            topics.append(topic)
            seen_topics.add(key)

    return {
        "id": course_id,
        "code": code,
        "name": name,
        "semester": _clean_text(course.get("semester")),
        "status": _normalise_status(
            course.get("status"),
            VALID_COURSE_STATUSES,
            "active"
        ),
        "topics": topics,
        "created_at": course.get("created_at") or _now(),
        "updated_at": course.get("updated_at") or _now()
    }


def _normalise_data(data):
    if not isinstance(data, dict):
        data = default_course_data()

    used_ids = set()
    courses = []
    for raw_course in data.get("courses", []):
        if not isinstance(raw_course, dict):
            continue
        course = _normalise_course(raw_course, used_ids)
        if course["code"] or course["name"]:
            courses.append(course)

    links = data.get("document_links", {})
    if not isinstance(links, dict):
        links = {}

    clean_links = {}
    for key, value in links.items():
        if not isinstance(value, dict):
            continue
        course_id = _clean_text(value.get("course_id"))
        if course_id not in used_ids:
            continue
        clean_links[str(key)] = {
            "course_id": course_id,
            "topic": _clean_text(value.get("topic")),
            "source_type": _normalise_status(
                value.get("source_type"),
                VALID_SOURCE_TYPES,
                "document"
            ),
            "display_path": str(value.get("display_path") or key),
            "linked_at": value.get("linked_at") or _now()
        }

    active_course_id = data.get("active_course_id")
    if active_course_id not in used_ids:
        active_course_id = courses[0]["id"] if courses else None

    return {
        "version": COURSE_DATA_VERSION,
        "active_course_id": active_course_id,
        "courses": courses,
        "document_links": clean_links
    }


def ensure_courses_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(COURSES_FILE):
        save_course_data(default_course_data())


def load_course_data():
    ensure_courses_file()

    try:
        with open(COURSES_FILE, "r", encoding="utf-8") as file:
            return _normalise_data(json.load(file))
    except (json.JSONDecodeError, OSError):
        return default_course_data()


def save_course_data(data):
    guard_legacy_structured_write(infer_authority_control_path(COURSES_FILE))
    os.makedirs(os.path.dirname(COURSES_FILE), exist_ok=True)
    normalised = _normalise_data(data)
    temporary_file = COURSES_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(normalised, file, indent=2, ensure_ascii=False)

    os.replace(temporary_file, COURSES_FILE)


def _build_course_service():
    """
    Build the Phase 2 CourseService lazily.

    Imports stay inside this function to avoid a course_manager ->
    CourseService -> course_manager import cycle at module startup.
    A fresh service is returned on every call so tests and callers that
    temporarily replace COURSES_FILE continue to work correctly.
    """
    from personal_learning_assistant.repositories.json.course_repository import (
        LegacyJsonCourseRepository,
    )
    from personal_learning_assistant.services.course_service import (
        CourseService,
    )

    return CourseService(
        LegacyJsonCourseRepository(
            COURSES_FILE
        ),
        now=_now,
    )


def list_courses(status=None):
    """
    Compatibility facade for the legacy list_courses API.

    The public return value remains a list of legacy dictionaries.
    """
    from personal_learning_assistant.domain.course_models import (
        ListCoursesQuery,
    )

    result = _build_course_service().list_courses(
        ListCoursesQuery(
            status=status
        )
    )

    return [
        course.to_legacy_dict()
        for course in result.courses
    ]


def find_course(identifier):
    """
    Compatibility facade for the legacy find_course API.
    """
    from personal_learning_assistant.domain.course_models import (
        GetCourseQuery,
    )

    result = _build_course_service().get_course(
        GetCourseQuery(
            identifier=identifier
        )
    )

    if result.course is None:
        return None

    return result.course.to_legacy_dict()


def get_active_course():
    """
    Compatibility facade for the legacy get_active_course API.
    """
    result = (
        _build_course_service()
        .get_active_course()
    )

    if result.course is None:
        return None

    return result.course.to_legacy_dict()


def create_course(
    code,
    name,
    semester="",
    status="active",
    topics=None,
):
    """
    Compatibility facade for legacy course creation.
    """
    from personal_learning_assistant.domain.course_models import (
        CreateCourseCommand,
    )

    result = _build_course_service().create_course(
        CreateCourseCommand(
            code=code,
            name=name,
            semester=semester,
            status=status,
            topics=tuple(
                topics or []
            ),
        )
    )

    return result.course.to_legacy_dict()


def set_active_course(identifier):
    """
    Compatibility facade for the legacy set_active_course API.
    """
    from personal_learning_assistant.domain.course_models import (
        SetActiveCourseCommand,
    )

    result = _build_course_service().set_active_course(
        SetActiveCourseCommand(
            identifier=identifier
        )
    )

    return result.course.to_legacy_dict()


def update_course_status(
    identifier,
    status,
):
    """
    Compatibility facade for legacy course status updates.
    """
    from personal_learning_assistant.domain.course_models import (
        UpdateCourseStatusCommand,
    )

    result = (
        _build_course_service()
        .update_course_status(
            UpdateCourseStatusCommand(
                identifier=identifier,
                status=status,
            )
        )
    )

    return result.course.to_legacy_dict()


def add_topic(
    course_identifier,
    topic_name,
    status="not_started",
):
    """
    Compatibility facade for the legacy add_topic API.
    """
    from personal_learning_assistant.domain.course_models import (
        AddTopicCommand,
    )

    result = _build_course_service().add_topic(
        AddTopicCommand(
            course_identifier=course_identifier,
            topic_name=topic_name,
            status=status,
        )
    )

    return (
        result.topic.to_legacy_dict(),
        bool(result.created),
    )


def update_topic_status(
    course_identifier,
    topic_name,
    status,
    confidence=None,
):
    """
    Compatibility facade for the legacy update_topic_status API.
    """
    from personal_learning_assistant.domain.course_models import (
        UpdateTopicStatusCommand,
    )

    result = (
        _build_course_service()
        .update_topic_status(
            UpdateTopicStatusCommand(
                course_identifier=course_identifier,
                topic_name=topic_name,
                status=status,
                confidence=confidence,
            )
        )
    )

    return result.topic.to_legacy_dict()


def get_course_progress(course_identifier):
    course = find_course(course_identifier)
    if course is None:
        return None

    counts = {status: 0 for status in VALID_TOPIC_STATUSES}
    for topic in course["topics"]:
        counts[topic["status"]] += 1

    total = len(course["topics"])
    mastered = counts["mastered"]

    return {
        "course": course,
        "total_topics": total,
        "mastered_topics": mastered,
        "progress_percent": round((mastered / total) * 100) if total else 0,
        "counts": counts,
        "weak_topics": [
            topic["name"] for topic in course["topics"]
            if topic["status"] == "weak"
        ],
        "missing_topics": [
            topic["name"] for topic in course["topics"]
            if topic["status"] == "not_started"
        ]
    }


def recommend_next_topics(course_identifier, limit=5):
    course = find_course(course_identifier)
    if course is None:
        return []

    priority = {
        "weak": 0,
        "learning": 1,
        "review": 2,
        "not_started": 3,
        "practiced": 4,
        "mastered": 5
    }
    ordered = sorted(
        enumerate(course["topics"]),
        key=lambda pair: (priority[pair[1]["status"]], pair[0])
    )

    return [
        topic for _, topic in ordered
        if topic["status"] != "mastered"
    ][:max(1, int(limit))]


def _is_inside(path, parent):
    try:
        return os.path.commonpath([
            os.path.abspath(path),
            os.path.abspath(parent)
        ]) == os.path.abspath(parent)
    except (ValueError, OSError):
        return False


def canonical_document_key(file_path):
    absolute_path = os.path.abspath(file_path)

    try:
        from obsidian_integration import get_vault_path
        vault_path = get_vault_path()
    except (ImportError, OSError):
        vault_path = None

    if vault_path and _is_inside(absolute_path, vault_path):
        relative = os.path.relpath(absolute_path, vault_path)
        return "obsidian:" + relative.replace("\\", "/")

    if _is_inside(absolute_path, BASE_DIR):
        relative = os.path.relpath(absolute_path, BASE_DIR)
        return "base:" + relative.replace("\\", "/")

    return "external:" + os.path.normcase(absolute_path).replace("\\", "/")


def infer_source_type(file_path):
    path = str(file_path).lower().replace("\\", "/")
    extension = os.path.splitext(path)[1]

    if "youtube" in path or "transcript" in path:
        return "youtube_lecture"
    if "obsidian" in path or path.endswith(".md"):
        return "obsidian_note"
    if extension == ".pdf":
        return "course_pdf"
    if extension == ".txt":
        return "text_note"
    return "document"


def link_document(
    file_path,
    course_identifier,
    topic="",
    source_type=None,
):
    """Compatibility facade for CourseService source linking."""
    from personal_learning_assistant.domain.course_models import (
        LinkDocumentCommand,
    )

    result = _build_course_service().link_document(
        LinkDocumentCommand(
            file_path=str(file_path),
            course_identifier=course_identifier,
            topic=topic,
            source_type=source_type,
        )
    )

    return (
        result.link.to_legacy_dict()
        if result.link
        else None
    )


def unlink_document(file_path):
    """Compatibility facade for source unlinking."""
    from personal_learning_assistant.domain.course_models import (
        UnlinkDocumentCommand,
    )

    result = _build_course_service().unlink_document(
        UnlinkDocumentCommand(
            file_path=str(file_path)
        )
    )

    return result.removed


def get_document_link(file_path):
    """Compatibility facade for document-link queries."""
    from personal_learning_assistant.domain.course_models import (
        DocumentQuery,
    )

    result = _build_course_service().get_document_link(
        DocumentQuery(
            file_path=str(file_path)
        )
    )

    if result.link is None:
        return None

    return result.link.to_legacy_dict()


def _tagged_course_from_content(content, courses):
    header = (content or "")[:5000]
    tag_values = []
    patterns = [
        r"(?im)^\s*(?:course|course_code)\s*:\s*[\"']?([^\n\"']+)",
        r"(?i)\[\s*course\s*:\s*([^\]]+)\]"
    ]
    for pattern in patterns:
        tag_values.extend(re.findall(pattern, header))

    for value in tag_values:
        normalised = _clean_text(value).lower()
        for course in courses:
            if normalised in {
                course["id"].lower(),
                course["code"].lower(),
                course["name"].lower()
            }:
                return course

    return None


def _read_tag_header(file_path):
    if os.path.splitext(str(file_path))[1].lower() not in {".md", ".txt"}:
        return ""

    for encoding in ("utf-8", "latin-1"):
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read(5000)
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    return ""


def _tagged_topic_from_content(content):
    header = (content or "")[:5000]
    patterns = [
        r"(?im)^\s*topic\s*:\s*[\"']?([^\n\"']+)",
        r"(?i)\[\s*topic\s*:\s*([^\]]+)\]"
    ]
    for pattern in patterns:
        match = re.search(pattern, header)
        if match:
            return _clean_text(match.group(1))
    return ""



def identify_course_for_document(
    file_path,
    content=None,
):
    """Compatibility facade for document-to-course identification."""
    from personal_learning_assistant.domain.course_models import (
        DocumentQuery,
    )

    result = (
        _build_course_service()
        .identify_course_for_document(
            DocumentQuery(
                file_path=str(file_path),
                content=content,
            )
        )
    )

    if result.course is None:
        return None

    return result.course.to_legacy_dict()


def get_document_metadata(
    file_path,
    content=None,
):
    """Compatibility facade for document course/source metadata."""
    from personal_learning_assistant.domain.course_models import (
        DocumentQuery,
    )

    result = (
        _build_course_service()
        .get_document_metadata(
            DocumentQuery(
                file_path=str(file_path),
                content=content,
            )
        )
    )

    return result.metadata.to_legacy_dict()


def document_matches_course(
    file_path,
    course_identifier,
    content=None,
):
    """Compatibility facade for document/course matching."""
    from personal_learning_assistant.domain.course_models import (
        DocumentCourseMatchQuery,
    )

    result = (
        _build_course_service()
        .document_matches_course(
            DocumentCourseMatchQuery(
                file_path=str(file_path),
                course_identifier=course_identifier,
                content=content,
            )
        )
    )

    return result.matches


def linked_documents_for_course(
    course_identifier,
):
    """Compatibility facade for linked-source listing."""
    from personal_learning_assistant.domain.course_models import (
        CourseDocumentQuery,
    )

    result = (
        _build_course_service()
        .linked_documents_for_course(
            CourseDocumentQuery(
                course_identifier=course_identifier
            )
        )
    )

    return [
        link.to_legacy_dict(
            include_document_key=True
        )
        for link in result.links
    ]



def _build_course_cli():
    """
    Lazily load the terminal adapter.

    Keeping this import lazy prevents CLI concerns from becoming a dependency
    of course data/services and preserves the existing root-module API.
    """
    from personal_learning_assistant.ui.cli.course_cli import (
        CourseCLI,
    )

    return CourseCLI(
        course_api=__import__(
            __name__
        )
    )


def print_course_progress(course_identifier):
    """Compatibility wrapper for the extracted CLI renderer."""
    return _build_course_cli().print_course_progress(
        course_identifier
    )


def choose_course(
    prompt="Select a course",
    allow_back=True,
):
    """Compatibility wrapper for the extracted interactive selector."""
    return _build_course_cli().choose_course(
        prompt=prompt,
        allow_back=allow_back,
    )


def _show_courses():
    return _build_course_cli().show_courses()


def _add_course_interactive():
    return _build_course_cli().add_course_interactive()


def _add_topic_interactive():
    return _build_course_cli().add_topic_interactive()


def _update_topic_interactive():
    return _build_course_cli().update_topic_interactive()


def _link_document_interactive():
    return _build_course_cli().link_document_interactive()


def _show_linked_sources():
    return _build_course_cli().show_linked_sources()


def course_manager_menu():
    """Compatibility entry point used by main.py option 23."""
    return _build_course_cli().run()


if __name__ == "__main__":
    course_manager_menu()
