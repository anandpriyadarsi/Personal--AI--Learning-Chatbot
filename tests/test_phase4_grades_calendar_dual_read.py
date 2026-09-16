from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.assessments_topics_importer import (
    import_assessments_and_topics,
)
from personal_learning_assistant.migration.courses_topics_importer import (
    import_courses_and_topics,
)
from personal_learning_assistant.migration.grades_calendar_importer import (
    import_grades_and_academic_calendar,
)
from personal_learning_assistant.migration.legacy_source_scanner import (
    LegacySourceSpec,
    scan_legacy_sources,
)
from personal_learning_assistant.repositories.grade_calendar_backend import (
    DualReadGradeCalendarRepository,
    GradeCalendarBackendConfig,
    build_grade_calendar_repository,
)
from personal_learning_assistant.repositories.json.grade_calendar_repository import (
    LegacyJsonGradeCalendarRepository,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.grade_calendar_repository import (
    SQLiteGradeCalendarRepository,
    SQLiteGradeCalendarRepositoryReadOnlyError,
    SQLiteGradeCalendarRepositorySchemaError,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase4"
STAMP = "2026-09-15T09:15:00Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_sources(tmp_path: Path, *, include_grade: bool = True):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("courses.json", "assessments.json"):
        (data / name).write_bytes((FIXTURES / name).read_bytes())
    if include_grade:
        (data / "semester_grade_config.json").write_bytes(
            (FIXTURES / "semester_grade_config.json").read_bytes()
        )
    snapshots = scan_legacy_sources(
        data,
        specs=(
            LegacySourceSpec("courses.json"),
            LegacySourceSpec("assessments.json"),
            LegacySourceSpec("semester_grade_config.json", required=False),
        ),
    ).sources
    return data, {Path(item.canonical_path).name: item for item in snapshots}


def _prepared(tmp_path: Path, *, include_grade: bool = True):
    data, snapshots = _copy_sources(tmp_path, include_grade=include_grade)
    db = tmp_path / "shadow.db"
    assert (apply_migrations(db))[:2] == (1, 2)
    connection = connect_database(db, synchronous="FULL")
    import_courses_and_topics(connection, snapshots["courses.json"], imported_at=STAMP)
    import_assessments_and_topics(connection, snapshots["assessments.json"], imported_at=STAMP)
    import_grades_and_academic_calendar(
        connection,
        snapshots["semester_grade_config.json"],
        snapshots["assessments.json"],
        imported_at=STAMP,
    )
    legacy = LegacyJsonGradeCalendarRepository(
        grade_config_path=data / "semester_grade_config.json",
        assessments_path=data / "assessments.json",
    )
    return data, snapshots, connection, legacy


def _dual(connection, legacy, sink=None):
    return build_grade_calendar_repository(
        "dual_read",
        legacy_repository=legacy,
        sqlite_connection=connection,
        diagnostic_sink=sink,
    )


def test_backend_config_accepts_only_legacy_or_dual_read():
    assert GradeCalendarBackendConfig("legacy").mode == "legacy"
    assert GradeCalendarBackendConfig("dual-read").mode == "dual_read"
    with pytest.raises(ValueError):
        GradeCalendarBackendConfig("sqlite")


def test_legacy_mode_preserves_grade_config(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        repository = build_grade_calendar_repository("legacy", legacy_repository=legacy)
        assert repository.load_grade_config() == legacy.load_grade_config()
    finally:
        connection.close()


def test_legacy_mode_preserves_calendar_deadlines(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        repository = build_grade_calendar_repository("legacy", legacy_repository=legacy)
        assert repository.load_calendar_deadlines() == legacy.load_calendar_deadlines()
        assert len(repository.load_calendar_deadlines()) == 2
    finally:
        connection.close()


def test_dual_read_returns_exact_legacy_state_and_parity_passes(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        repository = _dual(connection, legacy)
        expected = legacy.load_state()
        assert repository.load_state() == expected
        assert repository.last_parity_report is not None
        assert repository.last_parity_report.is_semantically_equal
    finally:
        connection.close()


def test_grade_scale_mismatch_is_reported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        connection.execute("UPDATE grade_bands SET grade_point_milli = 8000 WHERE letter_grade = 'A'")
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert repository.last_parity_report.mismatch_count > 0
        assert any(item.key == "grade_scale.bands" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_target_sgpa_mismatch_is_reported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        connection.execute("UPDATE semester_grade_settings SET target_sgpa_milli = 9000")
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any(item.key == "semester.target_sgpa" and item.status == "mismatch" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_course_credit_mismatch_is_reported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        course_id = connection.execute("SELECT id FROM courses WHERE code = 'MA103N'").fetchone()[0]
        connection.execute("UPDATE semester_courses SET credits_milli = 5000 WHERE course_id = ?", (course_id,))
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any(item.key.endswith(":credits") and item.status == "mismatch" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_manual_grade_mismatch_is_reported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        connection.execute("UPDATE manual_grade_entries SET grade_point_milli = 8000")
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any("manual:grade_point_milli" in item.key and item.status == "mismatch" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_semester_result_mismatch_is_reported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        connection.execute("UPDATE semester_results SET sgpa_milli = 8000")
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any(item.key == "semester_result.sgpa_milli" and item.status == "mismatch" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_calendar_title_mismatch_is_reported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        connection.execute("UPDATE academic_events SET title = 'Wrong title' WHERE deleted_at IS NULL")
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any(item.domain == "academic_calendar" and item.key.endswith(":title") and item.status == "mismatch" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_calendar_timestamp_mismatch_is_reported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        connection.execute("UPDATE academic_events SET starts_at = '2099-12-31' WHERE deleted_at IS NULL")
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any(item.key.endswith(":starts_at") and item.status == "mismatch" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_wrong_calendar_course_relationship_is_detected(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        courses = connection.execute("SELECT id FROM courses ORDER BY code").fetchall()
        event = connection.execute("SELECT id, course_id FROM academic_events ORDER BY id LIMIT 1").fetchone()
        other = next(row[0] for row in courses if row[0] != event[1])
        connection.execute("UPDATE academic_events SET course_id = ? WHERE id = ?", (other, event[0]))
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any(item.key == "academic_event_wrong_course" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_missing_calendar_target_is_detected(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        connection.execute("DELETE FROM academic_events")
        connection.commit()
        repository = _dual(connection, legacy)
        repository.load_state()
        assert any(item.key == "missing_academic_event_target" for item in repository.last_parity_report.diagnostics)
    finally:
        connection.close()


def test_absent_optional_grade_config_is_supported(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path, include_grade=False)
    try:
        repository = _dual(connection, legacy)
        state = repository.load_state()
        assert state["grade_source_present"] is False
        assert repository.last_parity_report.is_semantically_equal
    finally:
        connection.close()


def test_sqlite_read_failure_never_replaces_legacy_result(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)

    class BrokenShadow:
        def load_state(self, **kwargs):
            raise RuntimeError("synthetic shadow failure")

    repository = DualReadGradeCalendarRepository(legacy, BrokenShadow())
    expected = legacy.load_state()
    assert repository.load_state() == expected
    assert repository.last_parity_report.status == "mismatch"
    connection.close()


def test_diagnostic_sink_failure_never_breaks_legacy_read(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        def sink(_):
            raise RuntimeError("sink failed")

        repository = _dual(connection, legacy, sink=sink)
        assert repository.load_state() == legacy.load_state()
        assert repository.last_parity_report is not None
    finally:
        connection.close()


def test_sqlite_mutations_fail_explicitly(tmp_path):
    _, _, connection, _ = _prepared(tmp_path)
    try:
        repository = SQLiteGradeCalendarRepository(connection)
        with pytest.raises(SQLiteGradeCalendarRepositoryReadOnlyError):
            repository.save_grade_config({})
        with pytest.raises(SQLiteGradeCalendarRepositoryReadOnlyError):
            repository.save_state({})
    finally:
        connection.close()


def test_schema_validation_rejects_incomplete_database():
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE migration_imports (id TEXT)")
        with pytest.raises(SQLiteGradeCalendarRepositorySchemaError):
            SQLiteGradeCalendarRepository(connection)
    finally:
        connection.close()


def test_dual_read_changes_zero_legacy_bytes_and_zero_sqlite_state(tmp_path):
    data, _, connection, legacy = _prepared(tmp_path)
    paths = [data / "courses.json", data / "assessments.json", data / "semester_grade_config.json"]
    before_hashes = [_sha(path) for path in paths]
    before_rows = {
        table: connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        for table in (
            "grade_scales", "grade_bands", "semester_grade_settings",
            "semester_courses", "manual_grade_entries", "semester_results", "academic_events",
        )
    }
    before_changes = connection.total_changes
    repository = _dual(connection, legacy)
    repository.load_state()
    repository.load_state()
    assert [_sha(path) for path in paths] == before_hashes
    assert connection.total_changes == before_changes
    for table, rows in before_rows.items():
        assert connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() == rows
    connection.close()


def test_repeated_dual_reads_are_deterministic(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        repository = _dual(connection, legacy)
        first = repository.load_state()
        first_report = repository.last_parity_report.to_dict()
        second = repository.load_state()
        second_report = repository.last_parity_report.to_dict()
        assert first == second
        assert first_report == second_report
    finally:
        connection.close()


def test_integrity_and_foreign_keys_remain_clean(tmp_path):
    _, _, connection, legacy = _prepared(tmp_path)
    try:
        before = connection.total_changes
        _dual(connection, legacy).load_state()
        assert connection.total_changes == before
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_dual_read_save_remains_legacy_only(tmp_path):
    data, _, connection, legacy = _prepared(tmp_path)
    try:
        before_changes = connection.total_changes
        repository = _dual(connection, legacy)
        config = legacy.load_grade_config()
        config["target_sgpa"] = 9.0
        saved = repository.save_grade_config(config)
        assert saved["target_sgpa"] == 9.0
        assert json.loads((data / "semester_grade_config.json").read_text(encoding="utf-8"))["target_sgpa"] == 9.0
        assert connection.total_changes == before_changes
    finally:
        connection.close()
