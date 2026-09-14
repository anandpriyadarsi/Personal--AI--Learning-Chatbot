from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.course_backend import (
    CourseBackendConfig,
    DualReadCourseRepository,
    build_course_repository,
)
from personal_learning_assistant.repositories.json.course_repository import (
    LegacyJsonCourseRepository,
)
from personal_learning_assistant.repositories.sqlite.course_repository import (
    SQLiteCourseRepository,
    SQLiteCourseRepositoryReadOnlyError,
)
from personal_learning_assistant.services.course_service import CourseService
from personal_learning_assistant.domain.course_models import (
    GetCourseQuery,
    ListCoursesQuery,
    UpdateCourseStatusCommand,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "phase4" / "courses.json"
SOURCE_HASH = "a" * 64
IMPORTED_AT = "2026-09-14T18:00:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database_fingerprint(connection: sqlite3.Connection) -> str:
    dump = "\n".join(connection.iterdump()).encode("utf-8")
    return hashlib.sha256(dump).hexdigest()


def _copy_fixture(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = data_dir / "courses.json"
    target.write_bytes(FIXTURE.read_bytes())
    return target


def _migration_row(
    connection: sqlite3.Connection,
    *,
    row_id: str,
    legacy_key: str,
    target_table: str,
    target_id: str,
    details: dict,
) -> None:
    connection.execute(
        "INSERT INTO migration_imports "
        "(id, source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json) "
        "VALUES (?, 'data/courses.json', ?, 'legacy_json', '1', ?, ?, ?, ?, ?)",
        (
            row_id,
            SOURCE_HASH,
            legacy_key,
            target_table,
            target_id,
            IMPORTED_AT,
            json.dumps(details, sort_keys=True),
        ),
    )


def _phase3_like_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "phase4-shadow.db"
    connection = sqlite3.connect(str(database_path), isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE migration_imports (
            id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_version TEXT NOT NULL DEFAULT '',
            legacy_key TEXT NOT NULL DEFAULT '',
            target_table TEXT NOT NULL,
            target_id TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE semesters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            academic_year TEXT NOT NULL,
            starts_on TEXT,
            ends_on TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE courses (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL COLLATE NOCASE UNIQUE,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE semester_courses (
            semester_id TEXT NOT NULL REFERENCES semesters(id) ON DELETE RESTRICT,
            course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
            credits_milli INTEGER,
            instructor TEXT NOT NULL DEFAULT '',
            enrollment_status TEXT NOT NULL DEFAULT 'enrolled',
            PRIMARY KEY (semester_id, course_id)
        );
        CREATE TABLE topics (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'not_started',
            confidence INTEGER,
            raw_import_status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            UNIQUE (course_id, normalized_name)
        );
        CREATE TABLE course_aliases (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE topic_aliases (
            id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
            course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    semester_id = "sqlite-semester-1"
    course_ids = {
        "fixture-ma103n": "sqlite-course-ma",
        "fixture-cy100n": "sqlite-course-cy",
    }
    topic_ids = {
        "fixture-linear-systems": "sqlite-topic-linear",
        "fixture-lu": "sqlite-topic-lu",
    }

    connection.execute(
        "INSERT INTO semesters VALUES (?, ?, ?, NULL, NULL, 'planned', ?, ?)",
        (semester_id, "Legacy Semester 1", "legacy-unknown", IMPORTED_AT, IMPORTED_AT),
    )
    _migration_row(
        connection,
        row_id="ledger-semester-1",
        legacy_key="semester:1",
        target_table="semesters",
        target_id=semester_id,
        details={
            "kind": "semester_placeholder",
            "legacy_semester": "1",
            "academic_year": "legacy-unknown",
        },
    )
    for course_position, course in enumerate(raw["courses"]):
        target_id = course_ids[course["id"]]
        canonical_status = course["status"]
        connection.execute(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, '', ?, ?, NULL)",
            (
                target_id,
                course["code"],
                course["name"],
                canonical_status,
                course["created_at"],
                course["updated_at"],
            ),
        )
        connection.execute(
            "INSERT INTO semester_courses "
            "(semester_id, course_id, credits_milli, instructor, enrollment_status) "
            "VALUES (?, ?, NULL, '', ?)",
            (
                semester_id,
                target_id,
                "planned" if canonical_status == "planned" else "enrolled",
            ),
        )
        course_key = "course:id:{}".format(course["id"])
        _migration_row(
            connection,
            row_id="ledger-course-{}".format(course_position),
            legacy_key=course_key,
            target_table="courses",
            target_id=target_id,
            details={
                "kind": "course",
                "legacy_id": course["id"],
                "raw": course,
            },
        )
        _migration_row(
            connection,
            row_id="ledger-semester-course-{}".format(course_position),
            legacy_key=course_key + "/semester_course",
            target_table="semester_courses",
            target_id="{}|{}".format(semester_id, target_id),
            details={
                "kind": "semester_course",
                "legacy_semester": course["semester"],
                "credits_milli": None,
            },
        )

        for topic_position, topic in enumerate(course["topics"]):
            target_topic_id = topic_ids[topic["id"]]
            raw_status = topic["status"]
            canonical_status = "learning" if raw_status == "in progress" else raw_status
            confidence = topic["confidence"]
            connection.execute(
                "INSERT INTO topics "
                "(id, course_id, name, normalized_name, position, status, confidence, "
                "raw_import_status, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    target_topic_id,
                    target_id,
                    topic["name"],
                    topic["name"].casefold(),
                    topic_position,
                    canonical_status,
                    confidence,
                    raw_status,
                    IMPORTED_AT,
                    topic["last_updated"] or IMPORTED_AT,
                ),
            )
            _migration_row(
                connection,
                row_id="ledger-topic-{}-{}".format(course_position, topic_position),
                legacy_key=course_key + "/topic:id:" + topic["id"],
                target_table="topics",
                target_id=target_topic_id,
                details={
                    "kind": "topic",
                    "course_legacy_key": course_key,
                    "raw": topic,
                },
            )

    connection.execute(
        "INSERT INTO app_settings VALUES ('active_course_id', ?, ?)",
        (json.dumps(course_ids[raw["active_course_id"]]), IMPORTED_AT),
    )
    return connection


def _repositories(tmp_path: Path):
    legacy_path = _copy_fixture(tmp_path)
    legacy = LegacyJsonCourseRepository(path=legacy_path)
    connection = _phase3_like_connection(tmp_path)
    sqlite_repo = SQLiteCourseRepository(connection)
    dual = DualReadCourseRepository(legacy, sqlite_repo)
    return legacy_path, legacy, connection, sqlite_repo, dual


def _domain(report, name: str):
    return next(item for item in report.diagnostics if item.domain == name)


def test_sqlite_repository_implements_course_repository_read_contract(tmp_path):
    _, _, connection, sqlite_repo, _ = _repositories(tmp_path)
    try:
        state = sqlite_repo.load_state()
        assert state["active_course_id"] == "fixture-ma103n"
        assert [course["code"] for course in state["courses"]] == ["MA103N", "CY100N"]
        assert [topic["name"] for topic in state["courses"][0]["topics"]] == [
            "Linear Systems",
            "LU Factorization",
        ]
        assert state["courses"][0]["topics"][0]["status"] == "learning"
        assert state["courses"][0]["topics"][1]["confidence"] == 0
        assert sqlite_repo.get_document_link("anything") is None
        assert sqlite_repo.list_document_links() == {}
        with pytest.raises(SQLiteCourseRepositoryReadOnlyError):
            sqlite_repo.save_state(state)
        with pytest.raises(SQLiteCourseRepositoryReadOnlyError):
            sqlite_repo.upsert_document_link("x", {})
        with pytest.raises(SQLiteCourseRepositoryReadOnlyError):
            sqlite_repo.delete_document_link("x")
    finally:
        connection.close()


def test_dual_read_returns_legacy_and_matches_all_supported_domains(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        actual = dual.load_state()
        assert actual == expected
        report = dual.last_report
        assert report is not None
        assert report.status == "pass_with_deferred"
        assert report.mismatch_count == 0
        assert _domain(report, "course_catalogue").status == "matched"
        assert _domain(report, "active_course").status == "matched"
        assert _domain(report, "semester_mappings").status == "matched"
        assert _domain(report, "topics").status == "matched"
        assert _domain(report, "course_statuses").status == "matched"
        assert _domain(report, "topic_statuses").status == "matched"
        assert _domain(report, "raw_identities_and_statuses").status == "matched"
        assert _domain(report, "course_aliases").status == "matched"
        assert _domain(report, "topic_aliases").status == "matched"
        assert _domain(report, "course_ordering").status == "matched"
        assert _domain(report, "topic_ordering").status == "matched"
        document = _domain(report, "course_document_relationships")
        assert document.status == "deferred"
        assert document.legacy_value
    finally:
        connection.close()


def test_dual_read_reports_mismatch_without_changing_authoritative_result(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute(
            "UPDATE topics SET status = 'mastered' WHERE id = 'sqlite-topic-linear'"
        )
        actual = dual.load_state()
        assert actual == expected
        report = dual.last_report
        assert report is not None
        assert report.status == "mismatch"
        assert _domain(report, "topics").status == "mismatch"
        status_diag = _domain(report, "topic_statuses")
        assert status_diag.status == "mismatch"
        assert status_diag.legacy_value != status_diag.sqlite_value
    finally:
        connection.close()


def test_raw_status_difference_is_not_hidden_by_same_canonical_status(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        # Keep canonical status identical but corrupt only preserved raw evidence.
        connection.execute(
            "UPDATE topics SET raw_import_status = 'learning' "
            "WHERE id = 'sqlite-topic-linear'"
        )
        dual.load_state()
        report = dual.last_report
        assert report is not None
        assert _domain(report, "topic_statuses").status == "matched"
        raw_diag = _domain(report, "raw_identities_and_statuses")
        assert raw_diag.status == "mismatch"
        assert "does not suppress" in raw_diag.message
    finally:
        connection.close()


def test_raw_ledger_whitespace_difference_is_not_normalized_away(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute(
            "SELECT id, details_json FROM migration_imports "
            "WHERE target_table = 'topics' AND target_id = 'sqlite-topic-linear'"
        ).fetchone()
        details = json.loads(row[1])
        details["raw"]["status"] = "  in progress  "
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = ?",
            (json.dumps(details, sort_keys=True), row[0]),
        )
        dual.load_state()
        report = dual.last_report
        assert report is not None
        assert _domain(report, "topic_statuses").status == "matched"
        assert _domain(report, "raw_identities_and_statuses").status == "mismatch"
    finally:
        connection.close()


def test_alias_and_order_mismatches_are_explicit(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "INSERT INTO course_aliases "
            "(id, course_id, alias, normalized_alias, provider, source, created_at) "
            "VALUES ('alias-1', 'sqlite-course-ma', 'MATH', 'math', '', 'test', ?)",
            (IMPORTED_AT,),
        )
        connection.execute(
            "UPDATE topics SET position = 3 WHERE id = 'sqlite-topic-linear'"
        )
        dual.load_state()
        report = dual.last_report
        assert report is not None
        assert _domain(report, "course_aliases").status == "mismatch"
        assert _domain(report, "topic_ordering").status == "mismatch"
    finally:
        connection.close()


def test_all_read_operations_preserve_legacy_bytes_and_sqlite_state(tmp_path):
    legacy_path, _, connection, sqlite_repo, dual = _repositories(tmp_path)
    try:
        legacy_before = legacy_path.read_bytes()
        legacy_hash_before = _sha256(legacy_path)
        sqlite_before = _database_fingerprint(connection)
        changes_before = connection.total_changes

        dual.load_state()
        dual.get_document_link("base:knowledge/documents/synthetic-linear-algebra.pdf")
        dual.list_document_links()
        checks = sqlite_repo.integrity_checks()

        assert checks == {
            "integrity_check": ("ok",),
            "foreign_key_check": (),
            "pass": True,
        }
        assert legacy_path.read_bytes() == legacy_before
        assert _sha256(legacy_path) == legacy_hash_before
        assert _database_fingerprint(connection) == sqlite_before
        assert connection.total_changes == changes_before
    finally:
        connection.close()


def test_factory_supports_only_legacy_and_dual_read(tmp_path):
    legacy_path = _copy_fixture(tmp_path)
    legacy = build_course_repository("legacy", legacy_path=legacy_path)
    assert isinstance(legacy, LegacyJsonCourseRepository)

    connection = _phase3_like_connection(tmp_path)
    try:
        dual = build_course_repository(
            CourseBackendConfig("dual_read"),
            legacy_path=legacy_path,
            sqlite_connection=connection,
        )
        assert isinstance(dual, DualReadCourseRepository)
        assert dual.load_state()["active_course_id"] == "fixture-ma103n"
        with pytest.raises(ValueError, match="legacy.*dual_read"):
            CourseBackendConfig("sqlite")
        with pytest.raises(ValueError, match="explicit SQLite"):
            build_course_repository("dual_read", legacy_path=legacy_path)
    finally:
        connection.close()


def test_course_service_public_reads_are_unchanged_with_dual_backend(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        legacy_service = CourseService(legacy)
        dual_service = CourseService(dual)
        assert dual_service.list_courses(ListCoursesQuery()) == legacy_service.list_courses(
            ListCoursesQuery()
        )
        assert dual_service.get_course(GetCourseQuery("MA103N")) == legacy_service.get_course(
            GetCourseQuery("MA103N")
        )
        assert dual_service.get_active_course() == legacy_service.get_active_course()
    finally:
        connection.close()


def test_dual_read_commands_keep_legacy_writer_authoritative_only(tmp_path):
    legacy_path, _, connection, _, dual = _repositories(tmp_path)
    try:
        sqlite_before = _database_fingerprint(connection)
        service = CourseService(dual, now=lambda: "2026-09-14T18:30:00")
        result = service.update_course_status(
            UpdateCourseStatusCommand(identifier="CY100N", status="active")
        )
        assert result.course.status == "active"
        written = json.loads(legacy_path.read_text(encoding="utf-8"))
        cy = next(course for course in written["courses"] if course["code"] == "CY100N")
        assert cy["status"] == "active"
        assert _database_fingerprint(connection) == sqlite_before
        # A subsequent read sees the expected stale-shadow mismatch explicitly.
        dual.load_state()
        assert dual.last_report is not None
        assert dual.last_report.status == "mismatch"
    finally:
        connection.close()


def test_sqlite_shadow_failure_never_replaces_legacy_result(tmp_path):
    _, legacy, connection, sqlite_repo, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute("DROP TABLE topics")
        actual = dual.load_state()
        assert actual == expected
        assert dual.last_report is not None
        assert dual.last_report.status == "mismatch"
        assert _domain(dual.last_report, "sqlite_read").status == "error"
    finally:
        connection.close()

def test_diagnostic_sink_failure_never_breaks_authoritative_read(tmp_path):
    legacy_path = _copy_fixture(tmp_path)
    legacy = LegacyJsonCourseRepository(path=legacy_path)
    connection = _phase3_like_connection(tmp_path)
    sqlite_repo = SQLiteCourseRepository(connection)

    def failing_sink(_report):
        raise RuntimeError("synthetic diagnostic sink failure")

    dual = DualReadCourseRepository(legacy, sqlite_repo, diagnostic_sink=failing_sink)
    try:
        expected = legacy.load_state()
        assert dual.load_state() == expected
        assert dual.last_report is not None
        assert dual.last_report.status == "pass_with_deferred"
    finally:
        connection.close()
