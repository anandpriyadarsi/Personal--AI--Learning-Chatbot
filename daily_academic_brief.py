"""V12.3 Daily Academic Brief 2.0.

Creates one compact, explainable daily briefing from:
- today's and near-term deadlines
- assessment weightage / credits
- V11 study priorities
- V12 academic risk signals
- V12.2 deadline-aware study blocks
- weak assessment evidence

The brief is advisory. It does not modify deadlines, mastery, grades, or memory.
"""

from datetime import date

from course_manager import find_course
from assignment_exam_assistant import (
    list_assessments,
    assessment_weightage_percent,
    days_until,
)
from academic_intelligence_dashboard import (
    _latest_weak_evidence,
    _safe_progress,
)
from academic_calendar_planner import (
    deadline_pressure,
    recommended_blocks_for_assessment,
)
from intelligent_study_planner import (
    relevant_courses,
    build_global_tasks,
)


def _today():
    return date.today()


def _course_code(item):
    course = find_course(
        item.get("course_id")
    )

    return (
        course.get("code")
        if course
        else "COURSE"
    )


def _due_label(item):
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


def _urgent_assessments():
    rows = []

    for item in list_assessments(
        include_completed=False
    ):
        remaining = days_until(
            item.get("due_date", "")
        )

        if (
            remaining is not None
            and remaining <= 3
        ):
            rows.append(item)

    rows.sort(
        key=deadline_pressure,
        reverse=True
    )

    return rows


def _today_blocks():
    blocks = []

    for item in list_assessments(
        include_completed=False
    ):
        for block_date, minutes, label in (
            recommended_blocks_for_assessment(
                item
            )
        ):
            if block_date == _today():
                blocks.append({
                    "assessment": item,
                    "minutes": minutes,
                    "label": label,
                })

    blocks.sort(
        key=lambda row: deadline_pressure(
            row["assessment"]
        ),
        reverse=True
    )

    return blocks


def _top_risks(limit=3):
    rows = []

    for course in relevant_courses():
        progress = _safe_progress(
            course["id"]
        )

        weak_topics = progress.get(
            "weak_topics",
            []
        )

        evidence = _latest_weak_evidence(
            course["id"],
            limit=5
        )

        urgent = []

        for item in list_assessments(
            include_completed=False
        ):
            if str(
                item.get("course_id")
            ) != str(
                course["id"]
            ):
                continue

            remaining = days_until(
                item.get("due_date", "")
            )

            if (
                remaining is not None
                and remaining <= 7
            ):
                urgent.append(item)

        score = (
            len(weak_topics) * 12
            + len(evidence) * 18
            + len(urgent) * 15
        )

        if urgent:
            score += max(
                deadline_pressure(
                    item
                )
                for item in urgent
            ) * 0.20

        rows.append({
            "course": course,
            "score": round(
                score,
                1
            ),
            "weak_topics": weak_topics,
            "evidence": evidence,
            "urgent": urgent,
        })

    rows.sort(
        key=lambda row: row["score"],
        reverse=True
    )

    return rows[:limit]


def _brief_actions():
    tasks = build_global_tasks(
        relevant_courses()
    )

    return tasks[:5]


def print_daily_brief():
    urgent = _urgent_assessments()
    blocks = _today_blocks()
    risks = _top_risks()
    tasks = _brief_actions()

    print(
        "\n========== V12.3 DAILY ACADEMIC BRIEF 2.0 =========="
    )
    print(
        f"Date: {_today().isoformat()}"
    )

    if urgent:
        print(
            "\n1. DEADLINE ALERTS"
        )

        for item in urgent[:5]:
            weightage = (
                assessment_weightage_percent(
                    item
                )
            )

            line = (
                f"- {_course_code(item)} | "
                f"{item['title']} "
                f"| {_due_label(item)}"
            )

            if weightage is not None:
                line += (
                    f" | {weightage:g}% weight"
                )

            print(line)

    else:
        print(
            "\n1. DEADLINE ALERTS"
        )
        print(
            "- No assessment due within 3 days."
        )

    print(
        "\n2. TODAY'S REQUIRED STUDY BLOCKS"
    )

    if blocks:
        total = 0

        for block in blocks[:6]:
            item = block[
                "assessment"
            ]

            total += block[
                "minutes"
            ]

            print(
                f"- {_course_code(item)} | "
                f"{item['title']} | "
                f"{block['minutes']} min"
            )
            print(
                f"  {block['label']} "
                f"| {_due_label(item)}"
            )

        print(
            f"Total scheduled: "
            f"{total} min"
        )

    else:
        print(
            "- No deadline-based block is required today."
        )

    print(
        "\n3. TOP STUDY PRIORITIES"
    )

    if tasks:
        for index, task in enumerate(
            tasks[:3],
            start=1
        ):
            print(
                f"{index}. "
                f"{task['course_code']} | "
                f"{task['topic']} "
                f"| score {task['score']}"
            )

            reasons = []

            for reason in task.get(
                "reasons",
                []
            ):
                if (
                    reason
                    and reason not in reasons
                ):
                    reasons.append(
                        reason
                    )

            if reasons:
                print(
                    "   Why: "
                    + "; ".join(
                        reasons[:3]
                    )
                )

    else:
        print(
            "- No unresolved study priority found."
        )

    print(
        "\n4. ACADEMIC RISK WATCH"
    )

    meaningful = [
        row
        for row in risks
        if row["score"] > 0
    ]

    if meaningful:
        for row in meaningful:
            course = row[
                "course"
            ]

            print(
                f"- {course['code']} - "
                f"{course['name']} "
                f"| risk {row['score']}"
            )

            details = []

            if row[
                "weak_topics"
            ]:
                details.append(
                    "weak: "
                    + ", ".join(
                        row[
                            "weak_topics"
                        ][
                            :2
                        ]
                    )
                )

            if row[
                "evidence"
            ]:
                details.append(
                    "weak evidence: "
                    + ", ".join(
                        item["topic"]
                        for item in row[
                            "evidence"
                        ][
                            :2
                        ]
                    )
                )

            if row[
                "urgent"
            ]:
                details.append(
                    "urgent assessment"
                )

            if details:
                print(
                    "  "
                    + "; ".join(
                        details
                    )
                )

    else:
        print(
            "- No major academic risk signal."
        )

    print(
        "\n5. BEST NEXT ACTION"
    )

    if tasks:
        top = tasks[0]

        print(
            f"Start with: "
            f"{top['course_code']} | "
            f"{top['topic']}"
        )

        if top.get(
            "performance"
        ):
            performance = top[
                "performance"
            ]

            print(
                f"Evidence: "
                f"{performance['accuracy']}% "
                f"across "
                f"{performance['attempts']} attempt(s)"
            )

        print(
            "Reason: this currently has the highest "
            "combined academic priority."
        )

    elif blocks:
        item = blocks[0][
            "assessment"
        ]

        print(
            f"Start with: "
            f"{_course_code(item)} | "
            f"{item['title']}"
        )

    else:
        print(
            "No urgent action detected. "
            "Use the time for revision, projects, or rest."
        )


def daily_brief_menu():
    while True:
        print(
            "\n========== V12.3 DAILY ACADEMIC BRIEF 2.0 =========="
        )
        print(
            "1. Generate Today's Full Brief"
        )
        print(
            "2. Show Deadline Alerts Only"
        )
        print(
            "3. Show Today's Study Blocks Only"
        )
        print(
            "4. Show Top Study Priorities Only"
        )
        print(
            "5. Back"
        )

        choice = input(
            "\nEnter your choice (1-5): "
        ).strip()

        if choice == "1":
            print_daily_brief()

        elif choice == "2":
            rows = _urgent_assessments()

            print(
                "\n========== DEADLINE ALERTS =========="
            )

            if not rows:
                print(
                    "No assessment due within 3 days."
                )

            for item in rows:
                print(
                    f"- {_course_code(item)} | "
                    f"{item['title']} | "
                    f"{_due_label(item)}"
                )

        elif choice == "3":
            rows = _today_blocks()

            print(
                "\n========== TODAY'S STUDY BLOCKS =========="
            )

            if not rows:
                print(
                    "No deadline-based study block today."
                )

            for row in rows:
                item = row[
                    "assessment"
                ]

                print(
                    f"- {_course_code(item)} | "
                    f"{item['title']} | "
                    f"{row['minutes']} min "
                    f"| {row['label']}"
                )

        elif choice == "4":
            tasks = _brief_actions()

            print(
                "\n========== TOP STUDY PRIORITIES =========="
            )

            if not tasks:
                print(
                    "No unresolved priority found."
                )

            for index, task in enumerate(
                tasks[:5],
                start=1
            ):
                print(
                    f"{index}. "
                    f"{task['course_code']} | "
                    f"{task['topic']} "
                    f"| score {task['score']}"
                )

        elif choice == "5":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 5."
            )


if __name__ == "__main__":
    daily_brief_menu()
