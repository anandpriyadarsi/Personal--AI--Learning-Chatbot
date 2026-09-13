"""V10.4 Assessment Performance Engine.

Turns question outcomes into transparent academic evidence.

It tracks:
- attempts
- correct / partially correct / wrong / stuck outcomes
- earned marks versus maximum marks
- repeated mistakes
- topic-level performance

Important safety rule:
Assessment evidence never silently marks a topic mastered.
Very weak repeated performance can be offered as a weak-topic update, and
strong performance can be offered as a mastery suggestion, but the student
confirms any memory/progress change.
"""

from datetime import datetime

from assignment_exam_assistant import choose_assessment
from assessment_question_workspace import (
    get_workspace,
    save_workspace,
    choose_question,
    list_questions,
)
from course_manager import find_course
from learning_memory import (
    mark_weak_topic,
    mark_mastered_topic,
)


OUTCOMES = {
    "1": "correct",
    "2": "partially_correct",
    "3": "wrong",
    "4": "stuck",
}

OUTCOME_WEIGHTS = {
    "correct": 1.0,
    "partially_correct": 0.5,
    "wrong": 0.0,
    "stuck": 0.0,
}

WEAK_MIN_ATTEMPTS = 2
WEAK_THRESHOLD = 0.50

MASTERY_MIN_ATTEMPTS = 3
MASTERY_THRESHOLD = 0.80


def _now():
    return datetime.now().isoformat(
        timespec="seconds"
    )


def ensure_performance(question):
    performance = question.get(
        "performance"
    )

    if not isinstance(
        performance,
        dict
    ):
        performance = {}

    attempts = performance.get(
        "attempts",
        []
    )

    if not isinstance(attempts, list):
        attempts = []

    performance["attempts"] = attempts
    performance.setdefault(
        "mistakes",
        []
    )

    if not isinstance(
        performance["mistakes"],
        list
    ):
        performance["mistakes"] = []

    question["performance"] = performance
    return performance


def _float_or_none(value):
    if value is None:
        return None

    try:
        return float(value)
    except (
        TypeError,
        ValueError
    ):
        return None


def record_question_attempt(
    workspace,
    question
):
    performance = ensure_performance(
        question
    )

    print(
        "\n========== RECORD QUESTION PERFORMANCE =========="
    )
    print(
        question.get(
            "text",
            ""
        )
    )

    print("\nOutcome:")
    print("1. Correct")
    print("2. Partially Correct")
    print("3. Wrong")
    print("4. Stuck / Could Not Solve")

    choice = input(
        "\nChoose outcome (1-4): "
    ).strip()

    outcome = OUTCOMES.get(
        choice
    )

    if not outcome:
        print("\nInvalid outcome.")
        return

    max_marks = _float_or_none(
        question.get("marks")
    )

    earned_marks = None

    if max_marks is not None:
        raw = input(
            f"Marks earned out of {max_marks:g} "
            "(press Enter to skip): "
        ).strip()

        if raw:
            earned_marks = _float_or_none(
                raw
            )

            if earned_marks is None:
                print(
                    "\nMarks were not understood. "
                    "Saving outcome without marks."
                )

            else:
                earned_marks = max(
                    0.0,
                    min(
                        earned_marks,
                        max_marks
                    )
                )

    mistake = input(
        "Mistake / difficulty "
        "(optional): "
    ).strip()

    attempt = {
        "time": _now(),
        "outcome": outcome,
        "weight": OUTCOME_WEIGHTS[
            outcome
        ],
        "earned_marks": earned_marks,
        "max_marks": max_marks,
        "mistake": mistake,
    }

    performance[
        "attempts"
    ].append(
        attempt
    )

    if mistake:
        performance[
            "mistakes"
        ].append({
            "time": _now(),
            "text": mistake,
        })

    question[
        "updated_at"
    ] = _now()

    # Keep workspace status useful without claiming mastery.
    if outcome == "stuck":
        question["status"] = "stuck"
    elif outcome in {
        "wrong",
        "partially_correct",
        "correct",
    }:
        if question.get(
            "status"
        ) != "completed":
            question[
                "status"
            ] = "attempted"

    save_workspace(
        workspace
    )

    print(
        f"\nRecorded attempt: {outcome}."
    )

    if outcome == "correct":
        print(
            "The question was NOT automatically "
            "marked completed or the topic mastered."
        )


def attempt_accuracy(
    attempts
):
    if not attempts:
        return 0.0

    weights = [
        float(
            item.get(
                "weight",
                OUTCOME_WEIGHTS.get(
                    item.get("outcome"),
                    0.0
                )
            )
        )
        for item in attempts
    ]

    return sum(weights) / len(weights)


def marks_accuracy(
    attempts
):
    earned = 0.0
    maximum = 0.0

    for attempt in attempts:
        e = _float_or_none(
            attempt.get(
                "earned_marks"
            )
        )

        m = _float_or_none(
            attempt.get(
                "max_marks"
            )
        )

        if (
            e is not None
            and m is not None
            and m > 0
        ):
            earned += e
            maximum += m

    if maximum <= 0:
        return None

    return earned / maximum


def question_performance(
    question
):
    performance = ensure_performance(
        question
    )

    attempts = performance[
        "attempts"
    ]

    accuracy = attempt_accuracy(
        attempts
    )

    marks_rate = marks_accuracy(
        attempts
    )

    outcomes = {
        "correct": 0,
        "partially_correct": 0,
        "wrong": 0,
        "stuck": 0,
    }

    for attempt in attempts:
        outcome = attempt.get(
            "outcome"
        )

        if outcome in outcomes:
            outcomes[
                outcome
            ] += 1

    return {
        "attempts": len(attempts),
        "accuracy": accuracy,
        "marks_accuracy": marks_rate,
        "outcomes": outcomes,
        "mistakes": performance.get(
            "mistakes",
            []
        ),
    }


def print_question_performance(
    workspace
):
    question = choose_question(
        workspace
    )

    if not question:
        return

    report = question_performance(
        question
    )

    print(
        "\n========== QUESTION PERFORMANCE =========="
    )
    print(
        question.get(
            "text",
            ""
        )
    )
    print(
        f"\nTopic    : "
        f"{question.get('topic') or 'Not tagged'}"
    )
    print(
        f"Attempts : "
        f"{report['attempts']}"
    )
    print(
        f"Accuracy : "
        f"{round(report['accuracy'] * 100)}%"
    )

    if (
        report["marks_accuracy"]
        is not None
    ):
        print(
            f"Marks    : "
            f"{round(report['marks_accuracy'] * 100)}%"
        )

    print("\nOutcomes:")
    for name, count in report[
        "outcomes"
    ].items():
        print(
            f"- {name}: {count}"
        )

    mistakes = report[
        "mistakes"
    ]

    if mistakes:
        print("\nRecorded mistakes:")
        for item in mistakes[-10:]:
            print(
                f"- {item.get('text')}"
            )


def aggregate_topic_performance(
    workspace
):
    topics = {}

    for question in workspace.get(
        "questions",
        []
    ):
        topic = str(
            question.get(
                "topic",
                ""
            )
        ).strip()

        if not topic:
            continue

        report = question_performance(
            question
        )

        if (
            report["attempts"]
            == 0
        ):
            continue

        key = topic.lower()

        if key not in topics:
            topics[key] = {
                "topic": topic,
                "questions_attempted": 0,
                "attempts": 0,
                "weighted_sum": 0.0,
                "correct": 0,
                "partial": 0,
                "wrong": 0,
                "stuck": 0,
                "earned_marks": 0.0,
                "max_marks": 0.0,
                "mistakes": [],
            }

        bucket = topics[key]
        bucket[
            "questions_attempted"
        ] += 1

        attempts = ensure_performance(
            question
        )["attempts"]

        for attempt in attempts:
            bucket["attempts"] += 1

            bucket[
                "weighted_sum"
            ] += float(
                attempt.get(
                    "weight",
                    OUTCOME_WEIGHTS.get(
                        attempt.get(
                            "outcome"
                        ),
                        0.0
                    )
                )
            )

            outcome = attempt.get(
                "outcome"
            )

            if outcome == "correct":
                bucket[
                    "correct"
                ] += 1

            elif outcome == "partially_correct":
                bucket[
                    "partial"
                ] += 1

            elif outcome == "wrong":
                bucket[
                    "wrong"
                ] += 1

            elif outcome == "stuck":
                bucket[
                    "stuck"
                ] += 1

            earned = _float_or_none(
                attempt.get(
                    "earned_marks"
                )
            )

            maximum = _float_or_none(
                attempt.get(
                    "max_marks"
                )
            )

            if (
                earned is not None
                and maximum is not None
                and maximum > 0
            ):
                bucket[
                    "earned_marks"
                ] += earned
                bucket[
                    "max_marks"
                ] += maximum

            mistake = str(
                attempt.get(
                    "mistake",
                    ""
                )
            ).strip()

            if mistake:
                bucket[
                    "mistakes"
                ].append(
                    mistake
                )

    reports = []

    for bucket in topics.values():
        attempts = bucket[
            "attempts"
        ]

        accuracy = (
            bucket[
                "weighted_sum"
            ] / attempts
            if attempts
            else 0.0
        )

        marks_rate = (
            bucket[
                "earned_marks"
            ] / bucket[
                "max_marks"
            ]
            if bucket[
                "max_marks"
            ] > 0
            else None
        )

        evidence = classify_topic_evidence(
            attempts,
            accuracy
        )

        reports.append({
            **bucket,
            "accuracy": accuracy,
            "marks_accuracy": marks_rate,
            "evidence": evidence,
        })

    reports.sort(
        key=lambda item: (
            evidence_order(
                item["evidence"]
            ),
            item["accuracy"],
            -item["attempts"],
        )
    )

    return reports


def evidence_order(label):
    return {
        "weak_evidence": 0,
        "needs_more_practice": 1,
        "insufficient_evidence": 2,
        "strong_evidence": 3,
    }.get(
        label,
        9
    )


def classify_topic_evidence(
    attempts,
    accuracy
):
    if attempts < WEAK_MIN_ATTEMPTS:
        return "insufficient_evidence"

    if accuracy < WEAK_THRESHOLD:
        return "weak_evidence"

    if (
        attempts >= MASTERY_MIN_ATTEMPTS
        and accuracy >= MASTERY_THRESHOLD
    ):
        return "strong_evidence"

    return "needs_more_practice"


def print_topic_report(
    assessment,
    workspace
):
    course = find_course(
        assessment.get(
            "course_id"
        )
    )

    reports = aggregate_topic_performance(
        workspace
    )

    print(
        "\n========== V10.4 TOPIC PERFORMANCE REPORT =========="
    )

    if course:
        print(
            f"Course: "
            f"{course['code']} - "
            f"{course['name']}"
        )

    if not reports:
        print(
            "\nNo topic-linked performance evidence yet."
        )
        print(
            "Tag questions to course topics and "
            "record attempts first."
        )
        return

    for number, report in enumerate(
        reports,
        start=1
    ):
        print(
            f"\n{number}. "
            f"{report['topic']}"
        )
        print(
            f"   Attempts : "
            f"{report['attempts']}"
        )
        print(
            f"   Questions: "
            f"{report['questions_attempted']}"
        )
        print(
            f"   Accuracy : "
            f"{round(report['accuracy'] * 100)}%"
        )

        if (
            report["marks_accuracy"]
            is not None
        ):
            print(
                f"   Marks    : "
                f"{round(report['marks_accuracy'] * 100)}%"
            )

        print(
            f"   Evidence : "
            f"{report['evidence']}"
        )

        if report["mistakes"]:
            unique = []

            for mistake in report[
                "mistakes"
            ]:
                if (
                    mistake.lower()
                    not in {
                        item.lower()
                        for item in unique
                    }
                ):
                    unique.append(
                        mistake
                    )

            print(
                "   Mistakes : "
                + "; ".join(
                    unique[:3]
                )
            )


def choose_topic_report(
    reports
):
    if not reports:
        return None

    for number, report in enumerate(
        reports,
        start=1
    ):
        print(
            f"{number}. "
            f"{report['topic']} "
            f"| {round(report['accuracy'] * 100)}% "
            f"| {report['attempts']} attempts "
            f"| {report['evidence']}"
        )

    try:
        choice = int(
            input(
                "\nChoose topic number: "
            ).strip()
        )
    except ValueError:
        print("\nInvalid number.")
        return None

    if (
        choice < 1
        or choice > len(reports)
    ):
        print("\nInvalid topic number.")
        return None

    return reports[
        choice - 1
    ]


def sync_evidence_to_learning_memory(
    assessment,
    workspace
):
    course = find_course(
        assessment.get(
            "course_id"
        )
    )

    if not course:
        print("\nCourse not found.")
        return

    reports = aggregate_topic_performance(
        workspace
    )

    if not reports:
        print(
            "\nNo topic performance evidence available."
        )
        return

    actionable = [
        report
        for report in reports
        if report[
            "evidence"
        ] in {
            "weak_evidence",
            "strong_evidence",
        }
    ]

    if not actionable:
        print(
            "\nThere is not enough strong or weak evidence "
            "to suggest a memory update yet."
        )
        return

    print(
        "\n========== EVIDENCE REVIEW =========="
    )
    print(
        "Nothing is changed automatically."
    )

    for report in actionable:
        print(
            "\n" + "-" * 60
        )
        print(
            f"Topic: {report['topic']}"
        )
        print(
            f"Attempts: "
            f"{report['attempts']}"
        )
        print(
            f"Accuracy: "
            f"{round(report['accuracy'] * 100)}%"
        )
        print(
            f"Evidence: "
            f"{report['evidence']}"
        )

        if (
            report[
                "evidence"
            ] == "weak_evidence"
        ):
            action = input(
                "Mark this topic WEAK in course memory? "
                "(yes/no): "
            ).strip().lower()

            if action == "yes":
                mark_weak_topic(
                    report["topic"],
                    course_id=course["id"]
                )

                print(
                    "Saved as weak."
                )

        elif (
            report[
                "evidence"
            ] == "strong_evidence"
        ):
            print(
                "Strong assessment evidence does not prove "
                "full mastery by itself."
            )

            action = input(
                "Do you want to mark this topic MASTERED "
                "after your own review? (yes/no): "
            ).strip().lower()

            if action == "yes":
                mark_mastered_topic(
                    report["topic"],
                    course_id=course["id"]
                )

                print(
                    "Saved as mastered."
                )


def assessment_summary(
    assessment,
    workspace
):
    questions = workspace.get(
        "questions",
        []
    )

    attempted_questions = 0
    total_attempts = 0
    weighted_sum = 0.0

    total_earned = 0.0
    total_marks = 0.0

    for question in questions:
        report = question_performance(
            question
        )

        if report[
            "attempts"
        ] > 0:
            attempted_questions += 1

        attempts = ensure_performance(
            question
        )["attempts"]

        for attempt in attempts:
            total_attempts += 1
            weighted_sum += float(
                attempt.get(
                    "weight",
                    OUTCOME_WEIGHTS.get(
                        attempt.get(
                            "outcome"
                        ),
                        0.0
                    )
                )
            )

            earned = _float_or_none(
                attempt.get(
                    "earned_marks"
                )
            )
            maximum = _float_or_none(
                attempt.get(
                    "max_marks"
                )
            )

            if (
                earned is not None
                and maximum is not None
                and maximum > 0
            ):
                total_earned += earned
                total_marks += maximum

    accuracy = (
        weighted_sum / total_attempts
        if total_attempts
        else 0.0
    )

    print(
        "\n========== ASSESSMENT PERFORMANCE SUMMARY =========="
    )
    print(
        f"Assessment : "
        f"{assessment['title']}"
    )
    print(
        f"Questions  : "
        f"{len(questions)}"
    )
    print(
        f"Attempted questions: "
        f"{attempted_questions}"
    )
    print(
        f"Recorded attempts  : "
        f"{total_attempts}"
    )

    if total_attempts:
        print(
            f"Attempt accuracy   : "
            f"{round(accuracy * 100)}%"
        )
    else:
        print(
            "Attempt accuracy   : "
            "No evidence yet"
        )

    if total_marks > 0:
        print(
            f"Marks recorded     : "
            f"{total_earned:g}/{total_marks:g} "
            f"({round(100 * total_earned / total_marks)}%)"
        )

    reports = aggregate_topic_performance(
        workspace
    )

    weak = [
        item["topic"]
        for item in reports
        if item[
            "evidence"
        ] == "weak_evidence"
    ]

    strong = [
        item["topic"]
        for item in reports
        if item[
            "evidence"
        ] == "strong_evidence"
    ]

    if weak:
        print(
            "\nWeak evidence topics:"
        )
        for topic in weak:
            print(
                f"- {topic}"
            )

    if strong:
        print(
            "\nStrong evidence topics:"
        )
        for topic in strong:
            print(
                f"- {topic}"
            )


def repeated_mistakes_report(
    workspace
):
    mistakes = {}

    for question in workspace.get(
        "questions",
        []
    ):
        topic = (
            question.get("topic")
            or "Unmapped topic"
        )

        performance = ensure_performance(
            question
        )

        for item in performance.get(
            "mistakes",
            []
        ):
            text = str(
                item.get(
                    "text",
                    ""
                )
            ).strip()

            if not text:
                continue

            key = text.lower()

            if key not in mistakes:
                mistakes[key] = {
                    "text": text,
                    "count": 0,
                    "topics": set(),
                }

            mistakes[key][
                "count"
            ] += 1

            mistakes[key][
                "topics"
            ].add(
                topic
            )

    rows = sorted(
        mistakes.values(),
        key=lambda item: (
            item["count"],
            item["text"]
        ),
        reverse=True
    )

    print(
        "\n========== MISTAKE PATTERN REPORT =========="
    )

    if not rows:
        print(
            "\nNo mistakes have been recorded yet."
        )
        return

    for number, item in enumerate(
        rows,
        start=1
    ):
        print(
            f"{number}. "
            f"{item['text']}"
        )
        print(
            f"   Seen: {item['count']} time(s)"
        )
        print(
            "   Topics: "
            + ", ".join(
                sorted(
                    item["topics"]
                )
            )
        )


def performance_engine_menu():
    assessment = choose_assessment(
        include_completed=True
    )

    if not assessment:
        return

    workspace = get_workspace(
        assessment["id"],
        create=True
    )

    while True:
        print(
            "\n========== V10.4 ASSESSMENT PERFORMANCE ENGINE =========="
        )
        print(
            f"Assessment: "
            f"{assessment['title']}"
        )

        print(
            "\n1. Record Question Attempt"
        )
        print(
            "2. View Question Performance"
        )
        print(
            "3. View Topic Performance Report"
        )
        print(
            "4. View Assessment Performance Summary"
        )
        print(
            "5. View Repeated Mistakes"
        )
        print(
            "6. Review Evidence → Update Learning Memory"
        )
        print(
            "7. View Questions"
        )
        print(
            "8. Change Assessment"
        )
        print(
            "9. Back"
        )

        choice = input(
            "\nEnter your choice (1-9): "
        ).strip()

        if choice == "1":
            question = choose_question(
                workspace
            )

            if question:
                record_question_attempt(
                    workspace,
                    question
                )

        elif choice == "2":
            print_question_performance(
                workspace
            )

        elif choice == "3":
            print_topic_report(
                assessment,
                workspace
            )

        elif choice == "4":
            assessment_summary(
                assessment,
                workspace
            )

        elif choice == "5":
            repeated_mistakes_report(
                workspace
            )

        elif choice == "6":
            sync_evidence_to_learning_memory(
                assessment,
                workspace
            )

        elif choice == "7":
            list_questions(
                workspace
            )

        elif choice == "8":
            selected = choose_assessment(
                include_completed=True
            )

            if selected:
                assessment = selected

                workspace = get_workspace(
                    assessment["id"],
                    create=True
                )

        elif choice == "9":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 9."
            )


if __name__ == "__main__":
    performance_engine_menu()
