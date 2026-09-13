"""Knowledge ingestion and retrieval for Personal AI Learning Chatbot V8."""

import os
import re

from knowledge_paths import BASE_DIR
from obsidian_integration import (
    get_obsidian_markdown_files,
    get_vault_path
)
from course_manager import (
    find_course,
    get_document_metadata
)


KNOWLEDGE_DIR = os.path.join(
    BASE_DIR,
    "knowledge"
)

OBSIDIAN_DIR = os.path.join(
    KNOWLEDGE_DIR,
    "obsidian"
)

DOCUMENTS_DIR = os.path.join(
    KNOWLEDGE_DIR,
    "documents"
)

SUPPORTED_EXTENSIONS = [
    ".md",
    ".txt",
    ".pdf"
]

LOCAL_KNOWLEDGE_FOLDERS = [
    OBSIDIAN_DIR,
    DOCUMENTS_DIR
]


def ensure_local_knowledge_folders():
    """
    Explicitly create the legacy local knowledge folders.

    Importing knowledge.py and read-only discovery must never create
    directories. Call this helper only from a feature that is about
    to write a file into one of these locations.
    """
    for folder in LOCAL_KNOWLEDGE_FOLDERS:
        os.makedirs(
            folder,
            exist_ok=True
        )


STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were",
    "be", "been", "being", "of", "to", "in", "on",
    "for", "with", "and", "or", "as", "at", "by",
    "from", "this", "that", "these", "those", "what",
    "why", "how", "when", "where", "which", "who",
    "do", "does", "did", "can", "could", "should",
    "would", "i", "me", "my", "we", "our", "you",
    "your"
}


def find_documents(course_id=None):
    documents = []

    for folder in LOCAL_KNOWLEDGE_FOLDERS:
        for root, dirs, files in os.walk(folder):
            for file_name in files:
                extension = os.path.splitext(
                    file_name
                )[1].lower()

                if extension in SUPPORTED_EXTENSIONS:
                    documents.append(
                        os.path.join(
                            root,
                            file_name
                        )
                    )

    # Direct Obsidian vault integration
    documents.extend(
        get_obsidian_markdown_files()
    )

    # Remove duplicates while preserving paths
    unique_documents = list(
        dict.fromkeys(
            os.path.abspath(path)
            for path in documents
        )
    )

    documents = sorted(unique_documents)

    if course_id is None:
        return documents

    course = find_course(course_id)
    if course is None:
        return []

    course_documents = []
    for file_path in documents:
        metadata = get_document_metadata(file_path)
        extension = os.path.splitext(file_path)[1].lower()
        if metadata["course_id"] is None and extension in {".md", ".txt"}:
            metadata = get_document_metadata(
                file_path,
                read_text_file(file_path)[:5000]
            )
        if metadata["course_id"] == course["id"]:
            course_documents.append(file_path)

    return course_documents


def read_text_file(file_path):
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:
            return file.read()

    except UnicodeDecodeError:
        try:
            with open(
                file_path,
                "r",
                encoding="latin-1"
            ) as file:
                return file.read()

        except Exception as error:
            return (
                f"[Could not read text file: "
                f"{error}]"
            )

    except FileNotFoundError:
        return "[File not found.]"

    except OSError as error:
        return (
            f"[Could not read file: {error}]"
        )


def read_pdf_file(file_path):
    try:
        from pypdf import PdfReader

    except ImportError:
        return (
            "[PDF support is not installed. "
            "Run: pip install pypdf]"
        )

    try:
        reader = PdfReader(
            file_path
        )

        pages_text = []

        for page_number, page in enumerate(
            reader.pages,
            start=1
        ):
            text = page.extract_text()

            if text:
                pages_text.append(
                    f"\n--- Page {page_number} ---\n"
                    f"{text.strip()}"
                )

        if not pages_text:
            return (
                "[No readable text found in this PDF. "
                "It may be a scanned/image-only PDF.]"
            )

        return "\n".join(
            pages_text
        )

    except Exception as error:
        return (
            f"[Could not read PDF: {error}]"
        )


def read_document(file_path):
    extension = os.path.splitext(
        file_path
    )[1].lower()

    if extension in [".md", ".txt"]:
        return read_text_file(
            file_path
        )

    if extension == ".pdf":
        return read_pdf_file(
            file_path
        )

    return "[Unsupported file type.]"


def tokenize(text):
    words = re.findall(
        r"[A-Za-z0-9]+",
        text.lower()
    )

    return [
        word
        for word in words
        if (
            word not in STOP_WORDS
            and len(word) > 1
        )
    ]


def split_into_chunks(
    content,
    chunk_size=1000
):
    content = content.strip()

    if not content:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(
            r"\n\s*\n",
            content
        )
        if paragraph.strip()
    ]

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        candidate = (
            paragraph
            if not current_chunk
            else (
                current_chunk
                + "\n\n"
                + paragraph
            )
        )

        if len(candidate) <= chunk_size:
            current_chunk = candidate

        else:
            if current_chunk:
                chunks.append(
                    current_chunk
                )

            if len(paragraph) <= chunk_size:
                current_chunk = paragraph

            else:
                start = 0

                while start < len(paragraph):
                    chunks.append(
                        paragraph[
                            start:
                            start + chunk_size
                        ]
                    )

                    start += chunk_size

                current_chunk = ""

    if current_chunk:
        chunks.append(
            current_chunk
        )

    return chunks


def get_page_number(chunk):
    match = re.search(
        r"--- Page (\d+) ---",
        chunk
    )

    if match:
        return int(
            match.group(1)
        )

    return None


def score_chunk(
    chunk,
    query,
    file_path,
    metadata=None
):
    chunk_lower = chunk.lower()
    query_lower = query.lower().strip()

    query_words = tokenize(
        query
    )

    chunk_words = tokenize(
        chunk
    )

    if not query_words:
        return 0

    score = 0

    if query_lower in chunk_lower:
        score += 12

    word_counts = {}

    for word in query_words:
        count = chunk_words.count(
            word
        )

        word_counts[
            word
        ] = count

        if count > 0:
            score += 3
            score += min(
                count,
                3
            )

    matched_words = [
        word
        for word, count
        in word_counts.items()
        if count > 0
    ]

    coverage = (
        len(matched_words)
        / len(query_words)
    )

    if coverage == 1:
        score += 8

    elif coverage >= 0.75:
        score += 5

    elif coverage >= 0.5:
        score += 2

    file_name = os.path.basename(
        file_path
    ).lower()

    for word in query_words:
        if word in file_name:
            score += 2

    if metadata:
        metadata_text = " ".join([
            metadata.get("course_code") or "",
            metadata.get("course_name") or "",
            metadata.get("topic") or ""
        ]).lower()

        for word in query_words:
            if word in metadata_text:
                score += 2

    if (
        len(matched_words) == 1
        and len(query_words) >= 3
    ):
        score -= 3

    return score


def retrieve_best_chunks(
    query,
    top_k=5,
    course_id=None
):
    documents = find_documents()
    ranked_results = []
    selected_course = find_course(course_id) if course_id else None

    if course_id and selected_course is None:
        return []

    for file_path in documents:
        metadata = get_document_metadata(file_path)

        if (
            selected_course
            and metadata["course_id"] != selected_course["id"]
        ):
            # Avoid loading large PDFs from unrelated courses.
            continue

        content = read_document(
            file_path
        )

        if content.startswith(
            "[Could not"
        ):
            continue

        if content.startswith(
            "[PDF support"
        ):
            continue

        if content.startswith(
            "[No readable text"
        ):
            continue

        metadata = get_document_metadata(file_path, content)

        chunks = split_into_chunks(
            content
        )

        for chunk in chunks:
            score = score_chunk(
                chunk,
                query,
                file_path,
                metadata
            )

            if score > 0:
                result = {
                    "file": file_path,
                    "text": chunk,
                    "score": score,
                    "page": get_page_number(
                        chunk
                    )
                }
                result.update(metadata)
                ranked_results.append(result)

    ranked_results.sort(
        key=lambda item: item[
            "score"
        ],
        reverse=True
    )

    return ranked_results[
        :top_k
    ]


def describe_source(file_path):
    vault_path = get_vault_path()

    try:
        inside_vault = (
            vault_path
            and os.path.commonpath([
                os.path.abspath(file_path),
                os.path.abspath(vault_path)
            ]) == os.path.abspath(vault_path)
        )
    except (ValueError, OSError):
        inside_vault = False

    if inside_vault:
        relative = os.path.relpath(
            file_path,
            vault_path
        )

        return (
            f"Obsidian Vault: {relative}"
        )

    try:
        return os.path.relpath(file_path, BASE_DIR)
    except ValueError:
        return os.path.abspath(file_path)


def show_knowledge_library(course_id=None):
    documents = find_documents(course_id=course_id)
    selected_course = find_course(course_id) if course_id else None

    print(
        "\n========== KNOWLEDGE LIBRARY V8 =========="
    )

    if selected_course:
        print(
            f"Course filter: {selected_course['code']} - "
            f"{selected_course['name']}"
        )

    if not documents:
        print(
            "\nNo supported documents found."
        )
        return

    print(
        f"\nDocuments found: "
        f"{len(documents)}"
    )

    vault_path = get_vault_path()

    if vault_path:
        print(
            f"Obsidian vault connected: "
            f"{vault_path}"
        )

    for number, file_path in enumerate(
        documents,
        start=1
    ):
        extension = os.path.splitext(
            file_path
        )[1].lower()

        metadata = get_document_metadata(file_path)
        course_tag = (
            f" [{metadata['course_code']}]"
            if metadata["course_code"] else " [UNTAGGED]"
        )
        topic_tag = (
            f" | topic: {metadata['topic']}"
            if metadata["topic"] else ""
        )

        print(
            f"{number}. {describe_source(file_path)} "
            f"[{extension[1:].upper()}]{course_tag}{topic_tag}"
        )


def preview_document(course_id=None):
    documents = find_documents(course_id=course_id)

    if not documents:
        print(
            "\nNo supported documents found."
        )
        return

    print(
        "\n========== DOCUMENTS =========="
    )

    for number, file_path in enumerate(
        documents,
        start=1
    ):
        print(
            f"{number}. "
            f"{describe_source(file_path)}"
        )

    try:
        choice = int(
            input(
                "\nEnter document number: "
            ).strip()
        )

        if (
            choice < 1
            or choice > len(documents)
        ):
            print(
                "\nInvalid document number."
            )
            return

    except ValueError:
        print(
            "\nPlease enter a valid number."
        )
        return

    selected_file = documents[
        choice - 1
    ]

    content = read_document(
        selected_file
    )

    print(
        "\n========== PREVIEW =========="
    )

    print(
        content[:1500]
    )

    if len(content) > 1500:
        print(
            "\n[Preview truncated...]"
        )


def knowledge_search_menu(course_id=None):
    print(
        "\n========== KNOWLEDGE RETRIEVAL V8 =========="
    )

    query = input(
        "\nEnter topic or question to search: "
    ).strip()

    if not query:
        print(
            "\nPlease enter a search topic."
        )
        return

    results = retrieve_best_chunks(
        query,
        top_k=5,
        course_id=course_id
    )

    if not results:
        print(
            f'\nNo relevant information found '
            f'for "{query}".'
        )
        return

    print(
        f"\nTop {len(results)} "
        f"most relevant result(s):"
    )

    for number, result in enumerate(
        results,
        start=1
    ):
        print(
            "\n" + "=" * 70
        )

        print(
            f"Result {number}"
        )

        print(
            f"Source : "
            f"{describe_source(result['file'])}"
        )

        if result.get("course_code"):
            print(
                f"Course : {result['course_code']} - "
                f"{result['course_name']}"
            )

        if result.get("topic"):
            print(f"Topic  : {result['topic']}")

        if result[
            "page"
        ] is not None:
            print(
                f"Page   : "
                f"{result['page']}"
            )

        print(
            f"Score  : "
            f"{result['score']}"
        )

        print(
            "=" * 70
        )

        print(
            result["text"]
        )

        print(
            "-" * 70
        )


if __name__ == "__main__":
    show_knowledge_library()
