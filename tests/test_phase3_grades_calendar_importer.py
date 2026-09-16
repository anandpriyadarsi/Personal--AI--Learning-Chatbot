from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
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
    import_grades_calendar,
    render_grade_calendar_import_review_markdown,
)
from personal_learning_assistant.migration.legacy_json_import import (
    LegacyImportDataError,
    LegacyImportError,
    LegacySourceChangedError,
)
from personal_learning_assistant.migration.legacy_source_scanner import (
    LegacySourceSpec,
    scan_legacy_sources,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP_1 = "2026-09-14T10:00:00Z"
STAMP_2 = "2026-09-14T10:30:00Z"


def _grade_config():
    return {
        "version": 1,
        "semester_name": "Semester 1",
        "target_sgpa": 8.5,
        "grade_scale": [
            {"letter": "A", "min_score": 80, "grade_point": 9},
            {"letter": "B", "min_score": 60, "grade_point": 7},
            {"letter": "F", "min_score": 0, "grade_point": 0},
        ],
        "courses": [
            {
                "course_id": "fixture-ma103n",
                "credits": 4,
                "manual_grade_point": 9,
                "manual_letter_grade": "A",
            }
        ],
        "semester_result": {
            "earned_credits": 4,
            "earned_grade_points": 36,
            "sgpa": 9,
            "verified": False,
            "source": "synthetic fixture",
            "recorded_at": "2026-09-14T09:05:00Z",
        },
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _scan(data_dir: Path):
    snapshots = scan_legacy_sources(
        data_dir,
        specs=(
            LegacySourceSpec("courses.json"),
            LegacySourceSpec("assessments.json"),
            LegacySourceSpec("semester_grade_config.json", required=False),
        ),
    ).sources
    return {Path(item.canonical_path).name: item for item in snapshots}


def _prepare_sources(
    tmp_path: Path,
    *,
    grade_present: bool = True,
    grade_data=None,
    assessment_data=None,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "courses.json").write_bytes(
        (FIXTURES / "courses.json").read_bytes()
    )
    if assessment_data is None:
        (data_dir / "assessments.json").write_bytes(
            (FIXTURES / "assessments.json").read_bytes()
        )
    else:
        _write_json(data_dir / "assessments.json", assessment_data)
    if grade_present:
        _write_json(
            data_dir / "semester_grade_config.json",
            _grade_config() if grade_data is None else grade_data,
        )
    return data_dir, _scan(data_dir)


def _connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "shadow.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    return connect_database(database_path, synchronous="FULL")


def _prepared_database(
    tmp_path: Path,
    *,
    grade_present: bool = True,
    grade_data=None,
    assessment_data=None,
    import_assessments: bool = True,
):
    data_dir, snapshots = _prepare_sources(
        tmp_path,
        grade_present=grade_present,
        grade_data=grade_data,
        assessment_data=assessment_data,
    )
    connection = _connection(tmp_path)
    import_courses_and_topics(
        connection,
        snapshots["courses.json"],
        imported_at=STAMP_1,
    )
    if import_assessments:
        import_assessments_and_topics(
            connection,
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
    return data_dir, snapshots, connection


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])


def test_grade_config_and_assessment_deadline_import_without_touching_sources(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    paths = tuple(
        data_dir / name
        for name in (
            "courses.json",
            "assessments.json",
            "semester_grade_config.json",
        )
    )
    before = tuple(_sha256(path) for path in paths)

    try:
        result = import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )

        assert result.grade_scales.created == 1
        assert result.grade_bands.created == 3
        assert result.semester_grade_settings.created == 1
        assert result.semester_course_credits.updated == 1
        assert result.manual_grade_entries.created == 1
        assert result.semester_results.created == 1
        assert result.academic_events.created == 1
        assert result.assessments_without_due_date == 0
        assert result.optional_sources_absent == ()
        assert result.review_required_items == 0
        assert result.changed_rows == 9

        scale = connection.execute(
            "SELECT id, name, source, verified FROM grade_scales"
        ).fetchone()
        assert str(uuid.UUID(scale[0])) == scale[0]
        assert "Legacy Planning Grade Scale" in scale[1]
        assert scale[2] == "legacy_json:data/semester_grade_config.json"
        assert scale[3] == 0

        bands = connection.execute(
            "SELECT minimum_bps, letter_grade, grade_point_milli "
            "FROM grade_bands ORDER BY minimum_bps DESC"
        ).fetchall()
        assert [tuple(row) for row in bands] == [
            (8000, "A", 9000),
            (6000, "B", 7000),
            (0, "F", 0),
        ]

        settings = connection.execute(
            "SELECT scale_id, target_sgpa_milli FROM semester_grade_settings"
        ).fetchone()
        assert tuple(settings) == (scale[0], 8500)
        course_credit = connection.execute(
            "SELECT credits_milli FROM semester_courses AS sc "
            "JOIN courses AS c ON c.id = sc.course_id WHERE c.code = 'MA103N'"
        ).fetchone()[0]
        assert course_credit == 4000

        manual = connection.execute(
            "SELECT score_bps, letter_grade, grade_point_milli, entry_kind "
            "FROM manual_grade_entries"
        ).fetchone()
        assert tuple(manual) == (None, "A", 9000, "legacy_manual_override")
        semester_result = connection.execute(
            "SELECT earned_credits_milli, earned_grade_points_milli, "
            "sgpa_milli, verified, source FROM semester_results"
        ).fetchone()
        assert tuple(semester_result) == (
            4000,
            36000,
            9000,
            0,
            "synthetic fixture",
        )

        event = connection.execute(
            "SELECT event_kind, title, starts_at, all_day, reference_type, "
            "reference_id, source_entity_type, source_entity_id, deleted_at "
            "FROM academic_events"
        ).fetchone()
        assert tuple(event) == (
            "assessment_deadline",
            "Synthetic Quiz",
            "2099-01-15",
            1,
            "assessment",
            event[5],
            "assessment",
            event[5],
            None,
        )

        report = render_grade_calendar_import_review_markdown(result)
        assert "# Grades and Academic Calendar Import Review" in report
        assert "absent/not configured: none" in report
        assert str(tmp_path) not in report
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    assert tuple(_sha256(path) for path in paths) == before


def test_identical_reimport_is_noop_and_alias_works(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path)
    try:
        first = import_grades_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        original = connection.execute(
            "SELECT id, updated_at FROM academic_events"
        ).fetchone()
        second = import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_2,
        )

        assert first.changed_rows == 9
        assert second.changed_rows == 0
        assert second.grade_scales.matched == 1
        assert second.grade_bands.matched == 3
        assert second.semester_grade_settings.matched == 1
        assert second.semester_course_credits.matched == 1
        assert second.manual_grade_entries.matched == 1
        assert second.semester_results.matched == 1
        assert second.academic_events.matched == 1
        assert _count(connection, "grade_scales") == 1
        assert _count(connection, "grade_bands") == 3
        assert _count(connection, "manual_grade_entries") == 1
        assert _count(connection, "academic_events") == 1
        assert connection.execute(
            "SELECT id, updated_at FROM academic_events"
        ).fetchone() == original
    finally:
        connection.close()


def test_absent_optional_grade_config_is_not_an_error(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path, grade_present=False)
    try:
        result = import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )

        assert result.optional_sources_absent == (
            "data/semester_grade_config.json",
        )
        assert result.grade_scales.total == 0
        assert result.grade_bands.total == 0
        assert result.semester_grade_settings.total == 0
        assert result.academic_events.created == 1
        assert any(
            issue.code == "grade_configuration_absent" for issue in result.issues
        )
        report = render_grade_calendar_import_review_markdown(result)
        assert "data/semester_grade_config.json" in report
        assert "absent/not configured" in report
    finally:
        connection.close()


def test_changed_assessment_hash_updates_same_linked_calendar_event(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    try:
        first = import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        assert first.academic_events.created == 1
        old_event = connection.execute(
            "SELECT id, starts_at FROM academic_events"
        ).fetchone()
        old_hash = snapshots["assessments.json"].source_hash

        assessment_path = data_dir / "assessments.json"
        data = json.loads(assessment_path.read_text(encoding="utf-8"))
        data["assessments"][0]["title"] = "Synthetic Quiz — Revised"
        data["assessments"][0]["due_date"] = "2099-01-20"
        data["assessments"][0]["due_time"] = "14:30"
        _write_json(assessment_path, data)
        changed = _scan(data_dir)
        import_assessments_and_topics(
            connection,
            changed["assessments.json"],
            imported_at=STAMP_2,
        )

        result = import_grades_and_academic_calendar(
            connection,
            changed["semester_grade_config.json"],
            changed["assessments.json"],
            imported_at=STAMP_2,
        )
        event = connection.execute(
            "SELECT id, title, starts_at, all_day FROM academic_events"
        ).fetchone()
        assert result.academic_events.updated == 1
        assert event[0] == old_event[0]
        assert tuple(event[1:]) == (
            "Synthetic Quiz — Revised",
            "2099-01-20T14:30",
            0,
        )
        hashes = {
            row[0]
            for row in connection.execute(
                "SELECT source_hash FROM migration_imports "
                "WHERE target_table = 'academic_events'"
            ).fetchall()
        }
        assert old_hash in hashes
        assert changed["assessments.json"].source_hash in hashes
        assert _count(connection, "academic_events") == 1
    finally:
        connection.close()


def test_changed_grade_config_versions_scale_and_preserves_manual_history(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    try:
        import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        old_scale_id = connection.execute(
            "SELECT scale_id FROM semester_grade_settings"
        ).fetchone()[0]

        grade_path = data_dir / "semester_grade_config.json"
        data = json.loads(grade_path.read_text(encoding="utf-8"))
        data["target_sgpa"] = 8.75
        data["grade_scale"][0]["min_score"] = 82
        data["courses"][0]["manual_grade_point"] = 8
        data["courses"][0]["manual_letter_grade"] = "B+"
        _write_json(grade_path, data)
        changed = _scan(data_dir)

        result = import_grades_and_academic_calendar(
            connection,
            changed["semester_grade_config.json"],
            changed["assessments.json"],
            imported_at=STAMP_2,
        )
        settings = connection.execute(
            "SELECT scale_id, target_sgpa_milli FROM semester_grade_settings"
        ).fetchone()
        assert result.grade_scales.created == 1
        assert result.grade_bands.created == 3
        assert result.semester_grade_settings.updated == 1
        assert settings[0] != old_scale_id
        assert settings[1] == 8750
        assert _count(connection, "grade_scales") == 2
        assert _count(connection, "grade_bands") == 6
        assert _count(connection, "manual_grade_entries") == 2
        manual_rows = connection.execute(
            "SELECT letter_grade, grade_point_milli FROM manual_grade_entries "
            "ORDER BY recorded_at, letter_grade"
        ).fetchall()
        assert {tuple(row) for row in manual_rows} == {("A", 9000), ("B+", 8000)}
    finally:
        connection.close()


def test_unresolved_grade_course_is_reported_without_guessing(tmp_path):
    config = _grade_config()
    config["courses"][0]["course_id"] = "missing-course"
    _, snapshots, connection = _prepared_database(tmp_path, grade_data=config)
    try:
        result = import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        assert result.semester_course_credits.total == 0
        assert result.manual_grade_entries.total == 0
        assert result.review_required_items == 1
        assert result.review_items[0].reason == "unresolved_course_reference"
        assert _count(connection, "manual_grade_entries") == 0
        assert result.academic_events.created == 1
    finally:
        connection.close()


def test_assessment_without_due_date_creates_no_calendar_event(tmp_path):
    assessment_data = json.loads(
        (FIXTURES / "assessments.json").read_text(encoding="utf-8")
    )
    assessment_data["assessments"][0]["due_date"] = None
    _, snapshots, connection = _prepared_database(
        tmp_path,
        assessment_data=assessment_data,
    )
    try:
        result = import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        assert result.academic_events.total == 0
        assert result.assessments_without_due_date == 1
        assert _count(connection, "academic_events") == 0
    finally:
        connection.close()


def test_removed_due_date_soft_deletes_previously_projected_event(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    try:
        import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        event_id = connection.execute("SELECT id FROM academic_events").fetchone()[0]

        assessment_path = data_dir / "assessments.json"
        data = json.loads(assessment_path.read_text(encoding="utf-8"))
        data["assessments"][0]["due_date"] = None
        _write_json(assessment_path, data)
        changed = _scan(data_dir)
        import_assessments_and_topics(
            connection,
            changed["assessments.json"],
            imported_at=STAMP_2,
        )

        result = import_grades_and_academic_calendar(
            connection,
            changed["semester_grade_config.json"],
            changed["assessments.json"],
            imported_at=STAMP_2,
        )
        event = connection.execute(
            "SELECT id, status, deleted_at FROM academic_events"
        ).fetchone()
        assert result.academic_events.updated == 1
        assert result.assessments_without_due_date == 1
        assert tuple(event) == (event_id, "cancelled", STAMP_2)
    finally:
        connection.close()


def test_optional_grade_file_appearing_after_missing_scan_is_rejected(tmp_path):
    data_dir, snapshots, connection = _prepared_database(
        tmp_path,
        grade_present=False,
    )
    _write_json(data_dir / "semester_grade_config.json", _grade_config())
    try:
        with pytest.raises(LegacySourceChangedError, match="appeared after scan"):
            import_grades_and_academic_calendar(
                connection,
                snapshots["semester_grade_config.json"],
                snapshots["assessments.json"],
                imported_at=STAMP_1,
            )
        assert _count(connection, "grade_scales") == 0
        assert _count(connection, "academic_events") == 0
    finally:
        connection.close()


def test_malformed_grade_config_fails_without_partial_writes(tmp_path):
    bad = _grade_config()
    bad["grade_scale"] = {"not": "an array"}
    _, snapshots, connection = _prepared_database(tmp_path, grade_data=bad)
    try:
        with pytest.raises(LegacyImportDataError):
            import_grades_and_academic_calendar(
                connection,
                snapshots["semester_grade_config.json"],
                snapshots["assessments.json"],
                imported_at=STAMP_1,
            )
        assert _count(connection, "grade_scales") == 0
        assert _count(connection, "academic_events") == 0
    finally:
        connection.close()


def test_assessment_fix5_precondition_is_enforced_before_grade_writes(tmp_path):
    _, snapshots, connection = _prepared_database(
        tmp_path,
        import_assessments=False,
    )
    try:
        with pytest.raises(LegacyImportError, match="Fix 5"):
            import_grades_and_academic_calendar(
                connection,
                snapshots["semester_grade_config.json"],
                snapshots["assessments.json"],
                imported_at=STAMP_1,
            )
        assert _count(connection, "grade_scales") == 0
        assert _count(connection, "academic_events") == 0
    finally:
        connection.close()


def test_source_changed_after_scan_is_rejected_before_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    grade_path = data_dir / "semester_grade_config.json"
    data = json.loads(grade_path.read_text(encoding="utf-8"))
    data["target_sgpa"] = 9.5
    _write_json(grade_path, data)
    try:
        with pytest.raises(LegacySourceChangedError):
            import_grades_and_academic_calendar(
                connection,
                snapshots["semester_grade_config.json"],
                snapshots["assessments.json"],
                imported_at=STAMP_1,
            )
        assert _count(connection, "grade_scales") == 0
        assert _count(connection, "academic_events") == 0
    finally:
        connection.close()
