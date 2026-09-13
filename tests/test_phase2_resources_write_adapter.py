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


def _service(path: Path):
    return ResourceService(
        LegacyJsonResourceRepository(
            str(path)
        )
    )


def _cli(
    path: Path,
    answers=None,
):
    answers = iter(
        answers or []
    )
    output = []

    cli = ResourcesCLI(
        _service(path),
        input_fn=lambda prompt: next(answers),
        output_fn=output.append,
    )

    return cli, output


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


def test_add_resource_routes_through_service_and_preserves_v1_shape(tmp_path):
    path = tmp_path / "resources.json"
    path.write_bytes(b"")

    cli, output = _cli(
        path,
        answers=[
            "MIT 18.06",
            "Course",
            "https://example.test/18.06",
        ],
    )

    returned = cli.add_resource()

    assert returned == {
        "title": "MIT 18.06",
        "type": "Course",
        "link": "https://example.test/18.06",
        "status": "Not Started",
    }

    assert output == [
        "\n========== ADD NEW RESOURCE ==========\n",
        "\n✅ Resource added successfully!",
    ]

    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == [
        {
            "title": "MIT 18.06",
            "type": "Course",
            "link": "https://example.test/18.06",
            "status": "Not Started",
        }
    ]


def test_add_resource_preserves_legacy_empty_input_behavior(tmp_path):
    path = tmp_path / "resources.json"

    cli, _ = _cli(
        path,
        answers=[
            "",
            "",
            "",
        ],
    )

    returned = cli.add_resource()

    assert returned == {
        "title": "",
        "type": "",
        "link": "",
        "status": "Not Started",
    }


def test_update_status_routes_through_service_and_preserves_menu(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    cli, output = _cli(
        path,
        answers=[
            "1",
            "3",
        ],
    )

    returned = cli.update_status()

    assert returned == {
        "title": "MIT Linear Algebra",
        "type": "Course",
        "link": "https://example.test/mit",
        "status": "Completed",
    }

    assert output == [
        "\n========== UPDATE STATUS ==========\n",
        "1. MIT Linear Algebra (In Progress)",
        "2. NumPy Practice (Completed)",
        "\nChoose Status",
        "1. Not Started",
        "2. In Progress",
        "3. Completed",
        "\n✅ Status updated successfully!",
    ]

    saved = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        saved[0]["status"]
        == "Completed"
    )


def test_update_status_empty_store_matches_legacy_behavior(tmp_path):
    path = tmp_path / "resources.json"
    path.write_bytes(b"")

    before = _hash(path)

    cli, output = _cli(path)

    assert cli.update_status() is None
    assert output == [
        "\nNo resources found."
    ]
    assert _hash(path) == before


@pytest.mark.parametrize(
    ("answers", "expected_message"),
    [
        (
            ["hello"],
            "\nPlease enter a valid number.",
        ),
        (
            ["99"],
            "Invalid choice.",
        ),
        (
            ["1", "9"],
            "Invalid status.",
        ),
    ],
)
def test_invalid_update_inputs_do_not_modify_store(
    tmp_path,
    answers,
    expected_message,
):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)

    cli, output = _cli(
        path,
        answers=answers,
    )

    assert cli.update_status() is None
    assert (
        expected_message
        in output
    )
    assert _hash(path) == before


def test_root_resource_write_functions_delegate_to_cli_adapter(monkeypatch):
    calls = []

    class FakeCLI:
        def add_resource(self):
            calls.append("add")
            return {
                "title": "A",
                "type": "B",
                "link": "C",
                "status": "Not Started",
            }

        def update_status(self):
            calls.append("update")
            return {
                "title": "A",
                "type": "B",
                "link": "C",
                "status": "Completed",
            }

    monkeypatch.setattr(
        resources,
        "_build_resources_cli",
        lambda: FakeCLI(),
    )

    def fail_legacy_loader():
        raise AssertionError(
            "Legacy root loader was used by a routed write command."
        )

    def fail_legacy_saver(value):
        raise AssertionError(
            "Legacy root saver was used by a routed write command."
        )

    monkeypatch.setattr(
        resources,
        "load_resources",
        fail_legacy_loader,
    )
    monkeypatch.setattr(
        resources,
        "save_resources",
        fail_legacy_saver,
    )

    added = resources.add_resource()
    updated = resources.update_status()

    assert (
        added["status"]
        == "Not Started"
    )
    assert (
        updated["status"]
        == "Completed"
    )
    assert calls == [
        "add",
        "update",
    ]


def test_all_five_root_resource_commands_now_delegate(monkeypatch):
    calls = []

    class FakeCLI:
        def add_resource(self):
            calls.append("add")

        def view_resources(self):
            calls.append("view")

        def search_resources(self):
            calls.append("search")

        def count_resources(self):
            calls.append("count")

        def update_status(self):
            calls.append("update")

    monkeypatch.setattr(
        resources,
        "_build_resources_cli",
        lambda: FakeCLI(),
    )

    resources.add_resource()
    resources.view_resources()
    resources.search_resources()
    resources.count_resources()
    resources.update_status()

    assert calls == [
        "add",
        "view",
        "search",
        "count",
        "update",
    ]
