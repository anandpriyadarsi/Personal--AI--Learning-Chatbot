from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from personal_learning_assistant.migration.assessments_topics_importer import (
    import_assessments_and_topics,
)
from personal_learning_assistant.migration.attempts_performance_importer import (
    import_attempts_mistakes_and_performance,
)
from personal_learning_assistant.migration.courses_topics_importer import (
    import_courses_and_topics,
)
from personal_learning_assistant.migration.grades_calendar_importer import (
    import_grades_and_academic_calendar,
)
from personal_learning_assistant.migration.learning_progress_importer import (
    import_learning_memory_and_progress,
)
from personal_learning_assistant.migration.legacy_source_scanner import (
    LegacySourceSpec,
    scan_legacy_sources,
)
from personal_learning_assistant.migration.question_topic_mappings_importer import (
    import_question_topic_mappings,
)
from personal_learning_assistant.migration.questions_sources_importer import (
    import_questions_and_sources,
)
from personal_learning_assistant.migration.reverse_export_restore import (
    Phase32SafetyError,
    Phase32ValidationError,
    REQUIRED_EXPORT_SOURCES,
    rehearse_phase3_restore,
    reverse_export_phase3,
    run_phase3_completion_gate,
)
from personal_learning_assistant.migration.study_plans_importer import (
    import_study_plans,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP = "2026-09-14T12:00:00Z"
REQUIRED_NAMES = (
    "courses.json",
    "assessments.json",
    "assessment_workspace.json",
    "learning_memory.json",
    "course_progress_history.json",
    "weekly_study_plans.json",
    "multi_course_weekly_plans.json",
)
SPECS = tuple(LegacySourceSpec(name) for name in REQUIRED_NAMES) + (
    LegacySourceSpec("intelligent_study_plans.json", required=False),
    LegacySourceSpec("semester_grade_config.json", required=False),
)


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _intelligent_plan():
    return {
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
    }


def _grade_config():
    return {
        "version": 1,
        "semester_name": "Semester 1",
        "target_sgpa": 8.5,
        "grade_scale": [
            {"letter": "A", "min_score": 80, "grade_point": 9},
            {"letter": "B", "min_score": 60, "grade_point": 7},
            {"letter": "F", "min_score": 0, "grade_point": 0},
        ],
        "courses": [
            {
                "course_id": "fixture-ma103n",
                "credits": 4,
                "manual_grade_point": 9,
                "manual_letter_grade": "A",
            }
        ],
        "semester_result": {
            "earned_credits": 4,
            "earned_grade_points": 36,
            "sgpa": 9,
            "verified": False,
            "source": "synthetic fixture",
            "recorded_at": "2026-09-14T11:55:00Z",
        },
    }


def _source_hashes(source_directory: Path):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_directory.glob("*.json"))
    }


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _prepare(tmp_path: Path, *, include_optional: bool = False):
    source_directory = tmp_path / "legacy-fixtures"
    source_directory.mkdir()
    for name in REQUIRED_NAMES:
        shutil.copyfile(FIXTURES / name, source_directory / name)
    if include_optional:
        _write_json(
            source_directory / "intelligent_study_plans.json",
            _intelligent_plan(),
        )
        _write_json(
            source_directory / "semester_grade_config.json",
            _grade_config(),
        )

    manifest = scan_legacy_sources(source_directory, specs=SPECS)
    snapshots = {
        Path(snapshot.canonical_path).name: snapshot
        for snapshot in manifest.sources
    }
    database_path = tmp_path / "phase3-shadow.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    connection = connect_database(database_path, synchronous="FULL")

    import_courses_and_topics(
        connection,
        snapshots["courses.json"],
        imported_at=STAMP,
    )
    import_assessments_and_topics(
        connection,
        snapshots["assessments.json"],
        imported_at=STAMP,
    )
    import_questions_and_sources(
        connection,
        snapshots["assessment_workspace.json"],
        imported_at=STAMP,
    )
    import_question_topic_mappings(
        connection,
        snapshots["assessment_workspace.json"],
        imported_at=STAMP,
    )
    import_attempts_mistakes_and_performance(
        connection,
        snapshots["assessment_workspace.json"],
        imported_at=STAMP,
    )
    import_learning_memory_and_progress(
        connection,
        snapshots["learning_memory.json"],
        snapshots["course_progress_history.json"],
        imported_at=STAMP,
    )
    import_study_plans(
        connection,
        (
            snapshots["weekly_study_plans.json"],
            snapshots["multi_course_weekly_plans.json"],
            snapshots["intelligent_study_plans.json"],
        ),
        imported_at=STAMP,
    )
    import_grades_and_academic_calendar(
        connection,
        snapshots["semester_grade_config.json"],
        snapshots["assessments.json"],
        imported_at=STAMP,
    )
    return source_directory, database_path, connection


def test_reverse_export_is_isolated_and_reconciles_legacy_structures(tmp_path):
    source_directory, _, connection = _prepare(tmp_path)
    before_hashes = _source_hashes(source_directory)
    before_changes = connection.total_changes
    output = tmp_path / "phase3-reverse-export"

    try:
        result = reverse_export_phase3(
            connection,
            output,
            legacy_source_directory=source_directory,
            generated_at=STAMP,
        )

        assert result.output_directory == output
        assert result.status == "pass_with_documented_differences"
        assert result.integrity_check == ("ok",)
        assert result.foreign_key_check == ()
        assert {item.source_path for item in result.artifacts} == set(
            REQUIRED_EXPORT_SOURCES
        )
        assert all(_is_below(output / item.relative_path, output) for item in result.artifacts)
        assert _source_hashes(source_directory) == before_hashes
        assert connection.total_changes == before_changes

        courses = json.loads(
            (output / "legacy_json" / "courses.json").read_text(encoding="utf-8")
        )
        assert courses["active_course_id"] == "fixture-ma103n"
        assert courses["document_links"] == {}
        assert [course["id"] for course in courses["courses"]] == [
            "fixture-ma103n",
            "fixture-cy100n",
        ]

        multi = json.loads(
            (
                output
                / "legacy_json"
                / "multi_course_weekly_plans.json"
            ).read_text(encoding="utf-8")
        )
        assert multi["plans"][0]["requested_minutes"] == 120
        assert multi["plans"][0]["stored_minutes"] == 108
        assert sum(item["minutes"] for item in multi["plans"][0]["items"]) == 108

        discrepancy_codes = {
            item["code"] for item in result.documented_discrepancies
        }
        assert "requested_allocated_minutes_difference" in discrepancy_codes
        assert "assessment_schema_code_v2_file_v1" in discrepancy_codes
        assert "learning_memory_code_v2_file_v1" in discrepancy_codes
        plan_difference = next(
            item
            for item in result.documented_discrepancies
            if item["code"] == "requested_allocated_minutes_difference"
        )
        assert plan_difference["requested_minutes"] == 120
        assert plan_difference["allocated_minutes"] == 108
        assert plan_difference["policy"] == "preserved_without_rebalancing"

        reconciliation = {
            item["source_path"]: item for item in result.reconciliation
        }
        assert set(reconciliation) == set(REQUIRED_EXPORT_SOURCES)
        assert reconciliation["data/courses.json"]["status"] == "documented_difference"
        assert reconciliation["data/courses.json"]["source_entity_count"] == 2
        assert reconciliation["data/courses.json"]["export_entity_count"] == 2
        assert reconciliation[
            "data/multi_course_weekly_plans.json"
        ]["source_entity_count"] == 1

        manifest_text = result.manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        assert manifest["authority"] == {
            "legacy_json_authoritative_until_phase4": True,
            "sqlite_role": "temporary_shadow",
            "real_user_data_written": False,
        }
        assert str(tmp_path) not in manifest_text
        assert manifest["database"]["integrity_check"]["results"] == ["ok"]
        assert manifest["database"]["foreign_key_check"]["violations"] == []
        assert manifest["unmigrated_legacy_sources"]
        relational = json.loads(
            result.relational_snapshot_path.read_text(encoding="utf-8")
        )
        assert relational["database_role"] == "temporary_shadow"
        assert "migration_imports" in relational["tables"]
        assert "study_plans" in relational["tables"]
    finally:
        connection.close()


def test_restore_rehearsal_uses_only_copies_and_proves_idempotency(tmp_path):
    source_directory, database_path, connection = _prepare(tmp_path)
    before_sources = _source_hashes(source_directory)
    before_database = hashlib.sha256(database_path.read_bytes()).hexdigest()
    export_directory = tmp_path / "phase3-export-for-rehearsal"
    rehearsal_directory = tmp_path / "phase3-restore-rehearsal"

    try:
        exported = reverse_export_phase3(
            connection,
            export_directory,
            legacy_source_directory=source_directory,
            generated_at=STAMP,
        )
        result = rehearse_phase3_restore(
            connection,
            exported,
            rehearsal_directory,
            generated_at=STAMP,
        )

        assert result.status == "pass"
        assert (result.migrations_first_apply)[:2] == (1, 2)
        assert result.migrations_second_apply == ()
        assert result.migration_idempotent is True
        assert result.import_idempotent is True
        assert result.second_import_changes == 0
        assert result.export_hashes_unchanged is True
        assert result.integrity_check == ("ok", "ok", "ok")
        assert result.foreign_key_check == ()
        assert (
            result.source_fingerprint
            == result.backup_fingerprint
            == result.restored_fingerprint
        )
        assert (
            result.reimport_first_fingerprint
            == result.reimport_second_fingerprint
        )
        for path in (
            result.backup_path,
            result.restored_database_path,
            result.reimport_database_path,
            result.report_path,
        ):
            assert path.exists()
            assert _is_below(path, rehearsal_directory)
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        assert report["safety"]["temporary_copies_only"] is True
        assert report["safety"]["real_legacy_or_user_data_written"] is False
        assert report["migration_idempotency"]["pass"] is True
        assert report["reverse_export_reimport"]["idempotent"] is True
        assert _source_hashes(source_directory) == before_sources
        assert hashlib.sha256(database_path.read_bytes()).hexdigest() == before_database
    finally:
        connection.close()


def test_completion_gate_runs_end_to_end_without_source_mutation(tmp_path):
    source_directory, _, connection = _prepare(tmp_path)
    before_sources = _source_hashes(source_directory)

    try:
        result = run_phase3_completion_gate(
            connection,
            tmp_path / "phase3-final-export",
            tmp_path / "phase3-final-rehearsal",
            legacy_source_directory=source_directory,
            generated_at=STAMP,
        )

        assert result.status == "pass"
        assert result.sqlite_unchanged is True
        assert result.legacy_sources_unchanged is True
        assert result.reverse_export.integrity_check == ("ok",)
        assert result.reverse_export.foreign_key_check == ()
        assert result.restore_rehearsal.migration_idempotent is True
        assert result.restore_rehearsal.import_idempotent is True
        assert _source_hashes(source_directory) == before_sources
    finally:
        connection.close()


def test_optional_plan_and_grade_sources_round_trip_in_rehearsal(tmp_path):
    source_directory, _, connection = _prepare(tmp_path, include_optional=True)

    try:
        exported = reverse_export_phase3(
            connection,
            tmp_path / "phase3-optional-export",
            legacy_source_directory=source_directory,
            generated_at=STAMP,
        )
        paths = {item.source_path for item in exported.artifacts}
        assert "data/intelligent_study_plans.json" in paths
        assert "data/semester_grade_config.json" in paths

        intelligent = json.loads(
            (
                exported.output_directory
                / "legacy_json"
                / "intelligent_study_plans.json"
            ).read_text(encoding="utf-8")
        )
        assert intelligent["plans"][0]["requested_minutes"] == 90
        assert intelligent["plans"][0]["stored_minutes"] == 90
        assert intelligent["plans"][0]["items"][0]["minutes"] == 90

        grade = json.loads(
            (
                exported.output_directory
                / "legacy_json"
                / "semester_grade_config.json"
            ).read_text(encoding="utf-8")
        )
        assert grade["target_sgpa"] == 8.5
        assert grade["grade_scale_verified"] is False
        assert grade["semester_result"]["sgpa"] == 9

        rehearsal = rehearse_phase3_restore(
            connection,
            exported,
            tmp_path / "phase3-optional-rehearsal",
            generated_at=STAMP,
        )
        assert rehearsal.migrations_second_apply == ()
        assert rehearsal.second_import_changes == 0
        assert rehearsal.reimport_first_fingerprint == rehearsal.reimport_second_fingerprint
        assert rehearsal.foreign_key_check == ()
    finally:
        connection.close()


def test_safety_guards_refuse_existing_or_protected_destinations(tmp_path):
    source_directory, _, connection = _prepare(tmp_path)
    output = tmp_path / "phase3-one-shot-export"

    try:
        reverse_export_phase3(
            connection,
            output,
            legacy_source_directory=source_directory,
            generated_at=STAMP,
        )
        with pytest.raises(Phase32SafetyError, match="new and absent"):
            reverse_export_phase3(
                connection,
                output,
                legacy_source_directory=source_directory,
                generated_at=STAMP,
            )

        with pytest.raises(Phase32SafetyError, match="protected|data"):
            reverse_export_phase3(
                connection,
                source_directory / "phase3-export",
                legacy_source_directory=source_directory,
                generated_at=STAMP,
            )
        assert not (source_directory / "phase3-export").exists()
    finally:
        connection.close()


def test_production_database_name_is_refused_before_output_creation(tmp_path):
    database_path = tmp_path / "learning_assistant.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    connection = connect_database(database_path, synchronous="FULL")
    output = tmp_path / "phase3-production-export"

    try:
        with pytest.raises(Phase32SafetyError, match="production database"):
            reverse_export_phase3(
                connection,
                output,
                generated_at=STAMP,
            )
        assert not output.exists()
    finally:
        connection.close()


def test_foreign_key_violation_blocks_export_before_output_creation(tmp_path):
    _, _, connection = _prepare(tmp_path)
    output = tmp_path / "phase3-invalid-export"

    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "orphan-topic",
                "missing-course",
                "Orphan",
                "orphan",
                0,
                "not_started",
                STAMP,
                STAMP,
            ),
        )
        connection.execute("PRAGMA foreign_keys = ON")

        with pytest.raises(Phase32ValidationError, match="foreign_key_check"):
            reverse_export_phase3(
                connection,
                output,
                generated_at=STAMP,
            )
        assert not output.exists()
    finally:
        connection.close()
