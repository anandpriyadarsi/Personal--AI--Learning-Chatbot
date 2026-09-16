from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.assessments_topics_importer import (
    import_assessments_and_topics,
)
from personal_learning_assistant.migration.attempts_performance_importer import (
    import_assessment_performance,
    import_attempts_mistakes_and_performance,
    render_attempt_performance_review_markdown,
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
from personal_learning_assistant.migration.questions_sources_importer import (
    import_questions_and_sources,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP_1 = "2026-09-14T06:00:00Z"
STAMP_2 = "2026-09-14T06:15:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_sources(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    filenames = (
        "courses.json",
        "assessments.json",
        "assessment_workspace.json",
    )
    for name in filenames:
        (data_dir / name).write_bytes((FIXTURES / name).read_bytes())

    snapshots = scan_legacy_sources(
        data_dir,
        specs=tuple(LegacySourceSpec(name) for name in filenames),
    ).sources
    return data_dir, {Path(item.canonical_path).name: item for item in snapshots}


def _rescan(data_dir: Path, filename: str = "assessment_workspace.json"):
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
    import_assessments_and_topics(
        connection,
        snapshots["assessments.json"],
        imported_at=STAMP_1,
    )
    import_questions_and_sources(
        connection,
        snapshots["assessment_workspace.json"],
        imported_at=STAMP_1,
    )
    return data_dir, snapshots, connection


def _workspace_data(data_dir: Path):
    path = data_dir / "assessment_workspace.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _write_workspace(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])


def _add_attempt_evidence(data_dir: Path) -> Path:
    path, data = _workspace_data(data_dir)
    questions = data["workspaces"]["fixture-assessment-1"]["questions"]
    questions[0]["performance"] = {
        "attempts": [
            {
                "time": "2026-09-14T06:01:00",
                "outcome": "correct",
                "weight": 1.0,
                "earned_marks": 2,
                "max_marks": 2,
                "mistake": "",
            },
            {
                "time": "2026-09-14T06:05:00",
                "outcome": "partially correct",
                "weight": 0.5,
                "earned_marks": 1,
                "max_marks": 2,
                "mistake": "Forgot one row operation.",
            },
        ],
        "mistakes": [
            {
                "time": "2026-09-14T06:05:30",
                "text": "Standalone duplicate note kept for review only.",
            }
        ],
    }
    questions[1]["attempts"] = [
        {
            "time": "2026-09-14T06:08:00",
            "outcome": "wrong",
            "earned_marks": 0,
            "max_marks": 3,
            "mistake": "Used wrong pivot.",
        }
    ]
    _write_workspace(path, data)
    return path


def test_empty_attempt_snapshot_imports_no_rows_without_touching_files(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    source = data_dir / "assessment_workspace.json"
    before = _sha256(source)

    try:
        result = import_attempts_mistakes_and_performance(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_1,
        )

        assert result.questions_scanned == 2
        assert result.questions_with_attempts == 0
        assert result.total_attempts == 0
        assert result.total_mistakes == 0
        assert result.attempts.total == 0
        assert result.mistake_events.total == 0
        assert result.changed_rows == 0
        assert result.attempt_accuracy == 0.0
        assert result.marks_accuracy is None
        assert _table_count(connection, "question_attempts") == 0
        assert _table_count(connection, "mistake_events") == 0

        report = render_attempt_performance_review_markdown(result)
        assert "# Attempt / Mistake Performance Import Review" in report
        assert "No attempt evidence was present" in report
        assert str(tmp_path) not in report
    finally:
        connection.close()

    assert _sha256(source) == before


def test_attempts_and_mistakes_import_with_marks_and_outcomes(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    source = _add_attempt_evidence(data_dir)
    snapshot = _rescan(data_dir)
    before = _sha256(source)

    # Fix 6 must be run against the changed workspace hash before Fix 8.
    import_questions_and_sources(connection, snapshot, imported_at=STAMP_2)

    try:
        result = import_assessment_performance(
            connection,
            snapshot,
            imported_at=STAMP_2,
        )

        assert result.questions_scanned == 2
        assert result.questions_with_attempts == 2
        assert result.attempts.created == 3
        assert result.mistake_events.created == 2
        assert result.total_attempts == 3
        assert result.total_mistakes == 2
        assert result.outcome_counts["correct"] == 1
        assert result.outcome_counts["partially_correct"] == 1
        assert result.outcome_counts["wrong"] == 1
        assert result.marks_evidence_attempts == 3
        assert result.earned_marks_milli == 3000
        assert result.max_marks_milli == 7000
        assert result.deferred_mistakes == 1

        attempts = connection.execute(
            "SELECT attempt_number, outcome, earned_marks_milli, "
            "max_marks_milli FROM question_attempts ORDER BY occurred_at"
        ).fetchall()
        assert [row[0] for row in attempts] == [1, 2, 1]
        assert [row[1] for row in attempts] == [
            "correct",
            "partially_correct",
            "wrong",
        ]
        assert [row[2] for row in attempts] == [2000, 1000, 0]
        assert [row[3] for row in attempts] == [2000, 2000, 3000]

        mistakes = connection.execute(
            "SELECT category, mistake_text FROM mistake_events "
            "ORDER BY created_at, mistake_text"
        ).fetchall()
        assert [row[0] for row in mistakes] == [
            "legacy_attempt_mistake",
            "legacy_attempt_mistake",
        ]
        assert {row[1] for row in mistakes} == {
            "Forgot one row operation.",
            "Used wrong pivot.",
        }

        ledger_tables = [
            row[0]
            for row in connection.execute(
                "SELECT target_table FROM migration_imports "
                "WHERE source_path = 'data/assessment_workspace.json' "
                "ORDER BY target_table"
            ).fetchall()
        ]
        assert ledger_tables.count("question_attempts") == 3
        assert ledger_tables.count("mistake_events") == 2

        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    assert _sha256(source) == before


def test_identical_reimport_is_a_noop(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    _add_attempt_evidence(data_dir)
    snapshot = _rescan(data_dir)
    import_questions_and_sources(connection, snapshot, imported_at=STAMP_2)

    try:
        first = import_attempts_mistakes_and_performance(
            connection,
            snapshot,
            imported_at=STAMP_1,
        )
        original_rows = connection.execute(
            "SELECT id, occurred_at FROM question_attempts ORDER BY id"
        ).fetchall()

        second = import_attempts_mistakes_and_performance(
            connection,
            snapshot,
            imported_at=STAMP_2,
        )

        assert first.changed_rows == 5
        assert second.changed_rows == 0
        assert second.attempts.matched == 3
        assert second.mistake_events.matched == 2
        assert _table_count(connection, "question_attempts") == 3
        assert _table_count(connection, "mistake_events") == 2
        assert connection.execute(
            "SELECT id, occurred_at FROM question_attempts ORDER BY id"
        ).fetchall() == original_rows
    finally:
        connection.close()


def test_changed_workspace_requires_question_import_for_exact_hash(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    _add_attempt_evidence(data_dir)
    changed_snapshot = _rescan(data_dir)

    try:
        with pytest.raises(LegacyImportDataError):
            import_attempts_mistakes_and_performance(
                connection,
                changed_snapshot,
                imported_at=STAMP_2,
            )
    finally:
        connection.close()


def test_changed_hash_updates_stable_attempt_targets_after_question_reimport(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    _add_attempt_evidence(data_dir)
    first_snapshot = _rescan(data_dir)
    import_questions_and_sources(connection, first_snapshot, imported_at=STAMP_1)
    first = import_attempts_mistakes_and_performance(
        connection,
        first_snapshot,
        imported_at=STAMP_1,
    )

    path, data = _workspace_data(data_dir)
    first_attempt = data["workspaces"]["fixture-assessment-1"]["questions"][0][
        "performance"
    ]["attempts"][0]
    first_attempt["earned_marks"] = 1.5
    _write_workspace(path, data)

    second_snapshot = _rescan(data_dir)
    assert second_snapshot.source_hash != first_snapshot.source_hash
    import_questions_and_sources(connection, second_snapshot, imported_at=STAMP_2)

    try:
        second = import_attempts_mistakes_and_performance(
            connection,
            second_snapshot,
            imported_at=STAMP_2,
        )

        assert first.attempts.created == 3
        assert second.attempts.updated == 3
        assert _table_count(connection, "question_attempts") == 3
        assert _table_count(connection, "mistake_events") == 2
        earned = connection.execute(
            "SELECT earned_marks_milli FROM question_attempts "
            "ORDER BY occurred_at LIMIT 1"
        ).fetchone()[0]
        assert earned == 1500

        hashes = {
            row[0]
            for row in connection.execute(
                "SELECT source_hash FROM migration_imports "
                "WHERE target_table = 'question_attempts'"
            ).fetchall()
        }
        assert hashes == {first_snapshot.source_hash, second_snapshot.source_hash}
    finally:
        connection.close()


def test_invalid_marks_do_not_break_constraints(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    question = data["workspaces"]["fixture-assessment-1"]["questions"][0]
    question["performance"] = {
        "attempts": [
            {
                "time": "2026-09-14T07:00:00",
                "outcome": "unknown strange value",
                "earned_marks": 10,
                "max_marks": 2,
                "mistake": {"bad": "shape"},
            }
        ]
    }
    _write_workspace(path, data)
    snapshot = _rescan(data_dir)
    import_questions_and_sources(connection, snapshot, imported_at=STAMP_2)

    try:
        result = import_attempts_mistakes_and_performance(
            connection,
            snapshot,
            imported_at=STAMP_2,
        )

        assert result.attempts.created == 1
        assert result.mistake_events.total == 0
        assert result.outcome_counts["unknown"] == 1
        row = connection.execute(
            "SELECT outcome, earned_marks_milli, max_marks_milli "
            "FROM question_attempts"
        ).fetchone()
        assert row[0] == "unknown"
        assert row[1] is None
        assert row[2] == 2000

        issue_codes = {issue.code for issue in result.issues}
        assert "unknown_attempt_outcome" in issue_codes
        assert "earned_marks_exceed_max" in issue_codes
        assert "invalid_attempt_mistake" in issue_codes
    finally:
        connection.close()


def test_source_change_after_scan_is_rejected_before_writes(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    _add_attempt_evidence(data_dir)
    snapshot = _rescan(data_dir)
    import_questions_and_sources(connection, snapshot, imported_at=STAMP_1)

    path, data = _workspace_data(data_dir)
    data["workspaces"]["fixture-assessment-1"]["questions"][0]["performance"][
        "attempts"
    ][0]["outcome"] = "wrong"
    _write_workspace(path, data)

    try:
        with pytest.raises(LegacySourceChangedError):
            import_attempts_mistakes_and_performance(
                connection,
                snapshot,
                imported_at=STAMP_2,
            )
        assert _table_count(connection, "question_attempts") == 0
        assert _table_count(connection, "mistake_events") == 0
    finally:
        connection.close()
