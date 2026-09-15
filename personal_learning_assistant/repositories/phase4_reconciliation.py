"""Read-only final Phase 4 structured-domain reconciliation helpers.

This module aggregates the already-established Phase 4.1-4.8 dual-read parity
reports and verifies the Phase 3 SQLite relational target without changing
legacy files or SQLite state.

It is intentionally a *readiness/reconciliation* component.  It does not open a
production database, does not switch application authority to SQLite, and does
not block legacy writers.  An explicit authority-promotion implementation is a
separate action after this gate is reviewed and approved.
"""

from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


STATUS_PASS = "pass"
STATUS_REVIEW_REQUIRED = "review_required"
STATUS_BLOCKED = "blocked"

REQUIRED_DOMAINS: Tuple[str, ...] = (
    "courses_topics",
    "assessments_topics",
    "questions_sources",
    "question_topic_mappings",
    "attempts_performance",
    "learning_progress",
    "study_plans",
    "grades_calendar",
)

REQUIRED_TABLES: Tuple[str, ...] = (
    "schema_migrations",
    "migration_imports",
    "semesters",
    "courses",
    "semester_courses",
    "course_aliases",
    "topics",
    "topic_aliases",
    "assessments",
    "assessment_topics",
    "questions",
    "question_sources",
    "question_topic_mappings",
    "question_attempts",
    "mistake_events",
    "learning_memory_entries",
    "topic_progress_events",
    "progress_snapshots",
    "study_plans",
    "study_plan_items",
    "grade_scales",
    "grade_bands",
    "semester_grade_settings",
    "manual_grade_entries",
    "semester_results",
    "academic_events",
)

# Ledger targets owned by the structured domains covered by Phase 4.  Tables not
# in this map (for example app_settings or future Phase 5 tables) are outside
# this report's ownership and are deliberately ignored rather than guessed.
_LEDGER_ID_COLUMNS: Mapping[str, str] = {
    "semesters": "id",
    "courses": "id",
    "topics": "id",
    "assessments": "id",
    "assessment_topics": "id",
    "questions": "id",
    "question_sources": "id",
    "question_topic_mappings": "id",
    "question_attempts": "id",
    "mistake_events": "id",
    "learning_memory_entries": "id",
    "topic_progress_events": "id",
    "progress_snapshots": "id",
    "study_plans": "id",
    "study_plan_items": "id",
    "grade_scales": "id",
    "grade_bands": "id",
    "semester_grade_settings": "semester_id",
    "manual_grade_entries": "id",
    "semester_results": "id",
    "academic_events": "id",
}

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Phase4ReconciliationError(RuntimeError):
    """Base class for final Phase 4 reconciliation failures."""


class Phase4ReconciliationInputError(Phase4ReconciliationError, ValueError):
    """Raised for malformed/ambiguous reconciliation evidence."""


class Phase4ReconciliationSafetyError(Phase4ReconciliationError):
    """Raised when reconciliation is pointed at the production DB filename."""


@dataclass(frozen=True)
class Phase4DomainResult:
    domain: str
    status: str
    report_count: int
    mismatch_count: int
    deferred_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "status": self.status,
            "report_count": self.report_count,
            "mismatch_count": self.mismatch_count,
            "deferred_count": self.deferred_count,
        }


@dataclass(frozen=True)
class Phase4ReconciliationFinding:
    severity: str
    code: str
    message: str
    entity_type: str = ""
    entity_id: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
        }


@dataclass(frozen=True)
class Phase4ReconciliationReport:
    report_version: int
    generated_at: str
    status: str
    authority: Mapping[str, Any]
    domain_results: Tuple[Phase4DomainResult, ...]
    database: Mapping[str, Any]
    ledger_target_failures: Tuple[Mapping[str, Any], ...]
    duplicate_legacy_identities: Tuple[Mapping[str, Any], ...]
    findings: Tuple[Phase4ReconciliationFinding, ...]

    @property
    def mismatch_count(self) -> int:
        return sum(item.mismatch_count for item in self.domain_results)

    @property
    def deferred_count(self) -> int:
        return sum(item.deferred_count for item in self.domain_results)

    @property
    def ready_for_promotion_step(self) -> bool:
        return self.status == STATUS_PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "status": self.status,
            "ready_for_promotion_step": self.ready_for_promotion_step,
            "authority": deepcopy(dict(self.authority)),
            "domain_results": [item.to_dict() for item in self.domain_results],
            "database": deepcopy(dict(self.database)),
            "ledger_target_failures": [deepcopy(dict(item)) for item in self.ledger_target_failures],
            "duplicate_legacy_identities": [
                deepcopy(dict(item)) for item in self.duplicate_legacy_identities
            ],
            "findings": [item.to_dict() for item in self.findings],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _database_label(connection: sqlite3.Connection) -> str:
    rows = connection.execute("PRAGMA database_list").fetchall()
    main_path = ""
    for row in rows:
        if str(row[1]) == "main":
            main_path = str(row[2])
            break
    if not main_path:
        return ":memory:"
    name = Path(main_path).name
    if name.casefold() == "learning_assistant.db":
        raise Phase4ReconciliationSafetyError(
            "Final Phase 4 reconciliation refuses learning_assistant.db; "
            "use an explicit temporary/shadow database."
        )
    return name


def _table_names(connection: sqlite3.Connection) -> Tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    )


def _quote_identifier(value: str) -> str:
    if not _SQL_IDENTIFIER.fullmatch(value):
        raise Phase4ReconciliationInputError(
            "unsafe SQLite identifier in reconciliation target"
        )
    return '"{}"'.format(value)


def _report_value(report: Any, key: str, default: Any = None) -> Any:
    if isinstance(report, Mapping):
        return report.get(key, default)
    return getattr(report, key, default)


def _normalize_reports(value: Any) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        return (value,)
    if hasattr(value, "status") or hasattr(value, "mismatch_count"):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _summarize_domain(domain: str, reports_value: Any) -> Phase4DomainResult:
    reports = _normalize_reports(reports_value)
    if not reports:
        return Phase4DomainResult(
            domain=domain,
            status=STATUS_BLOCKED,
            report_count=0,
            mismatch_count=1,
            deferred_count=0,
        )

    mismatches = 0
    deferred = 0
    for report in reports:
        raw_mismatch = _report_value(report, "mismatch_count", None)
        raw_deferred = _report_value(report, "deferred_count", 0)
        raw_status = str(_report_value(report, "status", "")).strip().casefold()

        if raw_mismatch is None:
            raw_equal = _report_value(report, "is_semantically_equal", None)
            if raw_equal is None:
                raise Phase4ReconciliationInputError(
                    "{} report lacks mismatch_count/is_semantically_equal".format(domain)
                )
            raw_mismatch = 0 if bool(raw_equal) else 1

        try:
            mismatch_count = int(raw_mismatch)
            deferred_count = int(raw_deferred)
        except (TypeError, ValueError) as error:
            raise Phase4ReconciliationInputError(
                "{} report counts must be integers".format(domain)
            ) from error
        if mismatch_count < 0 or deferred_count < 0:
            raise Phase4ReconciliationInputError(
                "{} report counts must be non-negative".format(domain)
            )
        if raw_status in {"mismatch", "error", "blocked", "fail"}:
            mismatch_count = max(1, mismatch_count)
        mismatches += mismatch_count
        deferred += deferred_count

    if mismatches:
        status = STATUS_BLOCKED
    elif deferred:
        status = STATUS_REVIEW_REQUIRED
    else:
        status = STATUS_PASS
    return Phase4DomainResult(
        domain=domain,
        status=status,
        report_count=len(reports),
        mismatch_count=mismatches,
        deferred_count=deferred,
    )


def _ledger_target_failures(
    connection: sqlite3.Connection,
    tables: set[str],
) -> Tuple[Mapping[str, Any], ...]:
    if "migration_imports" not in tables:
        return ()
    rows = connection.execute(
        "SELECT source_path, source_hash, source_type, source_version, "
        "legacy_key, target_table, target_id "
        "FROM migration_imports ORDER BY source_path, legacy_key, target_table, target_id"
    ).fetchall()
    failures = []
    for row in rows:
        target_table = str(row[5])
        target_id = str(row[6])
        if target_table == "semester_courses":
            if "semester_courses" not in tables or "|" not in target_id:
                exists = False
            else:
                semester_id, course_id = target_id.split("|", 1)
                exists = (
                    connection.execute(
                        "SELECT 1 FROM semester_courses "
                        "WHERE semester_id = ? AND course_id = ?",
                        (semester_id, course_id),
                    ).fetchone()
                    is not None
                )
        else:
            id_column = _LEDGER_ID_COLUMNS.get(target_table)
            if id_column is None:
                continue
            if target_table not in tables:
                exists = False
            else:
                sql = "SELECT 1 FROM {} WHERE {} = ?".format(
                    _quote_identifier(target_table),
                    _quote_identifier(id_column),
                )
                exists = connection.execute(sql, (target_id,)).fetchone() is not None
        if not exists:
            failures.append(
                {
                    "source_path": str(row[0]),
                    "source_hash": str(row[1]),
                    "source_type": str(row[2]),
                    "source_version": str(row[3]),
                    "legacy_key": str(row[4]),
                    "target_table": target_table,
                    "target_id": target_id,
                    "reason": "ledger_target_missing",
                }
            )
    return tuple(failures)


def _duplicate_legacy_identities(
    connection: sqlite3.Connection,
    tables: set[str],
) -> Tuple[Mapping[str, Any], ...]:
    if "migration_imports" not in tables:
        return ()
    rows = connection.execute(
        "SELECT source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, COUNT(DISTINCT target_id) "
        "FROM migration_imports "
        "GROUP BY source_path, source_hash, source_type, source_version, legacy_key, target_table "
        "HAVING COUNT(DISTINCT target_id) > 1 "
        "ORDER BY source_path, legacy_key, target_table"
    ).fetchall()
    return tuple(
        {
            "source_path": str(row[0]),
            "source_hash": str(row[1]),
            "source_type": str(row[2]),
            "source_version": str(row[3]),
            "legacy_key": str(row[4]),
            "target_table": str(row[5]),
            "target_count": int(row[6]),
        }
        for row in rows
    )


def build_phase4_reconciliation_report(
    connection: sqlite3.Connection,
    domain_reports: Mapping[str, Any],
    *,
    generated_at: Optional[str] = None,
) -> Phase4ReconciliationReport:
    """Aggregate Phase 4 parity evidence without mutating either authority.

    ``domain_reports`` must contain all eight structured-domain groups.  Each
    value may be one Phase 4 parity report or an iterable of reports.  Domain
    report objects are intentionally duck-typed so the existing per-fix report
    dataclasses can be aggregated without changing them.
    """
    if not isinstance(domain_reports, Mapping):
        raise Phase4ReconciliationInputError("domain_reports must be a mapping")

    supplied = set(str(key) for key in domain_reports)
    missing_domains = sorted(set(REQUIRED_DOMAINS) - supplied)
    extra_domains = sorted(supplied - set(REQUIRED_DOMAINS))
    if missing_domains or extra_domains:
        raise Phase4ReconciliationInputError(
            "Phase 4 domain set mismatch; missing={} extra={}".format(
                missing_domains, extra_domains
            )
        )

    before_changes = connection.total_changes
    label = _database_label(connection)
    table_names = _table_names(connection)
    tables = set(table_names)
    missing_tables = sorted(set(REQUIRED_TABLES) - tables)

    integrity = [
        str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()
    ]
    foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()]

    domain_results = tuple(
        _summarize_domain(domain, domain_reports[domain])
        for domain in REQUIRED_DOMAINS
    )
    ledger_failures = _ledger_target_failures(connection, tables)
    duplicates = _duplicate_legacy_identities(connection, tables)

    findings = []
    if missing_tables:
        findings.append(
            Phase4ReconciliationFinding(
                severity="error",
                code="required_tables_missing",
                message="Required Phase 4 SQLite tables are missing: {}".format(
                    ", ".join(missing_tables)
                ),
                entity_type="database",
            )
        )
    if integrity != ["ok"]:
        findings.append(
            Phase4ReconciliationFinding(
                severity="error",
                code="integrity_check_failed",
                message="PRAGMA integrity_check did not return only 'ok'.",
                entity_type="database",
            )
        )
    if foreign_keys:
        findings.append(
            Phase4ReconciliationFinding(
                severity="error",
                code="foreign_key_check_failed",
                message="PRAGMA foreign_key_check returned violations.",
                entity_type="database",
            )
        )
    if ledger_failures:
        findings.append(
            Phase4ReconciliationFinding(
                severity="error",
                code="ledger_targets_missing",
                message="One or more Phase 4 migration-ledger targets are missing.",
                entity_type="migration_imports",
            )
        )
    if duplicates:
        findings.append(
            Phase4ReconciliationFinding(
                severity="error",
                code="duplicate_legacy_identity_targets",
                message="One current legacy identity maps to multiple SQLite targets.",
                entity_type="migration_imports",
            )
        )

    for result in domain_results:
        if result.status == STATUS_BLOCKED:
            findings.append(
                Phase4ReconciliationFinding(
                    severity="error",
                    code="domain_parity_blocked",
                    message="Phase 4 parity is blocked for {}.".format(result.domain),
                    entity_type="parity",
                    entity_id=result.domain,
                )
            )
        elif result.status == STATUS_REVIEW_REQUIRED:
            findings.append(
                Phase4ReconciliationFinding(
                    severity="warning",
                    code="domain_parity_deferred",
                    message=(
                        "Phase 4 parity contains documented deferred evidence for {}."
                    ).format(result.domain),
                    entity_type="parity",
                    entity_id=result.domain,
                )
            )

    severities = {item.severity for item in findings}
    status = (
        STATUS_BLOCKED
        if "error" in severities
        else STATUS_REVIEW_REQUIRED
        if "warning" in severities
        else STATUS_PASS
    )

    if connection.total_changes != before_changes:
        raise Phase4ReconciliationSafetyError(
            "final Phase 4 reconciliation unexpectedly changed SQLite state"
        )

    return Phase4ReconciliationReport(
        report_version=1,
        generated_at=generated_at or _utc_now(),
        status=status,
        authority={
            "legacy_structured_storage": "authoritative",
            "sqlite": "read_only_shadow",
            "authority_switch_performed": False,
            "legacy_writers_blocked": False,
            "scope": "Phase 4.1-4.8 structured domains",
        },
        domain_results=domain_results,
        database={
            "label": label,
            "role": "temporary_or_explicit_shadow",
            "required_tables": list(REQUIRED_TABLES),
            "missing_required_tables": missing_tables,
            "integrity_check": {
                "status": STATUS_PASS if integrity == ["ok"] else "fail",
                "results": integrity,
            },
            "foreign_key_check": {
                "status": STATUS_PASS if not foreign_keys else "fail",
                "violations": [list(row) for row in foreign_keys],
            },
        },
        ledger_target_failures=ledger_failures,
        duplicate_legacy_identities=duplicates,
        findings=tuple(findings),
    )


def render_phase4_reconciliation_json(
    report: Phase4ReconciliationReport,
    *,
    indent: int = 2,
) -> str:
    if indent < 0:
        raise Phase4ReconciliationInputError("indent must be non-negative")
    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
    ) + "\n"


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", " ")


def render_phase4_reconciliation_markdown(
    report: Phase4ReconciliationReport,
) -> str:
    lines = [
        "# Final Phase 4 Structured Cutover / Reconciliation Readiness Report",
        "",
        "- Status: **{}**".format(report.status),
        "- Generated: `{}`".format(report.generated_at),
        "- SQLite role: `read_only_shadow`",
        "- Authority switch performed: **no**",
        "- Legacy writers blocked: **no**",
        "",
        "> Passing this report means the Phase 4.1-4.8 shadow/reconciliation "
        "foundation is ready for the explicit authority-promotion step. It does "
        "not itself make SQLite authoritative.",
        "",
        "## Domain parity",
        "",
        "| Domain | Status | Reports | Mismatches | Deferred |",
        "|---|---|---:|---:|---:|",
    ]
    for item in report.domain_results:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                _md(item.domain),
                _md(item.status),
                item.report_count,
                item.mismatch_count,
                item.deferred_count,
            )
        )
    lines.extend(
        [
            "",
            "## SQLite checks",
            "",
            "- Database: `{}`".format(_md(report.database["label"])),
            "- Missing required tables: {}".format(
                len(report.database["missing_required_tables"])
            ),
            "- `integrity_check`: **{}**".format(
                report.database["integrity_check"]["status"]
            ),
            "- `foreign_key_check`: **{}**".format(
                report.database["foreign_key_check"]["status"]
            ),
            "- Ledger target failures: {}".format(len(report.ledger_target_failures)),
            "- Duplicate current legacy identities: {}".format(
                len(report.duplicate_legacy_identities)
            ),
            "",
            "## Findings",
            "",
            "| Severity | Code | Entity | Message |",
            "|---|---|---|---|",
        ]
    )
    if report.findings:
        for finding in report.findings:
            entity = finding.entity_type
            if finding.entity_id:
                entity = "{}:{}".format(entity, finding.entity_id)
            lines.append(
                "| {} | {} | {} | {} |".format(
                    _md(finding.severity),
                    _md(finding.code),
                    _md(entity),
                    _md(finding.message),
                )
            )
    else:
        lines.append("| info | none |  | No blocking or deferred findings. |")
    return "\n".join(lines) + "\n"


__all__ = (
    "Phase4DomainResult",
    "Phase4ReconciliationError",
    "Phase4ReconciliationFinding",
    "Phase4ReconciliationInputError",
    "Phase4ReconciliationReport",
    "Phase4ReconciliationSafetyError",
    "REQUIRED_DOMAINS",
    "REQUIRED_TABLES",
    "STATUS_BLOCKED",
    "STATUS_PASS",
    "STATUS_REVIEW_REQUIRED",
    "build_phase4_reconciliation_report",
    "render_phase4_reconciliation_json",
    "render_phase4_reconciliation_markdown",
)
