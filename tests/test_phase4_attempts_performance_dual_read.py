from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.attempt_performance_backend import (
    AttemptPerformanceBackendConfig,
    DualReadAttemptPerformanceRepository,
    build_attempt_performance_repository,
)
from personal_learning_assistant.repositories.json.attempt_performance_repository import (
    LegacyJsonAttemptPerformanceRepository,
)
from personal_learning_assistant.repositories.sqlite.attempt_performance_repository import (
    SQLiteAttemptPerformanceRepository,
    SQLiteAttemptPerformanceRepositoryReadOnlyError,
    SQLiteAttemptPerformanceRepositorySchemaError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "phase4" / "attempts_performance_workspace.json"
IMPORTED_AT = "2026-09-15T01:40:00Z"
SOURCE_PATH = "data/assessment_workspace.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy(tmp_path: Path):
    path = tmp_path / "assessment_workspace.json"
    shutil.copyfile(FIXTURE, path)
    return path, LegacyJsonAttemptPerformanceRepository(path=path)


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE migration_imports (
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_version TEXT NOT NULL,
            legacy_key TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_id TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        CREATE TABLE questions (
            id TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            max_marks_milli INTEGER,
            status TEXT NOT NULL,
            user_notes TEXT NOT NULL DEFAULT '',
            import_batch_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE question_attempts (
            id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
            attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
            outcome TEXT NOT NULL,
            earned_marks_milli INTEGER CHECK (earned_marks_milli IS NULL OR earned_marks_milli >= 0),
            max_marks_milli INTEGER CHECK (max_marks_milli IS NULL OR max_marks_milli >= 0),
            response_ref TEXT,
            feedback_ref TEXT,
            occurred_at TEXT NOT NULL,
            UNIQUE(question_id, attempt_number),
            CHECK (earned_marks_milli IS NULL OR max_marks_milli IS NULL OR earned_marks_milli <= max_marks_milli)
        );
        CREATE TABLE mistake_events (
            id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL REFERENCES question_attempts(id) ON DELETE RESTRICT,
            category TEXT NOT NULL,
            mistake_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );
        """
    )


def _ledger(
    connection: sqlite3.Connection,
    *,
    source_hash: str,
    legacy_key: str,
    target_table: str,
    target_id: str,
    details: dict,
    imported_at: str = IMPORTED_AT,
) -> None:
    connection.execute(
        "INSERT INTO migration_imports "
        "(source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json) "
        "VALUES (?, ?, 'legacy_json', '1', ?, ?, ?, ?, ?)",
        (
            SOURCE_PATH,
            source_hash,
            legacy_key,
            target_table,
            target_id,
            imported_at,
            json.dumps(details, sort_keys=True, ensure_ascii=False),
        ),
    )


def _canonical_ref(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _install_shadow(connection: sqlite3.Connection, source_path: Path) -> None:
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    source_hash = _sha256(source_path)
    workspace = raw["workspaces"]["fixture-assessment-quiz-1"]
    q1, q2 = workspace["questions"]
    question_targets = {
        q1["id"]: "sqlite-performance-q1",
        q2["id"]: "sqlite-performance-q2",
    }

    for ordinal, question in enumerate((q1, q2), start=1):
        target = question_targets[question["id"]]
        connection.execute(
            "INSERT INTO questions "
            "(id, assessment_id, ordinal, question_text, max_marks_milli, status, "
            "user_notes, created_at, updated_at, deleted_at) "
            "VALUES (?, 'sqlite-assessment-quiz-1', ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                target,
                ordinal,
                question["text"],
                int(question["marks"] * 1000),
                question["status"],
                question.get("notes", ""),
                question.get("created_at", IMPORTED_AT),
                question.get("updated_at", IMPORTED_AT),
            ),
        )
        qkey = "assessment:id:fixture-assessment-quiz-1/question:id:{}".format(
            question["id"]
        )
        _ledger(
            connection,
            source_hash=source_hash,
            legacy_key=qkey,
            target_table="questions",
            target_id=target,
            details={
                "kind": "assessment_question_raw_unit",
                "legacy_id": question["id"],
                "assessment_legacy_key": "assessment:id:fixture-assessment-quiz-1",
                "ordinal": ordinal,
                "raw": question,
            },
            imported_at="2026-09-15T01:35:00Z",
        )

    # q1: one top-level attempt, then two V10.4 nested attempts.
    attempt_specs = [
        (q1, "sqlite-performance-q1", "attempts", 1, 1, "sqlite-attempt-q1-top"),
        (q1, "sqlite-performance-q1", "performance.attempts", 1, 2, "sqlite-attempt-q1-p1"),
        (q1, "sqlite-performance-q1", "performance.attempts", 2, 3, "sqlite-attempt-q1-p2"),
        (q2, "sqlite-performance-q2", "performance.attempts", 1, 1, "sqlite-attempt-q2-p1"),
    ]
    attempt_key_to_target = {}
    mistake_number = 0
    for question, question_target, origin, position, attempt_number, attempt_target in attempt_specs:
        raw_attempts = (
            question["attempts"]
            if origin == "attempts"
            else question["performance"]["attempts"]
        )
        attempt = raw_attempts[position - 1]
        qkey = "assessment:id:fixture-assessment-quiz-1/question:id:{}".format(
            question["id"]
        )
        akey = "{}/attempt:{}:{}".format(qkey, origin, position)
        attempt_key_to_target[akey] = attempt_target
        outcome = attempt["outcome"]
        weight = attempt.get(
            "weight",
            {"correct": 1.0, "partially_correct": 0.5, "wrong": 0.0, "stuck": 0.0}.get(outcome, 0.0),
        )
        earned = attempt.get("earned_marks")
        maximum = attempt.get("max_marks", question.get("marks"))
        earned_milli = None if earned is None else int(float(earned) * 1000)
        max_milli = None if maximum is None else int(float(maximum) * 1000)
        connection.execute(
            "INSERT INTO question_attempts "
            "(id, question_id, attempt_number, outcome, earned_marks_milli, "
            "max_marks_milli, response_ref, feedback_ref, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_target,
                question_target,
                attempt_number,
                outcome,
                earned_milli,
                max_milli,
                _canonical_ref(attempt.get("response_ref", attempt.get("response"))),
                _canonical_ref(attempt.get("feedback_ref", attempt.get("feedback"))),
                attempt["time"],
            ),
        )
        _ledger(
            connection,
            source_hash=source_hash,
            legacy_key=akey,
            target_table="question_attempts",
            target_id=attempt_target,
            details={
                "kind": "question_attempt",
                "assessment_legacy_key": "assessment:id:fixture-assessment-quiz-1",
                "question_legacy_key": qkey,
                "raw_question_id": question["id"],
                "attempt_number": attempt_number,
                "outcome": outcome,
                "weight": weight,
                "raw": attempt,
            },
        )
        mistake = attempt.get("mistake")
        if isinstance(mistake, str) and mistake.strip():
            mistake_number += 1
            mkey = akey + "/mistake:legacy_attempt"
            mtarget = "sqlite-mistake-{}".format(mistake_number)
            connection.execute(
                "INSERT INTO mistake_events "
                "(id, attempt_id, category, mistake_text, created_at, resolved_at) "
                "VALUES (?, ?, 'legacy_attempt_mistake', ?, ?, NULL)",
                (mtarget, attempt_target, mistake.strip(), attempt["time"]),
            )
            _ledger(
                connection,
                source_hash=source_hash,
                legacy_key=mkey,
                target_table="mistake_events",
                target_id=mtarget,
                details={
                    "kind": "mistake_event",
                    "question_legacy_key": qkey,
                    "attempt_legacy_key": akey,
                    "raw": {"attempt_id": attempt_target, "mistake": mistake},
                },
            )
    connection.commit()


def _prepared(tmp_path: Path):
    source_path, legacy = _legacy(tmp_path)
    connection = sqlite3.connect(tmp_path / "phase4_5_shadow.db")
    _schema(connection)
    _install_shadow(connection, source_path)
    sqlite_repo = SQLiteAttemptPerformanceRepository(connection)
    dual = DualReadAttemptPerformanceRepository(legacy, sqlite_repo)
    return source_path, legacy, connection, sqlite_repo, dual


def _domains(report):
    return {item.domain: item for item in report.diagnostics}


def _sqlite_fingerprint(connection: sqlite3.Connection):
    result = {}
    for table in ("migration_imports", "questions", "question_attempts", "mistake_events"):
        result[table] = tuple(
            tuple(row)
            for row in connection.execute("SELECT * FROM {} ORDER BY rowid".format(table)).fetchall()
        )
    return result


def test_sqlite_repository_contract_and_write_rejection(tmp_path):
    _, _, connection, repository, _ = _prepared(tmp_path)
    try:
        snapshot = repository.parity_snapshot()
        assert len(snapshot["current_attempt_rows"]) == 4
        assert len(snapshot["current_mistake_rows"]) == 3
        assert snapshot["source_hash"]
        assert snapshot["anomalies"] == ()
        with pytest.raises(SQLiteAttemptPerformanceRepositoryReadOnlyError):
            repository.save_state({})
    finally:
        connection.close()


def test_clean_dual_read_returns_exact_legacy_with_only_standalone_deferred(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        expected = legacy.load_state()
        actual = dual.load_state()
        assert actual == expected
        assert actual is not expected
        assert dual.last_report.mismatch_count == 0
        assert dual.last_report.status == "pass_with_deferred"
        domains = _domains(dual.last_report)
        assert domains["standalone_mistakes"].status == "deferred"
        assert domains["attempt_semantics_and_order"].status == "matched"
        assert domains["question_performance_summary"].status == "matched"
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("sql", "domain"),
    (
        ("UPDATE question_attempts SET outcome='wrong' WHERE id='sqlite-attempt-q1-p2'", "attempt_semantics_and_order"),
        ("UPDATE question_attempts SET earned_marks_milli=3000 WHERE id='sqlite-attempt-q1-p2'", "attempt_semantics_and_order"),
        ("UPDATE question_attempts SET response_ref='changed' WHERE id='sqlite-attempt-q1-p1'", "attempt_semantics_and_order"),
        ("UPDATE question_attempts SET feedback_ref='changed' WHERE id='sqlite-attempt-q1-p1'", "attempt_semantics_and_order"),
        ("UPDATE question_attempts SET occurred_at='2099-01-01T00:00:00' WHERE id='sqlite-attempt-q1-p1'", "attempt_semantics_and_order"),
    ),
)
def test_attempt_field_mismatches_are_explicit(tmp_path, sql, domain):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute(sql)
        connection.commit()
        expected = legacy.load_state()
        assert dual.load_state() == expected
        assert _domains(dual.last_report)[domain].status == "mismatch"
        assert dual.last_report.mismatch_count > 0
    finally:
        connection.close()


def test_attempt_number_and_order_mismatch_is_detected(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute("UPDATE question_attempts SET attempt_number=9 WHERE id='sqlite-attempt-q1-p2'")
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        domains = _domains(dual.last_report)
        assert domains["attempt_semantics_and_order"].status == "mismatch"
        assert domains["sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_wrong_question_ownership_is_structural_corruption(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        # Free the q2 attempt-number slot first so the UNIQUE constraint remains valid.
        connection.execute("UPDATE question_attempts SET attempt_number=2 WHERE id='sqlite-attempt-q2-p1'")
        connection.execute(
            "UPDATE question_attempts SET question_id='sqlite-performance-q2', attempt_number=1 "
            "WHERE id='sqlite-attempt-q1-top'"
        )
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_exact_raw_performance_evidence_mismatch_is_not_normalized_away(tmp_path):
    source_path, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
        data["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["performance"]["attempts"][0]["mistake"] += "  "
        source_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["raw_performance_evidence"].status == "mismatch"
        assert _domains(dual.last_report)["source_hash"].status == "mismatch"
    finally:
        connection.close()


def test_mistake_text_mismatch_is_explicit(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute("UPDATE mistake_events SET mistake_text='changed' WHERE id='sqlite-mistake-2'")
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["attempt_attached_mistakes"].status == "mismatch"
        assert _domains(dual.last_report)["sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_mistake_parent_ownership_is_validated(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute("UPDATE mistake_events SET attempt_id='sqlite-attempt-q1-p2' WHERE id='sqlite-mistake-2'")
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


@pytest.mark.parametrize(
    "sql",
    (
        "UPDATE mistake_events SET category='other' WHERE id='sqlite-mistake-1'",
        "UPDATE mistake_events SET resolved_at='2026-09-15T02:00:00' WHERE id='sqlite-mistake-1'",
    ),
)
def test_mistake_category_and_resolution_corruption_are_detected(tmp_path, sql):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute(sql)
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_performance_summary_detects_relational_changes(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute("UPDATE question_attempts SET earned_marks_milli=1000 WHERE id='sqlite-attempt-q1-p1'")
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["question_performance_summary"].status == "mismatch"
    finally:
        connection.close()


def test_unledgered_attempt_is_structural_anomaly(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute(
            "INSERT INTO question_attempts VALUES "
            "('rogue-attempt','sqlite-performance-q2',2,'wrong',NULL,3000,NULL,NULL,'2026-09-15T03:00:00')"
        )
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_unledgered_mistake_is_structural_anomaly(tmp_path):
    _, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        connection.execute(
            "INSERT INTO mistake_events VALUES "
            "('rogue-mistake','sqlite-attempt-q1-p2','legacy_attempt_mistake','rogue','2026-09-15T03:00:00',NULL)"
        )
        connection.commit()
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["sqlite_structure"].status == "mismatch"
    finally:
        connection.close()


def test_historical_attempt_and_mistake_are_deferred_not_current(tmp_path):
    source_path, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        old_hash = "0" * 64
        connection.execute(
            "INSERT INTO question_attempts VALUES "
            "('old-attempt','sqlite-performance-q2',2,'wrong',0,3000,NULL,NULL,'2026-09-14T00:00:00')"
        )
        _ledger(
            connection,
            source_hash=old_hash,
            legacy_key="assessment:id:fixture-assessment-quiz-1/question:id:fixture-performance-question-2/attempt:performance.attempts:2",
            target_table="question_attempts",
            target_id="old-attempt",
            details={
                "kind": "question_attempt",
                "question_legacy_key": "assessment:id:fixture-assessment-quiz-1/question:id:fixture-performance-question-2",
                "attempt_number": 2,
                "weight": 0.0,
                "raw": {"outcome": "wrong"},
            },
            imported_at="2026-09-14T00:00:00Z",
        )
        connection.execute(
            "INSERT INTO mistake_events VALUES "
            "('old-mistake','old-attempt','legacy_attempt_mistake','old','2026-09-14T00:00:00',NULL)"
        )
        _ledger(
            connection,
            source_hash=old_hash,
            legacy_key="old/mistake:legacy_attempt",
            target_table="mistake_events",
            target_id="old-mistake",
            details={"kind": "mistake_event", "attempt_legacy_key": "old-attempt-key", "raw": {"mistake": "old"}},
            imported_at="2026-09-14T00:00:00Z",
        )
        connection.commit()
        assert _sha256(source_path)
        assert dual.load_state() == legacy.load_state()
        domains = _domains(dual.last_report)
        assert domains["historical_attempt_rows"].status == "deferred"
        assert domains["historical_mistake_rows"].status == "deferred"
        assert domains["sqlite_structure"].status == "matched"
    finally:
        connection.close()


def test_standalone_mistake_lists_are_deferred_and_not_fabricated(tmp_path):
    _, legacy, connection, repository, dual = _prepared(tmp_path)
    try:
        snapshot = repository.parity_snapshot()
        assert len(snapshot["current_mistake_rows"]) == 3
        assert dual.load_state() == legacy.load_state()
        diagnostic = _domains(dual.last_report)["standalone_mistakes"]
        assert diagnostic.status == "deferred"
        assert "performance.mistakes" in repr(diagnostic.legacy_value)
    finally:
        connection.close()


def test_both_attempt_origins_preserve_meaningful_order(tmp_path):
    _, legacy, connection, repository, dual = _prepared(tmp_path)
    try:
        rows = repository.parity_snapshot()["current_attempt_rows"]
        q1 = [item for item in rows if item["question_id"] == "fixture-performance-question-1"]
        assert [(item["origin"], item["origin_position"], item["attempt_number"]) for item in q1] == [
            ("attempts", 1, 1),
            ("performance.attempts", 1, 2),
            ("performance.attempts", 2, 3),
        ]
        assert dual.load_state() == legacy.load_state()
        assert _domains(dual.last_report)["attempt_semantics_and_order"].status == "matched"
    finally:
        connection.close()


def test_alias_normalization_remains_visible_when_it_changes_application_summary(tmp_path):
    source_path, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
        data["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["performance"]["attempts"][0]["outcome"] = "partially correct"
        source_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        assert dual.load_state() == legacy.load_state()
        domains = _domains(dual.last_report)
        assert domains["raw_performance_evidence"].status == "mismatch"
        assert domains["question_performance_summary"].status == "mismatch"
    finally:
        connection.close()


def test_sqlite_shadow_failure_never_replaces_legacy_result(tmp_path):
    _, legacy = _legacy(tmp_path)

    class BrokenShadow:
        def parity_snapshot(self):
            raise RuntimeError("synthetic shadow failure")

    dual = DualReadAttemptPerformanceRepository(legacy, BrokenShadow())
    expected = legacy.load_state()
    assert dual.load_state() == expected
    assert dual.last_report.status == "mismatch"
    assert dual.last_report.diagnostics[0].domain == "sqlite_read"


def test_diagnostic_sink_failure_never_breaks_legacy_read(tmp_path):
    _, legacy, connection, repository, _ = _prepared(tmp_path)
    try:
        def bad_sink(report):
            raise RuntimeError("synthetic sink failure")

        dual = DualReadAttemptPerformanceRepository(legacy, repository, bad_sink)
        assert dual.load_state() == legacy.load_state()
        assert dual.last_report is not None
    finally:
        connection.close()


def test_reads_preserve_legacy_bytes_sqlite_state_and_integrity(tmp_path):
    source_path, legacy, connection, repository, dual = _prepared(tmp_path)
    try:
        before_bytes = source_path.read_bytes()
        before_hash = _sha256(source_path)
        before_sqlite = _sqlite_fingerprint(connection)
        before_changes = connection.total_changes

        assert dual.load_state() == legacy.load_state()
        repository.load_state()
        checks = repository.integrity_checks()

        assert source_path.read_bytes() == before_bytes
        assert _sha256(source_path) == before_hash
        assert _sqlite_fingerprint(connection) == before_sqlite
        assert connection.total_changes == before_changes
        assert checks["integrity_check"] == ("ok",)
        assert checks["foreign_key_check"] == ()
        assert checks["pass"] is True
    finally:
        connection.close()


def test_factory_allows_only_legacy_and_dual_read_with_explicit_sqlite(tmp_path):
    path, legacy = _legacy(tmp_path)
    assert isinstance(
        build_attempt_performance_repository("legacy", legacy_path=path),
        LegacyJsonAttemptPerformanceRepository,
    )
    with pytest.raises(ValueError):
        AttemptPerformanceBackendConfig("sqlite")
    with pytest.raises(ValueError, match="explicit SQLite"):
        build_attempt_performance_repository("dual_read", legacy_repository=legacy)

    connection = sqlite3.connect(tmp_path / "factory.db")
    _schema(connection)
    _install_shadow(connection, path)
    try:
        built = build_attempt_performance_repository(
            "dual_read",
            legacy_repository=legacy,
            sqlite_connection=connection,
        )
        assert isinstance(built, DualReadAttemptPerformanceRepository)
    finally:
        connection.close()


def test_sqlite_repository_rejects_incomplete_schema(tmp_path):
    connection = sqlite3.connect(tmp_path / "bad.db")
    try:
        connection.execute("CREATE TABLE migration_imports (id INTEGER)")
        with pytest.raises(SQLiteAttemptPerformanceRepositorySchemaError):
            SQLiteAttemptPerformanceRepository(connection)
    finally:
        connection.close()


def test_dual_save_writes_only_legacy_and_leaves_sqlite_unchanged(tmp_path):
    source_path, legacy, connection, _, dual = _prepared(tmp_path)
    try:
        state = legacy.load_state()
        state["workspaces"]["fixture-assessment-quiz-1"]["questions"][1]["performance"]["attempts"].append(
            {
                "time": "2026-09-15T02:30:00",
                "outcome": "correct",
                "weight": 1.0,
                "earned_marks": 3,
                "max_marks": 3,
                "mistake": "",
            }
        )
        before_sqlite = _sqlite_fingerprint(connection)
        saved = dual.save_state(state)
        assert saved == legacy.load_state()
        assert _sqlite_fingerprint(connection) == before_sqlite
        assert source_path.exists()
        assert dual.load_state() == legacy.load_state()
        assert dual.last_report.mismatch_count > 0
    finally:
        connection.close()
