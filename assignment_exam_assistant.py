"""V10 Assignment & Exam Assistant.

Tracks assignments, quizzes, labs, midsems and exams, then combines deadlines,
course progress and source-grounded RAG to help Anand prepare realistically.
"""

import json
import os
from datetime import date, datetime

from knowledge_paths import BASE_DIR
from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)
from course_manager import choose_course, find_course
from academic_progress import rank_course_topics, print_progress_dashboard
from rag_answer import (
    rag_answer,
    clean_terminal_markdown,
    print_verified_sources,
    llm_is_configured,
)
from semantic_retrieval import load_semantic_index


DATA_DIR = os.path.join(BASE_DIR, "data")
ASSESSMENTS_FILE = os.path.join(DATA_DIR, "assessments.json")

ASSESSMENT_VERSION = 2
MAX_ASSESSMENTS = 200

ASSESSMENT_TYPES = {
    "1": "assignment",
    "2": "quiz",
    "3": "lab",
    "4": "midsem",
    "5": "endsem",
    "6": "exam",
    "7": "project",
}

VALID_STATUSES = {
    "pending",
    "in_progress",
    "completed",
}


def _today():
    return date.today()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def default_store():
    return {
        "version": ASSESSMENT_VERSION,
        "assessments": [],
    }


def load_store():
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(ASSESSMENTS_FILE):
        return default_store()

    try:
        with open(ASSESSMENTS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return default_store()

    if not isinstance(data, dict):
        return default_store()

    assessments = data.get("assessments", [])
    if not isinstance(assessments, list):
        assessments = []

    return {
        "version": ASSESSMENT_VERSION,
        "assessments": assessments[-MAX_ASSESSMENTS:],
    }


def save_store(store):
    guard_legacy_structured_write(infer_authority_control_path(ASSESSMENTS_FILE))
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_file = ASSESSMENTS_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(store, file, indent=2, ensure_ascii=False)

    os.replace(temp_file, ASSESSMENTS_FILE)


def _next_id(store):
    existing = []

    for item in store.get("assessments", []):
        try:
            existing.append(int(item.get("id", 0)))
        except (TypeError, ValueError):
            pass

    return str(max(existing, default=0) + 1)


def parse_date(text):
    try:
        return datetime.strptime(
            text.strip(),
            "%Y-%m-%d"
        ).date()
    except ValueError:
        return None


def days_until(due_date):
    parsed = parse_date(due_date)

    if parsed is None:
        return None

    return (parsed - _today()).days



def _float_or_none(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def assessment_weightage_percent(item):
    return _float_or_none(item.get("weightage_percent"))


def assessment_course_credits(item, course=None):
    value = _float_or_none(item.get("course_credits"))
    if value is not None:
        return value

    if course is None:
        course = find_course(item.get("course_id"))

    if not course:
        return None

    for key in ("credits", "credit", "course_credits"):
        value = _float_or_none(course.get(key))
        if value is not None:
            return value

    return None


def _ask_optional_float(prompt, minimum=0.0, maximum=None, default=None):
    while True:
        default_text = ""
        if default is not None:
            default_text = f" [default {default:g}]"

        raw = input(
            f"{prompt}{default_text} "
            "(press Enter if unknown): "
        ).strip()

        if not raw:
            return default

        value = _float_or_none(raw)

        if value is None:
            print("Please enter a valid number or press Enter.")
            continue

        if value < minimum:
            print(f"Value must be at least {minimum}.")
            continue

        if maximum is not None and value > maximum:
            print(f"Value cannot exceed {maximum}.")
            continue

        return value


def assessment_academic_impact(item):
    weightage = assessment_weightage_percent(item) or 0.0
    credits = assessment_course_credits(item) or 0.0
    return round(weightage * credits, 2)


def weighted_course_score_contribution(item):
    weightage = assessment_weightage_percent(item)
    total_marks = _float_or_none(item.get("total_marks"))
    obtained_marks = _float_or_none(item.get("obtained_marks"))

    if (
        weightage is None
        or total_marks is None
        or obtained_marks is None
        or total_marks <= 0
    ):
        return None

    return round(
        (obtained_marks / total_marks) * weightage,
        3
    )


def assessment_priority(item):
    if item.get("status") == "completed":
        return -999

    days = days_until(item.get("due_date", ""))

    if days is None:
        urgency = 0
    elif days < 0:
        urgency = 100
    elif days == 0:
        urgency = 90
    elif days <= 2:
        urgency = 80
    elif days <= 7:
        urgency = 60
    elif days <= 14:
        urgency = 40
    else:
        urgency = 20

    type_bonus = {
        "endsem": 25,
        "midsem": 22,
        "exam": 20,
        "project": 15,
        "assignment": 12,
        "quiz": 10,
        "lab": 8,
    }.get(
        item.get("type"),
        5
    )

    status_bonus = (
        8
        if item.get("status") == "in_progress"
        else 0
    )

    weightage = assessment_weightage_percent(item) or 0.0
    credits = assessment_course_credits(item) or 0.0

    weightage_bonus = min(30.0, weightage * 0.8)
    credit_bonus = min(10.0, credits * 2.0)

    return round(
        urgency
        + type_bonus
        + status_bonus
        + weightage_bonus
        + credit_bonus,
        1
    )


def list_assessments(include_completed=True):
    items = load_store()["assessments"]

    if not include_completed:
        items = [
            item for item in items
            if item.get("status") != "completed"
        ]

    return sorted(
        items,
        key=lambda item: (
            -assessment_priority(item),
            item.get("due_date", "9999-12-31"),
        )
    )


def choose_assessment(include_completed=False):
    items = list_assessments(
        include_completed=include_completed
    )

    if not items:
        print("\nNo matching assessments found.")
        return None

    print("\n========== ASSESSMENTS ==========")

    for index, item in enumerate(items, start=1):
        course = find_course(
            item.get("course_id")
        )

        course_code = (
            course["code"]
            if course
            else "UNKNOWN"
        )

        days = days_until(
            item.get("due_date", "")
        )

        if days is None:
            due_text = item.get(
                "due_date",
                "No date"
            )
        elif days < 0:
            due_text = (
                f"OVERDUE by {abs(days)} day(s)"
            )
        elif days == 0:
            due_text = "due TODAY"
        else:
            due_text = f"due in {days} day(s)"

        print(
            f"{index}. [{course_code}] "
            f"{item.get('title', 'Untitled')} "
            f"| {item.get('type')} "
            f"| {item.get('status')} "
            f"| {due_text}"
        )

    try:
        choice = int(
            input(
                "\nChoose assessment number: "
            ).strip()
        )
    except ValueError:
        print("\nPlease enter a valid number.")
        return None

    if choice < 1 or choice > len(items):
        print("\nInvalid assessment number.")
        return None

    return items[choice - 1]


def choose_assessment_type():
    print("\nAssessment type:")
    print("1. Assignment")
    print("2. Quiz")
    print("3. Lab")
    print("4. Midsem")
    print("5. Endsem")
    print("6. Exam")
    print("7. Project")

    choice = input(
        "\nChoose type (1-7): "
    ).strip()

    return ASSESSMENT_TYPES.get(choice)


def add_assessment():
    print("\n========== ADD ASSESSMENT ==========")

    course = choose_course(
        "Select Course"
    )

    if not course:
        print("\nNo course selected.")
        return

    assessment_type = choose_assessment_type()

    if not assessment_type:
        print("\nInvalid assessment type.")
        return

    title = input(
        "\nTitle: "
    ).strip()

    if not title:
        print("\nTitle cannot be empty.")
        return

    while True:
        due_date = input(
            "Due date (YYYY-MM-DD): "
        ).strip()

        if parse_date(due_date):
            break

        print(
            "Invalid date. Example: 2026-09-20"
        )

    print("\n--- NITK Academic Impact ---")
    print(
        "Weightage means this assessment's percentage "
        "contribution to the FINAL COURSE GRADE."
    )
    print(
        "Example: Quiz 1 contributes 10% to MA103N -> enter 10."
    )

    weightage_percent = _ask_optional_float(
        "Assessment weightage (%)",
        minimum=0.0,
        maximum=100.0
    )

    detected_credits = assessment_course_credits(
        {"course_id": course["id"]},
        course=course
    )

    course_credits = _ask_optional_float(
        "Course credits",
        minimum=0.0,
        default=detected_credits
    )

    print(
        "\nYou do NOT need to know question-wise marks before the quiz."
    )
    print(
        "Total quiz marks can also be left unknown now and entered later."
    )

    total_marks = _ask_optional_float(
        "Total marks of this assessment",
        minimum=0.0
    )

    topics = input(
        "Topics/syllabus focus "
        "(comma-separated, optional): "
    ).strip()

    description = input(
        "Notes/instructions "
        "(optional): "
    ).strip()

    store = load_store()

    item = {
        "id": _next_id(store),
        "course_id": course["id"],
        "type": assessment_type,
        "title": title,
        "due_date": due_date,
        "weightage_percent": weightage_percent,
        "course_credits": course_credits,
        "total_marks": total_marks,
        "obtained_marks": None,
        "topics": [
            topic.strip()
            for topic in topics.split(",")
            if topic.strip()
        ],
        "description": description,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
    }

    store["assessments"].append(item)
    store["assessments"] = store["assessments"][-MAX_ASSESSMENTS:]
    save_store(store)

    print(
        f"\nSaved: {title} for {course['code']}."
    )

    if weightage_percent is not None:
        print(
            f"Weightage: {weightage_percent:g}% "
            "of final course grade."
        )

    if course_credits is not None:
        print(
            f"Course credits: {course_credits:g}"
        )

    print(
        "Question-wise marks will be recorded only "
        "after you know the actual quiz questions."
    )


def print_upcoming():
    items = list_assessments(
        include_completed=False
    )

    print(
        "\n========== UPCOMING ASSIGNMENTS & EXAMS =========="
    )

    if not items:
        print("\nNo pending assessments.")
        return

    for item in items:
        course = find_course(
            item.get("course_id")
        )

        code = (
            course["code"]
            if course
            else "UNKNOWN"
        )

        days = days_until(
            item.get("due_date", "")
        )

        if days is None:
            timing = item.get(
                "due_date",
                "No date"
            )
        elif days < 0:
            timing = (
                f"OVERDUE {abs(days)} day(s)"
            )
        elif days == 0:
            timing = "TODAY"
        else:
            timing = f"{days} day(s) left"

        print(
            f"\n[{code}] {item['title']}"
        )
        print(
            f"Type     : {item['type']}"
        )
        print(
            f"Due      : {item['due_date']} "
            f"({timing})"
        )
        print(
            f"Status   : {item['status']}"
        )
        weightage = assessment_weightage_percent(item)
        credits = assessment_course_credits(
            item,
            course=course
        )

        if weightage is not None:
            print(
                f"Weightage: {weightage:g}% "
                "of final course grade"
            )

        if credits is not None:
            print(
                f"Credits  : {credits:g}"
            )

        print(
            f"Priority : "
            f"{assessment_priority(item)}"
        )

        if item.get("topics"):
            print(
                "Topics   : "
                + ", ".join(
                    item["topics"]
                )
            )



def edit_assessment_academic_details():
    item = choose_assessment(
        include_completed=True
    )

    if not item:
        return

    course = find_course(
        item.get("course_id")
    )

    print(
        "\n========== EDIT WEIGHTAGE / CREDITS / MARKS =========="
    )

    weightage = _ask_optional_float(
        "Assessment weightage (%)",
        minimum=0.0,
        maximum=100.0,
        default=assessment_weightage_percent(item)
    )

    credits = _ask_optional_float(
        "Course credits",
        minimum=0.0,
        default=assessment_course_credits(
            item,
            course=course
        )
    )

    total_marks = _ask_optional_float(
        "Total assessment marks",
        minimum=0.0,
        default=_float_or_none(
            item.get("total_marks")
        )
    )

    store = load_store()

    for stored in store["assessments"]:
        if str(stored.get("id")) == str(item.get("id")):
            stored["weightage_percent"] = weightage
            stored["course_credits"] = credits
            stored["total_marks"] = total_marks
            stored["updated_at"] = _now()
            break

    save_store(store)

    print("\nAcademic details updated.")


def record_assessment_result():
    item = choose_assessment(
        include_completed=True
    )

    if not item:
        return

    total_marks = _float_or_none(
        item.get("total_marks")
    )

    if total_marks is None or total_marks <= 0:
        print(
            "\nTotal marks are still unknown."
        )
        print(
            "Use Edit Weightage / Credits / Marks "
            "after the quiz paper/result is available."
        )
        return

    obtained = _ask_optional_float(
        f"Marks obtained out of {total_marks:g}",
        minimum=0.0,
        maximum=total_marks
    )

    if obtained is None:
        print("\nNo result entered.")
        return

    store = load_store()
    updated = None

    for stored in store["assessments"]:
        if str(stored.get("id")) == str(item.get("id")):
            stored["obtained_marks"] = obtained
            stored["updated_at"] = _now()
            updated = stored
            break

    save_store(store)

    print(
        f"\nSaved result: {obtained:g}/{total_marks:g}"
    )

    contribution = weighted_course_score_contribution(
        updated or item
    )

    weightage = assessment_weightage_percent(
        updated or item
    )

    if contribution is not None and weightage is not None:
        print(
            f"Weighted contribution to course score: "
            f"{contribution:g} out of {weightage:g} "
            "percentage points."
        )


def update_assessment_status():
    item = choose_assessment(
        include_completed=True
    )

    if not item:
        return

    print("\n1. pending")
    print("2. in_progress")
    print("3. completed")

    mapping = {
        "1": "pending",
        "2": "in_progress",
        "3": "completed",
    }

    choice = input(
        "\nNew status: "
    ).strip()

    status = mapping.get(choice)

    if not status:
        print("\nInvalid status.")
        return

    store = load_store()

    for stored in store["assessments"]:
        if str(stored.get("id")) == str(item.get("id")):
            stored["status"] = status
            stored["updated_at"] = _now()
            break

    save_store(store)

    print(
        f"\nStatus updated to {status}."
    )


def delete_assessment():
    item = choose_assessment(
        include_completed=True
    )

    if not item:
        return

    confirm = input(
        f"\nDelete '{item['title']}'? "
        "Type yes to confirm: "
    ).strip().lower()

    if confirm != "yes":
        print("\nDelete cancelled.")
        return

    store = load_store()

    store["assessments"] = [
        stored
        for stored in store["assessments"]
        if str(stored.get("id"))
        != str(item.get("id"))
    ]

    save_store(store)

    print("\nAssessment deleted.")


def recommended_minutes_per_day(days_left):
    if days_left is None:
        return 45
    if days_left <= 0:
        return 120
    if days_left <= 2:
        return 90
    if days_left <= 7:
        return 60
    if days_left <= 14:
        return 45
    return 30


def show_preparation_plan():
    item = choose_assessment(
        include_completed=False
    )

    if not item:
        return

    course = find_course(
        item.get("course_id")
    )

    if not course:
        print("\nCourse not found.")
        return

    days = days_until(
        item.get("due_date")
    )

    ranked = rank_course_topics(
        course["id"],
        limit=8
    )

    explicit_topics = [
        topic.lower()
        for topic in item.get(
            "topics",
            []
        )
    ]

    if explicit_topics:
        focused = [
            topic
            for topic in ranked
            if any(
                key in topic.get(
                    "name",
                    ""
                ).lower()
                or topic.get(
                    "name",
                    ""
                ).lower() in key
                for key in explicit_topics
            )
        ]

        if focused:
            ranked = focused + [
                topic
                for topic in ranked
                if topic not in focused
            ]

    print(
        "\n========== PREPARATION PLAN =========="
    )

    print(
        f"Assessment : {item['title']}"
    )
    print(
        f"Course     : "
        f"{course['code']} - "
        f"{course['name']}"
    )
    print(
        f"Type       : {item['type']}"
    )
    print(
        f"Due        : {item['due_date']}"
    )

    if days is not None:
        print(
            f"Days left  : {days}"
        )

    print(
        f"Suggested daily time: "
        f"{recommended_minutes_per_day(days)} minutes"
    )

    if item.get("topics"):
        print(
            "\nAssessment focus:"
        )

        for topic in item["topics"]:
            print(
                f"- {topic}"
            )

    print(
        "\nCourse priorities:"
    )

    if ranked:
        for number, topic in enumerate(
            ranked[:5],
            start=1
        ):
            print(
                f"{number}. {topic.get('name')} "
                f"| {topic.get('status')} "
                f"| priority "
                f"{topic.get('priority_score', 0)}"
            )
    else:
        print(
            "- No unfinished priority topics found."
        )

    print(
        "\nSuggested structure:"
    )

    if item["type"] in {
        "midsem",
        "endsem",
        "exam",
        "quiz"
    }:
        print(
            "1. Recall concepts without notes."
        )
        print(
            "2. Repair weak topics using course sources."
        )
        print(
            "3. Solve representative questions."
        )
        print(
            "4. Review mistakes, not just correct answers."
        )
        print(
            "5. Finish with a timed/self-check session."
        )

    elif item["type"] == "assignment":
        print(
            "1. Read the complete assignment first."
        )
        print(
            "2. Map every question to its topic."
        )
        print(
            "3. Review only the required concepts."
        )
        print(
            "4. Solve independently before asking AI."
        )
        print(
            "5. Verify formatting, outputs and submission requirements."
        )

    elif item["type"] == "lab":
        print(
            "1. Understand the experiment/task objective."
        )
        print(
            "2. Review the method/code before the lab."
        )
        print(
            "3. Predict expected outputs or observations."
        )
        print(
            "4. Prepare common errors and debugging checks."
        )

    else:
        print(
            "1. Break the work into small deliverables."
        )
        print(
            "2. Start the highest-risk part first."
        )
        print(
            "3. Leave time for testing/revision."
        )


def source_grounded_assessment_help():
    item = choose_assessment(
        include_completed=False
    )

    if not item:
        return

    course = find_course(
        item.get("course_id")
    )

    if not course:
        print("\nCourse not found.")
        return

    semantic_chunks = load_semantic_index()

    if semantic_chunks is None:
        print(
            "\nNo semantic index available."
        )
        return

    if not llm_is_configured():
        print(
            "\nLLM is not configured."
        )
        return

    topic_text = (
        ", ".join(
            item.get("topics", [])
        )
        or "not explicitly specified"
    )

    question = (
        f"I am preparing for my {item['type']} "
        f"'{item['title']}' in {course['code']} "
        f"{course['name']}. "
        f"The assessment focus is: {topic_text}. "
        f"Due date: {item['due_date']}. "
        "Using only my selected course sources and stored course progress, "
        "tell me what I should study, what I should practice, "
        "which weak areas deserve priority, and give me a short preparation checklist. "
        "Do not invent syllabus content that is absent from my course sources."
    )

    try:
        answer, results = rag_answer(
            question,
            semantic_chunks,
            course_id=course["id"],
            mode_instruction=(
                "Act as an assessment preparation coach. "
                "Stay strictly grounded in the selected course sources. "
                "Prioritize the named assessment topics when those topics "
                "are supported by the retrieved material."
            )
        )
    except Exception as error:
        print(
            f"\nAssessment assistant failed: {error}"
        )
        return

    if answer is None:
        print(
            "\nI could not find enough course material "
            "for this assessment."
        )
        return

    print(
        "\n========== SOURCE-GROUNDED ASSESSMENT HELP =========="
    )

    print(
        clean_terminal_markdown(
            answer
        )
    )

    print_verified_sources(
        results
    )


def show_course_progress_for_assessment():
    item = choose_assessment(
        include_completed=False
    )

    if not item:
        return

    course = find_course(
        item.get("course_id")
    )

    if not course:
        print("\nCourse not found.")
        return

    print_progress_dashboard(
        course["id"]
    )


def assignment_exam_menu():
    while True:
        print(
            "\n========== V11.1 ASSIGNMENT & EXAM ASSISTANT =========="
        )
        print("1. Add Assignment / Quiz / Exam")
        print("2. View Upcoming Assessments")
        print("3. Update Assessment Status")
        print("4. Edit Weightage / Credits / Marks")
        print("5. Record Assessment Result")
        print("6. Preparation Plan")
        print("7. Source-Grounded AI Preparation Help")
        print("8. View Course Progress for an Assessment")
        print("9. Delete Assessment")
        print("10. Back")

        choice = input(
            "\nEnter your choice (1-10): "
        ).strip()

        if choice == "1":
            add_assessment()
        elif choice == "2":
            print_upcoming()
        elif choice == "3":
            update_assessment_status()
        elif choice == "4":
            edit_assessment_academic_details()
        elif choice == "5":
            record_assessment_result()
        elif choice == "6":
            show_preparation_plan()
        elif choice == "7":
            source_grounded_assessment_help()
        elif choice == "8":
            show_course_progress_for_assessment()
        elif choice == "9":
            delete_assessment()
        elif choice == "10":
            break
        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 10."
            )


if __name__ == "__main__":
    assignment_exam_menu()
