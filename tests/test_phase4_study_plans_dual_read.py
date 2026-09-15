from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.json.study_plan_repository import (
    LegacyJsonStudyPlanRepository,
)
from personal_learning_assistant.repositories.sqlite.study_plan_repository import (
    INTELLIGENT_SOURCE_PATH,
    MULTI_SOURCE_PATH,
    WEEKLY_SOURCE_PATH,
    SQLiteStudyPlanRepository,
    SQLiteStudyPlanRepositoryReadOnlyError,
    SQLiteStudyPlanRepositorySchemaError,
)
from personal_learning_assistant.repositories.study_plan_backend import (
    DualReadStudyPlanRepository,
    StudyPlanBackendConfig,
    build_study_plan_repository,
    compare_study_plan_parity,
    _legacy_source_projection,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase4"
SOURCE_FILES = {
    WEEKLY_SOURCE_PATH: "weekly_study_plans.json",
    MULTI_SOURCE_PATH: "multi_course_weekly_plans.json",
    INTELLIGENT_SOURCE_PATH: "intelligent_study_plans.json",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_sources(tmp_path: Path, *, include_intelligent: bool = True):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("weekly_study_plans.json", "multi_course_weekly_plans.json"):
        (data / name).write_bytes((FIXTURES / name).read_bytes())
    if include_intelligent:
        name = "intelligent_study_plans.json"
        (data / name).write_bytes((FIXTURES / name).read_bytes())
    return LegacyJsonStudyPlanRepository(
        weekly_path=data / "weekly_study_plans.json",
        multi_course_path=data / "multi_course_weekly_plans.json",
        intelligent_path=data / "intelligent_study_plans.json",
    )


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
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
            deleted_at TEXT
        );
        CREATE TABLE study_plans (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            horizon TEXT NOT NULL,
            starts_on TEXT NOT NULL,
            ends_on TEXT NOT NULL,
            requested_minutes INTEGER NOT NULL,
            allocated_minutes INTEGER NOT NULL,
            status TEXT NOT NULL,
            engine_name TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            rationale TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE study_plan_items (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES study_plans(id),
            plan_date TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            course_id TEXT REFERENCES courses(id),
            topic_id TEXT REFERENCES topics(id),
            assessment_id TEXT,
            resource_id TEXT,
            note_id TEXT,
            minutes INTEGER NOT NULL,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            score REAL,
            status TEXT NOT NULL
        );
        """
    )
    connection.executemany(
        "INSERT INTO courses(id, code, name, deleted_at) VALUES (?, ?, ?, NULL)",
        [
            ("fixture-ma103n", "MA103N", "Synthetic Linear Algebra"),
            ("fixture-cy100n", "CY100N", "Synthetic Engineering Chemistry"),
        ],
    )
    connection.executemany(
        "INSERT INTO topics(id, course_id, name, normalized_name, deleted_at) VALUES (?, ?, ?, ?, NULL)",
        [
            ("topic-linear", "fixture-ma103n", "Linear Systems", "linear systems"),
            ("topic-atomic", "fixture-cy100n", "Atomic Structure", "atomic structure"),
        ],
    )
    connection.commit()


def _topic_target(raw_course: str, raw_topic: str):
    if raw_course == "fixture-ma103n" and raw_topic == "Linear Systems":
        return "topic-linear"
    if raw_course == "fixture-cy100n" and raw_topic == "Atomic Structure":
        return "topic-atomic"
    return None


def _seed_shadow(connection: sqlite3.Connection, legacy: LegacyJsonStudyPlanRepository):
    state = legacy.load_state()
    store_by_source = {
        WEEKLY_SOURCE_PATH: state["weekly"],
        MULTI_SOURCE_PATH: state["multi_course"],
        INTELLIGENT_SOURCE_PATH: state["intelligent"],
    }
    counter = 0
    for source_path, store in store_by_source.items():
        if store is None:
            continue
        projected = _legacy_source_projection(legacy, source_path, store)
        plan_target = {}
        for plan in projected["plan_rows"]:
            counter += 1
            target = "plan-{}".format(counter)
            plan_target[plan["legacy_key"]] = target
            connection.execute(
                "INSERT INTO study_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target,
                    plan["kind"],
                    plan["horizon"],
                    plan["starts_on"],
                    plan["ends_on"],
                    plan["requested_minutes"],
                    plan["allocated_minutes"],
                    plan["status"],
                    plan["engine_name"],
                    plan["engine_version"],
                    plan["rationale"],
                    plan["created_at"],
                    plan["updated_at"],
                ),
            )
            raw = next(
                item["raw"] for item in projected["raw_plan_evidence"]
                if item["legacy_key"] == plan["legacy_key"]
            )
            connection.execute(
                "INSERT INTO migration_imports VALUES (?, ?, 'legacy_json', ?, ?, 'study_plans', ?, ?, ?)",
                (
                    source_path,
                    projected["source_hash"],
                    str(projected["source_version"]),
                    plan["legacy_key"],
                    target,
                    "2026-09-15T06:30:00Z",
                    json.dumps({
                        "kind": "study_plan",
                        "engine_name": plan["engine_name"],
                        "engine_version": plan["engine_version"],
                        "legacy_kind": plan["kind"],
                        "raw": raw,
                    }, sort_keys=True),
                ),
            )
        for item in projected["item_rows"]:
            counter += 1
            target = "item-{}".format(counter)
            course_id = item["raw_course_id"] or None
            topic_id = _topic_target(item["raw_course_id"], item["raw_topic"])
            connection.execute(
                "INSERT INTO study_plan_items VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?)",
                (
                    target,
                    plan_target[item["plan_legacy_key"]],
                    item["plan_date"],
                    item["ordinal"],
                    course_id,
                    topic_id,
                    item["minutes"],
                    item["action"],
                    item["reason"],
                    item["score"],
                    item["status"],
                ),
            )
            connection.execute(
                "INSERT INTO migration_imports VALUES (?, ?, 'legacy_json', ?, ?, 'study_plan_items', ?, ?, ?)",
                (
                    source_path,
                    projected["source_hash"],
                    str(projected["source_version"]),
                    item["legacy_key"],
                    target,
                    "2026-09-15T06:30:00Z",
                    json.dumps({
                        "kind": "study_plan_item",
                        "plan_legacy_key": item["plan_legacy_key"],
                        "raw_course_id": item["raw_course_id"],
                        "raw_topic": item["raw_topic"],
                        "target_course_id": course_id,
                        "target_topic_id": topic_id,
                        "raw": item["raw"],
                    }, sort_keys=True),
                ),
            )
    connection.commit()


def _setup(tmp_path: Path, *, include_intelligent: bool = True):
    legacy = _copy_sources(tmp_path, include_intelligent=include_intelligent)
    connection = sqlite3.connect(str(tmp_path / "shadow.db"))
    _schema(connection)
    _seed_shadow(connection, legacy)
    sqlite_repo = SQLiteStudyPlanRepository(connection)
    dual = DualReadStudyPlanRepository(legacy, sqlite_repo)
    return legacy, connection, sqlite_repo, dual


def _domains(report):
    return {item.domain for item in report.diagnostics if item.status in {"mismatch", "error"}}


def test_legacy_mode_preserves_exact_stores(tmp_path):
    legacy = _copy_sources(tmp_path)
    repo = build_study_plan_repository("legacy", legacy_repository=legacy)
    assert repo.load_state() == legacy.load_state()


def test_dual_read_returns_exact_authoritative_legacy_state(tmp_path):
    legacy, connection, _, dual = _setup(tmp_path)
    try:
        assert dual.load_state() == legacy.load_state()
        assert dual.last_report.is_semantically_equal
    finally:
        connection.close()


def test_matching_study_plan_data_produces_parity_success(tmp_path):
    _, connection, _, dual = _setup(tmp_path)
    try:
        dual.load_state()
        assert dual.last_report.status == "pass"
    finally:
        connection.close()


def test_sqlite_repository_rejects_writes(tmp_path):
    _, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        with pytest.raises(SQLiteStudyPlanRepositoryReadOnlyError):
            sqlite_repo.save_state({})
    finally:
        connection.close()


def test_schema_validation_rejects_incomplete_schema():
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE study_plans(id TEXT PRIMARY KEY)")
        with pytest.raises(SQLiteStudyPlanRepositorySchemaError):
            SQLiteStudyPlanRepository(connection)
    finally:
        connection.close()


def test_missing_sqlite_plan_row_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM study_plan_items WHERE plan_id = 'plan-1'")
        connection.execute("DELETE FROM study_plans WHERE id = 'plan-1'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_extra_unledgered_sqlite_plan_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute(
            "INSERT INTO study_plans VALUES ('rogue-plan','weekly','week','2026-09-15','2026-09-21',0,0,'proposed','rogue','1','', '2026-09-15','2026-09-15')"
        )
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_global_structure" in _domains(report)
    finally:
        connection.close()


def test_missing_sqlite_plan_item_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("DELETE FROM study_plan_items WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_extra_unledgered_sqlite_item_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute(
            "INSERT INTO study_plan_items VALUES ('rogue-item','plan-1','2026-09-20',99,NULL,NULL,NULL,NULL,NULL,5,'Buffer','',NULL,'planned')"
        )
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_global_structure" in _domains(report)
    finally:
        connection.close()


def test_plan_kind_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plans SET kind = 'wrong' WHERE id = 'plan-1'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_semantics" in _domains(report)
    finally:
        connection.close()


def test_requested_minutes_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plans SET requested_minutes = requested_minutes + 1 WHERE id = 'plan-1'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_semantics" in _domains(report)
    finally:
        connection.close()


def test_allocated_minutes_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plans SET allocated_minutes = allocated_minutes + 5 WHERE id = 'plan-1'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_semantics" in _domains(report)
    finally:
        connection.close()


def test_raw_plan_difference_is_not_normalized_away(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        payload = json.loads(legacy.weekly_path.read_text(encoding="utf-8"))
        payload["plans"][0]["course_name"] = " Synthetic Linear Algebra "
        legacy.weekly_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "raw_plan_evidence" in _domains(report)
    finally:
        connection.close()


def test_source_hash_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        legacy.weekly_path.write_text(legacy.weekly_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "source_hash" in _domains(report)
    finally:
        connection.close()


def test_item_minutes_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET minutes = minutes + 1 WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_item_semantics" in _domains(report)
    finally:
        connection.close()


def test_item_action_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET action = 'Different action' WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_item_semantics" in _domains(report)
    finally:
        connection.close()


def test_item_score_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        target = connection.execute("SELECT id FROM study_plan_items WHERE score IS NOT NULL LIMIT 1").fetchone()[0]
        connection.execute("UPDATE study_plan_items SET score = score + 1 WHERE id = ?", (target,))
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_item_semantics" in _domains(report)
    finally:
        connection.close()


def test_item_status_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET status = 'completed' WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_item_semantics" in _domains(report)
    finally:
        connection.close()


def test_item_order_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET ordinal = 99 WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "plan_item_semantics" in _domains(report)
    finally:
        connection.close()


def test_wrong_plan_ownership_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        other_plan = connection.execute("SELECT id FROM study_plans WHERE id <> 'plan-1' ORDER BY id LIMIT 1").fetchone()[0]
        connection.execute("UPDATE study_plan_items SET plan_id = ? WHERE id = 'item-2'", (other_plan,))
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_wrong_course_relationship_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET course_id = 'fixture-cy100n' WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_wrong_topic_relationship_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET topic_id = 'topic-atomic' WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_cross_course_topic_relationship_is_detected_even_if_ledger_changed(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET topic_id = 'topic-atomic' WHERE id = 'item-2'")
        row = connection.execute("SELECT rowid, details_json FROM migration_imports WHERE target_id = 'item-2'").fetchone()
        details = json.loads(row[1])
        details["target_topic_id"] = "topic-atomic"
        connection.execute("UPDATE migration_imports SET details_json = ? WHERE rowid = ?", (json.dumps(details), row[0]))
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_missing_course_target_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM courses WHERE id = 'fixture-ma103n'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_missing_topic_target_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM topics WHERE id = 'topic-linear'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_unexpected_cross_domain_item_link_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute("UPDATE study_plan_items SET assessment_id = 'unexpected' WHERE id = 'item-2'")
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()


def test_historical_rows_are_deferred_not_current_authority(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute(
            "INSERT INTO study_plans VALUES ('historical-plan','weekly','week','2026-09-01','2026-09-07',60,60,'proposed','weekly_planner','V9.1','legacy study-plan import','2026-09-01','2026-09-01')"
        )
        connection.execute(
            "INSERT INTO migration_imports VALUES (?, ?, 'legacy_json', '1', 'old-plan-key', 'study_plans', 'historical-plan', '2026-09-01T00:00:00Z', ?)",
            (WEEKLY_SOURCE_PATH, "oldhash", json.dumps({"kind": "study_plan", "raw": {"id": "old"}})),
        )
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert any(item.domain == "historical_rows" and item.status == "deferred" for item in report.diagnostics)
        assert report.is_semantically_equal
    finally:
        connection.close()


def test_optional_intelligent_store_absence_can_match(tmp_path):
    legacy, connection, _, dual = _setup(tmp_path, include_intelligent=False)
    try:
        state = dual.load_state()
        assert state["intelligent"] is None
        intelligent = [
            d for d in dual.last_report.diagnostics
            if d.source_path == INTELLIGENT_SOURCE_PATH and d.domain == "source_presence"
        ][0]
        assert intelligent.status == "matched"
    finally:
        connection.close()


def test_sqlite_failure_does_not_replace_legacy_result(tmp_path):
    legacy = _copy_sources(tmp_path)

    class BrokenShadow:
        def parity_snapshot(self):
            raise RuntimeError("shadow unavailable")

    dual = DualReadStudyPlanRepository(legacy, BrokenShadow())
    assert dual.load_state() == legacy.load_state()
    assert dual.last_report.status == "mismatch"
    assert dual.last_report.diagnostics[0].domain == "sqlite_read"


def test_diagnostic_sink_failure_does_not_break_legacy_result(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        dual = DualReadStudyPlanRepository(
            legacy,
            sqlite_repo,
            diagnostic_sink=lambda _report: (_ for _ in ()).throw(RuntimeError("sink")),
        )
        assert dual.load_state() == legacy.load_state()
        assert dual.last_report is not None
    finally:
        connection.close()


def test_dual_read_save_writes_legacy_only(tmp_path):
    legacy, connection, sqlite_repo, dual = _setup(tmp_path)
    try:
        before = sqlite_repo.parity_snapshot()
        store = legacy.load_weekly_store()
        store["plans"][0]["message"] = "legacy-only write"
        dual.save_weekly_store(store)
        after = sqlite_repo.parity_snapshot()
        assert after == before
        assert legacy.load_weekly_store()["plans"][0]["message"] == "legacy-only write"
    finally:
        connection.close()


def test_dual_read_preserves_legacy_bytes_and_hashes(tmp_path):
    legacy, connection, _, dual = _setup(tmp_path)
    try:
        paths = [legacy.weekly_path, legacy.multi_course_path, legacy.intelligent_path]
        before = [(path.read_bytes(), _sha(path)) for path in paths]
        dual.load_state()
        after = [(path.read_bytes(), _sha(path)) for path in paths]
        assert after == before
    finally:
        connection.close()


def test_dual_read_preserves_sqlite_rows_and_total_changes(tmp_path):
    _, connection, _, dual = _setup(tmp_path)
    try:
        before_changes = connection.total_changes
        before_rows = connection.execute("SELECT * FROM study_plans ORDER BY id").fetchall()
        before_items = connection.execute("SELECT * FROM study_plan_items ORDER BY id").fetchall()
        dual.load_state()
        assert connection.total_changes == before_changes
        assert connection.execute("SELECT * FROM study_plans ORDER BY id").fetchall() == before_rows
        assert connection.execute("SELECT * FROM study_plan_items ORDER BY id").fetchall() == before_items
    finally:
        connection.close()


def test_repeated_dual_reads_are_deterministic_and_side_effect_free(tmp_path):
    _, connection, _, dual = _setup(tmp_path)
    try:
        before = connection.total_changes
        first = dual.load_state()
        first_report = dual.last_report.to_dict()
        second = dual.load_state()
        second_report = dual.last_report.to_dict()
        assert second == first
        assert second_report == first_report
        assert connection.total_changes == before
    finally:
        connection.close()


def test_integrity_and_foreign_key_checks_are_clean(tmp_path):
    _, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        result = sqlite_repo.integrity_checks()
        assert result["integrity_check"] == (("ok",),)
        assert result["foreign_key_check"] == ()
    finally:
        connection.close()


def test_factory_accepts_only_legacy_and_dual_read(tmp_path):
    legacy = _copy_sources(tmp_path)
    assert build_study_plan_repository("legacy", legacy_repository=legacy) is legacy
    with pytest.raises(ValueError):
        StudyPlanBackendConfig("sqlite")


def test_dual_read_factory_requires_explicit_sqlite(tmp_path):
    legacy = _copy_sources(tmp_path)
    with pytest.raises(ValueError):
        build_study_plan_repository("dual_read", legacy_repository=legacy)


def test_factory_with_explicit_connection_builds_dual_read(tmp_path):
    legacy, connection, _, _ = _setup(tmp_path)
    try:
        repo = build_study_plan_repository(
            "dual_read",
            legacy_repository=legacy,
            sqlite_connection=connection,
        )
        assert isinstance(repo, DualReadStudyPlanRepository)
        assert repo.load_state() == legacy.load_state()
    finally:
        connection.close()


def test_source_version_mismatch_is_detected(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        connection.execute(
            "UPDATE migration_imports SET source_version = '99' WHERE source_path = ?",
            (WEEKLY_SOURCE_PATH,),
        )
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "source_version" in _domains(report)
    finally:
        connection.close()


def test_duplicate_current_legacy_identity_is_structural_mismatch(tmp_path):
    legacy, connection, sqlite_repo, _ = _setup(tmp_path)
    try:
        row = connection.execute(
            "SELECT source_hash, source_version, legacy_key, details_json FROM migration_imports "
            "WHERE source_path = ? AND target_table = 'study_plans' LIMIT 1",
            (WEEKLY_SOURCE_PATH,),
        ).fetchone()
        connection.execute(
            "INSERT INTO study_plans VALUES ('duplicate-plan','weekly','week','2026-09-15','2026-09-21',120,120,'proposed','weekly_planner','V9.1','legacy study-plan import','2026-09-15','2026-09-15')"
        )
        connection.execute(
            "INSERT INTO migration_imports VALUES (?, ?, 'legacy_json', ?, ?, 'study_plans', 'duplicate-plan', '2026-09-15T06:31:00Z', ?)",
            (WEEKLY_SOURCE_PATH, row[0], row[1], row[2], row[3]),
        )
        connection.commit()
        report = compare_study_plan_parity(legacy, legacy.load_state(), sqlite_repo.parity_snapshot())
        assert "sqlite_structure" in _domains(report)
    finally:
        connection.close()
