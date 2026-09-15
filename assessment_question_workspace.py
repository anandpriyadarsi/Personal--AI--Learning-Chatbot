"""V10.1 Assessment Question Workspace.

Adds question-by-question tracking for assignments/exams and source-grounded help.
Question sheets can be registered manually or imported from plain text/Markdown.
The workspace does not silently mark questions complete.
"""

import json
import os
import re
from datetime import datetime

from knowledge_paths import BASE_DIR
from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)
from course_manager import find_course
from assignment_exam_assistant import (
    choose_assessment,
    load_store as load_assessment_store,
)
from rag_answer import (
    rag_answer,
    clean_terminal_markdown,
    print_verified_sources,
    llm_is_configured,
)
from semantic_retrieval import load_semantic_index


DATA_DIR = os.path.join(BASE_DIR, "data")
WORKSPACE_FILE = os.path.join(DATA_DIR, "assessment_workspace.json")

WORKSPACE_VERSION = 1
MAX_QUESTIONS_PER_ASSESSMENT = 200

VALID_QUESTION_STATUSES = {
    "not_started",
    "attempted",
    "stuck",
    "completed",
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def default_store():
    return {
        "version": WORKSPACE_VERSION,
        "workspaces": {}
    }


def load_store():
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(WORKSPACE_FILE):
        return default_store()

    try:
        with open(WORKSPACE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return default_store()

    if not isinstance(data, dict):
        return default_store()

    workspaces = data.get("workspaces", {})
    if not isinstance(workspaces, dict):
        workspaces = {}

    return {
        "version": WORKSPACE_VERSION,
        "workspaces": workspaces
    }


def save_store(store):
    guard_legacy_structured_write(infer_authority_control_path(WORKSPACE_FILE))
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_file = WORKSPACE_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(
            store,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(temp_file, WORKSPACE_FILE)


def assessment_exists(assessment_id):
    assessment_store = load_assessment_store()

    return any(
        str(item.get("id")) == str(assessment_id)
        for item in assessment_store.get("assessments", [])
    )


def get_workspace(assessment_id, create=False):
    store = load_store()
    key = str(assessment_id)

    workspace = store["workspaces"].get(key)

    if workspace is None and create:
        workspace = {
            "assessment_id": key,
            "created_at": _now(),
            "updated_at": _now(),
            "questions": []
        }
        store["workspaces"][key] = workspace
        save_store(store)

    return workspace


def save_workspace(workspace):
    store = load_store()
    key = str(workspace["assessment_id"])
    workspace["updated_at"] = _now()
    store["workspaces"][key] = workspace
    save_store(store)


def next_question_id(workspace):
    ids = []

    for item in workspace.get("questions", []):
        try:
            ids.append(int(item.get("id", 0)))
        except (TypeError, ValueError):
            pass

    return str(max(ids, default=0) + 1)


def add_question_to_workspace(
    workspace,
    text,
    topic="",
    marks=None
):
    text = str(text or "").strip()

    if not text:
        return False

    if len(workspace["questions"]) >= MAX_QUESTIONS_PER_ASSESSMENT:
        return False

    question = {
        "id": next_question_id(workspace),
        "text": text,
        "topic": str(topic or "").strip(),
        "marks": marks,
        "status": "not_started",
        "notes": "",
        "created_at": _now(),
        "updated_at": _now(),
    }

    workspace["questions"].append(question)
    save_workspace(workspace)
    return True


def manual_add_question(workspace):
    print("\n========== ADD QUESTION ==========")

    text = input(
        "\nQuestion text: "
    ).strip()

    if not text:
        print("\nQuestion cannot be empty.")
        return

    topic = input(
        "Topic (optional): "
    ).strip()

    marks_raw = input(
        "Marks (optional): "
    ).strip()

    marks = None

    if marks_raw:
        try:
            marks = float(marks_raw)
        except ValueError:
            print(
                "\nMarks were not understood; "
                "saving without marks."
            )

    if add_question_to_workspace(
        workspace,
        text,
        topic=topic,
        marks=marks
    ):
        print("\nQuestion added.")
    else:
        print("\nCould not add question.")


def import_questions_from_text(workspace):
    print(
        "\n========== IMPORT QUESTIONS FROM TEXT =========="
    )

    print(
        "Paste questions below."
    )
    print(
        "Enter a blank line twice when finished."
    )

    lines = []
    blank_count = 0

    while True:
        line = input()

        if not line.strip():
            blank_count += 1
            if blank_count >= 2:
                break
            lines.append("")
            continue

        blank_count = 0
        lines.append(line)

    raw_text = "\n".join(lines).strip()

    if not raw_text:
        print("\nNo text entered.")
        return

    # Detect common question numbering:
    # 1. ..., 1) ..., Q1. ..., Question 1 ...
    pattern = re.compile(
        r"(?im)^(?:q(?:uestion)?\s*)?(\d+)\s*[\.\)\-:]\s+"
    )

    matches = list(pattern.finditer(raw_text))

    questions = []

    if matches:
        for index, match in enumerate(matches):
            start = match.end()
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(raw_text)
            )

            text = raw_text[start:end].strip()

            if text:
                questions.append(text)
    else:
        # Fallback: one non-empty paragraph = one question
        questions = [
            part.strip()
            for part in re.split(
                r"\n\s*\n",
                raw_text
            )
            if part.strip()
        ]

    if not questions:
        print("\nNo questions detected.")
        return

    added = 0

    for text in questions:
        if add_question_to_workspace(
            workspace,
            text
        ):
            added += 1

    print(
        f"\nImported {added} question(s)."
    )


def workspace_progress(workspace):
    questions = workspace.get(
        "questions",
        []
    )

    total = len(questions)

    counts = {
        "not_started": 0,
        "attempted": 0,
        "stuck": 0,
        "completed": 0,
    }

    for question in questions:
        status = question.get(
            "status",
            "not_started"
        )

        if status in counts:
            counts[status] += 1

    percent = (
        round(
            100
            * counts["completed"]
            / total
        )
        if total
        else 0
    )

    return {
        "total": total,
        **counts,
        "completed_percent": percent,
    }


def print_workspace_summary(
    assessment,
    workspace
):
    course = find_course(
        assessment.get("course_id")
    )

    progress = workspace_progress(
        workspace
    )

    print(
        "\n========== ASSESSMENT QUESTION WORKSPACE =========="
    )

    print(
        f"Assessment : {assessment['title']}"
    )

    if course:
        print(
            f"Course     : "
            f"{course['code']} - "
            f"{course['name']}"
        )

    print(
        f"Questions  : {progress['total']}"
    )
    print(
        f"Completed  : {progress['completed']} "
        f"({progress['completed_percent']}%)"
    )
    print(
        f"Attempted  : {progress['attempted']}"
    )
    print(
        f"Stuck      : {progress['stuck']}"
    )
    print(
        f"Not started: {progress['not_started']}"
    )


def list_questions(workspace):
    questions = workspace.get(
        "questions",
        []
    )

    if not questions:
        print("\nNo questions in this workspace.")
        return

    print("\n========== QUESTIONS ==========")

    for index, question in enumerate(
        questions,
        start=1
    ):
        topic = (
            f" | topic: {question['topic']}"
            if question.get("topic")
            else ""
        )

        marks = (
            f" | {question['marks']} marks"
            if question.get("marks") is not None
            else ""
        )

        preview = question["text"].replace(
            "\n",
            " "
        )

        if len(preview) > 100:
            preview = preview[:97] + "..."

        print(
            f"{index}. "
            f"[{question['status']}] "
            f"{preview}"
            f"{topic}{marks}"
        )


def choose_question(workspace):
    questions = workspace.get(
        "questions",
        []
    )

    if not questions:
        print("\nNo questions exist yet.")
        return None

    list_questions(workspace)

    try:
        choice = int(
            input(
                "\nChoose question number: "
            ).strip()
        )
    except ValueError:
        print("\nPlease enter a valid number.")
        return None

    if choice < 1 or choice > len(questions):
        print("\nInvalid question number.")
        return None

    return questions[choice - 1]


def update_question_status(workspace):
    question = choose_question(
        workspace
    )

    if not question:
        return

    print("\n1. not_started")
    print("2. attempted")
    print("3. stuck")
    print("4. completed")

    mapping = {
        "1": "not_started",
        "2": "attempted",
        "3": "stuck",
        "4": "completed",
    }

    choice = input(
        "\nNew status: "
    ).strip()

    status = mapping.get(choice)

    if not status:
        print("\nInvalid status.")
        return

    question["status"] = status
    question["updated_at"] = _now()

    save_workspace(
        workspace
    )

    print(
        f"\nQuestion marked {status}."
    )


def add_question_note(workspace):
    question = choose_question(
        workspace
    )

    if not question:
        return

    note = input(
        "\nNote / mistake / reminder: "
    ).strip()

    if not note:
        print("\nNo note entered.")
        return

    existing = question.get(
        "notes",
        ""
    ).strip()

    if existing:
        question["notes"] = (
            existing
            + "\n"
            + note
        )
    else:
        question["notes"] = note

    question["updated_at"] = _now()
    save_workspace(workspace)

    print("\nQuestion note saved.")


def edit_question_topic(workspace):
    question = choose_question(
        workspace
    )

    if not question:
        return

    topic = input(
        "\nTopic for this question: "
    ).strip()

    question["topic"] = topic
    question["updated_at"] = _now()
    save_workspace(workspace)

    print("\nTopic updated.")


def delete_question(workspace):
    question = choose_question(
        workspace
    )

    if not question:
        return

    confirm = input(
        "\nType yes to delete this question: "
    ).strip().lower()

    if confirm != "yes":
        print("\nDelete cancelled.")
        return

    workspace["questions"] = [
        item
        for item in workspace["questions"]
        if str(item.get("id"))
        != str(question.get("id"))
    ]

    save_workspace(workspace)

    print("\nQuestion deleted.")


def build_question_prompt(
    assessment,
    question
):
    topic_text = (
        question.get("topic")
        or "not explicitly tagged"
    )

    note_text = (
        question.get("notes")
        or "none"
    )

    return (
        f"I am working on this assessment question:\n"
        f"{question['text']}\n\n"
        f"Assessment: {assessment['title']}\n"
        f"Assessment type: {assessment['type']}\n"
        f"Question topic tag: {topic_text}\n"
        f"My notes/mistakes: {note_text}\n\n"
        "Help me solve or understand this question using ONLY my selected "
        "course sources. First identify the concept being tested. Then give "
        "the minimum prerequisite explanation needed. Then guide the solution "
        "step by step. Do not invent syllabus facts absent from the sources. "
        "Do not mark the question completed automatically."
    )


def source_grounded_question_help(
    assessment,
    workspace
):
    question = choose_question(
        workspace
    )

    if not question:
        return

    course = find_course(
        assessment.get("course_id")
    )

    if not course:
        print("\nCourse not found.")
        return

    semantic_chunks = (
        load_semantic_index()
    )

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

    try:
        answer, results = rag_answer(
            build_question_prompt(
                assessment,
                question
            ),
            semantic_chunks,
            course_id=course["id"],
            mode_instruction=(
                "You are in Assessment Question Workspace mode. "
                "Stay strictly within the selected course sources. "
                "Guide the student through the question rather than merely "
                "dumping an unsupported answer. If source context is missing, say so."
            )
        )
    except Exception as error:
        print(
            f"\nQuestion help failed: {error}"
        )
        return

    if answer is None:
        print(
            "\nNot enough relevant course material was found."
        )
        return

    print(
        "\n========== SOURCE-GROUNDED QUESTION HELP =========="
    )

    print(
        clean_terminal_markdown(
            answer
        )
    )

    print_verified_sources(
        results
    )


def next_question_to_work_on(
    workspace
):
    questions = workspace.get(
        "questions",
        []
    )

    if not questions:
        print("\nNo questions exist yet.")
        return

    status_order = {
        "stuck": 0,
        "attempted": 1,
        "not_started": 2,
        "completed": 3,
    }

    candidates = sorted(
        questions,
        key=lambda question: (
            status_order.get(
                question.get(
                    "status",
                    "not_started"
                ),
                9
            ),
            -(
                question.get("marks")
                if isinstance(
                    question.get("marks"),
                    (int, float)
                )
                else 0
            )
        )
    )

    selected = candidates[0]

    if selected.get("status") == "completed":
        print(
            "\nEvery question is marked completed."
        )
        return

    print(
        "\n========== NEXT QUESTION TO WORK ON =========="
    )
    print(
        f"Status : {selected['status']}"
    )
    print(
        f"Topic  : "
        f"{selected.get('topic') or 'Not tagged'}"
    )
    print(
        f"\n{selected['text']}"
    )

    if selected.get("notes"):
        print(
            f"\nSaved note: {selected['notes']}"
        )


def assessment_question_workspace_menu():
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
        print_workspace_summary(
            assessment,
            workspace
        )

        print(
            "\n========== V10.1 QUESTION WORKSPACE =========="
        )
        print("1. View Questions")
        print("2. Add Question Manually")
        print("3. Import Questions from Pasted Text")
        print("4. Update Question Status")
        print("5. Add Question Note / Mistake")
        print("6. Tag Question Topic")
        print("7. Source-Grounded Help for One Question")
        print("8. What Question Should I Work on Next?")
        print("9. Delete Question")
        print("10. Change Assessment")
        print("11. Back")

        choice = input(
            "\nEnter your choice (1-11): "
        ).strip()

        if choice == "1":
            list_questions(
                workspace
            )

        elif choice == "2":
            manual_add_question(
                workspace
            )

        elif choice == "3":
            import_questions_from_text(
                workspace
            )

        elif choice == "4":
            update_question_status(
                workspace
            )

        elif choice == "5":
            add_question_note(
                workspace
            )

        elif choice == "6":
            edit_question_topic(
                workspace
            )

        elif choice == "7":
            source_grounded_question_help(
                assessment,
                workspace
            )

        elif choice == "8":
            next_question_to_work_on(
                workspace
            )

        elif choice == "9":
            delete_question(
                workspace
            )

        elif choice == "10":
            new_assessment = choose_assessment(
                include_completed=True
            )

            if new_assessment:
                assessment = new_assessment
                workspace = get_workspace(
                    assessment["id"],
                    create=True
                )

        elif choice == "11":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 11."
            )


if __name__ == "__main__":
    assessment_question_workspace_menu()
