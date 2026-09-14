"""Phase 3 read-only migration reconciliation reports.

The report builder consumes an already-open SQLite shadow database, the exact
legacy-source manifest used by the importers, and (optionally) the importer run
results and old/new parity observations.  It never opens a database, writes a
source, mutates SQLite, or treats missing parity/rollback evidence as success.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .legacy_json_import import ImportIssue, ImportTally
from .legacy_source_scanner import (
    LegacySourceManifest,
    LegacySourceSpec,
    STATUS_EMPTY,
    STATUS_MISSING,
    STATUS_VALID_JSON,
    scan_legacy_sources,
)


REPORT_VERSION = 1
EXPECTED_PARITY_DOMAINS: Tuple[str, ...] = (
    "priority",
    "performance",
    "plan",
    "calendar",
    "grade",
    "brief",
)

STATUS_PASS = "pass"
STATUS_REVIEW_REQUIRED = "review_required"
STATUS_BLOCKED = "blocked"
PARITY_NOT_RUN = "not_run"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REPORT_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")

_EXPECTED_TABLES: Tuple[str, ...] = (
    "schema_migrations",
    "app_settings",
    "migration_imports",
    "operation_journal",
    "outbox_events",
    "semesters",
    "courses",
    "semester_courses",
    "course_aliases",
    "course_relations",
    "topics",
    "topic_aliases",
    "vaults",
    "note_metadata",
    "tags",
    "note_tags",
    "note_courses",
    "note_topics",
    "note_links",
    "resources",
    "resource_courses",
    "resource_topics",
    "resource_notes",
    "resource_progress_events",
    "knowledge_documents",
    "resource_documents",
    "knowledge_chunks",
    "index_jobs",
    "assessments",
    "note_assessments",
    "resource_assessments",
    "assessment_topics",
    "questions",
    "question_topic_mappings",
    "question_sources",
    "question_attempts",
    "mistake_events",
    "topic_progress_events",
    "progress_snapshots",
    "learning_memory_entries",
    "study_plans",
    "study_plan_items",
    "study_sessions",
    "grade_scales",
    "grade_bands",
    "semester_grade_settings",
    "manual_grade_entries",
    "semester_results",
    "academic_events",
)

_RELATIONSHIP_QUERIES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("semester_courses", "SELECT COUNT(*) FROM semester_courses", ("semester_courses",)),
    ("course_relations", "SELECT COUNT(*) FROM course_relations", ("course_relations",)),
    ("course_topics", "SELECT COUNT(*) FROM topics WHERE deleted_at IS NULL", ("topics",)),
    ("course_assessments", "SELECT COUNT(*) FROM assessments WHERE deleted_at IS NULL", ("assessments",)),
    ("assessment_topics", "SELECT COUNT(*) FROM assessment_topics", ("assessment_topics",)),
    ("assessment_topics_resolved", "SELECT COUNT(*) FROM assessment_topics WHERE topic_id IS NOT NULL", ("assessment_topics",)),
    ("assessment_questions", "SELECT COUNT(*) FROM questions WHERE deleted_at IS NULL", ("questions",)),
    ("question_topic_mappings", "SELECT COUNT(*) FROM question_topic_mappings", ("question_topic_mappings",)),
    ("question_sources", "SELECT COUNT(*) FROM question_sources", ("question_sources",)),
    ("question_attempts", "SELECT COUNT(*) FROM question_attempts", ("question_attempts",)),
    ("attempt_mistakes", "SELECT COUNT(*) FROM mistake_events", ("mistake_events",)),
    ("topic_progress_events", "SELECT COUNT(*) FROM topic_progress_events", ("topic_progress_events",)),
    ("course_progress_snapshots", "SELECT COUNT(*) FROM progress_snapshots", ("progress_snapshots",)),
    ("study_plan_items", "SELECT COUNT(*) FROM study_plan_items", ("study_plan_items",)),
    ("grade_scale_bands", "SELECT COUNT(*) FROM grade_bands", ("grade_bands",)),
    ("semester_grade_settings", "SELECT COUNT(*) FROM semester_grade_settings", ("semester_grade_settings",)),
    ("semester_manual_grades", "SELECT COUNT(*) FROM manual_grade_entries", ("manual_grade_entries",)),
    ("assessment_calendar_events", "SELECT COUNT(*) FROM academic_events WHERE event_kind = 'assessment_deadline'", ("academic_events",)),
    ("note_courses", "SELECT COUNT(*) FROM note_courses", ("note_courses",)),
    ("note_topics", "SELECT COUNT(*) FROM note_topics", ("note_topics",)),
    ("note_links", "SELECT COUNT(*) FROM note_links", ("note_links",)),
    ("note_assessments", "SELECT COUNT(*) FROM note_assessments", ("note_assessments",)),
    ("resource_courses", "SELECT COUNT(*) FROM resource_courses", ("resource_courses",)),
    ("resource_topics", "SELECT COUNT(*) FROM resource_topics", ("resource_topics",)),
    ("resource_notes", "SELECT COUNT(*) FROM resource_notes", ("resource_notes",)),
    ("resource_assessments", "SELECT COUNT(*) FROM resource_assessments", ("resource_assessments",)),
    ("resource_documents", "SELECT COUNT(*) FROM resource_documents", ("resource_documents",)),
    ("document_chunks", "SELECT COUNT(*) FROM knowledge_chunks", ("knowledge_chunks",)),
    ("resource_progress_events", "SELECT COUNT(*) FROM resource_progress_events", ("resource_progress_events",)),
)

_REVIEW_MARKERS = {
    "ambiguous",
    "deferred",
    "not_configured",
    "review_required",
    "unresolved",
}


class ReconciliationError(RuntimeError):
    """Base class for reconciliation failures."""


class ReconciliationInputError(ReconciliationError, ValueError):
    """Raised when supplied report evidence is malformed or non-portable."""


class ReconciliationSafetyError(ReconciliationError):
    """Raised when a Phase 3 report is pointed at the production DB name."""


@dataclass(frozen=True)
class ReconciliationFinding:
    severity: str
    code: str
    message: str
    entity_type: str = ""
    entity_id: str = ""


@dataclass(frozen=True)
class EntityImportCount:
    entity: str
    created: int
    updated: int
    matched: int

    @property
    def before(self) -> int:
        return self.created + self.updated + self.matched


@dataclass(frozen=True)
class ImportRunSummary:
    importer: str
    source_paths: Tuple[str, ...]
    entities: Tuple[EntityImportCount, ...]
    skipped: int = 0
    flagged: int = 0

    @property
    def before(self) -> int:
        return sum(item.before for item in self.entities) + self.skipped

    @property
    def imported(self) -> int:
        return sum(item.created + item.updated for item in self.entities)

    @property
    def created(self) -> int:
        return sum(item.created for item in self.entities)

    @property
    def updated(self) -> int:
        return sum(item.updated for item in self.entities)

    @property
    def matched(self) -> int:
        return sum(item.matched for item in self.entities)


@dataclass(frozen=True)
class ParityCheck:
    domain: str
    fixture: str
    legacy_value: Any
    sqlite_value: Any
    status: str
    tolerance: Optional[float] = None
    note: str = ""


@dataclass(frozen=True)
class RollbackEvidence:
    backup_used: str
    backup_sha256: str
    command: str
    runbook: str
    verified: bool = False


@dataclass(frozen=True)
class ReconciliationReport:
    report_version: int
    generated_at: str
    status: str
    authority: Mapping[str, Any]
    source_manifest_hash_before: str
    source_manifest_hash_after: str
    sources: Tuple[Mapping[str, Any], ...]
    import_runs: Tuple[ImportRunSummary, ...]
    database: Mapping[str, Any]
    relationship_counts: Mapping[str, Optional[int]]
    duplicates: Tuple[Mapping[str, Any], ...]
    ledger_target_failures: Tuple[Mapping[str, Any], ...]
    unresolved_references: Tuple[Mapping[str, Any], ...]
    assessment_validation: Mapping[str, Any]
    plan_minute_validation: Tuple[Mapping[str, Any], ...]
    grade_validation: Mapping[str, Any]
    calendar_validation: Mapping[str, Any]
    parity: Mapping[str, Any]
    rollback: Mapping[str, Any]
    findings: Tuple[ReconciliationFinding, ...]

    def to_dict(self) -> Dict[str, Any]:
        return _json_safe(self)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, ImportRunSummary):
        return {
            "importer": value.importer,
            "source_paths": [_json_safe(item) for item in value.source_paths],
            "counts": {
                "before": value.before,
                "imported": value.imported,
                "created": value.created,
                "updated": value.updated,
                "matched": value.matched,
                "skipped": value.skipped,
                "flagged": value.flagged,
            },
            "entities": [_json_safe(item) for item in value.entities],
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _portable_path(value: str, field: str) -> str:
    raw = str(value).strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or re.match(r"^[A-Za-z]:/", raw)
        or raw.startswith("//")
        or ".." in path.parts
    ):
        raise ReconciliationInputError(
            "{} must be a non-empty project-relative path".format(field)
        )
    return path.as_posix()


def _safe_label(value: str, field: str) -> str:
    text = str(value).strip()
    if not text or not _REPORT_LABEL_RE.fullmatch(text):
        raise ReconciliationInputError(
            "{} must use portable letters, digits, dot, colon, underscore, or dash"
            .format(field)
        )
    return text


def make_parity_check(
    domain: str,
    fixture: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    tolerance: Optional[float] = None,
    note: str = "",
) -> ParityCheck:
    """Create one explicit old/new comparison without hiding rounding."""
    normalized_domain = _safe_label(domain.lower(), "parity domain")
    normalized_fixture = _safe_label(fixture, "parity fixture")
    if tolerance is not None and tolerance < 0:
        raise ReconciliationInputError("parity tolerance must be non-negative")

    if (
        tolerance is not None
        and not isinstance(legacy_value, bool)
        and not isinstance(sqlite_value, bool)
        and isinstance(legacy_value, (int, float, Decimal))
        and isinstance(sqlite_value, (int, float, Decimal))
    ):
        equal = abs(float(legacy_value) - float(sqlite_value)) <= tolerance
    else:
        equal = legacy_value == sqlite_value

    return ParityCheck(
        domain=normalized_domain,
        fixture=normalized_fixture,
        legacy_value=legacy_value,
        sqlite_value=sqlite_value,
        status=STATUS_PASS if equal else "fail",
        tolerance=tolerance,
        note=str(note),
    )


def _entity_count(name: str, tally: ImportTally) -> EntityImportCount:
    return EntityImportCount(
        entity=name,
        created=int(tally.created),
        updated=int(tally.updated),
        matched=int(tally.matched),
    )


def _flag_count(result: Any, skipped: int) -> int:
    review_items = len(tuple(getattr(result, "review_items", ())))
    issues: Iterable[ImportIssue] = getattr(result, "issues", ())
    warning_count = sum(
        1 for issue in issues if str(issue.severity).lower() in {"warning", "error"}
    )
    return max(review_items, warning_count, int(skipped))


def summarize_import_result(result: Any) -> ImportRunSummary:
    """Normalize any Fix 4–11 result into the report count contract."""
    from .assessments_topics_importer import AssessmentTopicImportResult
    from .attempts_performance_importer import AttemptPerformanceImportResult
    from .courses_topics_importer import CourseTopicImportResult
    from .grades_calendar_importer import GradeCalendarImportResult
    from .learning_progress_importer import LearningProgressImportResult
    from .question_topic_mappings_importer import QuestionTopicMappingImportResult
    from .questions_sources_importer import QuestionSourceImportResult
    from .study_plans_importer import StudyPlanImportResult

    importer = ""
    paths: Tuple[str, ...]
    entities: Tuple[EntityImportCount, ...]
    skipped = 0

    if isinstance(result, CourseTopicImportResult):
        importer = "courses_topics"
        paths = (result.source_path,)
        entities = (
            _entity_count("semesters", result.semesters),
            _entity_count("courses", result.courses),
            _entity_count("semester_courses", result.semester_courses),
            _entity_count("topics", result.topics),
            _entity_count("settings", result.settings),
        )
        skipped = int(result.deferred_document_links)
    elif isinstance(result, AssessmentTopicImportResult):
        importer = "assessments_topics"
        paths = (result.source_path,)
        entities = (
            _entity_count("assessments", result.assessments),
            _entity_count("assessment_topics", result.assessment_topics),
        )
        skipped = int(result.deferred_course_credits)
    elif isinstance(result, QuestionSourceImportResult):
        importer = "questions_sources"
        paths = (result.source_path,)
        entities = (
            _entity_count("questions", result.questions),
            _entity_count("question_sources", result.question_sources),
        )
        skipped = int(result.deferred_topic_records) + int(
            result.deferred_performance_records
        )
    elif isinstance(result, QuestionTopicMappingImportResult):
        importer = "question_topic_mappings"
        paths = (result.source_path,)
        entities = (
            _entity_count("mapping_observations", result.mapping_observations),
            _entity_count("question_topic_mappings", result.question_topic_mappings),
        )
        skipped = int(result.unmapped_questions) + int(
            result.unresolved_candidates
        )
    elif isinstance(result, AttemptPerformanceImportResult):
        importer = "attempts_performance"
        paths = (result.source_path,)
        entities = (
            _entity_count("question_attempts", result.attempts),
            _entity_count("mistake_events", result.mistake_events),
        )
        skipped = int(result.deferred_mistakes)
    elif isinstance(result, LearningProgressImportResult):
        importer = "learning_progress"
        paths = (result.memory_source_path, result.progress_source_path)
        entities = (
            _entity_count("learning_memory_entries", result.learning_memory_entries),
            _entity_count("topic_progress_events", result.topic_progress_events),
            _entity_count("progress_snapshots", result.progress_snapshots),
        )
        skipped = int(result.deferred_activity_records)
    elif isinstance(result, StudyPlanImportResult):
        importer = "study_plans"
        paths = tuple(sorted(result.imported_sources + result.optional_sources_absent))
        entities = (
            _entity_count("study_plans", result.study_plans),
            _entity_count("study_plan_items", result.study_plan_items),
        )
    elif isinstance(result, GradeCalendarImportResult):
        importer = "grades_calendar"
        paths = tuple(sorted(result.imported_sources + result.optional_sources_absent))
        entities = (
            _entity_count("grade_scales", result.grade_scales),
            _entity_count("grade_bands", result.grade_bands),
            _entity_count("semester_grade_settings", result.semester_grade_settings),
            _entity_count("semester_course_credits", result.semester_course_credits),
            _entity_count("manual_grade_entries", result.manual_grade_entries),
            _entity_count("semester_results", result.semester_results),
            _entity_count("academic_events", result.academic_events),
        )
        skipped = int(result.assessments_without_due_date)
    else:
        raise ReconciliationInputError(
            "unsupported importer result type: {}".format(type(result).__name__)
        )

    return ImportRunSummary(
        importer=importer,
        source_paths=tuple(_portable_path(path, "import source path") for path in paths),
        entities=entities,
        skipped=skipped,
        flagged=_flag_count(result, skipped),
    )


def _table_names(connection: sqlite3.Connection) -> Tuple[str, ...]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _quoted_identifier(value: str) -> str:
    if not _SQL_IDENTIFIER_RE.fullmatch(value):
        raise ReconciliationInputError("unsafe SQLite identifier in schema")
    return '"{}"'.format(value)


def _database_label(connection: sqlite3.Connection) -> str:
    rows = connection.execute("PRAGMA database_list").fetchall()
    main_path = ""
    for row in rows:
        if str(row[1]) == "main":
            main_path = str(row[2])
            break
    if not main_path:
        return ":memory:"
    label = Path(main_path).name
    if label.lower() == "learning_assistant.db":
        raise ReconciliationSafetyError(
            "Phase 3 reconciliation refuses data/learning_assistant.db; "
            "use an explicit temporary shadow database"
        )
    return label


def _source_reconciliation(
    manifest: LegacySourceManifest,
    ledger_rows: Sequence[Sequence[Any]],
) -> Tuple[str, Tuple[Mapping[str, Any], ...], Tuple[ReconciliationFinding, ...]]:
    source_roots = {snapshot.physical_path.parent for snapshot in manifest.sources}
    if len(source_roots) > 1:
        raise ReconciliationInputError(
            "all legacy source snapshots must share one data directory"
        )

    if source_roots:
        specs = tuple(
            LegacySourceSpec(
                snapshot.physical_path.name,
                required=snapshot.required,
                allow_empty=snapshot.allow_empty,
                source_type=snapshot.source_type,
            )
            for snapshot in manifest.sources
        )
        after = scan_legacy_sources(next(iter(source_roots)), specs=specs)
    else:
        after = manifest

    observations: Dict[Tuple[str, str], int] = {}
    all_observations: Dict[str, int] = {}
    distinct_targets: Dict[Tuple[str, str], set[Tuple[str, str]]] = {}
    for row in ledger_rows:
        source_path = str(row[0])
        source_hash = str(row[1])
        observations[(source_path, source_hash)] = (
            observations.get((source_path, source_hash), 0) + 1
        )
        all_observations[source_path] = all_observations.get(source_path, 0) + 1
        distinct_targets.setdefault((source_path, source_hash), set()).add(
            (str(row[4]), str(row[5]))
        )

    after_by_path = {item.canonical_path: item for item in after.sources}
    entries = []
    findings = []
    for before in manifest.sources:
        current = after_by_path.get(before.canonical_path)
        preserved = (
            current is not None
            and current.status == before.status
            and current.source_hash == before.source_hash
            and current.byte_count == before.byte_count
        )
        current_observations = observations.get(
            (before.canonical_path, before.source_hash), 0
        )

        if not preserved:
            preservation = "changed"
            findings.append(
                ReconciliationFinding(
                    severity="error",
                    code="legacy_source_changed",
                    message="Legacy source no longer matches the approved manifest.",
                    entity_type="source",
                    entity_id=before.canonical_path,
                )
            )
        else:
            preservation = "unchanged"

        if before.status == STATUS_VALID_JSON:
            coverage = "covered" if current_observations else "uncovered"
            if not current_observations:
                findings.append(
                    ReconciliationFinding(
                        severity="warning",
                        code="source_without_current_ledger_evidence",
                        message="Importable source has no ledger observation for its current hash.",
                        entity_type="source",
                        entity_id=before.canonical_path,
                    )
                )
        elif before.status == STATUS_MISSING and not before.required:
            coverage = "optional_absent"
        elif before.status == STATUS_EMPTY and before.allow_empty:
            coverage = "empty_source"
        else:
            coverage = "not_importable"
            severity = "error" if before.required else "warning"
            findings.append(
                ReconciliationFinding(
                    severity=severity,
                    code="source_not_importable",
                    message=before.issue or "Legacy source is not importable.",
                    entity_type="source",
                    entity_id=before.canonical_path,
                )
            )

        entries.append(
            {
                "path": before.canonical_path,
                "source_type": before.source_type,
                "required": before.required,
                "status": before.status,
                "size_bytes": before.byte_count,
                "sha256": before.source_hash,
                "schema_version": before.source_version,
                "json_kind": before.json_kind,
                "current_status": "missing" if current is None else current.status,
                "current_size_bytes": 0 if current is None else current.byte_count,
                "current_sha256": "" if current is None else current.source_hash,
                "preservation": preservation,
                "coverage": coverage,
                "ledger_observations_current_hash": current_observations,
                "ledger_observations_all_hashes": all_observations.get(
                    before.canonical_path, 0
                ),
                "distinct_targets_current_hash": len(
                    distinct_targets.get(
                        (before.canonical_path, before.source_hash), set()
                    )
                ),
            }
        )

    unexpected_after = tuple(after.unexpected_json_paths)
    if unexpected_after:
        findings.append(
            ReconciliationFinding(
                severity="warning",
                code="unexpected_json_sources",
                message="Unexpected JSON sources require an explicit disposition: {}"
                .format(", ".join(unexpected_after)),
                entity_type="source_manifest",
            )
        )

    if after.manifest_hash != manifest.manifest_hash:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="source_manifest_changed",
                message="Source manifest hash changed after the import run.",
                entity_type="source_manifest",
            )
        )

    return after.manifest_hash, tuple(entries), tuple(findings)


def _ledger_rows(connection: sqlite3.Connection, tables: set[str]) -> Tuple[Tuple[Any, ...], ...]:
    if "migration_imports" not in tables:
        return ()
    rows = connection.execute(
        "SELECT source_path, source_hash, source_type, source_version, "
        "target_table, target_id, legacy_key, details_json "
        "FROM migration_imports "
        "ORDER BY source_path, source_hash, target_table, legacy_key"
    ).fetchall()
    return tuple(tuple(row) for row in rows)


def _ledger_target_findings(
    connection: sqlite3.Connection,
    tables: set[str],
    ledger_rows: Sequence[Sequence[Any]],
) -> Tuple[Mapping[str, Any], ...]:
    findings = []
    primary_keys: Dict[str, Tuple[str, ...]] = {}

    for row in ledger_rows:
        source_path = str(row[0])
        target_table = str(row[4])
        target_id = str(row[5])
        legacy_key = str(row[6])
        reason = ""

        if target_table not in tables or not _SQL_IDENTIFIER_RE.fullmatch(target_table):
            reason = "target_table_missing"
        else:
            if target_table not in primary_keys:
                info = connection.execute(
                    "PRAGMA table_info({})".format(_quoted_identifier(target_table))
                ).fetchall()
                ordered = sorted(
                    ((int(item[5]), str(item[1])) for item in info if int(item[5]) > 0),
                    key=lambda item: item[0],
                )
                primary_keys[target_table] = tuple(item[1] for item in ordered)

            keys = primary_keys[target_table]
            values = (target_id,) if len(keys) == 1 else tuple(target_id.split("|"))
            if not keys:
                reason = "target_table_has_no_primary_key"
            elif len(values) != len(keys):
                reason = "target_id_shape_mismatch"
            else:
                where = " AND ".join(
                    "{} = ?".format(_quoted_identifier(key)) for key in keys
                )
                exists = connection.execute(
                    "SELECT 1 FROM {} WHERE {} LIMIT 1".format(
                        _quoted_identifier(target_table), where
                    ),
                    values,
                ).fetchone()
                if exists is None:
                    reason = "target_row_missing"

        if reason:
            findings.append(
                {
                    "source_path": source_path,
                    "legacy_key": legacy_key,
                    "target_table": target_table,
                    "target_id": target_id,
                    "reason": reason,
                }
            )

    return tuple(findings)


def _duplicate_findings(
    connection: sqlite3.Connection, tables: set[str]
) -> Tuple[Mapping[str, Any], ...]:
    if "migration_imports" not in tables:
        return ()
    rows = connection.execute(
        "SELECT source_path, source_type, legacy_key, target_table, "
        "GROUP_CONCAT(DISTINCT target_id), COUNT(DISTINCT target_id) "
        "FROM migration_imports "
        "GROUP BY source_path, source_type, legacy_key, target_table "
        "HAVING COUNT(DISTINCT target_id) > 1 "
        "ORDER BY source_path, target_table, legacy_key"
    ).fetchall()
    return tuple(
        {
            "kind": "legacy_identity_target_drift",
            "source_path": str(row[0]),
            "source_type": str(row[1]),
            "legacy_key": str(row[2]),
            "target_table": str(row[3]),
            "target_ids": sorted(str(row[4]).split(",")),
            "distinct_target_count": int(row[5]),
        }
        for row in rows
    )


def _details_markers(value: Any, prefix: str = "") -> Tuple[Tuple[str, str], ...]:
    found = []
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            child = value[key]
            path = "{}.{}".format(prefix, key) if prefix else str(key)
            if (
                isinstance(child, str)
                and str(child).strip().lower() in _REVIEW_MARKERS
                and any(token in str(key).lower() for token in ("state", "status", "reason", "resolution"))
            ):
                found.append((path, str(child).strip().lower()))
            found.extend(_details_markers(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_details_markers(child, "{}[{}]".format(prefix, index)))
    return tuple(found)


def _unresolved_references(
    connection: sqlite3.Connection,
    tables: set[str],
    ledger_rows: Sequence[Sequence[Any]],
) -> Tuple[Mapping[str, Any], ...]:
    unresolved = []
    specs = (
        (
            "assessment_topic",
            "assessment_topics",
            "SELECT id, raw_label FROM assessment_topics WHERE topic_id IS NULL ORDER BY id",
            "topic_id",
        ),
        (
            "question_source",
            "question_sources",
            "SELECT id, raw_source_label FROM question_sources "
            "WHERE document_id IS NULL AND resource_id IS NULL AND note_id IS NULL ORDER BY id",
            "document/resource/note",
        ),
        (
            "learning_memory_topic",
            "learning_memory_entries",
            "SELECT id, raw_topic FROM learning_memory_entries "
            "WHERE topic_id IS NULL AND raw_topic <> '' ORDER BY id",
            "topic_id",
        ),
    )
    for category, table, sql, reference in specs:
        if table not in tables:
            continue
        for row in connection.execute(sql).fetchall():
            unresolved.append(
                {
                    "kind": category,
                    "table": table,
                    "row_id": str(row[0]),
                    "reference": reference,
                    "raw_label": str(row[1]),
                }
            )

    if {"study_plan_items", "migration_imports"}.issubset(tables):
        plan_evidence: Dict[str, Mapping[str, Any]] = {}
        evidence_rows = connection.execute(
            "SELECT target_id, details_json FROM migration_imports "
            "WHERE target_table = 'study_plan_items' "
            "ORDER BY imported_at, id"
        ).fetchall()
        for evidence_row in evidence_rows:
            try:
                details = json.loads(str(evidence_row[1]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(details, Mapping):
                plan_evidence[str(evidence_row[0])] = details

        for row in connection.execute(
            "SELECT id, course_id, topic_id FROM study_plan_items "
            "WHERE course_id IS NULL OR topic_id IS NULL ORDER BY id"
        ).fetchall():
            evidence = plan_evidence.get(str(row[0]), {})
            raw_course = str(evidence.get("raw_course_id") or "").strip()
            raw_topic = str(evidence.get("raw_topic") or "").strip()
            if row[1] is None and raw_course:
                unresolved.append(
                    {
                        "kind": "study_plan_course",
                        "table": "study_plan_items",
                        "row_id": str(row[0]),
                        "reference": "course_id",
                        "raw_label": raw_course,
                    }
                )
            if row[2] is None and raw_topic:
                unresolved.append(
                    {
                        "kind": "study_plan_topic",
                        "table": "study_plan_items",
                        "row_id": str(row[0]),
                        "reference": "topic_id",
                        "raw_label": raw_topic,
                    }
                )

    for row in ledger_rows:
        try:
            details = json.loads(str(row[7]))
        except (TypeError, ValueError, json.JSONDecodeError):
            unresolved.append(
                {
                    "kind": "invalid_ledger_details",
                    "table": "migration_imports",
                    "row_id": "{}:{}".format(row[0], row[6]),
                    "reference": "details_json",
                    "raw_label": "",
                }
            )
            continue
        for path, marker in _details_markers(details):
            unresolved.append(
                {
                    "kind": "ledger_review_marker",
                    "table": str(row[4]),
                    "row_id": str(row[5]),
                    "reference": path,
                    "raw_label": marker,
                    "source_path": str(row[0]),
                    "legacy_key": str(row[6]),
                }
            )

    unique: Dict[str, Mapping[str, Any]] = {}
    for item in unresolved:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        unique[key] = item
    return tuple(unique[key] for key in sorted(unique))


def _assessment_validation(
    connection: sqlite3.Connection, tables: set[str]
) -> Mapping[str, Any]:
    if "assessments" not in tables:
        return {
            "status": "unavailable",
            "courses": [],
            "score_issue_ids": [],
            "assessments_missing_weight": 0,
        }

    rows = connection.execute(
        "SELECT course_id, COUNT(*), COUNT(weight_bps), COALESCE(SUM(weight_bps), 0) "
        "FROM assessments WHERE deleted_at IS NULL GROUP BY course_id ORDER BY course_id"
    ).fetchall()
    courses = []
    overall = STATUS_PASS
    for row in rows:
        total = int(row[1])
        weighted = int(row[2])
        weight_sum = int(row[3])
        if weighted == 0:
            status = "not_provided"
        elif weighted < total:
            status = "partial"
            overall = STATUS_REVIEW_REQUIRED
        elif weight_sum == 10000:
            status = STATUS_PASS
        elif weight_sum > 10000:
            status = "overallocated"
            overall = STATUS_BLOCKED
        else:
            status = "underallocated"
            overall = STATUS_REVIEW_REQUIRED
        courses.append(
            {
                "course_id": str(row[0]),
                "assessment_count": total,
                "weighted_assessment_count": weighted,
                "weight_bps": weight_sum,
                "status": status,
            }
        )

    score_rows = connection.execute(
        "SELECT id FROM assessments WHERE "
        "(earned_points_milli IS NOT NULL AND max_points_milli IS NULL) OR "
        "(earned_points_milli IS NOT NULL AND max_points_milli IS NOT NULL "
        "AND earned_points_milli > max_points_milli) ORDER BY id"
    ).fetchall()
    score_issue_ids = [str(row[0]) for row in score_rows]
    if score_issue_ids:
        overall = STATUS_BLOCKED
    missing_weight = int(
        connection.execute(
            "SELECT COUNT(*) FROM assessments "
            "WHERE deleted_at IS NULL AND weight_bps IS NULL"
        ).fetchone()[0]
    )
    return {
        "status": overall,
        "courses": courses,
        "score_issue_ids": score_issue_ids,
        "assessments_missing_weight": missing_weight,
    }


def _plan_minute_validation(
    connection: sqlite3.Connection, tables: set[str]
) -> Tuple[Mapping[str, Any], ...]:
    if not {"study_plans", "study_plan_items"}.issubset(tables):
        return ()
    rows = connection.execute(
        "SELECT p.id, p.kind, p.engine_name, p.engine_version, "
        "p.requested_minutes, p.allocated_minutes, "
        "COALESCE(SUM(CASE WHEN i.status <> 'superseded' THEN i.minutes ELSE 0 END), 0) "
        "FROM study_plans AS p LEFT JOIN study_plan_items AS i ON i.plan_id = p.id "
        "GROUP BY p.id, p.kind, p.engine_name, p.engine_version, "
        "p.requested_minutes, p.allocated_minutes ORDER BY p.kind, p.id"
    ).fetchall()
    output = []
    for row in rows:
        requested = int(row[4])
        allocated = int(row[5])
        item_minutes = int(row[6])
        if item_minutes != allocated:
            status = STATUS_BLOCKED
        elif requested != allocated:
            status = "documented_difference"
        else:
            status = STATUS_PASS
        output.append(
            {
                "plan_id": str(row[0]),
                "kind": str(row[1]),
                "engine_name": str(row[2]),
                "engine_version": str(row[3]),
                "requested_minutes": requested,
                "allocated_minutes": allocated,
                "active_item_minutes": item_minutes,
                "allocation_gap_minutes": requested - allocated,
                "status": status,
            }
        )
    return tuple(output)


def _grade_validation(
    connection: sqlite3.Connection, tables: set[str]
) -> Mapping[str, Any]:
    needed = {"grade_scales", "semester_courses", "semester_results"}
    if not needed.issubset(tables):
        return {
            "status": "unavailable",
            "unverified_grade_scales": 0,
            "semester_courses_without_credits": 0,
            "semester_result_issues": [],
        }

    unverified = int(
        connection.execute(
            "SELECT COUNT(*) FROM grade_scales WHERE verified = 0"
        ).fetchone()[0]
    )
    missing_credits = int(
        connection.execute(
            "SELECT COUNT(*) FROM semester_courses WHERE credits_milli IS NULL"
        ).fetchone()[0]
    )
    result_issues = []
    rows = connection.execute(
        "SELECT id, earned_credits_milli, earned_grade_points_milli, sgpa_milli "
        "FROM semester_results ORDER BY id"
    ).fetchall()
    for row in rows:
        credits = int(row[1])
        grade_points = int(row[2])
        actual = int(row[3])
        if credits == 0:
            expected = 0 if grade_points == 0 else None
        else:
            expected = int(
                (Decimal(grade_points) * Decimal(1000) / Decimal(credits)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
        if expected is None or expected != actual:
            result_issues.append(
                {
                    "semester_result_id": str(row[0]),
                    "expected_sgpa_milli": expected,
                    "actual_sgpa_milli": actual,
                }
            )

    if result_issues:
        status = STATUS_BLOCKED
    elif unverified or missing_credits:
        status = STATUS_REVIEW_REQUIRED
    else:
        status = STATUS_PASS
    return {
        "status": status,
        "unverified_grade_scales": unverified,
        "semester_courses_without_credits": missing_credits,
        "semester_result_issues": result_issues,
    }


def _calendar_validation(
    connection: sqlite3.Connection, tables: set[str]
) -> Mapping[str, Any]:
    if not {"assessments", "academic_events"}.issubset(tables):
        return {
            "status": "unavailable",
            "assessments_with_due_date": 0,
            "active_deadline_events": 0,
            "missing_event_ids": [],
            "duplicate_event_ids": [],
            "mismatched_event_ids": [],
            "stale_event_ids": [],
        }

    assessments = connection.execute(
        "SELECT id, course_id, title, due_on, due_time FROM assessments "
        "WHERE deleted_at IS NULL ORDER BY id"
    ).fetchall()
    events = connection.execute(
        "SELECT id, course_id, title, starts_at, all_day, reference_type, "
        "reference_id, source_entity_type, source_entity_id FROM academic_events "
        "WHERE deleted_at IS NULL AND event_kind = 'assessment_deadline' "
        "ORDER BY id"
    ).fetchall()
    by_assessment: Dict[str, list[Sequence[Any]]] = {}
    for event in events:
        by_assessment.setdefault(str(event[6]), []).append(event)

    missing = []
    duplicates = []
    mismatched = []
    stale = []
    assessment_ids = {str(row[0]) for row in assessments}
    due_count = 0
    for assessment in assessments:
        assessment_id = str(assessment[0])
        due_on = None if assessment[3] is None else str(assessment[3])
        linked = by_assessment.get(assessment_id, [])
        if due_on is None:
            stale.extend(str(item[0]) for item in linked)
            continue
        due_count += 1
        if not linked:
            missing.append(assessment_id)
            continue
        if len(linked) > 1:
            duplicates.extend(str(item[0]) for item in linked)
            continue
        event = linked[0]
        due_time = None if assessment[4] is None else str(assessment[4])
        expected_start = due_on if due_time is None else "{}T{}".format(due_on, due_time)
        expected_all_day = 1 if due_time is None else 0
        if (
            str(event[1]) != str(assessment[1])
            or str(event[2]) != str(assessment[2])
            or str(event[3]) != expected_start
            or int(event[4]) != expected_all_day
            or str(event[5]) != "assessment"
            or str(event[7]) != "assessment"
            or str(event[8]) != assessment_id
        ):
            mismatched.append(str(event[0]))

    for assessment_id, linked in by_assessment.items():
        if assessment_id not in assessment_ids:
            stale.extend(str(item[0]) for item in linked)

    has_errors = any((missing, duplicates, mismatched, stale))
    return {
        "status": STATUS_BLOCKED if has_errors else STATUS_PASS,
        "assessments_with_due_date": due_count,
        "active_deadline_events": len(events),
        "missing_event_ids": sorted(missing),
        "duplicate_event_ids": sorted(duplicates),
        "mismatched_event_ids": sorted(mismatched),
        "stale_event_ids": sorted(set(stale)),
    }


def _parity_summary(checks: Sequence[ParityCheck]) -> Mapping[str, Any]:
    grouped: Dict[str, list[ParityCheck]] = {
        domain: [] for domain in EXPECTED_PARITY_DOMAINS
    }
    for check in checks:
        domain = _safe_label(check.domain.lower(), "parity domain")
        _safe_label(check.fixture, "parity fixture")
        if check.status not in {STATUS_PASS, "fail"}:
            raise ReconciliationInputError("parity status must be pass or fail")
        grouped.setdefault(domain, []).append(check)

    domains: Dict[str, Any] = {}
    for domain in sorted(grouped):
        domain_checks = sorted(grouped[domain], key=lambda item: item.fixture)
        if not domain_checks:
            status = PARITY_NOT_RUN
        elif any(item.status == "fail" for item in domain_checks):
            status = "fail"
        else:
            status = STATUS_PASS
        domains[domain] = {
            "status": status,
            "checks": [_json_safe(item) for item in domain_checks],
        }
    return {"required_domains": list(EXPECTED_PARITY_DOMAINS), "domains": domains}


def _rollback_summary(evidence: Optional[RollbackEvidence]) -> Mapping[str, Any]:
    if evidence is None:
        return {
            "status": "not_provided",
            "backup_used": "",
            "backup_sha256": "",
            "command": "",
            "runbook": "",
            "verified": False,
        }

    backup = _portable_path(evidence.backup_used, "rollback backup_used")
    runbook = _portable_path(evidence.runbook, "rollback runbook")
    digest = str(evidence.backup_sha256).strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        raise ReconciliationInputError(
            "rollback backup_sha256 must be a 64-character SHA-256 digest"
        )
    command = str(evidence.command).strip()
    if not command:
        raise ReconciliationInputError("rollback command must not be empty")
    if re.search(r"(^|\s)(?:[A-Za-z]:[\\/]|/)", command):
        raise ReconciliationInputError(
            "rollback command must use project-relative paths"
        )
    status = STATUS_PASS if evidence.verified else "not_verified"
    return {
        "status": status,
        "backup_used": backup,
        "backup_sha256": digest,
        "command": command,
        "runbook": runbook,
        "verified": bool(evidence.verified),
    }


def _database_summary(
    connection: sqlite3.Connection,
    table_names: Tuple[str, ...],
) -> Mapping[str, Any]:
    tables = set(table_names)
    counts = {
        table: int(
            connection.execute(
                "SELECT COUNT(*) FROM {}".format(_quoted_identifier(table))
            ).fetchone()[0]
        )
        for table in table_names
    }
    if "schema_migrations" in tables:
        migrations = [
            {
                "version": int(row[0]),
                "name": str(row[1]),
                "checksum": str(row[2]),
            }
            for row in connection.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
    else:
        migrations = []

    integrity_rows = [
        str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()
    ]
    fk_rows = [
        {
            "table": str(row[0]),
            "rowid": None if row[1] is None else int(row[1]),
            "parent": str(row[2]),
            "foreign_key_index": int(row[3]),
        }
        for row in connection.execute("PRAGMA foreign_key_check").fetchall()
    ]
    missing = sorted(set(_EXPECTED_TABLES) - tables)
    return {
        "label": _database_label(connection),
        "role": "temporary_shadow",
        "schema_migrations": migrations,
        "missing_expected_tables": missing,
        "table_counts": counts,
        "integrity_check": {
            "status": STATUS_PASS if integrity_rows == ["ok"] else "fail",
            "results": integrity_rows,
        },
        "foreign_key_check": {
            "status": STATUS_PASS if not fk_rows else "fail",
            "violations": fk_rows,
        },
    }


def build_reconciliation_report(
    connection: sqlite3.Connection,
    manifest: LegacySourceManifest,
    *,
    import_results: Sequence[Any] = (),
    import_runs: Sequence[ImportRunSummary] = (),
    parity_checks: Sequence[ParityCheck] = (),
    rollback: Optional[RollbackEvidence] = None,
    generated_at: Optional[str] = None,
) -> ReconciliationReport:
    """Build a complete read-only Fix 12 report from explicit evidence."""
    before_changes = connection.total_changes
    table_names = _table_names(connection)
    tables = set(table_names)
    database = _database_summary(connection, table_names)
    ledger_rows = _ledger_rows(connection, tables)
    after_hash, sources, source_findings = _source_reconciliation(
        manifest, ledger_rows
    )

    summaries = tuple(import_runs) + tuple(
        summarize_import_result(result) for result in import_results
    )
    for summary in summaries:
        _safe_label(summary.importer, "importer")
        for path in summary.source_paths:
            _portable_path(path, "import source path")
        if min(summary.skipped, summary.flagged) < 0:
            raise ReconciliationInputError("import counts must be non-negative")

    ledger_orphans = _ledger_target_findings(
        connection, tables, ledger_rows
    )
    duplicates = _duplicate_findings(connection, tables)
    unresolved = _unresolved_references(connection, tables, ledger_rows)

    relationship_counts: Dict[str, Optional[int]] = {}
    for name, sql, required in _RELATIONSHIP_QUERIES:
        relationship_counts[name] = (
            int(connection.execute(sql).fetchone()[0])
            if set(required).issubset(tables)
            else None
        )

    assessments = _assessment_validation(connection, tables)
    plans = _plan_minute_validation(connection, tables)
    grades = _grade_validation(connection, tables)
    calendar = _calendar_validation(connection, tables)
    parity = _parity_summary(parity_checks)
    rollback_summary = _rollback_summary(rollback)

    findings = list(source_findings)
    missing_tables = database["missing_expected_tables"]
    if missing_tables:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="schema_tables_missing",
                message="Expected migration tables are missing: {}".format(
                    ", ".join(missing_tables)
                ),
                entity_type="database",
            )
        )
    if database["integrity_check"]["status"] != STATUS_PASS:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="integrity_check_failed",
                message="PRAGMA integrity_check did not return only ok.",
                entity_type="database",
            )
        )
    if database["foreign_key_check"]["status"] != STATUS_PASS:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="foreign_key_check_failed",
                message="PRAGMA foreign_key_check returned violations.",
                entity_type="database",
            )
        )
    for item in ledger_orphans:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="ledger_target_invalid",
                message="Migration ledger target cannot be resolved: {}."
                .format(item["reason"]),
                entity_type=str(item["target_table"]),
                entity_id=str(item["target_id"]),
            )
        )
    if duplicates:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="duplicate_legacy_identity_targets",
                message="One or more legacy identities drifted to multiple targets.",
                entity_type="migration_imports",
            )
        )
    if unresolved:
        findings.append(
            ReconciliationFinding(
                severity="warning",
                code="unresolved_references",
                message="Unresolved/review references remain: {}.".format(
                    len(unresolved)
                ),
                entity_type="migration",
            )
        )
    if any(summary.flagged for summary in summaries):
        findings.append(
            ReconciliationFinding(
                severity="warning",
                code="import_records_flagged",
                message="Importer results contain flagged records requiring review.",
                entity_type="import_run",
            )
        )
    if assessments["status"] == STATUS_BLOCKED:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="assessment_validation_failed",
                message="Assessment weight or score validation failed.",
                entity_type="assessments",
            )
        )
    elif assessments["status"] == STATUS_REVIEW_REQUIRED:
        findings.append(
            ReconciliationFinding(
                severity="warning",
                code="assessment_weights_require_review",
                message="Assessment weights are incomplete or underallocated.",
                entity_type="assessments",
            )
        )
    if any(item["status"] == STATUS_BLOCKED for item in plans):
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="plan_item_minutes_mismatch",
                message="Allocated plan minutes do not equal active item minutes.",
                entity_type="study_plans",
            )
        )
    if any(item["status"] == "documented_difference" for item in plans):
        findings.append(
            ReconciliationFinding(
                severity="warning",
                code="requested_allocated_minutes_differ",
                message="Requested and allocated plan minutes differ; source values were preserved.",
                entity_type="study_plans",
            )
        )
    if grades["status"] == STATUS_BLOCKED:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="semester_result_validation_failed",
                message="Stored semester result does not reconcile to SGPA evidence.",
                entity_type="semester_results",
            )
        )
    elif grades["status"] == STATUS_REVIEW_REQUIRED:
        findings.append(
            ReconciliationFinding(
                severity="warning",
                code="grade_evidence_requires_review",
                message="Unverified grade scales or missing course credits remain.",
                entity_type="grades",
            )
        )
    if calendar["status"] == STATUS_BLOCKED:
        findings.append(
            ReconciliationFinding(
                severity="error",
                code="calendar_projection_failed",
                message="Assessment deadlines and active calendar events do not reconcile.",
                entity_type="academic_events",
            )
        )

    parity_domains = parity["domains"]
    for domain in EXPECTED_PARITY_DOMAINS:
        domain_status = parity_domains[domain]["status"]
        if domain_status == "fail":
            findings.append(
                ReconciliationFinding(
                    severity="error",
                    code="parity_failed",
                    message="Old-versus-new parity failed for {}.".format(domain),
                    entity_type="parity",
                    entity_id=domain,
                )
            )
        elif domain_status == PARITY_NOT_RUN:
            findings.append(
                ReconciliationFinding(
                    severity="warning",
                    code="parity_not_run",
                    message="Old-versus-new parity has not run for {}.".format(domain),
                    entity_type="parity",
                    entity_id=domain,
                )
            )
    if rollback_summary["status"] != STATUS_PASS:
        findings.append(
            ReconciliationFinding(
                severity="warning",
                code="rollback_evidence_incomplete",
                message="Verified backup, rollback command, and runbook are not complete.",
                entity_type="rollback",
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
        raise ReconciliationSafetyError(
            "reconciliation unexpectedly changed the SQLite connection"
        )

    return ReconciliationReport(
        report_version=REPORT_VERSION,
        generated_at=generated_at or _utc_now_text(),
        status=status,
        authority={
            "legacy_structured_files": "authoritative",
            "sqlite": "temporary_shadow_reconciliation_target",
            "cutover_performed": False,
        },
        source_manifest_hash_before=manifest.manifest_hash,
        source_manifest_hash_after=after_hash,
        sources=sources,
        import_runs=summaries,
        database=database,
        relationship_counts=relationship_counts,
        duplicates=duplicates,
        ledger_target_failures=ledger_orphans,
        unresolved_references=unresolved,
        assessment_validation=assessments,
        plan_minute_validation=plans,
        grade_validation=grades,
        calendar_validation=calendar,
        parity=parity,
        rollback=rollback_summary,
        findings=tuple(findings),
    )


def render_reconciliation_json(
    report: ReconciliationReport, *, indent: int = 2
) -> str:
    """Render deterministic, UTF-8-safe machine-readable report JSON."""
    if indent < 0:
        raise ReconciliationInputError("JSON indent must be non-negative")
    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
    ) + "\n"


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _md_json(value: Any) -> str:
    return _md(
        json.dumps(
            _json_safe(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def render_reconciliation_markdown(report: ReconciliationReport) -> str:
    """Render the same evidence as a portable human-review report."""
    lines = [
        "# Phase 3 Migration Reconciliation Report",
        "",
        "- Status: **{}**".format(report.status),
        "- Generated: `{}`".format(report.generated_at),
        "- Database role: `temporary_shadow`",
        "- Legacy/current files remain authoritative; no cutover was performed.",
        "",
        "## Source preservation and coverage",
        "",
        "| Source | Status | Bytes | Scanned SHA-256 | Current SHA-256 | Version | Preserved | Coverage | Current ledger rows |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for source in report.sources:
        lines.append(
            "| {path} | {status} | {size_bytes} | `{sha256}` | `{current_sha256}` | {schema_version} | "
            "{preservation} | {coverage} | {ledger_observations_current_hash} |"
            .format(**{key: _md(value) for key, value in source.items()})
        )

    lines.extend(
        [
            "",
            "## Import run counts",
            "",
            "| Importer | Sources | Before | Imported | Created | Updated | Matched | Skipped | Flagged |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if report.import_runs:
        for run in report.import_runs:
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    _md(run.importer),
                    _md(", ".join(run.source_paths)),
                    run.before,
                    run.imported,
                    run.created,
                    run.updated,
                    run.matched,
                    run.skipped,
                    run.flagged,
                )
            )
    else:
        lines.append("| _No importer results supplied_ |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")

    lines.extend(
        [
            "",
            "## SQLite checks",
            "",
            "- `integrity_check`: **{}** — {}".format(
                report.database["integrity_check"]["status"],
                _md(", ".join(report.database["integrity_check"]["results"])),
            ),
            "- `foreign_key_check`: **{}** — {} violation(s)".format(
                report.database["foreign_key_check"]["status"],
                len(report.database["foreign_key_check"]["violations"]),
            ),
            "- Ledger target failures: {}".format(
                len(report.ledger_target_failures)
            ),
            "- Duplicate legacy identities: {}".format(len(report.duplicates)),
            "- Unresolved/review references: {}".format(
                len(report.unresolved_references)
            ),
            "",
            "### Applied schema migrations",
            "",
            "| Version | Name | Checksum |",
            "|---:|---|---|",
        ]
    )
    if report.database["schema_migrations"]:
        for migration in report.database["schema_migrations"]:
            lines.append(
                "| {version} | {name} | `{checksum}` |".format(
                    **{key: _md(value) for key, value in migration.items()}
                )
            )
    else:
        lines.append("|  | _No applied migrations_ |  |")

    lines.extend(
        [
            "",
            "### SQLite table counts",
            "",
            "| Table | Rows |",
            "|---|---:|",
        ]
    )
    for table, count in sorted(report.database["table_counts"].items()):
        lines.append("| {} | {} |".format(_md(table), count))

    lines.extend(
        [
            "",
            "### Relationship counts",
            "",
            "| Relationship | Rows |",
            "|---|---:|",
        ]
    )
    for relationship, count in sorted(report.relationship_counts.items()):
        lines.append(
            "| {} | {} |".format(
                _md(relationship), "unavailable" if count is None else count
            )
        )

    lines.extend(
        [
            "",
            "### Duplicate identities",
            "",
            "| Source | Legacy key | Target table | Target IDs |",
            "|---|---|---|---|",
        ]
    )
    if report.duplicates:
        for item in report.duplicates:
            lines.append(
                "| {source_path} | {legacy_key} | {target_table} | {target_ids} |"
                .format(
                    source_path=_md(item["source_path"]),
                    legacy_key=_md(item["legacy_key"]),
                    target_table=_md(item["target_table"]),
                    target_ids=_md(", ".join(item["target_ids"])),
                )
            )
    else:
        lines.append("| _None_ |  |  |  |")

    lines.extend(
        [
            "",
            "### Ledger target failures",
            "",
            "| Source | Legacy key | Target | Reason |",
            "|---|---|---|---|",
        ]
    )
    if report.ledger_target_failures:
        for item in report.ledger_target_failures:
            lines.append(
                "| {source_path} | {legacy_key} | {target_table}:{target_id} | {reason} |"
                .format(**{key: _md(value) for key, value in item.items()})
            )
    else:
        lines.append("| _None_ |  |  |  |")

    lines.extend(
        [
            "",
            "### Unresolved and review references",
            "",
            "| Kind | Table | Row | Reference | Raw value |",
            "|---|---|---|---|---|",
        ]
    )
    if report.unresolved_references:
        for item in report.unresolved_references:
            lines.append(
                "| {} | {} | {} | {} | {} |".format(
                    _md(item.get("kind", "")),
                    _md(item.get("table", "")),
                    _md(item.get("row_id", "")),
                    _md(item.get("reference", "")),
                    _md(item.get("raw_label", "")),
                )
            )
    else:
        lines.append("| _None_ |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Domain validation",
            "",
            "- Assessment weights/scores: **{}**".format(
                report.assessment_validation["status"]
            ),
            "- Grades: **{}**".format(report.grade_validation["status"]),
            "- Assessment calendar: **{}**".format(
                report.calendar_validation["status"]
            ),
            "- Assessments missing weights: {}".format(
                report.assessment_validation["assessments_missing_weight"]
            ),
            "- Assessment score issue IDs: {}".format(
                _md(", ".join(report.assessment_validation["score_issue_ids"]) or "none")
            ),
            "- Unverified grade scales: {}".format(
                report.grade_validation["unverified_grade_scales"]
            ),
            "- Semester courses without credits: {}".format(
                report.grade_validation["semester_courses_without_credits"]
            ),
            "- Semester result issues: {}".format(
                _md_json(report.grade_validation["semester_result_issues"])
            ),
            "- Calendar missing events: {}".format(
                _md(", ".join(report.calendar_validation["missing_event_ids"]) or "none")
            ),
            "- Calendar duplicate events: {}".format(
                _md(", ".join(report.calendar_validation["duplicate_event_ids"]) or "none")
            ),
            "- Calendar mismatched events: {}".format(
                _md(", ".join(report.calendar_validation["mismatched_event_ids"]) or "none")
            ),
            "- Calendar stale events: {}".format(
                _md(", ".join(report.calendar_validation["stale_event_ids"]) or "none")
            ),
            "",
            "### Assessment weight totals",
            "",
            "| Course | Assessments | With weight | Weight bps | Status |",
            "|---|---:|---:|---:|---|",
        ]
    )
    if report.assessment_validation["courses"]:
        for course in report.assessment_validation["courses"]:
            lines.append(
                "| {course_id} | {assessment_count} | {weighted_assessment_count} | "
                "{weight_bps} | {status} |".format(
                    **{key: _md(value) for key, value in course.items()}
                )
            )
    else:
        lines.append("| _No assessments_ | 0 | 0 | 0 | pass |")

    lines.extend(
        [
            "",
            "### Requested versus allocated plan minutes",
            "",
            "| Plan | Engine | Requested | Allocated | Item total | Gap | Status |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    if report.plan_minute_validation:
        for plan in report.plan_minute_validation:
            lines.append(
                "| {plan_id} | {engine_name} {engine_version} | {requested_minutes} | "
                "{allocated_minutes} | {active_item_minutes} | {allocation_gap_minutes} | "
                "{status} |".format(**{key: _md(value) for key, value in plan.items()})
            )
    else:
        lines.append("| _No plans_ |  | 0 | 0 | 0 | 0 | pass |")

    lines.extend(
        [
            "",
            "## Old-versus-new parity",
            "",
            "| Domain | Fixture | Legacy | SQLite | Tolerance | Status | Note |",
            "|---|---|---|---|---:|---|---|",
        ]
    )
    for domain in EXPECTED_PARITY_DOMAINS:
        section = report.parity["domains"][domain]
        if section["checks"]:
            for check in section["checks"]:
                lines.append(
                    "| {} | {} | `{}` | `{}` | {} | {} | {} |".format(
                        _md(domain),
                        _md(check["fixture"]),
                        _md_json(check["legacy_value"]),
                        _md_json(check["sqlite_value"]),
                        "" if check["tolerance"] is None else check["tolerance"],
                        _md(check["status"]),
                        _md(check["note"]),
                    )
                )
        else:
            lines.append(
                "| {} | _not run_ |  |  |  | {} |  |".format(
                    _md(domain), _md(section["status"])
                )
            )

    lines.extend(
        [
            "",
            "## Rollback evidence",
            "",
            "- Status: **{}**".format(report.rollback["status"]),
            "- Backup used: `{}`".format(_md(report.rollback["backup_used"] or "not provided")),
            "- Backup SHA-256: `{}`".format(_md(report.rollback["backup_sha256"] or "not provided")),
            "- Command: `{}`".format(_md(report.rollback["command"] or "not provided")),
            "- Runbook: `{}`".format(_md(report.rollback["runbook"] or "not provided")),
            "",
            "## Findings",
            "",
            "| Severity | Code | Entity | Message |",
            "|---|---|---|---|",
        ]
    )
    if report.findings:
        for finding in report.findings:
            entity = ":".join(
                part for part in (finding.entity_type, finding.entity_id) if part
            )
            lines.append(
                "| {} | `{}` | {} | {} |".format(
                    _md(finding.severity),
                    _md(finding.code),
                    _md(entity),
                    _md(finding.message),
                )
            )
    else:
        lines.append("| info | `none` |  | No findings. |")

    lines.append("")
    return "\n".join(lines)


# Discoverable aliases using the feature title and generator terminology.
generate_reconciliation_report = build_reconciliation_report
render_reconciliation_report_json = render_reconciliation_json
render_reconciliation_report_markdown = render_reconciliation_markdown


__all__: Tuple[str, ...] = (
    "EXPECTED_PARITY_DOMAINS",
    "EntityImportCount",
    "ImportRunSummary",
    "ParityCheck",
    "ReconciliationError",
    "ReconciliationFinding",
    "ReconciliationInputError",
    "ReconciliationReport",
    "ReconciliationSafetyError",
    "RollbackEvidence",
    "build_reconciliation_report",
    "generate_reconciliation_report",
    "make_parity_check",
    "render_reconciliation_json",
    "render_reconciliation_markdown",
    "render_reconciliation_report_json",
    "render_reconciliation_report_markdown",
    "summarize_import_result",
)
