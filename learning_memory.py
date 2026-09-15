"""Persistent global and course-aware learning memory for V8.

The V7 public functions remain compatible. Every topic, note, and activity can
now optionally be stored inside a course scope by passing ``course_id``.
Existing V7 ``learning_memory.json`` files are migrated without losing their
global weak topics, mastered topics, notes, or recent activity.
"""

import json
import os
from datetime import datetime

from knowledge_paths import BASE_DIR
from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)
from personal_learning_assistant.repositories.structured_authority_router import (
    maybe_load_sqlite_structured_store,
    maybe_save_sqlite_structured_store,
)


DATA_DIR = os.path.join(BASE_DIR, "data")
MEMORY_FILE = os.path.join(DATA_DIR, "learning_memory.json")

MEMORY_VERSION = 2
MAX_RECENT_ACTIVITY = 30
MAX_WEAK_TOPICS = 50
MAX_MASTERED_TOPICS = 50
MAX_NOTES = 30


def _now():
    return datetime.now().isoformat(timespec="seconds")


def default_memory():
    return {
        "version": MEMORY_VERSION,
        "weak_topics": [],
        "mastered_topics": [],
        "recent_activity": [],
        "notes": [],
        "course_memory": {}
    }


def _empty_scope():
    return {
        "weak_topics": [],
        "mastered_topics": [],
        "recent_activity": [],
        "notes": []
    }


def normalize_topic(topic):
    return " ".join(str(topic or "").strip().split())


def _normalise_note(item):
    if isinstance(item, str):
        return {"text": item.strip(), "created_at": None}
    if isinstance(item, dict):
        return {
            "text": str(item.get("text", "")).strip(),
            "created_at": item.get("created_at")
        }
    return {"text": "", "created_at": None}


def _normalise_activity(item):
    if not isinstance(item, dict):
        return None
    question = str(item.get("question", "")).strip()
    if not question:
        return None
    return {
        "mode": str(item.get("mode", "Academic Study")).strip(),
        "question": question,
        "topic": str(item.get("topic", "")).strip(),
        "time": item.get("time")
    }


def _normalise_scope(scope):
    if not isinstance(scope, dict):
        scope = {}

    weak = []
    for topic in scope.get("weak_topics", []):
        topic = normalize_topic(topic)
        if topic and topic.lower() not in {item.lower() for item in weak}:
            weak.append(topic)

    mastered = []
    for topic in scope.get("mastered_topics", []):
        topic = normalize_topic(topic)
        if topic and topic.lower() not in {item.lower() for item in mastered}:
            mastered.append(topic)

    weak_names = {item.lower() for item in weak}
    mastered = [item for item in mastered if item.lower() not in weak_names]

    activities = []
    for item in scope.get("recent_activity", []):
        activity = _normalise_activity(item)
        if activity:
            activities.append(activity)

    notes = []
    for item in scope.get("notes", []):
        note = _normalise_note(item)
        if note["text"]:
            notes.append(note)

    return {
        "weak_topics": weak[-MAX_WEAK_TOPICS:],
        "mastered_topics": mastered[-MAX_MASTERED_TOPICS:],
        "recent_activity": activities[-MAX_RECENT_ACTIVITY:],
        "notes": notes[-MAX_NOTES:]
    }


def _normalise_memory(data):
    if not isinstance(data, dict):
        return default_memory()

    global_scope = _normalise_scope(data)
    course_memory = {}
    raw_course_memory = data.get("course_memory", {})
    if isinstance(raw_course_memory, dict):
        for course_id, scope in raw_course_memory.items():
            clean_id = str(course_id).strip()
            if clean_id:
                course_memory[clean_id] = _normalise_scope(scope)

    return {
        "version": MEMORY_VERSION,
        "weak_topics": global_scope["weak_topics"],
        "mastered_topics": global_scope["mastered_topics"],
        "recent_activity": global_scope["recent_activity"],
        "notes": global_scope["notes"],
        "course_memory": course_memory
    }


def ensure_memory_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(MEMORY_FILE):
        save_memory(default_memory())


def load_memory():
    routed = maybe_load_sqlite_structured_store("learning_memory", MEMORY_FILE)
    if routed is not None:
        return _normalise_memory(routed)
    ensure_memory_file()

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            return _normalise_memory(json.load(file))
    except (json.JSONDecodeError, OSError):
        return default_memory()


def save_memory(memory):
    normalised = _normalise_memory(memory)
    if maybe_save_sqlite_structured_store("learning_memory", MEMORY_FILE, normalised):
        return
    guard_legacy_structured_write(infer_authority_control_path(MEMORY_FILE))
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    temporary_file = MEMORY_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(normalised, file, indent=2, ensure_ascii=False)

    os.replace(temporary_file, MEMORY_FILE)


def _resolve_course_id(course_identifier):
    if course_identifier is None:
        return None

    try:
        from course_manager import find_course
        course = find_course(course_identifier)
    except ImportError:
        course = None

    if course:
        return course["id"]
    return str(course_identifier).strip() or None


def _scope_for(memory, course_id=None, create=False):
    resolved_id = _resolve_course_id(course_id)
    if resolved_id is None:
        return memory, None

    if create and resolved_id not in memory["course_memory"]:
        memory["course_memory"][resolved_id] = _empty_scope()

    return memory["course_memory"].get(resolved_id, _empty_scope()), resolved_id


def add_unique_topic(items, topic, max_items):
    topic = normalize_topic(topic)
    if not topic:
        return

    if topic.lower() not in {item.lower() for item in items}:
        items.append(topic)
    if len(items) > max_items:
        del items[:-max_items]


def _sync_course_topic(course_id, topic, status):
    if not course_id:
        return
    try:
        from course_manager import update_topic_status
        update_topic_status(course_id, topic, status)
    except (ImportError, ValueError, OSError):
        # Memory remains useful even when the course catalogue is unavailable.
        pass


def mark_weak_topic(topic, course_id=None):
    memory = load_memory()
    topic = normalize_topic(topic)
    if not topic:
        return False

    scope, resolved_id = _scope_for(memory, course_id, create=True)
    add_unique_topic(scope["weak_topics"], topic, MAX_WEAK_TOPICS)
    scope["mastered_topics"] = [
        item for item in scope["mastered_topics"]
        if item.lower() != topic.lower()
    ]

    save_memory(memory)
    _sync_course_topic(resolved_id, topic, "weak")
    return True


def mark_mastered_topic(topic, course_id=None):
    memory = load_memory()
    topic = normalize_topic(topic)
    if not topic:
        return False

    scope, resolved_id = _scope_for(memory, course_id, create=True)
    add_unique_topic(scope["mastered_topics"], topic, MAX_MASTERED_TOPICS)
    scope["weak_topics"] = [
        item for item in scope["weak_topics"]
        if item.lower() != topic.lower()
    ]

    save_memory(memory)
    _sync_course_topic(resolved_id, topic, "mastered")
    return True


def add_memory_note(note, course_id=None):
    memory = load_memory()
    note = str(note or "").strip()
    if not note:
        return False

    scope, _ = _scope_for(memory, course_id, create=True)
    scope["notes"].append({"text": note, "created_at": _now()})
    scope["notes"] = scope["notes"][-MAX_NOTES:]
    save_memory(memory)
    return True


def record_activity(mode_name, question, course_id=None, topic=None):
    memory = load_memory()
    question = str(question or "").strip()
    if not question:
        return False

    scope, _ = _scope_for(memory, course_id, create=True)
    scope["recent_activity"].append({
        "mode": str(mode_name or "Academic Study").strip(),
        "question": question,
        "topic": normalize_topic(topic),
        "time": _now()
    })
    scope["recent_activity"] = scope["recent_activity"][-MAX_RECENT_ACTIVITY:]
    save_memory(memory)
    return True


def get_course_memory(course_id):
    memory = load_memory()
    scope, resolved_id = _scope_for(memory, course_id, create=False)
    return resolved_id, scope


def _scope_context_lines(scope, label=None):
    lines = []
    if label:
        lines.append(label)

    weak = scope["weak_topics"][-10:]
    mastered = scope["mastered_topics"][-10:]
    recent = scope["recent_activity"][-6:]
    notes = scope["notes"][-6:]

    if weak:
        lines.append("Known weak topics: " + ", ".join(weak))
    if mastered:
        lines.append("Topics marked mastered: " + ", ".join(mastered))
    if recent:
        lines.append("Recent study activity:")
        for item in recent:
            topic = f" | topic: {item['topic']}" if item.get("topic") else ""
            lines.append(f"- [{item['mode']}] {item['question']}{topic}")
    if notes:
        lines.append("Saved learning notes:")
        for item in notes:
            lines.append(f"- {item['text']}")

    return lines


def build_memory_context(course_id=None):
    memory = load_memory()
    lines = _scope_context_lines(memory, "GENERAL LEARNING MEMORY")

    resolved_id = _resolve_course_id(course_id)
    if resolved_id:
        course_scope = memory["course_memory"].get(resolved_id, _empty_scope())
        course_label = f"COURSE MEMORY ({resolved_id})"

        try:
            from course_manager import find_course, get_course_progress
            course = find_course(resolved_id)
            if course:
                course_label = f"COURSE MEMORY ({course['code']} - {course['name']})"
                progress = get_course_progress(resolved_id)
                lines.append(
                    f"Course progress: {progress['mastered_topics']}/"
                    f"{progress['total_topics']} topics mastered "
                    f"({progress['progress_percent']}%)."
                )
                if progress["weak_topics"]:
                    lines.append(
                        "Course topics currently weak: "
                        + ", ".join(progress["weak_topics"][:10])
                    )
                if progress["missing_topics"]:
                    lines.append(
                        "Course topics not started: "
                        + ", ".join(progress["missing_topics"][:10])
                    )
        except (ImportError, OSError):
            pass

        lines.extend(_scope_context_lines(course_scope, course_label))

    meaningful = [line for line in lines if line != "GENERAL LEARNING MEMORY"]
    if not meaningful:
        return "No persistent learning memory saved yet."
    return "\n".join(lines)


def show_memory_summary(course_id=None):
    memory = load_memory()
    scope, resolved_id = _scope_for(memory, course_id, create=False)

    label = "GENERAL"
    if resolved_id:
        label = resolved_id
        try:
            from course_manager import find_course
            course = find_course(resolved_id)
            if course:
                label = f"{course['code']} - {course['name']}"
        except ImportError:
            pass

    print("\n========== PERSISTENT LEARNING MEMORY ==========")
    print(f"Scope: {label}")

    print("\nWeak topics:")
    if scope["weak_topics"]:
        for topic in scope["weak_topics"]:
            print(f"- {topic}")
    else:
        print("- None")

    print("\nMastered topics:")
    if scope["mastered_topics"]:
        for topic in scope["mastered_topics"]:
            print(f"- {topic}")
    else:
        print("- None")

    print("\nRecent activity:")
    if scope["recent_activity"]:
        for item in scope["recent_activity"][-10:]:
            print(f"- [{item['mode']}] {item['question']}")
    else:
        print("- None")

    print("\nSaved notes:")
    if scope["notes"]:
        for item in scope["notes"][-10:]:
            print(f"- {item['text']}")
    else:
        print("- None")


def _scope_name(course_id):
    if course_id is None:
        return "General"
    try:
        from course_manager import find_course
        course = find_course(course_id)
        if course:
            return f"{course['code']} - {course['name']}"
    except ImportError:
        pass
    return str(course_id)


def memory_menu():
    try:
        from course_manager import choose_course, get_active_course
        active = get_active_course()
    except ImportError:
        choose_course = None
        active = None

    course_id = active["id"] if active else None

    while True:
        print("\n========== LEARNING MEMORY MENU V8 ==========")
        print(f"Current scope: {_scope_name(course_id)}")
        print("1. View Memory Summary")
        print("2. Mark Weak Topic")
        print("3. Mark Mastered Topic")
        print("4. Add Learning Note")
        print("5. Use General Memory Scope")
        print("6. Select Course Memory Scope")
        print("7. Back")

        choice = input("\nEnter your choice (1-7): ").strip()

        if choice == "1":
            show_memory_summary(course_id)
        elif choice == "2":
            topic = input("\nTopic to mark as weak: ").strip()
            if mark_weak_topic(topic, course_id):
                print(f"\nSaved weak topic: {topic}")
        elif choice == "3":
            topic = input("\nTopic to mark as mastered: ").strip()
            if mark_mastered_topic(topic, course_id):
                print(f"\nSaved mastered topic: {topic}")
        elif choice == "4":
            note = input("\nLearning note to remember: ").strip()
            if add_memory_note(note, course_id):
                print("\nLearning note saved.")
        elif choice == "5":
            course_id = None
            print("\nMemory scope changed to General.")
        elif choice == "6":
            if choose_course is None:
                print("\nCourse Manager is not available.")
                continue
            course = choose_course("Select Memory Course")
            if course:
                course_id = course["id"]
                print(f"\nMemory scope changed to {course['code']}.")
        elif choice == "7":
            break
        else:
            print("\nInvalid choice. Please enter 1 to 7.")


if __name__ == "__main__":
    memory_menu()
