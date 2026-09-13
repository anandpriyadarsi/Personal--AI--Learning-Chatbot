"""Shared legacy-course normalization rules.

Phase 2 Fix 13 moves normalization/path-independent course rules out of the legacy root course_manager compatibility facade.
"""

import os


import re


from datetime import datetime


from knowledge_paths import BASE_DIR


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


__all__ = [
    'COURSES_FILE',
    'VALID_COURSE_STATUSES',
    'VALID_SOURCE_TYPES',
    'VALID_TOPIC_STATUSES',
    '_clean_text',
    '_normalise_course',
    '_normalise_data',
    '_normalise_status',
    '_normalise_topic',
    '_now',
    '_read_tag_header',
    '_slug',
    '_tagged_course_from_content',
    '_tagged_topic_from_content',
    'canonical_document_key',
    'default_course_data',
    'infer_source_type'
]
