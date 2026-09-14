import ast
import os
from pathlib import Path

import course_manager

from personal_learning_assistant.domain.knowledge_models import (
    KnowledgeDocument,
)
from personal_learning_assistant.repositories.filesystem.knowledge_repository import (
    LegacyFileKnowledgeRepository,
)
from personal_learning_assistant.repositories.interfaces import (
    KnowledgeRepository,
)
from personal_learning_assistant.services.knowledge_service import (
    KnowledgeService,
)
from personal_learning_assistant.ui.cli.course_cli import (
    CourseCLI,
)


def _module_tree(module):
    return ast.parse(
        Path(module.__file__).read_text(
            encoding="utf-8"
        )
    )


def _imports_module(
    module,
    wanted,
):
    tree = _module_tree(module)

    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.Import,
        ):
            if any(
                alias.name == wanted
                for alias in node.names
            ):
                return True

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module == wanted
        ):
            return True

    return False


def test_course_manager_root_is_still_thin_facade():
    tree = _module_tree(
        course_manager
    )

    function = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name
        == "_link_document_interactive"
    )

    assert not any(
        isinstance(
            node,
            ast.ImportFrom,
        )
        and node.module == "knowledge"
        for node in ast.walk(
            function
        )
    )


def test_course_cli_no_longer_imports_legacy_knowledge():
    from personal_learning_assistant.ui.cli import (
        course_cli,
    )

    assert not _imports_module(
        course_cli,
        "knowledge",
    )


def test_knowledge_repository_protocol_declares_read_boundary():
    methods = {
        name
        for name, value
        in vars(
            KnowledgeRepository
        ).items()
        if callable(value)
        and not name.startswith("_")
    }

    assert {
        "list_document_paths",
        "get_vault_path",
    }.issubset(
        methods
    )


def test_repository_read_does_not_create_missing_folders(
    tmp_path,
):
    first = (
        tmp_path
        / "knowledge"
        / "obsidian"
    )
    second = (
        tmp_path
        / "knowledge"
        / "documents"
    )

    repository = (
        LegacyFileKnowledgeRepository(
            base_dir=tmp_path,
            local_folders=(
                first,
                second,
            ),
            obsidian_files_provider=(
                lambda: []
            ),
            vault_path_provider=(
                lambda: None
            ),
        )
    )

    assert (
        repository
        .list_document_paths()
        == ()
    )
    assert not first.exists()
    assert not second.exists()


def test_repository_discovers_supported_files_and_deduplicates(
    tmp_path,
):
    local = (
        tmp_path
        / "knowledge"
        / "documents"
    )
    local.mkdir(
        parents=True
    )

    md_file = local / "a.md"
    txt_file = local / "b.txt"
    pdf_file = local / "c.pdf"
    ignored = local / "d.csv"

    for path in (
        md_file,
        txt_file,
        pdf_file,
        ignored,
    ):
        path.write_text(
            "x",
            encoding="utf-8",
        )

    repository = (
        LegacyFileKnowledgeRepository(
            base_dir=tmp_path,
            local_folders=(
                local,
            ),
            obsidian_files_provider=(
                lambda: [
                    str(md_file)
                ]
            ),
            vault_path_provider=(
                lambda: None
            ),
        )
    )

    found = (
        repository
        .list_document_paths()
    )

    assert found == tuple(
        sorted(
            {
                os.path.abspath(
                    md_file
                ),
                os.path.abspath(
                    txt_file
                ),
                os.path.abspath(
                    pdf_file
                ),
            }
        )
    )


def test_knowledge_service_describes_vault_document(
    tmp_path,
):
    vault = (
        tmp_path
        / "vault"
    )
    vault.mkdir()

    note = (
        vault
        / "Linear Algebra"
        / "LU.md"
    )
    note.parent.mkdir()
    note.write_text(
        "LU",
        encoding="utf-8",
    )

    repository = (
        LegacyFileKnowledgeRepository(
            base_dir=tmp_path,
            local_folders=(),
            obsidian_files_provider=(
                lambda: [
                    str(note)
                ]
            ),
            vault_path_provider=(
                lambda: str(vault)
            ),
        )
    )

    document = (
        KnowledgeService(
            repository
        )
        .describe_document(
            note
        )
    )

    assert isinstance(
        document,
        KnowledgeDocument,
    )
    assert (
        document.scope
        == "obsidian_vault"
    )
    assert (
        document.display_name
        == (
            "Obsidian Vault: "
            + os.path.join(
                "Linear Algebra",
                "LU.md",
            )
        )
    )


def test_new_knowledge_layers_do_not_import_course_manager():
    from personal_learning_assistant.repositories.filesystem import (
        knowledge_repository,
    )
    from personal_learning_assistant.services import (
        knowledge_service,
    )

    assert not _imports_module(
        knowledge_repository,
        "course_manager",
    )
    assert not _imports_module(
        knowledge_service,
        "course_manager",
    )


def test_course_cli_link_uses_injected_service_and_course_api(
    monkeypatch,
):
    output = []
    linked = []

    class FakeAPI:
        @staticmethod
        def get_document_metadata(
            file_path,
        ):
            return {
                "course_code": (
                    "MA103N"
                ),
            }

        @staticmethod
        def link_document(
            file_path,
            course_id,
            topic,
        ):
            linked.append(
                (
                    file_path,
                    course_id,
                    topic,
                )
            )

    class FakeResult:
        documents = (
            KnowledgeDocument(
                path="C:/docs/lu.pdf",
                display_name=(
                    "knowledge/documents/"
                    "lu.pdf"
                ),
                scope="project",
            ),
        )

    class FakeService:
        def list_documents(self):
            return FakeResult()

    answers = iter(
        [
            "1",
            "LU Factorization",
        ]
    )

    cli = CourseCLI(
        course_api=FakeAPI(),
        input_fn=lambda prompt: next(
            answers
        ),
        output_fn=output.append,
    )

    monkeypatch.setattr(
        cli,
        "choose_course",
        lambda prompt: {
            "id": "ma103n",
            "code": "MA103N",
        },
    )

    monkeypatch.setattr(
        cli,
        "_build_knowledge_service",
        lambda: FakeService(),
    )

    cli.link_document_interactive()

    assert linked == [
        (
            "C:/docs/lu.pdf",
            "ma103n",
            "LU Factorization",
        )
    ]

    assert any(
        (
            "knowledge/documents/"
            "lu.pdf"
        )
        in line
        for line in output
    )


def test_course_cli_link_keeps_invalid_number_behavior(
    monkeypatch,
):
    output = []

    class FakeAPI:
        @staticmethod
        def get_document_metadata(
            file_path,
        ):
            return {
                "course_code": None,
            }

    class FakeResult:
        documents = (
            KnowledgeDocument(
                path="C:/docs/a.pdf",
                display_name="a.pdf",
                scope="external",
            ),
        )

    class FakeService:
        def list_documents(self):
            return FakeResult()

    cli = CourseCLI(
        course_api=FakeAPI(),
        input_fn=lambda prompt: "hello",
        output_fn=output.append,
    )

    monkeypatch.setattr(
        cli,
        "choose_course",
        lambda prompt: {
            "id": "ma103n",
            "code": "MA103N",
        },
    )

    monkeypatch.setattr(
        cli,
        "_build_knowledge_service",
        lambda: FakeService(),
    )

    assert (
        cli.link_document_interactive()
        is None
    )

    assert (
        "\nPlease enter a valid number."
        in output
    )


def test_course_cli_builder_targets_knowledge_service():
    from personal_learning_assistant.ui.cli import (
        course_cli,
    )

    tree = _module_tree(
        course_cli
    )

    class_node = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.ClassDef,
        )
        and node.name
        == "CourseCLI"
    )

    helper = next(
        node
        for node in class_node.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name
        == "_build_knowledge_service"
    )

    imported = set()

    for node in ast.walk(
        helper
    ):
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            imported.add(
                node.module
            )

    assert (
        "personal_learning_assistant."
        "services.knowledge_service"
        in imported
    )
