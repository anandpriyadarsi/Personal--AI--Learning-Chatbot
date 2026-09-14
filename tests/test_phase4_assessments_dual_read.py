from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.assessment_backend import (
    AssessmentBackendConfig,
    DualReadAssessmentRepository,
    build_assessment_repository,
)
from personal_learning_assistant.repositories.json.assessment_repository import (
    LegacyJsonAssessmentRepository,
)
from personal_learning_assistant.repositories.sqlite.assessment_repository import (
    SQLiteAssessmentRepository,
    SQLiteAssessmentRepositoryReadOnlyError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "phase4" / "assessments.json"
COURSE_SOURCE_HASH = "c" * 64
IMPORTED_AT = "2026-09-15T00:30:00Z"
COURSE_IMPORTED_AT = "2026-09-14T18:00:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database_fingerprint(connection: sqlite3.Connection) -> str:
    return hashlib.sha256("\n".join(connection.iterdump()).encode("utf-8")).hexdigest()


def _copy_fixture(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = data_dir / "assessments.json"
    target.write_bytes(FIXTURE.read_bytes())
    return target


def _ledger_row(
    connection: sqlite3.Connection,
    *,
    row_id: str,
    source_path: str,
    source_hash: str,
    source_version: str,
    legacy_key: str,
    target_table: str,
    target_id: str,
    imported_at: str,
    details: dict,
) -> None:
    connection.execute(
        "INSERT INTO migration_imports "
        "(id, source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json) "
        "VALUES (?, ?, ?, 'legacy_json', ?, ?, ?, ?, ?, ?)",
        (
            row_id,
            source_path,
            source_hash,
            source_version,
            legacy_key,
            target_table,
            target_id,
            imported_at,
            json.dumps(details, sort_keys=True),
        ),
    )


def _phase3_like_connection(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "phase4-assessment-shadow.db"
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
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
        CREATE TABLE assessments (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
            assessment_type TEXT NOT NULL,
            title TEXT NOT NULL,
            due_on TEXT,
            due_time TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            weight_bps INTEGER,
            max_points_milli INTEGER,
            earned_points_milli INTEGER,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE assessment_topics (
            id TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
            topic_id TEXT REFERENCES topics(id) ON DELETE RESTRICT,
            raw_label TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            confidence REAL,
            created_at TEXT NOT NULL
        );
        """
    )

    course_rows = (
        ("sqlite-course-ma", "fixture-ma103n", "MA103N", "Synthetic Linear Algebra"),
        ("sqlite-course-cy", "fixture-cy100n", "CY100N", "Synthetic Engineering Chemistry"),
    )
    for index, (target_id, legacy_id, code, name) in enumerate(course_rows):
        connection.execute(
            "INSERT INTO courses VALUES (?, ?, ?, 'active', '', ?, ?, NULL)",
            (target_id, code, name, COURSE_IMPORTED_AT, COURSE_IMPORTED_AT),
        )
        _ledger_row(
            connection,
            row_id="course-ledger-{}".format(index),
            source_path="data/courses.json",
            source_hash=COURSE_SOURCE_HASH,
            source_version="1",
            legacy_key="course:id:{}".format(legacy_id),
            target_table="courses",
            target_id=target_id,
            imported_at=COURSE_IMPORTED_AT,
            details={
                "kind": "course",
                "legacy_id": legacy_id,
                "raw": {"id": legacy_id, "code": code, "name": name},
            },
        )

    # Course topics exist so Phase 4.2 can validate a reviewed/resolved
    # assessment-topic relation without owning the course-topic domain.
    connection.execute(
        "INSERT INTO topics VALUES "
        "('sqlite-topic-linear', 'sqlite-course-ma', 'Linear Systems', 'linear systems', 0, 'learning', 2, 'learning', ?, ?, NULL), "
        "('sqlite-topic-chem', 'sqlite-course-cy', 'Synthetic Catalysis', 'synthetic catalysis', 0, 'not_started', NULL, 'not_started', ?, ?, NULL)",
        (COURSE_IMPORTED_AT, COURSE_IMPORTED_AT, COURSE_IMPORTED_AT, COURSE_IMPORTED_AT),
    )

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_hash = _sha256(FIXTURE)
    assessment_targets = {
        "fixture-assessment-quiz-1": "sqlite-assessment-quiz",
        "fixture-assessment-project-1": "sqlite-assessment-project",
    }
    course_targets = {
        "fixture-ma103n": "sqlite-course-ma",
        "fixture-cy100n": "sqlite-course-cy",
    }

    topic_counter = 0
    for assessment_position, item in enumerate(raw["assessments"]):
        target_id = assessment_targets[item["id"]]
        course_target = course_targets[item["course_id"]]
        connection.execute(
            "INSERT INTO assessments "
            "(id, course_id, assessment_type, title, due_on, due_time, status, "
            "weight_bps, max_points_milli, earned_points_milli, description, "
            "created_at, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                target_id,
                course_target,
                item["type"],
                item["title"],
                item.get("due_date"),
                item.get("due_time"),
                item["status"],
                int(round(item["weightage_percent"] * 100))
                if item.get("weightage_percent") is not None
                else None,
                int(round(item["total_marks"] * 1000))
                if item.get("total_marks") is not None
                else None,
                int(round(item["obtained_marks"] * 1000))
                if item.get("obtained_marks") is not None
                else None,
                item.get("description", ""),
                item.get("created_at", IMPORTED_AT),
                item.get("updated_at", item.get("created_at", IMPORTED_AT)),
            ),
        )
        assessment_key = "assessment:id:{}".format(item["id"])
        _ledger_row(
            connection,
            row_id="assessment-ledger-{}".format(assessment_position),
            source_path="data/assessments.json",
            source_hash=source_hash,
            source_version="2",
            legacy_key=assessment_key,
            target_table="assessments",
            target_id=target_id,
            imported_at=IMPORTED_AT,
            details={
                "kind": "assessment",
                "legacy_id": item["id"],
                "legacy_course_id": item["course_id"],
                "target_course_id": course_target,
                "raw": item,
            },
        )
        for topic_position, label in enumerate(item["topics"]):
            topic_counter += 1
            topic_target = "sqlite-assessment-topic-{}".format(topic_counter)
            connection.execute(
                "INSERT INTO assessment_topics "
                "(id, assessment_id, topic_id, raw_label, source, confidence, created_at) "
                "VALUES (?, ?, NULL, ?, 'legacy_json:data/assessments.json', NULL, ?)",
                (topic_target, target_id, label, IMPORTED_AT),
            )
            normalized = " ".join(label.strip().split()).casefold()
            _ledger_row(
                connection,
                row_id="assessment-topic-ledger-{}".format(topic_counter),
                source_path="data/assessments.json",
                source_hash=source_hash,
                source_version="2",
                legacy_key="{}/topic:label:{}".format(assessment_key, normalized),
                target_table="assessment_topics",
                target_id=topic_target,
                imported_at=IMPORTED_AT,
                details={
                    "kind": "assessment_topic_raw_label",
                    "assessment_legacy_key": assessment_key,
                    "position": topic_position,
                    "raw_label": label,
                    "normalized_label": normalized,
                    "resolution_state": "review_required",
                },
            )

    return connection


def _repositories(tmp_path: Path, diagnostic_sink=None):
    legacy_path = _copy_fixture(tmp_path)
    legacy = LegacyJsonAssessmentRepository(path=legacy_path)
    connection = _phase3_like_connection(tmp_path)
    sqlite_repo = SQLiteAssessmentRepository(connection)
    dual = DualReadAssessmentRepository(
        legacy, sqlite_repo, diagnostic_sink=diagnostic_sink
    )
    return legacy_path, legacy, connection, sqlite_repo, dual


def _domain(report, name: str):
    return next(item for item in report.diagnostics if item.domain == name)


def test_sqlite_repository_read_contract_and_write_rejection(tmp_path):
    _, _, connection, sqlite_repo, _ = _repositories(tmp_path)
    try:
        state = sqlite_repo.load_state()
        assert state["version"] == 2
        assert [item["id"] for item in state["assessments"]] == [
            "fixture-assessment-quiz-1",
            "fixture-assessment-project-1",
        ]
        assert state["assessments"][0]["topics"] == [
            "Linear Systems",
            "Row Reduction",
        ]
        assert state["assessments"][0]["weightage_percent"] == 12.5
        assert state["assessments"][0]["obtained_marks"] == 17.25
        with pytest.raises(SQLiteAssessmentRepositoryReadOnlyError):
            sqlite_repo.save_state(state)
    finally:
        connection.close()


def test_clean_dual_read_returns_exact_legacy_and_matches_supported_domains(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        actual = dual.load_state()
        assert actual == expected
        report = dual.last_report
        assert report is not None
        assert report.status == "pass_with_deferred"
        assert report.mismatch_count == 0
        for domain in (
            "assessment_catalogue",
            "assessment_statuses",
            "assessment_course_relationships",
            "assessment_ordering",
            "assessment_topics",
            "assessment_topic_ordering",
            "raw_identities_and_statuses",
            "raw_assessment_records",
            "assessment_field_alias_evidence",
            "source_version",
            "source_hash",
            "sqlite_structure",
            "resolved_assessment_topic_identities",
            "assessment_alias_tables",
        ):
            assert _domain(report, domain).status == "matched"
        credits = _domain(report, "assessment_course_credits")
        assert credits.status == "deferred"
        assert credits.legacy_value == credits.sqlite_value
    finally:
        connection.close()


def test_assessment_field_mismatch_does_not_replace_legacy_result(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute(
            "UPDATE assessments SET title = 'Shadow Corruption' "
            "WHERE id = 'sqlite-assessment-quiz'"
        )
        assert dual.load_state() == expected
        report = dual.last_report
        assert report is not None
        assert _domain(report, "assessment_catalogue").status == "mismatch"
    finally:
        connection.close()


def test_assessment_status_mismatch_is_explicit(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "UPDATE assessments SET status = 'completed' "
            "WHERE id = 'sqlite-assessment-quiz'"
        )
        dual.load_state()
        assert _domain(dual.last_report, "assessment_statuses").status == "mismatch"
    finally:
        connection.close()


def test_assessment_ordering_mismatch_is_not_sorted_away(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute(
            "SELECT * FROM migration_imports WHERE id = 'assessment-ledger-0'"
        ).fetchone()
        columns = [item[1] for item in connection.execute("PRAGMA table_info(migration_imports)")]
        connection.execute("DELETE FROM migration_imports WHERE id = 'assessment-ledger-0'")
        placeholders = ",".join("?" for _ in columns)
        connection.execute(
            "INSERT INTO migration_imports ({}) VALUES ({})".format(
                ",".join(columns), placeholders
            ),
            tuple(row),
        )
        dual.load_state()
        diag = _domain(dual.last_report, "assessment_ordering")
        assert diag.status == "mismatch"
        assert "rather than sorted away" in diag.message
    finally:
        connection.close()


def test_actual_assessment_course_relationship_corruption_is_detected(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute(
            "UPDATE assessments SET course_id = 'sqlite-course-cy' "
            "WHERE id = 'sqlite-assessment-quiz'"
        )
        assert dual.load_state() == expected
        assert _domain(dual.last_report, "assessment_course_relationships").status == "mismatch"
        structure = _domain(dual.last_report, "sqlite_structure")
        assert structure.status == "mismatch"
        assert any("course relationship differs" in text for text in structure.sqlite_value)
    finally:
        connection.close()


def test_actual_assessment_topic_relationship_corruption_is_detected(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "UPDATE assessment_topics SET assessment_id = 'sqlite-assessment-project' "
            "WHERE id = 'sqlite-assessment-topic-1'"
        )
        dual.load_state()
        assert _domain(dual.last_report, "assessment_topics").status == "mismatch"
        assert _domain(dual.last_report, "sqlite_structure").status == "mismatch"
    finally:
        connection.close()


def test_assessment_topic_ordering_mismatch_is_explicit(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute(
            "SELECT id, details_json FROM migration_imports "
            "WHERE id = 'assessment-topic-ledger-1'"
        ).fetchone()
        details = json.loads(row[1])
        details["position"] = 4
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = ?",
            (json.dumps(details, sort_keys=True), row[0]),
        )
        dual.load_state()
        assert _domain(dual.last_report, "assessment_topic_ordering").status == "mismatch"
    finally:
        connection.close()


def test_raw_identity_whitespace_difference_is_not_normalized_away(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute(
            "SELECT id, details_json FROM migration_imports "
            "WHERE id = 'assessment-ledger-0'"
        ).fetchone()
        details = json.loads(row[1])
        details["raw"]["status"] = "  in_progress  "
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = ?",
            (json.dumps(details, sort_keys=True), row[0]),
        )
        dual.load_state()
        assert _domain(dual.last_report, "assessment_statuses").status == "matched"
        assert _domain(dual.last_report, "raw_identities_and_statuses").status == "mismatch"
        assert _domain(dual.last_report, "raw_assessment_records").status == "mismatch"
    finally:
        connection.close()


def test_legacy_field_alias_evidence_difference_is_not_hidden(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute(
            "SELECT id, details_json FROM migration_imports "
            "WHERE id = 'assessment-ledger-0'"
        ).fetchone()
        details = json.loads(row[1])
        value = details["raw"].pop("weightage_percent")
        details["raw"]["weight"] = value
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = ?",
            (json.dumps(details, sort_keys=True), row[0]),
        )
        dual.load_state()
        assert _domain(dual.last_report, "assessment_catalogue").status == "matched"
        assert _domain(dual.last_report, "assessment_field_alias_evidence").status == "mismatch"
    finally:
        connection.close()


def test_resolved_cross_course_topic_link_is_structural_mismatch(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "UPDATE assessment_topics SET topic_id = 'sqlite-topic-chem' "
            "WHERE id = 'sqlite-assessment-topic-1'"
        )
        dual.load_state()
        report = dual.last_report
        assert _domain(report, "resolved_assessment_topic_identities").status == "deferred"
        structure = _domain(report, "sqlite_structure")
        assert structure.status == "mismatch"
        assert any("links across courses" in text for text in structure.sqlite_value)
    finally:
        connection.close()


def test_stale_historical_assessment_and_topic_rows_are_reported(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        old_hash = "b" * 64
        old_stamp = "2026-09-14T00:00:00Z"
        connection.execute(
            "INSERT INTO assessments VALUES "
            "('sqlite-stale-assessment', 'sqlite-course-ma', 'quiz', 'Stale', NULL, NULL, 'pending', NULL, NULL, NULL, '', ?, ?, NULL)",
            (old_stamp, old_stamp),
        )
        connection.execute(
            "INSERT INTO assessment_topics VALUES "
            "('sqlite-stale-assessment-topic', 'sqlite-stale-assessment', NULL, 'Stale Topic', 'legacy_json:data/assessments.json', NULL, ?)",
            (old_stamp,),
        )
        _ledger_row(
            connection,
            row_id="old-assessment-ledger",
            source_path="data/assessments.json",
            source_hash=old_hash,
            source_version="1",
            legacy_key="assessment:id:old",
            target_table="assessments",
            target_id="sqlite-stale-assessment",
            imported_at=old_stamp,
            details={
                "kind": "assessment",
                "legacy_id": "old",
                "legacy_course_id": "fixture-ma103n",
                "target_course_id": "sqlite-course-ma",
                "raw": {"id": "old", "course_id": "fixture-ma103n"},
            },
        )
        _ledger_row(
            connection,
            row_id="old-assessment-topic-ledger",
            source_path="data/assessments.json",
            source_hash=old_hash,
            source_version="1",
            legacy_key="assessment:id:old/topic:label:stale topic",
            target_table="assessment_topics",
            target_id="sqlite-stale-assessment-topic",
            imported_at=old_stamp,
            details={
                "kind": "assessment_topic_raw_label",
                "assessment_legacy_key": "assessment:id:old",
                "position": 0,
                "raw_label": "Stale Topic",
            },
        )
        dual.load_state()
        structure = _domain(dual.last_report, "sqlite_structure")
        assert structure.status == "mismatch"
        text = " ".join(structure.sqlite_value)
        assert "older data/assessments.json imports" in text
    finally:
        connection.close()


def test_shadow_failure_never_replaces_legacy_result(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    expected = legacy.load_state()
    connection.close()
    assert dual.load_state() == expected
    assert _domain(dual.last_report, "sqlite_read").status == "error"


def test_diagnostic_sink_failure_never_breaks_legacy_read(tmp_path):
    def broken_sink(_report):
        raise RuntimeError("sink unavailable")

    _, legacy, connection, _, dual = _repositories(tmp_path, diagnostic_sink=broken_sink)
    try:
        assert dual.load_state() == legacy.load_state()
        assert dual.last_report is not None
    finally:
        connection.close()


def test_all_reads_preserve_legacy_bytes_hash_and_sqlite_state(tmp_path):
    legacy_path, legacy, connection, sqlite_repo, dual = _repositories(tmp_path)
    try:
        legacy_bytes = legacy_path.read_bytes()
        legacy_hash = _sha256(legacy_path)
        sqlite_fingerprint = _database_fingerprint(connection)
        changes = connection.total_changes

        legacy.load_state()
        sqlite_repo.load_state()
        dual.load_state()
        checks = sqlite_repo.integrity_checks()

        assert legacy_path.read_bytes() == legacy_bytes
        assert _sha256(legacy_path) == legacy_hash
        assert _database_fingerprint(connection) == sqlite_fingerprint
        assert connection.total_changes == changes
        assert checks["integrity_check"] == ("ok",)
        assert checks["foreign_key_check"] == ()
        assert checks["pass"] is True
    finally:
        connection.close()


def test_factory_supports_only_legacy_and_dual_read_with_explicit_sqlite(tmp_path):
    legacy_path = _copy_fixture(tmp_path)
    legacy = build_assessment_repository("legacy", legacy_path=legacy_path)
    assert isinstance(legacy, LegacyJsonAssessmentRepository)
    with pytest.raises(ValueError):
        AssessmentBackendConfig("sqlite")
    with pytest.raises(ValueError, match="explicit SQLite"):
        build_assessment_repository("dual_read", legacy_path=legacy_path)

    connection = _phase3_like_connection(tmp_path)
    try:
        dual = build_assessment_repository(
            "dual_read", legacy_path=legacy_path, sqlite_connection=connection
        )
        assert isinstance(dual, DualReadAssessmentRepository)
        assert dual.load_state() == legacy.load_state()
    finally:
        connection.close()


def test_dual_read_writes_legacy_only_and_next_read_reports_stale_shadow(tmp_path):
    legacy_path, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        sqlite_before = _database_fingerprint(connection)
        state = legacy.load_state()
        state["assessments"][0]["title"] = "Legacy Authoritative Edit"
        saved = dual.save_state(state)
        assert saved["assessments"][0]["title"] == "Legacy Authoritative Edit"
        assert json.loads(legacy_path.read_text(encoding="utf-8"))["assessments"][0]["title"] == "Legacy Authoritative Edit"
        assert _database_fingerprint(connection) == sqlite_before

        assert dual.load_state()["assessments"][0]["title"] == "Legacy Authoritative Edit"
        assert _domain(dual.last_report, "assessment_catalogue").status == "mismatch"
    finally:
        connection.close()


def test_legacy_repository_preserves_current_store_shape_and_last_200_contract(tmp_path):
    path = tmp_path / "assessments.json"
    raw = {
        "version": 1,
        "assessments": [{"id": str(index), "status": "pending"} for index in range(205)],
        "unrelated": "preserved only in source, not application store",
    }
    path.write_text(json.dumps(raw), encoding="utf-8")
    repo = LegacyJsonAssessmentRepository(path=path)
    before = path.read_bytes()
    state = repo.load_state()
    assert state["version"] == 2
    assert len(state["assessments"]) == 200
    assert state["assessments"][0]["id"] == "5"
    assert state["assessments"][-1]["id"] == "204"
    assert path.read_bytes() == before
