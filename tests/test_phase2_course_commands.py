import json

import pytest

import course_manager

from personal_learning_assistant.domain.course_models import (
    AddTopicCommand,
    CreateCourseCommand,
    SetActiveCourseCommand,
    UpdateCourseStatusCommand,
    UpdateTopicStatusCommand,
)
from personal_learning_assistant.repositories.json.course_repository import (
    LegacyJsonCourseRepository,
)
from personal_learning_assistant.services.course_service import (
    CourseService,
)


FIXED_NOW = "2026-09-13T20:30:00"

BASE_FIXTURE = {
    "version": 1,
    "active_course_id": "ma103n",
    "courses": [
        {
            "id": "ma103n",
            "code": "MA103N",
            "name": "Linear Algebra",
            "semester": "Semester 1",
            "status": "active",
            "topics": [
                {
                    "name": "LU Factorization",
                    "status": "learning",
                    "confidence": 2,
                    "last_updated": "2026-09-13T20:00:00",
                }
            ],
            "created_at": "2026-08-20T09:00:00",
            "updated_at": "2026-09-13T20:00:00",
        },
        {
            "id": "cy100n",
            "code": "CY100N",
            "name": "Chemistry",
            "semester": "Semester 1",
            "status": "active",
            "topics": [],
            "created_at": "2026-08-20T09:10:00",
            "updated_at": "2026-08-20T09:10:00",
        },
    ],
    "document_links": {},
}


def _write(path, payload=BASE_FIXTURE):
    path.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )


def _read(path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def _service(path):
    return CourseService(
        LegacyJsonCourseRepository(path),
        now=lambda: FIXED_NOW,
    )


def _legacy_file(monkeypatch, path):
    monkeypatch.setattr(
        course_manager,
        "COURSES_FILE",
        str(path),
    )
    monkeypatch.setattr(
        course_manager,
        "_now",
        lambda: FIXED_NOW,
    )


def test_create_course_matches_legacy_result_and_json(
    tmp_path,
    monkeypatch,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    legacy_result = course_manager.create_course(
        code="CS101",
        name="Programming",
        semester="Semester 1",
        status="planned",
        topics=["Python Basics"],
    )

    service_result = _service(
        service_file
    ).create_course(
        CreateCourseCommand(
            code="CS101",
            name="Programming",
            semester="Semester 1",
            status="planned",
            topics=(
                {"name": "Python Basics"},
            ),
        )
    )

    assert (
        service_result.course.to_legacy_dict()
        == legacy_result
    )
    assert _read(service_file) == _read(
        legacy_file
    )


def test_set_active_course_matches_legacy(
    tmp_path,
    monkeypatch,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    legacy_result = (
        course_manager.set_active_course(
            "CY100N"
        )
    )
    service_result = _service(
        service_file
    ).set_active_course(
        SetActiveCourseCommand(
            identifier="CY100N"
        )
    )

    assert (
        service_result.course.to_legacy_dict()
        == legacy_result
    )
    assert _read(service_file) == _read(
        legacy_file
    )


def test_update_course_status_matches_legacy(
    tmp_path,
    monkeypatch,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    legacy_result = (
        course_manager.update_course_status(
            "MA103N",
            "completed",
        )
    )
    service_result = _service(
        service_file
    ).update_course_status(
        UpdateCourseStatusCommand(
            identifier="MA103N",
            status="completed",
        )
    )

    assert (
        service_result.course.to_legacy_dict()
        == legacy_result
    )
    assert _read(service_file) == _read(
        legacy_file
    )


def test_add_topic_matches_legacy(
    tmp_path,
    monkeypatch,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    legacy_topic, legacy_created = (
        course_manager.add_topic(
            "MA103N",
            "Vector Spaces",
            status="not_started",
        )
    )
    service_result = _service(
        service_file
    ).add_topic(
        AddTopicCommand(
            course_identifier="MA103N",
            topic_name="Vector Spaces",
            status="not_started",
        )
    )

    assert (
        service_result.topic.to_legacy_dict()
        == legacy_topic
    )
    assert (
        service_result.created
        == legacy_created
    )
    assert _read(service_file) == _read(
        legacy_file
    )


def test_add_existing_topic_does_not_write(
    tmp_path,
    monkeypatch,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    before = service_file.read_bytes()

    legacy_topic, legacy_created = (
        course_manager.add_topic(
            "MA103N",
            "LU Factorization",
        )
    )
    service_result = _service(
        service_file
    ).add_topic(
        AddTopicCommand(
            course_identifier="MA103N",
            topic_name="LU Factorization",
        )
    )

    assert (
        service_result.topic.to_legacy_dict()
        == legacy_topic
    )
    assert (
        service_result.created
        == legacy_created
        == False
    )
    assert service_file.read_bytes() == before


def test_update_topic_status_matches_legacy_and_preserves_practiced(
    tmp_path,
    monkeypatch,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    legacy_result = (
        course_manager.update_topic_status(
            "MA103N",
            "LU Factorization",
            "practiced",
            confidence=4,
        )
    )
    service_result = _service(
        service_file
    ).update_topic_status(
        UpdateTopicStatusCommand(
            course_identifier="MA103N",
            topic_name="LU Factorization",
            status="practiced",
            confidence=4,
        )
    )

    assert (
        service_result.topic.to_legacy_dict()
        == legacy_result
    )
    assert (
        service_result.topic.status
        == "practiced"
    )
    assert _read(service_file) == _read(
        legacy_file
    )


def test_update_missing_topic_matches_legacy_create_behavior(
    tmp_path,
    monkeypatch,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    legacy_result = (
        course_manager.update_topic_status(
            "MA103N",
            "Bases",
            "learning",
            confidence=3,
        )
    )
    service_result = _service(
        service_file
    ).update_topic_status(
        UpdateTopicStatusCommand(
            course_identifier="MA103N",
            topic_name="Bases",
            status="learning",
            confidence=3,
        )
    )

    assert (
        service_result.topic.to_legacy_dict()
        == legacy_result
    )
    assert _read(service_file) == _read(
        legacy_file
    )


@pytest.mark.parametrize(
    "service_call,legacy_call,error_text",
    [
        (
            lambda service: service.create_course(
                CreateCourseCommand(
                    code="",
                    name="Bad",
                )
            ),
            lambda: course_manager.create_course(
                code="",
                name="Bad",
            ),
            "Course code is required.",
        ),
        (
            lambda service: service.set_active_course(
                SetActiveCourseCommand(
                    identifier="NOPE"
                )
            ),
            lambda: course_manager.set_active_course(
                "NOPE"
            ),
            "Course not found.",
        ),
        (
            lambda service: service.update_course_status(
                UpdateCourseStatusCommand(
                    identifier="MA103N",
                    status="invalid-status",
                )
            ),
            lambda: course_manager.update_course_status(
                "MA103N",
                "invalid-status",
            ),
            "Invalid course status.",
        ),
        (
            lambda service: service.update_topic_status(
                UpdateTopicStatusCommand(
                    course_identifier="MA103N",
                    topic_name="LU Factorization",
                    status="invalid-status",
                )
            ),
            lambda: course_manager.update_topic_status(
                "MA103N",
                "LU Factorization",
                "invalid-status",
            ),
            "Invalid topic status.",
        ),
    ],
)
def test_command_validation_matches_legacy_errors(
    tmp_path,
    monkeypatch,
    service_call,
    legacy_call,
    error_text,
):
    legacy_file = tmp_path / "legacy.json"
    service_file = tmp_path / "service.json"
    _write(legacy_file)
    _write(service_file)

    _legacy_file(
        monkeypatch,
        legacy_file,
    )

    with pytest.raises(
        ValueError,
        match=error_text.replace(".", r"\."),
    ):
        legacy_call()

    with pytest.raises(
        ValueError,
        match=error_text.replace(".", r"\."),
    ):
        service_call(
            _service(service_file)
        )
