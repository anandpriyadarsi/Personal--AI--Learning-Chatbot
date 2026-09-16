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
from personal_learning_assistant.migration.study_plans_importer import (
    import_study_plans,
    import_weekly_multi_intelligent_study_plans,
    render_study_plan_import_review_markdown,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP_1 = "2026-09-14T09:00:00Z"
STAMP_2 = "2026-09-14T09:15:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _prepare_sources(tmp_path: Path, *, include_intelligent: bool = False):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in (
        "courses.json",
        "weekly_study_plans.json",
        "multi_course_weekly_plans.json",
    ):
        (data_dir / name).write_bytes((FIXTURES / name).read_bytes())

    if include_intelligent:
        _write_json(
            data_dir / "intelligent_study_plans.json",
            {
                "version": 1,
                "plans": [
                    {
                        "id": "fixture-v11-week",
                        "kind": "week",
                        "created_at": "2026-01-02T00:00:00",
                        "start_date": "2026-01-02",
                        "study_days": 1,
                        "minutes_per_day": 90,
                        "courses": [
                            {
                                "id": "fixture-ma103n",
                                "code": "MA103N",
                                "name": "Synthetic Linear Algebra",
                            }
                        ],
                        "days": [
                            {
                                "date": "2026-01-02",
                                "available_minutes": 90,
                                "sessions": [
                                    {
                                        "course_id": "fixture-ma103n",
                                        "course_code": "MA103N",
                                        "topic": "Linear Systems",
                                        "status": "weak",
                                        "score": 82.5,
                                        "minutes": 90,
                                        "actions": [
                                            "Repair the weak point",
                                            "Solve two questions",
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )

    filenames = [
        "courses.json",
        "weekly_study_plans.json",
        "multi_course_weekly_plans.json",
        "intelligent_study_plans.json",
    ]
    snapshots = scan_legacy_sources(
        data_dir,
        specs=tuple(
            LegacySourceSpec(
                name,
                required=name != "intelligent_study_plans.json",
            )
            for name in filenames
        ),
    ).sources
    return data_dir, {Path(item.canonical_path).name: item for item in snapshots}


def _rescan(data_dir: Path, *filenames: str):
    snapshots = scan_legacy_sources(
        data_dir,
        specs=tuple(
            LegacySourceSpec(
                name,
                required=name != "intelligent_study_plans.json",
            )
            for name in filenames
        ),
    ).sources
    return {Path(item.canonical_path).name: item for item in snapshots}


def _connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "shadow.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    return connect_database(database_path, synchronous="FULL")


def _prepared_database(tmp_path: Path, *, include_intelligent: bool = False):
    data_dir, snapshots = _prepare_sources(
        tmp_path,
        include_intelligent=include_intelligent,
    )
    connection = _connection(tmp_path)
    import_courses_and_topics(
        connection,
        snapshots["courses.json"],
        imported_at=STAMP_1,
    )
    return data_dir, snapshots, connection


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])


def _study_plan_ids(connection: sqlite3.Connection):
    return [row[0] for row in connection.execute("SELECT id FROM study_plans ORDER BY kind, id")]


def test_weekly_and_multi_course_plans_import_without_touching_sources(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    paths = tuple(
        data_dir / name
        for name in (
            "courses.json",
            "weekly_study_plans.json",
            "multi_course_weekly_plans.json",
        )
    )
    before = tuple(_sha256(path) for path in paths)

    try:
        result = import_study_plans(
            connection,
            [
                snapshots["weekly_study_plans.json"],
                snapshots["multi_course_weekly_plans.json"],
                snapshots["intelligent_study_plans.json"],
            ],
            imported_at=STAMP_1,
        )

        assert result.study_plans.created == 2
        assert result.study_plan_items.created == 6
        assert result.changed_rows == 8
        assert result.total_plan_items == 6
        assert result.optional_sources_absent == ("data/intelligent_study_plans.json",)
        assert result.unresolved_course_refs == 0
        assert result.unresolved_topic_refs >= 2
        assert set(result.imported_sources) == {
            "data/weekly_study_plans.json",
            "data/multi_course_weekly_plans.json",
        }

        rows = connection.execute(
            "SELECT kind, horizon, requested_minutes, allocated_minutes, "
            "engine_name, engine_version FROM study_plans ORDER BY kind"
        ).fetchall()
        assert [row[0] for row in rows] == ["multi_course_weekly", "weekly"]
        assert rows[0][1:] == (
            "week",
            120,
            108,
            "multi_course_planner",
            "V9.2",
        )
        assert rows[1][1:] == (
            "week",
            240,
            240,
            "weekly_planner",
            "V9.1",
        )

        item_rows = connection.execute(
            "SELECT action, minutes, course_id, topic_id FROM study_plan_items "
            "ORDER BY plan_date, ordinal"
        ).fetchall()
        assert len(item_rows) == 6
        assert any("Linear Systems" in row[0] and row[3] is not None for row in item_rows)
        assert all(row[1] >= 0 for row in item_rows)
        assert all(row[2] is not None for row in item_rows if row[0] != "Study Review")
        for plan_id in _study_plan_ids(connection):
            assert str(uuid.UUID(plan_id)) == plan_id

        report = render_study_plan_import_review_markdown(result)
        assert "# Study Plan Import Review" in report
        assert "Optional sources absent" in report
        assert str(tmp_path) not in report

        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    assert tuple(_sha256(path) for path in paths) == before


def test_identical_reimport_is_a_noop_and_alias_works(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path)

    try:
        first = import_weekly_multi_intelligent_study_plans(
            connection,
            [
                snapshots["weekly_study_plans.json"],
                snapshots["multi_course_weekly_plans.json"],
                snapshots["intelligent_study_plans.json"],
            ],
            imported_at=STAMP_1,
        )
        original_rows = connection.execute(
            "SELECT id, updated_at FROM study_plans ORDER BY id"
        ).fetchall()

        second = import_study_plans(
            connection,
            [
                snapshots["weekly_study_plans.json"],
                snapshots["multi_course_weekly_plans.json"],
                snapshots["intelligent_study_plans.json"],
            ],
            imported_at=STAMP_2,
        )

        assert first.changed_rows == 8
        assert second.changed_rows == 0
        assert second.study_plans.matched == 2
        assert second.study_plan_items.matched == 6
        assert _table_count(connection, "study_plans") == 2
        assert _table_count(connection, "study_plan_items") == 6
        assert connection.execute(
            "SELECT id, updated_at FROM study_plans ORDER BY id"
        ).fetchall() == original_rows
    finally:
        connection.close()


def test_optional_intelligent_study_plans_import_when_present(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path, include_intelligent=True)

    try:
        result = import_study_plans(
            connection,
            [
                snapshots["weekly_study_plans.json"],
                snapshots["multi_course_weekly_plans.json"],
                snapshots["intelligent_study_plans.json"],
            ],
            imported_at=STAMP_1,
        )

        assert result.study_plans.created == 3
        assert result.study_plan_items.created == 7
        assert result.optional_sources_absent == ()

        row = connection.execute(
            "SELECT kind, horizon, requested_minutes, allocated_minutes "
            "FROM study_plans WHERE engine_name = 'intelligent_study_planner'"
        ).fetchone()
        assert tuple(row) == ("intelligent_week", "week", 90, 90)

        item = connection.execute(
            "SELECT topic_id, minutes, action, score FROM study_plan_items "
            "WHERE action LIKE '%Repair the weak point%'"
        ).fetchone()
        assert item[0] is not None
        assert item[1] == 90
        assert item[3] == 82.5
    finally:
        connection.close()


def test_changed_source_hash_updates_stable_plan_and_adds_new_ledger_evidence(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)

    try:
        import_study_plans(
            connection,
            [
                snapshots["weekly_study_plans.json"],
                snapshots["multi_course_weekly_plans.json"],
                snapshots["intelligent_study_plans.json"],
            ],
            imported_at=STAMP_1,
        )
        weekly_id = connection.execute(
            "SELECT id FROM study_plans WHERE kind = 'weekly'"
        ).fetchone()[0]
        old_hash = snapshots["weekly_study_plans.json"].source_hash

        weekly_path = data_dir / "weekly_study_plans.json"
        data = json.loads(weekly_path.read_text(encoding="utf-8"))
        data["plans"][0]["total_minutes"] = 300
        data["plans"][0]["days"][0]["minutes"] = 120
        _write_json(weekly_path, data)
        rescanned = _rescan(
            data_dir,
            "weekly_study_plans.json",
            "multi_course_weekly_plans.json",
            "intelligent_study_plans.json",
        )

        result = import_study_plans(
            connection,
            [
                rescanned["weekly_study_plans.json"],
                rescanned["multi_course_weekly_plans.json"],
                rescanned["intelligent_study_plans.json"],
            ],
            imported_at=STAMP_2,
        )

        assert result.study_plans.updated == 1
        assert result.study_plan_items.updated == 4
        updated_weekly = connection.execute(
            "SELECT id, requested_minutes, allocated_minutes FROM study_plans "
            "WHERE kind = 'weekly'"
        ).fetchone()
        assert tuple(updated_weekly) == (weekly_id, 300, 300)
        assert rescanned["weekly_study_plans.json"].source_hash != old_hash
        ledger_hashes = {
            row[0]
            for row in connection.execute(
                "SELECT source_hash FROM migration_imports "
                "WHERE source_path = 'data/weekly_study_plans.json' "
                "AND target_table = 'study_plans'"
            ).fetchall()
        }
        assert old_hash in ledger_hashes
        assert rescanned["weekly_study_plans.json"].source_hash in ledger_hashes
        assert _table_count(connection, "study_plans") == 2
    finally:
        connection.close()


def test_unresolved_course_reference_is_preserved_as_review_without_failing(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    weekly_path = data_dir / "weekly_study_plans.json"
    data = json.loads(weekly_path.read_text(encoding="utf-8"))
    data["plans"][0]["course_id"] = "missing-course"
    _write_json(weekly_path, data)
    rescanned = _rescan(
        data_dir,
        "weekly_study_plans.json",
        "multi_course_weekly_plans.json",
        "intelligent_study_plans.json",
    )

    try:
        result = import_study_plans(
            connection,
            [
                rescanned["weekly_study_plans.json"],
                snapshots["multi_course_weekly_plans.json"],
                rescanned["intelligent_study_plans.json"],
            ],
            imported_at=STAMP_1,
        )

        assert result.study_plans.created == 2
        assert result.unresolved_course_refs == 4
        assert any(issue.code == "unresolved_course_reference" for issue in result.issues)
        assert connection.execute(
            "SELECT COUNT(*) FROM study_plan_items WHERE course_id IS NULL"
        ).fetchone()[0] == 4
    finally:
        connection.close()


def test_malformed_plans_shape_fails_without_partial_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    weekly_path = data_dir / "weekly_study_plans.json"
    _write_json(weekly_path, {"version": 1, "plans": {"bad": "shape"}})
    rescanned = _rescan(
        data_dir,
        "weekly_study_plans.json",
        "multi_course_weekly_plans.json",
        "intelligent_study_plans.json",
    )

    try:
        with pytest.raises(LegacyImportDataError):
            import_study_plans(
                connection,
                [
                    rescanned["weekly_study_plans.json"],
                    snapshots["multi_course_weekly_plans.json"],
                    rescanned["intelligent_study_plans.json"],
                ],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "study_plans") == 0
        assert _table_count(connection, "study_plan_items") == 0
    finally:
        connection.close()


def test_source_changed_after_scan_is_rejected_before_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    weekly_path = data_dir / "weekly_study_plans.json"
    data = json.loads(weekly_path.read_text(encoding="utf-8"))
    data["plans"][0]["total_minutes"] = 999
    _write_json(weekly_path, data)

    try:
        with pytest.raises(LegacySourceChangedError):
            import_study_plans(
                connection,
                [
                    snapshots["weekly_study_plans.json"],
                    snapshots["multi_course_weekly_plans.json"],
                    snapshots["intelligent_study_plans.json"],
                ],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "study_plans") == 0
        assert _table_count(connection, "study_plan_items") == 0
    finally:
        connection.close()
