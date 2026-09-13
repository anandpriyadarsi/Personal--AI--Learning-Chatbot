"""V9.2 Multi-Course Weekly Planner.

Combines several V9/V9.1 course plans into one balanced 7-day academic plan.
It uses the existing V8 course catalogue, V9 priority engine, and V9.1 study
actions. It does not automatically mark topics as mastered.
"""

import json
import os
from datetime import date, datetime, timedelta

from knowledge_paths import BASE_DIR
from course_manager import choose_course, find_course
from academic_progress import (
    rank_course_topics,
    get_course_snapshots,
    record_progress_snapshot,
)
from weekly_planner import action_for_topic


DATA_DIR = os.path.join(BASE_DIR, "data")
MULTI_PLANS_FILE = os.path.join(
    DATA_DIR,
    "multi_course_weekly_plans.json"
)

PLAN_VERSION = 1
MAX_SAVED_PLANS = 20

DEFAULT_WEEKLY_MINUTES = 600
MIN_WEEKLY_MINUTES = 120
MAX_WEEKLY_MINUTES = 3000

DEFAULT_STUDY_DAYS = 6
MIN_COURSES = 2
MAX_COURSES = 8

MIN_COURSE_SHARE = 0.12
MAX_COURSE_SHARE = 0.45


def _today():
    return date.today()


def _now():
    return datetime.now().isoformat(
        timespec="seconds"
    )


def default_store():
    return {
        "version": PLAN_VERSION,
        "plans": []
    }


def load_store():
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    if not os.path.exists(
        MULTI_PLANS_FILE
    ):
        return default_store()

    try:
        with open(
            MULTI_PLANS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

    except (
        json.JSONDecodeError,
        OSError
    ):
        return default_store()

    if not isinstance(data, dict):
        return default_store()

    plans = data.get(
        "plans",
        []
    )

    if not isinstance(plans, list):
        plans = []

    return {
        "version": PLAN_VERSION,
        "plans": plans[
            -MAX_SAVED_PLANS:
        ]
    }


def save_store(store):
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    temporary_file = (
        MULTI_PLANS_FILE
        + ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            store,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary_file,
        MULTI_PLANS_FILE
    )


def save_plan(plan):
    store = load_store()

    store["plans"].append(
        plan
    )

    store["plans"] = (
        store["plans"][
            -MAX_SAVED_PLANS:
        ]
    )

    save_store(
        store
    )


def latest_plan():
    plans = load_store()[
        "plans"
    ]

    if not plans:
        return None

    return plans[-1]


def _safe_int(value, default):
    try:
        return int(value)

    except (
        TypeError,
        ValueError
    ):
        return default


def ask_number_of_courses():
    raw = input(
        "\nHow many courses should this "
        "weekly plan include? [default 3]: "
    ).strip()

    if not raw:
        return 3

    value = _safe_int(
        raw,
        3
    )

    return max(
        MIN_COURSES,
        min(
            value,
            MAX_COURSES
        )
    )


def select_courses():
    count = ask_number_of_courses()
    selected = []
    selected_ids = set()

    print(
        "\nSelect courses one by one."
    )

    while len(selected) < count:
        course = choose_course(
            f"Select Course "
            f"{len(selected) + 1}/{count}"
        )

        if course is None:
            print(
                "\nCourse selection cancelled."
            )
            return []

        if course["id"] in selected_ids:
            print(
                "\nThat course is already selected. "
                "Choose a different course."
            )
            continue

        selected.append(
            course
        )

        selected_ids.add(
            course["id"]
        )

    return selected


def ask_weekly_minutes():
    raw = input(
        f"\nTotal study time available for "
        f"these courses this week in minutes "
        f"[default {DEFAULT_WEEKLY_MINUTES}]: "
    ).strip()

    if not raw:
        return DEFAULT_WEEKLY_MINUTES

    value = _safe_int(
        raw,
        DEFAULT_WEEKLY_MINUTES
    )

    return max(
        MIN_WEEKLY_MINUTES,
        min(
            value,
            MAX_WEEKLY_MINUTES
        )
    )


def ask_study_days():
    raw = input(
        "\nHow many study days in the next "
        "7 days? [default 6]: "
    ).strip()

    if not raw:
        return DEFAULT_STUDY_DAYS

    value = _safe_int(
        raw,
        DEFAULT_STUDY_DAYS
    )

    return max(
        1,
        min(
            value,
            7
        )
    )


def choose_active_days(number_of_days):
    patterns = {
        1: [0],
        2: [0, 4],
        3: [0, 3, 6],
        4: [0, 2, 4, 6],
        5: [0, 1, 3, 4, 6],
        6: [0, 1, 2, 3, 4, 6],
        7: list(range(7))
    }

    return patterns[
        number_of_days
    ]


def course_urgency(course):
    """
    Transparent urgency score based on the
    strongest unresolved topics in the course.
    """

    ranked = rank_course_topics(
        course["id"],
        limit=5
    )

    if not ranked:
        return 10.0, []

    scores = [
        float(
            item.get(
                "priority_score",
                0
            )
        )
        for item in ranked
    ]

    top_score = scores[0]
    average_top = (
        sum(scores)
        / len(scores)
    )

    urgency = (
        0.65 * top_score
        + 0.35 * average_top
    )

    return max(
        10.0,
        urgency
    ), ranked


def bounded_course_allocations(
    courses,
    total_minutes
):
    """
    Allocate time by urgency while preventing
    one course from consuming the entire week.
    """

    raw = []

    for course in courses:
        urgency, ranked = (
            course_urgency(
                course
            )
        )

        raw.append({
            "course": course,
            "urgency": urgency,
            "ranked": ranked
        })

    urgency_total = sum(
        item["urgency"]
        for item in raw
    )

    count = len(raw)

    if urgency_total <= 0:
        urgency_total = count

        for item in raw:
            item["urgency"] = 1

    min_minutes = int(
        total_minutes
        * MIN_COURSE_SHARE
    )

    max_minutes = int(
        total_minutes
        * MAX_COURSE_SHARE
    )

    # When many courses are selected, an equal
    # share may naturally be below 12%.
    min_minutes = min(
        min_minutes,
        total_minutes // count
    )

    allocations = []

    for item in raw:
        share = (
            item["urgency"]
            / urgency_total
        )

        minutes = round(
            total_minutes
            * share
        )

        minutes = max(
            min_minutes,
            min(
                minutes,
                max_minutes
            )
        )

        allocations.append({
            **item,
            "minutes": minutes
        })

    current_total = sum(
        item["minutes"]
        for item in allocations
    )

    difference = (
        total_minutes
        - current_total
    )

    # Correct rounding/caps in small steps.
    order = sorted(
        range(len(allocations)),
        key=lambda index: allocations[
            index
        ]["urgency"],
        reverse=True
    )

    while difference != 0:
        changed = False

        for index in order:
            item = allocations[
                index
            ]

            if difference > 0:
                if (
                    item["minutes"]
                    < max_minutes
                ):
                    item["minutes"] += 1
                    difference -= 1
                    changed = True

            else:
                if (
                    item["minutes"]
                    > min_minutes
                ):
                    item["minutes"] -= 1
                    difference += 1
                    changed = True

            if difference == 0:
                break

        if not changed:
            break

    return allocations


def build_course_sessions(
    allocation
):
    course = allocation["course"]
    ranked = allocation["ranked"]
    total_minutes = allocation[
        "minutes"
    ]

    if not ranked:
        return [{
            "course_id": course["id"],
            "course_code": course["code"],
            "course_name": course["name"],
            "topic": "Mixed revision",
            "status": "mastered",
            "priority_score": 0,
            "minutes": total_minutes,
            "actions": [
                "Do mixed recall from mastered topics",
                "Solve a small mixed practice set",
                "Only reopen a topic if recall is weak"
            ]
        }]

    # Aim for sessions of roughly 45-75 minutes.
    session_count = max(
        1,
        round(
            total_minutes / 60
        )
    )

    session_count = min(
        session_count,
        max(
            1,
            len(ranked) + 1
        )
    )

    base_minutes = (
        total_minutes
        // session_count
    )

    remainder = (
        total_minutes
        % session_count
    )

    sessions = []

    for index in range(
        session_count
    ):
        topic = ranked[
            index % len(ranked)
        ]

        minutes = (
            base_minutes
            + (
                1
                if index < remainder
                else 0
            )
        )

        sessions.append({
            "course_id": course["id"],
            "course_code": course["code"],
            "course_name": course["name"],
            "topic": topic.get(
                "name",
                "Unnamed topic"
            ),
            "status": topic.get(
                "status",
                "not_started"
            ),
            "priority_score": topic.get(
                "priority_score",
                0
            ),
            "minutes": minutes,
            "actions": action_for_topic(
                topic,
                minutes
            )
        })

    return sessions


def distribute_sessions_across_days(
    sessions,
    study_days
):
    offsets = choose_active_days(
        study_days
    )

    start = _today()

    days = []

    for offset in offsets:
        current_date = (
            start
            + timedelta(
                days=offset
            )
        )

        days.append({
            "date": (
                current_date.isoformat()
            ),
            "day": (
                current_date.strftime(
                    "%A"
                )
            ),
            "total_minutes": 0,
            "sessions": []
        })

    # Long/high-priority sessions first.
    sessions = sorted(
        sessions,
        key=lambda session: (
            session.get(
                "priority_score",
                0
            ),
            session.get(
                "minutes",
                0
            )
        ),
        reverse=True
    )

    last_course_by_day = {
        index: None
        for index in range(
            len(days)
        )
    }

    for session in sessions:
        candidate_indexes = sorted(
            range(len(days)),
            key=lambda index: (
                (
                    last_course_by_day[
                        index
                    ]
                    == session[
                        "course_id"
                    ]
                ),
                days[
                    index
                ][
                    "total_minutes"
                ]
            )
        )

        target = candidate_indexes[
            0
        ]

        days[
            target
        ]["sessions"].append(
            session
        )

        days[
            target
        ][
            "total_minutes"
        ] += session[
            "minutes"
        ]

        last_course_by_day[
            target
        ] = session[
            "course_id"
        ]

    return days


def create_multi_course_plan(
    courses,
    total_minutes,
    study_days
):
    allocations = (
        bounded_course_allocations(
            courses,
            total_minutes
        )
    )

    all_sessions = []

    for allocation in allocations:
        record_progress_snapshot(
            allocation[
                "course"
            ][
                "id"
            ]
        )

        all_sessions.extend(
            build_course_sessions(
                allocation
            )
        )

    days = (
        distribute_sessions_across_days(
            all_sessions,
            study_days
        )
    )

    return {
        "version": PLAN_VERSION,
        "created_at": _now(),
        "start_date": (
            _today().isoformat()
        ),
        "study_days": study_days,
        "total_weekly_minutes": (
            total_minutes
        ),
        "courses": [
            {
                "course_id": item[
                    "course"
                ][
                    "id"
                ],
                "course_code": item[
                    "course"
                ][
                    "code"
                ],
                "course_name": item[
                    "course"
                ][
                    "name"
                ],
                "urgency_score": round(
                    item["urgency"],
                    1
                ),
                "allocated_minutes": (
                    item[
                        "minutes"
                    ]
                ),
                "priority_topics": [
                    {
                        "name": topic.get(
                            "name"
                        ),
                        "status": topic.get(
                            "status"
                        ),
                        "priority_score": (
                            topic.get(
                                "priority_score",
                                0
                            )
                        )
                    }
                    for topic in item[
                        "ranked"
                    ][
                        :3
                    ]
                ]
            }
            for item in allocations
        ],
        "days": days
    }


def print_multi_course_plan(plan):
    if not plan:
        print(
            "\nNo multi-course plan available."
        )
        return

    print(
        "\n========== V9.2 MULTI-COURSE WEEKLY PLAN =========="
    )

    print(
        f"Start date       : "
        f"{plan['start_date']}"
    )

    print(
        f"Study days       : "
        f"{plan['study_days']}/7"
    )

    print(
        f"Weekly study time: "
        f"{plan['total_weekly_minutes']} minutes"
    )

    print(
        "\nCOURSE TIME ALLOCATION"
    )

    for course in plan[
        "courses"
    ]:
        percent = round(
            100
            * course[
                "allocated_minutes"
            ]
            / plan[
                "total_weekly_minutes"
            ],
            1
        )

        print(
            f"- {course['course_code']} "
            f"{course['course_name']}: "
            f"{course['allocated_minutes']} min "
            f"({percent}%)"
        )

        priorities = course.get(
            "priority_topics",
            []
        )

        if priorities:
            names = ", ".join(
                topic["name"]
                for topic in priorities
            )

            print(
                f"  Priority: {names}"
            )

    for day in plan[
        "days"
    ]:
        print(
            f"\n--- {day['day']} | "
            f"{day['date']} | "
            f"{day['total_minutes']} min ---"
        )

        if not day[
            "sessions"
        ]:
            print(
                "Rest / buffer day"
            )
            continue

        for number, session in enumerate(
            day["sessions"],
            start=1
        ):
            print(
                f"{number}. "
                f"{session['course_code']} | "
                f"{session['topic']} | "
                f"{session['minutes']} min"
            )

            for action in session[
                "actions"
            ]:
                print(
                    f"   - {action}"
                )

    print(
        "\nPlanner rules:"
    )

    print(
        "- Weak/high-priority courses receive more time."
    )

    print(
        "- Every selected course still receives protected study time."
    )

    print(
        "- One course is prevented from consuming the whole week."
    )

    print(
        "- Studying does not automatically mark a topic mastered."
    )


def generate_multi_course_plan():
    courses = select_courses()

    if len(courses) < 2:
        print(
            "\nSelect at least two different courses."
        )
        return

    total_minutes = (
        ask_weekly_minutes()
    )

    study_days = (
        ask_study_days()
    )

    plan = create_multi_course_plan(
        courses,
        total_minutes,
        study_days
    )

    save_plan(
        plan
    )

    print_multi_course_plan(
        plan
    )

    print(
        "\nMulti-course weekly plan saved locally."
    )


def compare_course_pressure():
    courses = select_courses()

    if len(courses) < 2:
        return

    rows = []

    for course in courses:
        urgency, ranked = (
            course_urgency(
                course
            )
        )

        top_topic = (
            ranked[0]["name"]
            if ranked
            else "No urgent unfinished topic"
        )

        rows.append(
            (
                urgency,
                course,
                top_topic
            )
        )

    rows.sort(
        key=lambda row: row[0],
        reverse=True
    )

    print(
        "\n========== COURSE PRESSURE COMPARISON =========="
    )

    for number, (
        urgency,
        course,
        top_topic
    ) in enumerate(
        rows,
        start=1
    ):
        print(
            f"{number}. "
            f"{course['code']} - "
            f"{course['name']}"
        )

        print(
            f"   Urgency score: "
            f"{urgency:.1f}"
        )

        print(
            f"   Highest-priority topic: "
            f"{top_topic}"
        )


def multi_course_planner_menu():
    while True:
        print(
            "\n========== V9.2 MULTI-COURSE PLANNER =========="
        )

        print(
            "1. Generate Balanced Multi-Course Plan"
        )

        print(
            "2. View Latest Multi-Course Plan"
        )

        print(
            "3. Compare Course Pressure"
        )

        print(
            "4. Back"
        )

        choice = input(
            "\nEnter your choice (1-4): "
        ).strip()

        if choice == "1":
            generate_multi_course_plan()

        elif choice == "2":
            plan = latest_plan()

            if plan is None:
                print(
                    "\nNo saved multi-course plan yet."
                )

            else:
                print_multi_course_plan(
                    plan
                )

        elif choice == "3":
            compare_course_pressure()

        elif choice == "4":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 4."
            )


if __name__ == "__main__":
    multi_course_planner_menu()
