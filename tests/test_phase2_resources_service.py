import builtins
import hashlib
import json
from pathlib import Path

import pytest

from personal_learning_assistant.domain.resource_models import (
    CreateResourceCommand,
    ListResourcesQuery,
    SearchResourcesQuery,
    UpdateResourceStatusCommand,
)
from personal_learning_assistant.repositories.json.resource_repository import (
    LegacyJsonResourceRepository,
)
from personal_learning_assistant.services.resource_service import (
    ResourceService,
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


@pytest.mark.read_only
def test_zero_byte_legacy_file_reads_empty_without_rewrite(tmp_path):
    path = tmp_path / "resources.json"
    path.write_bytes(b"")

    before = _hash(path)

    repository = LegacyJsonResourceRepository(
        str(path)
    )

    assert repository.load_resources() == []
    assert path.stat().st_size == 0
    assert _hash(path) == before


@pytest.mark.read_only
def test_missing_file_read_does_not_create_file(tmp_path):
    path = tmp_path / "resources.json"

    repository = LegacyJsonResourceRepository(
        str(path)
    )

    assert repository.load_resources() == []
    assert not path.exists()


@pytest.mark.read_only
def test_invalid_json_read_does_not_repair_source(tmp_path):
    path = tmp_path / "resources.json"
    path.write_text(
        "{not valid json",
        encoding="utf-8",
    )

    before = _hash(path)

    repository = LegacyJsonResourceRepository(
        str(path)
    )

    assert repository.load_resources() == []
    assert _hash(path) == before


def test_create_initialises_zero_byte_store_only_on_explicit_command(tmp_path):
    path = tmp_path / "resources.json"
    path.write_bytes(b"")

    service = _service(path)

    result = service.create_resource(
        CreateResourceCommand(
            title="MIT 18.06",
            resource_type="Course",
            link="https://example.test/18.06",
        )
    )

    assert result.resource.position == 1
    assert result.resource.status == "Not Started"

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


def test_create_preserves_legacy_values_without_new_validation(tmp_path):
    path = tmp_path / "resources.json"
    service = _service(path)

    result = service.create_resource(
        CreateResourceCommand(
            title="",
            resource_type="",
            link="",
        )
    )

    assert result.resource.to_legacy_dict() == {
        "title": "",
        "type": "",
        "link": "",
        "status": "Not Started",
    }


@pytest.mark.read_only
def test_list_count_and_get_are_non_interactive(tmp_path, monkeypatch):
    path = tmp_path / "resources.json"
    _write_resources(path)

    def fail_input(*args, **kwargs):
        raise AssertionError(
            "ResourceService called input()."
        )

    monkeypatch.setattr(
        builtins,
        "input",
        fail_input,
    )

    service = _service(path)

    assert (
        service.count_resources().count
        == 2
    )
    assert (
        service.get_resource(1).title
        == "MIT Linear Algebra"
    )
    assert (
        service.get_resource(2).status
        == "Completed"
    )
    assert service.get_resource(3) is None


@pytest.mark.read_only
def test_list_filters_preserve_legacy_values(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    service = _service(path)

    result = service.list_resources(
        ListResourcesQuery(
            resource_type="website",
            status="completed",
        )
    )

    assert [
        resource.title
        for resource in result.resources
    ] == ["NumPy Practice"]


@pytest.mark.read_only
def test_search_matches_title_and_type_case_insensitively(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    service = _service(path)

    by_title = service.search_resources(
        SearchResourcesQuery(
            text="linear",
        )
    )
    by_type = service.search_resources(
        SearchResourcesQuery(
            text="WEBSITE",
        )
    )

    assert [
        item.title
        for item in by_title.resources
    ] == ["MIT Linear Algebra"]

    assert [
        item.title
        for item in by_type.resources
    ] == ["NumPy Practice"]


@pytest.mark.read_only
def test_blank_search_preserves_legacy_match_all_behavior(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    service = _service(path)

    result = service.search_resources(
        SearchResourcesQuery(
            text="   "
        )
    )

    assert len(
        result.resources
    ) == 2


@pytest.mark.parametrize(
    ("requested", "stored"),
    [
        (
            "Not Started",
            "Not Started",
        ),
        (
            "not_started",
            "Not Started",
        ),
        (
            "In Progress",
            "In Progress",
        ),
        (
            "in_progress",
            "In Progress",
        ),
        (
            "Completed",
            "Completed",
        ),
        (
            "completed",
            "Completed",
        ),
    ],
)
def test_status_update_preserves_exact_v1_labels(
    tmp_path,
    requested,
    stored,
):
    path = tmp_path / "resources.json"
    _write_resources(path)

    service = _service(path)

    result = service.update_status(
        UpdateResourceStatusCommand(
            position=1,
            status=requested,
        )
    )

    assert (
        result.resource.status
        == stored
    )

    saved = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        saved[0]["status"]
        == stored
    )


def test_invalid_status_does_not_modify_store(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)
    service = _service(path)

    with pytest.raises(
        ValueError,
        match="Status must be",
    ):
        service.update_status(
            UpdateResourceStatusCommand(
                position=1,
                status="Paused",
            )
        )

    assert _hash(path) == before


def test_invalid_position_does_not_modify_store(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)
    service = _service(path)

    with pytest.raises(
        IndexError,
        match="out of range",
    ):
        service.update_status(
            UpdateResourceStatusCommand(
                position=99,
                status="Completed",
            )
        )

    assert _hash(path) == before


@pytest.mark.read_only
def test_all_service_read_queries_leave_hash_unchanged(tmp_path):
    path = tmp_path / "resources.json"
    _write_resources(path)

    before = _hash(path)
    service = _service(path)

    service.list_resources()
    service.count_resources()
    service.get_resource(1)
    service.search_resources(
        SearchResourcesQuery(
            text="MIT"
        )
    )

    assert _hash(path) == before


def test_atomic_write_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "resources.json"
    service = _service(path)

    service.create_resource(
        CreateResourceCommand(
            title="Course",
            resource_type="Course",
            link="x",
        )
    )

    assert path.exists()
    assert not path.with_name(
        path.name + ".tmp"
    ).exists()
