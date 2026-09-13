"""V10.2 Assignment File Importer.

Imports assignment/question-sheet files into the V10.1 question workspace.
Supported:
- PDF (text-based PDFs through pypdf)
- TXT
- Markdown

For PDFs, extracted questions retain page numbers so the workspace can show
where each question came from. Scanned/image-only PDFs are reported clearly;
this module does not silently OCR or invent text.
"""

import os
import re

from assignment_exam_assistant import choose_assessment
from assessment_question_workspace import (
    get_workspace,
    add_question_to_workspace,
    print_workspace_summary,
    list_questions,
)
from knowledge_paths import BASE_DIR
from math_document_reader import read_pdf_pages_math_aware


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
}

QUESTION_PATTERNS = [
    re.compile(
        r"(?im)^(?:q(?:uestion)?\s*)?(\d+)\s*[\.\)\-:]\s+"
    ),
    re.compile(
        r"(?im)^\s*\((\d+)\)\s+"
    ),
]


def normalize_path(path):
    path = str(path or "").strip().strip('"').strip("'")
    return os.path.abspath(
        os.path.expanduser(path)
    )


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

        except OSError as error:
            raise RuntimeError(
                f"Could not read text file: {error}"
            )

    except OSError as error:
        raise RuntimeError(
            f"Could not read text file: {error}"
        )


def read_pdf_pages(file_path):
    try:
        pages = read_pdf_pages_math_aware(
            file_path
        )

    except RuntimeError as error:
        raise RuntimeError(
            str(error)
        )

    return [
        {
            "page": item["page"],
            "text": item["text"]
        }
        for item in pages
    ]


def _split_numbered_questions(text):
    matches = []

    for pattern in QUESTION_PATTERNS:
        candidate = list(
            pattern.finditer(text)
        )

        if len(candidate) > len(matches):
            matches = candidate

    if not matches:
        return []

    questions = []

    for index, match in enumerate(
        matches
    ):
        start = match.end()

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        question_text = text[
            start:end
        ].strip()

        if question_text:
            questions.append({
                "number": match.group(1),
                "text": question_text
            })

    return questions


def extract_questions_from_plain_text(text):
    text = str(text or "").strip()

    if not text:
        return []

    numbered = _split_numbered_questions(
        text
    )

    if numbered:
        return [
            {
                "text": item["text"],
                "source_page": None,
                "source_question_number": item[
                    "number"
                ],
            }
            for item in numbered
        ]

    # Fallback: paragraph-based extraction.
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(
            r"\n\s*\n",
            text
        )
        if paragraph.strip()
    ]

    return [
        {
            "text": paragraph,
            "source_page": None,
            "source_question_number": None,
        }
        for paragraph in paragraphs
    ]


def extract_questions_from_pdf(file_path):
    pages = read_pdf_pages(
        file_path
    )

    extracted = []

    for page_data in pages:
        page_questions = (
            _split_numbered_questions(
                page_data["text"]
            )
        )

        if page_questions:
            for item in page_questions:
                extracted.append({
                    "text": item["text"],
                    "source_page": page_data[
                        "page"
                    ],
                    "source_question_number": item[
                        "number"
                    ],
                })

    # If page-by-page numbering failed, try the whole document
    # while preserving page markers.
    if not extracted:
        combined_parts = []

        for page_data in pages:
            combined_parts.append(
                f"\n--- SOURCE PAGE "
                f"{page_data['page']} ---\n"
                f"{page_data['text']}"
            )

        combined = "\n".join(
            combined_parts
        )

        numbered = (
            _split_numbered_questions(
                combined
            )
        )

        for item in numbered:
            source_page = None

            page_matches = list(
                re.finditer(
                    r"--- SOURCE PAGE (\d+) ---",
                    combined[
                        :combined.find(
                            item["text"]
                        )
                    ]
                )
            )

            if page_matches:
                source_page = int(
                    page_matches[-1].group(1)
                )

            cleaned = re.sub(
                r"--- SOURCE PAGE \d+ ---",
                "",
                item["text"]
            ).strip()

            if cleaned:
                extracted.append({
                    "text": cleaned,
                    "source_page": source_page,
                    "source_question_number": item[
                        "number"
                    ],
                })

    return extracted


def extract_questions_from_file(
    file_path
):
    extension = os.path.splitext(
        file_path
    )[1].lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise RuntimeError(
            "Unsupported file type. "
            "Use PDF, TXT or Markdown."
        )

    if extension == ".pdf":
        return extract_questions_from_pdf(
            file_path
        )

    text = read_text_file(
        file_path
    )

    return extract_questions_from_plain_text(
        text
    )


def _enrich_last_question(
    workspace,
    source_file,
    source_page,
    source_question_number
):
    if not workspace.get("questions"):
        return

    question = workspace[
        "questions"
    ][-1]

    question["source_file"] = (
        source_file
    )

    question["source_page"] = (
        source_page
    )

    question[
        "source_question_number"
    ] = source_question_number


def import_questions_to_workspace(
    assessment,
    workspace,
    file_path
):
    extracted = (
        extract_questions_from_file(
            file_path
        )
    )

    if not extracted:
        print(
            "\nNo questions could be detected."
        )
        print(
            "Try adding questions manually in "
            "V10.1 Question Workspace."
        )
        return 0

    added = 0
    source_name = os.path.basename(
        file_path
    )

    for item in extracted:
        success = add_question_to_workspace(
            workspace,
            item["text"]
        )

        if not success:
            continue

        _enrich_last_question(
            workspace,
            source_name,
            item.get(
                "source_page"
            ),
            item.get(
                "source_question_number"
            )
        )

        # Save after metadata enrichment.
        from assessment_question_workspace import (
            save_workspace
        )

        save_workspace(
            workspace
        )

        added += 1

    return added


def print_import_preview(
    extracted,
    file_path
):
    print(
        "\n========== IMPORT PREVIEW =========="
    )

    print(
        f"File: {os.path.basename(file_path)}"
    )

    print(
        f"Detected questions: "
        f"{len(extracted)}"
    )

    for index, item in enumerate(
        extracted[:10],
        start=1
    ):
        page = item.get(
            "source_page"
        )

        q_number = item.get(
            "source_question_number"
        )

        source_parts = []

        if q_number:
            source_parts.append(
                f"Q{q_number}"
            )

        if page:
            source_parts.append(
                f"page {page}"
            )

        source_text = (
            " | ".join(source_parts)
            if source_parts
            else "source location unavailable"
        )

        preview = item[
            "text"
        ].replace(
            "\n",
            " "
        )

        if len(preview) > 140:
            preview = (
                preview[:137]
                + "..."
            )

        print(
            f"\n{index}. "
            f"[{source_text}]"
        )

        print(
            preview
        )

    if len(extracted) > 10:
        print(
            f"\n...and "
            f"{len(extracted) - 10} more."
        )


def import_assignment_file():
    assessment = choose_assessment(
        include_completed=True
    )

    if not assessment:
        return

    workspace = get_workspace(
        assessment["id"],
        create=True
    )

    print(
        "\n========== V10.2 ASSIGNMENT FILE IMPORTER =========="
    )

    print(
        "Supported: PDF, TXT, Markdown"
    )

    path = input(
        "\nPaste the full file path: "
    ).strip()

    file_path = normalize_path(
        path
    )

    if not os.path.isfile(
        file_path
    ):
        print(
            "\nThat file does not exist."
        )
        return

    try:
        extracted = (
            extract_questions_from_file(
                file_path
            )
        )

    except RuntimeError as error:
        print(
            f"\n{error}"
        )
        return

    if not extracted:
        print(
            "\nNo questions were detected."
        )
        return

    print_import_preview(
        extracted,
        file_path
    )

    confirm = input(
        "\nImport these questions into "
        "the assessment workspace? "
        "Type yes to continue: "
    ).strip().lower()

    if confirm != "yes":
        print(
            "\nImport cancelled."
        )
        return

    added = import_questions_to_workspace(
        assessment,
        workspace,
        file_path
    )

    print(
        f"\nImported {added} question(s)."
    )

    print_workspace_summary(
        assessment,
        workspace
    )


def show_question_sources():
    assessment = choose_assessment(
        include_completed=True
    )

    if not assessment:
        return

    workspace = get_workspace(
        assessment["id"],
        create=True
    )

    questions = workspace.get(
        "questions",
        []
    )

    if not questions:
        print(
            "\nNo questions in this workspace."
        )
        return

    print(
        "\n========== QUESTION SOURCE MAP =========="
    )

    for index, question in enumerate(
        questions,
        start=1
    ):
        source_file = question.get(
            "source_file"
        )

        source_page = question.get(
            "source_page"
        )

        source_number = question.get(
            "source_question_number"
        )

        if not source_file:
            source_text = (
                "manually entered / "
                "source not recorded"
            )
        else:
            parts = [
                source_file
            ]

            if source_number:
                parts.append(
                    f"Q{source_number}"
                )

            if source_page:
                parts.append(
                    f"page {source_page}"
                )

            source_text = (
                " | ".join(parts)
            )

        preview = question[
            "text"
        ].replace(
            "\n",
            " "
        )

        if len(preview) > 90:
            preview = (
                preview[:87]
                + "..."
            )

        print(
            f"{index}. {preview}"
        )

        print(
            f"   Source: {source_text}"
        )


def assignment_file_importer_menu():
    while True:
        print(
            "\n========== V10.2 ASSIGNMENT FILE IMPORTER =========="
        )

        print(
            "1. Import Question Sheet File"
        )

        print(
            "2. View Question Source Map"
        )

        print(
            "3. Open Question Workspace Summary"
        )

        print(
            "4. Back"
        )

        choice = input(
            "\nEnter your choice (1-4): "
        ).strip()

        if choice == "1":
            import_assignment_file()

        elif choice == "2":
            show_question_sources()

        elif choice == "3":
            assessment = choose_assessment(
                include_completed=True
            )

            if assessment:
                workspace = get_workspace(
                    assessment["id"],
                    create=True
                )

                print_workspace_summary(
                    assessment,
                    workspace
                )

                list_questions(
                    workspace
                )

        elif choice == "4":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 4."
            )


if __name__ == "__main__":
    assignment_file_importer_menu()
