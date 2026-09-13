import hashlib
import json
from pathlib import Path

import pytest

import resources
from personal_learning_assistant.repositories.json.resource_repository import (
    LegacyJsonResourceRepository,
)
from personal_learning_assistant.services.resource_service import (
    ResourceService,
)
from personal_learning_assistant.ui.cli.resources_cli import (
    ResourcesCLI,
)


def _hash(path: Path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _write_resources(path: Path):
    path.write_text(
        json.dumps(
            [
                {
                    "title": "MIT Linear Algebra",
                    "type": "Course",
                    "link": "https://example.test/mit",
                    "status": "In Progress",
                },
                {
                    "title": "NumPy Practice",
                    "type": "Website",
                    "link": "https://example.test/numpy",
                    "status": "Completed",
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


def _cli(path, answers=None):
    service = ResourceService(
        LegacyJsonResourceRepository(
            str(path)
        )
    )

    answers = iter(
        answers or []
    )
    output = []

    cli = ResourcesCLI(
        service,
        input_fn=lambda prompt: next(answers),
        output_fn=output.append,
    )

    return cli, output


@pytest.mark.read_only
def test_view_resources_preserves_legacy_rendering(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)
    cli, output = _cli(path)

    returned = cli.view_resources()

    assert returned == [
        {
            "title": "MIT Linear Algebra",
            "type": "Course",
            "link": "https://example.test/mit",
            "status": "In Progress",
        },
        {
            "title": "NumPy Practice",
            "type": "Website",
            "link": "https://example.test/numpy",
            "status": "Completed",
        },
    ]

    assert output == [
        "\n========== MY LEARNING RESOURCES ==========",
        "\n----------------------------",
        "Resource 1",
        "----------------------------",
        "Title  : MIT Linear Algebra",
        "Type   : Course",
        "Link   : https://example.test/mit",
        "Status : In Progress",
        "\n----------------------------",
        "Resource 2",
        "----------------------------",
        "Title  : NumPy Practice",
        "Type   : Website",
        "Link   : https://example.test/numpy",
        "Status : Completed",
    ]

    assert _hash(path) == before


@pytest.mark.read_only
def test_view_empty_store_matches_legacy_message(tmp_path):
    path = tmp_path / "resources.json"
    path.write_bytes(b"")

    before = _hash(path)
    cli, output = _cli(path)

    assert cli.view_resources() == []
    assert output == [
        "\nNo resources found."
    ]
    assert _hash(path) == before


@pytest.mark.read_only
def test_search_routes_input_through_service_and_preserves_output(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)
    cli, output = _cli(
        path,
        answers=["LINEAR"],
    )

    returned = cli.search_resources()

    assert returned == [
        {
            "title": "MIT Linear Algebra",
            "type": "Course",
            "link": "https://example.test/mit",
            "status": "In Progress",
        }
    ]

    assert output == [
        "\n----------------------------",
        "Title  : MIT Linear Algebra",
        "Type   : Course",
        "Link   : https://example.test/mit",
        "Status : In Progress",
    ]

    assert _hash(path) == before


@pytest.mark.read_only
def test_search_no_match_preserves_legacy_message(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    cli, output = _cli(
        path,
        answers=["missing"],
    )

    assert cli.search_resources() == []
    assert output == [
        "\n❌ No matching resource found."
    ]


@pytest.mark.read_only
def test_blank_search_preserves_legacy_match_all_behavior(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)
    cli, output = _cli(
        path,
        answers=[""],
    )

    returned = cli.search_resources()

    assert len(returned) == 2
    assert "Title  : MIT Linear Algebra" in output
    assert "Title  : NumPy Practice" in output
    assert _hash(path) == before


@pytest.mark.read_only
def test_count_resources_preserves_legacy_summary(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)
    cli, output = _cli(path)

    assert cli.count_resources() == 2
    assert output == [
        "\n========== RESOURCE SUMMARY ==========",
        "\n📚 Total Resources : 2",
    ]
    assert _hash(path) == before


def test_root_resource_read_functions_delegate_to_cli_adapter(monkeypatch):
    calls = []

    class FakeCLI:
        def view_resources(self):
            calls.append("view")
            return ["view"]

        def search_resources(self):
            calls.append("search")
            return ["search"]

        def count_resources(self):
            calls.append("count")
            return 7

    monkeypatch.setattr(
        resources,
        "_build_resources_cli",
        lambda: FakeCLI(),
    )

    def fail_legacy_loader():
        raise AssertionError(
            "Legacy root loader was used by a routed read command."
        )

    monkeypatch.setattr(
        resources,
        "load_resources",
        fail_legacy_loader,
    )

    assert resources.view_resources() == ["view"]
    assert resources.search_resources() == ["search"]
    assert resources.count_resources() == 7
    assert calls == [
        "view",
        "search",
        "count",
    ]
