from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.json.question_repository import (
    LegacyJsonQuestionRepository,
)
from personal_learning_assistant.repositories.question_backend import (
    DualReadQuestionRepository,
    QuestionBackendConfig,
    build_question_repository,
)
from personal_learning_assistant.repositories.sqlite.question_repository import (
    SQLiteQuestionRepository,
    SQLiteQuestionRepositoryReadOnlyError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "phase4" / "assessment_workspace.json"
WORKSPACE_SOURCE_HASH = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
ASSESSMENT_SOURCE_HASH = "a" * 64
IMPORTED_AT = "2026-09-15T00:35:00Z"
ASSESSMENT_IMPORTED_AT = "2026-09-15T00:30:00Z"


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


def _ledger_row(
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


def _phase3_like_connection(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "phase4-question-shadow.db"
    connection = sqlite3.connect(str(db), isolation_level=None)
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
        CREATE TABLE assessments (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            assessment_type TEXT NOT NULL,
            title TEXT NOT NULL,
            due_on TEXT,
            due_time TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
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
            assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            max_marks_milli INTEGER,
            status TEXT NOT NULL DEFAULT 'not_started',
            user_notes TEXT NOT NULL DEFAULT '',
            import_batch_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            UNIQUE (assessment_id, ordinal)
        );
        CREATE TABLE knowledge_documents (id TEXT PRIMARY KEY);
        CREATE TABLE resources (id TEXT PRIMARY KEY);
        CREATE TABLE note_metadata (id TEXT PRIMARY KEY);
        CREATE TABLE question_sources (
            id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
            document_id TEXT REFERENCES knowledge_documents(id) ON DELETE RESTRICT,
            resource_id TEXT REFERENCES resources(id) ON DELETE RESTRICT,
            note_id TEXT REFERENCES note_metadata(id) ON DELETE RESTRICT,
            page_number INTEGER,
            locator TEXT NOT NULL DEFAULT '',
            raw_source_label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE question_topic_mappings (
            id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
            topic_id TEXT NOT NULL,
            score REAL,
            rank INTEGER,
            method TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'proposed',
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        );
        """
    )

    assessment_targets = {
        "fixture-assessment-quiz-1": "sqlite-assessment-quiz",
        "fixture-assessment-project-1": "sqlite-assessment-project",
    }
    for index, (legacy_id, target_id) in enumerate(assessment_targets.items()):
        connection.execute(
            "INSERT INTO assessments VALUES (?, 'course', 'synthetic', ?, NULL, NULL, "
            "'pending', NULL, NULL, NULL, '', ?, ?, NULL)",
            (target_id, legacy_id, ASSESSMENT_IMPORTED_AT, ASSESSMENT_IMPORTED_AT),
        )
        _ledger_row(
            connection,
            row_id="assessment-ledger-{}".format(index),
            source_path="data/assessments.json",
            source_hash=ASSESSMENT_SOURCE_HASH,
            source_version="2",
            legacy_key="assessment:id:{}".format(legacy_id),
            target_table="assessments",
            target_id=target_id,
            imported_at=ASSESSMENT_IMPORTED_AT,
            details={"kind": "assessment", "legacy_id": legacy_id, "raw": {"id": legacy_id}},
        )

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    question_targets = {
        "fixture-question-1": "sqlite-question-1",
        "fixture-question-2": "sqlite-question-2",
        "fixture-question-3": "sqlite-question-3",
    }
    source_targets = {
        "fixture-question-1": "sqlite-source-1",
        "fixture-question-2": "sqlite-source-2",
    }
    batch = "synthetic-import-batch"
    question_counter = 0
    source_counter = 0
    for assessment_id, workspace in raw["workspaces"].items():
        assessment_target = assessment_targets[assessment_id]
        assessment_key = "assessment:id:{}".format(assessment_id)
        for position, item in enumerate(workspace["questions"]):
            question_counter += 1
            target_id = question_targets[item["id"]]
            status = item.get("status") or "not_started"
            marks = item.get("marks")
            marks_milli = None if marks is None else int(round(float(marks) * 1000))
            connection.execute(
                "INSERT INTO questions "
                "(id, assessment_id, ordinal, question_text, max_marks_milli, status, "
                "user_notes, import_batch_id, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    target_id,
                    assessment_target,
                    position + 1,
                    item["text"],
                    marks_milli,
                    status,
                    item.get("notes") or "",
                    batch,
                    item.get("created_at", IMPORTED_AT),
                    item.get("updated_at", item.get("created_at", IMPORTED_AT)),
                ),
            )
            question_key = "{}/question:id:{}".format(assessment_key, item["id"])
            _ledger_row(
                connection,
                row_id="question-ledger-{}".format(question_counter),
                source_path="data/assessment_workspace.json",
                source_hash=WORKSPACE_SOURCE_HASH,
                source_version="1",
                legacy_key=question_key,
                target_table="questions",
                target_id=target_id,
                imported_at=IMPORTED_AT,
                details={
                    "kind": "assessment_question_raw_unit",
                    "assessment_legacy_key": assessment_key,
                    "legacy_id": item["id"],
                    "ordinal": position + 1,
                    "import_batch_id": batch,
                    "parser_state": "review_required",
                    "topic_state": "deferred",
                    "performance_state": "deferred",
                    "raw": item,
                },
            )

            if item.get("source_file"):
                source_counter += 1
                source_id = source_targets[item["id"]]
                locator = "question:{}".format(item["source_question_number"])
                connection.execute(
                    "INSERT INTO question_sources "
                    "(id, question_id, document_id, resource_id, note_id, page_number, "
                    "locator, raw_source_label, created_at) "
                    "VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?)",
                    (
                        source_id,
                        target_id,
                        item.get("source_page"),
                        locator,
                        item["source_file"],
                        item.get("created_at", IMPORTED_AT),
                    ),
                )
                _ledger_row(
                    connection,
                    row_id="source-ledger-{}".format(source_counter),
                    source_path="data/assessment_workspace.json",
                    source_hash=WORKSPACE_SOURCE_HASH,
                    source_version="1",
                    legacy_key=question_key + "/source:legacy",
                    target_table="question_sources",
                    target_id=source_id,
                    imported_at=IMPORTED_AT,
                    details={
                        "kind": "question_source_raw_annotation",
                        "question_legacy_key": question_key,
                        "raw_source_label": item["source_file"],
                        "raw_page_number": item.get("source_page"),
                        "raw_question_number": item.get("source_question_number"),
                        "resolution_state": "review_required",
                    },
                )
    return connection


def _repositories(tmp_path: Path, diagnostic_sink=None):
    legacy_path = _copy_fixture(tmp_path)
    legacy = LegacyJsonQuestionRepository(path=legacy_path)
    connection = _phase3_like_connection(tmp_path)
    sqlite_repo = SQLiteQuestionRepository(connection)
    dual = DualReadQuestionRepository(legacy, sqlite_repo, diagnostic_sink=diagnostic_sink)
    return legacy_path, legacy, connection, sqlite_repo, dual


def _domain(report, name: str):
    return next(item for item in report.diagnostics if item.domain == name)


def test_sqlite_repository_read_contract_and_write_rejection(tmp_path):
    _, _, connection, sqlite_repo, _ = _repositories(tmp_path)
    try:
        state = sqlite_repo.load_state()
        assert state["version"] == 1
        assert list(state["workspaces"]) == [
            "fixture-assessment-quiz-1",
            "fixture-assessment-project-1",
        ]
        questions = state["workspaces"]["fixture-assessment-quiz-1"]["questions"]
        assert [item["id"] for item in questions] == [
            "fixture-question-1",
            "fixture-question-2",
        ]
        assert questions[0]["marks"] == 2.5
        assert questions[0]["status"] == "attempted"
        with pytest.raises(SQLiteQuestionRepositoryReadOnlyError):
            sqlite_repo.save_state(state)
    finally:
        connection.close()


def test_clean_dual_read_returns_exact_legacy_and_matches_supported_domains(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        actual = dual.load_state()
        assert actual == expected
        report = dual.last_report
        assert report is not None
        assert report.status == "pass_with_deferred"
        assert report.mismatch_count == 0
        for domain in (
            "question_catalogue",
            "question_statuses",
            "question_assessment_relationships",
            "question_ordering",
            "question_sources",
            "question_source_ordering",
            "question_source_identities",
            "raw_identities_and_statuses",
            "raw_question_records",
            "raw_question_source_evidence",
            "source_version",
            "source_hash",
            "sqlite_structure",
            "resolved_question_topic_mappings",
            "resolved_question_source_relationships",
        ):
            assert _domain(report, domain).status == "matched"
        assert _domain(report, "question_topic_mappings").status == "deferred"
        assert _domain(report, "workspace_metadata").status == "deferred"
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("sql", "domain"),
    (
        ("UPDATE questions SET question_text = 'Shadow text' WHERE id = 'sqlite-question-1'", "question_catalogue"),
        ("UPDATE questions SET status = 'completed' WHERE id = 'sqlite-question-1'", "question_statuses"),
        ("UPDATE questions SET max_marks_milli = 9000 WHERE id = 'sqlite-question-1'", "question_catalogue"),
        ("UPDATE questions SET user_notes = 'Shadow note' WHERE id = 'sqlite-question-1'", "question_catalogue"),
    ),
)
def test_question_field_mismatches_never_replace_legacy_result(tmp_path, sql, domain):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute(sql)
        assert dual.load_state() == expected
        assert _domain(dual.last_report, domain).status == "mismatch"
        assert _domain(dual.last_report, "sqlite_structure").status == "mismatch"
    finally:
        connection.close()



def test_question_identity_and_import_batch_mismatches_are_explicit(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute(
            "SELECT id, details_json FROM migration_imports WHERE id = 'question-ledger-1'"
        ).fetchone()
        details = json.loads(row[1])
        details["legacy_id"] = "different-question-id"
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = ?",
            (json.dumps(details, sort_keys=True), row[0]),
        )
        connection.execute(
            "UPDATE questions SET import_batch_id = 'wrong-batch' WHERE id = 'sqlite-question-2'"
        )
        dual.load_state()
        assert _domain(dual.last_report, "question_catalogue").status == "mismatch"
        assert _domain(dual.last_report, "raw_identities_and_statuses").status == "matched"
        structure = _domain(dual.last_report, "sqlite_structure")
        assert structure.status == "mismatch"
        assert any("import_batch_id" in item for item in structure.sqlite_value)
    finally:
        connection.close()


def test_question_source_identity_ledger_mismatch_is_not_hidden(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "UPDATE migration_imports SET legacy_key = "
            "'assessment:id:fixture-assessment-quiz-1/question:id:fixture-question-1/source:changed' "
            "WHERE id = 'source-ledger-1'"
        )
        dual.load_state()
        assert _domain(dual.last_report, "question_source_identities").status == "mismatch"
    finally:
        connection.close()

def test_actual_assessment_relationship_corruption_is_detected(tmp_path):
    _, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        expected = legacy.load_state()
        connection.execute(
            "UPDATE questions SET assessment_id = 'sqlite-assessment-project', ordinal = 2 "
            "WHERE id = 'sqlite-question-1'"
        )
        assert dual.load_state() == expected
        assert _domain(dual.last_report, "question_assessment_relationships").status == "mismatch"
        assert _domain(dual.last_report, "question_ordering").status == "mismatch"
        assert _domain(dual.last_report, "sqlite_structure").status == "mismatch"
    finally:
        connection.close()


def test_question_ordinal_order_mismatch_is_not_sorted_away(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute("UPDATE questions SET ordinal = 10 WHERE id = 'sqlite-question-1'")
        dual.load_state()
        diag = _domain(dual.last_report, "question_ordering")
        assert diag.status == "mismatch"
        assert "rather than sorted away" in diag.message
        assert _domain(dual.last_report, "question_source_ordering").status == "mismatch"
    finally:
        connection.close()


def test_raw_identity_status_difference_is_not_normalized_away(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        row = connection.execute(
            "SELECT id, details_json FROM migration_imports WHERE id = 'question-ledger-1'"
        ).fetchone()
        details = json.loads(row[1])
        details["raw"]["status"] = " attempted "
        connection.execute(
            "UPDATE migration_imports SET details_json = ? WHERE id = ?",
            (json.dumps(details, sort_keys=True), row[0]),
        )
        dual.load_state()
        assert _domain(dual.last_report, "question_statuses").status == "matched"
        assert _domain(dual.last_report, "raw_identities_and_statuses").status == "mismatch"
        assert _domain(dual.last_report, "raw_question_records").status == "mismatch"
    finally:
        connection.close()


def test_question_source_ownership_raw_page_locator_and_order_mismatches_are_explicit(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "UPDATE question_sources SET question_id = 'sqlite-question-2', "
            "raw_source_label = 'Changed.pdf', page_number = 9, locator = 'question:99' "
            "WHERE id = 'sqlite-source-1'"
        )
        dual.load_state()
        assert _domain(dual.last_report, "question_sources").status == "mismatch"
        assert _domain(dual.last_report, "question_source_ordering").status == "mismatch"
        assert _domain(dual.last_report, "sqlite_structure").status == "mismatch"
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("column", "table", "target_id"),
    (
        ("document_id", "knowledge_documents", "doc-1"),
        ("resource_id", "resources", "resource-1"),
        ("note_id", "note_metadata", "note-1"),
    ),
)
def test_reviewed_source_relationships_are_validated_and_explicitly_deferred(
    tmp_path, column, table, target_id
):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute("INSERT INTO {} (id) VALUES (?)".format(table), (target_id,))
        connection.execute(
            "UPDATE question_sources SET {} = ? WHERE id = 'sqlite-source-1'".format(column),
            (target_id,),
        )
        dual.load_state()
        assert _domain(dual.last_report, "sqlite_structure").status == "matched"
        resolved = _domain(dual.last_report, "resolved_question_source_relationships")
        assert resolved.status == "deferred"
        assert resolved.sqlite_value[0][column] == target_id
    finally:
        connection.close()


@pytest.mark.parametrize("column", ("document_id", "resource_id", "note_id"))
def test_missing_resolved_source_targets_are_structural_mismatches(tmp_path, column):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "UPDATE question_sources SET {} = 'missing-target' WHERE id = 'sqlite-source-1'".format(column)
        )
        connection.execute("PRAGMA foreign_keys = ON")
        dual.load_state()
        structure = _domain(dual.last_report, "sqlite_structure")
        assert structure.status == "mismatch"
        assert any(column in item and "missing target" in item for item in structure.sqlite_value)
    finally:
        connection.close()


def test_stale_rows_from_older_workspace_hash_are_detected(tmp_path):
    _, _, connection, _, dual = _repositories(tmp_path)
    try:
        connection.execute(
            "INSERT INTO questions VALUES "
            "('stale-question', 'sqlite-assessment-quiz', 9, 'Old question', NULL, "
            "'not_started', '', 'old-batch', '2026-09-14', '2026-09-14', NULL)"
        )
        _ledger_row(
            connection,
            row_id="old-question-ledger",
            source_path="data/assessment_workspace.json",
            source_hash="b" * 64,
            source_version="1",
            legacy_key="assessment:id:fixture-assessment-quiz-1/question:id:old",
            target_table="questions",
            target_id="stale-question",
            imported_at="2026-09-14T00:00:00Z",
            details={
                "kind": "assessment_question_raw_unit",
                "assessment_legacy_key": "assessment:id:fixture-assessment-quiz-1",
                "legacy_id": "old",
                "ordinal": 9,
                "import_batch_id": "old-batch",
                "raw": {"id": "old", "text": "Old question", "status": "not_started"},
            },
        )
        dual.load_state()
        structure = _domain(dual.last_report, "sqlite_structure")
        assert structure.status == "mismatch"
        assert any("older workspace imports" in item for item in structure.sqlite_value)
    finally:
        connection.close()


def test_sqlite_failure_and_diagnostic_sink_failure_never_break_legacy_read(tmp_path):
    def broken_sink(_report):
        raise RuntimeError("sink failure")

    _, legacy, connection, _, dual = _repositories(tmp_path, diagnostic_sink=broken_sink)
    try:
        expected = legacy.load_state()
        assert dual.load_state() == expected
        connection.execute("DROP TABLE migration_imports")
        assert dual.load_state() == expected
        assert dual.last_report is not None
        assert _domain(dual.last_report, "sqlite_read").status == "error"
    finally:
        connection.close()


def test_reads_preserve_legacy_bytes_hash_sqlite_state_and_integrity(tmp_path):
    legacy_path, _, connection, sqlite_repo, dual = _repositories(tmp_path)
    try:
        legacy_bytes = legacy_path.read_bytes()
        legacy_hash = _sha256(legacy_path)
        sqlite_fingerprint = _database_fingerprint(connection)
        total_changes = connection.total_changes

        dual.load_state()
        sqlite_repo.load_state()
        checks = sqlite_repo.integrity_checks()

        assert legacy_path.read_bytes() == legacy_bytes
        assert _sha256(legacy_path) == legacy_hash
        assert _database_fingerprint(connection) == sqlite_fingerprint
        assert connection.total_changes == total_changes
        assert checks["integrity_check"] == ("ok",)
        assert checks["foreign_key_check"] == ()
        assert checks["pass"] is True
    finally:
        connection.close()


def test_factory_supports_only_legacy_and_dual_read_and_never_opens_db_implicitly(tmp_path):
    path = _copy_fixture(tmp_path)
    legacy = build_question_repository("legacy", legacy_path=path)
    assert isinstance(legacy, LegacyJsonQuestionRepository)
    with pytest.raises(ValueError, match="explicit SQLite"):
        build_question_repository("dual_read", legacy_path=path)
    with pytest.raises(ValueError, match="legacy.*dual_read"):
        QuestionBackendConfig("sqlite")

    connection = _phase3_like_connection(tmp_path)
    try:
        dual = build_question_repository(
            "dual_read", legacy_path=path, sqlite_connection=connection
        )
        assert isinstance(dual, DualReadQuestionRepository)
    finally:
        connection.close()


def test_dual_write_path_remains_legacy_only(tmp_path):
    legacy_path, legacy, connection, _, dual = _repositories(tmp_path)
    try:
        sqlite_before = _database_fingerprint(connection)
        state = legacy.load_state()
        state["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["notes"] = "Legacy update"
        saved = dual.save_state(state)
        assert saved["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["notes"] == "Legacy update"
        assert json.loads(legacy_path.read_text(encoding="utf-8"))["workspaces"]["fixture-assessment-quiz-1"]["questions"][0]["notes"] == "Legacy update"
        assert _database_fingerprint(connection) == sqlite_before
        dual.load_state()
        assert dual.last_report.status == "mismatch"
    finally:
        connection.close()


def test_existing_question_workspace_public_api_surface_is_unchanged():
    path = ROOT / "assessment_question_workspace.py"
    if not path.exists():
        pytest.skip("public workspace module is supplied by the exact repository checkout")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {
        node.name: [arg.arg for arg in node.args.args]
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    expected = {
        "load_store": [],
        "save_store": ["store"],
        "get_workspace": ["assessment_id", "create"],
        "save_workspace": ["workspace"],
        "add_question_to_workspace": ["workspace", "text", "topic", "marks"],
        "workspace_progress": ["workspace"],
        "choose_question": ["workspace"],
        "update_question_status": ["workspace"],
        "add_question_note": ["workspace"],
        "edit_question_topic": ["workspace"],
        "delete_question": ["workspace"],
        "assessment_question_workspace_menu": [],
    }
    for name, args in expected.items():
        assert functions.get(name) == args
