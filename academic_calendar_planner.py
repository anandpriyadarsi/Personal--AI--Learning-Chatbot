"""V12.2 Academic Calendar + Deadline Planner.

Unifies:
- course assessments and deadlines
- assessment weightage / credits
- intelligent study priorities
- 7-day and 30-day academic views
- overload detection
- exam countdowns
- recommended study blocks around deadlines

This module is advisory and read-only. It does not modify assessment dates,
course mastery, or grades.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from course_manager import find_course
from assignment_exam_assistant import (
    list_assessments,
    assessment_priority,
    assessment_weightage_percent,
    assessment_course_credits,
    days_until,
)
from intelligent_study_planner import (
    relevant_courses,
    build_global_tasks,
)


WEEK_WINDOW = 7
MONTH_WINDOW = 30


def _today():
    return date.today()


def _parse_date(text):
    try:
        return datetime.strptime(
            str(text),
            "%Y-%m-%d"
        ).date()
    except Exception:
        return None


def _course_code(item):
    course = find_course(
        item.get("course_id")
    )

    if not course:
        return "COURSE"

    return course.get(
        "code",
        "COURSE"
    )


def _timing_text(item):
    remaining = days_until(
        item.get("due_date", "")
    )

    if remaining is None:
        return "date unknown"

    if remaining < 0:
        return (
            f"OVERDUE by "
            f"{abs(remaining)} day(s)"
        )

    if remaining == 0:
        return "DUE TODAY"

    if remaining == 1:
        return "due tomorrow"

    return f"due in {remaining} days"


def pending_assessments():
    return list_assessments(
        include_completed=False
    )


def assessments_in_window(days):
    start = _today()
    end = start + timedelta(
        days=days
    )

    rows = []

    for item in pending_assessments():
        due = _parse_date(
            item.get("due_date")
        )

        if due is None:
            continue

        if start <= due <= end:
            rows.append(item)

    rows.sort(
        key=lambda item: (
            _parse_date(
                item.get("due_date")
            ),
            -assessment_priority(
                item
            ),
        )
    )

    return rows


def deadline_pressure(item):
    """
    Relative planning pressure from deadline + academic impact.
    Not an official academic score.
    """
    base = float(
        assessment_priority(
            item
        )
    )

    remaining = days_until(
        item.get("due_date", "")
    )

    if remaining is None:
        countdown_bonus = 0
    elif remaining < 0:
        countdown_bonus = 35
    elif remaining == 0:
        countdown_bonus = 30
    elif remaining <= 2:
        countdown_bonus = 24
    elif remaining <= 5:
        countdown_bonus = 16
    elif remaining <= 7:
        countdown_bonus = 10
    elif remaining <= 14:
        countdown_bonus = 5
    else:
        countdown_bonus = 0

    return round(
        base + countdown_bonus,
        1
    )


def print_week_calendar():
    rows = assessments_in_window(
        WEEK_WINDOW
    )

    print(
        "\n========== V12.2 NEXT 7 DAYS =========="
    )

    if not rows:
        print(
            "\nNo assessments due in the next 7 days."
        )
        return

    grouped = defaultdict(list)

    for item in rows:
        grouped[
            item["due_date"]
        ].append(
            item
        )

    for due_date in sorted(
        grouped.keys()
    ):
        parsed = _parse_date(
            due_date
        )

        day_name = (
            parsed.strftime("%A")
            if parsed
            else ""
        )

        print(
            f"\n--- {day_name} | "
            f"{due_date} ---"
        )

        for item in sorted(
            grouped[due_date],
            key=deadline_pressure,
            reverse=True
        ):
            weightage = (
                assessment_weightage_percent(
                    item
                )
            )

            print(
                f"- {_course_code(item)} | "
                f"{item['title']} "
                f"| {item.get('type')}"
            )

            print(
                f"  {_timing_text(item)} "
                f"| pressure {deadline_pressure(item)}"
            )

            if weightage is not None:
                print(
                    f"  Weightage: "
                    f"{weightage:g}% "
                    f"of final course grade"
                )


def print_month_calendar():
    rows = assessments_in_window(
        MONTH_WINDOW
    )

    print(
        "\n========== V12.2 NEXT 30 DAYS =========="
    )

    if not rows:
        print(
            "\nNo assessments due in the next 30 days."
        )
        return

    current_week = None

    for item in rows:
        due = _parse_date(
            item.get("due_date")
        )

        if due is None:
            continue

        week_start = (
            due
            - timedelta(
                days=due.weekday()
            )
        )

        if week_start != current_week:
            current_week = week_start

            print(
                f"\nWEEK OF "
                f"{week_start.isoformat()}"
            )

        weightage = (
            assessment_weightage_percent(
                item
            )
        )

        line = (
            f"- {item['due_date']} | "
            f"{_course_code(item)} | "
            f"{item['title']}"
        )

        if weightage is not None:
            line += (
                f" | {weightage:g}%"
            )

        print(line)


def print_deadline_countdowns():
    rows = pending_assessments()

    print(
        "\n========== DEADLINE COUNTDOWNS =========="
    )

    if not rows:
        print(
            "\nNo pending assessments."
        )
        return

    ranked = sorted(
        rows,
        key=deadline_pressure,
        reverse=True
    )

    for index, item in enumerate(
        ranked[:15],
        start=1
    ):
        weightage = (
            assessment_weightage_percent(
                item
            )

        )

        credits = (
            assessment_course_credits(
                item
            )
        )

        print(
            f"\n{index}. "
            f"{_course_code(item)} | "
            f"{item['title']}"
        )

        print(
            f"   {_timing_text(item)}"
        )

        if weightage is not None:
            print(
                f"   Weightage: "
                f"{weightage:g}%"
            )

        if credits is not None:
            print(
                f"   Course credits: "
                f"{credits:g}"
            )

        print(
            f"   Planning pressure: "
            f"{deadline_pressure(item)}"
        )


def workload_by_date(days=14):
    start = _today()
    end = start + timedelta(
        days=days
    )

    grouped = defaultdict(list)

    for item in pending_assessments():
        due = _parse_date(
            item.get("due_date")
        )

        if (
            due is not None
            and start <= due <= end
        ):
            grouped[due].append(
                item
            )

    return grouped


def print_overload_report():
    grouped = workload_by_date(
        days=14
    )

    print(
        "\n========== OVERLOAD REPORT: NEXT 14 DAYS =========="
    )

    if not grouped:
        print(
            "\nNo deadlines in the next 14 days."
        )
        return

    overloaded = []

    for due, items in grouped.items():
        total_pressure = sum(
            deadline_pressure(item)
            for item in items
        )

        total_weight = sum(
            assessment_weightage_percent(
                item
            )
            or 0.0
            for item in items
        )

        if (
            len(items) >= 2
            or total_pressure >= 160
            or total_weight >= 25
        ):
            overloaded.append(
                (
                    due,
                    items,
                    total_pressure,
                    total_weight
                )
            )

    if not overloaded:
        print(
            "\nNo major overload signal detected."
        )
        return

    overloaded.sort(
        key=lambda row: (
            row[2],
            row[3]
        ),
        reverse=True
    )

    for due, items, pressure, weight in overloaded:
        print(
            f"\n{due.isoformat()} "
            f"({due.strftime('%A')})"
        )

        print(
            f"Deadlines: {len(items)}"
        )

        print(
            f"Combined pressure: "
            f"{pressure:.1f}"
        )

        if weight > 0:
            print(
                f"Combined tracked weightage: "
                f"{weight:.1f}%"
            )

        for item in items:
            print(
                f"- {_course_code(item)} | "
                f"{item['title']}"
            )


def recommended_blocks_for_assessment(
    item
):
    remaining = days_until(
        item.get("due_date", "")
    )

    weightage = (
        assessment_weightage_percent(
            item
        )
        or 0.0
    )

    if remaining is None:
        return []

    if remaining < 0:
        return [
            (
                _today(),
                90,
                "Immediate overdue recovery"
            )
        ]

    if remaining == 0:
        return [
            (
                _today(),
                90,
                "Final preparation / completion"
            )
        ]

    if remaining == 1:
        pattern = [
            (0, 75, "Main preparation"),
        ]

    elif remaining <= 3:
        pattern = [
            (0, 60, "Core preparation"),
            (
                max(
                    0,
                    remaining - 1
                ),
                60,
                "Final review"
            ),
        ]

    elif remaining <= 7:
        pattern = [
            (0, 45, "Start preparation"),
            (
                max(
                    1,
                    remaining // 2
                ),
                60,
                "Practice / progress"),
            (
                remaining - 1,
                60,
                "Final review"
            ),
        ]

    else:
        pattern = [
            (0, 30, "Initial setup"),
            (
                max(
                    2,
                    remaining - 7
                ),
                45,
                "Early preparation"),
            (
                max(
                    3,
                    remaining - 3
                ),
                60,
                "Focused practice"),
            (
                remaining - 1,
                60,
                "Final review"
            ),
        ]

    multiplier = 1.0

    if weightage >= 25:
        multiplier = 1.5

    elif weightage >= 15:
        multiplier = 1.25

    blocks = []

    due = _parse_date(
        item.get("due_date")
    )

    if due is None:
        return []

    for offset, minutes, label in pattern:
        block_date = (
            _today()
            + timedelta(
                days=offset
            )
        )

        if block_date >= due:
            block_date = (
                due
                - timedelta(
                    days=1
                )
            )

        if block_date < _today():
            block_date = _today()

        blocks.append(
            (
                block_date,
                round(
                    minutes
                    * multiplier
                ),
                label
            )
        )

    return blocks


def print_deadline_study_plan():
    rows = assessments_in_window(
        14
    )

    print(
        "\n========== DEADLINE-AWARE STUDY BLOCKS =========="
    )

    if not rows:
        print(
            "\nNo assessments due in the next 14 days."
        )
        return

    schedule = defaultdict(list)

    for item in rows:
        for block_date, minutes, label in (
            recommended_blocks_for_assessment(
                item
            )
        ):
            schedule[
                block_date
            ].append(
                {
                    "assessment": item,
                    "minutes": minutes,
                    "label": label,
                }
            )

    for block_date in sorted(
        schedule.keys()
    ):
        print(
            f"\n--- "
            f"{block_date.strftime('%A')} | "
            f"{block_date.isoformat()} ---"
        )

        total = 0

        for entry in sorted(
            schedule[
                block_date
            ],
            key=lambda row: deadline_pressure(
                row["assessment"]
            ),
            reverse=True
        ):
            item = entry[
                "assessment"
            ]

            total += entry[
                "minutes"
            ]

            print(
                f"- {_course_code(item)} | "
                f"{item['title']} | "
                f"{entry['minutes']} min"
            )

            print(
                f"  {entry['label']} "
                f"| {_timing_text(item)}"
            )

        print(
            f"  Planned academic load: "
            f"{total} min"
        )

        if total > 180:
            print(
                "  WARNING: heavy planned load; "
                "consider starting one task earlier."
            )


def print_priority_calendar():
    tasks = build_global_tasks(
        relevant_courses()
    )

    print(
        "\n========== CALENDAR + STUDY PRIORITY VIEW =========="
    )

    if not tasks:
        print(
            "\nNo unresolved study priorities found."
        )
        return

    print(
        "\nTop study priorities right now:"
    )

    for number, task in enumerate(
        tasks[:8],
        start=1
    ):
        print(
            f"{number}. "
            f"{task['course_code']} | "
            f"{task['topic']} "
            f"| score {task['score']}"
        )

        if task.get(
            "assessments"
        ):
            print(
                "   Linked assessment: "
                + ", ".join(
                    task[
                        "assessments"
                    ][
                        :2
                    ]
                )
            )

        if task.get(
            "reasons"
        ):
            print(
                "   Why: "
                + "; ".join(
                    task[
                        "reasons"
                    ][
                        :3
                    ]
                )
            )


def print_free_buffer_days():
    horizon = 14
    grouped = workload_by_date(
        days=horizon
    )

    print(
        "\n========== BUFFER DAYS: NEXT 14 DAYS =========="
    )

    buffer_days = []

    for offset in range(
        horizon + 1
    ):
        current = (
            _today()
            + timedelta(
                days=offset
            )
        )

        if current not in grouped:
            buffer_days.append(
                current
            )

    if not buffer_days:
        print(
            "\nNo deadline-free days found."
        )
        return

    for day in buffer_days:
        print(
            f"- {day.strftime('%A')} "
            f"{day.isoformat()}"
        )


def academic_calendar_menu():
    while True:
        print(
            "\n========== V12.2 ACADEMIC CALENDAR + DEADLINE PLANNER =========="
        )

        print(
            "1. Next 7 Days"
        )
        print(
            "2. Next 30 Days"
        )
        print(
            "3. Deadline Countdowns"
        )
        print(
            "4. Overload Report"
        )
        print(
            "5. Deadline-Aware Study Blocks"
        )
        print(
            "6. Calendar + Study Priority View"
        )
        print(
            "7. Buffer / Deadline-Free Days"
        )
        print(
            "8. Back"
        )

        choice = input(
            "\nEnter your choice (1-8): "
        ).strip()

        if choice == "1":
            print_week_calendar()

        elif choice == "2":
            print_month_calendar()

        elif choice == "3":
            print_deadline_countdowns()

        elif choice == "4":
            print_overload_report()

        elif choice == "5":
            print_deadline_study_plan()

        elif choice == "6":
            print_priority_calendar()

        elif choice == "7":
            print_free_buffer_days()

        elif choice == "8":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 8."
            )


if __name__ == "__main__":
    academic_calendar_menu()
