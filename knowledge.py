import os

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


def split_into_chunks(content, chunk_size=1200):
    content = content.strip()

    if not content:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in content.split("\n\n")
        if paragraph.strip()
    ]

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 2 <= chunk_size:
            if current_chunk:
                current_chunk += "\n\n"
            current_chunk += paragraph
        else:
            if current_chunk:
                chunks.append(current_chunk)

            if len(paragraph) > chunk_size:
                start = 0
                while start < len(paragraph):
                    chunks.append(paragraph[start:start + chunk_size])
                    start += chunk_size
                current_chunk = ""
            else:
                current_chunk = paragraph

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def find_relevant_chunks(content, query):
    query = query.lower().strip()

    if not query:
        return []

    chunks = split_into_chunks(content)
    matches = []

    query_words = [
        word for word in query.split()
        if len(word) > 2
    ]

    for chunk in chunks:
        chunk_lower = chunk.lower()

        exact_match = query in chunk_lower
        word_matches = sum(
            1 for word in query_words
            if word in chunk_lower
        )

        if exact_match or word_matches > 0:
            score = word_matches

            if exact_match:
                score += 5

            matches.append({
                "text": chunk,
                "score": score
            })

    matches.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return matches[:5]


def search_knowledge(query):
    documents = find_documents()
    results = []

    query = query.strip()

    if not query:
        return results

    for file_path in documents:
        content = read_document(file_path)

        if content.startswith("[Could not"):
            continue

        if content.startswith("[PDF support"):
            continue

        matches = find_relevant_chunks(content, query)

        if matches:
            results.append({
                "file": file_path,
                "matches": matches
            })

    return results


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
        choice = int(input("\nEnter document number: ").strip())

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
    print("\n========== SEARCH KNOWLEDGE ==========")

    query = input(
        "\nEnter topic or question to search: "
    ).strip()

    if not query:
        print("\nPlease enter a search topic.")
        return

    results = search_knowledge(query)

    if not results:
        print(
            f'\nNo matching information found for "{query}".'
        )
        return

    print(
        f"\nFound information in "
        f"{len(results)} document(s)."
    )

    for result in results:
        relative_path = os.path.relpath(
            result["file"],
            BASE_DIR
        )

        print("\n" + "=" * 70)
        print(f"Source: {relative_path}")
        print("=" * 70)

        for number, match in enumerate(
            result["matches"],
            start=1
        ):
            print(f"\nMatch {number}:")
            print(match["text"])
            print("-" * 50)


def main():
    while True:
        print("\n========== KNOWLEDGE LIBRARY ==========")
        print("1. View Knowledge Library")
        print("2. Search Knowledge")
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
