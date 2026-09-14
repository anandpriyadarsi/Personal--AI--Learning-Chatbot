import ast
import json
import os
from pathlib import Path

import knowledge

from personal_learning_assistant.repositories.interfaces import (
    CourseKnowledgeContext,
)
from personal_learning_assistant.repositories.json.knowledge_course_context import (
    LegacyJsonCourseKnowledgeContext,
)


def _write_state(
    path,
    payload,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )


def _context(
    tmp_path,
    payload=None,
    vault_path=None,
):
    courses_file = (
        tmp_path
        / "data"
        / "courses.json"
    )

    if payload is not None:
        _write_state(
            courses_file,
            payload,
        )

    return LegacyJsonCourseKnowledgeContext(
        courses_file=courses_file,
        base_dir=tmp_path,
        vault_path_provider=(
            lambda: (
                str(vault_path)
                if vault_path
                else None
            )
        ),
    )


def _state():
    return {
        "version": 1,
        "active_course_id": "ma103n",
        "courses": [
            {
                "id": "ma103n",
                "code": "MA103N",
                "name": "Linear Algebra",
                "semester": "1",
                "status": "active",
                "topics": [],
            },
            {
                "id": "cy100n",
                "code": "CY100N",
                "name": "Engineering Chemistry",
                "semester": "1",
                "status": "active",
                "topics": [],
            },
        ],
        "document_links": {},
    }


def _imports_course_manager(
    module,
):
    tree = ast.parse(
        Path(
            module.__file__
        ).read_text(
            encoding="utf-8"
        )
    )

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
            == "course_manager"
        ):
            return True

        if isinstance(
            node,
            ast.Import,
        ):
            if any(
                alias.name
                == "course_manager"
                for alias in node.names
            ):
                return True

    return False


def test_knowledge_no_longer_imports_course_manager():
    assert not _imports_course_manager(
        knowledge
    )


def test_context_adapter_no_course_manager_import():
    from personal_learning_assistant.repositories.json import (
        knowledge_course_context,
    )

    assert not _imports_course_manager(
        knowledge_course_context
    )


def test_course_knowledge_protocol_declares_read_surface():
    methods = {
        name
        for name, value
        in vars(
            CourseKnowledgeContext
        ).items()
        if callable(value)
        and not name.startswith("_")
    }

    assert {
        "find_course",
        "get_document_metadata",
    }.issubset(
        methods
    )


def test_missing_courses_file_is_read_only(
    tmp_path,
):
    context = _context(
        tmp_path,
    )

    courses_file = (
        tmp_path
        / "data"
        / "courses.json"
    )

    assert not courses_file.exists()

    assert (
        context.find_course(
            "MA103N"
        )
        is None
    )

    metadata = (
        context
        .get_document_metadata(
            tmp_path
            / "unknown.pdf"
        )
    )

    assert (
        metadata["course_id"]
        is None
    )
    assert not courses_file.exists()
    assert not (
        tmp_path
        / "data"
    ).exists()


def test_invalid_courses_json_is_tolerant_and_read_only(
    tmp_path,
):
    courses_file = (
        tmp_path
        / "data"
        / "courses.json"
    )
    courses_file.parent.mkdir(
        parents=True
    )
    courses_file.write_text(
        "{broken",
        encoding="utf-8",
    )

    before = courses_file.read_bytes()

    context = LegacyJsonCourseKnowledgeContext(
        courses_file=courses_file,
        base_dir=tmp_path,
    )

    assert (
        context.find_course(
            "MA103N"
        )
        is None
    )

    assert (
        courses_file.read_bytes()
        == before
    )


def test_find_course_matches_id_code_and_name(
    tmp_path,
):
    context = _context(
        tmp_path,
        _state(),
    )

    assert (
        context.find_course(
            "ma103n"
        )["id"]
        == "ma103n"
    )
    assert (
        context.find_course(
            "MA103N"
        )["name"]
        == "Linear Algebra"
    )
    assert (
        context.find_course(
            "linear algebra"
        )["code"]
        == "MA103N"
    )


def test_explicit_document_link_wins(
    tmp_path,
):
    payload = _state()

    target = (
        tmp_path
        / "knowledge"
        / "documents"
        / "generic.pdf"
    )

    context = _context(
        tmp_path,
        payload,
    )

    key = (
        context
        .canonical_document_key(
            target
        )
    )

    payload["document_links"][
        key
    ] = {
        "course_id": "ma103n",
        "topic": "LU Factorization",
        "source_type": "course_pdf",
        "display_path": str(
            target
        ),
        "linked_at": (
            "2026-09-14T06:00:00"
        ),
    }

    _write_state(
        tmp_path
        / "data"
        / "courses.json",
        payload,
    )

    metadata = (
        context
        .get_document_metadata(
            target
        )
    )

    assert (
        metadata["course_id"]
        == "ma103n"
    )
    assert (
        metadata["topic"]
        == "LU Factorization"
    )
    assert (
        metadata["source_type"]
        == "course_pdf"
    )


def test_frontmatter_course_and_topic_are_preserved(
    tmp_path,
):
    context = _context(
        tmp_path,
        _state(),
    )

    note = (
        tmp_path
        / "knowledge"
        / "documents"
        / "lesson.md"
    )
    note.parent.mkdir(
        parents=True
    )
    note.write_text(
        (
            "course: MA103N\n"
            "topic: Vector Spaces\n"
            "\n# Lesson\n"
        ),
        encoding="utf-8",
    )

    metadata = (
        context
        .get_document_metadata(
            note
        )
    )

    assert (
        metadata["course_id"]
        == "ma103n"
    )
    assert (
        metadata["topic"]
        == "Vector Spaces"
    )
    assert (
        metadata["source_type"]
        == "obsidian_note"
    )


def test_path_course_inference_is_preserved(
    tmp_path,
):
    context = _context(
        tmp_path,
        _state(),
    )

    target = (
        tmp_path
        / "knowledge"
        / "documents"
        / "MA103N"
        / "week2.pdf"
    )

    metadata = (
        context
        .get_document_metadata(
            target
        )
    )

    assert (
        metadata["course_id"]
        == "ma103n"
    )


def test_obsidian_canonical_key_uses_vault_relative_path(
    tmp_path,
):
    vault = (
        tmp_path
        / "vault"
    )
    note = (
        vault
        / "Linear Algebra"
        / "LU.md"
    )

    context = _context(
        tmp_path,
        _state(),
        vault_path=vault,
    )

    assert (
        context
        .canonical_document_key(
            note
        )
        == (
            "obsidian:"
            "Linear Algebra/LU.md"
        )
    )


def test_knowledge_find_course_wrapper_delegates(
    monkeypatch,
):
    calls = []

    class FakeContext:
        def find_course(
            self,
            identifier,
        ):
            calls.append(
                identifier
            )
            return {
                "id": "ma103n",
                "code": "MA103N",
                "name": "Linear Algebra",
            }

    monkeypatch.setattr(
        knowledge,
        "_build_course_knowledge_context",
        lambda: FakeContext(),
    )

    result = knowledge.find_course(
        "MA103N"
    )

    assert (
        result["id"]
        == "ma103n"
    )
    assert calls == [
        "MA103N"
    ]


def test_knowledge_metadata_wrapper_delegates(
    monkeypatch,
):
    calls = []

    class FakeContext:
        def get_document_metadata(
            self,
            file_path,
            content=None,
        ):
            calls.append(
                (
                    file_path,
                    content,
                )
            )
            return {
                "course_id": "ma103n",
                "course_code": "MA103N",
                "course_name": "Linear Algebra",
                "topic": "",
                "source_type": "course_pdf",
                "document_key": "base:x.pdf",
            }

    monkeypatch.setattr(
        knowledge,
        "_build_course_knowledge_context",
        lambda: FakeContext(),
    )

    result = (
        knowledge
        .get_document_metadata(
            "x.pdf",
            "body",
        )
    )

    assert (
        result["course_code"]
        == "MA103N"
    )
    assert calls == [
        (
            "x.pdf",
            "body",
        )
    ]


def test_fix17_monkeypatch_hooks_still_exist():
    # Older Phase 2 characterization tests patch these names directly.
    assert callable(
        knowledge.find_course
    )
    assert callable(
        knowledge.get_document_metadata
    )
