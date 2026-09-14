from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.assessments_topics_importer import (
    import_assessments_and_topics,
)
from personal_learning_assistant.migration.courses_topics_importer import (
    import_courses_and_topics,
)
from personal_learning_assistant.migration.grades_calendar_importer import (
    import_grades_and_academic_calendar,
)
from personal_learning_assistant.migration.legacy_source_scanner import (
    LegacySourceSpec,
    scan_legacy_sources,
)
from personal_learning_assistant.migration.reconciliation_reports import (
    EXPECTED_PARITY_DOMAINS,
    ReconciliationInputError,
    ReconciliationSafetyError,
    RollbackEvidence,
    build_reconciliation_report,
    make_parity_check,
    render_reconciliation_json,
    render_reconciliation_markdown,
)
from personal_learning_assistant.migration.study_plans_importer import (
    import_study_plans,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase1"
STAMP_1 = "2026-09-14T11:00:00Z"
STAMP_2 = "2026-09-14T11:30:00Z"

SPECS = (
    LegacySourceSpec("courses.json"),
    LegacySourceSpec("assessments.json"),
    LegacySourceSpec("weekly_study_plans.json"),
    LegacySourceSpec("multi_course_weekly_plans.json"),
    LegacySourceSpec("intelligent_study_plans.json", required=False),
    LegacySourceSpec("semester_grade_config.json", required=False),
)


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
            "recorded_at": "2026-09-14T10:55:00Z",
        },
    }


def _prepare(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in (
        "courses.json",
        "assessments.json",
        "weekly_study_plans.json",
        "multi_course_weekly_plans.json",
    ):
        (data_dir / name).write_bytes((FIXTURES / name).read_bytes())
    _write_json(data_dir / "semester_grade_config.json", _grade_config())

    manifest = scan_legacy_sources(data_dir, specs=SPECS)
    snapshots = {
        Path(snapshot.canonical_path).name: snapshot
        for snapshot in manifest.sources
    }

    database_path = tmp_path / "shadow.db"
    assert apply_migrations(database_path) == (1, 2)
    connection = connect_database(database_path, synchronous="FULL")

    courses = import_courses_and_topics(
        connection, snapshots["courses.json"], imported_at=STAMP_1
    )
    assessments = import_assessments_and_topics(
        connection, snapshots["assessments.json"], imported_at=STAMP_1
    )
    plans = import_study_plans(
        connection,
        [
            snapshots["weekly_study_plans.json"],
            snapshots["multi_course_weekly_plans.json"],
            snapshots["intelligent_study_plans.json"],
        ],
        imported_at=STAMP_1,
    )
    grades = import_grades_and_academic_calendar(
        connection,
        snapshots["semester_grade_config.json"],
        snapshots["assessments.json"],
        imported_at=STAMP_1,
    )
    return data_dir, manifest, snapshots, connection, (
        courses,
        assessments,
        plans,
        grades,
    )


def _parity_checks(*, failed_domain: str = ""):
    return tuple(
        make_parity_check(
            domain,
            "synthetic-fixture",
            {"value": domain},
            {"value": "different" if domain == failed_domain else domain},
            note="characterized fixture",
        )
        for domain in EXPECTED_PARITY_DOMAINS
    )


def _rollback(*, verified: bool = True):
    return RollbackEvidence(
        backup_used="backup/phase3-fixture.tar",
        backup_sha256="a" * 64,
        command="python -m tools.restore backup/phase3-fixture.tar",
        runbook="docs/ROLLBACK.md",
        verified=verified,
    )


def _hashes(data_dir: Path):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(data_dir.glob("*.json"))
    }


def test_report_contains_portable_machine_and_human_reconciliation(tmp_path):
    data_dir, manifest, _, connection, results = _prepare(tmp_path)
    before_hashes = _hashes(data_dir)
    before_changes = connection.total_changes
    before_counts = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT name, (SELECT COUNT(*) FROM migration_imports) "
            "FROM sqlite_master WHERE name = 'migration_imports'"
        ).fetchall()
    }

    try:
        report = build_reconciliation_report(
            connection,
            manifest,
            import_results=results,
            parity_checks=_parity_checks(),
            rollback=_rollback(),
            generated_at=STAMP_2,
        )

        assert report.status == "review_required"
        assert report.source_manifest_hash_before == report.source_manifest_hash_after
        assert all(item["preservation"] == "unchanged" for item in report.sources)
        assert all(
            item["coverage"] in {"covered", "optional_absent"}
            for item in report.sources
        )
        assert report.database["role"] == "temporary_shadow"
        assert report.database["label"] == "shadow.db"
        assert report.database["integrity_check"] == {
            "status": "pass",
            "results": ["ok"],
        }
        assert report.database["foreign_key_check"] == {
            "status": "pass",
            "violations": [],
        }
        assert report.ledger_target_failures == ()
        assert report.duplicates == ()
        assert report.calendar_validation["status"] == "pass"
        assert report.calendar_validation["assessments_with_due_date"] == 1
        assert report.grade_validation["unverified_grade_scales"] == 1
        assert report.assessment_validation["score_issue_ids"] == []
        assert report.relationship_counts["semester_courses"] == 2
        assert report.relationship_counts["assessment_calendar_events"] == 1

        multi = next(
            item
            for item in report.plan_minute_validation
            if item["kind"] == "multi_course_weekly"
        )
        assert multi["requested_minutes"] == 120
        assert multi["allocated_minutes"] == 108
        assert multi["active_item_minutes"] == 108
        assert multi["status"] == "documented_difference"

        machine = json.loads(render_reconciliation_json(report))
        assert machine["report_version"] == 1
        assert machine["import_runs"][0]["counts"]["before"] >= 1
        assert machine["import_runs"][0]["counts"]["created"] >= 1
        assert machine["source_manifest_hash_after"] == manifest.manifest_hash
        assert machine["sources"][0]["current_sha256"]
        assert machine["parity"]["domains"]["brief"]["status"] == "pass"
        assert machine["rollback"]["status"] == "pass"

        markdown = render_reconciliation_markdown(report)
        assert "# Phase 3 Migration Reconciliation Report" in markdown
        assert "## Source preservation and coverage" in markdown
        assert "## Old-versus-new parity" in markdown
        assert "120 | 108 | 108 | 12 | documented_difference" in markdown
        assert str(tmp_path) not in markdown
        assert str(tmp_path) not in render_reconciliation_json(report)

        assert _hashes(data_dir) == before_hashes
        assert connection.total_changes == before_changes
        assert before_counts == {"migration_imports": before_counts["migration_imports"]}
    finally:
        connection.close()


def test_identical_second_import_is_reported_as_matched_not_created(tmp_path):
    _, manifest, snapshots, connection, _ = _prepare(tmp_path)
    try:
        second = (
            import_courses_and_topics(
                connection, snapshots["courses.json"], imported_at=STAMP_2
            ),
            import_assessments_and_topics(
                connection, snapshots["assessments.json"], imported_at=STAMP_2
            ),
            import_study_plans(
                connection,
                [
                    snapshots["weekly_study_plans.json"],
                    snapshots["multi_course_weekly_plans.json"],
                    snapshots["intelligent_study_plans.json"],
                ],
                imported_at=STAMP_2,
            ),
            import_grades_and_academic_calendar(
                connection,
                snapshots["semester_grade_config.json"],
                snapshots["assessments.json"],
                imported_at=STAMP_2,
            ),
        )
        report = build_reconciliation_report(
            connection,
            manifest,
            import_results=second,
            parity_checks=_parity_checks(),
            rollback=_rollback(),
            generated_at=STAMP_2,
        )
        machine = report.to_dict()
        assert all(run["counts"]["created"] == 0 for run in machine["import_runs"])
        assert all(run["counts"]["updated"] == 0 for run in machine["import_runs"])
        assert all(run["counts"]["matched"] > 0 for run in machine["import_runs"])
    finally:
        connection.close()


def test_source_change_after_manifest_blocks_report_and_shows_current_hash(tmp_path):
    data_dir, manifest, _, connection, _ = _prepare(tmp_path)
    course_path = data_dir / "courses.json"
    old_hash = hashlib.sha256(course_path.read_bytes()).hexdigest()
    course_path.write_bytes(course_path.read_bytes() + b"\n")

    try:
        report = build_reconciliation_report(
            connection,
            manifest,
            parity_checks=_parity_checks(),
            rollback=_rollback(),
            generated_at=STAMP_2,
        )
        source = next(item for item in report.sources if item["path"] == "data/courses.json")
        assert report.status == "blocked"
        assert source["sha256"] == old_hash
        assert source["current_sha256"] != old_hash
        assert source["preservation"] == "changed"
        assert {finding.code for finding in report.findings} >= {
            "legacy_source_changed",
            "source_manifest_changed",
        }
    finally:
        connection.close()


def test_foreign_key_violation_and_missing_ledger_target_are_blocking(tmp_path):
    _, manifest, _, connection, _ = _prepare(tmp_path)
    source = next(item for item in manifest.sources if item.canonical_path == "data/courses.json")
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "INSERT INTO assessments "
        "(id, course_id, assessment_type, title, status, description, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "broken-assessment",
            "missing-course",
            "quiz",
            "Broken",
            "pending",
            "",
            STAMP_2,
            STAMP_2,
        ),
    )
    connection.execute(
        "INSERT INTO migration_imports "
        "(id, source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "orphan-ledger-row",
            source.canonical_path,
            source.source_hash,
            source.source_type,
            source.source_version,
            "course:missing",
            "courses",
            "missing-target",
            STAMP_2,
            "{}",
        ),
    )
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        report = build_reconciliation_report(
            connection,
            manifest,
            parity_checks=_parity_checks(),
            rollback=_rollback(),
            generated_at=STAMP_2,
        )
        assert report.status == "blocked"
        assert report.database["foreign_key_check"]["status"] == "fail"
        assert report.ledger_target_failures == (
            {
                "source_path": "data/courses.json",
                "legacy_key": "course:missing",
                "target_table": "courses",
                "target_id": "missing-target",
                "reason": "target_row_missing",
            },
        )
        assert {finding.code for finding in report.findings} >= {
            "foreign_key_check_failed",
            "ledger_target_invalid",
        }
    finally:
        connection.close()


def test_legacy_identity_target_drift_is_listed_as_duplicate(tmp_path):
    _, manifest, _, connection, _ = _prepare(tmp_path)
    row = connection.execute(
        "SELECT source_path, source_type, source_version, legacy_key "
        "FROM migration_imports WHERE target_table = 'courses' ORDER BY legacy_key LIMIT 1"
    ).fetchone()
    connection.execute(
        "INSERT INTO courses "
        "(id, code, name, status, description, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("drift-target", "DRIFT101", "Drift", "active", "", STAMP_2, STAMP_2),
    )
    connection.execute(
        "INSERT INTO migration_imports "
        "(id, source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "drift-ledger-row",
            row[0],
            "f" * 64,
            row[1],
            row[2],
            row[3],
            "courses",
            "drift-target",
            STAMP_2,
            "{}",
        ),
    )

    try:
        report = build_reconciliation_report(
            connection,
            manifest,
            parity_checks=_parity_checks(),
            rollback=_rollback(),
            generated_at=STAMP_2,
        )
        assert report.status == "blocked"
        assert len(report.duplicates) == 1
        assert report.duplicates[0]["kind"] == "legacy_identity_target_drift"
        assert report.duplicates[0]["distinct_target_count"] == 2
        assert "duplicate_legacy_identity_targets" in {
            finding.code for finding in report.findings
        }
    finally:
        connection.close()


def test_missing_parity_is_never_reported_as_pass_and_failure_blocks(tmp_path):
    _, manifest, _, connection, _ = _prepare(tmp_path)
    try:
        missing = build_reconciliation_report(
            connection,
            manifest,
            rollback=_rollback(),
            generated_at=STAMP_2,
        )
        assert all(
            section["status"] == "not_run"
            for section in missing.parity["domains"].values()
        )
        assert sum(
            finding.code == "parity_not_run" for finding in missing.findings
        ) == 6

        failed = build_reconciliation_report(
            connection,
            manifest,
            parity_checks=_parity_checks(failed_domain="grade"),
            rollback=_rollback(),
            generated_at=STAMP_2,
        )
        assert failed.status == "blocked"
        assert failed.parity["domains"]["grade"]["status"] == "fail"
        assert any(
            finding.code == "parity_failed" and finding.entity_id == "grade"
            for finding in failed.findings
        )
    finally:
        connection.close()


def test_unverified_or_nonportable_rollback_evidence_never_passes(tmp_path):
    _, manifest, _, connection, _ = _prepare(tmp_path)
    try:
        report = build_reconciliation_report(
            connection,
            manifest,
            parity_checks=_parity_checks(),
            rollback=_rollback(verified=False),
            generated_at=STAMP_2,
        )
        assert report.rollback["status"] == "not_verified"
        assert any(
            finding.code == "rollback_evidence_incomplete"
            for finding in report.findings
        )

        with pytest.raises(ReconciliationInputError):
            build_reconciliation_report(
                connection,
                manifest,
                rollback=RollbackEvidence(
                    backup_used=str(tmp_path / "private-backup.tar"),
                    backup_sha256="a" * 64,
                    command="python restore.py private-backup.tar",
                    runbook="docs/ROLLBACK.md",
                    verified=True,
                ),
            )
        with pytest.raises(ReconciliationInputError):
            build_reconciliation_report(
                connection,
                manifest,
                rollback=RollbackEvidence(
                    backup_used="backup/ok.tar",
                    backup_sha256="a" * 64,
                    command="python restore.py /private/ok.tar",
                    runbook="docs/ROLLBACK.md",
                    verified=True,
                ),
            )
    finally:
        connection.close()


def test_phase3_report_refuses_production_database_name(tmp_path):
    data_dir = tmp_path / "sources"
    data_dir.mkdir()
    manifest = scan_legacy_sources(data_dir, specs=())
    production = tmp_path / "data" / "learning_assistant.db"
    production.parent.mkdir()
    assert apply_migrations(production) == (1, 2)
    connection = connect_database(production, synchronous="FULL")
    try:
        with pytest.raises(ReconciliationSafetyError):
            build_reconciliation_report(connection, manifest)
    finally:
        connection.close()


def test_numeric_parity_honours_documented_tolerance():
    passed = make_parity_check(
        "performance", "rounding-fixture", 0.3333, 0.3334, tolerance=0.0001
    )
    failed = make_parity_check(
        "performance", "rounding-fixture", 0.3333, 0.3335, tolerance=0.0001
    )
    assert passed.status == "pass"
    assert failed.status == "fail"
    with pytest.raises(ReconciliationInputError):
        make_parity_check(
            "performance", "rounding-fixture", 1, 1, tolerance=-0.1
        )
