"""V9 Course Planner + Academic Progress Engine.

Builds on the V8 course catalogue and course-aware learning memory.
It does not replace course_manager.py; it reads the existing V8 course/topic
state and adds progress snapshots, priority scoring, gap analysis and study
planning.
"""

import json
import os
from datetime import datetime, timedelta

from knowledge_paths import BASE_DIR
from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)
from course_manager import (
    choose_course,
    find_course,
    get_active_course,
    get_course_progress,
    print_course_progress,
    recommend_next_topics,
)
from learning_memory import get_course_memory


DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "course_progress_history.json")
HISTORY_VERSION = 1
MAX_SNAPSHOTS_PER_COURSE = 120

STATUS_WEIGHTS = {
    "weak": 100,
    "learning": 80,
    "review": 65,
    "not_started": 55,
    "practiced": 35,
    "mastered": 0,
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _today():
    return datetime.now().date().isoformat()


def default_history():
    return {
        "version": HISTORY_VERSION,
        "courses": {},
    }


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return default_history()

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return default_history()

    if not isinstance(data, dict):
        return default_history()

    courses = data.get("courses")
    if not isinstance(courses, dict):
        courses = {}

    return {
        "version": HISTORY_VERSION,
        "courses": courses,
    }


def save_history(data):
    guard_legacy_structured_write(infer_authority_control_path(HISTORY_FILE))
    os.makedirs(DATA_DIR, exist_ok=True)
    temporary = HISTORY_FILE + ".tmp"

    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    os.replace(temporary, HISTORY_FILE)


def _safe_confidence(topic):
    value = topic.get("confidence")
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(value, 5))


def _topic_counts(course):
    counts = {
        "not_started": 0,
        "learning": 0,
        "practiced": 0,
        "review": 0,
        "weak": 0,
        "mastered": 0,
        "other": 0,
    }

    for topic in course.get("topics", []):
        status = str(topic.get("status") or "not_started").strip().lower()
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1

    return counts


def make_snapshot(course_id):
    course = find_course(course_id)
    if course is None:
        return None

    progress = get_course_progress(course["id"])
    counts = _topic_counts(course)

    confidence_values = [
        _safe_confidence(topic)
        for topic in course.get("topics", [])
        if _safe_confidence(topic) > 0
    ]

    average_confidence = 0.0
    if confidence_values:
        average_confidence = round(
            sum(confidence_values) / len(confidence_values),
            2,
        )

    return {
        "captured_at": _now(),
        "date": _today(),
        "course_id": course["id"],
        "course_code": course.get("code", ""),
        "course_name": course.get("name", ""),
        "total_topics": progress.get("total_topics", len(course.get("topics", []))),
        "mastered_topics": progress.get("mastered_topics", counts["mastered"]),
        "progress_percent": progress.get("progress_percent", 0),
        "average_confidence": average_confidence,
        "status_counts": counts,
        "weak_topics": list(progress.get("weak_topics", [])),
        "missing_topics": list(progress.get("missing_topics", [])),
    }


def record_progress_snapshot(course_id, force=False):
    snapshot = make_snapshot(course_id)
    if snapshot is None:
        return None

    history = load_history()
    course_id = snapshot["course_id"]
    snapshots = history["courses"].setdefault(course_id, [])

    # One automatic snapshot per day is enough. A forced snapshot is useful
    # after a deliberate study/update session.
    if not force and snapshots and snapshots[-1].get("date") == snapshot["date"]:
        snapshots[-1] = snapshot
    else:
        snapshots.append(snapshot)

    history["courses"][course_id] = snapshots[-MAX_SNAPSHOTS_PER_COURSE:]
    save_history(history)
    return snapshot


def get_course_snapshots(course_id):
    course = find_course(course_id)
    if course is None:
        return []
    return load_history()["courses"].get(course["id"], [])


def get_recent_course_activity(course_id):
    _, scope = get_course_memory(course_id)
    return list(scope.get("recent_activity", []))


def _parse_activity_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def topic_last_activity(course_id, topic_name):
    topic_lower = topic_name.lower()
    latest = None

    for item in get_recent_course_activity(course_id):
        combined = " ".join([
            str(item.get("topic") or ""),
            str(item.get("question") or ""),
        ]).lower()

        if topic_lower not in combined:
            continue

        moment = _parse_activity_time(item.get("time"))
        if moment and (latest is None or moment > latest):
            latest = moment

    return latest


def priority_score(course_id, topic, position=0):
    status = str(topic.get("status") or "not_started").strip().lower()
    score = STATUS_WEIGHTS.get(status, 45)
    reasons = []

    if status == "weak":
        reasons.append("marked weak")
    elif status == "learning":
        reasons.append("currently being learned")
    elif status == "review":
        reasons.append("review is due")
    elif status == "not_started":
        reasons.append("unfinished syllabus topic")
    elif status == "practiced":
        reasons.append("needs consolidation")

    confidence = _safe_confidence(topic)
    if confidence:
        confidence_bonus = max(0, (5 - confidence) * 6)
        score += confidence_bonus
        if confidence <= 2:
            reasons.append("low confidence")

    last_activity = topic_last_activity(course_id, topic.get("name", ""))
    if last_activity:
        days = (datetime.now() - last_activity).days
        if days >= 14:
            score += 18
            reasons.append("not studied recently")
        elif days >= 7:
            score += 10
            reasons.append("revision becoming due")
        elif days <= 1:
            score -= 6
    else:
        if status not in {"mastered", "not_started"}:
            score += 8
            reasons.append("no recent activity recorded")

    # Small syllabus-order preference for otherwise similar unfinished topics.
    score += max(0, 10 - min(position, 10))

    if status == "mastered":
        score = 0
        reasons = ["already mastered"]

    return score, reasons


def rank_course_topics(course_id, limit=8):
    course = find_course(course_id)
    if course is None:
        return []

    ranked = []

    for position, topic in enumerate(course.get("topics", [])):
        score, reasons = priority_score(course["id"], topic, position)
        item = dict(topic)
        item["priority_score"] = score
        item["priority_reasons"] = reasons
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            item["priority_score"],
            -course_topic_index(course, item.get("name", "")),
        ),
        reverse=True,
    )

    unfinished = [item for item in ranked if item["priority_score"] > 0]
    return unfinished[:limit]


def course_topic_index(course, topic_name):
    for index, topic in enumerate(course.get("topics", [])):
        if str(topic.get("name", "")).lower() == str(topic_name).lower():
            return index
    return 9999


def get_progress_trend(course_id):
    """Return current-vs-history progress without mutating history."""
    current = make_snapshot(course_id)
    if current is None:
        return None

    snapshots = list(get_course_snapshots(course_id))

    # Before Fix 14 this query recorded/replaced today's snapshot and then
    # excluded that newest item from comparison. Preserve that comparison
    # behavior without writing: if the newest stored snapshot is from today,
    # treat it as the current-history slot and compare against earlier history.
    historical = snapshots
    if (
        historical
        and historical[-1].get("date") == current.get("date")
    ):
        historical = historical[:-1]

    if not historical:
        return {
            "current": current,
            "previous": None,
            "delta_progress": 0,
            "delta_mastered": 0,
        }

    previous = None
    cutoff = datetime.now().date() - timedelta(days=7)

    for snapshot in reversed(historical):
        try:
            snapshot_date = datetime.fromisoformat(
                snapshot["date"]
            ).date()
        except (KeyError, TypeError, ValueError):
            continue

        if snapshot_date <= cutoff:
            previous = snapshot
            break

    if previous is None:
        previous = historical[-1]

    return {
        "current": current,
        "previous": previous,
        "delta_progress": (
            current["progress_percent"]
            - previous.get("progress_percent", 0)
            if previous
            else 0
        ),
        "delta_mastered": (
            current["mastered_topics"]
            - previous.get("mastered_topics", 0)
            if previous
            else 0
        ),
    }


def print_progress_dashboard(course_id):
    course = find_course(course_id)
    if course is None:
        print("\nCourse not found.")
        return

    snapshot = make_snapshot(course["id"])
    counts = snapshot["status_counts"]

    print(f"\n========== {course['code']} PROGRESS DASHBOARD ==========")
    print(f"Course      : {course['name']}")
    print(f"Progress    : {snapshot['progress_percent']}%")
    print(
        f"Mastered    : {snapshot['mastered_topics']}/"
        f"{snapshot['total_topics']} topics"
    )
    print(f"Confidence  : {snapshot['average_confidence']}/5 average")
    print("\nTopic status:")
    print(f"- Weak        : {counts['weak']}")
    print(f"- Learning    : {counts['learning']}")
    print(f"- Practiced   : {counts['practiced']}")
    print(f"- Review      : {counts['review']}")
    print(f"- Not started : {counts['not_started']}")
    print(f"- Mastered    : {counts['mastered']}")

    if snapshot["weak_topics"]:
        print("\nWeak topics:")
        for topic in snapshot["weak_topics"][:10]:
            print(f"- {topic}")

    if snapshot["missing_topics"]:
        print("\nNot-started / missing topics:")
        for topic in snapshot["missing_topics"][:10]:
            print(f"- {topic}")


def print_priority_report(course_id):
    course = find_course(course_id)
    if course is None:
        return

    ranked = rank_course_topics(course["id"], limit=8)
    print(f"\n========== {course['code']} PRIORITY ENGINE ==========")

    if not ranked:
        print("\nNo unfinished priority topics found.")
        return

    for number, topic in enumerate(ranked, start=1):
        reasons = ", ".join(topic["priority_reasons"]) or "continue progress"
        confidence = _safe_confidence(topic)
        confidence_text = f" | confidence {confidence}/5" if confidence else ""
        print(
            f"{number}. {topic.get('name', 'Unnamed topic')}"
            f" | {topic.get('status', 'not_started')}"
            f" | priority {topic['priority_score']}"
            f"{confidence_text}"
        )
        print(f"   Why: {reasons}")


def print_study_next(course_id):
    course = find_course(course_id)
    if course is None:
        return

    ranked = rank_course_topics(course["id"], limit=3)
    print(f"\n========== WHAT TO STUDY NEXT: {course['code']} ==========")

    if not ranked:
        print("\nAll stored topics are mastered. Use mixed revision and practice.")
        return

    for number, topic in enumerate(ranked, start=1):
        reasons = ", ".join(topic["priority_reasons"]) or "highest current priority"
        print(f"\n{number}. {topic['name']}")
        print(f"   Status : {topic.get('status', 'not_started')}")
        print(f"   Reason : {reasons}")

        if topic.get("status") == "weak":
            action = "Relearn the core idea, solve 2 easy examples, then 3 independent questions."
        elif topic.get("status") == "learning":
            action = "Finish the concept, write a short recall note, then solve practice questions."
        elif topic.get("status") == "review":
            action = "Do active recall first, then one mixed problem without looking at notes."
        elif topic.get("status") == "not_started":
            action = "Learn the prerequisite idea and first concept, then attempt 2 basic questions."
        else:
            action = "Do a short recall and one application problem to strengthen retention."

        print(f"   Action : {action}")


def print_gap_report(course_id):
    course = find_course(course_id)
    if course is None:
        return

    progress = get_course_progress(course["id"])
    weak = progress.get("weak_topics", [])
    missing = progress.get("missing_topics", [])

    print(f"\n========== {course['code']} GAP REPORT ==========")

    print("\nWeak topics:")
    if weak:
        for topic in weak:
            print(f"- {topic}")
    else:
        print("- None stored")

    print("\nNot-started / missing topics:")
    if missing:
        for topic in missing:
            print(f"- {topic}")
    else:
        print("- None stored")

    ranked = rank_course_topics(course["id"], limit=5)
    if ranked:
        print("\nHighest-priority gaps:")
        for index, topic in enumerate(ranked, start=1):
            print(f"{index}. {topic['name']} ({topic.get('status', 'not_started')})")


def print_weekly_progress(course_id):
    course = find_course(course_id)
    if course is None:
        return

    trend = get_progress_trend(course["id"])
    current = trend["current"]
    previous = trend["previous"]

    print(f"\n========== {course['code']} WEEKLY PROGRESS ==========")
    print(f"Current progress : {current['progress_percent']}%")
    print(f"Topics mastered  : {current['mastered_topics']}/{current['total_topics']}")

    if previous is None:
        print("\nNot enough history yet for a comparison.")
        print("Use 'Save Progress Snapshot Now' to build comparison history.")
        return

    print(f"Previous snapshot: {previous.get('date', 'Unknown')}")
    print(f"Progress change  : {trend['delta_progress']:+}%")
    print(f"Mastery change   : {trend['delta_mastered']:+} topic(s)")

    if trend["delta_progress"] > 0:
        print("Trend             : Moving forward")
    elif trend["delta_progress"] == 0:
        print("Trend             : No mastery percentage change yet")
    else:
        print("Trend             : Progress status decreased; review topic updates")


def _select_initial_course():
    active = get_active_course()
    if active:
        return active
    return choose_course("Select Course for Academic Progress")


def academic_progress_menu():
    course = _select_initial_course()

    if course is None:
        print("\nNo course selected. Add/select a course in Course Manager first.")
        return

    while True:
        print("\n========== V9 COURSE PLANNER + PROGRESS ENGINE ==========")
        print(f"Current course: {course['code']} - {course['name']}")
        print("1. Course Progress Dashboard")
        print("2. View Detailed Topic Progress")
        print("3. What Should I Study Next?")
        print("4. Priority Topic Report")
        print("5. Weak + Missing Topic Report")
        print("6. Weekly Progress Trend")
        print("7. Save Progress Snapshot Now")
        print("8. Change Course")
        print("9. Back")

        choice = input("\nEnter your choice (1-9): ").strip()

        if choice == "1":
            print_progress_dashboard(course["id"])
        elif choice == "2":
            print_course_progress(course["id"])
        elif choice == "3":
            print_study_next(course["id"])
        elif choice == "4":
            print_priority_report(course["id"])
        elif choice == "5":
            print_gap_report(course["id"])
        elif choice == "6":
            print_weekly_progress(course["id"])
        elif choice == "7":
            snapshot = record_progress_snapshot(course["id"], force=True)
            if snapshot:
                print(f"\nProgress snapshot saved for {snapshot['date']}.")
        elif choice == "8":
            selected = choose_course("Select Course for Academic Progress")
            if selected:
                course = selected
        elif choice == "9":
            break
        else:
            print("\nInvalid choice. Please enter 1 to 9.")


if __name__ == "__main__":
    academic_progress_menu()
