from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

import personal_learning_assistant.migration.question_topic_mappings_importer as importer
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
from personal_learning_assistant.migration.question_topic_mappings_importer import (
    import_question_topic_mappings,
    import_topic_mappings,
    render_question_topic_mapping_review_markdown,
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
STAMP_2 = "2026-09-14T06:01:00Z"
STAMP_3 = "2026-09-14T06:02:00Z"
STAMP_4 = "2026-09-14T06:03:00Z"
STAMP_5 = "2026-09-14T06:15:00Z"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_sources(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in (
        "courses.json",
        "assessments.json",
        "assessment_workspace.json",
    ):
        (data_dir / name).write_bytes((FIXTURES / name).read_bytes())
    return data_dir


def _scan(data_dir: Path):
    snapshots = scan_legacy_sources(
        data_dir,
        specs=tuple(
            LegacySourceSpec(name)
            for name in (
                "courses.json",
                "assessments.json",
                "assessment_workspace.json",
            )
        ),
    ).sources
    return {Path(item.canonical_path).name: item for item in snapshots}


def _rescan_workspace(data_dir: Path):
    return scan_legacy_sources(
        data_dir,
        specs=(LegacySourceSpec("assessment_workspace.json"),),
    ).sources[0]


def _connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "shadow.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    return connect_database(database_path, synchronous="FULL")


def _write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _json_data(data_dir: Path, filename: str):
    path = data_dir / filename
    return path, json.loads(path.read_text(encoding="utf-8"))


def _first_question(data):
    return data["workspaces"]["fixture-assessment-1"]["questions"][0]


def _add_course_topic(data_dir: Path, *, course_index: int, topic_id: str, name: str):
    path, data = _json_data(data_dir, "courses.json")
    data["courses"][course_index]["topics"].append(
        {
            "id": topic_id,
            "name": name,
            "status": "not_started",
            "confidence": None,
        }
    )
    _write_json(path, data)


def _import_chain(data_dir: Path, connection: sqlite3.Connection):
    snapshots = _scan(data_dir)
    import_courses_and_topics(
        connection,
        snapshots["courses.json"],
        imported_at=STAMP_1,
    )
    import_assessments_and_topics(
        connection,
        snapshots["assessments.json"],
        imported_at=STAMP_2,
    )
    import_questions_and_sources(
        connection,
        snapshots["assessment_workspace.json"],
        imported_at=STAMP_3,
    )
    return snapshots


def _prepared_database(tmp_path: Path):
    data_dir = _copy_sources(tmp_path)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)
    return data_dir, snapshots, connection


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])


def _mapping_observation_count(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM migration_imports "
            "WHERE legacy_key LIKE '%/topic_mapping:observation'"
        ).fetchone()[0]
    )


def test_unmapped_fixture_records_audited_absence_without_guessing_topics(tmp_path):
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
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )

        assert result.questions_scanned == 2
        assert result.mapping_observations.created == 2
        assert result.question_topic_mappings.total == 0
        assert result.changed_rows == 0
        assert result.accepted_mappings == 0
        assert result.proposed_mappings == 0
        assert result.unmapped_questions == 2
        assert result.unresolved_candidates == 0
        assert result.review_required_items == 2
        assert result.review_required_questions == 2
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _mapping_observation_count(connection) == 2
        assert _table_count(connection, "migration_imports") == 14

        details = json.loads(
            connection.execute(
                "SELECT details_json FROM migration_imports "
                "WHERE legacy_key LIKE '%/topic_mapping:observation' "
                "ORDER BY legacy_key LIMIT 1"
            ).fetchone()[0]
        )
        assert details["kind"] == "question_topic_mapping_observation"
        assert details["raw_topic"] == ""
        assert details["raw_topic_mapping"] is None
        assert details["candidate_resolutions"] == []

        codes = [issue.code for issue in result.issues]
        assert codes.count("question_topic_mapping_missing") == 2
        report = render_question_topic_mapping_review_markdown(result)
        assert "# Question Topic Mapping Review" in report
        assert "Questions scanned: 2" in report
        assert "Unmapped questions: 2" in report
        assert "no_legacy_topic_mapping" in report
        assert str(tmp_path) not in report
    finally:
        connection.close()

    assert tuple(_sha256(path) for path in paths) == before


def test_identical_reimport_is_noop_and_short_alias_works(tmp_path):
    _, snapshots, connection = _prepared_database(tmp_path)

    try:
        first = import_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        second = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_5,
        )

        assert first.mapping_observations.created == 2
        assert second.mapping_observations.matched == 2
        assert second.changed_rows == 0
        assert second.question_topic_mappings.total == 0
        assert _mapping_observation_count(connection) == 2
        assert _table_count(connection, "migration_imports") == 14
    finally:
        connection.close()


def test_exact_manual_topic_tag_imports_as_accepted_mapping(tmp_path):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic"] = "  Linear   Systems  "
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        row = connection.execute(
            "SELECT m.id, t.name, m.score, m.rank, m.method, m.state, "
            "m.reason, m.created_at, m.reviewed_at "
            "FROM question_topic_mappings AS m "
            "JOIN topics AS t ON t.id = m.topic_id"
        ).fetchone()
        assert str(uuid.UUID(row[0])) == row[0]
        assert tuple(row[1:]) == (
            "Linear Systems",
            None,
            None,
            "legacy_manual_topic",
            "accepted",
            "legacy accepted_topic",
            STAMP_4,
            STAMP_4,
        )
        assert result.question_topic_mappings.created == 1
        assert result.accepted_mappings == 1
        assert result.proposed_mappings == 0
        assert result.unmapped_questions == 1
        assert result.review_required_questions == 1
        assert _table_count(connection, "migration_imports") == 15
    finally:
        connection.close()


def test_pending_suggestion_stays_proposed_with_score_rank_and_method(tmp_path):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic_mapping"] = {
        "method": "automatic_medium_suggestion",
        "suggested_topic": "Linear Systems",
        "score": 0.45,
        "confidence": "medium",
        "alternatives": [
            {
                "topic": "Linear Systems",
                "score": 0.45,
                "components": {"fuzzy": 0.8},
            }
        ],
        "accepted": False,
        "mapped_at": "2026-09-13T09:30:00",
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        row = connection.execute(
            "SELECT score, rank, method, state, reason, created_at, reviewed_at "
            "FROM question_topic_mappings"
        ).fetchone()
        assert tuple(row) == (
            0.45,
            1,
            "automatic_medium_suggestion",
            "proposed",
            "legacy suggested + alternative; confidence=medium",
            "2026-09-13T09:30:00",
            None,
        )
        assert result.accepted_mappings == 0
        assert result.proposed_mappings == 1
        assert result.unmapped_questions == 1
        assert {item.reason for item in result.review_items} == {
            "pending_legacy_suggestion",
            "no_legacy_topic_mapping",
        }
        repeated = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_5,
        )
        assert repeated.question_topic_mappings.matched == 1
        assert repeated.mapping_observations.matched == 2
        assert repeated.changed_rows == 0
        assert _table_count(connection, "question_topic_mappings") == 1
    finally:
        connection.close()


def test_confirmed_automatic_mapping_imports_as_accepted(tmp_path):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    question = _first_question(data)
    question["topic"] = "Linear Systems"
    question["topic_mapping"] = {
        "method": "review_confirmed",
        "suggested_topic": "Linear Systems",
        "score": 0.71,
        "confidence": "high",
        "alternatives": [{"topic": "Linear Systems", "score": 0.71}],
        "accepted": True,
        "mapped_at": "2026-09-13T10:00:00",
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        row = connection.execute(
            "SELECT score, rank, method, state, reviewed_at "
            "FROM question_topic_mappings"
        ).fetchone()
        assert tuple(row) == (
            0.71,
            1,
            "review_confirmed",
            "accepted",
            "2026-09-13T10:00:00",
        )
        assert result.accepted_mappings == 1
        assert result.proposed_mappings == 0
        assert result.review_required_questions == 1
        assert result.review_items[0].reason == "no_legacy_topic_mapping"
    finally:
        connection.close()


def test_ranked_alternatives_resolve_only_inside_assessment_course(tmp_path):
    data_dir = _copy_sources(tmp_path)
    _add_course_topic(
        data_dir,
        course_index=0,
        topic_id="fixture-matrix-rank",
        name="Matrix Rank",
    )
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic_mapping"] = {
        "method": "automatic_low_suggestion",
        "suggested_topic": "Linear Systems",
        "score": 0.6,
        "confidence": "low",
        "alternatives": [
            {"topic": "Linear Systems", "score": 0.6},
            {"topic": "Matrix Rank", "score": 0.4},
        ],
        "accepted": False,
        "mapped_at": "2026-09-13T10:10:00",
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        rows = connection.execute(
            "SELECT t.name, m.score, m.rank, m.state "
            "FROM question_topic_mappings AS m "
            "JOIN topics AS t ON t.id = m.topic_id ORDER BY m.rank"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("Linear Systems", 0.6, 1, "proposed"),
            ("Matrix Rank", 0.4, 2, "proposed"),
        ]
        assert result.proposed_mappings == 2
        assert result.unresolved_candidates == 0
        assert result.review_required_items == 3
    finally:
        connection.close()


def test_suggested_topic_missing_from_alternatives_is_prepended_deterministically(
    tmp_path,
):
    data_dir = _copy_sources(tmp_path)
    _add_course_topic(
        data_dir,
        course_index=0,
        topic_id="fixture-matrix-rank",
        name="Matrix Rank",
    )
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic_mapping"] = {
        "suggested_topic": "Matrix Rank",
        "score": 0.9,
        "alternatives": [{"topic": "Linear Systems", "score": 0.4}],
        "accepted": False,
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        rows = connection.execute(
            "SELECT t.name, m.rank FROM question_topic_mappings AS m "
            "JOIN topics AS t ON t.id = m.topic_id ORDER BY m.rank"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("Matrix Rank", 1),
            ("Linear Systems", 2),
        ]
    finally:
        connection.close()


def test_cross_course_topic_name_is_not_used_as_a_foreign_key(tmp_path):
    data_dir = _copy_sources(tmp_path)
    _add_course_topic(
        data_dir,
        course_index=1,
        topic_id="fixture-cross-course-only",
        name="Cross Course Only",
    )
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic"] = "Cross Course Only"
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        assert _table_count(connection, "question_topic_mappings") == 0
        assert result.unresolved_candidates == 1
        assert result.unmapped_questions == 2
        assert "unresolved_question_topic_label" in {
            issue.code for issue in result.issues
        }
        observation = json.loads(
            connection.execute(
                "SELECT details_json FROM migration_imports "
                "WHERE legacy_key LIKE '%fixture-question-1/topic_mapping:observation'"
            ).fetchone()[0]
        )
        assert observation["candidate_resolutions"][0]["resolution"] == "unresolved"
        assert observation["candidate_resolutions"][0]["target_ids"] == []
    finally:
        connection.close()


def test_invalid_optional_mapping_values_never_silently_accept_a_topic(tmp_path):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic_mapping"] = {
        "method": 42,
        "suggested_topic": "Linear Systems",
        "score": 1.5,
        "confidence": "mysterious",
        "alternatives": [{"topic": "Linear Systems", "score": "bad"}],
        "accepted": "yes",
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        row = connection.execute(
            "SELECT score, method, state, reviewed_at "
            "FROM question_topic_mappings"
        ).fetchone()
        assert tuple(row) == (
            None,
            "legacy_topic_mapping",
            "proposed",
            None,
        )
        codes = [issue.code for issue in result.issues]
        assert codes.count("invalid_question_topic_score") == 2
        assert {
            "invalid_question_topic_method",
            "unknown_question_topic_confidence",
            "invalid_question_topic_accepted_flag",
        }.issubset(codes)
    finally:
        connection.close()


def test_conflicting_primary_and_alternative_scores_are_flagged_and_preserved(
    tmp_path,
):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic_mapping"] = {
        "suggested_topic": "Linear Systems",
        "score": 0.8,
        "alternatives": [{"topic": "Linear Systems", "score": 0.7}],
        "accepted": False,
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        row = connection.execute(
            "SELECT score, reason FROM question_topic_mappings"
        ).fetchone()
        assert row[0] == 0.8
        assert "conflicting raw scores" in row[1]
        assert "conflicting_question_topic_scores" in {
            issue.code for issue in result.issues
        }
        details = json.loads(
            connection.execute(
                "SELECT details_json FROM migration_imports "
                "WHERE target_table = 'question_topic_mappings'"
            ).fetchone()[0]
        )
        assert details["raw_topic_mapping"]["score"] == 0.8
        assert details["raw_candidate"]["score"] == 0.7
    finally:
        connection.close()


def test_inconsistent_accepted_metadata_is_imported_but_remains_reviewable(tmp_path):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    question = _first_question(data)
    question["topic_mapping"] = {
        "suggested_topic": "Linear Systems",
        "score": 0.75,
        "alternatives": [{"topic": "Linear Systems", "score": 0.75}],
        "accepted": True,
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        result = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        row = connection.execute(
            "SELECT state, reviewed_at FROM question_topic_mappings"
        ).fetchone()
        assert tuple(row) == ("accepted", STAMP_4)
        assert "inconsistent_accepted_question_topic_mapping" in {
            issue.code for issue in result.issues
        }
        assert "inconsistent_accepted_mapping" in {
            item.reason for item in result.review_items
        }
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("topic_not_string", "field 'topic' must be a string or null"),
        ("mapping_not_object", "field 'topic_mapping' must be an object or null"),
        ("alternatives_not_array", "alternatives must be an array"),
        ("alternative_not_object", "must be an object"),
        ("alternative_without_label", "has no label"),
        ("duplicate_alternative", "duplicate topic alternative"),
    ),
)
def test_malformed_mapping_shapes_fail_without_partial_mapping_writes(
    tmp_path,
    case,
    message,
):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    question = _first_question(data)
    if case == "topic_not_string":
        question["topic"] = ["Linear Systems"]
    elif case == "mapping_not_object":
        question["topic_mapping"] = ["Linear Systems"]
    elif case == "alternatives_not_array":
        question["topic_mapping"] = {"alternatives": {"topic": "Linear Systems"}}
    elif case == "alternative_not_object":
        question["topic_mapping"] = {"alternatives": ["Linear Systems"]}
    elif case == "alternative_without_label":
        question["topic_mapping"] = {"alternatives": [{"score": 0.5}]}
    elif case == "duplicate_alternative":
        question["topic_mapping"] = {
            "alternatives": [
                {"topic": "Linear Systems", "score": 0.5},
                {"topic": " linear   systems ", "score": 0.4},
            ]
        }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        with pytest.raises(LegacyImportDataError, match=message):
            import_question_topic_mappings(
                connection,
                snapshots["assessment_workspace.json"],
                imported_at=STAMP_4,
            )
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _mapping_observation_count(connection) == 0
        assert _table_count(connection, "migration_imports") == 12
    finally:
        connection.close()


def test_changed_snapshot_updates_stable_mapping_and_adds_new_evidence(tmp_path):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    question = _first_question(data)
    question["topic_mapping"] = {
        "suggested_topic": "Linear Systems",
        "score": 0.4,
        "alternatives": [{"topic": "Linear Systems", "score": 0.4}],
        "accepted": False,
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        first = import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        original_id = connection.execute(
            "SELECT id FROM question_topic_mappings"
        ).fetchone()[0]

        question["topic"] = "Linear Systems"
        question["topic_mapping"]["score"] = 0.8
        question["topic_mapping"]["alternatives"][0]["score"] = 0.8
        question["topic_mapping"]["accepted"] = True
        question["topic_mapping"]["mapped_at"] = STAMP_5
        _write_json(path, data)
        changed_snapshot = _rescan_workspace(data_dir)
        import_questions_and_sources(
            connection,
            changed_snapshot,
            imported_at=STAMP_5,
        )

        second = import_question_topic_mappings(
            connection,
            changed_snapshot,
            imported_at=STAMP_5,
        )
        row = connection.execute(
            "SELECT id, score, state, reviewed_at FROM question_topic_mappings"
        ).fetchone()
        assert tuple(row) == (original_id, 0.8, "accepted", STAMP_5)
        assert first.question_topic_mappings.created == 1
        assert second.question_topic_mappings.updated == 1
        assert second.mapping_observations.created == 2
        assert second.accepted_mappings == 1
        assert _table_count(connection, "question_topic_mappings") == 1
        assert _table_count(connection, "migration_imports") == 20
    finally:
        connection.close()


def test_fix7_requires_fix6_evidence_for_the_exact_changed_snapshot(tmp_path):
    data_dir, _, connection = _prepared_database(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic"] = "Linear Systems"
    _write_json(path, data)
    changed_snapshot = _rescan_workspace(data_dir)

    try:
        with pytest.raises(
            LegacyImportDataError,
            match="import questions/sources for this snapshot first",
        ):
            import_question_topic_mappings(
                connection,
                changed_snapshot,
                imported_at=STAMP_4,
            )
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _mapping_observation_count(connection) == 0
        assert _table_count(connection, "migration_imports") == 12
    finally:
        connection.close()


def test_omitted_mapping_is_not_treated_as_deletion(tmp_path):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic_mapping"] = {
        "suggested_topic": "Linear Systems",
        "score": 0.5,
        "alternatives": [{"topic": "Linear Systems", "score": 0.5}],
        "accepted": False,
    }
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)

    try:
        import_question_topic_mappings(
            connection,
            snapshots["assessment_workspace.json"],
            imported_at=STAMP_4,
        )
        _first_question(data).pop("topic_mapping")
        _write_json(path, data)
        changed_snapshot = _rescan_workspace(data_dir)
        import_questions_and_sources(
            connection,
            changed_snapshot,
            imported_at=STAMP_5,
        )
        result = import_question_topic_mappings(
            connection,
            changed_snapshot,
            imported_at=STAMP_5,
        )

        assert _table_count(connection, "question_topic_mappings") == 1
        assert connection.execute(
            "SELECT state FROM question_topic_mappings"
        ).fetchone()[0] == "proposed"
        assert result.unmapped_questions == 2
        assert result.question_topic_mappings.total == 0
    finally:
        connection.close()


def test_late_missing_question_mapping_rolls_back_earlier_mapping_and_observation(
    tmp_path,
):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic"] = "Linear Systems"
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)
    connection.execute(
        "DELETE FROM migration_imports WHERE target_table = 'questions' "
        "AND legacy_key LIKE '%fixture-question-2'"
    )

    try:
        with pytest.raises(
            LegacyImportDataError,
            match="fixture-question-2",
        ):
            import_question_topic_mappings(
                connection,
                snapshots["assessment_workspace.json"],
                imported_at=STAMP_4,
            )
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _mapping_observation_count(connection) == 0
        assert _table_count(connection, "migration_imports") == 11
    finally:
        connection.close()


def test_source_changed_after_scan_is_rejected_without_mapping_writes(tmp_path):
    data_dir, snapshots, connection = _prepared_database(tmp_path)
    path = data_dir / "assessment_workspace.json"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    try:
        with pytest.raises(LegacySourceChangedError):
            import_question_topic_mappings(
                connection,
                snapshots["assessment_workspace.json"],
                imported_at=STAMP_4,
            )
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _mapping_observation_count(connection) == 0
    finally:
        connection.close()


def test_source_change_during_transaction_rolls_back_every_fix7_write(
    tmp_path,
    monkeypatch,
):
    data_dir = _copy_sources(tmp_path)
    path, data = _json_data(data_dir, "assessment_workspace.json")
    _first_question(data)["topic"] = "Linear Systems"
    _write_json(path, data)
    connection = _connection(tmp_path)
    snapshots = _import_chain(data_dir, connection)
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
            import_question_topic_mappings(
                connection,
                snapshots["assessment_workspace.json"],
                imported_at=STAMP_4,
            )
        assert _table_count(connection, "question_topic_mappings") == 0
        assert _mapping_observation_count(connection) == 0
        assert _table_count(connection, "migration_imports") == 12
    finally:
        connection.close()
