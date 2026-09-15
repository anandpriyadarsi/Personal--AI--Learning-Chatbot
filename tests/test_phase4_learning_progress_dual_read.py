from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.json.learning_progress_repository import (
    LegacyJsonLearningProgressRepository,
)
from personal_learning_assistant.repositories.learning_progress_backend import (
    DualReadLearningProgressRepository,
    LearningProgressBackendConfig,
    build_learning_progress_repository,
)
from personal_learning_assistant.repositories.sqlite.learning_progress_repository import (
    SQLiteLearningProgressRepository,
    SQLiteLearningProgressRepositoryReadOnlyError,
    SQLiteLearningProgressRepositorySchemaError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase4"
STAMP = "2026-09-14T05:30:00Z"
OLD_STAMP = "2026-09-13T05:30:00Z"
MEMORY_SOURCE = "data/learning_memory.json"
PROGRESS_SOURCE = "data/course_progress_history.json"
COURSE_SOURCE = "data/courses.json"
ENGINE = "legacy_course_progress_history_v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_sources(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("learning_memory.json", "course_progress_history.json", "courses.json"):
        (data / name).write_bytes((FIXTURES / name).read_bytes())
    return data


def _connection(tmp_path: Path) -> sqlite3.Connection:
    path = tmp_path / "shadow.db"
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE migration_imports (
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_version TEXT,
            legacy_key TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_id TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        CREATE TABLE courses (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE topics (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id),
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            position INTEGER NOT NULL,
            status TEXT NOT NULL,
            confidence INTEGER,
            raw_import_status TEXT,
            deleted_at TEXT
        );
        CREATE TABLE learning_memory_entries (
            id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            kind TEXT NOT NULL,
            topic_id TEXT REFERENCES topics(id),
            raw_topic TEXT NOT NULL DEFAULT '',
            memory_text TEXT NOT NULL DEFAULT '',
            source_entity_type TEXT,
            source_entity_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT
        );
        CREATE TABLE topic_progress_events (
            id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL REFERENCES topics(id),
            event_type TEXT NOT NULL,
            previous_status TEXT,
            new_status TEXT,
            confidence INTEGER,
            evidence_type TEXT,
            evidence_id TEXT,
            occurred_at TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE progress_snapshots (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id),
            snapshot_date TEXT NOT NULL,
            counts_json TEXT NOT NULL,
            score_json TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    return connection


def _ledger(
    connection: sqlite3.Connection,
    *,
    source_path: str,
    source_hash: str,
    source_version: int,
    legacy_key: str,
    target_table: str,
    target_id: str,
    details: dict,
    imported_at: str = STAMP,
):
    connection.execute(
        "INSERT INTO migration_imports "
        "(source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json) "
        "VALUES (?, ?, 'legacy_json', ?, ?, ?, ?, ?, ?)",
        (
            source_path,
            source_hash,
            str(source_version),
            legacy_key,
            target_table,
            target_id,
            imported_at,
            json.dumps(details, ensure_ascii=False, sort_keys=True),
        ),
    )


def _course_setup(connection: sqlite3.Connection, data_dir: Path):
    courses = json.loads((data_dir / "courses.json").read_text(encoding="utf-8"))
    source_hash = _sha(data_dir / "courses.json")
    course_targets = {
        "fixture-ma103n": "sqlite-course-ma",
        "fixture-cy100n": "sqlite-course-cy",
    }
    topic_targets = {
        ("fixture-ma103n", "Linear Systems"): "sqlite-topic-linear",
        ("fixture-ma103n", "LU Factorization"): "sqlite-topic-lu",
    }
    for course in courses["courses"]:
        target = course_targets[course["id"]]
        connection.execute(
            "INSERT INTO courses (id, code, name, deleted_at) VALUES (?, ?, ?, NULL)",
            (target, course["code"], course["name"]),
        )
        course_key = "course:id:{}".format(course["id"])
        _ledger(
            connection,
            source_path=COURSE_SOURCE,
            source_hash=source_hash,
            source_version=1,
            legacy_key=course_key,
            target_table="courses",
            target_id=target,
            details={"kind": "course", "legacy_id": course["id"], "raw": course},
        )
        for position, topic in enumerate(course.get("topics", [])):
            topic_target = topic_targets[(course["id"], topic["name"])]
            status = str(topic.get("status") or "not_started").strip().lower().replace(" ", "_")
            if status == "in_progress":
                status = "learning"
            confidence = topic.get("confidence")
            connection.execute(
                "INSERT INTO topics "
                "(id, course_id, name, normalized_name, position, status, confidence, raw_import_status, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    topic_target,
                    target,
                    topic["name"],
                    topic["name"].casefold(),
                    position,
                    status,
                    confidence,
                    status,
                ),
            )
            _ledger(
                connection,
                source_path=COURSE_SOURCE,
                source_hash=source_hash,
                source_version=1,
                legacy_key="{}/topic:id:{}".format(course_key, topic.get("id") or position),
                target_table="topics",
                target_id=topic_target,
                details={
                    "kind": "topic",
                    "course_legacy_key": course_key,
                    "raw": topic,
                },
            )
    return course_targets, topic_targets


def _memory_entries(connection: sqlite3.Connection, data_dir: Path, course_targets, topic_targets):
    memory_path = data_dir / "learning_memory.json"
    source_hash = _sha(memory_path)
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    target_counter = 0
    entry_targets = {}

    def add(scope_prefix, scope_type, scope_id, raw_course_id, kind, position, *, raw_topic="", memory_text="", created_at=STAMP, raw=None, topic_id=None, source_type=None):
        nonlocal target_counter
        target_counter += 1
        target = "sqlite-memory-{:02d}".format(target_counter)
        if kind in {"weak_topic", "mastered_topic"}:
            legacy_key = "{}/kind:{}/topic:{}".format(scope_prefix, kind, raw_topic.casefold())
        else:
            legacy_key = "{}/kind:{}/index:{}".format(scope_prefix, kind, position)
        connection.execute(
            "INSERT INTO learning_memory_entries "
            "(id, scope_type, scope_id, kind, topic_id, raw_topic, memory_text, source_entity_type, "
            "source_entity_id, created_at, updated_at, archived_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL)",
            (
                target,
                scope_type,
                scope_id,
                kind,
                topic_id,
                raw_topic,
                memory_text,
                source_type,
                created_at,
                created_at,
            ),
        )
        _ledger(
            connection,
            source_path=MEMORY_SOURCE,
            source_hash=source_hash,
            source_version=2,
            legacy_key=legacy_key,
            target_table="learning_memory_entries",
            target_id=target,
            details={
                "kind": "learning_memory_entry",
                "scope_type": scope_type,
                "scope_id": scope_id,
                "raw_course_id": raw_course_id,
                "entry_kind": kind,
                "raw_topic": raw_topic,
                "topic_id": topic_id,
                "raw": raw or {"position": position},
            },
        )
        entry_targets[legacy_key] = target
        return target, legacy_key

    # Global scope.
    for pos, topic in enumerate(memory["weak_topics"]):
        add("scope:global", "global", None, "", "weak_topic", pos, raw_topic=topic, raw={"topic": topic, "position": pos})
    for pos, topic in enumerate(memory["mastered_topics"]):
        add("scope:global", "global", None, "", "mastered_topic", pos, raw_topic=topic, raw={"topic": topic, "position": pos})
    for pos, activity in enumerate(memory["recent_activity"]):
        add(
            "scope:global", "global", None, "", "activity", pos,
            raw_topic=activity.get("topic", ""), memory_text=activity["question"],
            created_at=activity["time"], raw={"activity": activity, "position": pos},
            source_type="legacy_recent_activity",
        )
    for pos, note in enumerate(memory["notes"]):
        add(
            "scope:global", "global", None, "", "note", pos,
            memory_text=note["text"], created_at=note["created_at"],
            raw={"note": note, "position": pos},
        )

    for course_id, scope in memory["course_memory"].items():
        course_target = course_targets[course_id]
        prefix = "scope:course:{}".format(course_id)
        for pos, topic in enumerate(scope["weak_topics"]):
            topic_target = topic_targets.get((course_id, topic))
            entry_target, legacy_key = add(
                prefix, "course", course_target, course_id, "weak_topic", pos,
                raw_topic=topic, raw={"topic": topic, "position": pos}, topic_id=topic_target,
            )
            if topic_target:
                event_id = "sqlite-event-weak"
                connection.execute(
                    "INSERT INTO topic_progress_events "
                    "(id, topic_id, event_type, previous_status, new_status, confidence, evidence_type, evidence_id, occurred_at, note) "
                    "VALUES (?, ?, 'legacy_memory_weak_topic', NULL, 'weak', NULL, 'learning_memory_entries', ?, ?, ?)",
                    (event_id, topic_target, entry_target, STAMP, "Imported from legacy learning memory without changing topic status."),
                )
                _ledger(
                    connection,
                    source_path=MEMORY_SOURCE,
                    source_hash=source_hash,
                    source_version=2,
                    legacy_key=legacy_key + "/topic_progress_event",
                    target_table="topic_progress_events",
                    target_id=event_id,
                    details={
                        "kind": "topic_progress_event_from_learning_memory",
                        "event_type": "legacy_memory_weak_topic",
                        "new_status": "weak",
                        "topic_id": topic_target,
                        "evidence_id": entry_target,
                        "raw": {"topic": topic, "position": pos},
                    },
                )
        for pos, topic in enumerate(scope["mastered_topics"]):
            topic_target = topic_targets.get((course_id, topic))
            entry_target, legacy_key = add(
                prefix, "course", course_target, course_id, "mastered_topic", pos,
                raw_topic=topic, raw={"topic": topic, "position": pos}, topic_id=topic_target,
            )
            if topic_target:
                event_id = "sqlite-event-mastered"
                connection.execute(
                    "INSERT INTO topic_progress_events "
                    "(id, topic_id, event_type, previous_status, new_status, confidence, evidence_type, evidence_id, occurred_at, note) "
                    "VALUES (?, ?, 'legacy_memory_mastered_topic', NULL, 'mastered', NULL, 'learning_memory_entries', ?, ?, ?)",
                    (event_id, topic_target, entry_target, STAMP, "Imported from legacy learning memory without changing topic status."),
                )
                _ledger(
                    connection,
                    source_path=MEMORY_SOURCE,
                    source_hash=source_hash,
                    source_version=2,
                    legacy_key=legacy_key + "/topic_progress_event",
                    target_table="topic_progress_events",
                    target_id=event_id,
                    details={
                        "kind": "topic_progress_event_from_learning_memory",
                        "event_type": "legacy_memory_mastered_topic",
                        "new_status": "mastered",
                        "topic_id": topic_target,
                        "evidence_id": entry_target,
                        "raw": {"topic": topic, "position": pos},
                    },
                )
        for pos, activity in enumerate(scope["recent_activity"]):
            add(
                prefix, "course", course_target, course_id, "activity", pos,
                raw_topic=activity.get("topic", ""), memory_text=activity["question"],
                created_at=activity["time"], raw={"activity": activity, "position": pos},
                topic_id=topic_targets.get((course_id, activity.get("topic", ""))),
                source_type="legacy_recent_activity",
            )
        for pos, note in enumerate(scope["notes"]):
            add(
                prefix, "course", course_target, course_id, "note", pos,
                memory_text=note["text"], created_at=note["created_at"],
                raw={"note": note, "position": pos},
            )
    return entry_targets


def _progress_rows(connection: sqlite3.Connection, data_dir: Path, course_targets):
    progress_path = data_dir / "course_progress_history.json"
    source_hash = _sha(progress_path)
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    targets = []
    counter = 0
    for course_id, snapshots in progress["courses"].items():
        for snapshot in snapshots:
            counter += 1
            target = "sqlite-progress-{:02d}".format(counter)
            legacy_key = "course:{}/date:{}/engine:{}".format(course_id, snapshot["date"], ENGINE)
            connection.execute(
                "INSERT INTO progress_snapshots "
                "(id, course_id, snapshot_date, counts_json, score_json, engine_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    target,
                    course_targets[course_id],
                    snapshot["date"],
                    json.dumps({
                        "mastered_topics": snapshot.get("mastered_topics"),
                        "total_topics": snapshot.get("total_topics"),
                    }, sort_keys=True, separators=(",", ":")),
                    json.dumps({"progress_percent": snapshot.get("progress_percent")}, sort_keys=True, separators=(",", ":")),
                    ENGINE,
                    STAMP,
                ),
            )
            _ledger(
                connection,
                source_path=PROGRESS_SOURCE,
                source_hash=source_hash,
                source_version=1,
                legacy_key=legacy_key,
                target_table="progress_snapshots",
                target_id=target,
                details={
                    "kind": "course_progress_snapshot",
                    "course_id": course_targets[course_id],
                    "snapshot_date": snapshot["date"],
                    "engine_version": ENGINE,
                    "raw": snapshot,
                },
            )
            targets.append(target)
    return targets


def _prepared(tmp_path: Path):
    data_dir = _copy_sources(tmp_path)
    connection = _connection(tmp_path)
    course_targets, topic_targets = _course_setup(connection, data_dir)
    entry_targets = _memory_entries(connection, data_dir, course_targets, topic_targets)
    progress_targets = _progress_rows(connection, data_dir, course_targets)
    connection.commit()
    legacy = LegacyJsonLearningProgressRepository(
        memory_path=data_dir / "learning_memory.json",
        progress_path=data_dir / "course_progress_history.json",
        courses_path=data_dir / "courses.json",
    )
    sqlite_repo = SQLiteLearningProgressRepository(connection)
    dual = DualReadLearningProgressRepository(legacy, sqlite_repo)
    return data_dir, connection, legacy, sqlite_repo, dual, course_targets, topic_targets, entry_targets, progress_targets


def _fingerprint(connection: sqlite3.Connection):
    tables = (
        "courses", "topics", "learning_memory_entries", "topic_progress_events",
        "progress_snapshots", "migration_imports",
    )
    result = {}
    for table in tables:
        rows = connection.execute("SELECT * FROM {} ORDER BY rowid".format(table)).fetchall()
        result[table] = tuple(tuple(row) for row in rows)
    return result


def _domains(report):
    return {item.domain: item for item in report.diagnostics}


def test_legacy_mode_preserves_learning_memory_read(tmp_path):
    data_dir = _copy_sources(tmp_path)
    repo = build_learning_progress_repository(
        "legacy",
        memory_path=data_dir / "learning_memory.json",
        progress_path=data_dir / "course_progress_history.json",
        courses_path=data_dir / "courses.json",
    )
    raw = json.loads((data_dir / "learning_memory.json").read_text(encoding="utf-8"))
    assert repo.load_memory() == raw


def test_legacy_mode_preserves_academic_progress_history_read(tmp_path):
    data_dir = _copy_sources(tmp_path)
    repo = build_learning_progress_repository(
        LearningProgressBackendConfig("legacy"),
        memory_path=data_dir / "learning_memory.json",
        progress_path=data_dir / "course_progress_history.json",
        courses_path=data_dir / "courses.json",
    )
    raw = json.loads((data_dir / "course_progress_history.json").read_text(encoding="utf-8"))
    assert repo.load_progress_history() == raw


def test_dual_read_returns_exact_authoritative_memory_result(tmp_path):
    _, connection, legacy, _, dual, *_ = _prepared(tmp_path)
    try:
        expected = legacy.load_memory()
        assert dual.load_memory() == expected
        assert dual.last_report.is_semantically_equal
    finally:
        connection.close()


def test_dual_read_returns_exact_authoritative_progress_result(tmp_path):
    _, connection, legacy, _, dual, *_ = _prepared(tmp_path)
    try:
        expected = legacy.load_progress_history()
        assert dual.load_progress_history() == expected
        assert dual.last_report.is_semantically_equal
    finally:
        connection.close()


def test_matching_memory_and_progress_are_green(tmp_path):
    _, connection, _, _, dual, *_ = _prepared(tmp_path)
    try:
        dual.load_memory()
        assert _domains(dual.last_report)["learning_memory_semantics"].status == "matched"
        dual.load_progress_history()
        domains = _domains(dual.last_report)
        assert domains["progress_history_semantics"].status == "matched"
        assert domains["current_topic_progress_semantics"].status == "matched"
        assert domains["current_course_progress_summaries"].status == "matched"
    finally:
        connection.close()


def test_missing_sqlite_memory_row_produces_mismatch(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    entry_targets = rest[-2]
    try:
        target = next(target for key, target in entry_targets.items() if "/kind:note/" in key)
        connection.execute("DELETE FROM learning_memory_entries WHERE id = ?", (target,))
        connection.commit()
        dual.load_memory()
        assert dual.last_report.mismatch_count > 0
        assert _domains(dual.last_report)["learning_memory_sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_unledgered_extra_memory_row_is_detected(tmp_path):
    _, connection, _, _, dual, *_ = _prepared(tmp_path)
    try:
        connection.execute(
            "INSERT INTO learning_memory_entries "
            "(id, scope_type, scope_id, kind, topic_id, raw_topic, memory_text, source_entity_type, source_entity_id, created_at, updated_at, archived_at) "
            "VALUES ('rogue-memory', 'global', NULL, 'note', NULL, '', 'rogue', NULL, NULL, ?, ?, NULL)",
            (STAMP, STAMP),
        )
        connection.commit()
        dual.load_memory()
        diagnostic = _domains(dual.last_report)["learning_memory_sqlite_structure"]
        assert diagnostic.status == "mismatch"
        assert "unledgered" in " ".join(diagnostic.sqlite_value)
    finally:
        connection.close()


def test_historical_memory_row_is_detected_but_deferred(tmp_path):
    data_dir, connection, _, _, dual, *_ = _prepared(tmp_path)
    try:
        connection.execute(
            "INSERT INTO learning_memory_entries "
            "(id, scope_type, scope_id, kind, topic_id, raw_topic, memory_text, source_entity_type, source_entity_id, created_at, updated_at, archived_at) "
            "VALUES ('old-memory', 'global', NULL, 'note', NULL, '', 'old', NULL, NULL, ?, ?, NULL)",
            (OLD_STAMP, OLD_STAMP),
        )
        _ledger(
            connection,
            source_path=MEMORY_SOURCE,
            source_hash="0" * 64,
            source_version=2,
            legacy_key="scope:global/kind:note/index:999",
            target_table="learning_memory_entries",
            target_id="old-memory",
            details={"kind": "learning_memory_entry", "scope_type": "global", "scope_id": None, "entry_kind": "note", "raw": {"note": "old", "position": 999}},
            imported_at=OLD_STAMP,
        )
        connection.commit()
        dual.load_memory()
        assert _domains(dual.last_report)["historical_learning_memory_rows"].status == "deferred"
    finally:
        connection.close()


def test_weak_topic_mismatch_is_detected(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    entry_targets = rest[-2]
    try:
        key = next(key for key in entry_targets if "/kind:weak_topic/" in key and "fixture-ma103n" in key)
        connection.execute("UPDATE learning_memory_entries SET raw_topic = 'Different Weak Topic' WHERE id = ?", (entry_targets[key],))
        connection.commit()
        dual.load_memory()
        assert _domains(dual.last_report)["learning_memory_semantics"].status == "mismatch"
    finally:
        connection.close()


def test_mastered_topic_mismatch_is_detected(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    entry_targets = rest[-2]
    try:
        key = next(key for key in entry_targets if "/kind:mastered_topic/" in key and "fixture-ma103n" in key)
        connection.execute("UPDATE learning_memory_entries SET raw_topic = 'Different Mastered Topic' WHERE id = ?", (entry_targets[key],))
        connection.commit()
        dual.load_memory()
        assert _domains(dual.last_report)["learning_memory_semantics"].status == "mismatch"
    finally:
        connection.close()


def test_learning_memory_note_text_mismatch_is_detected(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    entry_targets = rest[-2]
    try:
        key = next(key for key in entry_targets if "scope:course:fixture-ma103n/kind:note/" in key)
        connection.execute("UPDATE learning_memory_entries SET memory_text = 'Changed note' WHERE id = ?", (entry_targets[key],))
        connection.commit()
        dual.load_memory()
        assert _domains(dual.last_report)["learning_memory_semantics"].status == "mismatch"
    finally:
        connection.close()


def test_memory_course_topic_relationship_mismatch_is_structural(tmp_path):
    _, connection, _, _, dual, course_targets, _, entry_targets, _ = _prepared(tmp_path)
    try:
        key = next(key for key in entry_targets if "fixture-ma103n/kind:weak_topic" in key)
        connection.execute(
            "UPDATE learning_memory_entries SET scope_id = ? WHERE id = ?",
            (course_targets["fixture-cy100n"], entry_targets[key]),
        )
        connection.commit()
        dual.load_memory()
        assert _domains(dual.last_report)["learning_memory_sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_topic_status_mismatch_is_detected(tmp_path):
    _, connection, _, _, dual, _, topic_targets, *_ = _prepared(tmp_path)
    try:
        connection.execute("UPDATE topics SET status = 'weak' WHERE id = ?", (topic_targets[("fixture-ma103n", "Linear Systems")],))
        connection.commit()
        dual.load_progress_history()
        assert _domains(dual.last_report)["current_topic_progress_semantics"].status == "mismatch"
    finally:
        connection.close()


def test_topic_confidence_mismatch_is_detected(tmp_path):
    _, connection, _, _, dual, _, topic_targets, *_ = _prepared(tmp_path)
    try:
        connection.execute("UPDATE topics SET confidence = 5 WHERE id = ?", (topic_targets[("fixture-ma103n", "Linear Systems")],))
        connection.commit()
        dual.load_progress_history()
        assert _domains(dual.last_report)["current_topic_progress_semantics"].status == "mismatch"
    finally:
        connection.close()


def test_missing_progress_snapshot_is_detected(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    progress_targets = rest[-1]
    try:
        connection.execute("DELETE FROM progress_snapshots WHERE id = ?", (progress_targets[0],))
        connection.commit()
        dual.load_progress_history()
        domains = _domains(dual.last_report)
        assert domains["progress_history_semantics"].status == "mismatch"
        assert domains["academic_progress_sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_unledgered_extra_progress_snapshot_is_detected(tmp_path):
    _, connection, _, _, dual, course_targets, *_ = _prepared(tmp_path)
    try:
        connection.execute(
            "INSERT INTO progress_snapshots (id, course_id, snapshot_date, counts_json, score_json, engine_version, created_at) "
            "VALUES ('rogue-progress', ?, '2026-09-15', '{}', '{}', ?, ?)",
            (course_targets["fixture-ma103n"], ENGINE, STAMP),
        )
        connection.commit()
        dual.load_progress_history()
        diagnostic = _domains(dual.last_report)["academic_progress_sqlite_structure"]
        assert diagnostic.status == "mismatch"
        assert "unledgered" in " ".join(diagnostic.sqlite_value)
    finally:
        connection.close()


def test_historical_progress_snapshot_is_deferred(tmp_path):
    _, connection, _, _, dual, course_targets, *_ = _prepared(tmp_path)
    try:
        connection.execute(
            "INSERT INTO progress_snapshots (id, course_id, snapshot_date, counts_json, score_json, engine_version, created_at) "
            "VALUES ('old-progress', ?, '2026-08-01', ?, ?, ?, ?)",
            (course_targets["fixture-ma103n"], '{"mastered_topics":0,"total_topics":2}', '{"progress_percent":0}', ENGINE, OLD_STAMP),
        )
        _ledger(
            connection,
            source_path=PROGRESS_SOURCE,
            source_hash="1" * 64,
            source_version=1,
            legacy_key="course:fixture-ma103n/date:2026-08-01/engine:" + ENGINE,
            target_table="progress_snapshots",
            target_id="old-progress",
            details={"kind": "course_progress_snapshot", "course_id": course_targets["fixture-ma103n"], "snapshot_date": "2026-08-01", "engine_version": ENGINE, "raw": {"date": "2026-08-01", "course_id": "fixture-ma103n", "mastered_topics": 0, "total_topics": 2, "progress_percent": 0}},
            imported_at=OLD_STAMP,
        )
        connection.commit()
        dual.load_progress_history()
        assert _domains(dual.last_report)["historical_progress_rows"].status == "deferred"
    finally:
        connection.close()


def test_progress_snapshot_value_mismatch_is_detected(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    progress_targets = rest[-1]
    try:
        connection.execute("UPDATE progress_snapshots SET score_json = '{\"progress_percent\":99}' WHERE id = ?", (progress_targets[0],))
        connection.commit()
        dual.load_progress_history()
        snapshots = dual.sqlite_repository.parity_snapshot()["progress_history"]["snapshots"]
        snapshot = next(item for item in snapshots if item["target_id"] == progress_targets[0])
        assert snapshot["scores"]["progress_percent"] == 99
        assert _domains(dual.last_report)["academic_progress_sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_progress_snapshot_date_relationship_mismatch_is_structural(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    progress_targets = rest[-1]
    try:
        connection.execute("UPDATE progress_snapshots SET snapshot_date = '2026-09-02' WHERE id = ?", (progress_targets[0],))
        connection.commit()
        dual.load_progress_history()
        snapshots = dual.sqlite_repository.parity_snapshot()["progress_history"]["snapshots"]
        snap = next(item for item in snapshots if item["target_id"] == progress_targets[0])
        assert snap["snapshot_date"] != snap["raw"]["date"]
        assert _domains(dual.last_report)["academic_progress_sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_wrong_progress_course_ownership_is_detected(tmp_path):
    _, connection, _, _, dual, course_targets, *rest = _prepared(tmp_path)
    progress_targets = rest[-1]
    try:
        connection.execute("UPDATE progress_snapshots SET course_id = ? WHERE id = ?", (course_targets["fixture-cy100n"], progress_targets[0]))
        connection.commit()
        dual.load_progress_history()
        assert _domains(dual.last_report)["academic_progress_sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_ledger_target_missing_from_relational_sqlite_is_detected(tmp_path):
    _, connection, _, _, dual, *rest = _prepared(tmp_path)
    entry_targets = rest[-2]
    try:
        note_target = next(target for key, target in entry_targets.items() if key.startswith("scope:global/kind:note/"))
        connection.execute("DELETE FROM learning_memory_entries WHERE id = ?", (note_target,))
        connection.commit()
        dual.load_memory()
        assert _domains(dual.last_report)["learning_memory_sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_duplicate_legacy_identity_mapping_is_detected(tmp_path):
    data_dir, connection, _, _, dual, *_ = _prepared(tmp_path)
    try:
        connection.execute(
            "INSERT INTO learning_memory_entries "
            "(id, scope_type, scope_id, kind, topic_id, raw_topic, memory_text, source_entity_type, source_entity_id, created_at, updated_at, archived_at) "
            "VALUES ('duplicate-memory', 'global', NULL, 'note', NULL, '', 'duplicate', NULL, NULL, ?, ?, NULL)",
            (STAMP, STAMP),
        )
        _ledger(
            connection,
            source_path=MEMORY_SOURCE,
            source_hash=_sha(data_dir / "learning_memory.json"),
            source_version=2,
            legacy_key="scope:global/kind:note/index:0",
            target_table="learning_memory_entries",
            target_id="duplicate-memory",
            details={"kind": "learning_memory_entry", "scope_type": "global", "scope_id": None, "entry_kind": "note", "raw": {"note": "duplicate", "position": 0}},
            imported_at=STAMP,
        )
        connection.commit()
        dual.load_memory()
        diagnostic = _domains(dual.last_report)["learning_memory_sqlite_structure"]
        assert diagnostic.status == "mismatch"
        assert "duplicate" in " ".join(diagnostic.sqlite_value)
    finally:
        connection.close()


def test_sqlite_read_failure_does_not_break_legacy_read(tmp_path):
    _, connection, legacy, sqlite_repo, dual, *_ = _prepared(tmp_path)
    expected = legacy.load_memory()
    original = sqlite_repo.parity_snapshot
    try:
        sqlite_repo.parity_snapshot = lambda: (_ for _ in ()).throw(RuntimeError("shadow unavailable"))
        assert dual.load_memory() == expected
        assert dual.last_report.status == "mismatch"
        assert _domains(dual.last_report)["sqlite_read"].status == "error"
    finally:
        sqlite_repo.parity_snapshot = original
        connection.close()


def test_diagnostic_sink_failure_does_not_break_legacy_read(tmp_path):
    _, connection, legacy, sqlite_repo, _, *_ = _prepared(tmp_path)
    dual = DualReadLearningProgressRepository(
        legacy,
        sqlite_repo,
        diagnostic_sink=lambda _report: (_ for _ in ()).throw(RuntimeError("sink failed")),
    )
    try:
        assert dual.load_progress_history() == legacy.load_progress_history()
        assert dual.last_report is not None
    finally:
        connection.close()


def test_sqlite_mutations_fail_explicitly(tmp_path):
    _, connection, _, sqlite_repo, _, *_ = _prepared(tmp_path)
    try:
        with pytest.raises(SQLiteLearningProgressRepositoryReadOnlyError):
            sqlite_repo.save_memory({})
        with pytest.raises(SQLiteLearningProgressRepositoryReadOnlyError):
            sqlite_repo.save_progress_history({})
        with pytest.raises(SQLiteLearningProgressRepositoryReadOnlyError):
            sqlite_repo.record_progress_snapshot("fixture-ma103n")
    finally:
        connection.close()


def test_schema_validation_rejects_incomplete_database(tmp_path):
    connection = sqlite3.connect(str(tmp_path / "bad.db"))
    try:
        connection.execute("CREATE TABLE migration_imports (id INTEGER)")
        with pytest.raises(SQLiteLearningProgressRepositorySchemaError):
            SQLiteLearningProgressRepository(connection)
    finally:
        connection.close()


def test_dual_reads_change_zero_legacy_bytes_and_zero_sqlite_state(tmp_path):
    data_dir, connection, _, _, dual, *_ = _prepared(tmp_path)
    memory_path = data_dir / "learning_memory.json"
    progress_path = data_dir / "course_progress_history.json"
    courses_path = data_dir / "courses.json"
    before_bytes = {path.name: path.read_bytes() for path in (memory_path, progress_path, courses_path)}
    before_hashes = {path.name: _sha(path) for path in (memory_path, progress_path, courses_path)}
    before_db = _fingerprint(connection)
    before_changes = connection.total_changes
    try:
        dual.load_memory()
        dual.load_progress_history()
        dual.load_current_progress_state()
        assert connection.total_changes == before_changes
        assert _fingerprint(connection) == before_db
        for path in (memory_path, progress_path, courses_path):
            assert path.read_bytes() == before_bytes[path.name]
            assert _sha(path) == before_hashes[path.name]
    finally:
        connection.close()


def test_repeated_dual_reads_are_deterministic_and_side_effect_free(tmp_path):
    _, connection, _, _, dual, *_ = _prepared(tmp_path)
    before = _fingerprint(connection)
    changes = connection.total_changes
    try:
        first_memory = dual.load_memory()
        first_progress = dual.load_progress_history()
        second_memory = dual.load_memory()
        second_progress = dual.load_progress_history()
        assert first_memory == second_memory
        assert first_progress == second_progress
        assert _fingerprint(connection) == before
        assert connection.total_changes == changes
    finally:
        connection.close()


def test_progress_reads_do_not_create_new_snapshots(tmp_path):
    _, connection, _, _, dual, *_ = _prepared(tmp_path)
    before = connection.execute("SELECT COUNT(*) FROM progress_snapshots").fetchone()[0]
    try:
        dual.load_progress_history()
        dual.load_current_progress_state()
        after = connection.execute("SELECT COUNT(*) FROM progress_snapshots").fetchone()[0]
        assert after == before
    finally:
        connection.close()


def test_learning_memory_reads_do_not_append_events_or_entries(tmp_path):
    _, connection, _, _, dual, *_ = _prepared(tmp_path)
    before = (
        connection.execute("SELECT COUNT(*) FROM learning_memory_entries").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0],
    )
    try:
        dual.load_memory()
        after = (
            connection.execute("SELECT COUNT(*) FROM learning_memory_entries").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0],
        )
        assert after == before
    finally:
        connection.close()


def test_integrity_and_foreign_key_checks_are_clean(tmp_path):
    _, connection, _, sqlite_repo, _, *_ = _prepared(tmp_path)
    try:
        result = sqlite_repo.integrity_checks()
        assert result["integrity_check"] == "ok"
        assert result["foreign_key_check"] == ()
    finally:
        connection.close()


def test_factory_supports_only_legacy_and_dual_read(tmp_path):
    data_dir = _copy_sources(tmp_path)
    with pytest.raises(ValueError):
        LearningProgressBackendConfig("sqlite")
    with pytest.raises(ValueError):
        build_learning_progress_repository(
            "dual_read",
            memory_path=data_dir / "learning_memory.json",
            progress_path=data_dir / "course_progress_history.json",
            courses_path=data_dir / "courses.json",
        )
    assert isinstance(
        build_learning_progress_repository(
            "legacy",
            memory_path=data_dir / "learning_memory.json",
            progress_path=data_dir / "course_progress_history.json",
            courses_path=data_dir / "courses.json",
        ),
        LegacyJsonLearningProgressRepository,
    )


def test_dual_read_writes_only_legacy_memory(tmp_path):
    data_dir, connection, legacy, _, dual, *_ = _prepared(tmp_path)
    before_db = _fingerprint(connection)
    try:
        memory = legacy.load_memory()
        memory["notes"].append({"text": "Legacy-only write.", "created_at": "2026-09-15T00:00:00"})
        dual.save_memory(memory)
        assert legacy.load_memory()["notes"][-1]["text"] == "Legacy-only write."
        assert _fingerprint(connection) == before_db
    finally:
        connection.close()


def test_dual_read_writes_only_legacy_progress_history(tmp_path):
    _, connection, legacy, _, dual, *_ = _prepared(tmp_path)
    before_db = _fingerprint(connection)
    try:
        history = legacy.load_progress_history()
        history["courses"]["fixture-cy100n"].append({"date": "2026-09-15", "course_id": "fixture-cy100n", "mastered_topics": 0, "total_topics": 0, "progress_percent": 0})
        dual.save_progress_history(history)
        assert legacy.load_progress_history()["courses"]["fixture-cy100n"][-1]["date"] == "2026-09-15"
        assert _fingerprint(connection) == before_db
    finally:
        connection.close()
