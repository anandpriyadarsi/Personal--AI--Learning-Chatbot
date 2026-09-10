import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
OBSIDIAN_DIR = os.path.join(KNOWLEDGE_DIR, "obsidian")
DOCUMENTS_DIR = os.path.join(KNOWLEDGE_DIR, "documents")

SUPPORTED_EXTENSIONS = [".md", ".txt", ".pdf"]

KNOWLEDGE_FOLDERS = [
    OBSIDIAN_DIR,
    DOCUMENTS_DIR
]

for folder in KNOWLEDGE_FOLDERS:
    os.makedirs(folder, exist_ok=True)

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "being", "of", "to", "in", "on", "for", "with", "and", "or",
    "as", "at", "by", "from", "this", "that", "these", "those",
    "what", "why", "how", "when", "where", "which", "who",
    "do", "does", "did", "can", "could", "should", "would",
    "i", "me", "my", "we", "our", "you", "your"
}

def find_documents():
    documents = []

    for folder in KNOWLEDGE_FOLDERS:
        for root, dirs, files in os.walk(folder):
            for file in files:
                extension = os.path.splitext(file)[1].lower()

                if extension in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    documents.append(full_path)

    return sorted(documents)

def read_text_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()

    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1") as file:
                return file.read()
        except Exception as error:
            return f"[Could not read text file: {error}]"

    except FileNotFoundError:
        return "[File not found.]"

    except OSError as error:
        return f"[Could not read file: {error}]"

def read_pdf_file(file_path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return "[PDF support is not installed. Run: pip install pypdf]"

    try:
        reader = PdfReader(file_path)
        pages_text = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text()

            if text:
                pages_text.append(
                    f"\n--- Page {page_number} ---\n{text.strip()}"
                )

        if not pages_text:
            return (
                "[No readable text found in this PDF. "
                "It may be a scanned/image-only PDF.]"
            )

        return "\n".join(pages_text)

    except Exception as error:
        return f"[Could not read PDF: {error}]"

def read_document(file_path):
    extension = os.path.splitext(file_path)[1].lower()

    if extension in [".md", ".txt"]:
        return read_text_file(file_path)

    if extension == ".pdf":
        return read_pdf_file(file_path)

    return "[Unsupported file type.]"

def tokenize(text):
    words = re.findall(r"[A-Za-z0-9]+", text.lower())

    return [
        word
        for word in words
        if word not in STOP_WORDS and len(word) > 1
    ]

def split_into_chunks(content, chunk_size=1000):
    content = content.strip()

    if not content:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", content)
        if paragraph.strip()
    ]

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        candidate = (
            paragraph
            if not current_chunk
            else current_chunk + "\n\n" + paragraph
        )

        if len(candidate) <= chunk_size:
            current_chunk = candidate

        else:
            if current_chunk:
                chunks.append(current_chunk)

            if len(paragraph) <= chunk_size:
                current_chunk = paragraph
            else:
                start = 0
                while start < len(paragraph):
                    chunks.append(
                        paragraph[start:start + chunk_size]
                    )
                    start += chunk_size
                current_chunk = ""

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def get_page_number(chunk):
    match = re.search(r"--- Page (\d+) ---", chunk)

    if match:
        return int(match.group(1))

    return None

def score_chunk(chunk, query, file_path):
    chunk_lower = chunk.lower()
    query_lower = query.lower().strip()

    query_words = tokenize(query)
    chunk_words = tokenize(chunk)

    if not query_words:
        return 0

    score = 0

    if query_lower in chunk_lower:
        score += 12

    word_counts = {}

    for word in query_words:
        count = chunk_words.count(word)
        word_counts[word] = count

        if count > 0:
            score += 3
            score += min(count, 3)

    matched_words = [
        word for word, count in word_counts.items()
        if count > 0
    ]

    coverage = len(matched_words) / len(query_words)

    if coverage == 1:
        score += 8
    elif coverage >= 0.75:
        score += 5
    elif coverage >= 0.5:
        score += 2

    file_name = os.path.basename(file_path).lower()

    for word in query_words:
        if word in file_name:
            score += 2

    if len(matched_words) == 1 and len(query_words) >= 3:
        score -= 3

    return score

def retrieve_best_chunks(query, top_k=5):
    documents = find_documents()
    ranked_results = []

    for file_path in documents:
        content = read_document(file_path)

        if content.startswith("[Could not"):
            continue

        if content.startswith("[PDF support"):
            continue

        if content.startswith("[No readable text"):
            continue

        chunks = split_into_chunks(content)

        for chunk in chunks:
            score = score_chunk(
                chunk,
                query,
                file_path
            )

            if score > 0:
                ranked_results.append({
                    "file": file_path,
                    "text": chunk,
                    "score": score,
                    "page": get_page_number(chunk)
                })

    ranked_results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return ranked_results[:top_k]

def show_knowledge_library():
    documents = find_documents()

    print("\n========== KNOWLEDGE LIBRARY ==========")

    if not documents:
        print("\nNo supported documents found.")
        print("\nAdd .md, .txt or .pdf files inside:")
        print(f"  {OBSIDIAN_DIR}")
        print(f"  {DOCUMENTS_DIR}")
        return

    print(f"\nDocuments found: {len(documents)}")

    for number, file_path in enumerate(documents, start=1):
        relative_path = os.path.relpath(file_path, BASE_DIR)
        extension = os.path.splitext(file_path)[1].lower()

        print(
            f"{number}. {relative_path} "
            f"[{extension[1:].upper()}]"
        )

def preview_document():
    documents = find_documents()

    if not documents:
        print("\nNo supported documents found.")
        return

    print("\n========== DOCUMENTS ==========")

    for number, file_path in enumerate(documents, start=1):
        relative_path = os.path.relpath(file_path, BASE_DIR)
        print(f"{number}. {relative_path}")

    try:
        choice = int(
            input("\nEnter document number: ").strip()
        )

        if choice < 1 or choice > len(documents):
            print("\nInvalid document number.")
            return

    except ValueError:
        print("\nPlease enter a valid number.")
        return

    selected_file = documents[choice - 1]
    content = read_document(selected_file)

    print("\n========== PREVIEW ==========")
    print(content[:1500])

    if len(content) > 1500:
        print("\n[Preview truncated...]")

def knowledge_search_menu():
    print("\n========== KNOWLEDGE RETRIEVAL V2 ==========")

    query = input(
        "\nEnter topic or question to search: "
    ).strip()

    if not query:
        print("\nPlease enter a search topic.")
        return

    results = retrieve_best_chunks(
        query,
        top_k=5
    )

    if not results:
        print(
            f'\nNo relevant information found for "{query}".'
        )
        return

    print(
        f"\nTop {len(results)} most relevant result(s):"
    )

    for number, result in enumerate(results, start=1):
        relative_path = os.path.relpath(
            result["file"],
            BASE_DIR
        )

        print("\n" + "=" * 70)
        print(f"Result {number}")
        print(f"Source : {relative_path}")

        if result["page"] is not None:
            print(f"Page   : {result['page']}")

        print(f"Score  : {result['score']}")
        print("=" * 70)

        print(result["text"])
        print("-" * 70)

def main():
    while True:
        print("\n========== KNOWLEDGE LIBRARY ==========")
        print("1. View Knowledge Library")
        print("2. Search Knowledge (Retrieval V2)")
        print("3. Preview Document")
        print("4. Exit")

        choice = input(
            "\nEnter your choice: "
        ).strip()

        if choice == "1":
            show_knowledge_library()

        elif choice == "2":
            knowledge_search_menu()

        elif choice == "3":
            preview_document()

        elif choice == "4":
            print("\nExiting Knowledge Library.")
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1, 2, 3, or 4."
            )

if __name__ == "__main__":
    main()
