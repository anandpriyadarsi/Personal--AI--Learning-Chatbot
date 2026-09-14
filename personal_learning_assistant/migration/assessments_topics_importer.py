"""Idempotent Phase 3 importer for legacy ``assessments.json``.

This is a shadow migration adapter only. It imports a verified legacy snapshot
into an explicit temporary SQLite database while JSON remains authoritative.
Assessment topic strings are preserved as unresolved raw labels; this importer
never guesses links to normalized course topics.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Tuple

from personal_learning_assistant.repositories.sqlite.connection import transaction

from .import_ledger import MigrationImportLedger, build_import_identity
from .legacy_json_import import (
    ImportIssue,
    ImportTally,
    LegacyImportDataError,
    LegacyImportError,
    add_tally,
    ensure_tables,
    freeze_tally,
    load_verified_json,
    source_sha256,
    stable_target_id,
)
from .legacy_source_scanner import LegacySourceSnapshot


REQUIRED_TABLES = (
    "migration_imports",
    "courses",
    "assessments",
    "assessment_topics",
)

VALID_ASSESSMENT_STATUSES = {
    "pending",
    "in_progress",
    "completed",
}

KNOWN_ASSESSMENT_TYPES = {
    "assignment",
    "quiz",
    "lab",
    "midsem",
    "endsem",
    "exam",
    "project",
}

_STATUS_ALIASES = {
    "inprogress": "in_progress",
    "not_started": "pending",
    "open": "pending",
    "done": "completed",
    "complete": "completed",
}

_TYPE_ALIASES = {
    "mid_sem": "midsem",
    "midterm": "midsem",
    "mid_term": "midsem",
    "end_sem": "endsem",
    "final": "endsem",
    "final_exam": "endsem",
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")


@dataclass(frozen=True)
class AssessmentTopicReviewItem:
    assessment_legacy_key: str
    assessment_target_id: str
    course_target_id: str
    position: int
    raw_label: str
    reason: str = "unresolved_legacy_label"


@dataclass(frozen=True)
class AssessmentTopicImportResult:
    source_path: str
    source_hash: str
    assessments: ImportTally
    assessment_topics: ImportTally
    deferred_course_credits: int
    review_items: Tuple[AssessmentTopicReviewItem, ...]
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        tallies = (self.assessments, self.assessment_topics)
        return sum(item.created + item.updated for item in tallies)

    @property
    def review_required_topics(self) -> int:
        return len(self.review_items)

    @property
    def unresolved_topics(self) -> int:
        return self.review_required_topics


# Short compatibility name for callers that describe this as the assessment
# importer rather than the assessment/topic importer.
AssessmentImportResult = AssessmentTopicImportResult


@dataclass(frozen=True)
class _PreparedAssessmentTopic:
    legacy_key: str
    target_id: str
    raw_label: str
    normalized_label: str
    position: int


@dataclass(frozen=True)
class _PreparedAssessment:
    legacy_key: str
    raw_legacy_id: str
    target_id: str
    legacy_course_id: str
    assessment_type: str
    title: str
    due_on: Optional[str]
    due_time: Optional[str]
    status: str
    weight_bps: Optional[int]
    max_points_milli: Optional[int]
    earned_points_milli: Optional[int]
    description: str
    created_at: str
    updated_at: str
    topics: Tuple[_PreparedAssessmentTopic, ...]
    raw: Mapping[str, Any]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _required_identifier(value: Any, field: str, position: int) -> str:
    if isinstance(value, (dict, list, bool)):
        raise LegacyImportDataError(
            "assessment at index {} has invalid {}".format(position, field)
        )
    text = _clean_text(value)
    if not text:
        raise LegacyImportDataError(
            "assessment at index {} has no {}".format(position, field)
        )
    return text


def _required_string(value: Any, field: str, legacy_key: str) -> str:
    if not isinstance(value, str):
        raise LegacyImportDataError(
            "assessment {} field '{}' must be a string".format(
                legacy_key,
                field,
            )
        )
    text = _clean_text(value)
    if not text:
        raise LegacyImportDataError(
            "assessment {} has no {}".format(legacy_key, field)
        )
    return text


def _description(value: Any, legacy_key: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LegacyImportDataError(
            "assessment {} field 'description' must be a string".format(
                legacy_key
            )
        )
    return value


def _timestamp(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if not isinstance(value, str):
        return fallback
    return value.strip() or fallback


def _normalized_token(value: Any) -> str:
    text = _clean_text(value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _assessment_status(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> str:
    raw = _clean_text(value)
    if not raw:
        return "pending"

    normalized = _normalized_token(raw)
    canonical = _STATUS_ALIASES.get(normalized, normalized)
    if canonical not in VALID_ASSESSMENT_STATUSES:
        issues.append(
            ImportIssue(
                severity="warning",
                code="unknown_assessment_status",
                message=(
                    "Assessment status {!r} is unsupported; imported as "
                    "'pending' while the raw record remains in the ledger."
                ).format(raw),
                legacy_key=legacy_key,
            )
        )
        return "pending"

    if canonical != normalized:
        issues.append(
            ImportIssue(
                severity="warning",
                code="normalized_assessment_status",
                message="Assessment status {!r} imported as {!r}.".format(
                    raw,
                    canonical,
                ),
                legacy_key=legacy_key,
            )
        )
    return canonical


def _assessment_type(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> str:
    raw = _clean_text(value)
    if not raw:
        raise LegacyImportDataError(
            "assessment {} has no type".format(legacy_key)
        )

    normalized = _normalized_token(raw)
    canonical = _TYPE_ALIASES.get(normalized, normalized)
    if not canonical:
        raise LegacyImportDataError(
            "assessment {} has no usable type".format(legacy_key)
        )
    if canonical != normalized:
        issues.append(
            ImportIssue(
                severity="warning",
                code="normalized_assessment_type",
                message="Assessment type {!r} imported as {!r}.".format(
                    raw,
                    canonical,
                ),
                legacy_key=legacy_key,
            )
        )
    elif canonical not in KNOWN_ASSESSMENT_TYPES:
        issues.append(
            ImportIssue(
                severity="warning",
                code="unknown_assessment_type",
                message=(
                    "Unknown assessment type {!r} was preserved as {!r}."
                ).format(raw, canonical),
                legacy_key=legacy_key,
            )
        )
    return canonical


def _due_date(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        if not _DATE_RE.fullmatch(text):
            raise ValueError
        date.fromisoformat(text)
    except ValueError:
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_assessment_due_date",
                message=(
                    "Due date {!r} is not YYYY-MM-DD; imported as NULL while "
                    "the raw value remains in the ledger."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
        return None
    return text


def _due_time(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not _TIME_RE.fullmatch(text):
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_assessment_due_time",
                message=(
                    "Due time {!r} is not HH:MM or HH:MM:SS; imported as "
                    "NULL while the raw value remains in the ledger."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
        return None
    return text


def _values_equivalent(left: Any, right: Any) -> bool:
    if left == right:
        return True
    try:
        return Decimal(str(left).strip()) == Decimal(str(right).strip())
    except (InvalidOperation, ValueError):
        return False


def _alias_value(
    raw: Mapping[str, Any],
    primary: str,
    legacy: str,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Any:
    primary_value = raw.get(primary)
    legacy_value = raw.get(legacy)
    primary_present = primary_value is not None and primary_value != ""
    legacy_present = legacy_value is not None and legacy_value != ""

    if (
        primary_present
        and legacy_present
        and not _values_equivalent(primary_value, legacy_value)
    ):
        raise LegacyImportDataError(
            "assessment {} has conflicting '{}' and '{}' values".format(
                legacy_key,
                primary,
                legacy,
            )
        )

    if primary_present:
        return primary_value
    if legacy_present:
        issues.append(
            ImportIssue(
                severity="info",
                code="legacy_assessment_field_alias",
                message="Legacy field '{}' was read as '{}'.".format(
                    legacy,
                    primary,
                ),
                legacy_key=legacy_key,
            )
        )
        return legacy_value
    return None


def _scaled_number(
    value: Any,
    *,
    scale: int,
    field_name: str,
    issue_prefix: str,
    issues: List[ImportIssue],
    legacy_key: str,
    maximum: Optional[Decimal] = None,
) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        number = Decimal("NaN")

    if not number.is_finite():
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_{}".format(issue_prefix),
                message=(
                    "{} {!r} is not a finite number; imported as NULL."
                ).format(field_name, value),
                legacy_key=legacy_key,
            )
        )
        return None

    if number < 0 or (maximum is not None and number > maximum):
        range_text = "non-negative"
        if maximum is not None:
            range_text = "between 0 and {}".format(maximum)
        issues.append(
            ImportIssue(
                severity="warning",
                code="out_of_range_{}".format(issue_prefix),
                message=(
                    "{} {!r} is not {}; imported as NULL."
                ).format(field_name, value, range_text),
                legacy_key=legacy_key,
            )
        )
        return None

    scaled = number * Decimal(scale)
    rounded = scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if rounded != scaled:
        issues.append(
            ImportIssue(
                severity="warning",
                code="rounded_{}".format(issue_prefix),
                message=(
                    "{} {!r} required half-up rounding to the schema's "
                    "integer storage unit."
                ).format(field_name, value),
                legacy_key=legacy_key,
            )
        )
    return int(rounded)


def _topic_key(assessment_key: str, normalized_label: str) -> str:
    return "{}/topic:label:{}".format(assessment_key, normalized_label)


def _prepare_assessments(
    snapshot: LegacySourceSnapshot,
    data: Mapping[str, Any],
    imported_at: str,
    issues: List[ImportIssue],
) -> Tuple[Tuple[_PreparedAssessment, ...], int]:
    raw_assessments = data.get("assessments", [])
    if not isinstance(raw_assessments, list):
        raise LegacyImportDataError(
            "assessments.json field 'assessments' must be an array"
        )

    prepared: List[_PreparedAssessment] = []
    seen_assessment_keys = set()
    deferred_course_credits = 0

    for position, raw_assessment in enumerate(raw_assessments):
        if not isinstance(raw_assessment, dict):
            raise LegacyImportDataError(
                "assessment at index {} must be a JSON object".format(position)
            )

        raw_id = _required_identifier(raw_assessment.get("id"), "id", position)
        legacy_key = "assessment:id:{}".format(raw_id)
        if legacy_key in seen_assessment_keys:
            raise LegacyImportDataError(
                "duplicate legacy assessment identity: {}".format(legacy_key)
            )
        seen_assessment_keys.add(legacy_key)

        legacy_course_id = _required_identifier(
            raw_assessment.get("course_id"),
            "course_id",
            position,
        )
        title = _required_string(
            raw_assessment.get("title"),
            "title",
            legacy_key,
        )
        raw_assessment_type = _alias_value(
            raw_assessment,
            "type",
            "assessment_type",
            issues=issues,
            legacy_key=legacy_key,
        )
        assessment_type = _assessment_type(
            raw_assessment_type,
            issues=issues,
            legacy_key=legacy_key,
        )
        status = _assessment_status(
            raw_assessment.get("status"),
            issues=issues,
            legacy_key=legacy_key,
        )

        raw_due_on = _alias_value(
            raw_assessment,
            "due_date",
            "due_on",
            issues=issues,
            legacy_key=legacy_key,
        )
        due_on = _due_date(
            raw_due_on,
            issues=issues,
            legacy_key=legacy_key,
        )
        due_time = _due_time(
            raw_assessment.get("due_time"),
            issues=issues,
            legacy_key=legacy_key,
        )

        raw_weight = _alias_value(
            raw_assessment,
            "weightage_percent",
            "weight",
            issues=issues,
            legacy_key=legacy_key,
        )
        raw_max_points = _alias_value(
            raw_assessment,
            "total_marks",
            "max_score",
            issues=issues,
            legacy_key=legacy_key,
        )
        raw_earned_points = _alias_value(
            raw_assessment,
            "obtained_marks",
            "score",
            issues=issues,
            legacy_key=legacy_key,
        )

        weight_bps = _scaled_number(
            raw_weight,
            scale=100,
            field_name="Assessment weightage percent",
            issue_prefix="assessment_weightage",
            issues=issues,
            legacy_key=legacy_key,
            maximum=Decimal("100"),
        )
        max_points_milli = _scaled_number(
            raw_max_points,
            scale=1000,
            field_name="Assessment total marks",
            issue_prefix="assessment_total_marks",
            issues=issues,
            legacy_key=legacy_key,
        )
        earned_points_milli = _scaled_number(
            raw_earned_points,
            scale=1000,
            field_name="Assessment obtained marks",
            issue_prefix="assessment_obtained_marks",
            issues=issues,
            legacy_key=legacy_key,
        )
        if (
            earned_points_milli is not None
            and max_points_milli is not None
            and earned_points_milli > max_points_milli
        ):
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="assessment_score_exceeds_total",
                    message=(
                        "Obtained marks exceed total marks; obtained marks were "
                        "imported as NULL while the raw values remain in the ledger."
                    ),
                    legacy_key=legacy_key,
                )
            )
            earned_points_milli = None

        if (
            raw_assessment.get("course_credits") is not None
            and raw_assessment.get("course_credits") != ""
        ):
            deferred_course_credits += 1
            issues.append(
                ImportIssue(
                    severity="info",
                    code="assessment_course_credits_deferred",
                    message=(
                        "Assessment-level course_credits remains in the source/"
                        "ledger for later credit-authority reconciliation."
                    ),
                    legacy_key=legacy_key,
                )
            )

        raw_topics = raw_assessment.get("topics", [])
        if raw_topics is None:
            raw_topics = []
        if not isinstance(raw_topics, list):
            raise LegacyImportDataError(
                "topics for assessment {} must be an array".format(legacy_key)
            )

        prepared_topics: List[_PreparedAssessmentTopic] = []
        seen_topic_labels = set()
        for topic_position, raw_label in enumerate(raw_topics):
            if not isinstance(raw_label, str):
                raise LegacyImportDataError(
                    "topic {} for assessment {} must be a string".format(
                        topic_position,
                        legacy_key,
                    )
                )
            normalized_label = _clean_text(raw_label).casefold()
            if not normalized_label:
                raise LegacyImportDataError(
                    "topic {} for assessment {} is blank".format(
                        topic_position,
                        legacy_key,
                    )
                )
            if normalized_label in seen_topic_labels:
                raise LegacyImportDataError(
                    "duplicate raw topic label in assessment {}: {!r}".format(
                        legacy_key,
                        raw_label,
                    )
                )
            seen_topic_labels.add(normalized_label)

            topic_legacy_key = _topic_key(legacy_key, normalized_label)
            prepared_topics.append(
                _PreparedAssessmentTopic(
                    legacy_key=topic_legacy_key,
                    target_id=stable_target_id(
                        snapshot.canonical_path,
                        "assessment_topic",
                        topic_legacy_key,
                    ),
                    raw_label=raw_label,
                    normalized_label=normalized_label,
                    position=topic_position,
                )
            )
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="assessment_topic_review_required",
                    message=(
                        "Raw assessment topic label was preserved without an "
                        "automatic topic link and requires review."
                    ),
                    legacy_key=topic_legacy_key,
                )
            )

        created_at = _timestamp(raw_assessment.get("created_at"), imported_at)
        updated_at = _timestamp(raw_assessment.get("updated_at"), created_at)
        prepared.append(
            _PreparedAssessment(
                legacy_key=legacy_key,
                raw_legacy_id=raw_id,
                target_id=stable_target_id(
                    snapshot.canonical_path,
                    "assessment",
                    legacy_key,
                ),
                legacy_course_id=legacy_course_id,
                assessment_type=assessment_type,
                title=title,
                due_on=due_on,
                due_time=due_time,
                status=status,
                weight_bps=weight_bps,
                max_points_milli=max_points_milli,
                earned_points_milli=earned_points_milli,
                description=_description(
                    raw_assessment.get("description"),
                    legacy_key,
                ),
                created_at=created_at,
                updated_at=updated_at,
                topics=tuple(prepared_topics),
                raw=dict(raw_assessment),
            )
        )

    return tuple(prepared), deferred_course_credits


def _course_candidates(
    connection: sqlite3.Connection,
    legacy_key: str,
) -> Tuple[str, ...]:
    rows = connection.execute(
        "SELECT mi.legacy_key, mi.target_id "
        "FROM migration_imports AS mi "
        "JOIN courses AS c ON c.id = mi.target_id "
        "WHERE mi.source_path = 'data/courses.json' "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'courses' "
        "AND c.deleted_at IS NULL"
    ).fetchall()
    folded_key = legacy_key.casefold()
    return tuple(
        sorted(
            {
                str(row[1])
                for row in rows
                if str(row[0]).casefold() == folded_key
            }
        )
    )


def _resolve_course_target(
    connection: sqlite3.Connection,
    legacy_course_id: str,
) -> str:
    lookup_keys = (
        "course:id:{}".format(legacy_course_id),
        "course:code:{}".format(legacy_course_id.casefold()),
    )
    for lookup_key in lookup_keys:
        candidates = _course_candidates(connection, lookup_key)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise LegacyImportDataError(
                "ambiguous imported course mapping for legacy course_id {!r}"
                .format(legacy_course_id)
            )

    raise LegacyImportDataError(
        "unresolved legacy course_id {!r}; import courses/topics first"
        .format(legacy_course_id)
    )


def _ledger_disposition(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot: LegacySourceSnapshot,
    *,
    legacy_key: str,
    target_table: str,
    target_id: str,
    existence_sql: str,
    existence_params: Tuple[Any, ...],
) -> str:
    identity = build_import_identity(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        source_type=snapshot.source_type,
        source_version=snapshot.source_version,
        legacy_key=legacy_key,
        target_table=target_table,
    )
    existing = ledger.find(identity)
    if existing is not None:
        if existing.target_id != target_id:
            ledger.record_snapshot_import(
                snapshot,
                legacy_key=legacy_key,
                target_table=target_table,
                target_id=target_id,
            )
        target_exists = connection.execute(
            existence_sql,
            existence_params,
        ).fetchone()
        if target_exists is None:
            raise LegacyImportError(
                "migration ledger points to a missing {} target: {}".format(
                    target_table,
                    target_id,
                )
            )
        return "matched"

    target_exists = connection.execute(
        existence_sql,
        existence_params,
    ).fetchone()
    return "updated" if target_exists is not None else "created"


def import_assessments_and_topics(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> AssessmentTopicImportResult:
    """Import one verified ``assessments.json`` snapshot transactionally."""
    ensure_tables(connection, REQUIRED_TABLES)
    data = load_verified_json(snapshot, expected_kind="object")

    if snapshot.canonical_path != "data/assessments.json":
        raise LegacyImportDataError(
            "assessments/topics importer requires data/assessments.json"
        )
    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")

    issues: List[ImportIssue] = []
    prepared, deferred_course_credits = _prepare_assessments(
        snapshot,
        data,
        imported_at,
        issues,
    )

    version = data.get("version")
    if version not in (None, 1, 2, "1", "2"):
        issues.append(
            ImportIssue(
                severity="warning",
                code="unexpected_assessments_version",
                message=(
                    "assessments.json version {!r} was imported without "
                    "rewriting the source."
                ).format(version),
            )
        )

    counters: Dict[str, Dict[str, int]] = {
        "assessments": {},
        "assessment_topics": {},
    }
    review_items: List[AssessmentTopicReviewItem] = []
    ledger = MigrationImportLedger(connection)
    topic_source = "legacy_json:{}".format(snapshot.canonical_path)

    with transaction(connection, immediate=True):
        for assessment in prepared:
            course_target_id = _resolve_course_target(
                connection,
                assessment.legacy_course_id,
            )
            disposition = _ledger_disposition(
                connection,
                ledger,
                snapshot,
                legacy_key=assessment.legacy_key,
                target_table="assessments",
                target_id=assessment.target_id,
                existence_sql="SELECT 1 FROM assessments WHERE id = ?",
                existence_params=(assessment.target_id,),
            )
            if disposition != "matched":
                connection.execute(
                    "INSERT INTO assessments "
                    "(id, course_id, assessment_type, title, due_on, due_time, "
                    "status, weight_bps, max_points_milli, earned_points_milli, "
                    "description, created_at, updated_at, deleted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "course_id = excluded.course_id, "
                    "assessment_type = excluded.assessment_type, "
                    "title = excluded.title, due_on = excluded.due_on, "
                    "due_time = excluded.due_time, status = excluded.status, "
                    "weight_bps = excluded.weight_bps, "
                    "max_points_milli = excluded.max_points_milli, "
                    "earned_points_milli = excluded.earned_points_milli, "
                    "description = excluded.description, "
                    "updated_at = excluded.updated_at, deleted_at = NULL",
                    (
                        assessment.target_id,
                        course_target_id,
                        assessment.assessment_type,
                        assessment.title,
                        assessment.due_on,
                        assessment.due_time,
                        assessment.status,
                        assessment.weight_bps,
                        assessment.max_points_milli,
                        assessment.earned_points_milli,
                        assessment.description,
                        assessment.created_at,
                        assessment.updated_at,
                    ),
                )
                ledger.record_snapshot_import(
                    snapshot,
                    legacy_key=assessment.legacy_key,
                    target_table="assessments",
                    target_id=assessment.target_id,
                    details={
                        "kind": "assessment",
                        "legacy_id": assessment.raw_legacy_id,
                        "legacy_course_id": assessment.legacy_course_id,
                        "target_course_id": course_target_id,
                        "raw": dict(assessment.raw),
                    },
                    imported_at=imported_at,
                )
            add_tally(counters["assessments"], disposition)

            for topic in assessment.topics:
                disposition = _ledger_disposition(
                    connection,
                    ledger,
                    snapshot,
                    legacy_key=topic.legacy_key,
                    target_table="assessment_topics",
                    target_id=topic.target_id,
                    existence_sql="SELECT 1 FROM assessment_topics WHERE id = ?",
                    existence_params=(topic.target_id,),
                )
                if disposition != "matched":
                    connection.execute(
                        "INSERT INTO assessment_topics "
                        "(id, assessment_id, topic_id, raw_label, source, "
                        "confidence, created_at) "
                        "VALUES (?, ?, NULL, ?, ?, NULL, ?) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "assessment_id = excluded.assessment_id, "
                        "topic_id = NULL, raw_label = excluded.raw_label, "
                        "source = excluded.source, confidence = NULL",
                        (
                            topic.target_id,
                            assessment.target_id,
                            topic.raw_label,
                            topic_source,
                            imported_at,
                        ),
                    )
                    ledger.record_snapshot_import(
                        snapshot,
                        legacy_key=topic.legacy_key,
                        target_table="assessment_topics",
                        target_id=topic.target_id,
                        details={
                            "kind": "assessment_topic_raw_label",
                            "assessment_legacy_key": assessment.legacy_key,
                            "position": topic.position,
                            "raw_label": topic.raw_label,
                            "normalized_label": topic.normalized_label,
                            "resolution_state": "review_required",
                        },
                        imported_at=imported_at,
                    )
                add_tally(counters["assessment_topics"], disposition)
                review_items.append(
                    AssessmentTopicReviewItem(
                        assessment_legacy_key=assessment.legacy_key,
                        assessment_target_id=assessment.target_id,
                        course_target_id=course_target_id,
                        position=topic.position,
                        raw_label=topic.raw_label,
                    )
                )

        # TOCTOU guard: a source change during the transaction aborts everything.
        source_sha256(snapshot)

    return AssessmentTopicImportResult(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        assessments=freeze_tally(counters["assessments"]),
        assessment_topics=freeze_tally(counters["assessment_topics"]),
        deferred_course_credits=deferred_course_credits,
        review_items=tuple(review_items),
        issues=tuple(issues),
    )


def import_assessments(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> AssessmentTopicImportResult:
    """Compatibility alias for :func:`import_assessments_and_topics`."""
    return import_assessments_and_topics(
        connection,
        snapshot,
        imported_at=imported_at,
    )


def _markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def render_assessment_topic_review_markdown(
    result: AssessmentTopicImportResult,
) -> str:
    """Render a portable review report without writing it to disk."""
    lines = [
        "# Assessment Topic Review",
        "",
        "- Source: `{}`".format(_markdown_cell(result.source_path)),
        "- Source SHA-256: `{}`".format(result.source_hash),
        "- Review-required labels: {}".format(result.review_required_topics),
        "",
    ]
    if not result.review_items:
        lines.append("No assessment topic labels require review.")
        return "\n".join(lines) + "\n"

    lines.extend(
        (
            "| Assessment | Position | Raw label | State |",
            "|---|---:|---|---|",
        )
    )
    for item in result.review_items:
        lines.append(
            "| {} | {} | {} | review required |".format(
                _markdown_cell(item.assessment_legacy_key),
                item.position + 1,
                _markdown_cell(item.raw_label),
            )
        )
    return "\n".join(lines) + "\n"


__all__ = (
    "AssessmentImportResult",
    "AssessmentTopicImportResult",
    "AssessmentTopicReviewItem",
    "import_assessments",
    "import_assessments_and_topics",
    "render_assessment_topic_review_markdown",
)
