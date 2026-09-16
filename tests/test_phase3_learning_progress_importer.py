from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.courses_topics_importer import (
    import_courses_and_topics,
)
from personal_learning_assistant.migration.learning_progress_importer import (
    import_academic_progress,
    import_learning_memory_and_progress,
    render_learning_progress_review_markdown,
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
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP_1 = "2026-09-14T05:30:00Z"
STAMP_2 = "2026-09-14T05:45:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _prepare_sources(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    filenames = (
        "courses.json",
        "learning_memory.json",
        "course_progress_history.json",
    )
    for name in filenames:
        (data_dir / name).write_bytes((FIXTURES / name).read_bytes())

    snapshots = scan_legacy_sources(
        data_dir,
        specs=tuple(LegacySourceSpec(name) for name in filenames),
    ).sources
    return data_dir, {Path(item.canonical_path).name: item for item in snapshots}


def _rescan(data_dir: Path, *filenames: str):
    snapshots = scan_legacy_sources(
        data_dir,
        specs=tuple(LegacySourceSpec(name) for name in filenames),
    ).sources
    return {Path(item.canonical_path).name: item for item in snapshots}


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


def test_learning_memory_and_progress_import_without_touching_sources(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    source_paths = tuple(
        data_dir / name
        for name in (
            "courses.json",
            "learning_memory.json",
            "course_progress_history.json",
        )
    )
    before_hashes = tuple(_sha256(path) for path in source_paths)

    try:
        result = import_learning_memory_and_progress(
            connection,
            snapshots["learning_memory.json"],
            snapshots["course_progress_history.json"],
            imported_at=STAMP_1,
        )

        assert result.learning_memory_entries.created == 4
        assert result.progress_snapshots.created == 2
        assert result.topic_progress_events.total == 0
        assert result.unresolved_topics == 2
        assert result.unresolved_courses == 0
        assert result.changed_rows == 6

        kinds = [
            row[0]
            for row in connection.execute(
                "SELECT kind FROM learning_memory_entries ORDER BY kind, memory_text, raw_topic"
            ).fetchall()
        ]
        assert kinds == [
            "mastered_topic",
            "note",
            "note",
            "weak_topic",
        ]

        rows = connection.execute(
            "SELECT scope_type, scope_id, kind, topic_id, raw_topic, memory_text "
            "FROM learning_memory_entries ORDER BY kind, memory_text, raw_topic"
        ).fetchall()
        assert {row[0] for row in rows} == {"global"}
        assert {row[1] for row in rows} == {None}
        assert {row[3] for row in rows} == {None}
        assert "Synthetic Weak Topic" in {row[4] for row in rows}
        assert "Synthetic learning-memory note one." in {row[5] for row in rows}

        snapshots_rows = connection.execute(
            "SELECT ps.snapshot_date, ps.counts_json, ps.score_json, c.code "
            "FROM progress_snapshots AS ps "
            "JOIN courses AS c ON c.id = ps.course_id "
            "ORDER BY c.code"
        ).fetchall()
        assert len(snapshots_rows) == 2
        assert {row[0] for row in snapshots_rows} == {"2026-01-01"}
        assert {json.loads(row[1])["mastered_topics"] for row in snapshots_rows} == {0}
        assert {json.loads(row[2])["progress_percent"] for row in snapshots_rows} == {0.0}

        assert _table_count(connection, "topic_progress_events") == 0
        assert connection.execute(
            "SELECT status FROM topics WHERE normalized_name = 'linear systems'"
        ).fetchone()[0] == "not_started"

        issue_codes = {issue.code for issue in result.issues}
        assert "learning_memory_topic_unresolved" in issue_codes
        report = render_learning_progress_review_markdown(result)
        assert "# Learning Memory and Progress Review" in report
        assert "Review-required items: 2" in report
        assert "Synthetic Weak Topic" in report
        assert str(tmp_path) not in report
    finally:
        connection.close()

    assert tuple(_sha256(path) for path in source_paths) == before_hashes


def test_identical_reimport_is_noop_and_alias_works(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path)

    try:
        first = import_academic_progress(
            connection,
            snapshots["learning_memory.json"],
            snapshots["course_progress_history.json"],
            imported_at=STAMP_1,
        )
        second = import_learning_memory_and_progress(
            connection,
            snapshots["learning_memory.json"],
            snapshots["course_progress_history.json"],
            imported_at=STAMP_2,
        )

        assert first.changed_rows == 6
        assert second.changed_rows == 0
        assert second.learning_memory_entries.matched == 4
        assert second.progress_snapshots.matched == 2
        assert second.topic_progress_events.total == 0
        assert _table_count(connection, "learning_memory_entries") == 4
        assert _table_count(connection, "progress_snapshots") == 2
    finally:
        connection.close()


def test_course_scoped_memory_resolves_exact_topic_and_creates_event(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    memory_path = data_dir / "learning_memory.json"
    progress_path = data_dir / "course_progress_history.json"
    _write_json(
        memory_path,
        {
            "version": 2,
            "weak_topics": [],
            "mastered_topics": [],
            "notes": [],
            "recent_activity": [],
            "course_memory": {
                "fixture-ma103n": {
                    "weak_topics": ["Linear Systems"],
                    "mastered_topics": [],
                    "notes": [
                        {"text": "Need more row-reduction practice.", "created_at": "2026-09-10T10:00:00"}
                    ],
                    "recent_activity": [
                        {
                            "mode": "Academic Study",
                            "question": "Practiced one row-reduction question.",
                            "topic": "Linear Systems",
                            "time": "2026-09-10T10:30:00",
                        }
                    ],
                }
            },
        },
    )
    # Keep the progress source valid but small for this focused test.
    _write_json(
        progress_path,
        {"version": 1, "history": {"fixture-ma103n": []}},
    )
    fresh = _rescan(
        data_dir,
        "learning_memory.json",
        "course_progress_history.json",
    )

    try:
        result = import_learning_memory_and_progress(
            connection,
            fresh["learning_memory.json"],
            fresh["course_progress_history.json"],
            imported_at=STAMP_1,
        )

        assert result.learning_memory_entries.created == 3
        assert result.topic_progress_events.created == 1
        assert result.progress_snapshots.total == 0
        assert result.unresolved_topics == 0
        assert result.deferred_activity_records == 1

        course_rows = connection.execute(
            "SELECT scope_type, scope_id, kind, topic_id, raw_topic, memory_text "
            "FROM learning_memory_entries ORDER BY kind"
        ).fetchall()
        assert {row[0] for row in course_rows} == {"course"}
        assert all(row[1] for row in course_rows)
        assert any(row[2] == "weak_topic" and row[3] for row in course_rows)
        assert any(row[2] == "activity" and row[3] for row in course_rows)

        event = connection.execute(
            "SELECT event_type, new_status, evidence_type, evidence_id "
            "FROM topic_progress_events"
        ).fetchone()
        assert event[0] == "legacy_memory_weak_topic"
        assert event[1] == "weak"
        assert event[2] == "learning_memory_entries"
        assert event[3]

        # The importer records evidence only. It does not mutate topic mastery.
        assert connection.execute(
            "SELECT status FROM topics WHERE normalized_name = 'linear systems'"
        ).fetchone()[0] == "not_started"
    finally:
        connection.close()


def test_changed_memory_hash_updates_stable_entry_and_records_new_ledger(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    memory_path = data_dir / "learning_memory.json"

    try:
        first = import_learning_memory_and_progress(
            connection,
            snapshots["learning_memory.json"],
            snapshots["course_progress_history.json"],
            imported_at=STAMP_1,
        )
        note_row = connection.execute(
            "SELECT e.id, e.memory_text "
            "FROM learning_memory_entries AS e "
            "JOIN migration_imports AS mi ON mi.target_id = e.id "
            "WHERE mi.source_path = 'data/learning_memory.json' "
            "AND mi.target_table = 'learning_memory_entries' "
            "AND mi.legacy_key = 'scope:global/kind:note/index:0'"
        ).fetchone()
        assert note_row[1] == "Synthetic learning-memory note one."

        data = json.loads(memory_path.read_text(encoding="utf-8"))
        data["notes"][0] = "Updated learning-memory note one."
        _write_json(memory_path, data)
        fresh = _rescan(data_dir, "learning_memory.json")

        second = import_learning_memory_and_progress(
            connection,
            fresh["learning_memory.json"],
            snapshots["course_progress_history.json"],
            imported_at=STAMP_2,
        )
        updated_row = connection.execute(
            "SELECT id, memory_text FROM learning_memory_entries WHERE id = ?",
            (note_row[0],),
        ).fetchone()

        assert first.memory_source_hash != second.memory_source_hash
        assert updated_row[0] == note_row[0]
        assert updated_row[1] == "Updated learning-memory note one."
        assert second.learning_memory_entries.updated >= 1

        hashes_for_target = connection.execute(
            "SELECT COUNT(DISTINCT source_hash) FROM migration_imports "
            "WHERE target_table = 'learning_memory_entries' AND target_id = ?",
            (note_row[0],),
        ).fetchone()[0]
        assert hashes_for_target == 2
    finally:
        connection.close()


def test_unresolved_progress_course_is_reported_and_not_guessed(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    progress_path = data_dir / "course_progress_history.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    progress["history"]["missing-course"] = [
        {
            "date": "2026-01-02",
            "course_id": "missing-course",
            "mastered_topics": 1,
            "total_topics": 2,
            "progress_percent": 50.0,
        }
    ]
    _write_json(progress_path, progress)
    fresh = _rescan(data_dir, "course_progress_history.json")

    try:
        result = import_learning_memory_and_progress(
            connection,
            snapshots["learning_memory.json"],
            fresh["course_progress_history.json"],
            imported_at=STAMP_1,
        )

        assert result.unresolved_courses == 1
        assert result.progress_snapshots.created == 2
        assert all(
            item.reason != "unresolved_progress_history_course"
            or item.raw_course_id == "missing-course"
            for item in result.review_items
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM progress_snapshots WHERE snapshot_date = '2026-01-02'"
        ).fetchone()[0] == 0
        assert "progress_history_course_unresolved" in {issue.code for issue in result.issues}
    finally:
        connection.close()


def test_malformed_memory_shape_fails_without_partial_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    memory_path = data_dir / "learning_memory.json"
    _write_json(
        memory_path,
        {
            "version": 2,
            "weak_topics": "Linear Systems",
            "mastered_topics": [],
            "notes": [],
            "recent_activity": [],
            "course_memory": {},
        },
    )
    fresh = _rescan(data_dir, "learning_memory.json")

    try:
        with pytest.raises(LegacyImportDataError):
            import_learning_memory_and_progress(
                connection,
                fresh["learning_memory.json"],
                snapshots["course_progress_history.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "learning_memory_entries") == 0
        assert _table_count(connection, "topic_progress_events") == 0
        assert _table_count(connection, "progress_snapshots") == 0
    finally:
        connection.close()


def test_source_changed_after_scan_is_rejected_before_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    memory_path = data_dir / "learning_memory.json"
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    memory["notes"].append("Changed after scan.")
    _write_json(memory_path, memory)

    try:
        with pytest.raises(LegacySourceChangedError):
            import_learning_memory_and_progress(
                connection,
                snapshots["learning_memory.json"],
                snapshots["course_progress_history.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "learning_memory_entries") == 0
        assert _table_count(connection, "progress_snapshots") == 0
    finally:
        connection.close()


def test_duplicate_progress_snapshot_date_fails_without_partial_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    progress_path = data_dir / "course_progress_history.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    progress["history"]["fixture-ma103n"].append(
        {
            "date": "2026-01-01",
            "course_id": "fixture-ma103n",
            "mastered_topics": 1,
            "total_topics": 1,
            "progress_percent": 100.0,
        }
    )
    _write_json(progress_path, progress)
    fresh = _rescan(data_dir, "course_progress_history.json")

    try:
        with pytest.raises(LegacyImportDataError):
            import_learning_memory_and_progress(
                connection,
                snapshots["learning_memory.json"],
                fresh["course_progress_history.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "learning_memory_entries") == 0
        assert _table_count(connection, "progress_snapshots") == 0
    finally:
        connection.close()
