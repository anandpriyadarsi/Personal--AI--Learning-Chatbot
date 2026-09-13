import hashlib
import json

import course_manager

from personal_learning_assistant.domain.course_models import (
    GetCourseQuery,
    ListCoursesQuery,
)
from personal_learning_assistant.repositories.json.course_repository import (
    LegacyJsonCourseRepository,
)
from personal_learning_assistant.services.course_service import (
    CourseService,
)


FIXTURE = {
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
                    "status": "practiced",
                    "confidence": 3,
                    "last_updated": "2026-09-13T20:00:00",
                },
                {
                    "name": "Vector Spaces",
                    "status": "learning",
                    "confidence": 2,
                    "last_updated": "2026-09-13T20:01:00",
                },
            ],
            "created_at": "2026-08-20T09:00:00",
            "updated_at": "2026-09-13T20:01:00",
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


def _write_fixture(path):
    path.write_text(
        json.dumps(
            FIXTURE,
            indent=2,
        ),
        encoding="utf-8",
    )


def _sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _service(path):
    return CourseService(
        LegacyJsonCourseRepository(path)
    )


def test_list_courses_matches_legacy_output(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write_fixture(course_file)

    monkeypatch.setattr(
        course_manager,
        "COURSES_FILE",
        str(course_file),
    )

    legacy = course_manager.list_courses()
    result = _service(
        course_file
    ).list_courses()

    assert [
        course.to_legacy_dict()
        for course in result.courses
    ] == legacy


def test_status_filter_matches_legacy_output(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write_fixture(course_file)

    monkeypatch.setattr(
        course_manager,
        "COURSES_FILE",
        str(course_file),
    )

    legacy = course_manager.list_courses(
        status="active"
    )
    result = _service(
        course_file
    ).list_courses(
        ListCoursesQuery(
            status="active"
        )
    )

    assert [
        course.to_legacy_dict()
        for course in result.courses
    ] == legacy


def test_get_course_matches_legacy_lookup(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write_fixture(course_file)

    monkeypatch.setattr(
        course_manager,
        "COURSES_FILE",
        str(course_file),
    )

    legacy = course_manager.find_course(
        "MA103N"
    )
    result = _service(
        course_file
    ).get_course(
        GetCourseQuery(
            identifier="MA103N"
        )
    )

    assert result.course is not None
    assert result.course.to_legacy_dict() == legacy


def test_get_active_course_matches_legacy_output(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write_fixture(course_file)

    monkeypatch.setattr(
        course_manager,
        "COURSES_FILE",
        str(course_file),
    )

    legacy = course_manager.get_active_course()
    result = _service(
        course_file
    ).get_active_course()

    assert result.course is not None
    assert result.course.to_legacy_dict() == legacy


def test_read_queries_leave_courses_json_hash_unchanged(
    tmp_path,
):
    course_file = tmp_path / "courses.json"
    _write_fixture(course_file)

    before = _sha256(
        course_file
    )

    service = _service(
        course_file
    )
    service.list_courses()
    service.get_course(
        GetCourseQuery(
            identifier="Linear Algebra"
        )
    )
    service.get_active_course()

    after = _sha256(
        course_file
    )

    assert after == before


def test_missing_store_is_read_without_creating_file(
    tmp_path,
):
    course_file = (
        tmp_path
        / "missing"
        / "courses.json"
    )

    result = _service(
        course_file
    ).list_courses()

    assert result.courses == ()
    assert result.active_course_id is None
    assert not course_file.exists()


def test_practiced_topic_survives_service_normalization(
    tmp_path,
):
    course_file = tmp_path / "courses.json"
    _write_fixture(course_file)

    result = _service(
        course_file
    ).get_course(
        GetCourseQuery(
            identifier="MA103N"
        )
    )

    assert result.course is not None

    statuses = {
        topic.name: topic.status
        for topic in result.course.topics
    }

    assert statuses[
        "LU Factorization"
    ] == "practiced"
