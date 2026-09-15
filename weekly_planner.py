"""V9.1 Intelligent Weekly Planner.

Turns V9 course progress and topic priorities into a practical 7-day plan.
The planner is deterministic and transparent: it uses stored topic status,
confidence, recent activity, and V9 priority scores. It does not silently mark
topics as mastered.
"""

import json
import os
from datetime import date, datetime, timedelta

from knowledge_paths import BASE_DIR
from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)
from personal_learning_assistant.repositories.structured_authority_router import (
    maybe_load_sqlite_structured_store,
    maybe_save_sqlite_structured_store,
)
from course_manager import choose_course, find_course, get_active_course
from academic_progress import (
    rank_course_topics,
    record_progress_snapshot,
    print_progress_dashboard,
)


DATA_DIR = os.path.join(BASE_DIR, "data")
PLANS_FILE = os.path.join(DATA_DIR, "weekly_study_plans.json")
PLAN_VERSION = 1
MAX_SAVED_PLANS = 30

DEFAULT_DAILY_MINUTES = 60
MIN_DAILY_MINUTES = 20
MAX_DAILY_MINUTES = 300


def _today():
    return date.today()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def default_store():
    return {
        "version": PLAN_VERSION,
        "plans": [],
    }


def load_store():
    routed = maybe_load_sqlite_structured_store("weekly_study_plans", PLANS_FILE)
    if routed is not None:
        plans = routed.get("plans", []) if isinstance(routed, dict) else []
        return {"version": PLAN_VERSION, "plans": plans[-MAX_SAVED_PLANS:] if isinstance(plans, list) else []}
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(PLANS_FILE):
        return default_store()

    try:
        with open(PLANS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return default_store()

    if not isinstance(data, dict):
        return default_store()

    plans = data.get("plans", [])
    if not isinstance(plans, list):
        plans = []

    return {
        "version": PLAN_VERSION,
        "plans": plans[-MAX_SAVED_PLANS:],
    }


def save_store(store):
    if maybe_save_sqlite_structured_store("weekly_study_plans", PLANS_FILE, store):
        return
    guard_legacy_structured_write(infer_authority_control_path(PLANS_FILE))
    os.makedirs(DATA_DIR, exist_ok=True)
    temporary = PLANS_FILE + ".tmp"

    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(store, file, indent=2, ensure_ascii=False)

    os.replace(temporary, PLANS_FILE)


def save_plan(plan):
    store = load_store()
    store["plans"].append(plan)
    store["plans"] = store["plans"][-MAX_SAVED_PLANS:]
    save_store(store)


def get_saved_plans(course_id=None):
    plans = load_store()["plans"]

    if course_id is None:
        return plans

    course = find_course(course_id)
    if course is None:
        return []

    return [
        plan for plan in plans
        if plan.get("course_id") == course["id"]
    ]


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ask_daily_minutes():
    raw = input(
        f"\nHow many minutes can you study this course per study day? "
        f"[default {DEFAULT_DAILY_MINUTES}]: "
    ).strip()

    if not raw:
        return DEFAULT_DAILY_MINUTES

    value = _safe_int(raw, DEFAULT_DAILY_MINUTES)
    value = max(MIN_DAILY_MINUTES, min(value, MAX_DAILY_MINUTES))

    if value != _safe_int(raw, DEFAULT_DAILY_MINUTES):
        print(f"Using {value} minutes per study day.")

    return value


def ask_study_days():
    raw = input(
        "\nHow many days do you want to study this course in the next 7 days? "
        "[default 5]: "
    ).strip()

    if not raw:
        return 5

    days = _safe_int(raw, 5)
    return max(1, min(days, 7))


def choose_active_days(number_of_days):
    """Spread study days across the next seven days instead of clustering them."""
    if number_of_days >= 7:
        return list(range(7))

    if number_of_days == 6:
        return [0, 1, 2, 3, 4, 6]
    if number_of_days == 5:
        return [0, 1, 3, 4, 6]
    if number_of_days == 4:
        return [0, 2, 4, 6]
    if number_of_days == 3:
        return [0, 3, 6]
    if number_of_days == 2:
        return [0, 4]
    return [0]


def action_for_topic(topic, minutes):
    status = str(topic.get("status") or "not_started").lower()
    topic_name = topic.get("name", "Unnamed topic")

    if status == "weak":
        steps = [
            f"Relearn the core idea of {topic_name}",
            "Do 2 guided/basic examples",
            "Do 2-3 questions without looking at notes",
            "Write one sentence explaining what was confusing",
        ]
    elif status == "learning":
        steps = [
            f"Finish the current concept in {topic_name}",
            "Write a short active-recall summary",
            "Solve 3 practice questions",
            "Check the mistakes immediately",
        ]
    elif status == "review":
        steps = [
            f"Recall {topic_name} without opening notes",
            "Check notes and repair what you forgot",
            "Solve 2 mixed/application questions",
        ]
    elif status == "practiced":
        steps = [
            f"Quickly recall the method for {topic_name}",
            "Solve 2 application questions independently",
            "Mark any repeated error as a weak point",
        ]
    else:
        steps = [
            f"Learn the first core idea of {topic_name}",
            "Make a very short concept note",
            "Solve 2 basic questions",
            "Stop and record confusion instead of rushing ahead",
        ]

    if minutes <= 30:
        return steps[:2]
    if minutes <= 60:
        return steps[:3]
    return steps


def build_session(topic, minutes, session_type="study"):
    return {
        "type": session_type,
        "topic": topic.get("name", "Unnamed topic"),
        "status": topic.get("status", "not_started"),
        "priority_score": topic.get("priority_score", 0),
        "minutes": minutes,
        "actions": action_for_topic(topic, minutes),
    }


def create_weekly_plan(course_id, daily_minutes=60, study_days=5):
    course = find_course(course_id)
    if course is None:
        return None

    ranked = rank_course_topics(course["id"], limit=10)

    if not ranked:
        return {
            "version": PLAN_VERSION,
            "created_at": _now(),
            "course_id": course["id"],
            "course_code": course["code"],
            "course_name": course["name"],
            "start_date": _today().isoformat(),
            "daily_minutes": daily_minutes,
            "study_days": study_days,
            "days": [],
            "message": (
                "All stored topics currently appear mastered. "
                "Use mixed revision and practice instead of adding new content."
            ),
        }

    offsets = choose_active_days(study_days)
    start = _today()
    days = []

    # The first priority topic appears twice when possible:
    # first to learn/repair, later to retrieve from memory.
    topic_cursor = 0

    for session_number, offset in enumerate(offsets):
        current_date = start + timedelta(days=offset)

        if session_number == len(offsets) - 1 and len(offsets) >= 3:
            # End-week consolidation session.
            primary = ranked[0]
            secondary = ranked[1] if len(ranked) > 1 else None

            actions = [
                f"Active recall: {primary['name']}",
                "Redo one problem that was previously difficult",
            ]
            if secondary:
                actions.append(
                    f"Quick mixed check: {secondary['name']}"
                )
            actions.append(
                "Update topic status/confidence only after checking performance"
            )

            days.append({
                "date": current_date.isoformat(),
                "day": current_date.strftime("%A"),
                "kind": "weekly_review",
                "total_minutes": daily_minutes,
                "sessions": [{
                    "type": "weekly_review",
                    "topic": primary["name"],
                    "status": primary.get("status", ""),
                    "priority_score": primary.get("priority_score", 0),
                    "minutes": daily_minutes,
                    "actions": actions,
                }],
            })
            continue

        primary = ranked[topic_cursor % len(ranked)]
        topic_cursor += 1

        sessions = []

        if daily_minutes >= 80 and len(ranked) > 1:
            first_minutes = int(daily_minutes * 0.7)
            second_minutes = daily_minutes - first_minutes
            sessions.append(
                build_session(primary, first_minutes)
            )

            secondary = ranked[topic_cursor % len(ranked)]
            topic_cursor += 1
            sessions.append(
                build_session(
                    secondary,
                    second_minutes,
                    session_type="short_review",
                )
            )
        else:
            sessions.append(
                build_session(primary, daily_minutes)
            )

        days.append({
            "date": current_date.isoformat(),
            "day": current_date.strftime("%A"),
            "kind": "study",
            "total_minutes": daily_minutes,
            "sessions": sessions,
        })

    return {
        "version": PLAN_VERSION,
        "created_at": _now(),
        "course_id": course["id"],
        "course_code": course["code"],
        "course_name": course["name"],
        "start_date": start.isoformat(),
        "daily_minutes": daily_minutes,
        "study_days": study_days,
        "priority_topics": [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "priority_score": item.get("priority_score"),
                "reasons": item.get("priority_reasons", []),
            }
            for item in ranked[:6]
        ],
        "days": days,
    }


def print_plan(plan):
    if not plan:
        print("\nCould not create a weekly plan.")
        return

    print(
        f"\n========== {plan['course_code']} INTELLIGENT WEEKLY PLAN =========="
    )
    print(f"Course       : {plan['course_name']}")
    print(f"Start date   : {plan['start_date']}")
    print(f"Study days   : {plan['study_days']}/7")
    print(f"Time/day     : {plan['daily_minutes']} minutes")

    if plan.get("message"):
        print(f"\n{plan['message']}")
        return

    priorities = plan.get("priority_topics", [])
    if priorities:
        print("\nThis week's priorities:")
        for number, topic in enumerate(priorities[:5], start=1):
            reasons = ", ".join(topic.get("reasons", [])) or "current priority"
            print(
                f"{number}. {topic['name']} "
                f"({topic['status']}, score {topic['priority_score']})"
            )
            print(f"   Why: {reasons}")

    for day in plan.get("days", []):
        print(
            f"\n--- {day['day']} | {day['date']} | "
            f"{day['total_minutes']} min ---"
        )

        for session_number, session in enumerate(day["sessions"], start=1):
            if len(day["sessions"]) > 1:
                print(
                    f"Session {session_number}: "
                    f"{session['topic']} ({session['minutes']} min)"
                )
            else:
                print(
                    f"Focus: {session['topic']} "
                    f"({session['minutes']} min)"
                )

            for action in session["actions"]:
                print(f"  - {action}")

    print("\nEnd-of-week rule:")
    print(
        "- Do not mark a topic mastered only because you studied it. "
        "Update mastery/confidence after recall or practice."
    )


def print_latest_plan(course_id):
    plans = get_saved_plans(course_id)

    if not plans:
        print("\nNo saved weekly plan exists for this course yet.")
        return

    print_plan(plans[-1])


def generate_and_save_plan(course):
    daily_minutes = ask_daily_minutes()
    study_days = ask_study_days()

    # Capture V9 state used for planning.
    record_progress_snapshot(course["id"])

    plan = create_weekly_plan(
        course["id"],
        daily_minutes=daily_minutes,
        study_days=study_days,
    )

    if plan is None:
        print("\nCould not generate a plan.")
        return

    save_plan(plan)
    print_plan(plan)
    print("\nWeekly plan saved locally.")


def _select_initial_course():
    active = get_active_course()

    if active:
        return active

    return choose_course(
        "Select Course for Weekly Planner"
    )


def weekly_planner_menu():
    course = _select_initial_course()

    if course is None:
        print(
            "\nNo course selected. "
            "Add/select a course in Course Manager first."
        )
        return

    while True:
        print(
            "\n========== V9.1 INTELLIGENT WEEKLY PLANNER =========="
        )
        print(
            f"Current course: {course['code']} - {course['name']}"
        )
        print("1. Generate New 7-Day Plan")
        print("2. View Latest Saved Plan")
        print("3. View Current Progress Before Planning")
        print("4. Change Course")
        print("5. Back")

        choice = input(
            "\nEnter your choice (1-5): "
        ).strip()

        if choice == "1":
            generate_and_save_plan(course)

        elif choice == "2":
            print_latest_plan(course["id"])

        elif choice == "3":
            print_progress_dashboard(course["id"])

        elif choice == "4":
            selected = choose_course(
                "Select Course for Weekly Planner"
            )
            if selected:
                course = selected

        elif choice == "5":
            break

        else:
            print(
                "\nInvalid choice. Please enter 1 to 5."
            )


if __name__ == "__main__":
    weekly_planner_menu()
