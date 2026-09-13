"""V11 Intelligent Study Planner.

Combines:
- V9 course-topic priorities
- V10 assessment/deadline urgency
- V10.4 assessment performance evidence
- active-course context

It creates transparent daily and 7-day plans. It does not silently change
mastery, confidence, assessment status, or learning memory.
"""

import json
import os
from datetime import date, datetime, timedelta

from knowledge_paths import BASE_DIR
from course_manager import find_course, get_active_course, choose_course
from academic_progress import rank_course_topics
from assignment_exam_assistant import (
    list_assessments,
    assessment_priority,
    days_until,
)
from assessment_question_workspace import get_workspace
from assessment_performance import aggregate_topic_performance


DATA_DIR = os.path.join(BASE_DIR, "data")
STUDY_PLANS_FILE = os.path.join(
    DATA_DIR,
    "intelligent_study_plans.json"
)

PLAN_VERSION = 1
MAX_SAVED_PLANS = 30

DEFAULT_DAILY_MINUTES = 120
DEFAULT_WEEKLY_DAYS = 6
MIN_SESSION_MINUTES = 25
MAX_SESSION_MINUTES = 90


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
        STUDY_PLANS_FILE
    ):
        return default_store()

    try:
        with open(
            STUDY_PLANS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
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
        "plans": plans[-MAX_SAVED_PLANS:]
    }


def save_store(store):
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    temp = STUDY_PLANS_FILE + ".tmp"

    with open(
        temp,
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
        temp,
        STUDY_PLANS_FILE
    )


def save_plan(plan):
    store = load_store()
    store["plans"].append(plan)
    store["plans"] = store["plans"][-MAX_SAVED_PLANS:]
    save_store(store)


def latest_plan():
    plans = load_store()["plans"]
    return plans[-1] if plans else None


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ask_minutes(
    prompt,
    default=DEFAULT_DAILY_MINUTES,
    minimum=30,
    maximum=720
):
    raw = input(
        f"\n{prompt} [default {default}]: "
    ).strip()

    if not raw:
        return default

    value = _safe_int(raw, default)
    return max(
        minimum,
        min(value, maximum)
    )


def ask_weekly_days():
    raw = input(
        "\nHow many study days in the next 7 days? "
        f"[default {DEFAULT_WEEKLY_DAYS}]: "
    ).strip()

    if not raw:
        return DEFAULT_WEEKLY_DAYS

    return max(
        1,
        min(
            _safe_int(
                raw,
                DEFAULT_WEEKLY_DAYS
            ),
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
        7: list(range(7)),
    }

    return patterns[number_of_days]


def pending_assessments():
    return list_assessments(
        include_completed=False
    )


def relevant_courses():
    """
    Automatically include:
    - active course
    - courses with pending assessments
    """
    courses = []
    seen = set()

    active = get_active_course()

    if active:
        courses.append(active)
        seen.add(active["id"])

    for assessment in pending_assessments():
        course = find_course(
            assessment.get("course_id")
        )

        if course and course["id"] not in seen:
            courses.append(course)
            seen.add(course["id"])

    return courses


def topic_name_match(left, right):
    left = str(left or "").strip().lower()
    right = str(right or "").strip().lower()

    if not left or not right:
        return False

    return (
        left == right
        or left in right
        or right in left
    )


def course_assessments(course_id):
    return [
        item
        for item in pending_assessments()
        if str(item.get("course_id"))
        == str(course_id)
    ]


def performance_evidence_for_course(
    course_id
):
    evidence = {}

    for assessment in course_assessments(
        course_id
    ):
        workspace = get_workspace(
            assessment["id"],
            create=False
        )

        if not workspace:
            continue

        reports = aggregate_topic_performance(
            workspace
        )

        for report in reports:
            key = report["topic"].strip().lower()

            current = evidence.get(key)

            # Keep the report with most attempts,
            # then the lower accuracy if tied.
            if (
                current is None
                or report["attempts"] > current["attempts"]
                or (
                    report["attempts"] == current["attempts"]
                    and report["accuracy"] < current["accuracy"]
                )
            ):
                evidence[key] = report

    return evidence


def assessment_topic_bonus(
    topic_name,
    assessments
):
    bonus = 0
    reasons = []
    linked = []

    for assessment in assessments:
        urgency = assessment_priority(
            assessment
        )

        focus_topics = assessment.get(
            "topics",
            []
        )

        matched = any(
            topic_name_match(
                topic_name,
                focus
            )
            for focus in focus_topics
        )

        if matched:
            add = min(
                45,
                max(
                    12,
                    round(
                        urgency * 0.35
                    )
                )
            )

            bonus += add
            reasons.append(
                f"{assessment['title']} is approaching"
            )
            linked.append(
                assessment["title"]
            )

    return bonus, reasons, linked


def general_assessment_pressure(
    course_id
):
    assessments = course_assessments(
        course_id
    )

    if not assessments:
        return 0, [], []

    ranked = sorted(
        assessments,
        key=assessment_priority,
        reverse=True
    )

    top = ranked[0]
    urgency = assessment_priority(top)
    days = days_until(
        top.get("due_date", "")
    )

    bonus = min(
        30,
        max(
            5,
            round(
                urgency * 0.20
            )
        )
    )

    if days is None:
        timing = "upcoming"
    elif days < 0:
        timing = "overdue"
    elif days == 0:
        timing = "due today"
    else:
        timing = f"due in {days} day(s)"

    reasons = [
        f"{top['title']} is {timing}"
    ]

    return bonus, reasons, [
        top["title"]
    ]


def performance_bonus(
    topic_name,
    evidence
):
    for key, report in evidence.items():
        if topic_name_match(
            topic_name,
            key
        ):
            label = report.get(
                "evidence"
            )

            if label == "weak_evidence":
                return (
                    40,
                    [
                        "assessment evidence shows weakness"
                    ],
                    report
                )

            if label == "needs_more_practice":
                return (
                    20,
                    [
                        "assessment evidence needs more practice"
                    ],
                    report
                )

            if label == "insufficient_evidence":
                return (
                    6,
                    [
                        "limited assessment evidence"
                    ],
                    report
                )

            if label == "strong_evidence":
                return (
                    -12,
                    [
                        "recent assessment evidence is strong"
                    ],
                    report
                )

    return 0, [], None


def build_course_tasks(course):
    """
    Turn course progress, assessment pressure and performance evidence
    into ranked study-task candidates.
    """
    topics = rank_course_topics(
        course["id"],
        limit=12
    )

    assessments = course_assessments(
        course["id"]
    )

    evidence = (
        performance_evidence_for_course(
            course["id"]
        )
    )

    tasks = []

    for topic in topics:
        score = float(
            topic.get(
                "priority_score",
                0
            )
        )

        reasons = list(
            topic.get(
                "priority_reasons",
                []
            )
        )

        assessment_bonus, assessment_reasons, linked = (
            assessment_topic_bonus(
                topic.get("name"),
                assessments
            )
        )

        if not linked:
            general_bonus, general_reasons, general_linked = (
                general_assessment_pressure(
                    course["id"]
                )
            )
            assessment_bonus += general_bonus
            assessment_reasons.extend(
                general_reasons
            )
            linked.extend(
                general_linked
            )

        perf_bonus, perf_reasons, perf_report = (
            performance_bonus(
                topic.get("name"),
                evidence
            )
        )

        score += assessment_bonus
        score += perf_bonus

        reasons.extend(
            assessment_reasons
        )
        reasons.extend(
            perf_reasons
        )

        tasks.append({
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
            "score": round(
                max(0.0, score),
                1
            ),
            "reasons": reasons,
            "assessments": linked,
            "performance": (
                {
                    "attempts": perf_report.get(
                        "attempts"
                    ),
                    "accuracy": round(
                        perf_report.get(
                            "accuracy",
                            0.0
                        )
                        * 100
                    ),
                    "evidence": perf_report.get(
                        "evidence"
                    ),
                }
                if perf_report
                else None
            ),
        })

    # If a course has an assessment but no topic priorities,
    # create an assessment-work candidate.
    if not tasks and assessments:
        top = max(
            assessments,
            key=assessment_priority
        )

        tasks.append({
            "course_id": course["id"],
            "course_code": course["code"],
            "course_name": course["name"],
            "topic": (
                f"Assessment preparation: "
                f"{top['title']}"
            ),
            "status": "assessment",
            "score": float(
                max(
                    30,
                    assessment_priority(
                        top
                    )
                )
            ),
            "reasons": [
                "pending assessment needs progress"
            ],
            "assessments": [
                top["title"]
            ],
            "performance": None,
        })

    tasks.sort(
        key=lambda item: item[
            "score"
        ],
        reverse=True
    )

    return tasks


def build_global_tasks(
    courses=None
):
    if courses is None:
        courses = relevant_courses()

    tasks = []

    for course in courses:
        tasks.extend(
            build_course_tasks(
                course
            )
        )

    tasks.sort(
        key=lambda item: item[
            "score"
        ],
        reverse=True
    )

    return tasks


def default_actions(task):
    status = task.get(
        "status",
        "not_started"
    )

    topic = task[
        "topic"
    ]

    evidence = (
        task.get("performance")
        or {}
    )

    if (
        evidence.get("evidence")
        == "weak_evidence"
    ):
        return [
            f"Repair the exact weak point in {topic}",
            "Review one worked example from your course source",
            "Solve 2-3 questions without notes",
            "Compare mistakes with the previous failed/stuck attempts",
        ]

    if status == "weak":
        return [
            f"Relearn the core idea of {topic}",
            "Do one guided example",
            "Do 2 independent questions",
            "Write the confusion that remains",
        ]

    if status == "learning":
        return [
            f"Finish the current concept in {topic}",
            "Active-recall the method without notes",
            "Solve 2-3 practice questions",
        ]

    if status == "review":
        return [
            f"Recall {topic} from memory",
            "Check only what you forgot",
            "Solve 2 mixed/application questions",
        ]

    if status == "assessment":
        return [
            f"Work directly on {topic}",
            "Start with the highest-risk unfinished question",
            "Record any stuck point in the assessment workspace",
        ]

    return [
        f"Learn/revise {topic}",
        "Make a short active-recall summary",
        "Solve 2 basic questions",
    ]


def session_length(
    task,
    remaining_minutes
):
    score = task.get(
        "score",
        0
    )

    if score >= 100:
        desired = 75
    elif score >= 70:
        desired = 60
    elif score >= 45:
        desired = 45
    else:
        desired = 30

    desired = min(
        desired,
        MAX_SESSION_MINUTES,
        remaining_minutes
    )

    if (
        desired < MIN_SESSION_MINUTES
        and remaining_minutes >= MIN_SESSION_MINUTES
    ):
        desired = MIN_SESSION_MINUTES

    return desired


def choose_tasks_for_day(
    tasks,
    total_minutes,
    already_used=None
):
    if already_used is None:
        already_used = set()

    sessions = []
    remaining = total_minutes
    course_minutes = {}

    candidates = list(tasks)

    while (
        remaining >= MIN_SESSION_MINUTES
        and candidates
    ):
        # Balance urgency with avoiding one course monopolising the day.
        ranked = sorted(
            candidates,
            key=lambda task: (
                task["score"]
                - 0.12
                * course_minutes.get(
                    task["course_id"],
                    0
                ),
                (
                    task["course_id"],
                    task["topic"]
                )
                not in already_used,
            ),
            reverse=True
        )

        task = ranked[0]
        key = (
            task["course_id"],
            task["topic"]
        )

        minutes = session_length(
            task,
            remaining
        )

        if minutes < MIN_SESSION_MINUTES:
            break

        sessions.append({
            **task,
            "minutes": minutes,
            "actions": default_actions(
                task
            ),
        })

        remaining -= minutes

        course_minutes[
            task["course_id"]
        ] = (
            course_minutes.get(
                task["course_id"],
                0
            )
            + minutes
        )

        already_used.add(
            key
        )

        # Lower score temporarily so other tasks get a chance.
        task_copy = dict(task)
        task_copy["score"] = max(
            0,
            task["score"] - 35
        )

        candidates = [
            item
            for item in candidates
            if (
                item["course_id"],
                item["topic"]
            ) != key
        ]

        if (
            task_copy["score"] >= 30
            and remaining >= 45
        ):
            candidates.append(
                task_copy
            )

    return sessions, remaining


def create_today_plan(
    total_minutes
):
    courses = relevant_courses()

    if not courses:
        return None

    tasks = build_global_tasks(
        courses
    )

    if not tasks:
        return None

    sessions, unused = choose_tasks_for_day(
        tasks,
        total_minutes
    )

    return {
        "version": PLAN_VERSION,
        "kind": "today",
        "created_at": _now(),
        "date": _today().isoformat(),
        "available_minutes": total_minutes,
        "unused_minutes": unused,
        "courses": [
            {
                "id": course["id"],
                "code": course["code"],
                "name": course["name"],
            }
            for course in courses
        ],
        "sessions": sessions,
    }


def create_week_plan(
    minutes_per_day,
    study_days
):
    courses = relevant_courses()

    if not courses:
        return None

    tasks = build_global_tasks(
        courses
    )

    if not tasks:
        return None

    offsets = choose_active_days(
        study_days
    )

    days = []
    already_used = set()

    for day_number, offset in enumerate(
        offsets
    ):
        current = (
            _today()
            + timedelta(
                days=offset
            )
        )

        # End-week session leans slightly more toward unresolved tasks.
        day_tasks = [
            dict(task)
            for task in tasks
        ]

        if (
            day_number
            == len(offsets) - 1
            and len(offsets) >= 3
        ):
            for task in day_tasks:
                if task.get(
                    "performance"
                ):
                    task["score"] += 8

                if task.get(
                    "status"
                ) in {
                    "weak",
                    "review",
                }:
                    task["score"] += 8

        sessions, unused = choose_tasks_for_day(
            day_tasks,
            minutes_per_day,
            already_used=already_used
        )

        days.append({
            "date": current.isoformat(),
            "day": current.strftime(
                "%A"
            ),
            "available_minutes": minutes_per_day,
            "unused_minutes": unused,
            "sessions": sessions,
        })

    return {
        "version": PLAN_VERSION,
        "kind": "week",
        "created_at": _now(),
        "start_date": _today().isoformat(),
        "study_days": study_days,
        "minutes_per_day": minutes_per_day,
        "courses": [
            {
                "id": course["id"],
                "code": course["code"],
                "name": course["name"],
            }
            for course in courses
        ],
        "days": days,
    }


def print_session(
    session,
    number=None
):
    prefix = (
        f"{number}. "
        if number is not None
        else ""
    )

    print(
        f"{prefix}{session['course_code']} | "
        f"{session['topic']} | "
        f"{session['minutes']} min"
    )

    print(
        f"   Priority score: "
        f"{session['score']}"
    )

    if session.get(
        "reasons"
    ):
        unique_reasons = []

        for reason in session[
            "reasons"
        ]:
            if (
                reason
                and reason.lower()
                not in {
                    item.lower()
                    for item in unique_reasons
                }
            ):
                unique_reasons.append(
                    reason
                )

        print(
            "   Why: "
            + "; ".join(
                unique_reasons[:4]
            )
        )

    if session.get(
        "performance"
    ):
        performance = session[
            "performance"
        ]

        print(
            f"   Evidence: "
            f"{performance['accuracy']}% "
            f"across "
            f"{performance['attempts']} attempt(s) "
            f"({performance['evidence']})"
        )

    for action in session[
        "actions"
    ]:
        print(
            f"   - {action}"
        )


def print_today_plan(plan):
    if not plan:
        print(
            "\nNo study plan could be generated."
        )
        print(
            "Add/select an active course and/or "
            "create pending assessments first."
        )
        return

    print(
        "\n========== V11 TODAY'S INTELLIGENT STUDY PLAN =========="
    )

    print(
        f"Date: {plan['date']}"
    )
    print(
        f"Available time: "
        f"{plan['available_minutes']} minutes"
    )

    for index, session in enumerate(
        plan["sessions"],
        start=1
    ):
        print()
        print_session(
            session,
            number=index
        )

    if plan.get(
        "unused_minutes",
        0
    ) > 0:
        print(
            f"\nBuffer/rest: "
            f"{plan['unused_minutes']} minutes"
        )

    print(
        "\nRule: finishing a study session does not "
        "automatically mark a topic mastered."
    )


def print_week_plan(plan):
    if not plan:
        print(
            "\nNo weekly plan could be generated."
        )
        print(
            "Add/select an active course and/or "
            "create pending assessments first."
        )
        return

    print(
        "\n========== V11 INTELLIGENT 7-DAY STUDY PLAN =========="
    )

    print(
        f"Start date : "
        f"{plan['start_date']}"
    )
    print(
        f"Study days : "
        f"{plan['study_days']}/7"
    )
    print(
        f"Time/day   : "
        f"{plan['minutes_per_day']} minutes"
    )

    print("\nCourses considered:")
    for course in plan[
        "courses"
    ]:
        print(
            f"- {course['code']} - "
            f"{course['name']}"
        )

    for day in plan[
        "days"
    ]:
        print(
            f"\n--- {day['day']} | "
            f"{day['date']} ---"
        )

        if not day[
            "sessions"
        ]:
            print(
                "Rest / buffer / no unresolved priority found"
            )
            continue

        for index, session in enumerate(
            day["sessions"],
            start=1
        ):
            print_session(
                session,
                number=index
            )

        if day.get(
            "unused_minutes",
            0
        ) > 0:
            print(
                f"   Buffer: "
                f"{day['unused_minutes']} min"
            )

    print(
        "\nPlanner principle:"
    )
    print(
        "- Deadline pressure raises priority."
    )
    print(
        "- Weak assessment evidence raises priority."
    )
    print(
        "- Strong recent evidence reduces unnecessary repetition."
    )
    print(
        "- Course progress still controls the underlying topic order."
    )


def show_why_topic_is_priority():
    courses = relevant_courses()

    if not courses:
        print(
            "\nNo relevant courses found."
        )
        return

    tasks = build_global_tasks(
        courses
    )

    if not tasks:
        print(
            "\nNo unresolved study priorities found."
        )
        return

    print(
        "\n========== CURRENT STUDY PRIORITIES =========="
    )

    for index, task in enumerate(
        tasks[:12],
        start=1
    ):
        print(
            f"{index}. "
            f"{task['course_code']} | "
            f"{task['topic']} | "
            f"score {task['score']}"
        )

        if task.get(
            "reasons"
        ):
            print(
                "   "
                + "; ".join(
                    task[
                        "reasons"
                    ][
                        :4
                    ]
                )
            )


def add_extra_course_context():
    """
    Let the user temporarily make a course active if no assessment
    currently pulls it into V11.
    """
    course = choose_course(
        "Select Additional Study Course"
    )

    if not course:
        return

    print(
        f"\nSelected course: "
        f"{course['code']} - "
        f"{course['name']}"
    )
    print(
        "V11 automatically uses the active course plus "
        "courses with pending assessments."
    )
    print(
        "If this course should always appear, set it as "
        "the active course in Course Manager."
    )

    tasks = build_course_tasks(
        course
    )

    if not tasks:
        print(
            "\nNo unresolved priority topics were found."
        )
        return

    print(
        "\nTop priorities in this course:"
    )

    for index, task in enumerate(
        tasks[:5],
        start=1
    ):
        print(
            f"{index}. "
            f"{task['topic']} "
            f"| score {task['score']}"
        )


def generate_today():
    minutes = ask_minutes(
        "How many total study minutes do you have today?",
        default=DEFAULT_DAILY_MINUTES
    )

    plan = create_today_plan(
        minutes
    )

    if plan:
        save_plan(
            plan
        )

    print_today_plan(
        plan
    )


def generate_week():
    minutes = ask_minutes(
        "How many study minutes per study day?",
        default=DEFAULT_DAILY_MINUTES
    )

    days = ask_weekly_days()

    plan = create_week_plan(
        minutes,
        days
    )

    if plan:
        save_plan(
            plan
        )

    print_week_plan(
        plan
    )


def print_latest_plan():
    plan = latest_plan()

    if not plan:
        print(
            "\nNo V11 plan has been saved yet."
        )
        return

    if plan.get(
        "kind"
    ) == "today":
        print_today_plan(
            plan
        )
    else:
        print_week_plan(
            plan
        )


def intelligent_study_planner_menu():
    while True:
        print(
            "\n========== V11 INTELLIGENT STUDY PLANNER =========="
        )
        print(
            "1. Generate Today's Study Plan"
        )
        print(
            "2. Generate Intelligent 7-Day Plan"
        )
        print(
            "3. View Current Priority Queue"
        )
        print(
            "4. View Latest Saved V11 Plan"
        )
        print(
            "5. Inspect an Additional Course"
        )
        print(
            "6. Back"
        )

        choice = input(
            "\nEnter your choice (1-6): "
        ).strip()

        if choice == "1":
            generate_today()

        elif choice == "2":
            generate_week()

        elif choice == "3":
            show_why_topic_is_priority()

        elif choice == "4":
            print_latest_plan()

        elif choice == "5":
            add_extra_course_context()

        elif choice == "6":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 6."
            )


if __name__ == "__main__":
    intelligent_study_planner_menu()
