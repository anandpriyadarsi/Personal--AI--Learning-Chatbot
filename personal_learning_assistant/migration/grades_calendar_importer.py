"""Idempotent Phase 3 importer for grades and academic-calendar deadlines.

This module is a shadow migration adapter only.  It imports an optional,
verified ``semester_grade_config.json`` snapshot and projects already-imported
assessment deadlines into ``academic_events``.  Legacy JSON remains the source
of truth until the later structured-storage cutover is explicitly approved.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.repositories.sqlite.connection import transaction

from .import_ledger import MigrationImportLedger, build_import_identity
from .legacy_json_import import (
    ImportIssue,
    ImportTally,
    LegacyImportDataError,
    LegacyImportError,
    LegacySourceChangedError,
    add_tally,
    ensure_tables,
    freeze_tally,
    load_verified_json,
    source_sha256,
    stable_target_id,
)
from .legacy_source_scanner import (
    LegacySourceSnapshot,
    STATUS_MISSING,
    STATUS_VALID_JSON,
)


GRADE_SOURCE_PATH = "data/semester_grade_config.json"
ASSESSMENT_SOURCE_PATH = "data/assessments.json"
COURSE_SOURCE_PATH = "data/courses.json"

REQUIRED_TABLES = (
    "migration_imports",
    "semesters",
    "courses",
    "semester_courses",
    "assessments",
    "grade_scales",
    "grade_bands",
    "semester_grade_settings",
    "manual_grade_entries",
    "semester_results",
    "academic_events",
)


@dataclass(frozen=True)
class GradeCalendarReviewItem:
    source_path: str
    legacy_key: str
    entity_kind: str
    raw_reference: str
    reason: str


@dataclass(frozen=True)
class GradeCalendarImportResult:
    sources_scanned: int
    imported_sources: Tuple[str, ...]
    optional_sources_absent: Tuple[str, ...]
    grade_scales: ImportTally
    grade_bands: ImportTally
    semester_grade_settings: ImportTally
    semester_course_credits: ImportTally
    manual_grade_entries: ImportTally
    semester_results: ImportTally
    academic_events: ImportTally
    assessments_without_due_date: int
    review_items: Tuple[GradeCalendarReviewItem, ...]
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        tallies = (
            self.grade_scales,
            self.grade_bands,
            self.semester_grade_settings,
            self.semester_course_credits,
            self.manual_grade_entries,
            self.semester_results,
            self.academic_events,
        )
        return sum(item.created + item.updated for item in tallies)

    @property
    def review_required_items(self) -> int:
        return len(self.review_items)


# Compatibility aliases for callers using shorter feature names.
GradesCalendarImportResult = GradeCalendarImportResult
GradeAcademicCalendarImportResult = GradeCalendarImportResult


@dataclass(frozen=True)
class _PreparedGradeBand:
    legacy_key: str
    target_id: str
    minimum_bps: int
    letter_grade: str
    grade_point_milli: int
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedGradeScale:
    legacy_key: str
    target_id: str
    fingerprint: str
    name: str
    source: str
    verified: int
    active_from: Optional[str]
    active_to: Optional[str]
    created_at: str
    updated_at: str
    bands: Tuple[_PreparedGradeBand, ...]
    raw: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class _PreparedCourseGrade:
    legacy_key: str
    raw_course_id: str
    credits_milli: Optional[int]
    score_bps: Optional[int]
    letter_grade: Optional[str]
    grade_point_milli: Optional[int]
    entry_kind: str
    note: str
    recorded_at: str
    manual_entry_key: Optional[str]
    manual_entry_id: Optional[str]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedSemesterResult:
    legacy_key: str
    earned_credits_milli: int
    earned_grade_points_milli: int
    sgpa_milli: int
    verified: int
    source: str
    recorded_at: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedGradeConfig:
    semester_name: str
    target_sgpa_milli: Optional[int]
    scale: _PreparedGradeScale
    courses: Tuple[_PreparedCourseGrade, ...]
    result: Optional[_PreparedSemesterResult]


@dataclass(frozen=True)
class _PreparedDeadline:
    legacy_key: str
    target_id: str
    assessment_id: str
    course_id: str
    semester_id: Optional[str]
    title: str
    starts_at: Optional[str]
    all_day: int
    status: str
    created_at: str
    updated_at: str


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _clean_text(value).casefold()).strip("_")


def _timestamp(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _date_value(
    value: Any,
    *,
    field: str,
    legacy_key: str,
    issues: List[ImportIssue],
) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_{}".format(field),
                message=(
                    "Grade configuration field '{}' value {!r} is not an ISO "
                    "date; imported as NULL while raw data remains in the ledger."
                ).format(field, value),
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
        return _clean_text(left).casefold() == _clean_text(right).casefold()


def _alias_value(
    raw: Mapping[str, Any],
    fields: Sequence[str],
    *,
    legacy_key: str,
) -> Any:
    present = [
        (field, raw.get(field))
        for field in fields
        if raw.get(field) is not None and raw.get(field) != ""
    ]
    if not present:
        return None
    first_field, first_value = present[0]
    for field, value in present[1:]:
        if not _values_equivalent(first_value, value):
            raise LegacyImportDataError(
                "grade record {} has conflicting '{}' and '{}' values".format(
                    legacy_key,
                    first_field,
                    field,
                )
            )
    return first_value


def _scaled_number(
    value: Any,
    *,
    scale: int,
    field: str,
    legacy_key: str,
    issues: List[ImportIssue],
    minimum: Decimal = Decimal("0"),
    maximum: Optional[Decimal] = None,
    required: bool = False,
) -> Optional[int]:
    if value is None or value == "":
        if required:
            raise LegacyImportDataError(
                "grade record {} requires field '{}'".format(legacy_key, field)
            )
        return None
    if isinstance(value, bool):
        number = Decimal("NaN")
    else:
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            number = Decimal("NaN")
    valid = number.is_finite() and number >= minimum
    if maximum is not None:
        valid = valid and number <= maximum
    if not valid:
        range_text = ">= {}".format(minimum)
        if maximum is not None:
            range_text = "between {} and {}".format(minimum, maximum)
        if required:
            raise LegacyImportDataError(
                "grade record {} field '{}' must be {}".format(
                    legacy_key,
                    field,
                    range_text,
                )
            )
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_{}".format(field),
                message=(
                    "Grade field '{}' value {!r} is not {}; imported as NULL "
                    "while the raw value remains in the ledger."
                ).format(field, value, range_text),
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
                code="rounded_{}".format(field),
                message=(
                    "Grade field '{}' value {!r} required half-up rounding "
                    "to the schema's integer unit."
                ).format(field, value),
                legacy_key=legacy_key,
            )
        )
    return int(rounded)


def _boolean_flag(
    value: Any,
    *,
    field: str,
    legacy_key: str,
    issues: List[ImportIssue],
) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    token = _normalized_token(value)
    if token in {"true", "yes", "verified", "official", "1"}:
        return 1
    if token in {"false", "no", "unverified", "planning", "0"}:
        return 0
    issues.append(
        ImportIssue(
            severity="warning",
            code="invalid_{}".format(field),
            message=(
                "Boolean grade field '{}' value {!r} was imported as false."
            ).format(field, value),
            legacy_key=legacy_key,
        )
    )
    return 0


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _review(
    review_items: List[GradeCalendarReviewItem],
    *,
    source_path: str,
    legacy_key: str,
    entity_kind: str,
    raw_reference: Any,
    reason: str,
) -> None:
    review_items.append(
        GradeCalendarReviewItem(
            source_path=source_path,
            legacy_key=legacy_key,
            entity_kind=entity_kind,
            raw_reference=_clean_text(raw_reference),
            reason=reason,
        )
    )


def _prepare_grade_scale(
    data: Mapping[str, Any],
    imported_at: str,
    issues: List[ImportIssue],
) -> _PreparedGradeScale:
    raw_scale = data.get("grade_scale")
    if not isinstance(raw_scale, list) or not raw_scale:
        raise LegacyImportDataError(
            "semester_grade_config.json field 'grade_scale' must be a non-empty array"
        )

    normalized_bands: List[Dict[str, Any]] = []
    raw_bands: List[Mapping[str, Any]] = []
    seen_thresholds = set()
    for position, raw_band in enumerate(raw_scale):
        legacy_key = "grade_scale/band:index:{}".format(position)
        if not isinstance(raw_band, dict):
            raise LegacyImportDataError(
                "grade band at index {} must be an object".format(position)
            )
        letter = _clean_text(
            _alias_value(
                raw_band,
                ("letter", "letter_grade", "grade"),
                legacy_key=legacy_key,
            )
        )
        if not letter:
            raise LegacyImportDataError(
                "grade band {} requires a letter grade".format(legacy_key)
            )
        minimum_bps = _scaled_number(
            _alias_value(
                raw_band,
                ("min_score", "minimum_score", "minimum_percent"),
                legacy_key=legacy_key,
            ),
            scale=100,
            field="minimum_score",
            legacy_key=legacy_key,
            issues=issues,
            maximum=Decimal("100"),
            required=True,
        )
        grade_point_milli = _scaled_number(
            _alias_value(
                raw_band,
                ("grade_point", "point", "gp"),
                legacy_key=legacy_key,
            ),
            scale=1000,
            field="grade_point",
            legacy_key=legacy_key,
            issues=issues,
            maximum=Decimal("10"),
            required=True,
        )
        assert minimum_bps is not None
        assert grade_point_milli is not None
        if minimum_bps in seen_thresholds:
            raise LegacyImportDataError(
                "grade scale has duplicate minimum threshold {}".format(minimum_bps)
            )
        seen_thresholds.add(minimum_bps)
        normalized_bands.append(
            {
                "letter_grade": letter,
                "minimum_bps": minimum_bps,
                "grade_point_milli": grade_point_milli,
            }
        )
        raw_bands.append(dict(raw_band))

    verified = _boolean_flag(
        _alias_value(
            data,
            ("grade_scale_verified", "scale_verified", "verified"),
            legacy_key="grade_scale",
        ),
        field="grade_scale_verified",
        legacy_key="grade_scale",
        issues=issues,
    )
    source = _clean_text(
        _alias_value(
            data,
            ("grade_scale_source", "scale_source"),
            legacy_key="grade_scale",
        )
    ) or "legacy_json:{}".format(GRADE_SOURCE_PATH)
    active_from = _date_value(
        data.get("grade_scale_active_from"),
        field="grade_scale_active_from",
        legacy_key="grade_scale",
        issues=issues,
    )
    active_to = _date_value(
        data.get("grade_scale_active_to"),
        field="grade_scale_active_to",
        legacy_key="grade_scale",
        issues=issues,
    )
    if active_from and active_to and active_to < active_from:
        raise LegacyImportDataError("grade-scale active_to is before active_from")

    fingerprint = _fingerprint(
        {
            "bands": normalized_bands,
            "source": source,
            "verified": verified,
            "active_from": active_from,
            "active_to": active_to,
        }
    )
    scale_key = "grade_scale:fingerprint:{}".format(fingerprint)
    scale_id = stable_target_id(GRADE_SOURCE_PATH, "grade_scale", scale_key)
    base_name = _clean_text(data.get("grade_scale_name")) or "Legacy Planning Grade Scale"
    scale_name = "{} [{}]".format(base_name, fingerprint[:12])
    created_at = _timestamp(data.get("created_at"), imported_at)
    updated_at = _timestamp(data.get("updated_at"), created_at)

    bands = tuple(
        _PreparedGradeBand(
            legacy_key="{}/band:index:{}".format(scale_key, position),
            target_id=stable_target_id(
                GRADE_SOURCE_PATH,
                "grade_band",
                "{}/band:index:{}".format(scale_key, position),
            ),
            minimum_bps=int(item["minimum_bps"]),
            letter_grade=str(item["letter_grade"]),
            grade_point_milli=int(item["grade_point_milli"]),
            raw=raw_bands[position],
        )
        for position, item in enumerate(normalized_bands)
    )

    if not verified:
        issues.append(
            ImportIssue(
                severity="info",
                code="unverified_planning_grade_scale",
                message=(
                    "The imported grade scale remains an unverified planning "
                    "configuration, not official institutional policy."
                ),
                legacy_key=scale_key,
            )
        )

    return _PreparedGradeScale(
        legacy_key=scale_key,
        target_id=scale_id,
        fingerprint=fingerprint,
        name=scale_name,
        source=source,
        verified=verified,
        active_from=active_from,
        active_to=active_to,
        created_at=created_at,
        updated_at=updated_at,
        bands=bands,
        raw=tuple(raw_bands),
    )


def _prepare_course_grades(
    data: Mapping[str, Any],
    semester_name: str,
    imported_at: str,
    issues: List[ImportIssue],
    review_items: List[GradeCalendarReviewItem],
) -> Tuple[_PreparedCourseGrade, ...]:
    raw_courses = data.get("courses", [])
    if raw_courses is None:
        raw_courses = []
    if not isinstance(raw_courses, list):
        raise LegacyImportDataError(
            "semester_grade_config.json field 'courses' must be an array"
        )

    prepared: List[_PreparedCourseGrade] = []
    seen = set()
    for position, raw_course in enumerate(raw_courses):
        if not isinstance(raw_course, dict):
            raise LegacyImportDataError(
                "grade course at index {} must be an object".format(position)
            )
        raw_course_id = _clean_text(
            _alias_value(
                raw_course,
                ("course_id", "course_code", "code"),
                legacy_key="course:index:{}".format(position),
            )
        )
        legacy_key = "course:{}".format(raw_course_id or "index:{}".format(position))
        if not raw_course_id:
            raise LegacyImportDataError(
                "grade course at index {} has no course identifier".format(position)
            )
        folded = raw_course_id.casefold()
        if folded in seen:
            raise LegacyImportDataError(
                "duplicate grade course reference {!r}".format(raw_course_id)
            )
        seen.add(folded)

        credits_raw = _alias_value(
            raw_course,
            ("credits", "credit", "course_credits"),
            legacy_key=legacy_key,
        )
        credits_milli = _scaled_number(
            credits_raw,
            scale=1000,
            field="course_credits",
            legacy_key=legacy_key,
            issues=issues,
        )
        if credits_raw not in (None, "") and credits_milli is None:
            _review(
                review_items,
                source_path=GRADE_SOURCE_PATH,
                legacy_key=legacy_key,
                entity_kind="semester_course_credit",
                raw_reference=raw_course_id,
                reason="invalid_course_credits",
            )

        score_raw = _alias_value(
            raw_course,
            ("manual_score", "score_percent", "score"),
            legacy_key=legacy_key,
        )
        score_bps = _scaled_number(
            score_raw,
            scale=100,
            field="manual_score",
            legacy_key=legacy_key,
            issues=issues,
            maximum=Decimal("100"),
        )
        grade_point_raw = _alias_value(
            raw_course,
            ("manual_grade_point", "grade_point"),
            legacy_key=legacy_key,
        )
        grade_point_milli = _scaled_number(
            grade_point_raw,
            scale=1000,
            field="manual_grade_point",
            legacy_key=legacy_key,
            issues=issues,
            maximum=Decimal("10"),
        )
        letter = _clean_text(
            _alias_value(
                raw_course,
                ("manual_letter_grade", "letter_grade"),
                legacy_key=legacy_key,
            )
        ) or None
        entry_kind = _normalized_token(raw_course.get("entry_kind")) or "legacy_manual_override"
        note = _clean_text(raw_course.get("note"))
        recorded_identity = _clean_text(
            raw_course.get("recorded_at") or raw_course.get("updated_at")
        )
        recorded_at = recorded_identity or imported_at

        has_manual_fields = any(
            value is not None for value in (score_bps, letter, grade_point_milli)
        )
        manual_key: Optional[str] = None
        manual_id: Optional[str] = None
        if has_manual_fields:
            manual_fingerprint = _fingerprint(
                {
                    "semester": _normalized_token(semester_name),
                    "course": raw_course_id.casefold(),
                    "score_bps": score_bps,
                    "letter_grade": letter,
                    "grade_point_milli": grade_point_milli,
                    "entry_kind": entry_kind,
                    "note": note,
                    # An import-time fallback must not become part of identity;
                    # otherwise an unchanged undated source would create a new
                    # manual-grade row on every run.
                    "recorded_at": recorded_identity or None,
                }
            )
            manual_key = "{}/manual_grade:fingerprint:{}".format(
                legacy_key,
                manual_fingerprint,
            )
            manual_id = stable_target_id(
                GRADE_SOURCE_PATH,
                "manual_grade_entry",
                manual_key,
            )
        elif score_raw not in (None, "") or grade_point_raw not in (None, ""):
            _review(
                review_items,
                source_path=GRADE_SOURCE_PATH,
                legacy_key=legacy_key,
                entity_kind="manual_grade_entry",
                raw_reference=raw_course_id,
                reason="manual_grade_values_invalid",
            )

        prepared.append(
            _PreparedCourseGrade(
                legacy_key=legacy_key,
                raw_course_id=raw_course_id,
                credits_milli=credits_milli,
                score_bps=score_bps,
                letter_grade=letter,
                grade_point_milli=grade_point_milli,
                entry_kind=entry_kind,
                note=note,
                recorded_at=recorded_at,
                manual_entry_key=manual_key,
                manual_entry_id=manual_id,
                raw=dict(raw_course),
            )
        )
    return tuple(prepared)


def _prepare_semester_result(
    data: Mapping[str, Any],
    semester_name: str,
    imported_at: str,
    issues: List[ImportIssue],
    review_items: List[GradeCalendarReviewItem],
) -> Optional[_PreparedSemesterResult]:
    single_present = "semester_result" in data and data.get("semester_result") is not None
    many_present = "semester_results" in data and data.get("semester_results") is not None
    if single_present and many_present:
        raise LegacyImportDataError(
            "grade config cannot contain both semester_result and semester_results"
        )
    if not single_present and not many_present:
        return None

    raw_value = data.get("semester_result") if single_present else data.get("semester_results")
    if isinstance(raw_value, dict):
        result_rows = [raw_value]
    elif isinstance(raw_value, list):
        result_rows = raw_value
    else:
        raise LegacyImportDataError("semester result must be an object or array")
    if not result_rows:
        return None
    if len(result_rows) != 1 or not isinstance(result_rows[0], dict):
        raise LegacyImportDataError(
            "one semester_grade_config.json can contain at most one semester result object"
        )

    raw = result_rows[0]
    legacy_key = "semester_result:{}".format(
        _normalized_token(semester_name) or "unspecified"
    )
    earned_credits = _scaled_number(
        _alias_value(
            raw,
            ("earned_credits", "credits_earned"),
            legacy_key=legacy_key,
        ),
        scale=1000,
        field="earned_credits",
        legacy_key=legacy_key,
        issues=issues,
    )
    earned_points = _scaled_number(
        _alias_value(
            raw,
            ("earned_grade_points", "total_grade_points"),
            legacy_key=legacy_key,
        ),
        scale=1000,
        field="earned_grade_points",
        legacy_key=legacy_key,
        issues=issues,
    )
    sgpa = _scaled_number(
        raw.get("sgpa"),
        scale=1000,
        field="sgpa",
        legacy_key=legacy_key,
        issues=issues,
        maximum=Decimal("10"),
    )
    if any(value is None for value in (earned_credits, earned_points, sgpa)):
        _review(
            review_items,
            source_path=GRADE_SOURCE_PATH,
            legacy_key=legacy_key,
            entity_kind="semester_result",
            raw_reference=semester_name,
            reason="incomplete_or_invalid_semester_result",
        )
        issues.append(
            ImportIssue(
                severity="warning",
                code="semester_result_deferred",
                message=(
                    "Semester result was not inserted because earned credits, "
                    "earned grade points, and SGPA must all be valid."
                ),
                legacy_key=legacy_key,
            )
        )
        return None

    verified = _boolean_flag(
        raw.get("verified"),
        field="semester_result_verified",
        legacy_key=legacy_key,
        issues=issues,
    )
    source = _clean_text(raw.get("source")) or "legacy grade configuration"
    recorded_at = _timestamp(raw.get("recorded_at"), imported_at)
    return _PreparedSemesterResult(
        legacy_key=legacy_key,
        earned_credits_milli=int(earned_credits),
        earned_grade_points_milli=int(earned_points),
        sgpa_milli=int(sgpa),
        verified=verified,
        source=source,
        recorded_at=recorded_at,
        raw=dict(raw),
    )


def _prepare_grade_config(
    snapshot: LegacySourceSnapshot,
    imported_at: str,
    issues: List[ImportIssue],
    review_items: List[GradeCalendarReviewItem],
) -> _PreparedGradeConfig:
    data = load_verified_json(snapshot, expected_kind="object")
    version = data.get("version")
    if version not in (None, 1, "1"):
        issues.append(
            ImportIssue(
                severity="warning",
                code="unexpected_grade_config_version",
                message=(
                    "semester_grade_config.json version {!r} was imported "
                    "without rewriting the source."
                ).format(version),
            )
        )
    semester_name = _clean_text(
        _alias_value(
            data,
            ("semester_name", "semester"),
            legacy_key="semester",
        )
    )
    target_sgpa_milli = _scaled_number(
        _alias_value(
            data,
            ("target_sgpa", "sgpa_target"),
            legacy_key="semester_grade_settings",
        ),
        scale=1000,
        field="target_sgpa",
        legacy_key="semester_grade_settings",
        issues=issues,
        maximum=Decimal("10"),
    )
    scale = _prepare_grade_scale(data, imported_at, issues)
    courses = _prepare_course_grades(
        data,
        semester_name,
        imported_at,
        issues,
        review_items,
    )
    result = _prepare_semester_result(
        data,
        semester_name,
        imported_at,
        issues,
        review_items,
    )
    return _PreparedGradeConfig(
        semester_name=semester_name,
        target_sgpa_milli=target_sgpa_milli,
        scale=scale,
        courses=courses,
        result=result,
    )


def _reference_forms(value: Any) -> Tuple[str, ...]:
    token = _normalized_token(value)
    if not token:
        return ()
    forms = {token}
    reduced = token
    changed = True
    while changed:
        changed = False
        for prefix in ("legacy_", "semester_", "sem_"):
            if reduced.startswith(prefix) and len(reduced) > len(prefix):
                reduced = reduced[len(prefix):]
                forms.add(reduced)
                changed = True
    return tuple(sorted(forms))


def _resolve_semester_target(
    connection: sqlite3.Connection,
    semester_name: str,
    issues: List[ImportIssue],
    review_items: List[GradeCalendarReviewItem],
) -> Optional[str]:
    rows = connection.execute(
        "SELECT mi.legacy_key, mi.target_id, mi.details_json, s.name "
        "FROM migration_imports AS mi "
        "JOIN semesters AS s ON s.id = mi.target_id "
        "WHERE mi.source_path = ? AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'semesters'",
        (COURSE_SOURCE_PATH,),
    ).fetchall()
    targets: Dict[str, set[str]] = {}
    for row in rows:
        target_id = str(row[1])
        labels = set(_reference_forms(row[0])) | set(_reference_forms(row[3]))
        try:
            details = json.loads(str(row[2]))
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        if isinstance(details, dict):
            labels.update(_reference_forms(details.get("legacy_semester")))
        targets.setdefault(target_id, set()).update(labels)

    if not targets:
        reason = "missing_fix4_semester_evidence"
        candidates: Tuple[str, ...] = ()
    elif not semester_name and len(targets) == 1:
        only = next(iter(targets))
        issues.append(
            ImportIssue(
                severity="info",
                code="single_semester_fallback",
                message=(
                    "Grade configuration has no semester name; the only "
                    "Fix 4 imported semester was used."
                ),
                legacy_key="semester",
            )
        )
        return only
    else:
        wanted = set(_reference_forms(semester_name))
        candidates = tuple(
            sorted(target_id for target_id, labels in targets.items() if wanted & labels)
        )
        reason = (
            "unresolved_semester_reference"
            if not candidates
            else "ambiguous_semester_reference"
        )
        if len(candidates) == 1:
            return candidates[0]

    issues.append(
        ImportIssue(
            severity="warning",
            code=reason,
            message=(
                "Grade semester {!r} could not be resolved exactly through "
                "Fix 4 course-import evidence."
            ).format(semester_name),
            legacy_key="semester",
        )
    )
    _review(
        review_items,
        source_path=GRADE_SOURCE_PATH,
        legacy_key="semester",
        entity_kind="semester",
        raw_reference=semester_name,
        reason=reason,
    )
    return None


def _course_candidates(
    connection: sqlite3.Connection,
    raw_course_id: str,
) -> Tuple[str, ...]:
    folded = raw_course_id.casefold()
    lookup_keys = {
        "course:id:{}".format(raw_course_id).casefold(),
        "course:code:{}".format(folded),
    }
    rows = connection.execute(
        "SELECT mi.legacy_key, mi.target_id, mi.details_json, c.code "
        "FROM migration_imports AS mi "
        "JOIN courses AS c ON c.id = mi.target_id "
        "WHERE mi.source_path = ? AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'courses' AND c.deleted_at IS NULL",
        (COURSE_SOURCE_PATH,),
    ).fetchall()
    matches = set()
    for row in rows:
        identifiers = {str(row[0]).casefold(), str(row[3]).casefold()}
        try:
            details = json.loads(str(row[2]))
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        if isinstance(details, dict):
            legacy_id = _clean_text(details.get("legacy_id"))
            if legacy_id:
                identifiers.add(legacy_id.casefold())
        if folded in identifiers or lookup_keys & identifiers:
            matches.add(str(row[1]))
    return tuple(sorted(matches))


def _resolve_course_target(
    connection: sqlite3.Connection,
    raw_course_id: str,
    semester_id: Optional[str],
    issues: List[ImportIssue],
    review_items: List[GradeCalendarReviewItem],
    legacy_key: str,
) -> Optional[str]:
    candidates = _course_candidates(connection, raw_course_id)
    if len(candidates) == 1 and semester_id is not None:
        course_id = candidates[0]
        linked = connection.execute(
            "SELECT 1 FROM semester_courses WHERE semester_id = ? AND course_id = ?",
            (semester_id, course_id),
        ).fetchone()
        if linked is not None:
            return course_id
        reason = "course_not_enrolled_in_grade_semester"
    elif len(candidates) == 1:
        reason = "grade_semester_unresolved"
    elif not candidates:
        reason = "unresolved_course_reference"
    else:
        reason = "ambiguous_course_reference"

    issues.append(
        ImportIssue(
            severity="warning",
            code=reason,
            message=(
                "Grade course reference {!r} could not be linked exactly to "
                "the configured imported semester."
            ).format(raw_course_id),
            legacy_key=legacy_key,
        )
    )
    _review(
        review_items,
        source_path=GRADE_SOURCE_PATH,
        legacy_key=legacy_key,
        entity_kind="grade_course",
        raw_reference=raw_course_id,
        reason=reason,
    )
    return None


def _semester_for_assessment_course(
    connection: sqlite3.Connection,
    course_id: str,
    assessment_key: str,
    issues: List[ImportIssue],
    review_items: List[GradeCalendarReviewItem],
) -> Optional[str]:
    rows = connection.execute(
        "SELECT semester_id FROM semester_courses WHERE course_id = ? "
        "ORDER BY semester_id",
        (course_id,),
    ).fetchall()
    candidates = tuple(sorted({str(row[0]) for row in rows}))
    if len(candidates) == 1:
        return candidates[0]
    reason = (
        "calendar_semester_unresolved"
        if not candidates
        else "calendar_semester_ambiguous"
    )
    issues.append(
        ImportIssue(
            severity="warning",
            code=reason,
            message=(
                "Assessment calendar event could not be linked to exactly one "
                "semester; its course link is preserved without guessing."
            ),
            legacy_key=assessment_key,
        )
    )
    _review(
        review_items,
        source_path=ASSESSMENT_SOURCE_PATH,
        legacy_key=assessment_key,
        entity_kind="academic_event",
        raw_reference=course_id,
        reason=reason,
    )
    return None


def _assessment_event_status(value: Any) -> str:
    token = _normalized_token(value)
    if token in {"completed", "done"}:
        return "completed"
    if token in {"cancelled", "canceled", "archived"}:
        return "cancelled"
    return "scheduled"


def _prepare_deadlines(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    issues: List[ImportIssue],
    review_items: List[GradeCalendarReviewItem],
) -> Tuple[_PreparedDeadline, ...]:
    data = load_verified_json(snapshot, expected_kind="object")
    raw_assessments = data.get("assessments", [])
    if not isinstance(raw_assessments, list):
        raise LegacyImportDataError(
            "assessments.json field 'assessments' must be an array"
        )

    rows = connection.execute(
        "SELECT mi.legacy_key, mi.target_id, a.course_id, a.title, "
        "a.due_on, a.due_time, a.status, a.created_at, a.updated_at "
        "FROM migration_imports AS mi "
        "JOIN assessments AS a ON a.id = mi.target_id "
        "WHERE mi.source_path = ? AND mi.source_hash = ? "
        "AND mi.source_type = ? AND mi.source_version = ? "
        "AND mi.target_table = 'assessments' "
        "ORDER BY mi.legacy_key, mi.target_id",
        (
            snapshot.canonical_path,
            snapshot.source_hash,
            snapshot.source_type,
            snapshot.source_version,
        ),
    ).fetchall()
    unique_rows: Dict[str, sqlite3.Row] = {}
    for row in rows:
        target_id = str(row[1])
        if target_id in unique_rows and str(unique_rows[target_id][0]) != str(row[0]):
            raise LegacyImportError(
                "one imported assessment target has multiple current legacy identities"
            )
        unique_rows[target_id] = row
    if len(unique_rows) != len(raw_assessments):
        raise LegacyImportError(
            "current assessments snapshot has not been imported by Fix 5; "
            "import assessments/topics before building calendar events"
        )

    prepared: List[_PreparedDeadline] = []
    for row in unique_rows.values():
        assessment_key = str(row[0])
        assessment_id = str(row[1])
        course_id = str(row[2])
        due_on = None if row[4] is None else str(row[4])
        due_time = None if row[5] is None else str(row[5])
        starts_at = None
        all_day = 1
        if due_on:
            starts_at = due_on if not due_time else "{}T{}".format(due_on, due_time)
            all_day = 0 if due_time else 1
        event_key = "{}/academic_event:deadline".format(assessment_key)
        prepared.append(
            _PreparedDeadline(
                legacy_key=event_key,
                target_id=stable_target_id(
                    ASSESSMENT_SOURCE_PATH,
                    "academic_event",
                    event_key,
                ),
                assessment_id=assessment_id,
                course_id=course_id,
                semester_id=_semester_for_assessment_course(
                    connection,
                    course_id,
                    assessment_key,
                    issues,
                    review_items,
                ),
                title=str(row[3]),
                starts_at=starts_at,
                all_day=all_day,
                status=_assessment_event_status(row[6]),
                created_at=str(row[7]),
                updated_at=str(row[8]),
            )
        )
    return tuple(prepared)


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
            # Reuse the ledger's conflict validation and error type.
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
    target_exists = connection.execute(existence_sql, existence_params).fetchone()
    return "updated" if target_exists is not None else "created"


def _check_grade_snapshot(
    snapshot: Optional[LegacySourceSnapshot],
) -> Tuple[str, bool]:
    if snapshot is None:
        return GRADE_SOURCE_PATH, False
    if snapshot.canonical_path != GRADE_SOURCE_PATH:
        raise LegacyImportDataError(
            "grades/calendar importer requires data/semester_grade_config.json"
        )
    if snapshot.status == STATUS_MISSING:
        if snapshot.physical_path.exists():
            raise LegacySourceChangedError(
                "optional grade source appeared after scan: {}".format(
                    snapshot.canonical_path
                )
            )
        return snapshot.canonical_path, False
    if snapshot.status != STATUS_VALID_JSON:
        raise LegacyImportDataError(
            "optional grade source exists but is not valid_json: {}".format(
                snapshot.status
            )
        )
    return snapshot.canonical_path, True


def import_grades_and_academic_calendar(
    connection: sqlite3.Connection,
    grade_snapshot: Optional[LegacySourceSnapshot],
    assessment_snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> GradeCalendarImportResult:
    """Import explicit grade configuration and linked assessment deadlines.

    The grade source is optional.  The assessment source is required and its
    current hash must already have Fix 5 ``assessments`` ledger mappings.
    """
    ensure_tables(connection, REQUIRED_TABLES)
    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")
    if assessment_snapshot.canonical_path != ASSESSMENT_SOURCE_PATH:
        raise LegacyImportDataError(
            "grades/calendar importer requires data/assessments.json"
        )
    if assessment_snapshot.status != STATUS_VALID_JSON:
        raise LegacyImportDataError("assessments source must be valid_json")

    grade_path, grade_present = _check_grade_snapshot(grade_snapshot)
    issues: List[ImportIssue] = []
    review_items: List[GradeCalendarReviewItem] = []
    prepared_grade: Optional[_PreparedGradeConfig] = None
    semester_id: Optional[str] = None
    resolved_courses: Dict[str, Optional[str]] = {}

    if grade_present:
        assert grade_snapshot is not None
        prepared_grade = _prepare_grade_config(
            grade_snapshot,
            imported_at,
            issues,
            review_items,
        )
        semester_id = _resolve_semester_target(
            connection,
            prepared_grade.semester_name,
            issues,
            review_items,
        )
        for course in prepared_grade.courses:
            resolved_courses[course.legacy_key] = _resolve_course_target(
                connection,
                course.raw_course_id,
                semester_id,
                issues,
                review_items,
                course.legacy_key,
            )

    deadlines = _prepare_deadlines(
        connection,
        assessment_snapshot,
        issues,
        review_items,
    )
    counters: Dict[str, Dict[str, int]] = {
        "grade_scales": {},
        "grade_bands": {},
        "semester_grade_settings": {},
        "semester_course_credits": {},
        "manual_grade_entries": {},
        "semester_results": {},
        "academic_events": {},
    }
    assessments_without_due_date = 0
    ledger = MigrationImportLedger(connection)

    with transaction(connection, immediate=True):
        if prepared_grade is not None:
            assert grade_snapshot is not None
            scale = prepared_grade.scale
            disposition = _ledger_disposition(
                connection,
                ledger,
                grade_snapshot,
                legacy_key=scale.legacy_key,
                target_table="grade_scales",
                target_id=scale.target_id,
                existence_sql="SELECT 1 FROM grade_scales WHERE id = ?",
                existence_params=(scale.target_id,),
            )
            if disposition != "matched":
                connection.execute(
                    "INSERT INTO grade_scales "
                    "(id, name, source, verified, active_from, active_to, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET name = excluded.name, "
                    "source = excluded.source, verified = excluded.verified, "
                    "active_from = excluded.active_from, active_to = excluded.active_to, "
                    "updated_at = excluded.updated_at",
                    (
                        scale.target_id,
                        scale.name,
                        scale.source,
                        scale.verified,
                        scale.active_from,
                        scale.active_to,
                        scale.created_at,
                        scale.updated_at,
                    ),
                )
                ledger.record_snapshot_import(
                    grade_snapshot,
                    legacy_key=scale.legacy_key,
                    target_table="grade_scales",
                    target_id=scale.target_id,
                    details={
                        "kind": "grade_scale_version",
                        "fingerprint": scale.fingerprint,
                        "verified": bool(scale.verified),
                        "raw": list(scale.raw),
                    },
                    imported_at=imported_at,
                )
            add_tally(counters["grade_scales"], disposition)

            for band in scale.bands:
                disposition = _ledger_disposition(
                    connection,
                    ledger,
                    grade_snapshot,
                    legacy_key=band.legacy_key,
                    target_table="grade_bands",
                    target_id=band.target_id,
                    existence_sql="SELECT 1 FROM grade_bands WHERE id = ?",
                    existence_params=(band.target_id,),
                )
                if disposition != "matched":
                    connection.execute(
                        "INSERT INTO grade_bands "
                        "(id, scale_id, minimum_bps, letter_grade, grade_point_milli) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                        "scale_id = excluded.scale_id, "
                        "minimum_bps = excluded.minimum_bps, "
                        "letter_grade = excluded.letter_grade, "
                        "grade_point_milli = excluded.grade_point_milli",
                        (
                            band.target_id,
                            scale.target_id,
                            band.minimum_bps,
                            band.letter_grade,
                            band.grade_point_milli,
                        ),
                    )
                    ledger.record_snapshot_import(
                        grade_snapshot,
                        legacy_key=band.legacy_key,
                        target_table="grade_bands",
                        target_id=band.target_id,
                        details={
                            "kind": "grade_band",
                            "scale_id": scale.target_id,
                            "raw": dict(band.raw),
                        },
                        imported_at=imported_at,
                    )
                add_tally(counters["grade_bands"], disposition)

            if semester_id is not None:
                settings_key = "semester_grade_settings:{}".format(
                    _normalized_token(prepared_grade.semester_name) or semester_id
                )
                disposition = _ledger_disposition(
                    connection,
                    ledger,
                    grade_snapshot,
                    legacy_key=settings_key,
                    target_table="semester_grade_settings",
                    target_id=semester_id,
                    existence_sql=(
                        "SELECT 1 FROM semester_grade_settings WHERE semester_id = ?"
                    ),
                    existence_params=(semester_id,),
                )
                if disposition != "matched":
                    connection.execute(
                        "INSERT INTO semester_grade_settings "
                        "(semester_id, scale_id, target_sgpa_milli, updated_at) "
                        "VALUES (?, ?, ?, ?) ON CONFLICT(semester_id) DO UPDATE SET "
                        "scale_id = excluded.scale_id, "
                        "target_sgpa_milli = excluded.target_sgpa_milli, "
                        "updated_at = excluded.updated_at",
                        (
                            semester_id,
                            scale.target_id,
                            prepared_grade.target_sgpa_milli,
                            imported_at,
                        ),
                    )
                    ledger.record_snapshot_import(
                        grade_snapshot,
                        legacy_key=settings_key,
                        target_table="semester_grade_settings",
                        target_id=semester_id,
                        details={
                            "kind": "semester_grade_settings",
                            "semester_name": prepared_grade.semester_name,
                            "scale_id": scale.target_id,
                            "target_sgpa_milli": prepared_grade.target_sgpa_milli,
                        },
                        imported_at=imported_at,
                    )
                add_tally(counters["semester_grade_settings"], disposition)

            for course in prepared_grade.courses:
                course_id = resolved_courses.get(course.legacy_key)
                if semester_id is None or course_id is None:
                    continue
                composite_id = "{}|{}".format(semester_id, course_id)
                if course.credits_milli is not None:
                    credit_key = "{}/semester_course_credits".format(course.legacy_key)
                    disposition = _ledger_disposition(
                        connection,
                        ledger,
                        grade_snapshot,
                        legacy_key=credit_key,
                        target_table="semester_courses",
                        target_id=composite_id,
                        existence_sql=(
                            "SELECT 1 FROM semester_courses "
                            "WHERE semester_id = ? AND course_id = ?"
                        ),
                        existence_params=(semester_id, course_id),
                    )
                    if disposition != "matched":
                        connection.execute(
                            "UPDATE semester_courses SET credits_milli = ? "
                            "WHERE semester_id = ? AND course_id = ?",
                            (course.credits_milli, semester_id, course_id),
                        )
                        ledger.record_snapshot_import(
                            grade_snapshot,
                            legacy_key=credit_key,
                            target_table="semester_courses",
                            target_id=composite_id,
                            details={
                                "kind": "semester_course_credits",
                                "raw_course_id": course.raw_course_id,
                                "target_course_id": course_id,
                                "credits_milli": course.credits_milli,
                                "raw": dict(course.raw),
                            },
                            imported_at=imported_at,
                        )
                    add_tally(counters["semester_course_credits"], disposition)

                if course.manual_entry_id is not None and course.manual_entry_key is not None:
                    disposition = _ledger_disposition(
                        connection,
                        ledger,
                        grade_snapshot,
                        legacy_key=course.manual_entry_key,
                        target_table="manual_grade_entries",
                        target_id=course.manual_entry_id,
                        existence_sql="SELECT 1 FROM manual_grade_entries WHERE id = ?",
                        existence_params=(course.manual_entry_id,),
                    )
                    if disposition != "matched":
                        connection.execute(
                            "INSERT INTO manual_grade_entries "
                            "(id, semester_id, course_id, score_bps, letter_grade, "
                            "grade_point_milli, entry_kind, note, recorded_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(id) DO UPDATE SET "
                            "semester_id = excluded.semester_id, "
                            "course_id = excluded.course_id, score_bps = excluded.score_bps, "
                            "letter_grade = excluded.letter_grade, "
                            "grade_point_milli = excluded.grade_point_milli, "
                            "entry_kind = excluded.entry_kind, note = excluded.note",
                            (
                                course.manual_entry_id,
                                semester_id,
                                course_id,
                                course.score_bps,
                                course.letter_grade,
                                course.grade_point_milli,
                                course.entry_kind,
                                course.note,
                                course.recorded_at,
                            ),
                        )
                        ledger.record_snapshot_import(
                            grade_snapshot,
                            legacy_key=course.manual_entry_key,
                            target_table="manual_grade_entries",
                            target_id=course.manual_entry_id,
                            details={
                                "kind": "manual_grade_entry",
                                "raw_course_id": course.raw_course_id,
                                "target_course_id": course_id,
                                "raw": dict(course.raw),
                            },
                            imported_at=imported_at,
                        )
                    add_tally(counters["manual_grade_entries"], disposition)

            result = prepared_grade.result
            if result is not None and semester_id is not None:
                result_target_id = stable_target_id(
                    GRADE_SOURCE_PATH,
                    "semester_result",
                    "semester_result:target:{}".format(semester_id),
                )
                disposition = _ledger_disposition(
                    connection,
                    ledger,
                    grade_snapshot,
                    legacy_key=result.legacy_key,
                    target_table="semester_results",
                    target_id=result_target_id,
                    existence_sql="SELECT 1 FROM semester_results WHERE id = ?",
                    existence_params=(result_target_id,),
                )
                if disposition != "matched":
                    connection.execute(
                        "INSERT INTO semester_results "
                        "(id, semester_id, earned_credits_milli, "
                        "earned_grade_points_milli, sgpa_milli, verified, source, "
                        "recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "semester_id = excluded.semester_id, "
                        "earned_credits_milli = excluded.earned_credits_milli, "
                        "earned_grade_points_milli = excluded.earned_grade_points_milli, "
                        "sgpa_milli = excluded.sgpa_milli, "
                        "verified = excluded.verified, source = excluded.source, "
                        "recorded_at = excluded.recorded_at",
                        (
                            result_target_id,
                            semester_id,
                            result.earned_credits_milli,
                            result.earned_grade_points_milli,
                            result.sgpa_milli,
                            result.verified,
                            result.source,
                            result.recorded_at,
                        ),
                    )
                    ledger.record_snapshot_import(
                        grade_snapshot,
                        legacy_key=result.legacy_key,
                        target_table="semester_results",
                        target_id=result_target_id,
                        details={"kind": "semester_result", "raw": dict(result.raw)},
                        imported_at=imported_at,
                    )
                add_tally(counters["semester_results"], disposition)

        for deadline in deadlines:
            existing_event = connection.execute(
                "SELECT 1 FROM academic_events WHERE id = ?",
                (deadline.target_id,),
            ).fetchone()
            if deadline.starts_at is None and existing_event is None:
                assessments_without_due_date += 1
                continue
            disposition = _ledger_disposition(
                connection,
                ledger,
                assessment_snapshot,
                legacy_key=deadline.legacy_key,
                target_table="academic_events",
                target_id=deadline.target_id,
                existence_sql="SELECT 1 FROM academic_events WHERE id = ?",
                existence_params=(deadline.target_id,),
            )
            if disposition != "matched":
                if deadline.starts_at is None:
                    assessments_without_due_date += 1
                    connection.execute(
                        "UPDATE academic_events SET status = 'cancelled', "
                        "updated_at = ?, deleted_at = ? WHERE id = ?",
                        (imported_at, imported_at, deadline.target_id),
                    )
                    details = {
                        "kind": "assessment_deadline_tombstone",
                        "assessment_id": deadline.assessment_id,
                        "reason": "assessment_due_date_absent",
                    }
                else:
                    connection.execute(
                        "INSERT INTO academic_events "
                        "(id, semester_id, course_id, event_kind, title, starts_at, "
                        "ends_at, all_day, recurrence_rule, reference_type, "
                        "reference_id, status, source_entity_type, source_entity_id, "
                        "created_at, updated_at, deleted_at) "
                        "VALUES (?, ?, ?, 'assessment_deadline', ?, ?, NULL, ?, NULL, "
                        "'assessment', ?, ?, 'assessment', ?, ?, ?, NULL) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "semester_id = excluded.semester_id, "
                        "course_id = excluded.course_id, event_kind = excluded.event_kind, "
                        "title = excluded.title, starts_at = excluded.starts_at, "
                        "ends_at = NULL, all_day = excluded.all_day, "
                        "recurrence_rule = NULL, reference_type = 'assessment', "
                        "reference_id = excluded.reference_id, status = excluded.status, "
                        "source_entity_type = 'assessment', "
                        "source_entity_id = excluded.source_entity_id, "
                        "updated_at = excluded.updated_at, deleted_at = NULL",
                        (
                            deadline.target_id,
                            deadline.semester_id,
                            deadline.course_id,
                            deadline.title,
                            deadline.starts_at,
                            deadline.all_day,
                            deadline.assessment_id,
                            deadline.status,
                            deadline.assessment_id,
                            deadline.created_at,
                            deadline.updated_at,
                        ),
                    )
                    details = {
                        "kind": "assessment_deadline_event",
                        "assessment_id": deadline.assessment_id,
                        "course_id": deadline.course_id,
                        "semester_id": deadline.semester_id,
                    }
                ledger.record_snapshot_import(
                    assessment_snapshot,
                    legacy_key=deadline.legacy_key,
                    target_table="academic_events",
                    target_id=deadline.target_id,
                    details=details,
                    imported_at=imported_at,
                )
            elif deadline.starts_at is None:
                assessments_without_due_date += 1
            add_tally(counters["academic_events"], disposition)

        source_sha256(assessment_snapshot)
        if grade_present:
            assert grade_snapshot is not None
            source_sha256(grade_snapshot)
        elif grade_snapshot is not None:
            # Detect an optional file appearing after the approved missing scan.
            _check_grade_snapshot(grade_snapshot)

    imported_sources = [ASSESSMENT_SOURCE_PATH]
    optional_absent: List[str] = []
    if grade_present:
        imported_sources.insert(0, grade_path)
    else:
        optional_absent.append(grade_path)
        issues.append(
            ImportIssue(
                severity="info",
                code="grade_configuration_absent",
                message=(
                    "Optional data/semester_grade_config.json is absent; "
                    "grades remain not configured while assessment deadlines "
                    "can still be projected into the calendar."
                ),
            )
        )

    return GradeCalendarImportResult(
        sources_scanned=2 if grade_snapshot is not None else 1,
        imported_sources=tuple(imported_sources),
        optional_sources_absent=tuple(optional_absent),
        grade_scales=freeze_tally(counters["grade_scales"]),
        grade_bands=freeze_tally(counters["grade_bands"]),
        semester_grade_settings=freeze_tally(counters["semester_grade_settings"]),
        semester_course_credits=freeze_tally(counters["semester_course_credits"]),
        manual_grade_entries=freeze_tally(counters["manual_grade_entries"]),
        semester_results=freeze_tally(counters["semester_results"]),
        academic_events=freeze_tally(counters["academic_events"]),
        assessments_without_due_date=assessments_without_due_date,
        review_items=tuple(review_items),
        issues=tuple(issues),
    )


def import_grades_calendar(
    connection: sqlite3.Connection,
    grade_snapshot: Optional[LegacySourceSnapshot],
    assessment_snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> GradeCalendarImportResult:
    """Compatibility alias for :func:`import_grades_and_academic_calendar`."""
    return import_grades_and_academic_calendar(
        connection,
        grade_snapshot,
        assessment_snapshot,
        imported_at=imported_at,
    )


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def render_grade_calendar_import_review_markdown(
    result: GradeCalendarImportResult,
) -> str:
    """Render a portable review report without writing to the filesystem."""
    lines = [
        "# Grades and Academic Calendar Import Review",
        "",
        "- Imported sources: {}".format(", ".join(result.imported_sources) or "none"),
        "- Optional sources absent/not configured: {}".format(
            ", ".join(result.optional_sources_absent) or "none"
        ),
        "- Grade scales: created {}, updated {}, matched {}".format(
            result.grade_scales.created,
            result.grade_scales.updated,
            result.grade_scales.matched,
        ),
        "- Grade bands: created {}, updated {}, matched {}".format(
            result.grade_bands.created,
            result.grade_bands.updated,
            result.grade_bands.matched,
        ),
        "- Semester grade settings: created {}, updated {}, matched {}".format(
            result.semester_grade_settings.created,
            result.semester_grade_settings.updated,
            result.semester_grade_settings.matched,
        ),
        "- Semester course credits: created {}, updated {}, matched {}".format(
            result.semester_course_credits.created,
            result.semester_course_credits.updated,
            result.semester_course_credits.matched,
        ),
        "- Manual grade entries: created {}, updated {}, matched {}".format(
            result.manual_grade_entries.created,
            result.manual_grade_entries.updated,
            result.manual_grade_entries.matched,
        ),
        "- Semester results: created {}, updated {}, matched {}".format(
            result.semester_results.created,
            result.semester_results.updated,
            result.semester_results.matched,
        ),
        "- Academic events: created {}, updated {}, matched {}".format(
            result.academic_events.created,
            result.academic_events.updated,
            result.academic_events.matched,
        ),
        "- Assessments without due dates: {}".format(
            result.assessments_without_due_date
        ),
        "- Review-required items: {}".format(result.review_required_items),
        "",
    ]
    if not result.review_items:
        lines.append("No grade or calendar references require review.")
        return "\n".join(lines) + "\n"
    lines.extend(
        (
            "| Source | Legacy key | Entity | Raw reference | Reason |",
            "|---|---|---|---|---|",
        )
    )
    for item in result.review_items:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                _markdown_cell(item.source_path),
                _markdown_cell(item.legacy_key),
                _markdown_cell(item.entity_kind),
                _markdown_cell(item.raw_reference or "n/a"),
                _markdown_cell(item.reason),
            )
        )
    return "\n".join(lines) + "\n"


__all__ = (
    "GradeAcademicCalendarImportResult",
    "GradeCalendarImportResult",
    "GradeCalendarReviewItem",
    "GradesCalendarImportResult",
    "import_grades_and_academic_calendar",
    "import_grades_calendar",
    "render_grade_calendar_import_review_markdown",
)
