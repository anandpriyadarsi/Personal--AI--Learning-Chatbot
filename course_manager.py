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
    os.makedirs(os.path.dirname(COURSES_FILE), exist_ok=True)
    normalised = _normalise_data(data)
    temporary_file = COURSES_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(normalised, file, indent=2, ensure_ascii=False)

    os.replace(temporary_file, COURSES_FILE)


def list_courses(status=None):
    courses = load_course_data()["courses"]
    if status is None:
        return courses

    wanted = _normalise_status(status, VALID_COURSE_STATUSES, "active")
    return [course for course in courses if course["status"] == wanted]


def find_course(identifier):
    wanted = _clean_text(identifier).lower()
    if not wanted:
        return None

    for course in list_courses():
        if wanted in {
            course["id"].lower(),
            course["code"].lower(),
            course["name"].lower()
        }:
            return course

    return None


def get_active_course():
    data = load_course_data()
    active_id = data.get("active_course_id")
    return find_course(active_id) if active_id else None


def create_course(code, name, semester="", status="active", topics=None):
    code = _clean_text(code).upper()
    name = _clean_text(name)

    if not code:
        raise ValueError("Course code is required.")
    if not name:
        raise ValueError("Course name is required.")
    if find_course(code):
        raise ValueError(f"A course with code {code} already exists.")

    data = load_course_data()
    used_ids = {course["id"] for course in data["courses"]}
    course = _normalise_course({
        "id": _slug(code),
        "code": code,
        "name": name,
        "semester": semester,
        "status": status,
        "topics": topics or [],
        "created_at": _now(),
        "updated_at": _now()
    }, used_ids)

    data["courses"].append(course)
    if not data.get("active_course_id"):
        data["active_course_id"] = course["id"]
    save_course_data(data)
    return course


def set_active_course(identifier):
    course = find_course(identifier)
    if course is None:
        raise ValueError("Course not found.")

    data = load_course_data()
    data["active_course_id"] = course["id"]
    save_course_data(data)
    return course


def update_course_status(identifier, status):
    course = find_course(identifier)
    if course is None:
        raise ValueError("Course not found.")

    normalised_status = _normalise_status(
        status,
        VALID_COURSE_STATUSES,
        ""
    )
    if not normalised_status:
        raise ValueError("Invalid course status.")

    data = load_course_data()
    for item in data["courses"]:
        if item["id"] == course["id"]:
            item["status"] = normalised_status
            item["updated_at"] = _now()
            course = item
            break

    save_course_data(data)
    return course


def add_topic(course_identifier, topic_name, status="not_started"):
    course = find_course(course_identifier)
    if course is None:
        raise ValueError("Course not found.")

    topic_name = _clean_text(topic_name)
    if not topic_name:
        raise ValueError("Topic name is required.")

    data = load_course_data()
    for item in data["courses"]:
        if item["id"] != course["id"]:
            continue

        for topic in item["topics"]:
            if topic["name"].lower() == topic_name.lower():
                return topic, False

        topic = _normalise_topic({
            "name": topic_name,
            "status": status,
            "last_updated": _now()
        })
        item["topics"].append(topic)
        item["updated_at"] = _now()
        save_course_data(data)
        return topic, True

    raise ValueError("Course not found.")


def update_topic_status(course_identifier, topic_name, status, confidence=None):
    course = find_course(course_identifier)
    if course is None:
        raise ValueError("Course not found.")

    normalised_status = _normalise_status(
        status,
        VALID_TOPIC_STATUSES,
        ""
    )
    if not normalised_status:
        raise ValueError("Invalid topic status.")

    topic_name = _clean_text(topic_name)
    if not topic_name:
        raise ValueError("Topic name is required.")

    data = load_course_data()
    for item in data["courses"]:
        if item["id"] != course["id"]:
            continue

        selected = None
        for topic in item["topics"]:
            if topic["name"].lower() == topic_name.lower():
                selected = topic
                break

        if selected is None:
            selected = _normalise_topic({"name": topic_name})
            item["topics"].append(selected)

        selected["status"] = normalised_status
        selected["last_updated"] = _now()
        if confidence is not None:
            try:
                selected["confidence"] = max(0, min(5, int(confidence)))
            except (TypeError, ValueError):
                raise ValueError("Confidence must be a number from 0 to 5.")

        item["updated_at"] = _now()
        save_course_data(data)
        return selected

    raise ValueError("Course not found.")


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


def link_document(file_path, course_identifier, topic="", source_type=None):
    course = find_course(course_identifier)
    if course is None:
        raise ValueError("Course not found.")

    source_type = source_type or infer_source_type(file_path)
    source_type = _normalise_status(
        source_type,
        VALID_SOURCE_TYPES,
        "document"
    )

    data = load_course_data()
    key = canonical_document_key(file_path)
    data["document_links"][key] = {
        "course_id": course["id"],
        "topic": _clean_text(topic),
        "source_type": source_type,
        "display_path": str(file_path),
        "linked_at": _now()
    }
    save_course_data(data)
    return data["document_links"][key]


def unlink_document(file_path):
    data = load_course_data()
    key = canonical_document_key(file_path)
    if key not in data["document_links"]:
        return False
    del data["document_links"][key]
    save_course_data(data)
    return True


def get_document_link(file_path):
    return load_course_data()["document_links"].get(
        canonical_document_key(file_path)
    )


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


def identify_course_for_document(file_path, content=None):
    link = get_document_link(file_path)
    if link:
        return find_course(link["course_id"])

    courses = list_courses()
    if content is None:
        content = _read_tag_header(file_path)
    tagged = _tagged_course_from_content(content, courses)
    if tagged:
        return tagged

    searchable_path = re.sub(
        r"[^a-z0-9]+",
        " ",
        str(file_path).lower()
    )
    padded_path = " " + searchable_path + " "

    for course in courses:
        code = re.sub(r"[^a-z0-9]+", " ", course["code"].lower()).strip()
        name = re.sub(r"[^a-z0-9]+", " ", course["name"].lower()).strip()
        if code and f" {code} " in padded_path:
            return course
        if name and f" {name} " in padded_path:
            return course

    return None


def get_document_metadata(file_path, content=None):
    link = get_document_link(file_path)
    if content is None:
        content = _read_tag_header(file_path)
    course = identify_course_for_document(file_path, content)

    return {
        "course_id": course["id"] if course else None,
        "course_code": course["code"] if course else None,
        "course_name": course["name"] if course else None,
        "topic": (
            link.get("topic")
            if link and link.get("topic")
            else _tagged_topic_from_content(content)
        ),
        "source_type": (
            link.get("source_type") if link
            else infer_source_type(file_path)
        ),
        "document_key": canonical_document_key(file_path)
    }


def document_matches_course(file_path, course_identifier, content=None):
    course = find_course(course_identifier)
    if course is None:
        return False
    identified = identify_course_for_document(file_path, content)
    return bool(identified and identified["id"] == course["id"])


def linked_documents_for_course(course_identifier):
    course = find_course(course_identifier)
    if course is None:
        return []

    matches = []
    for key, link in load_course_data()["document_links"].items():
        if link["course_id"] == course["id"]:
            item = dict(link)
            item["document_key"] = key
            matches.append(item)
    return sorted(matches, key=lambda item: item["display_path"].lower())


def print_course_progress(course_identifier):
    progress = get_course_progress(course_identifier)
    if progress is None:
        print("\nCourse not found.")
        return

    course = progress["course"]
    print("\n" + "=" * 60)
    print(f"{course['code']} - {course['name']}")
    if course["semester"]:
        print(f"Semester : {course['semester']}")
    print(f"Status   : {course['status'].replace('_', ' ').title()}")
    print(f"Progress : {progress['mastered_topics']}/{progress['total_topics']} "
          f"topics mastered ({progress['progress_percent']}%)")
    print("=" * 60)

    if not course["topics"]:
        print("\nNo topics added yet.")
        return

    for number, topic in enumerate(course["topics"], start=1):
        status = topic["status"].replace("_", " ").title()
        confidence = topic["confidence"]
        confidence_text = f" | confidence {confidence}/5" if confidence else ""
        print(f"{number}. {topic['name']} - {status}{confidence_text}")


def choose_course(prompt="Select a course", allow_back=True):
    courses = list_courses()
    if not courses:
        print("\nNo courses exist yet. Open Course Manager and add one first.")
        return None

    active = get_active_course()
    print(f"\n========== {prompt.upper()} ==========")
    for number, course in enumerate(courses, start=1):
        marker = " [ACTIVE]" if active and active["id"] == course["id"] else ""
        print(f"{number}. {course['code']} - {course['name']}{marker}")
    if allow_back:
        print(f"{len(courses) + 1}. Back")

    try:
        choice = int(input("\nEnter course number: ").strip())
    except ValueError:
        print("\nPlease enter a valid number.")
        return None

    if allow_back and choice == len(courses) + 1:
        return None
    if choice < 1 or choice > len(courses):
        print("\nInvalid course number.")
        return None

    return set_active_course(courses[choice - 1]["id"])


def _show_courses():
    courses = list_courses()
    active = get_active_course()

    print("\n========== MY COURSES ==========")
    if not courses:
        print("\nNo courses added yet.")
        return

    for number, course in enumerate(courses, start=1):
        marker = " [ACTIVE]" if active and active["id"] == course["id"] else ""
        progress = get_course_progress(course["id"])
        print(
            f"{number}. {course['code']} - {course['name']}"
            f" | {course['semester'] or 'Semester not set'}"
            f" | {progress['progress_percent']}% mastered{marker}"
        )


def _add_course_interactive():
    print("\n========== ADD COURSE ==========")
    code = input("Course code (example MA103N): ").strip()
    name = input("Course name: ").strip()
    semester = input("Semester (example Semester 1): ").strip()

    try:
        course = create_course(code, name, semester)
        print(f"\nCourse added: {course['code']} - {course['name']}")
    except ValueError as error:
        print(f"\n{error}")


def _add_topic_interactive():
    course = choose_course("Add Topic To Course")
    if course is None:
        return
    topic = input("\nTopic name: ").strip()
    try:
        saved, created = add_topic(course["id"], topic)
        if created:
            print(f"\nTopic added: {saved['name']}")
        else:
            print("\nThat topic already exists.")
    except ValueError as error:
        print(f"\n{error}")


def _update_topic_interactive():
    course = choose_course("Update Topic Progress")
    if course is None:
        return
    print_course_progress(course["id"])
    topic = input("\nTopic name: ").strip()
    print("Statuses: not_started, learning, weak, review, practiced, mastered")
    status = input("New status: ").strip()
    confidence_text = input("Confidence 0-5 (press Enter to skip): ").strip()
    confidence = confidence_text if confidence_text else None
    try:
        saved = update_topic_status(course["id"], topic, status, confidence)
        print(f"\nUpdated {saved['name']} to {saved['status']}.")
    except ValueError as error:
        print(f"\n{error}")


def _link_document_interactive():
    course = choose_course("Link Knowledge Source")
    if course is None:
        return

    try:
        from knowledge import describe_source, find_documents
        documents = find_documents()
    except ImportError:
        print("\nKnowledge module is not available.")
        return

    if not documents:
        print("\nNo supported documents found.")
        return

    print("\n========== KNOWLEDGE SOURCES ==========")
    for number, path in enumerate(documents, start=1):
        metadata = get_document_metadata(path)
        current = (
            f" [{metadata['course_code']}]"
            if metadata["course_code"] else " [UNTAGGED]"
        )
        print(f"{number}. {describe_source(path)}{current}")

    try:
        choice = int(input("\nEnter source number: ").strip())
    except ValueError:
        print("\nPlease enter a valid number.")
        return

    if choice < 1 or choice > len(documents):
        print("\nInvalid source number.")
        return

    selected = documents[choice - 1]
    topic = input("Related topic (optional): ").strip()
    link_document(selected, course["id"], topic)
    print(f"\nSource linked to {course['code']}.")


def _show_linked_sources():
    course = choose_course("View Linked Sources")
    if course is None:
        return

    links = linked_documents_for_course(course["id"])
    print(f"\n========== {course['code']} SOURCES ==========")
    if not links:
        print("\nNo explicitly linked sources yet.")
        print("Files can also be auto-tagged from course codes in paths or Markdown tags.")
        return

    for number, link in enumerate(links, start=1):
        topic = f" | topic: {link['topic']}" if link["topic"] else ""
        print(
            f"{number}. {link['display_path']}"
            f" | {link['source_type'].replace('_', ' ')}{topic}"
        )


def course_manager_menu():
    while True:
        active = get_active_course()
        active_text = (
            f"{active['code']} - {active['name']}"
            if active else "None"
        )

        print("\n========== COURSE MANAGER V8 ==========")
        print(f"Active course: {active_text}")
        print("1. View All Courses")
        print("2. Add Course")
        print("3. Select Active Course")
        print("4. View Active Course Progress")
        print("5. Add Topic")
        print("6. Update Topic Status")
        print("7. Link Knowledge Source to Course")
        print("8. View Linked Sources")
        print("9. Back")

        choice = input("\nEnter your choice (1-9): ").strip()

        if choice == "1":
            _show_courses()
        elif choice == "2":
            _add_course_interactive()
        elif choice == "3":
            course = choose_course("Select Active Course")
            if course:
                print(f"\nActive course: {course['code']} - {course['name']}")
        elif choice == "4":
            if active:
                print_course_progress(active["id"])
            else:
                print("\nNo active course. Add or select a course first.")
        elif choice == "5":
            _add_topic_interactive()
        elif choice == "6":
            _update_topic_interactive()
        elif choice == "7":
            _link_document_interactive()
        elif choice == "8":
            _show_linked_sources()
        elif choice == "9":
            break
        else:
            print("\nInvalid choice. Please enter 1 to 9.")


if __name__ == "__main__":
    course_manager_menu()
