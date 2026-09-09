import os

# --------------------------------------------------
# Project paths
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
OBSIDIAN_DIR = os.path.join(KNOWLEDGE_DIR, "obsidian")
DOCUMENTS_DIR = os.path.join(KNOWLEDGE_DIR, "documents")

SUPPORTED_EXTENSIONS = [".md", ".txt"]

KNOWLEDGE_FOLDERS = [
    OBSIDIAN_DIR,
    DOCUMENTS_DIR
]

# Create folders automatically if they do not exist
for folder in KNOWLEDGE_FOLDERS:
    os.makedirs(folder, exist_ok=True)


# --------------------------------------------------
# Find documents
# --------------------------------------------------

def find_documents():
    documents = []

    for folder in KNOWLEDGE_FOLDERS:
        for root, dirs, files in os.walk(folder):
            for file in files:
                extension = os.path.splitext(file)[1].lower()

                if extension in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    documents.append(full_path)

    return documents


# --------------------------------------------------
# Read a document
# --------------------------------------------------

def read_document(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()

    except UnicodeDecodeError:
        return "[Could not read this file because of encoding.]"

    except FileNotFoundError:
        return "[File not found.]"

    except OSError as error:
        return f"[Could not read file: {error}]"


# --------------------------------------------------
# Find matching paragraphs
# --------------------------------------------------

def find_relevant_paragraphs(content, query):
    paragraphs = content.split("\n\n")
    matches = []

    query = query.lower().strip()

    for paragraph in paragraphs:
        if query in paragraph.lower():
            matches.append(paragraph.strip())

    return matches


# --------------------------------------------------
# Search knowledge library
# --------------------------------------------------

def search_knowledge(query):
    documents = find_documents()
    results = []

    query = query.strip()

    if not query:
        return results

    for file_path in documents:
        content = read_document(file_path)

        matches = find_relevant_paragraphs(content, query)

        if matches:
            results.append({
                "file": file_path,
                "matches": matches
            })

    return results


# --------------------------------------------------
# Show all documents
# --------------------------------------------------

def show_knowledge_library():
    documents = find_documents()

    print("\n========== KNOWLEDGE LIBRARY ==========")

    if not documents:
        print("\nNo supported documents found.")
        print("\nAdd .md or .txt files inside:")
        print(f"  {OBSIDIAN_DIR}")
        print(f"  {DOCUMENTS_DIR}")
        return

    print(f"\nDocuments found: {len(documents)}")

    for number, file_path in enumerate(documents, start=1):
        relative_path = os.path.relpath(file_path, BASE_DIR)

        print(f"\n{number}. {relative_path}")

        content = read_document(file_path)
        preview = content[:300]

        print("\nPreview:")
        print(preview)
        print("-" * 50)


# --------------------------------------------------
# Search menu
# --------------------------------------------------

def knowledge_search_menu():
    print("\n========== SEARCH KNOWLEDGE ==========")

    query = input("\nEnter topic to search: ").strip()

    if not query:
        print("\nPlease enter a search topic.")
        return

    results = search_knowledge(query)

    if not results:
        print(f'\nNo matching information found for "{query}".')
        return

    print(f"\nFound information in {len(results)} document(s).")

    for result in results:
        relative_path = os.path.relpath(result["file"], BASE_DIR)

        print("\n" + "=" * 60)
        print(f"Source: {relative_path}")
        print("=" * 60)

        for match_number, match in enumerate(result["matches"], start=1):
            print(f"\nMatch {match_number}:")
            print(match)


# --------------------------------------------------
# Main menu
# --------------------------------------------------

def main():
    while True:
        print("\n========== KNOWLEDGE LIBRARY ==========")
        print("1. View Knowledge Library")
        print("2. Search Knowledge")
        print("3. Exit")

        choice = input("\nEnter your choice: ").strip()

        if choice == "1":
            show_knowledge_library()

        elif choice == "2":
            knowledge_search_menu()

        elif choice == "3":
            print("\nExiting Knowledge Library.")
            break

        else:
            print("\nInvalid choice. Please enter 1, 2, or 3.")


if __name__ == "__main__":
    main()
