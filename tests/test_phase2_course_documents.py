import hashlib
import json
from pathlib import Path

import course_manager

from personal_learning_assistant.domain.course_models import (
    CourseDocumentQuery,
    DocumentCourseMatchQuery,
    DocumentQuery,
    LinkDocumentCommand,
    UnlinkDocumentCommand,
)
from personal_learning_assistant.repositories.json.course_repository import (
    LegacyJsonCourseRepository,
)
from personal_learning_assistant.services.course_service import (
    CourseService,
)


FIXED_NOW = "2026-09-13T21:30:00"

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
            "topics": [],
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


def _sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _service(path):
    return CourseService(
        LegacyJsonCourseRepository(path),
        now=lambda: FIXED_NOW,
    )


def _legacy_file(
    monkeypatch,
    path,
):
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


def _document(tmp_path, name="MA103N Notes.md"):
    path = tmp_path / name
    path.write_text(
        "# Notes\n",
        encoding="utf-8",
    )
    return path


def test_link_document_service_matches_facade_storage(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    _legacy_file(
        monkeypatch,
        course_file,
    )

    document = _document(tmp_path)

    result = _service(
        course_file
    ).link_document(
        LinkDocumentCommand(
            file_path=str(document),
            course_identifier="MA103N",
            topic="LU Factorization",
            source_type="obsidian_note",
        )
    )

    facade_link = course_manager.get_document_link(
        str(document)
    )

    assert result.link is not None
    assert (
        result.link.to_legacy_dict()
        == facade_link
    )
    assert (
        facade_link["linked_at"]
        == FIXED_NOW
    )


def test_facade_link_document_preserves_legacy_shape(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    _legacy_file(
        monkeypatch,
        course_file,
    )
    document = _document(tmp_path)

    link = course_manager.link_document(
        str(document),
        "MA103N",
        topic="Vector Spaces",
    )

    assert link == {
        "course_id": "ma103n",
        "topic": "Vector Spaces",
        "source_type": "obsidian_note",
        "display_path": str(document),
        "linked_at": FIXED_NOW,
    }


def test_get_document_link_read_query_does_not_change_hash(
    tmp_path,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    document = _document(tmp_path)

    service = _service(course_file)
    service.link_document(
        LinkDocumentCommand(
            file_path=str(document),
            course_identifier="MA103N",
        )
    )

    before = _sha256(course_file)

    result = service.get_document_link(
        DocumentQuery(
            file_path=str(document)
        )
    )

    after = _sha256(course_file)

    assert result.link is not None
    assert before == after


def test_unlink_document_existing_and_missing(
    tmp_path,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    document = _document(tmp_path)

    service = _service(course_file)
    service.link_document(
        LinkDocumentCommand(
            file_path=str(document),
            course_identifier="MA103N",
        )
    )

    removed = service.unlink_document(
        UnlinkDocumentCommand(
            file_path=str(document)
        )
    )
    missing = service.unlink_document(
        UnlinkDocumentCommand(
            file_path=str(document)
        )
    )

    assert removed.removed is True
    assert missing.removed is False


def test_identify_course_uses_explicit_link_first(
    tmp_path,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    document = _document(
        tmp_path,
        "unrelated-name.md",
    )

    service = _service(course_file)
    service.link_document(
        LinkDocumentCommand(
            file_path=str(document),
            course_identifier="CY100N",
        )
    )

    result = (
        service.identify_course_for_document(
            DocumentQuery(
                file_path=str(document),
                content="course: MA103N",
            )
        )
    )

    assert result.course is not None
    assert result.course.code == "CY100N"


def test_identify_course_supports_frontmatter_and_path_inference(
    tmp_path,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    service = _service(course_file)

    tagged = service.identify_course_for_document(
        DocumentQuery(
            file_path=str(
                tmp_path / "misc.md"
            ),
            content=(
                "course: CY100N\n"
                "topic: Bonding\n"
            ),
        )
    )
    inferred = service.identify_course_for_document(
        DocumentQuery(
            file_path=str(
                tmp_path
                / "MA103N"
                / "lecture.md"
            ),
            content="",
        )
    )

    assert tagged.course is not None
    assert tagged.course.code == "CY100N"

    assert inferred.course is not None
    assert inferred.course.code == "MA103N"


def test_document_metadata_matches_facade_and_is_read_only(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    _legacy_file(
        monkeypatch,
        course_file,
    )
    document = _document(
        tmp_path,
        "tagged.md",
    )
    document.write_text(
        "course: MA103N\n"
        "topic: Bases\n",
        encoding="utf-8",
    )

    before = _sha256(course_file)

    service_result = (
        _service(course_file)
        .get_document_metadata(
            DocumentQuery(
                file_path=str(document)
            )
        )
    )
    facade_result = (
        course_manager.get_document_metadata(
            str(document)
        )
    )

    after = _sha256(course_file)

    assert (
        service_result.metadata.to_legacy_dict()
        == facade_result
    )
    assert facade_result["course_code"] == "MA103N"
    assert facade_result["topic"] == "Bases"
    assert before == after


def test_document_matches_course_parity(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    _legacy_file(
        monkeypatch,
        course_file,
    )

    document = _document(
        tmp_path,
        "MA103N worksheet.md",
    )

    service_match = (
        _service(course_file)
        .document_matches_course(
            DocumentCourseMatchQuery(
                file_path=str(document),
                course_identifier="MA103N",
            )
        )
    )

    facade_match = (
        course_manager.document_matches_course(
            str(document),
            "MA103N",
        )
    )

    assert service_match.matches is True
    assert facade_match is True


def test_linked_documents_for_course_matches_legacy_shape_and_sort(
    tmp_path,
    monkeypatch,
):
    course_file = tmp_path / "courses.json"
    _write(course_file)
    _legacy_file(
        monkeypatch,
        course_file,
    )

    first = _document(
        tmp_path,
        "zeta.md",
    )
    second = _document(
        tmp_path,
        "Alpha.md",
    )

    course_manager.link_document(
        str(first),
        "MA103N",
    )
    course_manager.link_document(
        str(second),
        "MA103N",
    )

    before = _sha256(course_file)

    service_result = (
        _service(course_file)
        .linked_documents_for_course(
            CourseDocumentQuery(
                course_identifier="MA103N"
            )
        )
    )
    facade_result = (
        course_manager.linked_documents_for_course(
            "MA103N"
        )
    )

    service_links = [
        link.to_legacy_dict(
            include_document_key=True
        )
        for link in service_result.links
    ]

    after = _sha256(course_file)

    assert service_links == facade_result
    assert [
        Path(item["display_path"]).name
        for item in facade_result
    ] == [
        "Alpha.md",
        "zeta.md",
    ]
    assert before == after


def test_repository_document_queries_do_not_create_missing_store(
    tmp_path,
):
    course_file = (
        tmp_path
        / "missing"
        / "courses.json"
    )
    repo = LegacyJsonCourseRepository(
        course_file
    )

    assert (
        repo.get_document_link(
            "external:missing"
        )
        is None
    )
    assert (
        repo.list_document_links()
        == {}
    )
    assert not course_file.exists()
