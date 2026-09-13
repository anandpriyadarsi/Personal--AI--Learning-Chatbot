"""Source-grounded global and course-aware RAG tutoring for V8."""

import os
import re
import requests

from knowledge import BASE_DIR, read_text_file, retrieve_best_chunks
from semantic_retrieval import load_semantic_index
from hybrid_retrieval import hybrid_search
from course_manager import (
    choose_course,
    find_course,
    get_active_course,
    get_course_progress,
    get_document_metadata,
    print_course_progress,
    recommend_next_topics
)
from learning_memory import (
    build_memory_context,
    record_activity,
    mark_weak_topic,
    mark_mastered_topic,
    add_memory_note
)


DEFAULT_TOP_K = 5
DEFAULT_MAX_CONTEXT_CHARS = 12000
MAX_HISTORY_MESSAGES = 6
COURSE_CANDIDATE_MULTIPLIER = 5

TUTOR_MODES = {
    "1": {
        "name": "Explain a Concept",
        "instruction": (
            "Explain the concept with intuition first, then the formal idea, "
            "then a small example. End with 2 quick self-check questions."
        )
    },
    "2": {
        "name": "Solve a Doubt",
        "instruction": (
            "Diagnose the exact confusion first. Then resolve it step by step. "
            "Do not skip prerequisite ideas. Use a small worked example when useful."
        )
    },
    "3": {
        "name": "Summarize a Topic",
        "instruction": (
            "Create a concise academic summary containing the core idea, key definitions, "
            "important formulas or rules, common mistakes, and a short revision checklist."
        )
    },
    "4": {
        "name": "Generate Practice Questions",
        "instruction": (
            "Generate 5 practice questions based only on the retrieved academic context. "
            "Order them from easy to challenging. Do not give solutions unless asked."
        )
    },
    "5": {
        "name": "Quiz Me",
        "instruction": (
            "Act as an interactive tutor. Ask only ONE question at a time based on the "
            "retrieved context. Wait for the student's answer before evaluating it."
        )
    },
    "6": {
        "name": "Study Guidance",
        "instruction": (
            "Give practical study guidance from the retrieved material. Identify prerequisites, "
            "what to learn first, what to practise, and a short next-step plan."
        )
    },
    "7": {
        "name": "Free Academic Chat",
        "instruction": (
            "Answer naturally as a personal academic tutor while staying grounded in the "
            "retrieved context."
        )
    }
}

COURSE_TUTOR_MODES = {
    "1": {
        "name": "Course Question and Explanation",
        "instruction": (
            "Answer the question only from the selected course sources. "
            "Teach with intuition first, then formal detail and a small example."
        ),
        "default_question": ""
    },
    "2": {
        "name": "Solve a Course Doubt",
        "instruction": (
            "Identify the student's exact confusion inside the selected course, "
            "repair any missing prerequisite, and solve the doubt step by step."
        ),
        "default_question": ""
    },
    "3": {
        "name": "Revision Guidance",
        "instruction": (
            "Create a focused revision guide for the selected course. Prioritize weak, "
            "learning, and review topics. Include recall, practice, and self-check steps."
        ),
        "default_question": (
            "Using my course progress and course sources, what should I revise now, "
            "in what order, and how should I check that I understand it?"
        )
    },
    "4": {
        "name": "Course Practice Questions",
        "instruction": (
            "Generate 5 questions from the selected course sources, easy to challenging. "
            "Target weak or unfinished topics when the memory identifies them. "
            "Do not give solutions unless asked."
        ),
        "default_question": "Generate course-focused practice questions for my current need."
    },
    "5": {
        "name": "Course Quiz",
        "instruction": (
            "Quiz the student only on the selected course. Ask ONE question at a time, "
            "wait for the answer, then evaluate it before continuing."
        ),
        "default_question": "Start a quiz using my selected course sources and progress."
    },
    "6": {
        "name": "What Should I Study Next?",
        "instruction": (
            "Recommend the next study action for the selected course. Use course topic "
            "status and learning memory, explain the reason, and give a realistic short plan."
        ),
        "default_question": (
            "Based on my course topics, progress, weak areas, and sources, "
            "what should I study next?"
        )
    }
}


# --------------------------------------------------
# Configuration
# --------------------------------------------------

def load_local_env():
    """Load BASE_DIR/.env when python-dotenv is installed.

    Environment variables still work normally when the optional package is not
    installed, so this does not break the current V7 setup.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    return True


def get_llm_config():
    load_local_env()
    api_url = os.getenv("LLM_API_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()

    return api_url, api_key, model


def llm_is_configured():
    api_url, api_key, model = get_llm_config()
    return bool(api_url and api_key and model)


# --------------------------------------------------
# Source helpers
# --------------------------------------------------

def extract_page_number(text):
    match = re.search(r"--- Page (\d+) ---", text)

    if match:
        return int(match.group(1))

    return None


def make_source_label(result):
    try:
        relative_path = os.path.relpath(result["file"], BASE_DIR)
    except ValueError:
        relative_path = os.path.abspath(result["file"])

    page = result.get("page")

    if page is None:
        page = extract_page_number(
            result["text"]
        )

    course_code = result.get("course_code")
    topic = result.get("topic")
    details = []

    if course_code:
        details.append(f"course {course_code}")
    if topic:
        details.append(f"topic {topic}")
    if page is not None:
        details.append(f"page {page}")

    if details:
        return f"{relative_path} | " + " | ".join(details)

    return relative_path


def clean_terminal_markdown(text):
    """Convert common Markdown/LaTeX from LLM output into clean terminal text."""
    if not text:
        return text

    # Markdown headings and emphasis
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)
    text = re.sub(r"(?<!_)_(?!_)", "", text)

    # Common LaTeX wrappers generated by chat models
    text = text.replace(r"\(", "").replace(r"\)", "")
    text = text.replace(r"\[", "").replace(r"\]", "")
    text = text.replace(r"\mathbf", "").replace(r"\text", "")
    text = text.replace(r"\times", "x")
    text = text.replace(r"\cdot", "*")
    text = text.replace(r"\leq", "<=").replace(r"\geq", ">=")
    text = text.replace(r"\neq", "!=")

    # Remove braces left by simple LaTeX commands, while keeping content
    text = text.replace("{", "").replace("}", "")

    # Make excessive blank lines compact
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def display_name(file_path):
    """Return only the document filename for user-facing citations."""
    return os.path.basename(file_path)


def print_verified_sources(results):
    """Print the exact retrieved documents/pages independently of the LLM."""
    if not results:
        return

    print("\nSOURCES RETRIEVED")
    seen = set()

    for result in results:
        page = result.get("page")
        if page is None:
            page = extract_page_number(result.get("text", ""))

        name = display_name(result["file"])
        course_code = result.get("course_code")
        topic = result.get("topic")
        key = (name, page, course_code, topic)

        if key in seen:
            continue
        seen.add(key)

        details = []
        if course_code:
            details.append(course_code)
        if topic:
            details.append(topic)
        if page is not None:
            details.append(f"page {page}")

        suffix = " - " + " - ".join(details) if details else ""
        print(f"- {name}{suffix}")


# --------------------------------------------------
# Build RAG context
# --------------------------------------------------

def build_context(results, max_chars=DEFAULT_MAX_CONTEXT_CHARS):
    context_parts = []
    used_chars = 0

    for number, result in enumerate(results, start=1):
        source = make_source_label(result)

        course_line = ""
        if result.get("course_code"):
            course_line = (
                f"COURSE: {result['course_code']} - "
                f"{result.get('course_name', '')}\n"
            )
        if result.get("topic"):
            course_line += f"TOPIC TAG: {result['topic']}\n"

        block = (
            f"[SOURCE {number}]\n"
            f"{source}\n\n"
            f"{course_line}"
            f"{result['text'].strip()}\n"
        )

        if used_chars + len(block) > max_chars:
            remaining = max_chars - used_chars

            if remaining > 300:
                context_parts.append(
                    block[:remaining]
                )

            break

        context_parts.append(block)
        used_chars += len(block)

    return "\n\n".join(context_parts)


# --------------------------------------------------
# Prompt
# --------------------------------------------------

def build_messages(
    question,
    context,
    conversation_history=None,
    mode_instruction=None,
    persistent_memory=None,
    course_context=None
):
    system_message = (
        "You are Anand's personal academic learning assistant. "
        "Answer using ONLY the supplied academic context plus the conversation history. "
        "Persistent learning memory may describe weak topics, mastered topics, or recent study activity. "
        "Use that memory only to personalize explanation depth and study guidance. "
        "Do not treat persistent memory as an academic factual source. "
        "Do not invent facts that are not supported by the academic context. "
        "Use conversation history only to understand follow-up references such as "
        "'step 2', 'that method', 'give me an example', or 'explain it again'. "
        "If the retrieved academic context is insufficient, clearly say what is missing. "
        "Use simple, clear English. "
        "Teach with intuition first, then mathematics or technical detail. "
        "When useful, give step-by-step guidance. "
        "Write for a plain Windows terminal: do not use Markdown bold markers, "
        "Markdown headings, or LaTeX wrappers. "
        "Use readable plain-text mathematics such as A = LU and Ax = b. "
        "Do not invent source names, page numbers, or citations. "
        "The application will print verified retrieved sources separately."
    )

    if course_context:
        system_message += (
            " You are in STRICT COURSE-AWARE MODE. "
            "Use only sources tagged to the selected course. "
            "Never mix facts from another course. "
            "Course progress and memory personalize priorities but are not factual sources."
        )

    if mode_instruction:
        system_message += (
            " CURRENT TUTOR MODE INSTRUCTION: "
            + mode_instruction
        )

    if persistent_memory:
        system_message += (
            "\nPERSISTENT LEARNING MEMORY:\n"
            + persistent_memory
        )

    if course_context:
        system_message += (
            "\nSELECTED COURSE AND PROGRESS:\n"
            + course_context
        )

    messages = [
        {
            "role": "system",
            "content": system_message
        }
    ]

    if conversation_history:
        messages.extend(
            conversation_history[-MAX_HISTORY_MESSAGES:]
        )

    user_message = (
        f"CURRENT QUESTION:\n{question}\n\n"
        + (
            f"SELECTED COURSE:\n{course_context}\n\n"
            if course_context else ""
        )
        + f"RETRIEVED ACADEMIC CONTEXT:\n{context}\n\n"
        "Answer the current question using the retrieved academic context. "
        "Use the conversation history only to resolve what the user is referring to."
    )

    messages.append(
        {
            "role": "user",
            "content": user_message
        }
    )

    return messages


# --------------------------------------------------
# Call an OpenAI-compatible chat endpoint
# --------------------------------------------------

def call_llm(messages):
    api_url, api_key, model = get_llm_config()

    if not api_url or not api_key or not model:
        raise RuntimeError(
            "LLM is not configured. Set LLM_API_URL, "
            "LLM_API_KEY and LLM_MODEL."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2
    }

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=90
    )

    response.raise_for_status()

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "The LLM returned an unexpected response format."
        )


# --------------------------------------------------
# Conversation memory helpers
# --------------------------------------------------

FOLLOW_UP_HINTS = {
    "it", "this", "that", "these", "those",
    "step", "second", "first", "third",
    "example", "again", "more", "why",
    "how", "now", "same", "method"
}


def is_follow_up_question(question):
    words = re.findall(r"[A-Za-z0-9]+", question.lower())

    if len(words) <= 8:
        return True

    return any(word in FOLLOW_UP_HINTS for word in words)


def get_recent_user_question(conversation_history):
    if not conversation_history:
        return None

    for message in reversed(conversation_history):
        if message.get("role") == "user":
            return message.get("content")

    return None


def build_retrieval_query(question, conversation_history):
    previous_question = get_recent_user_question(
        conversation_history
    )

    if (
        previous_question
        and is_follow_up_question(question)
    ):
        return (
            f"{previous_question}\n"
            f"Follow-up: {question}"
        )

    return question


def add_turn_to_history(
    conversation_history,
    question,
    answer
):
    conversation_history.append({
        "role": "user",
        "content": question
    })

    conversation_history.append({
        "role": "assistant",
        "content": clean_terminal_markdown(answer)
    })

    if len(conversation_history) > MAX_HISTORY_MESSAGES:
        del conversation_history[:-MAX_HISTORY_MESSAGES]


# --------------------------------------------------
# Retrieve + Answer
# --------------------------------------------------

def build_course_context(course_id):
    course = find_course(course_id)
    if course is None:
        return None

    progress = get_course_progress(course["id"])
    lines = [
        f"Course code: {course['code']}",
        f"Course name: {course['name']}",
        f"Semester: {course['semester'] or 'Not set'}",
        f"Course status: {course['status']}",
        (
            f"Mastery progress: {progress['mastered_topics']}/"
            f"{progress['total_topics']} topics "
            f"({progress['progress_percent']}%)"
        )
    ]

    if course["topics"]:
        lines.append("Topic progress:")
        for topic in course["topics"]:
            confidence = (
                f", confidence {topic['confidence']}/5"
                if topic.get("confidence") else ""
            )
            lines.append(
                f"- {topic['name']}: {topic['status']}{confidence}"
            )
    else:
        lines.append("Topic progress: No course topics have been added yet.")

    recommendations = recommend_next_topics(course["id"], limit=5)
    if recommendations:
        lines.append("Priority topics suggested by stored progress:")
        for topic in recommendations:
            lines.append(f"- {topic['name']} ({topic['status']})")

    return "\n".join(lines)


def _metadata_for_result(result):
    file_path = result.get("file")
    if not file_path:
        return {}

    metadata = get_document_metadata(
        file_path,
        result.get("text", "")
    )

    if (
        metadata.get("course_id") is None
        and os.path.splitext(file_path)[1].lower() in {".md", ".txt"}
    ):
        content = read_text_file(file_path)
        if not content.startswith("[Could not"):
            metadata = get_document_metadata(file_path, content)

    return metadata


def _result_key(result):
    return (
        os.path.normcase(os.path.abspath(result.get("file", ""))),
        result.get("page"),
        result.get("text", "")[:160]
    )


def course_aware_search(query, semantic_chunks, course_id, top_k=DEFAULT_TOP_K):
    """Retrieve only material belonging to one selected course.

    Hybrid results are filtered by explicit/automatic course tags. A
    course-filtered lexical fallback is merged in so a relevant source is not
    lost merely because another course dominated the global semantic top-k.
    """
    course = find_course(course_id)
    if course is None:
        return []

    candidate_count = max(top_k * COURSE_CANDIDATE_MULTIPLIER, 20)
    candidates = hybrid_search(
        query,
        semantic_chunks,
        final_top_k=candidate_count
    )

    filtered = []
    seen = set()
    for raw_result in candidates:
        result = dict(raw_result)
        metadata = _metadata_for_result(result)
        if metadata.get("course_id") != course["id"]:
            continue
        result.update(metadata)
        key = _result_key(result)
        if key not in seen:
            filtered.append(result)
            seen.add(key)

    lexical_results = retrieve_best_chunks(
        query,
        top_k=max(top_k, 8),
        course_id=course["id"]
    )
    for raw_result in lexical_results:
        result = dict(raw_result)
        key = _result_key(result)
        if key not in seen:
            filtered.append(result)
            seen.add(key)

    return filtered[:top_k]


def rag_answer(
    question,
    semantic_chunks,
    conversation_history=None,
    top_k=DEFAULT_TOP_K,
    mode_instruction=None,
    course_id=None
):
    retrieval_query = build_retrieval_query(
        question,
        conversation_history
    )

    if course_id:
        results = course_aware_search(
            retrieval_query,
            semantic_chunks,
            course_id,
            top_k=top_k
        )
    else:
        results = hybrid_search(
            retrieval_query,
            semantic_chunks,
            final_top_k=top_k
        )

    if not results:
        return None, []

    context = build_context(results)

    persistent_memory = build_memory_context(course_id=course_id)
    course_context = build_course_context(course_id) if course_id else None

    messages = build_messages(
        question,
        context,
        conversation_history,
        mode_instruction,
        persistent_memory,
        course_context
    )

    answer = call_llm(messages)

    return answer, results


# --------------------------------------------------
# Fallback preview when no API is configured
# --------------------------------------------------

def show_retrieved_context(question, semantic_chunks, course_id=None):
    if course_id:
        results = course_aware_search(
            question,
            semantic_chunks,
            course_id,
            top_k=DEFAULT_TOP_K
        )
    else:
        results = hybrid_search(
            question,
            semantic_chunks,
            final_top_k=DEFAULT_TOP_K
        )

    if not results:
        print("\nNo relevant context found.")
        return

    print(
        "\n========== RETRIEVED CONTEXT =========="
    )

    for number, result in enumerate(
        results,
        start=1
    ):
        print(
            f"\n[{number}] "
            f"{make_source_label(result)}"
        )
        print("-" * 70)
        print(result["text"][:1200])

        if len(result["text"]) > 1200:
            print("\n[Context preview truncated...]")


# --------------------------------------------------
# Academic Tutor Modes
# --------------------------------------------------

def show_tutor_modes():
    print("\n========== ACADEMIC TUTOR MODES ==========")
    print("1. Explain a Concept")
    print("2. Solve a Doubt")
    print("3. Summarize a Topic")
    print("4. Generate Practice Questions")
    print("5. Quiz Me")
    print("6. Study Guidance")
    print("7. Free Academic Chat")
    print("8. Back")


def choose_tutor_mode():
    while True:
        show_tutor_modes()

        choice = input(
            "\nChoose tutor mode (1-8): "
        ).strip()

        if choice == "8":
            return None

        if choice in TUTOR_MODES:
            mode = TUTOR_MODES[choice]

            print(
                f"\nTutor mode: {mode['name']}"
            )

            return mode

        print(
            "\nInvalid choice. Please enter 1 to 8."
        )


# --------------------------------------------------
# Interactive RAG mode
# --------------------------------------------------

def rag_chat_loop():
    print(
        "\n========== RAG ACADEMIC ASSISTANT V5 =========="
    )

    semantic_chunks = load_semantic_index()

    if semantic_chunks is None:
        print(
            "\nNo saved semantic index found."
        )
        print(
            "Run semantic_retrieval.py and build the index first."
        )
        return

    if not llm_is_configured():
        print(
            "\nLLM API is not configured yet."
        )
        print(
            "RAG retrieval will still work, but answer generation "
            "needs these environment variables:"
        )
        print("  LLM_API_URL")
        print("  LLM_API_KEY")
        print("  LLM_MODEL")

    while True:
        mode = choose_tutor_mode()

        if mode is None:
            break

        conversation_history = []

        print(
            "\nConversation memory is ON for this tutor mode."
        )
        print(
            "Commands: back = change mode | clear = reset conversation"
        )

        while True:
            question = input(
                f"\n[{mode['name']}] Ask: "
            ).strip()

            if question.lower() == "back":
                break

            if question.lower() == "clear":
                conversation_history.clear()
                print(
                    "\nConversation memory cleared."
                )
                continue

            if question.lower().startswith("weak "):
                topic = question[5:].strip()

                if mark_weak_topic(topic):
                    print(
                        f"\nPersistent memory updated: weak topic = {topic}"
                    )
                continue

            if question.lower().startswith("mastered "):
                topic = question[9:].strip()

                if mark_mastered_topic(topic):
                    print(
                        f"\nPersistent memory updated: mastered topic = {topic}"
                    )
                continue

            if question.lower().startswith("remember "):
                note = question[9:].strip()

                if add_memory_note(note):
                    print(
                        "\nPersistent learning note saved."
                    )
                continue

            if not question:
                continue

            if not llm_is_configured():
                show_retrieved_context(
                    question,
                    semantic_chunks
                )
                continue

            try:
                print(
                    "\nRetrieving knowledge and generating answer..."
                )

                answer, results = rag_answer(
                    question,
                    semantic_chunks,
                    conversation_history,
                    mode_instruction=mode["instruction"]
                )

                if answer is None:
                    print(
                        "\nI could not find enough relevant material "
                        "in your knowledge library."
                    )
                    continue

                print(
                    "\n========== AI ACADEMIC ANSWER =========="
                )
                print(
                    clean_terminal_markdown(answer)
                )
                print_verified_sources(results)

                add_turn_to_history(
                    conversation_history,
                    question,
                    answer
                )

                record_activity(
                    mode["name"],
                    question
                )

            except requests.Timeout:
                print(
                    "\nThe LLM request timed out. "
                    "Please try again."
                )

            except requests.RequestException as error:
                print(
                    f"\nLLM request failed: {error}"
                )

            except RuntimeError as error:
                print(
                    f"\n{error}"
                )


def show_course_tutor_modes(course):
    print("\n========== COURSE-AWARE ACADEMIC ASSISTANT V8 ==========")
    print(f"Selected course: {course['code']} - {course['name']}")
    print("1. Course Question and Explanation")
    print("2. Solve a Course Doubt")
    print("3. Revision Guidance")
    print("4. Course Practice Questions")
    print("5. Course Quiz")
    print("6. What Should I Study Next?")
    print("7. View Course Progress")
    print("8. View Priority Topics")
    print("9. Change Course")
    print("10. Back")


def show_priority_topics(course):
    topics = recommend_next_topics(course["id"], limit=5)
    print(f"\n========== {course['code']} PRIORITY TOPICS ==========")

    if not course["topics"]:
        print("\nNo course topics exist yet.")
        print("Add the syllabus topics in Course Manager first.")
        return

    if not topics:
        print("\nEvery stored topic is marked mastered.")
        print("Use spaced revision and mixed practice to maintain mastery.")
        return

    for number, topic in enumerate(topics, start=1):
        reason = {
            "weak": "repair this weak area first",
            "learning": "finish the topic currently being learned",
            "review": "review is due",
            "not_started": "next unfinished syllabus topic"
        }.get(topic["status"], "continue building mastery")
        print(f"{number}. {topic['name']} - {reason}")


def _course_mode_loop(course, mode, semantic_chunks):
    conversation_history = []
    default_question = mode.get("default_question", "")

    print(f"\nMode: {mode['name']}")
    print("Conversation memory is ON for this course and mode.")
    print("Commands: back = change mode | clear = reset conversation")
    print("Memory commands: weak TOPIC | mastered TOPIC | remember NOTE")

    while True:
        prompt = f"\n[{course['code']} | {mode['name']}] Ask"
        if default_question:
            prompt += " (press Enter for suggested request)"
        question = input(prompt + ": ").strip()

        if question.lower() == "back":
            break

        if question.lower() == "clear":
            conversation_history.clear()
            print("\nConversation memory cleared.")
            continue

        if question.lower().startswith("weak "):
            topic = question[5:].strip()
            if mark_weak_topic(topic, course_id=course["id"]):
                print(f"\n{course['code']} memory updated: weak topic = {topic}")
            continue

        if question.lower().startswith("mastered "):
            topic = question[9:].strip()
            if mark_mastered_topic(topic, course_id=course["id"]):
                print(f"\n{course['code']} memory updated: mastered topic = {topic}")
            continue

        if question.lower().startswith("remember "):
            note = question[9:].strip()
            if add_memory_note(note, course_id=course["id"]):
                print(f"\nLearning note saved inside {course['code']} memory.")
            continue

        if not question:
            question = default_question
        if not question:
            continue

        if not llm_is_configured():
            show_retrieved_context(
                question,
                semantic_chunks,
                course_id=course["id"]
            )
            print("\nConfigure the LLM variables to generate a full answer.")
            continue

        try:
            print("\nRetrieving only this course and generating an answer...")
            answer, results = rag_answer(
                question,
                semantic_chunks,
                conversation_history,
                mode_instruction=mode["instruction"],
                course_id=course["id"]
            )

            if answer is None:
                print("\nNo relevant source tagged to this course was found.")
                print("Use Course Manager -> Link Knowledge Source to Course,")
                print("or put the course code in the source path/Markdown course tag.")
                continue

            print("\n========== COURSE-AWARE ANSWER ==========")
            print(clean_terminal_markdown(answer))
            print_verified_sources(results)

            add_turn_to_history(
                conversation_history,
                question,
                answer
            )
            record_activity(
                mode["name"],
                question,
                course_id=course["id"]
            )

        except requests.Timeout:
            print("\nThe LLM request timed out. Please try again.")
        except requests.RequestException as error:
            print(f"\nLLM request failed: {error}")
        except RuntimeError as error:
            print(f"\n{error}")


def course_rag_chat_loop():
    print("\n========== COURSE-AWARE ACADEMIC ASSISTANT V8 ==========")

    semantic_chunks = load_semantic_index()
    if semantic_chunks is None:
        print("\nNo saved semantic index found.")
        print("Run semantic_retrieval.py and build the index first.")
        return

    course = get_active_course()
    if course is None:
        course = choose_course("Select Course for Academic Assistant")
    if course is None:
        return

    if not llm_is_configured():
        print("\nLLM API is not configured. Course-filtered retrieval still works,")
        print("but generated tutoring needs LLM_API_URL, LLM_API_KEY, and LLM_MODEL.")

    while True:
        refreshed = find_course(course["id"])
        if refreshed:
            course = refreshed
        show_course_tutor_modes(course)
        choice = input("\nEnter your choice (1-10): ").strip()

        if choice in COURSE_TUTOR_MODES:
            _course_mode_loop(course, COURSE_TUTOR_MODES[choice], semantic_chunks)
        elif choice == "7":
            print_course_progress(course["id"])
        elif choice == "8":
            show_priority_topics(course)
        elif choice == "9":
            selected = choose_course("Change Academic Assistant Course")
            if selected:
                course = selected
        elif choice == "10":
            break
        else:
            print("\nInvalid choice. Please enter 1 to 10.")


if __name__ == "__main__":
    rag_chat_loop()
