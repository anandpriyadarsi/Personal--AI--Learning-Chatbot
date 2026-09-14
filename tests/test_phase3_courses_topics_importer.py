from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from personal_learning_assistant.migration.courses_topics_importer import (
    import_courses_and_topics,
)
from personal_learning_assistant.migration.legacy_json_import import (
    LegacyImportDataError,
    LegacySourceChangedError,
)
from personal_learning_assistant.migration.legacy_source_scanner import (
    LegacySourceSpec,
    scan_legacy_sources,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


ROOT = Path(__file__).resolve().parents[1]
COURSES_FIXTURE = ROOT / "tests" / "fixtures" / "phase1" / "courses.json"
STAMP_1 = "2026-09-14T02:30:00Z"
STAMP_2 = "2026-09-14T02:45:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_source(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = data_dir / "courses.json"
    target.write_bytes(COURSES_FIXTURE.read_bytes())
    manifest = scan_legacy_sources(
        data_dir,
        specs=(LegacySourceSpec("courses.json"),),
    )
    return target, manifest.sources[0]


def _rescan(data_dir: Path):
    return scan_legacy_sources(
        data_dir,
        specs=(LegacySourceSpec("courses.json"),),
    ).sources[0]


def _connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "shadow.db"
    assert apply_migrations(database_path) == (1, 2)
    return connect_database(database_path, synchronous="FULL")


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])


def test_courses_topics_imports_fixture_without_touching_source(tmp_path):
    source_path, snapshot = _prepare_source(tmp_path)
    before = _sha256(source_path)
    connection = _connection(tmp_path)

    try:
        result = import_courses_and_topics(
            connection,
            snapshot,
            imported_at=STAMP_1,
        )

        assert result.semesters.created == 1
        assert result.courses.created == 2
        assert result.semester_courses.created == 2
        assert result.topics.created == 1
        assert result.settings.created == 1
        assert result.deferred_document_links == 1

        assert _table_count(connection, "semesters") == 1
        assert _table_count(connection, "courses") == 2
        assert _table_count(connection, "semester_courses") == 2
        assert _table_count(connection, "topics") == 1
        assert _table_count(connection, "migration_imports") == 7

        course_rows = connection.execute(
            "SELECT id, code, name FROM courses ORDER BY code"
        ).fetchall()
        assert [row[1] for row in course_rows] == ["CY100N", "MA103N"]
        for row in course_rows:
            assert str(uuid.UUID(row[0])) == row[0]

        semester = connection.execute(
            "SELECT id, name, academic_year FROM semesters"
        ).fetchone()
        assert str(uuid.UUID(semester[0])) == semester[0]
        assert semester[1] == "Legacy Semester 1"
        assert semester[2] == "legacy-unknown"

        credits = connection.execute(
            "SELECT credits_milli FROM semester_courses ORDER BY course_id"
        ).fetchall()
        assert [tuple(row) for row in credits] == [(None,), (None,)]

        topic = connection.execute(
            "SELECT id, name, status, confidence, raw_import_status FROM topics"
        ).fetchone()
        assert str(uuid.UUID(topic[0])) == topic[0]
        assert tuple(topic[1:]) == (
            "Linear Systems",
            "not_started",
            None,
            "not_started",
        )

        active_value = connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'active_course_id'"
        ).fetchone()[0]
        active_id = json.loads(active_value)
        ma_id = connection.execute(
            "SELECT id FROM courses WHERE code = 'MA103N'"
        ).fetchone()[0]
        assert active_id == ma_id

        issue_codes = {issue.code for issue in result.issues}
        assert "document_links_deferred" in issue_codes
        assert "credits_deferred" in issue_codes
    finally:
        connection.close()

    assert _sha256(source_path) == before


def test_reimport_same_snapshot_is_noop_without_duplicate_ledger(tmp_path):
    _, snapshot = _prepare_source(tmp_path)
    connection = _connection(tmp_path)

    try:
        first = import_courses_and_topics(
            connection,
            snapshot,
            imported_at=STAMP_1,
        )
        assert first.changed_rows == 7
        first_setting_time = connection.execute(
            "SELECT updated_at FROM app_settings WHERE key = 'active_course_id'"
        ).fetchone()[0]

        second = import_courses_and_topics(
            connection,
            snapshot,
            imported_at=STAMP_2,
        )

        assert second.changed_rows == 0
        assert second.semesters.matched == 1
        assert second.courses.matched == 2
        assert second.semester_courses.matched == 2
        assert second.topics.matched == 1
        assert second.settings.matched == 1
        assert _table_count(connection, "migration_imports") == 7
        assert _table_count(connection, "courses") == 2
        assert _table_count(connection, "topics") == 1

        second_setting_time = connection.execute(
            "SELECT updated_at FROM app_settings WHERE key = 'active_course_id'"
        ).fetchone()[0]
        assert second_setting_time == first_setting_time == STAMP_1
    finally:
        connection.close()


def test_new_source_hash_updates_stable_targets_and_adds_ledger_evidence(tmp_path):
    source_path, snapshot = _prepare_source(tmp_path)
    connection = _connection(tmp_path)

    try:
        import_courses_and_topics(connection, snapshot, imported_at=STAMP_1)
        old_course_id = connection.execute(
            "SELECT id FROM courses WHERE code = 'MA103N'"
        ).fetchone()[0]
        old_topic_id = connection.execute("SELECT id FROM topics").fetchone()[0]

        data = json.loads(source_path.read_text(encoding="utf-8"))
        data["courses"][0]["name"] = "Synthetic Linear Algebra Revised"
        data["courses"][0]["topics"][0]["status"] = "practiced"
        data["courses"][0]["topics"][0]["confidence"] = 4
        source_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        changed_snapshot = _rescan(source_path.parent)

        result = import_courses_and_topics(
            connection,
            changed_snapshot,
            imported_at=STAMP_2,
        )

        course = connection.execute(
            "SELECT id, name FROM courses WHERE code = 'MA103N'"
        ).fetchone()
        assert course[0] == old_course_id
        assert course[1] == "Synthetic Linear Algebra Revised"

        topic = connection.execute(
            "SELECT id, status, confidence, raw_import_status FROM topics"
        ).fetchone()
        assert topic[0] == old_topic_id
        assert tuple(topic[1:]) == ("practiced", 4, "practiced")
        assert result.courses.updated == 2
        assert result.topics.updated == 1
        assert _table_count(connection, "migration_imports") == 14
    finally:
        connection.close()


def test_topic_status_alias_is_canonical_but_raw_value_is_preserved(tmp_path):
    source_path, _ = _prepare_source(tmp_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    data["courses"][0]["topics"][0]["status"] = "in progress"
    source_path.write_text(json.dumps(data), encoding="utf-8")
    snapshot = _rescan(source_path.parent)
    connection = _connection(tmp_path)

    try:
        result = import_courses_and_topics(connection, snapshot, imported_at=STAMP_1)
        row = connection.execute(
            "SELECT status, raw_import_status FROM topics"
        ).fetchone()
        assert tuple(row) == ("learning", "in progress")
        assert "normalized_topic_status" in {issue.code for issue in result.issues}
    finally:
        connection.close()


def test_duplicate_course_code_is_rejected_before_any_import_write(tmp_path):
    source_path, _ = _prepare_source(tmp_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    duplicate = dict(data["courses"][1])
    duplicate["id"] = "fixture-duplicate"
    duplicate["code"] = "ma103n"
    data["courses"].append(duplicate)
    source_path.write_text(json.dumps(data), encoding="utf-8")
    snapshot = _rescan(source_path.parent)
    connection = _connection(tmp_path)

    try:
        with pytest.raises(LegacyImportDataError, match="duplicate legacy course code"):
            import_courses_and_topics(connection, snapshot, imported_at=STAMP_1)
        assert _table_count(connection, "courses") == 0
        assert _table_count(connection, "topics") == 0
        assert _table_count(connection, "migration_imports") == 0
    finally:
        connection.close()


def test_source_changed_after_scan_is_rejected_without_writes(tmp_path):
    source_path, snapshot = _prepare_source(tmp_path)
    connection = _connection(tmp_path)
    source_path.write_text(
        source_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    try:
        with pytest.raises(LegacySourceChangedError):
            import_courses_and_topics(connection, snapshot, imported_at=STAMP_1)
        assert _table_count(connection, "courses") == 0
        assert _table_count(connection, "migration_imports") == 0
    finally:
        connection.close()


def test_invalid_courses_shape_is_rejected_without_partial_import(tmp_path):
    source_path, _ = _prepare_source(tmp_path)
    source_path.write_text(
        json.dumps({"version": 1, "courses": {"bad": "shape"}}),
        encoding="utf-8",
    )
    snapshot = _rescan(source_path.parent)
    connection = _connection(tmp_path)

    try:
        with pytest.raises(LegacyImportDataError, match="must be an array"):
            import_courses_and_topics(connection, snapshot, imported_at=STAMP_1)
        assert _table_count(connection, "courses") == 0
        assert _table_count(connection, "migration_imports") == 0
    finally:
        connection.close()


def test_missing_course_code_is_not_silently_invented(tmp_path):
    source_path, _ = _prepare_source(tmp_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    data["courses"][0]["code"] = ""
    source_path.write_text(json.dumps(data), encoding="utf-8")
    snapshot = _rescan(source_path.parent)
    connection = _connection(tmp_path)

    try:
        with pytest.raises(LegacyImportDataError, match="refusing to invent one"):
            import_courses_and_topics(connection, snapshot, imported_at=STAMP_1)
        assert _table_count(connection, "courses") == 0
    finally:
        connection.close()
