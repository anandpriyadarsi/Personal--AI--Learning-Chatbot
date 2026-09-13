import json

import course_manager


FIXED_NOW = "2026-09-13T21:00:00"

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


def _configure(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    course_file.write_text(
        json.dumps(
            FIXTURE,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        course_manager,
        "COURSES_FILE",
        str(course_file),
    )
    monkeypatch.setattr(
        course_manager,
        "_now",
        lambda: FIXED_NOW,
    )

    return course_file


def test_facade_queries_keep_legacy_return_shapes(
    tmp_path,
    monkeypatch,
):
    _configure(
        tmp_path,
        monkeypatch,
    )

    courses = course_manager.list_courses()
    found = course_manager.find_course(
        "MA103N"
    )
    active = course_manager.get_active_course()

    assert isinstance(courses, list)
    assert isinstance(courses[0], dict)
    assert found["code"] == "MA103N"
    assert active["id"] == "ma103n"


def test_facade_create_course_keeps_legacy_dict_shape(
    tmp_path,
    monkeypatch,
):
    _configure(
        tmp_path,
        monkeypatch,
    )

    created = course_manager.create_course(
        "CS101",
        "Programming",
        semester="Semester 1",
        status="planned",
        topics=["Python Basics"],
    )

    assert isinstance(created, dict)
    assert created["code"] == "CS101"
    assert created["status"] == "planned"
    assert created["topics"][0]["name"] == "Python Basics"


def test_facade_set_active_course_keeps_legacy_shape(
    tmp_path,
    monkeypatch,
):
    course_file = _configure(
        tmp_path,
        monkeypatch,
    )

    result = course_manager.set_active_course(
        "CY100N"
    )

    assert result["code"] == "CY100N"

    stored = json.loads(
        course_file.read_text(
            encoding="utf-8"
        )
    )
    assert (
        stored["active_course_id"]
        == "cy100n"
    )


def test_facade_update_course_status_keeps_legacy_shape(
    tmp_path,
    monkeypatch,
):
    _configure(
        tmp_path,
        monkeypatch,
    )

    result = (
        course_manager.update_course_status(
            "MA103N",
            "completed",
        )
    )

    assert result["status"] == "completed"
    assert (
        result["updated_at"]
        == FIXED_NOW
    )


def test_facade_add_topic_keeps_legacy_tuple_shape(
    tmp_path,
    monkeypatch,
):
    _configure(
        tmp_path,
        monkeypatch,
    )

    topic, created = course_manager.add_topic(
        "MA103N",
        "Vector Spaces",
        status="learning",
    )

    assert isinstance(topic, dict)
    assert created is True
    assert topic["name"] == "Vector Spaces"
    assert topic["status"] == "learning"


def test_facade_existing_topic_returns_false_without_duplicate(
    tmp_path,
    monkeypatch,
):
    _configure(
        tmp_path,
        monkeypatch,
    )

    topic, created = course_manager.add_topic(
        "MA103N",
        "LU Factorization",
    )

    assert created is False
    assert topic["status"] == "practiced"


def test_facade_update_topic_status_preserves_practiced(
    tmp_path,
    monkeypatch,
):
    _configure(
        tmp_path,
        monkeypatch,
    )

    result = course_manager.update_topic_status(
        "MA103N",
        "LU Factorization",
        "practiced",
        confidence=4,
    )

    assert result["status"] == "practiced"
    assert result["confidence"] == 4


def test_non_routed_course_functions_continue_to_use_public_facade(
    tmp_path,
    monkeypatch,
):
    _configure(
        tmp_path,
        monkeypatch,
    )

    progress = course_manager.get_course_progress(
        "MA103N"
    )

    assert progress is not None
    assert progress["course"]["code"] == "MA103N"
    assert progress["counts"]["practiced"] == 1
