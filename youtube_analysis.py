import os

from semantic_retrieval import load_semantic_index
from hybrid_retrieval import hybrid_search
from rag_answer import call_llm, clean_terminal_markdown, print_verified_sources
from youtube_ingestion import YOUTUBE_DIR

ANALYSIS_TOP_K = 6


def list_transcript_files():
    if not os.path.exists(YOUTUBE_DIR):
        return []
    return sorted(
        os.path.join(YOUTUBE_DIR, name)
        for name in os.listdir(YOUTUBE_DIR)
        if name.lower().endswith(".md")
    )


def choose_transcript():
    files = list_transcript_files()

    if not files:
        print("\nNo imported YouTube transcripts found.")
        return None

    print("\n========== IMPORTED YOUTUBE LECTURES ==========")

    for i, path in enumerate(files, start=1):
        print(f"{i}. {os.path.basename(path)}")

    try:
        choice = int(input("\nChoose lecture number: ").strip())
    except ValueError:
        print("\nPlease enter a valid number.")
        return None

    if choice < 1 or choice > len(files):
        print("\nInvalid lecture number.")
        return None

    return files[choice - 1]


def get_transcript_title(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            first = file.readline().strip()
        if first.startswith("# "):
            return first[2:].strip()
    except OSError:
        pass
    return os.path.basename(file_path)


def retrieve_lecture_context(lecture_path, semantic_chunks):
    matches = []

    for item in semantic_chunks:
        if os.path.abspath(item["file"]) == os.path.abspath(lecture_path):
            matches.append({
                "file": item["file"],
                "text": item["text"],
                "score": 1.0,
                "page": None
            })

    return matches[:ANALYSIS_TOP_K]


def build_context(results):
    return "\n\n".join(
        f"[LECTURE CHUNK {i}]\n{result['text'].strip()}"
        for i, result in enumerate(results, start=1)
    )


def run_analysis_prompt(lecture_path, semantic_chunks, mode_name, instruction):
    results = retrieve_lecture_context(lecture_path, semantic_chunks)

    if not results:
        print("\nCould not retrieve transcript content.")
        return

    title = get_transcript_title(lecture_path)
    context = build_context(results)

    messages = [
        {
            "role": "system",
            "content": (
                "You are Anand's YouTube lecture analysis assistant. "
                "Use ONLY the supplied lecture transcript context. "
                "Do not add outside facts unless explicitly requested. "
                "Preserve the lecture's terminology and level of detail. "
                "If the transcript does not support a point, say so. "
                "Use simple, clear English and plain terminal-friendly text."
            )
        },
        {
            "role": "user",
            "content": (
                f"LECTURE TITLE:\n{title}\n\n"
                f"ANALYSIS TASK:\n{instruction}\n\n"
                f"LECTURE TRANSCRIPT CONTEXT:\n{context}\n\n"
                "Produce the requested analysis."
            )
        }
    ]

    try:
        answer = call_llm(messages)
    except Exception as error:
        print(f"\nLecture analysis failed: {error}")
        return

    print(f"\n========== {mode_name.upper()} ==========")
    print(clean_terminal_markdown(answer))
    print_verified_sources(results)


def compare_with_obsidian(lecture_path, semantic_chunks):
    title = get_transcript_title(lecture_path)
    lecture_results = retrieve_lecture_context(lecture_path, semantic_chunks)

    if not lecture_results:
        print("\nCould not retrieve lecture content.")
        return

    related = hybrid_search(
        f"notes related to {title}",
        semantic_chunks,
        final_top_k=10
    )

    note_results = [
        result for result in related
        if result["file"].lower().endswith(".md")
        and "youtube_transcripts" not in result["file"].lower()
    ][:6]

    if not note_results:
        print("\nNo related non-YouTube Markdown notes were found.")
        return

    messages = [
        {
            "role": "system",
            "content": (
                "Compare the supplied lecture transcript context with the supplied study notes. "
                "Use only those sources. Identify overlap, missing notes, useful additions, "
                "and any visible inconsistency. Use plain terminal-friendly text."
            )
        },
        {
            "role": "user",
            "content": (
                f"LECTURE:\n{title}\n\n"
                f"LECTURE CONTEXT:\n{build_context(lecture_results)}\n\n"
                f"RELATED NOTES CONTEXT:\n{build_context(note_results)}\n\n"
                "Provide:\n"
                "1. Concepts already covered in notes\n"
                "2. Concepts missing from notes\n"
                "3. Suggested additions to Obsidian\n"
                "4. Any conflict or inconsistency visible in the supplied sources"
            )
        }
    ]

    try:
        answer = call_llm(messages)
    except Exception as error:
        print(f"\nComparison failed: {error}")
        return

    print("\n========== LECTURE VS OBSIDIAN ==========")
    print(clean_terminal_markdown(answer))
    print("\nLECTURE SOURCES")
    print_verified_sources(lecture_results)
    print("\nRELATED NOTES")
    print_verified_sources(note_results)


def lecture_analysis_menu():
    semantic_chunks = load_semantic_index()

    if semantic_chunks is None:
        print("\nNo semantic index available.")
        return

    lecture_path = choose_transcript()

    if not lecture_path:
        return

    while True:
        print("\n========== YOUTUBE LECTURE ANALYSIS V7.1 ==========")
        print(f"Lecture: {get_transcript_title(lecture_path)}")
        print("\n1. Lecture Summary")
        print("2. Key Concepts")
        print("3. Revision Notes")
        print("4. Practice Questions")
        print("5. Knowledge Gaps")
        print("6. Compare with Obsidian Notes")
        print("7. Choose Different Lecture")
        print("8. Back")

        choice = input("\nEnter your choice (1-8): ").strip()

        if choice == "1":
            run_analysis_prompt(
                lecture_path, semantic_chunks, "Lecture Summary",
                "Summarize the lecture in a structured way. Include the central idea, "
                "progression of topics, and the most important explanations from the transcript."
            )
        elif choice == "2":
            run_analysis_prompt(
                lecture_path, semantic_chunks, "Key Concepts",
                "Extract the key concepts taught in this lecture. For each concept, "
                "give a short explanation based only on the transcript."
            )
        elif choice == "3":
            run_analysis_prompt(
                lecture_path, semantic_chunks, "Revision Notes",
                "Create concise revision notes from this lecture. Include definitions, "
                "formulas or procedures mentioned, important examples, and a quick checklist."
            )
        elif choice == "4":
            run_analysis_prompt(
                lecture_path, semantic_chunks, "Practice Questions",
                "Generate 8 practice questions based only on this lecture, "
                "from basic recall to application. Do not provide answers."
            )
        elif choice == "5":
            run_analysis_prompt(
                lecture_path, semantic_chunks, "Knowledge Gaps",
                "Identify concepts in the lecture that would likely require prerequisite knowledge "
                "or further study. Only mention gaps supported by the transcript itself."
            )
        elif choice == "6":
            compare_with_obsidian(lecture_path, semantic_chunks)
        elif choice == "7":
            lecture_path = choose_transcript()
            if not lecture_path:
                return
        elif choice == "8":
            break
        else:
            print("\nInvalid choice. Please enter 1 to 8.")


if __name__ == "__main__":
    lecture_analysis_menu()
