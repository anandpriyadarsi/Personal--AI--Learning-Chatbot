from __future__ import annotations

import importlib
import inspect
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.phase4_reconciliation import (
    REQUIRED_DOMAINS,
    STATUS_BLOCKED,
    STATUS_PASS,
    STATUS_REVIEW_REQUIRED,
    Phase4ReconciliationInputError,
    Phase4ReconciliationSafetyError,
    build_phase4_reconciliation_report,
    render_phase4_reconciliation_json,
    render_phase4_reconciliation_markdown,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


@dataclass(frozen=True)
class _FakeParityReport:
    status: str = "pass"
    mismatch_count: int = 0
    deferred_count: int = 0

    @property
    def is_semantically_equal(self) -> bool:
        return self.mismatch_count == 0


def _domain_reports(**overrides):
    result = {domain: _FakeParityReport() for domain in REQUIRED_DOMAINS}
    result.update(overrides)
    return result


def _connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "phase4-final-shadow.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    return connect_database(database_path, synchronous="FULL")


def test_matching_all_phase4_domains_and_clean_sqlite_pass_without_writes(tmp_path):
    connection = _connection(tmp_path)
    try:
        before = connection.total_changes
        report = build_phase4_reconciliation_report(
            connection,
            _domain_reports(),
            generated_at="2026-09-15T00:00:00Z",
        )
        assert report.status == STATUS_PASS
        assert report.ready_for_promotion_step is True
        assert report.mismatch_count == 0
        assert report.deferred_count == 0
        assert report.authority["legacy_structured_storage"] == "authoritative"
        assert report.authority["sqlite"] == "read_only_shadow"
        assert report.authority["authority_switch_performed"] is False
        assert report.authority["legacy_writers_blocked"] is False
        assert report.database["integrity_check"]["results"] == ["ok"]
        assert report.database["foreign_key_check"]["violations"] == []
        assert report.database["missing_required_tables"] == []
        assert report.ledger_target_failures == ()
        assert report.duplicate_legacy_identities == ()
        assert connection.total_changes == before
    finally:
        connection.close()


def test_domain_mismatch_blocks_final_reconciliation(tmp_path):
    connection = _connection(tmp_path)
    try:
        report = build_phase4_reconciliation_report(
            connection,
            _domain_reports(
                questions_sources=_FakeParityReport(
                    status="mismatch",
                    mismatch_count=2,
                )
            ),
        )
        assert report.status == STATUS_BLOCKED
        assert report.ready_for_promotion_step is False
        assert report.mismatch_count == 2
        assert any(
            finding.code == "domain_parity_blocked"
            and finding.entity_id == "questions_sources"
            for finding in report.findings
        )
    finally:
        connection.close()


def test_documented_deferred_parity_requires_review_not_silent_pass(tmp_path):
    connection = _connection(tmp_path)
    try:
        report = build_phase4_reconciliation_report(
            connection,
            _domain_reports(
                courses_topics=_FakeParityReport(
                    status="pass_with_deferred",
                    deferred_count=1,
                )
            ),
        )
        assert report.status == STATUS_REVIEW_REQUIRED
        assert report.ready_for_promotion_step is False
        assert report.deferred_count == 1
        assert any(
            finding.code == "domain_parity_deferred"
            for finding in report.findings
        )
    finally:
        connection.close()


def test_missing_or_extra_phase4_domain_evidence_is_rejected(tmp_path):
    connection = _connection(tmp_path)
    try:
        missing = _domain_reports()
        missing.pop("grades_calendar")
        with pytest.raises(Phase4ReconciliationInputError):
            build_phase4_reconciliation_report(connection, missing)

        extra = _domain_reports()
        extra["future_domain"] = _FakeParityReport()
        with pytest.raises(Phase4ReconciliationInputError):
            build_phase4_reconciliation_report(connection, extra)
    finally:
        connection.close()


def test_ledger_target_missing_is_a_blocker(tmp_path):
    connection = _connection(tmp_path)
    try:
        connection.execute(
            "INSERT INTO migration_imports "
            "(id, source_path, source_hash, source_type, source_version, legacy_key, "
            "target_table, target_id, imported_at, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ledger-test-1",
                "data/courses.json",
                "a" * 64,
                "legacy_json",
                "1",
                "course:id:missing",
                "courses",
                "missing-course-target",
                "2026-09-15T00:00:00Z",
                "{}",
            ),
        )
        connection.commit()
        before = connection.total_changes
        report = build_phase4_reconciliation_report(connection, _domain_reports())
        assert report.status == STATUS_BLOCKED
        assert len(report.ledger_target_failures) == 1
        assert report.ledger_target_failures[0]["target_table"] == "courses"
        assert report.ledger_target_failures[0]["target_id"] == "missing-course-target"
        assert connection.total_changes == before
    finally:
        connection.close()


def test_valid_phase4_ledger_target_is_accepted(tmp_path):
    connection = _connection(tmp_path)
    try:
        connection.execute(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                "course-target",
                "SYN100",
                "Synthetic Course",
                "active",
                "",
                "2026-09-15T00:00:00Z",
                "2026-09-15T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO migration_imports "
            "(id, source_path, source_hash, source_type, source_version, legacy_key, "
            "target_table, target_id, imported_at, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ledger-test-2",
                "data/courses.json",
                "b" * 64,
                "legacy_json",
                "1",
                "course:id:synthetic",
                "courses",
                "course-target",
                "2026-09-15T00:00:00Z",
                "{}",
            ),
        )
        connection.commit()
        report = build_phase4_reconciliation_report(connection, _domain_reports())
        assert report.status == STATUS_PASS
        assert report.ledger_target_failures == ()
    finally:
        connection.close()


def test_reconciliation_refuses_production_database_filename(tmp_path):
    database_path = tmp_path / "learning_assistant.db"
    assert (apply_migrations(database_path))[:2] == (1, 2)
    connection = connect_database(database_path, synchronous="FULL")
    try:
        with pytest.raises(Phase4ReconciliationSafetyError):
            build_phase4_reconciliation_report(connection, _domain_reports())
    finally:
        connection.close()


def test_renderers_are_machine_readable_portable_and_explicit_about_authority(tmp_path):
    connection = _connection(tmp_path)
    try:
        report = build_phase4_reconciliation_report(
            connection,
            _domain_reports(),
            generated_at="2026-09-15T00:00:00Z",
        )
        rendered_json = render_phase4_reconciliation_json(report)
        payload = json.loads(rendered_json)
        assert payload["status"] == STATUS_PASS
        assert payload["authority"]["authority_switch_performed"] is False
        assert payload["ready_for_promotion_step"] is True

        markdown = render_phase4_reconciliation_markdown(report)
        assert "# Final Phase 4 Structured Cutover / Reconciliation Readiness Report" in markdown
        assert "Authority switch performed: **no**" in markdown
        assert "does not itself make SQLite authoritative" in markdown
        assert str(tmp_path) not in markdown
    finally:
        connection.close()


def test_all_phase4_backend_configs_still_reject_sqlite_authority_mode():
    modules = (
        "personal_learning_assistant.repositories.course_backend",
        "personal_learning_assistant.repositories.assessment_backend",
        "personal_learning_assistant.repositories.question_backend",
        "personal_learning_assistant.repositories.question_topic_backend",
        "personal_learning_assistant.repositories.attempt_performance_backend",
        "personal_learning_assistant.repositories.learning_progress_backend",
        "personal_learning_assistant.repositories.study_plan_backend",
        "personal_learning_assistant.repositories.grade_calendar_backend",
    )
    for module_name in modules:
        module = importlib.import_module(module_name)
        config_classes = [
            member
            for _, member in inspect.getmembers(module, inspect.isclass)
            if member.__module__ == module_name and member.__name__.endswith("BackendConfig")
        ]
        assert config_classes, "{} exposes no BackendConfig".format(module_name)
        for config_class in config_classes:
            # The completed Phase 4.1-4.8 branch is still legacy-authoritative.
            # The final reconciliation gate must not accidentally introduce a
            # hidden SQLite authority mode.
            with pytest.raises(ValueError):
                config_class("sqlite")
            with pytest.raises(ValueError):
                config_class("sqlite_only")
            assert config_class("legacy").mode == "legacy"
            assert config_class("dual_read").mode == "dual_read"
