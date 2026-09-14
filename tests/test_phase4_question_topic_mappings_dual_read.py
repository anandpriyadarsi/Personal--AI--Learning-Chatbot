from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.json.question_topic_mapping_repository import (
    LegacyJsonQuestionTopicMappingRepository,
)
from personal_learning_assistant.repositories.question_topic_backend import (
    DualReadQuestionTopicMappingRepository,
    QuestionTopicBackendConfig,
    build_question_topic_mapping_repository,
)
from personal_learning_assistant.repositories.sqlite.question_topic_mapping_repository import (
    SQLiteQuestionTopicMappingRepository,
    SQLiteQuestionTopicMappingRepositoryReadOnlyError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "phase4" / "question_topic_mappings_workspace.json"
IMPORTED_AT = "2026-09-15T01:00:00Z"
COURSE_IMPORTED_AT = "2026-09-14T18:00:00Z"
ASSESSMENT_IMPORTED_AT = "2026-09-14T18:10:00Z"
COURSE_HASH = "c" * 64
ASSESSMENT_HASH = "a" * 64


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database_fingerprint(connection: sqlite3.Connection) -> str:
    return hashlib.sha256("\n".join(connection.iterdump()).encode("utf-8")).hexdigest()


def _copy_fixture(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = data_dir / "assessment_workspace.json"
    target.write_bytes(FIXTURE.read_bytes())
    return target


def _ledger(
    connection: sqlite3.Connection,
    *,
    row_id: str,
    source_path: str,
    source_hash: str,
    source_version: str,
    legacy_key: str,
    target_table: str,
    target_id: str,
    imported_at: str,
    details: dict,
) -> None:
    connection.execute(
        "INSERT INTO migration_imports "
        "(id, source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json) "
        "VALUES (?, ?, ?, 'legacy_json', ?, ?, ?, ?, ?, ?)",
        (
            row_id,
            source_path,
            source_hash,
            source_version,
            legacy_key,
            target_table,
            target_id,
            imported_at,
            json.dumps(details, sort_keys=True),
        ),
    )


def _schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE migration_imports (
            id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_version TEXT NOT NULL DEFAULT '',
            legacy_key TEXT NOT NULL DEFAULT '',
            target_table TEXT NOT NULL,
            target_id TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE courses (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE assessments (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id),
            assessment_type TEXT NOT NULL,
            title TEXT NOT NULL,
            due_on TEXT,
            due_time TEXT,
            status TEXT NOT NULL,
            weight_bps INTEGER,
            max_points_milli INTEGER,
            earned_points_milli INTEGER,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE questions (
            id TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL REFERENCES assessments(id),
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
        CREATE TABLE question_topic_mappings (
            id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL REFERENCES questions(id),
            topic_id TEXT NOT NULL REFERENCES topics(id),
            score REAL,
            rank INTEGER,
            method TEXT NOT NULL,
            state TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        );
        """
    )


def _phase3_like_connection(tmp_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(tmp_path / "phase4-topic-shadow.db"), isolation_level=None)
    _schema(connection)

    connection.execute(
        "INSERT INTO courses VALUES "
        "('sqlite-course-ma', 'MA103N', 'Synthetic Linear Algebra', 'active', '', ?, ?, NULL), "
        "('sqlite-course-cy', 'CY100N', 'Synthetic Chemistry', 'active', '', ?, ?, NULL)",
        (COURSE_IMPORTED_AT, COURSE_IMPORTED_AT, COURSE_IMPORTED_AT, COURSE_IMPORTED_AT),
    )
    for idx, (target, legacy_id, code, name) in enumerate(
        (
            ("sqlite-course-ma", "fixture-ma103n", "MA103N", "Synthetic Linear Algebra"),
            ("sqlite-course-cy", "fixture-cy100n", "CY100N", "Synthetic Chemistry"),
        )
    ):
        _ledger(
            connection,
            row_id=f"course-{idx}",
            source_path="data/courses.json",
            source_hash=COURSE_HASH,
            source_version="1",
            legacy_key=f"course:id:{legacy_id}",
            target_table="courses",
            target_id=target,
            imported_at=COURSE_IMPORTED_AT,
            details={"kind": "course", "legacy_id": legacy_id, "raw": {"id": legacy_id, "code": code, "name": name}},
        )

    topic_rows = (
        ("sqlite-topic-linear", "sqlite-course-ma", "Linear Systems", "linear systems"),
        ("sqlite-topic-rank", "sqlite-course-ma", "Matrix Rank", "matrix rank"),
        ("sqlite-topic-chem", "sqlite-course-cy", "Matrix Rank", "matrix rank"),
    )
    for idx, (target, course_id, name, normalized) in enumerate(topic_rows):
        connection.execute(
            "INSERT INTO topics VALUES (?, ?, ?, ?, ?, 'not_started', NULL, 'not_started', ?, ?, NULL)",
            (target, course_id, name, normalized, idx, COURSE_IMPORTED_AT, COURSE_IMPORTED_AT),
        )
        legacy_topic_id = f"fixture-topic-{idx}"
        _ledger(
            connection,
            row_id=f"topic-{idx}",
            source_path="data/courses.json",
            source_hash=COURSE_HASH,
            source_version="1",
            legacy_key=f"course:id:fixture/topic:id:{legacy_topic_id}",
            target_table="topics",
            target_id=target,
            imported_at=COURSE_IMPORTED_AT,
            details={"kind": "topic", "legacy_id": legacy_topic_id, "raw": {"id": legacy_topic_id, "name": name}},
        )

    connection.execute(
        "INSERT INTO assessments VALUES "
        "('sqlite-assessment-quiz', 'sqlite-course-ma', 'quiz', 'Synthetic Quiz', NULL, NULL, 'pending', NULL, NULL, NULL, '', ?, ?, NULL)",
        (ASSESSMENT_IMPORTED_AT, ASSESSMENT_IMPORTED_AT),
    )
    _ledger(
        connection,
        row_id="assessment-0",
        source_path="data/assessments.json",
        source_hash=ASSESSMENT_HASH,
        source_version="2",
        legacy_key="assessment:id:fixture-assessment-quiz-1",
        target_table="assessments",
        target_id="sqlite-assessment-quiz",
        imported_at=ASSESSMENT_IMPORTED_AT,
        details={"kind": "assessment", "legacy_id": "fixture-assessment-quiz-1", "raw": {"id": "fixture-assessment-quiz-1"}},
    )

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_hash = _sha256(FIXTURE)
    questions = raw["workspaces"]["fixture-assessment-quiz-1"]["questions"]
    q_targets = {}
    for index, item in enumerate(questions, start=1):
        qid = f"sqlite-question-{index}"
        q_targets[item["id"]] = qid
        connection.execute(
            "INSERT INTO questions VALUES (?, 'sqlite-assessment-quiz', ?, ?, NULL, 'not_started', '', ?, ?, ?, NULL)",
            (qid, index, item["text"], f"batch-{index}", item["created_at"], item["updated_at"]),
        )
        qkey = f"assessment:id:fixture-assessment-quiz-1/question:id:{item['id']}"
        _ledger(
            connection,
            row_id=f"question-{index}",
            source_path="data/assessment_workspace.json",
            source_hash=source_hash,
            source_version="1",
            legacy_key=qkey,
            target_table="questions",
            target_id=qid,
            imported_at=IMPORTED_AT,
            details={
                "kind": "assessment_question_raw_unit",
                "assessment_legacy_key": "assessment:id:fixture-assessment-quiz-1",
                "legacy_id": item["id"],
                "ordinal": index,
                "import_batch_id": f"batch-{index}",
                "raw": item,
            },
        )

    mapping_specs = {
        "fixture-question-1": [
            ("Linear Systems", "linear systems", "sqlite-topic-linear", 0.82, 1, "review_confirmed", "accepted", "legacy suggested + alternative + accepted_topic; confidence=high", "2026-09-15T00:10:00", "2026-09-15T00:10:00"),
            ("Matrix Rank", "matrix rank", "sqlite-topic-rank", 0.42, 2, "review_confirmed", "proposed", "legacy alternative; confidence=high", "2026-09-15T00:10:00", None),
        ],
        "fixture-question-2": [
            ("Matrix Rank", "matrix rank", "sqlite-topic-rank", 0.61, 1, "automatic_medium_suggestion", "proposed", "legacy suggested + alternative; confidence=medium", "2026-09-15T00:20:00", None),
            ("Linear Systems", "linear systems", "sqlite-topic-linear", 0.31, 2, "automatic_medium_suggestion", "proposed", "legacy alternative; confidence=medium", "2026-09-15T00:20:00", None),
        ],
        "fixture-question-3": [],
    }

    for index, item in enumerate(questions, start=1):
        qkey = f"assessment:id:fixture-assessment-quiz-1/question:id:{item['id']}"
        resolutions = []
        for rank_index, spec in enumerate(mapping_specs[item["id"]], start=1):
            raw_label, normalized, topic_target, *_ = spec
            resolutions.append(
                {
                    "legacy_key": f"{qkey}/topic:label:{normalized}",
                    "raw_label": raw_label,
                    "normalized_label": normalized,
                    "state": spec[6],
                    "resolution": "resolved",
                    "target_ids": [topic_target],
                }
            )
        _ledger(
            connection,
            row_id=f"observation-{index}",
            source_path="data/assessment_workspace.json",
            source_hash=source_hash,
            source_version="1",
            legacy_key=f"{qkey}/topic_mapping:observation",
            target_table="questions",
            target_id=q_targets[item["id"]],
            imported_at=IMPORTED_AT,
            details={
                "kind": "question_topic_mapping_observation",
                "question_legacy_key": qkey,
                "course_target_id": "sqlite-course-ma",
                "raw_topic": item.get("topic"),
                "raw_topic_mapping": item.get("topic_mapping"),
                "candidate_resolutions": resolutions,
            },
        )

        for spec_index, spec in enumerate(mapping_specs[item["id"]], start=1):
            raw_label, normalized, topic_target, score, rank, method, state, reason, created_at, reviewed_at = spec
            mapping_id = f"sqlite-mapping-{index}-{spec_index}"
            connection.execute(
                "INSERT INTO question_topic_mappings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mapping_id, q_targets[item["id"]], topic_target, score, rank, method, state, reason, created_at, reviewed_at),
            )
            _ledger(
                connection,
                row_id=f"mapping-ledger-{index}-{spec_index}",
                source_path="data/assessment_workspace.json",
                source_hash=source_hash,
                source_version="1",
                legacy_key=f"{qkey}/topic:label:{normalized}",
                target_table="question_topic_mappings",
                target_id=mapping_id,
                imported_at=IMPORTED_AT,
                details={
                    "kind": "question_topic_mapping",
                    "question_legacy_key": qkey,
                    "question_target_id": q_targets[item["id"]],
                    "course_target_id": "sqlite-course-ma",
                    "topic_target_id": topic_target,
                    "raw_label": raw_label,
                    "normalized_label": normalized,
                    "origins": ["synthetic"],
                    "raw_candidate": {},
                    "raw_topic": item.get("topic"),
                    "raw_topic_mapping": item.get("topic_mapping"),
                    "resolution": "exact_course_topic_name",
                },
            )

    return connection


def _repositories(tmp_path: Path, diagnostic_sink=None):
    legacy_path = _copy_fixture(tmp_path)
    legacy = LegacyJsonQuestionTopicMappingRepository(path=legacy_path)
    connection = _phase3_like_connection(tmp_path)
    sqlite_repo = SQLiteQuestionTopicMappingRepository(connection)
    dual = DualReadQuestionTopicMappingRepository(legacy, sqlite_repo, diagnostic_sink)
    return legacy_path, legacy, connection, sqlite_repo, dual


def _domain(report, name: str):
    return next(item for item in report.diagnostics if item.domain == name)


def test_sqlite_mapping_repository_read_contract_and_write_rejection(tmp_path):
    _, _, connection, sqlite_repo, _ = _repositories(tmp_path)
    try:
        snapshot = sqlite_repo.parity_snapshot()
        assert len(snapshot["raw_mapping_observations"]) == 3
        assert len(snapshot["current_mapping_rows"]) == 4
        assert snapshot["anomalies"] == ()
        with pytest.raises(SQLiteQuestionTopicMappingRepositoryReadOnlyError):
            sqlite_repo.save_state({})
    finally:
        connection.close()


def test_clean_dual_read_returns_exact_legacy_and_matches_current_mappings(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        actual = dual.load_state()
        assert actual == expected
        report = dual.last_report
        assert report is not None
        assert report.status == "pass"
        assert report.mismatch_count == 0
        for name in (
            "raw_mapping_observations",
            "source_version",
            "source_hash",
            "resolved_mapping_semantics",
            "sqlite_structure",
        ):
            assert _domain(report, name).status == "matched"
    finally:
        connection.close()


def test_mapping_score_mismatch_is_explicit_and_legacy_wins(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute("UPDATE question_topic_mappings SET score = 0.11 WHERE id = 'sqlite-mapping-1-1'")
        assert dual.load_state() == expected
        assert _domain(dual.last_report, "resolved_mapping_semantics").status == "mismatch"
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("rank", 9),
        ("method", "wrong-method"),
        ("state", "proposed"),
        ("reason", "wrong reason"),
        ("created_at", "2099-01-01T00:00:00"),
        ("reviewed_at", None),
    ),
)
def test_mapping_metadata_mismatches_are_not_normalized_away(tmp_path, column, value):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            f"UPDATE question_topic_mappings SET {column} = ? WHERE id = 'sqlite-mapping-1-1'",
            (value,),
        )
        dual.load_state()
        assert _domain(dual.last_report, "resolved_mapping_semantics").status == "mismatch"
    finally:
        connection.close()


def test_raw_topic_observation_mismatch_is_explicit(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute("SELECT details_json FROM migration_imports WHERE id = 'observation-1'").fetchone()
        details = json.loads(row[0])
        details["raw_topic"] = " Linear Systems "
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = 'observation-1'",
            (json.dumps(details, sort_keys=True),),
        )
        dual.load_state()
        assert _domain(dual.last_report, "raw_mapping_observations").status == "mismatch"
    finally:
        connection.close()


def test_mapping_question_relationship_corruption_is_detected(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute("UPDATE question_topic_mappings SET question_id = 'sqlite-question-2' WHERE id = 'sqlite-mapping-1-1'")
        assert dual.load_state() == expected
        assert _domain(dual.last_report, "sqlite_structure").status == "mismatch"
    finally:
        connection.close()


def test_mapping_topic_relationship_corruption_is_detected(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute("UPDATE question_topic_mappings SET topic_id = 'sqlite-topic-rank' WHERE id = 'sqlite-mapping-1-1'")
        dual.load_state()
        assert _domain(dual.last_report, "sqlite_structure").status == "mismatch"
        assert _domain(dual.last_report, "resolved_mapping_semantics").status == "mismatch"
    finally:
        connection.close()


def test_cross_course_topic_corruption_is_detected(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute("UPDATE question_topic_mappings SET topic_id = 'sqlite-topic-chem' WHERE id = 'sqlite-mapping-1-2'")
        dual.load_state()
        diag = _domain(dual.last_report, "sqlite_structure")
        assert diag.status == "mismatch"
        assert any("crosses courses" in item for item in diag.sqlite_value)
    finally:
        connection.close()


def test_deleted_topic_is_detected(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute("UPDATE topics SET deleted_at = '2026-09-15T01:30:00Z' WHERE id = 'sqlite-topic-linear'")
        dual.load_state()
        assert _domain(dual.last_report, "sqlite_structure").status == "mismatch"
    finally:
        connection.close()


def test_duplicate_rank_is_detected(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute("UPDATE question_topic_mappings SET rank = 1 WHERE id = 'sqlite-mapping-1-2'")
        dual.load_state()
        diag = _domain(dual.last_report, "sqlite_structure")
        assert diag.status == "mismatch"
        assert any("duplicate current mapping rank" in item for item in diag.sqlite_value)
    finally:
        connection.close()


def test_unledgered_mapping_row_is_detected(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "INSERT INTO question_topic_mappings VALUES "
            "('rogue-map', 'sqlite-question-1', 'sqlite-topic-linear', 0.1, 7, 'rogue', 'proposed', '', ?, NULL)",
            (IMPORTED_AT,),
        )
        dual.load_state()
        diag = _domain(dual.last_report, "sqlite_structure")
        assert diag.status == "mismatch"
        assert any("unledgered" in item for item in diag.sqlite_value)
    finally:
        connection.close()


def test_historical_mapping_row_is_deferred_not_silently_current(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "INSERT INTO question_topic_mappings VALUES "
            "('old-map', 'sqlite-question-1', 'sqlite-topic-linear', 0.2, 8, 'old', 'proposed', '', '2026-09-14T00:00:00', NULL)"
        )
        _ledger(
            connection,
            row_id="old-map-ledger",
            source_path="data/assessment_workspace.json",
            source_hash="b" * 64,
            source_version="1",
            legacy_key="assessment:id:fixture-assessment-quiz-1/question:id:fixture-question-1/topic:label:old",
            target_table="question_topic_mappings",
            target_id="old-map",
            imported_at="2026-09-14T00:00:00Z",
            details={"kind": "question_topic_mapping"},
        )
        dual.load_state()
        assert _domain(dual.last_report, "sqlite_structure").status == "matched"
        assert _domain(dual.last_report, "historical_mapping_rows").status == "deferred"
    finally:
        connection.close()


def test_unresolved_candidate_is_deferred_and_not_guessed(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute("SELECT details_json FROM migration_imports WHERE id = 'observation-3'").fetchone()
        details = json.loads(row[0])
        details["raw_topic"] = "Unknown Topic"
        details["candidate_resolutions"] = [{
            "legacy_key": "x",
            "raw_label": "Unknown Topic",
            "normalized_label": "unknown topic",
            "state": "accepted",
            "resolution": "unresolved",
            "target_ids": [],
        }]
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = 'observation-3'",
            (json.dumps(details, sort_keys=True),),
        )
        # Make legacy raw evidence identical so this tests only deferral behavior.
        path = Path(dual.legacy_repository.path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["workspaces"]["fixture-assessment-quiz-1"]["questions"][2]["topic"] = "Unknown Topic"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Source hash intentionally differs now, proving exact hash parity catches source drift.
        dual.load_state()
        assert _domain(dual.last_report, "unresolved_mapping_candidates").status == "deferred"
        assert _domain(dual.last_report, "source_hash").status == "mismatch"
    finally:
        connection.close()


def test_sqlite_shadow_failure_never_replaces_legacy_result(tmp_path):
    _, legacy, connection, sqlite_repo, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute("DROP TABLE question_topic_mappings")
        assert dual.load_state() == expected
        assert _domain(dual.last_report, "sqlite_read").status == "error"
    finally:
        connection.close()


def test_diagnostic_sink_failure_never_breaks_legacy_read(tmp_path):
    def broken_sink(_report):
        raise RuntimeError("sink failed")

    _, legacy, connection, _, dual = _repositories(tmp_path, diagnostic_sink=broken_sink)
    try:
        expected = legacy.load_state()
        assert dual.load_state() == expected
        assert dual.last_report is not None
    finally:
        connection.close()


def test_reads_preserve_legacy_bytes_and_sqlite_state(tmp_path):
    legacy_path, _, connection, sqlite_repo, dual = _repositories(tmp_path)
    try:
        before_bytes = legacy_path.read_bytes()
        before_hash = _sha256(legacy_path)
        before_db = _database_fingerprint(connection)
        before_changes = connection.total_changes
        dual.load_state()
        sqlite_repo.load_state()
        checks = sqlite_repo.integrity_checks()
        assert legacy_path.read_bytes() == before_bytes
        assert _sha256(legacy_path) == before_hash
        assert _database_fingerprint(connection) == before_db
        assert connection.total_changes == before_changes
        assert checks["integrity_check"] == ("ok",)
        assert checks["foreign_key_check"] == ()
        assert checks["pass"] is True
    finally:
        connection.close()


def test_factory_supports_only_legacy_and_dual_read(tmp_path):
    path = _copy_fixture(tmp_path)
    legacy = build_question_topic_mapping_repository("legacy", legacy_path=path)
    assert isinstance(legacy, LegacyJsonQuestionTopicMappingRepository)
    with pytest.raises(ValueError):
        QuestionTopicBackendConfig("sqlite")
    with pytest.raises(ValueError, match="explicit SQLite"):
        build_question_topic_mapping_repository("dual_read", legacy_path=path)

    connection = _phase3_like_connection(tmp_path)
    try:
        dual = build_question_topic_mapping_repository(
            "dual_read", legacy_path=path, sqlite_connection=connection
        )
        assert isinstance(dual, DualReadQuestionTopicMappingRepository)
    finally:
        connection.close()


def test_dual_read_writes_only_legacy_json(tmp_path):
    legacy_path, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        before_db = _database_fingerprint(connection)
        state = legacy.load_state()
        state = deepcopy(state)
        state["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["topic"] = "Matrix Rank"
        saved = dual.save_state(state)
        assert saved["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["topic"] == "Matrix Rank"
        assert json.loads(legacy_path.read_text(encoding="utf-8"))["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["topic"] == "Matrix Rank"
        assert _database_fingerprint(connection) == before_db
    finally:
        connection.close()


def test_automatic_topic_mapping_module_is_not_required_for_repository_reads(tmp_path, monkeypatch):
    # Phase 4.4 compares stored decisions; it must not execute/recompute heuristic mapping.
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        assert dual.load_state() == expected
    finally:
        connection.close()
