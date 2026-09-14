from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

import personal_learning_assistant.migration.questions_sources_importer as importer
from personal_learning_assistant.migration.assessments_topics_importer import (
    import_assessments_and_topics,
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
    import_assessment_questions_and_sources,
    import_questions_and_sources,
    render_assessment_question_review_markdown,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP_1 = "2026-09-14T04:00:00Z"
STAMP_2 = "2026-09-14T04:15:00Z"


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
    assert apply_migrations(database_path) == (1, 2)
    return connect_database(database_path, synchronous="FULL")


def _prepared_database(tmp_path: Path, *, import_assessments: bool = True):
    data_dir, snapshots = _prepare_sources(tmp_path)
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


def test_questions_import_losslessly_without_touching_prerequisite_or_source_files(
    tmp_path,
):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    paths = tuple(
        data_dir / name
        for name in (
            "courses.json",
            "assessments.json",
            "assessment_workspace.json",
        )
    )
    before = tuple(_sha256(path) for path in paths)

    try:
        result = import_questions_and_sources(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_1,
        )

        assert result.questions.created == 2
        assert result.question_sources.total == 0
        assert result.changed_rows == 2
        assert result.review_required_questions == 2
        assert result.unresolved_sources == 0
        assert result.deferred_topic_mappings == 0
        assert result.deferred_attempts == 0
        assert str(uuid.UUID(result.import_batch_id)) == result.import_batch_id

        rows = connection.execute(
            "SELECT q.id, q.ordinal, q.question_text, q.max_marks_milli, "
            "q.status, q.user_notes, q.import_batch_id, a.title "
            "FROM questions AS q "
            "JOIN assessments AS a ON a.id = q.assessment_id "
            "ORDER BY q.ordinal"
        ).fetchall()
        assert [row[1] for row in rows] == [1, 2]
        assert [row[2] for row in rows] == [
            "Solve the synthetic linear system.",
            "Find the rank of the synthetic matrix.",
        ]
        assert [row[3] for row in rows] == [None, None]
        assert [row[4] for row in rows] == ["not_started", "not_started"]
        assert [row[5] for row in rows] == ["", ""]
        assert {row[6] for row in rows} == {result.import_batch_id}
        assert {row[7] for row in rows} == {"Synthetic Quiz"}
        for row in rows:
            assert str(uuid.UUID(row[0])) == row[0]

        assert _table_count(connection, "question_sources") == 0
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _table_count(connection, "question_attempts") == 0
        assert _table_count(connection, "migration_imports") == 12

        details = json.loads(
            connection.execute(
                "SELECT details_json FROM migration_imports "
                "WHERE target_table = 'questions' ORDER BY legacy_key LIMIT 1"
            ).fetchone()[0]
        )
        assert details["raw"]["attempts"] == []
        assert details["parser_state"] == "review_required"

        issue_codes = [issue.code for issue in result.issues]
        assert issue_codes.count("question_parser_review_required") == 2
        report = render_assessment_question_review_markdown(result)
        assert "# Assessment Question Review" in report
        assert "Review-required questions: 2" in report
        assert "Solve the synthetic linear system." in report
        assert str(tmp_path) not in report
    finally:
        connection.close()

    assert tuple(_sha256(path) for path in paths) == before


def test_identical_reimport_is_a_noop_and_compatibility_alias_works(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path)

    try:
        first = import_assessment_questions_and_sources(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_1,
        )
        original_rows = connection.execute(
            "SELECT id, updated_at FROM questions ORDER BY ordinal"
        ).fetchall()

        second = import_questions_and_sources(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_2,
        )

        assert first.changed_rows == 2
        assert second.changed_rows == 0
        assert second.questions.matched == 2
        assert second.question_sources.total == 0
        assert second.import_batch_id == first.import_batch_id
        assert _table_count(connection, "questions") == 2
        assert _table_count(connection, "migration_imports") == 12
        assert connection.execute(
            "SELECT id, updated_at FROM questions ORDER BY ordinal"
        ).fetchall() == original_rows
    finally:
        connection.close()


def test_raw_source_annotation_is_unresolved_and_optional_data_is_deferred(
    tmp_path,
):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    question = data["workspaces"]["fixture-assessment-1"]["questions"][0]
    question.update(
        {
            "marks": 2.3456,
            "status": "in progress",
            "notes": "Keep this exact\nstudent note.",
            "topic": "Linear Systems",
            "topic_mapping": {"suggested_topic": "Row Reduction"},
            "attempts": [{"outcome": "wrong"}],
            "source_file": "Synthetic Problem Sheet.pdf",
            "source_page": "3",
            "source_question_number": "2(b)",
        }
    )
    _write_workspace(path, data)
    snapshot = _rescan(data_dir)

    try:
        result = import_questions_and_sources(
            connection,
            snapshot,
            imported_at=STAMP_1,
        )
        row = connection.execute(
            "SELECT max_marks_milli, status, user_notes FROM questions "
            "WHERE ordinal = 1"
        ).fetchone()
        assert tuple(row) == (
            2346,
            "attempted",
            "Keep this exact\nstudent note.",
        )

        source = connection.execute(
            "SELECT id, document_id, resource_id, note_id, page_number, "
            "locator, raw_source_label FROM question_sources"
        ).fetchone()
        assert str(uuid.UUID(source[0])) == source[0]
        assert tuple(source[1:]) == (
            None,
            None,
            None,
            3,
            "question:2(b)",
            "Synthetic Problem Sheet.pdf",
        )
        assert result.question_sources.created == 1
        assert result.unresolved_sources == 1
        assert result.deferred_topic_records == 1
        assert result.deferred_performance_records == 1
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _table_count(connection, "question_attempts") == 0

        issue_codes = {issue.code for issue in result.issues}
        assert {
            "rounded_question_marks",
            "normalized_question_status",
            "question_topic_data_deferred",
            "question_performance_data_deferred",
            "question_source_review_required",
        }.issubset(issue_codes)

        source_details = json.loads(
            connection.execute(
                "SELECT details_json FROM migration_imports "
                "WHERE target_table = 'question_sources'"
            ).fetchone()[0]
        )
        assert source_details["raw_source_label"] == "Synthetic Problem Sheet.pdf"
        assert source_details["raw_page_number"] == "3"
        assert source_details["raw_question_number"] == "2(b)"

        repeated = import_questions_and_sources(
            connection,
            snapshot,
            imported_at=STAMP_2,
        )
        assert repeated.questions.matched == 2
        assert repeated.question_sources.matched == 1
        assert repeated.changed_rows == 0
        assert _table_count(connection, "question_sources") == 1
    finally:
        connection.close()


def test_changed_hash_preserves_question_ids_and_safely_reorders_rows(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)

    try:
        first = import_questions_and_sources(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_1,
        )
        original_ids = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT question_text, id FROM questions"
            ).fetchall()
        }

        path, data = _workspace_data(data_dir)
        questions = data["workspaces"]["fixture-assessment-1"]["questions"]
        questions[0]["text"] = "Solve the synthetic linear system, revised."
        questions[0]["source_file"] = "Revised Sheet.md"
        questions[0]["source_question_number"] = 7
        questions[:] = [questions[1], questions[0]]
        _write_workspace(path, data)
        changed_snapshot = _rescan(data_dir)

        second = import_questions_and_sources(
            connection,
            changed_snapshot,
            imported_at=STAMP_2,
        )

        rows = connection.execute(
            "SELECT id, ordinal, question_text FROM questions ORDER BY ordinal"
        ).fetchall()
        assert [tuple(row[1:]) for row in rows] == [
            (1, "Find the rank of the synthetic matrix."),
            (2, "Solve the synthetic linear system, revised."),
        ]
        assert rows[0][0] == original_ids["Find the rank of the synthetic matrix."]
        assert rows[1][0] == original_ids["Solve the synthetic linear system."]
        assert second.questions.updated == 2
        assert second.question_sources.created == 1
        assert second.import_batch_id != first.import_batch_id
        assert _table_count(connection, "questions") == 2
        assert _table_count(connection, "question_sources") == 1
        assert _table_count(connection, "migration_imports") == 15
    finally:
        connection.close()


def test_changed_raw_source_metadata_preserves_a_reviewed_document_link(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    question = data["workspaces"]["fixture-assessment-1"]["questions"][0]
    question.update(
        {
            "source_file": "Synthetic Source.pdf",
            "source_page": 1,
            "source_question_number": "1",
        }
    )
    _write_workspace(path, data)
    first_snapshot = _rescan(data_dir)

    try:
        import_questions_and_sources(
            connection,
            first_snapshot,
            imported_at=STAMP_1,
        )
        document_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO knowledge_documents "
            "(id, kind, canonical_uri, path_key, mime_type, content_hash, "
            "size_bytes, source_timestamp, extraction_status, "
            "extraction_version, extraction_error, created_at, updated_at) "
            "VALUES (?, 'pdf', NULL, 'synthetic/source.pdf', "
            "'application/pdf', ?, 1, NULL, 'complete', 'test', NULL, ?, ?)",
            (document_id, "a" * 64, STAMP_1, STAMP_1),
        )
        connection.execute(
            "UPDATE question_sources SET document_id = ?",
            (document_id,),
        )

        question["source_page"] = 2
        _write_workspace(path, data)
        result = import_questions_and_sources(
            connection,
            _rescan(data_dir),
            imported_at=STAMP_2,
        )

        source = connection.execute(
            "SELECT document_id, page_number FROM question_sources"
        ).fetchone()
        assert tuple(source) == (document_id, 2)
        assert result.question_sources.updated == 1
    finally:
        connection.close()


def test_question_omission_is_not_treated_as_deletion(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)

    try:
        import_questions_and_sources(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_1,
        )
        path, data = _workspace_data(data_dir)
        questions = data["workspaces"]["fixture-assessment-1"]["questions"]
        questions[:] = [questions[1]]
        _write_workspace(path, data)

        result = import_questions_and_sources(
            connection,
            _rescan(data_dir),
            imported_at=STAMP_2,
        )

        rows = connection.execute(
            "SELECT ordinal, question_text, deleted_at "
            "FROM questions ORDER BY ordinal"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            (1, "Find the rank of the synthetic matrix.", None),
            (2, "Solve the synthetic linear system.", None),
        ]
        assert result.questions.updated == 1
        assert _table_count(connection, "questions") == 2
    finally:
        connection.close()


def test_invalid_optional_values_are_flagged_and_raw_values_remain_in_ledger(
    tmp_path,
):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    question = data["workspaces"]["fixture-assessment-1"]["questions"][0]
    question.update(
        {
            "marks": -2,
            "status": "mystery",
            "source_file": "Raw Source.pdf",
            "source_page": 0,
            "source_question_number": {"bad": "shape"},
        }
    )
    _write_workspace(path, data)

    try:
        result = import_questions_and_sources(
            connection,
            _rescan(data_dir),
            imported_at=STAMP_1,
        )
        question_row = connection.execute(
            "SELECT max_marks_milli, status FROM questions WHERE ordinal = 1"
        ).fetchone()
        assert tuple(question_row) == (None, "not_started")
        source_row = connection.execute(
            "SELECT page_number, locator, raw_source_label FROM question_sources"
        ).fetchone()
        assert tuple(source_row) == (None, "", "Raw Source.pdf")
        issue_codes = {issue.code for issue in result.issues}
        assert {
            "out_of_range_question_marks",
            "unknown_question_status",
            "invalid_question_source_page",
            "invalid_question_source_locator",
        }.issubset(issue_codes)

        details = json.loads(
            connection.execute(
                "SELECT details_json FROM migration_imports "
                "WHERE target_table = 'questions' "
                "AND legacy_key LIKE '%fixture-question-1'"
            ).fetchone()[0]
        )
        assert details["raw"]["marks"] == -2
        assert details["raw"]["source_page"] == 0
        assert details["raw"]["source_question_number"] == {"bad": "shape"}
    finally:
        connection.close()


def test_page_or_locator_without_source_label_does_not_invent_a_source(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    question = data["workspaces"]["fixture-assessment-1"]["questions"][0]
    question["source_page"] = 2
    question["source_question_number"] = "4"
    _write_workspace(path, data)

    try:
        result = import_questions_and_sources(
            connection,
            _rescan(data_dir),
            imported_at=STAMP_1,
        )
        assert _table_count(connection, "question_sources") == 0
        assert "orphan_question_source_metadata" in {
            issue.code for issue in result.issues
        }
    finally:
        connection.close()


def test_malformed_parser_fragments_remain_distinct_and_in_source_order(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    questions = data["workspaces"]["fixture-assessment-1"]["questions"]
    questions[:] = [
        {"id": "1", "text": "Solve the system:"},
        {"id": "2", "text": "$$x+y=2$$"},
        {"id": "3", "text": "and explain whether it is consistent."},
    ]
    _write_workspace(path, data)

    try:
        result = import_questions_and_sources(
            connection,
            _rescan(data_dir),
            imported_at=STAMP_1,
        )
        rows = connection.execute(
            "SELECT ordinal, question_text FROM questions ORDER BY ordinal"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            (1, "Solve the system:"),
            (2, "$$x+y=2$$"),
            (3, "and explain whether it is consistent."),
        ]
        assert result.review_required_questions == 3
    finally:
        connection.close()


def test_missing_assessment_mapping_fails_without_question_writes(tmp_path):
    _, snapshots, connection = _prepared_database(
        tmp_path,
        import_assessments=False,
    )

    try:
        with pytest.raises(LegacyImportDataError, match="import assessments/topics first"):
            import_questions_and_sources(
                connection,
                snapshots["assessment_workspace.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "questions") == 0
        assert _table_count(connection, "question_sources") == 0
        assert _table_count(connection, "migration_imports") == 7
    finally:
        connection.close()


def test_late_unresolved_workspace_rolls_back_earlier_question_writes(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    data["workspaces"]["missing-assessment"] = {
        "assessment_id": "missing-assessment",
        "questions": [{"id": "1", "text": "Must roll back."}],
    }
    _write_workspace(path, data)

    try:
        with pytest.raises(LegacyImportDataError, match="missing-assessment"):
            import_questions_and_sources(
                connection,
                _rescan(data_dir),
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "questions") == 0
        assert _table_count(connection, "question_sources") == 0
        # Only Fix 4 and Fix 5 prerequisite evidence remains.
        assert _table_count(connection, "migration_imports") == 10
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda data: data.update({"workspaces": []}),
            "workspaces.*must be an object",
        ),
        (
            lambda data: data["workspaces"]["fixture-assessment-1"].update(
                {"assessment_id": "different-assessment"}
            ),
            "does not match assessment_id",
        ),
        (
            lambda data: data["workspaces"]["fixture-assessment-1"][
                "questions"
            ].append(
                dict(
                    data["workspaces"]["fixture-assessment-1"]["questions"][0]
                )
            ),
            "duplicate legacy question identity",
        ),
        (
            lambda data: data["workspaces"]["fixture-assessment-1"][
                "questions"
            ][0].update({"text": "  "}),
            "has no non-blank text",
        ),
    ),
)
def test_malformed_workspace_shapes_fail_before_any_question_write(
    tmp_path,
    mutation,
    message,
):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _workspace_data(data_dir)
    mutation(data)
    _write_workspace(path, data)

    try:
        with pytest.raises(LegacyImportDataError, match=message):
            import_questions_and_sources(
                connection,
                _rescan(data_dir),
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "questions") == 0
        assert _table_count(connection, "question_sources") == 0
    finally:
        connection.close()


def test_source_changed_after_scan_is_rejected_without_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    path = data_dir / "assessment_workspace.json"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    try:
        with pytest.raises(LegacySourceChangedError):
            import_questions_and_sources(
                connection,
                snapshots["assessment_workspace.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "questions") == 0
        assert _table_count(connection, "question_sources") == 0
    finally:
        connection.close()


def test_source_change_during_transaction_rolls_back_all_rows(tmp_path, monkeypatch):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    path = data_dir / "assessment_workspace.json"
    original_guard = importer.source_sha256

    def change_then_verify(snapshot):
        path.write_text(
            path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return original_guard(snapshot)

    monkeypatch.setattr(importer, "source_sha256", change_then_verify)

    try:
        with pytest.raises(LegacySourceChangedError):
            import_questions_and_sources(
                connection,
                snapshots["assessment_workspace.json"],
                imported_at=STAMP_1,
            )
        assert _table_count(connection, "questions") == 0
        assert _table_count(connection, "question_sources") == 0
        assert _table_count(connection, "migration_imports") == 10
    finally:
        connection.close()
