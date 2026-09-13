"""V13 Personal Academic Agent.

A natural-language command layer over the academic engines already built.

Examples:
- What should I do now?
- What should I study today?
- Plan my week.
- What is risky this week?
- Show my deadlines.
- How am I doing in MA103N?
- Project my SGPA.
- How much do I need in the remaining assessments?
- I have a doubt from my course notes.

The agent routes the user's request to the existing deterministic academic
engines rather than inventing a second source of truth.
"""

import re

from course_manager import choose_course
from daily_academic_brief import print_daily_brief
from intelligent_study_planner import (
    generate_today,
    generate_week,
    show_why_topic_is_priority,
)
from academic_intelligence_dashboard import (
    print_academic_overview,
    print_academic_risk_report,
    print_course_intelligence,
    print_assessment_dashboard,
)
from academic_calendar_planner import (
    print_week_calendar,
    print_month_calendar,
    print_deadline_countdowns,
    print_overload_report,
    print_deadline_study_plan,
)
from semester_grade_intelligence import (
    print_course_grade_intelligence,
    projection_tool,
    target_score_tool,
    sgpa_projection,
    target_sgpa_scenario,
)
from rag_answer import course_rag_chat_loop
from assignment_exam_assistant import assignment_exam_menu


INTENTS = {
    "NOW": "What should I do now?",
    "TODAY_PLAN": "Build today's study plan",
    "WEEK_PLAN": "Build a 7-day study plan",
    "PRIORITY": "Show current study priorities",
    "RISK": "Show academic risk",
    "DEADLINE": "Show deadlines",
    "OVERLOAD": "Show overload/deadline pressure",
    "ASSESSMENTS": "Show assessment dashboard",
    "COURSE_STATUS": "Show one course's academic status",
    "COURSE_GRADE": "Show one course's grade intelligence",
    "COURSE_PROJECTION": "Project final course score",
    "REQUIRED_SCORE": "Required score on remaining assessment weight",
    "SGPA": "Project semester SGPA",
    "TARGET_SGPA": "Target SGPA what-if",
    "DOUBT": "Open source-grounded course assistant",
    "ASSESSMENT_WORK": "Open Assignment & Exam Assistant",
    "HELP": "Show agent capabilities",
    "BACK": "Return to main menu",
}


def normalize(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "").strip().lower()
    )


def classify_intent(text):
    q = normalize(text)

    if not q:
        return "HELP"

    if q in {
        "back",
        "exit",
        "quit",
        "main menu",
        "return",
    }:
        return "BACK"

    if any(
        phrase in q
        for phrase in (
            "what should i do now",
            "what do i do now",
            "best next action",
            "what next",
            "what should i do first",
        )
    ):
        return "NOW"

    if any(
        phrase in q
        for phrase in (
            "plan today",
            "plan my day",
            "today's study plan",
            "todays study plan",
            "study today",
            "study tonight",
            "what should i study today",
            "what should i study tonight",
        )
    ):
        return "TODAY_PLAN"

    if any(
        phrase in q
        for phrase in (
            "plan my week",
            "weekly plan",
            "7 day plan",
            "seven day plan",
            "study this week",
        )
    ):
        return "WEEK_PLAN"

    if any(
        word in q
        for word in (
            "priority",
            "priorities",
            "most important topic",
        )
    ):
        return "PRIORITY"

    if any(
        phrase in q
        for phrase in (
            "risk",
            "risky",
            "danger",
            "falling behind",
            "weakest course",
        )
    ):
        return "RISK"

    if any(
        phrase in q
        for phrase in (
            "overload",
            "too many deadlines",
            "busy week",
            "heavy week",
        )
    ):
        return "OVERLOAD"

    if any(
        word in q
        for word in (
            "deadline",
            "deadlines",
            "due date",
            "due this week",
            "calendar",
        )
    ):
        return "DEADLINE"

    if any(
        phrase in q
        for phrase in (
            "assessment dashboard",
            "show assessments",
            "show quizzes",
            "show assignments",
            "upcoming assessments",
        )
    ):
        return "ASSESSMENTS"

    if any(
        phrase in q
        for phrase in (
            "how am i doing in",
            "course status",
            "course progress",
            "show course progress",
            "course intelligence",
        )
    ):
        return "COURSE_STATUS"

    if any(
        phrase in q
        for phrase in (
            "course grade",
            "grade intelligence",
            "weighted score",
            "course score",
        )
    ):
        return "COURSE_GRADE"

    if any(
        phrase in q
        for phrase in (
            "project final score",
            "predict final score",
            "project course score",
            "expected final score",
        )
    ):
        return "COURSE_PROJECTION"

    if any(
        phrase in q
        for phrase in (
            "how much do i need",
            "required score",
            "need in remaining",
            "score in remaining",
            "what marks do i need",
        )
    ):
        return "REQUIRED_SCORE"

    if any(
        phrase in q
        for phrase in (
            "target sgpa",
            "what sgpa do i need",
            "sgpa target",
            "what if sgpa",
        )
    ):
        return "TARGET_SGPA"

    if "sgpa" in q or "cgpa" in q:
        return "SGPA"

    if any(
        phrase in q
        for phrase in (
            "doubt",
            "explain from my notes",
            "explain from course",
            "ask course assistant",
            "source grounded",
            "source-grounded",
        )
    ):
        return "DOUBT"

    if any(
        phrase in q
        for phrase in (
            "add quiz",
            "add assignment",
            "add exam",
            "assessment assistant",
            "record result",
        )
    ):
        return "ASSESSMENT_WORK"

    if any(
        phrase in q
        for phrase in (
            "help",
            "what can you do",
            "commands",
            "capabilities",
        )
    ):
        return "HELP"

    # General "today" requests are usually planning requests.
    if "today" in q or "tonight" in q:
        return "TODAY_PLAN"

    # General "week" requests lean toward the calendar if deadlines are mentioned,
    # otherwise toward a study plan.
    if "week" in q:
        return "WEEK_PLAN"

    return "HELP"


def print_agent_help():
    print(
        "\n========== V13 PERSONAL ACADEMIC AGENT =========="
    )
    print(
        "You can type requests naturally."
    )

    examples = [
        "What should I do now?",
        "What should I study tonight?",
        "Plan my week.",
        "What is risky this week?",
        "Show my deadlines.",
        "Show upcoming assessments.",
        "How am I doing in MA103N?",
        "Show course grade intelligence.",
        "Project my final course score.",
        "How much do I need in the remaining assessments?",
        "Project my SGPA.",
        "What SGPA is possible from here?",
        "I have a doubt from my course notes.",
        "Add a quiz.",
    ]

    print(
        "\nExamples:"
    )

    for item in examples:
        print(
            f"- {item}"
        )

    print(
        "\nType 'back' to return to the main menu."
    )


def handle_now():
    print(
        "\nI am checking deadlines, risk and study priorities..."
    )

    print_daily_brief()


def handle_today_plan():
    print(
        "\nOpening the intelligent plan for today."
    )

    generate_today()


def handle_week_plan():
    print(
        "\nOpening the intelligent 7-day planner."
    )

    generate_week()


def handle_deadlines():
    print(
        "\n1. Next 7 days"
    )
    print(
        "2. Next 30 days"
    )
    print(
        "3. Ranked deadline countdowns"
    )

    choice = input(
        "Choose view [default 1]: "
    ).strip()

    if choice == "2":
        print_month_calendar()

    elif choice == "3":
        print_deadline_countdowns()

    else:
        print_week_calendar()


def handle_course_status():
    course = choose_course(
        "Select Course for Academic Intelligence"
    )

    if course:
        print_course_intelligence(
            course
        )


def execute_intent(
    intent,
    original_text=""
):
    if intent == "NOW":
        handle_now()

    elif intent == "TODAY_PLAN":
        handle_today_plan()

    elif intent == "WEEK_PLAN":
        handle_week_plan()

    elif intent == "PRIORITY":
        show_why_topic_is_priority()

    elif intent == "RISK":
        print_academic_risk_report()

    elif intent == "DEADLINE":
        handle_deadlines()

    elif intent == "OVERLOAD":
        print_overload_report()

    elif intent == "ASSESSMENTS":
        print_assessment_dashboard()

    elif intent == "COURSE_STATUS":
        handle_course_status()

    elif intent == "COURSE_GRADE":
        print_course_grade_intelligence()

    elif intent == "COURSE_PROJECTION":
        projection_tool()

    elif intent == "REQUIRED_SCORE":
        target_score_tool()

    elif intent == "SGPA":
        sgpa_projection()

    elif intent == "TARGET_SGPA":
        target_sgpa_scenario()

    elif intent == "DOUBT":
        print(
            "\nOpening the source-grounded Course Academic Assistant."
        )
        course_rag_chat_loop()

    elif intent == "ASSESSMENT_WORK":
        assignment_exam_menu()

    elif intent == "HELP":
        print_agent_help()

    elif intent == "BACK":
        return False

    else:
        print_agent_help()

    return True


def quick_command_menu():
    print(
        "\n========== QUICK COMMANDS =========="
    )
    print(
        "1. What should I do now?"
    )
    print(
        "2. Plan today"
    )
    print(
        "3. Plan this week"
    )
    print(
        "4. Academic risk"
    )
    print(
        "5. Deadlines"
    )
    print(
        "6. Course status"
    )
    print(
        "7. SGPA projection"
    )
    print(
        "8. Required remaining score"
    )
    print(
        "9. Course doubt / RAG"
    )
    print(
        "10. Back"
    )

    mapping = {
        "1": "NOW",
        "2": "TODAY_PLAN",
        "3": "WEEK_PLAN",
        "4": "RISK",
        "5": "DEADLINE",
        "6": "COURSE_STATUS",
        "7": "SGPA",
        "8": "REQUIRED_SCORE",
        "9": "DOUBT",
        "10": "BACK",
    }

    choice = input(
        "\nChoose (1-10): "
    ).strip()

    return mapping.get(
        choice,
        "HELP"
    )


def personal_academic_agent_menu():
    print(
        "\n" + "=" * 64
    )
    print(
        "V13 PERSONAL ACADEMIC AGENT"
    )
    print(
        "=" * 64
    )
    print(
        "Ask naturally. I will route your request "
        "to the correct academic engine."
    )
    print(
        "Type 'commands' for examples or 'back' to return."
    )

    while True:
        query = input(
            "\nYou > "
        ).strip()

        if normalize(query) in {
            "menu",
            "quick menu",
            "quick commands",
        }:
            intent = quick_command_menu()
        else:
            intent = classify_intent(
                query
            )

        print(
            f"\nAgent route: "
            f"{INTENTS.get(intent, intent)}"
        )

        keep_running = execute_intent(
            intent,
            original_text=query
        )

        if not keep_running:
            break


if __name__ == "__main__":
    personal_academic_agent_menu()
