import ast
from pathlib import Path

import knowledge

from personal_learning_assistant.domain.knowledge_models import (
    KnowledgeDocument,
    KnowledgeDocumentListResult,
)


def _function_node(name):
    path = Path(
        knowledge.__file__
    )
    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        )
    )

    return next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name == name
        )
    )


def test_find_documents_no_longer_walks_filesystem_directly():
    node = _function_node(
        "find_documents"
    )

    for child in ast.walk(
        node
    ):
        if (
            isinstance(
                child,
                ast.Call,
            )
            and isinstance(
                child.func,
                ast.Attribute,
            )
            and isinstance(
                child.func.value,
                ast.Name,
            )
            and child.func.value.id == "os"
        ):
            assert (
                child.func.attr
                != "walk"
            )

        if (
            isinstance(
                child,
                ast.Call,
            )
            and isinstance(
                child.func,
                ast.Name,
            )
        ):
            assert (
                child.func.id
                != "get_obsidian_markdown_files"
            )


def test_unfiltered_find_documents_delegates_to_knowledge_service(
    monkeypatch,
):
    class FakeService:
        def list_documents(self):
            return (
                KnowledgeDocumentListResult(
                    documents=(
                        KnowledgeDocument(
                            path="C:/a.md",
                            display_name="a.md",
                            scope="project",
                        ),
                        KnowledgeDocument(
                            path="C:/b.pdf",
                            display_name="b.pdf",
                            scope="project",
                        ),
                    )
                )
            )

    monkeypatch.setattr(
        knowledge,
        "_build_knowledge_service",
        lambda: FakeService(),
    )

    assert knowledge.find_documents() == [
        "C:/a.md",
        "C:/b.pdf",
    ]


def test_describe_source_delegates_to_knowledge_service(
    monkeypatch,
):
    class FakeService:
        def describe_document(
            self,
            file_path,
        ):
            return KnowledgeDocument(
                path=str(file_path),
                display_name=(
                    "Obsidian Vault: "
                    "Math/LU.md"
                ),
                scope="obsidian_vault",
            )

    monkeypatch.setattr(
        knowledge,
        "_build_knowledge_service",
        lambda: FakeService(),
    )

    assert (
        knowledge.describe_source(
            "C:/vault/Math/LU.md"
        )
        == "Obsidian Vault: Math/LU.md"
    )


def test_course_filter_preserves_unknown_course_behavior(
    monkeypatch,
):
    class FakeService:
        def list_documents(self):
            return (
                KnowledgeDocumentListResult(
                    documents=(
                        KnowledgeDocument(
                            path="C:/a.md",
                            display_name="a.md",
                            scope="project",
                        ),
                    )
                )
            )

    monkeypatch.setattr(
        knowledge,
        "_build_knowledge_service",
        lambda: FakeService(),
    )
    monkeypatch.setattr(
        knowledge,
        "find_course",
        lambda course_id: None,
    )

    assert (
        knowledge.find_documents(
            "unknown"
        )
        == []
    )


def test_course_filter_preserves_metadata_matching(
    monkeypatch,
):
    class FakeService:
        def list_documents(self):
            return (
                KnowledgeDocumentListResult(
                    documents=(
                        KnowledgeDocument(
                            path="C:/ma103n.pdf",
                            display_name="ma103n.pdf",
                            scope="project",
                        ),
                        KnowledgeDocument(
                            path="C:/other.pdf",
                            display_name="other.pdf",
                            scope="project",
                        ),
                    )
                )
            )

    monkeypatch.setattr(
        knowledge,
        "_build_knowledge_service",
        lambda: FakeService(),
    )
    monkeypatch.setattr(
        knowledge,
        "find_course",
        lambda course_id: {
            "id": "ma103n",
        },
    )

    def metadata(
        file_path,
        content=None,
    ):
        return {
            "course_id": (
                "ma103n"
                if "ma103n"
                in file_path.lower()
                else "cy101"
            )
        }

    monkeypatch.setattr(
        knowledge,
        "get_document_metadata",
        metadata,
    )

    assert (
        knowledge.find_documents(
            "MA103N"
        )
        == [
            "C:/ma103n.pdf"
        ]
    )


def test_text_course_filter_still_retries_with_header_content(
    monkeypatch,
):
    class FakeService:
        def list_documents(self):
            return (
                KnowledgeDocumentListResult(
                    documents=(
                        KnowledgeDocument(
                            path="C:/linear.md",
                            display_name="linear.md",
                            scope="project",
                        ),
                    )
                )
            )

    monkeypatch.setattr(
        knowledge,
        "_build_knowledge_service",
        lambda: FakeService(),
    )
    monkeypatch.setattr(
        knowledge,
        "find_course",
        lambda course_id: {
            "id": "ma103n",
        },
    )
    monkeypatch.setattr(
        knowledge,
        "read_text_file",
        lambda file_path: (
            "course: MA103N\n"
            "topic: LU Factorization"
        ),
    )

    calls = []

    def metadata(
        file_path,
        content=None,
    ):
        calls.append(
            content
        )

        if content is None:
            return {
                "course_id": None,
            }

        return {
            "course_id": "ma103n",
        }

    monkeypatch.setattr(
        knowledge,
        "get_document_metadata",
        metadata,
    )

    assert (
        knowledge.find_documents(
            "ma103n"
        )
        == [
            "C:/linear.md"
        ]
    )

    assert calls == [
        None,
        (
            "course: MA103N\n"
            "topic: LU Factorization"
        ),
    ]


def test_find_documents_builder_is_present():
    node = _function_node(
        "_build_knowledge_service"
    )

    imported_modules = {
        child.module
        for child in ast.walk(
            node
        )
        if (
            isinstance(
                child,
                ast.ImportFrom,
            )
            and child.module
        )
    }

    assert (
        "personal_learning_assistant."
        "services.knowledge_service"
        in imported_modules
    )

    assert (
        "personal_learning_assistant."
        "repositories.filesystem."
        "knowledge_repository"
        in imported_modules
    )


def test_legacy_public_function_names_are_preserved():
    assert callable(
        knowledge.find_documents
    )
    assert callable(
        knowledge.describe_source
    )
