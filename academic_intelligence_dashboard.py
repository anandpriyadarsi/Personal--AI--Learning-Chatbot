"""V12 Academic Intelligence Dashboard.

Unifies the major academic systems already built:
- V9 course/topic progress
- V10 assessment and deadline tracking
- V10.4 performance evidence
- V11 intelligent study priorities

This dashboard is read-only by design. It summarizes and explains academic
state but does not silently alter mastery, assessment status, or learning memory.
"""

from datetime import date

from course_manager import find_course, get_active_course, choose_course
from academic_progress import get_course_progress, rank_course_topics
from assignment_exam_assistant import (
    list_assessments,
    assessment_priority,
    assessment_weightage_percent,
    assessment_course_credits,
    days_until,
)
from assessment_question_workspace import get_workspace
from assessment_performance import aggregate_topic_performance
from intelligent_study_planner import (
    relevant_courses,
    build_global_tasks,
    build_course_tasks,
)


def _bar(percent, width=20):
    try:
        value = float(percent)
    except (TypeError, ValueError):
        value = 0.0

    value = max(0.0, min(value, 100.0))

    filled = round(
        width * value / 100
    )

    return (
        "[" +
        "#" * filled +
        "-" * (width - filled) +
        "]"
    )


def _course_label(course):
    return (
        f"{course.get('code', 'COURSE')} - "
        f"{course.get('name', 'Unnamed Course')}"
    )


def _safe_progress(course_id):
    try:
        return get_course_progress(
            course_id
        ) or {}
    except Exception:
        return {}


def _assessment_timing(item):
    remaining = days_until(
        item.get("due_date", "")
    )

    if remaining is None:
        return item.get(
            "due_date",
            "date unknown"
        )

    if remaining < 0:
        return (
            f"OVERDUE by "
            f"{abs(remaining)} day(s)"
        )

    if remaining == 0:
        return "DUE TODAY"

    if remaining == 1:
        return "due tomorrow"

    return (
        f"due in {remaining} days"
    )


def _course_assessments(course_id):
    return [
        item
        for item in list_assessments(
            include_completed=False
        )
        if str(
            item.get("course_id")
        ) == str(course_id)
    ]


def _course_performance(course_id):
    reports = []

    for assessment in _course_assessments(
        course_id
    ):
        workspace = get_workspace(
            assessment.get("id"),
            create=False
        )

        if not workspace:
            continue

        for report in aggregate_topic_performance(
            workspace
        ):
            reports.append(
                {
                    **report,
                    "assessment_title": (
                        assessment.get(
                            "title",
                            "Assessment"
                        )
                    ),
                }
            )

    return reports


def _latest_weak_evidence(
    course_id,
    limit=5
):
    reports = _course_performance(
        course_id
    )

    weak = [
        report
        for report in reports
        if report.get("evidence")
        in {
            "weak_evidence",
            "needs_more_practice",
        }
    ]

    weak.sort(
        key=lambda item: (
            0
            if item.get("evidence")
            == "weak_evidence"
            else 1,
            item.get(
                "accuracy",
                1.0
            ),
            -item.get(
                "attempts",
                0
            ),
        )
    )

    return weak[:limit]


def print_academic_overview():
    courses = relevant_courses()

    print(
        "\n========== V12 ACADEMIC INTELLIGENCE DASHBOARD =========="
    )
    print(
        f"Date: {date.today().isoformat()}"
    )

    if not courses:
        print(
            "\nNo active/relevant courses found."
        )
        print(
            "Add courses in Course Manager and "
            "set an active course or add assessments."
        )
        return

    pending = list_assessments(
        include_completed=False
    )

    urgent = [
        item
        for item in pending
        if (
            days_until(
                item.get(
                    "due_date",
                    ""
                )
            )
            is not None
            and days_until(
                item.get(
                    "due_date",
                    ""
                )
            ) <= 7
        )
    ]

    tasks = build_global_tasks(
        courses
    )

    print(
        f"\nRelevant courses : {len(courses)}"
    )
    print(
        f"Pending assessments: {len(pending)}"
    )
    print(
        f"Due within 7 days : {len(urgent)}"
    )

    if tasks:
        print(
            f"Highest priority  : "
            f"{tasks[0]['course_code']} | "
            f"{tasks[0]['topic']}"
        )

    print(
        "\nCOURSE SNAPSHOT"
    )

    for course in courses:
        progress = _safe_progress(
            course["id"]
        )

        percent = progress.get(
            "progress_percent",
            0
        )

        weak_topics = progress.get(
            "weak_topics",
            []
        )

        missing_topics = progress.get(
            "missing_topics",
            []
        )

        assessments = _course_assessments(
            course["id"]
        )

        print(
            "\n" + "-" * 68
        )
        print(
            _course_label(course)
        )
        print(
            f"Progress: "
            f"{_bar(percent)} "
            f"{percent}%"
        )

        if weak_topics:
            print(
                "Weak: "
                + ", ".join(
                    weak_topics[:4]
                )
            )

        if missing_topics:
            print(
                "Not started / missing: "
                + ", ".join(
                    missing_topics[:4]
                )
            )

        if assessments:
            top = max(
                assessments,
                key=assessment_priority
            )

            weightage = (
                assessment_weightage_percent(
                    top
                )
            )

            text = (
                f"Next important assessment: "
                f"{top['title']} "
                f"({_assessment_timing(top)})"
            )

            if weightage is not None:
                text += (
                    f" | {weightage:g}% weight"
                )

            print(text)

        evidence = _latest_weak_evidence(
            course["id"],
            limit=1
        )

        if evidence:
            item = evidence[0]

            print(
                f"Performance concern: "
                f"{item['topic']} "
                f"| {round(item['accuracy'] * 100)}% "
                f"across {item['attempts']} attempt(s)"
            )

        course_tasks = build_course_tasks(
            course
        )

        if course_tasks:
            print(
                f"Recommended next: "
                f"{course_tasks[0]['topic']} "
                f"(score {course_tasks[0]['score']})"
            )


def print_assessment_dashboard():
    assessments = list_assessments(
        include_completed=False
    )

    print(
        "\n========== ASSESSMENT DASHBOARD =========="
    )

    if not assessments:
        print(
            "\nNo pending assessments."
        )
        return

    for number, item in enumerate(
        assessments,
        start=1
    ):
        course = find_course(
            item.get("course_id")
        )

        code = (
            course.get("code")
            if course
            else "UNKNOWN"
        )

        weightage = (
            assessment_weightage_percent(
                item
            )
        )

        credits = (
            assessment_course_credits(
                item,
                course=course
            )
        )

        print(
            f"\n{number}. [{code}] "
            f"{item.get('title', 'Untitled')}"
        )

        print(
            f"   Type     : "
            f"{item.get('type')}"
        )

        print(
            f"   Deadline : "
            f"{item.get('due_date')} "
            f"({_assessment_timing(item)})"
        )

        if weightage is not None:
            print(
                f"   Weight   : "
                f"{weightage:g}% "
                f"of final course grade"
            )

        if credits is not None:
            print(
                f"   Credits  : "
                f"{credits:g}"
            )

        print(
            f"   Priority : "
            f"{assessment_priority(item)}"
        )

        if item.get("topics"):
            print(
                "   Topics   : "
                + ", ".join(
                    item["topics"][:5]
                )
            )


def print_priority_queue():
    tasks = build_global_tasks(
        relevant_courses()
    )

    print(
        "\n========== STUDY PRIORITY QUEUE =========="
    )

    if not tasks:
        print(
            "\nNo unresolved priorities found."
        )
        return

    for number, task in enumerate(
        tasks[:12],
        start=1
    ):
        print(
            f"\n{number}. "
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
                    reasons[:4]
                )
            )

        performance = task.get(
            "performance"
        )

        if performance:
            print(
                f"   Evidence: "
                f"{performance['accuracy']}% "
                f"across "
                f"{performance['attempts']} attempt(s)"
            )


def print_course_intelligence(
    course=None
):
    if course is None:
        course = choose_course(
            "Select Course for Intelligence View"
        )

    if not course:
        return

    progress = _safe_progress(
        course["id"]
    )

    print(
        "\n========== COURSE INTELLIGENCE =========="
    )
    print(
        _course_label(course)
    )

    percent = progress.get(
        "progress_percent",
        0
    )

    print(
        f"\nProgress: "
        f"{_bar(percent, width=30)} "
        f"{percent}%"
    )

    print(
        f"Mastered: "
        f"{progress.get('mastered_topics', 0)}/"
        f"{progress.get('total_topics', 0)}"
    )

    weak = progress.get(
        "weak_topics",
        []
    )

    if weak:
        print(
            "\nWeak topics:"
        )

        for topic in weak[:8]:
            print(
                f"- {topic}"
            )

    ranked = rank_course_topics(
        course["id"],
        limit=8
    )

    if ranked:
        print(
            "\nTopic priorities:"
        )

        for number, topic in enumerate(
            ranked,
            start=1
        ):
            print(
                f"{number}. "
                f"{topic.get('name')} "
                f"| {topic.get('status')} "
                f"| {topic.get('priority_score', 0)}"
            )

    assessments = _course_assessments(
        course["id"]
    )

    if assessments:
        print(
            "\nPending assessments:"
        )

        for item in sorted(
            assessments,
            key=assessment_priority,
            reverse=True
        )[:5]:
            weightage = (
                assessment_weightage_percent(
                    item
                )
            )

            line = (
                f"- {item['title']} "
                f"| {_assessment_timing(item)}"
            )

            if weightage is not None:
                line += (
                    f" | {weightage:g}%"
                )

            print(line)

    performance = _course_performance(
        course["id"]
    )

    if performance:
        print(
            "\nAssessment evidence:"
        )

        for report in sorted(
            performance,
            key=lambda item: (
                item.get(
                    "accuracy",
                    1
                ),
                -item.get(
                    "attempts",
                    0
                ),
            )
        )[:8]:
            print(
                f"- {report['topic']}: "
                f"{round(report['accuracy'] * 100)}% "
                f"| {report['attempts']} attempts "
                f"| {report['evidence']}"
            )

    tasks = build_course_tasks(
        course
    )

    if tasks:
        print(
            "\nBest next actions:"
        )

        for number, task in enumerate(
            tasks[:5],
            start=1
        ):
            print(
                f"{number}. "
                f"{task['topic']} "
                f"| score {task['score']}"
            )


def print_academic_risk_report():
    courses = relevant_courses()

    print(
        "\n========== ACADEMIC RISK REPORT =========="
    )

    if not courses:
        print(
            "\nNo courses available."
        )
        return

    risks = []

    for course in courses:
        progress = _safe_progress(
            course["id"]
        )

        weak_topics = progress.get(
            "weak_topics",
            []
        )

        performance = _latest_weak_evidence(
            course["id"],
            limit=5
        )

        assessments = _course_assessments(
            course["id"]
        )

        urgent = []

        for item in assessments:
            remaining = days_until(
                item.get(
                    "due_date",
                    ""
                )
            )

            if (
                remaining is not None
                and remaining <= 7
            ):
                urgent.append(
                    item
                )

        risk_score = (
            len(weak_topics) * 12
            + len(performance) * 18
            + len(urgent) * 15
        )

        if urgent:
            risk_score += max(
                assessment_priority(
                    item
                )
                for item in urgent
            ) * 0.25

        risks.append(
            {
                "course": course,
                "score": round(
                    risk_score,
                    1
                ),
                "weak_topics": weak_topics,
                "performance": performance,
                "urgent": urgent,
            }
        )

    risks.sort(
        key=lambda item: item[
            "score"
        ],
        reverse=True
    )

    for number, risk in enumerate(
        risks,
        start=1
    ):
        course = risk["course"]

        print(
            f"\n{number}. "
            f"{_course_label(course)} "
            f"| risk score "
            f"{risk['score']}"
        )

        if risk["urgent"]:
            print(
                "   Urgent assessments: "
                + ", ".join(
                    item["title"]
                    for item in risk[
                        "urgent"
                    ][
                        :3
                    ]
                )
            )

        if risk["weak_topics"]:
            print(
                "   Weak topics: "
                + ", ".join(
                    risk[
                        "weak_topics"
                    ][
                        :4
                    ]
                )
            )

        if risk["performance"]:
            print(
                "   Weak evidence: "
                + ", ".join(
                    item["topic"]
                    for item in risk[
                        "performance"
                    ][
                        :4
                    ]
                )
            )

        if (
            not risk["urgent"]
            and not risk["weak_topics"]
            and not risk["performance"]
        ):
            print(
                "   No significant risk signal."
            )


def print_today_brief():
    tasks = build_global_tasks(
        relevant_courses()
    )

    pending = list_assessments(
        include_completed=False
    )

    print(
        "\n========== TODAY'S ACADEMIC BRIEF =========="
    )
    print(
        f"Date: {date.today().isoformat()}"
    )

    due_soon = []

    for item in pending:
        remaining = days_until(
            item.get(
                "due_date",
                ""
            )
        )

        if (
            remaining is not None
            and remaining <= 3
        ):
            due_soon.append(
                item
            )

    if due_soon:
        print(
            "\nDeadline alerts:"
        )

        for item in due_soon[:5]:
            course = find_course(
                item.get("course_id")
            )

            code = (
                course.get("code")
                if course
                else "COURSE"
            )

            print(
                f"- {code}: "
                f"{item['title']} "
                f"({_assessment_timing(item)})"
            )

    if tasks:
        print(
            "\nTop 3 academic priorities:"
        )

        for number, task in enumerate(
            tasks[:3],
            start=1
        ):
            print(
                f"{number}. "
                f"{task['course_code']} | "
                f"{task['topic']}"
            )

            if task.get("reasons"):
                print(
                    "   "
                    + "; ".join(
                        task["reasons"][:3]
                    )
                )

    if not due_soon and not tasks:
        print(
            "\nNo urgent academic action found."
        )


def academic_intelligence_dashboard_menu():
    while True:
        print(
            "\n========== V12 ACADEMIC INTELLIGENCE DASHBOARD =========="
        )
        print(
            "1. Full Academic Overview"
        )
        print(
            "2. Today's Academic Brief"
        )
        print(
            "3. Study Priority Queue"
        )
        print(
            "4. Assessment Dashboard"
        )
        print(
            "5. Course Intelligence View"
        )
        print(
            "6. Academic Risk Report"
        )
        print(
            "7. Back"
        )

        choice = input(
            "\nEnter your choice (1-7): "
        ).strip()

        if choice == "1":
            print_academic_overview()

        elif choice == "2":
            print_today_brief()

        elif choice == "3":
            print_priority_queue()

        elif choice == "4":
            print_assessment_dashboard()

        elif choice == "5":
            print_course_intelligence()

        elif choice == "6":
            print_academic_risk_report()

        elif choice == "7":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 7."
            )


if __name__ == "__main__":
    academic_intelligence_dashboard_menu()
