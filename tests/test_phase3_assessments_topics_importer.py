from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from personal_learning_assistant.migration.assessments_topics_importer import (
    import_assessments_and_topics,
    render_assessment_topic_review_markdown,
)
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
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP_1 = "2026-09-14T03:00:00Z"
STAMP_2 = "2026-09-14T03:15:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_sources(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("courses.json", "assessments.json"):
        (data_dir / name).write_bytes((FIXTURES / name).read_bytes())

    snapshots = scan_legacy_sources(
        data_dir,
        specs=(
            LegacySourceSpec("courses.json"),
            LegacySourceSpec("assessments.json"),
        ),
    ).sources
    return data_dir, {Path(item.canonical_path).name: item for item in snapshots}


def _rescan(data_dir: Path, filename: str):
    return scan_legacy_sources(
        data_dir,
        specs=(LegacySourceSpec(filename),),
    ).sources[0]


def _connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "shadow.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    return connect_database(database_path, synchronous="FULL")


def _prepared_database(tmp_path: Path):
    data_dir, snapshots = _prepare_sources(tmp_path)
    connection = _connection(tmp_path)
    import_courses_and_topics(
        connection,
        snapshots["courses.json"],
        imported_at=STAMP_1,
    )
    return data_dir, snapshots, connection


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])


def _assessment_data(data_dir: Path):
    path = data_dir / "assessments.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _write_assessment_data(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def test_assessments_topics_imports_fixture_without_touching_sources(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    course_path = data_dir / "courses.json"
    assessment_path = data_dir / "assessments.json"
    before = (_sha256(course_path), _sha256(assessment_path))

    try:
        result = import_assessments_and_topics(
            connection,
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )

        assert result.assessments.created == 1
        assert result.assessment_topics.created == 2
        assert result.changed_rows == 3
        assert result.review_required_topics == 2
        assert result.unresolved_topics == 2
        assert result.deferred_course_credits == 0

        assert _table_count(connection, "assessments") == 1
        assert _table_count(connection, "assessment_topics") == 2
        assert _table_count(connection, "migration_imports") == 10

        assessment = connection.execute(
            "SELECT a.id, c.code, a.assessment_type, a.title, a.due_on, "
            "a.due_time, a.status, a.weight_bps, a.max_points_milli, "
            "a.earned_points_milli, a.description "
            "FROM assessments AS a JOIN courses AS c ON c.id = a.course_id"
        ).fetchone()
        assert str(uuid.UUID(assessment[0])) == assessment[0]
        assert tuple(assessment[1:]) == (
            "MA103N",
            "quiz",
            "Synthetic Quiz",
            "2099-01-15",
            None,
            "pending",
            None,
            None,
            None,
            "",
        )

        topic_rows = connection.execute(
            "SELECT id, topic_id, raw_label, source, confidence "
            "FROM assessment_topics ORDER BY raw_label"
        ).fetchall()
        assert [row[2] for row in topic_rows] == [
            "Linear Systems",
            "Row Reduction",
        ]
        for row in topic_rows:
            assert str(uuid.UUID(row[0])) == row[0]
            assert row[1] is None
            assert row[3] == "legacy_json:data/assessments.json"
            assert row[4] is None

        # Even an exact name match stays unresolved until a review decision.
        exact_match = connection.execute(
            "SELECT topic_id FROM assessment_topics WHERE raw_label = ?",
            ("Linear Systems",),
        ).fetchone()
        assert exact_match[0] is None

        issue_codes = [issue.code for issue in result.issues]
        assert issue_codes.count("assessment_topic_review_required") == 2

        report = render_assessment_topic_review_markdown(result)
        assert "# Assessment Topic Review" in report
        assert "Review-required labels: 2" in report
        assert "Linear Systems" in report
        assert str(tmp_path) not in report
    finally:
        connection.close()

    assert (_sha256(course_path), _sha256(assessment_path)) == before


def test_reimport_same_snapshot_is_noop_without_duplicate_rows(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path)

    try:
        first = import_assessments_and_topics(
            connection,
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        assert first.changed_rows == 3
        original_updated_at = connection.execute(
            "SELECT updated_at FROM assessments"
        ).fetchone()[0]

        second = import_assessments_and_topics(
            connection,
            snapshots["assessments.json"],
            imported_at=STAMP_2,
        )

        assert second.changed_rows == 0
        assert second.assessments.matched == 1
        assert second.assessment_topics.matched == 2
        assert second.review_required_topics == 2
        assert _table_count(connection, "assessments") == 1
        assert _table_count(connection, "assessment_topics") == 2
        assert _table_count(connection, "migration_imports") == 10
        assert connection.execute(
            "SELECT updated_at FROM assessments"
        ).fetchone()[0] == original_updated_at
    finally:
        connection.close()


def test_changed_hash_updates_stable_assessment_and_topic_targets(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)

    try:
        import_assessments_and_topics(
            connection,
            snapshots["assessments.json"],
            imported_at=STAMP_1,
        )
        old_assessment_id = connection.execute(
            "SELECT id FROM assessments"
        ).fetchone()[0]
        old_topic_ids = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT raw_label, id FROM assessment_topics"
            ).fetchall()
        }

        path, data = _assessment_data(data_dir)
        item = data["assessments"][0]
        item["title"] = "Synthetic Quiz Revised"
        item["topics"][0] = "  Linear Systems  "
        item["total_marks"] = 20
        item["obtained_marks"] = 16.5
        item["updated_at"] = STAMP_2
        _write_assessment_data(path, data)
        changed_snapshot = _rescan(data_dir, "assessments.json")

        result = import_assessments_and_topics(
            connection,
            changed_snapshot,
            imported_at=STAMP_2,
        )

        assessment = connection.execute(
            "SELECT id, title, max_points_milli, earned_points_milli "
            "FROM assessments"
        ).fetchone()
        assert tuple(assessment) == (
            old_assessment_id,
            "Synthetic Quiz Revised",
            20000,
            16500,
        )
        changed_topic = connection.execute(
            "SELECT id, raw_label FROM assessment_topics "
            "WHERE raw_label = '  Linear Systems  '"
        ).fetchone()
        assert changed_topic[0] == old_topic_ids["Linear Systems"]
        assert result.assessments.updated == 1
        assert result.assessment_topics.updated == 2
        assert _table_count(connection, "migration_imports") == 13
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("use_legacy_aliases", "expected_issue_count"),
    ((False, 0), (True, 3)),
)
def test_numeric_fields_convert_to_basis_points_and_milli_points(
    tmp_path,
    use_legacy_aliases,
    expected_issue_count,
):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    path, data = _assessment_data(data_dir)
    item = data["assessments"][0]
    item["due_time"] = "09:30"
    item["course_credits"] = 4
    if use_legacy_aliases:
        item["weight"] = 12.5
        item["max_score"] = 20
        item["score"] = 17.25
    else:
        item["weightage_percent"] = 12.5
        item["total_marks"] = 20
        item["obtained_marks"] = 17.25
    _write_assessment_data(path, data)
    snapshot = _rescan(data_dir, "assessments.json")

    try:
        result = import_assessments_and_topics(
            connection,
            snapshot,
            imported_at=STAMP_1,
        )
        row = connection.execute(
            "SELECT due_time, weight_bps, max_points_milli, "
            "earned_points_milli FROM assessments"
        ).fetchone()
        assert tuple(row) == ("09:30", 1250, 20000, 17250)
        assert result.deferred_course_credits == 1
        issue_codes = [issue.code for issue in result.issues]
        assert issue_codes.count("legacy_assessment_field_alias") == (
            expected_issue_count
        )
        assert "assessment_course_credits_deferred" in issue_codes
    finally:
        connection.close()


def test_invalid_optional_values_are_flagged_without_breaking_schema(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _assessment_data(data_dir)
    item = data["assessments"][0]
    item["status"] = "mystery"
    item["due_date"] = "2026-02-30"
    item["due_time"] = "29:90"
    item["weightage_percent"] = 101
    item["total_marks"] = -5
    item["obtained_marks"] = "not-a-number"
    _write_assessment_data(path, data)
    snapshot = _rescan(data_dir, "assessments.json")

    try:
        result = import_assessments_and_topics(
            connection,
            snapshot,
            imported_at=STAMP_1,
        )
        row = connection.execute(
            "SELECT status, due_on, due_time, weight_bps, max_points_milli, "
            "earned_points_milli FROM assessments"
        ).fetchone()
        assert tuple(row) == ("pending", None, None, None, None, None)
        issue_codes = {issue.code for issue in result.issues}
        assert {
            "unknown_assessment_status",
            "invalid_assessment_due_date",
            "invalid_assessment_due_time",
            "out_of_range_assessment_weightage",
            "out_of_range_assessment_total_marks",
            "invalid_assessment_obtained_marks",
        }.issubset(issue_codes)
    finally:
        connection.close()


def test_score_greater_than_total_is_preserved_only_in_ledger_and_flagged(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _assessment_data(data_dir)
    item = data["assessments"][0]
    item["total_marks"] = 10
    item["obtained_marks"] = 12
    _write_assessment_data(path, data)
    snapshot = _rescan(data_dir, "assessments.json")

    try:
        result = import_assessments_and_topics(
            connection,
            snapshot,
            imported_at=STAMP_1,
        )
        row = connection.execute(
            "SELECT max_points_milli, earned_points_milli FROM assessments"
        ).fetchone()
        assert tuple(row) == (10000, None)
        assert "assessment_score_exceeds_total" in {
            issue.code for issue in result.issues
        }
        details = json.loads(
            connection.execute(
                "SELECT details_json FROM migration_imports "
                "WHERE target_table = 'assessments'"
            ).fetchone()[0]
        )
        assert details["raw"]["obtained_marks"] == 12
    finally:
        connection.close()


def test_unresolved_course_mapping_rolls_back_without_assessment_writes(tmp_path):
    data_dir, snapshots = _prepare_sources(tmp_path)
    connection = _connection(tmp_path)

    try:
        with pytest.raises(LegacyImportDataError, match="import courses/topics first"):
            import_assessments_and_topics(
                connection,
                snapshots["assessments.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "assessments") == 0
        assert _table_count(connection, "assessment_topics") == 0
        assert _table_count(connection, "migration_imports") == 0
    finally:
        connection.close()

    assert (data_dir / "assessments.json").exists()


def test_duplicate_assessment_identity_fails_before_any_assessment_write(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _assessment_data(data_dir)
    data["assessments"].append(dict(data["assessments"][0]))
    _write_assessment_data(path, data)
    snapshot = _rescan(data_dir, "assessments.json")

    try:
        with pytest.raises(
            LegacyImportDataError,
            match="duplicate legacy assessment identity",
        ):
            import_assessments_and_topics(
                connection,
                snapshot,
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "assessments") == 0
        assert _table_count(connection, "assessment_topics") == 0
        # Only the prerequisite courses/topics importer ledger remains.
        assert _table_count(connection, "migration_imports") == 7
    finally:
        connection.close()


def test_duplicate_or_non_string_topic_labels_are_not_silently_dropped(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _assessment_data(data_dir)
    data["assessments"][0]["topics"] = ["Linear Systems", " linear systems "]
    _write_assessment_data(path, data)
    snapshot = _rescan(data_dir, "assessments.json")

    try:
        with pytest.raises(LegacyImportDataError, match="duplicate raw topic label"):
            import_assessments_and_topics(
                connection,
                snapshot,
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "assessments") == 0

        data["assessments"][0]["topics"] = ["Linear Systems", {"name": "RREF"}]
        _write_assessment_data(path, data)
        snapshot = _rescan(data_dir, "assessments.json")
        with pytest.raises(LegacyImportDataError, match="must be a string"):
            import_assessments_and_topics(
                connection,
                snapshot,
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "assessments") == 0
    finally:
        connection.close()


def test_conflicting_legacy_numeric_aliases_fail_without_partial_write(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _assessment_data(data_dir)
    data["assessments"][0]["weightage_percent"] = 10
    data["assessments"][0]["weight"] = 20
    _write_assessment_data(path, data)
    snapshot = _rescan(data_dir, "assessments.json")

    try:
        with pytest.raises(LegacyImportDataError, match="conflicting"):
            import_assessments_and_topics(
                connection,
                snapshot,
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "assessments") == 0
        assert _table_count(connection, "assessment_topics") == 0
    finally:
        connection.close()


def test_source_changed_after_scan_is_rejected_without_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    path = data_dir / "assessments.json"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    try:
        with pytest.raises(LegacySourceChangedError):
            import_assessments_and_topics(
                connection,
                snapshots["assessments.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "assessments") == 0
        assert _table_count(connection, "assessment_topics") == 0
    finally:
        connection.close()


def test_malformed_assessment_shape_and_missing_id_fail_without_writes(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path = data_dir / "assessments.json"
    path.write_text(
        json.dumps({"version": 1, "assessments": {"bad": "shape"}}),
        encoding="utf-8",
    )
    snapshot = _rescan(data_dir, "assessments.json")

    try:
        with pytest.raises(LegacyImportDataError, match="must be an array"):
            import_assessments_and_topics(
                connection,
                snapshot,
                imported_at=STAMP_1,
            )

        _, data = _assessment_data(FIXTURES)
        data["assessments"][0].pop("id")
        _write_assessment_data(path, data)
        snapshot = _rescan(data_dir, "assessments.json")
        with pytest.raises(LegacyImportDataError, match="has no id"):
            import_assessments_and_topics(
                connection,
                snapshot,
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "assessments") == 0
        assert _table_count(connection, "assessment_topics") == 0
    finally:
        connection.close()
