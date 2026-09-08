import os

SUPPORTED_EXTENSIONS = [".md", ".txt"]

KNOWLEDGE_FOLDERS = [
    "knowledge/obsidian",
    "knowledge/documents"
]


def find_documents():
    documents = []

    for folder in KNOWLEDGE_FOLDERS:
        if not os.path.exists(folder):
            continue

        for root, dirs, files in os.walk(folder):
            for file in files:
                extension = os.path.splitext(file)[1].lower()

                if extension in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    documents.append(full_path)

    return documents


def read_document(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()

    except UnicodeDecodeError:
        return "[Could not read this file because of encoding.]"

    except FileNotFoundError:
        return "[File not found.]"


def show_knowledge_library():
    documents = find_documents()

    print("\n========== KNOWLEDGE LIBRARY ==========")

    if not documents:
        print("\nNo supported documents found.")
        return

    print(f"\nDocuments found: {len(documents)}")

    for number, file_path in enumerate(documents, start=1):
        print(f"\n{number}. {file_path}")

        content = read_document(file_path)

        preview = content[:300]

        print("\nPreview:")
        print(preview)
        print("-" * 50)


if __name__ == "__main__":
    show_knowledge_library()