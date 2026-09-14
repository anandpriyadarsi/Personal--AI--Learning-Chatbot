"""Idempotent Phase 3 importer for legacy ``courses.json``.

This is a shadow migration adapter only. It imports a verified legacy snapshot
into an explicit temporary SQLite database while JSON remains authoritative.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from personal_learning_assistant.domain.course_normalization import (
    VALID_COURSE_STATUSES,
    VALID_TOPIC_STATUSES,
    _clean_text,
    _normalise_status,
)
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
    "app_settings",
    "semesters",
    "courses",
    "semester_courses",
    "topics",
)


@dataclass(frozen=True)
class CourseTopicImportResult:
    source_path: str
    source_hash: str
    semesters: ImportTally
    courses: ImportTally
    semester_courses: ImportTally
    topics: ImportTally
    settings: ImportTally
    deferred_document_links: int
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        tallies = (
            self.semesters,
            self.courses,
            self.semester_courses,
            self.topics,
            self.settings,
        )
        return sum(item.created + item.updated for item in tallies)


@dataclass(frozen=True)
class _PreparedTopic:
    legacy_key: str
    target_id: str
    name: str
    normalized_name: str
    status: str
    raw_status: Optional[str]
    confidence: Optional[int]
    position: int
    created_at: str
    updated_at: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedCourse:
    legacy_key: str
    raw_legacy_id: str
    target_id: str
    code: str
    name: str
    status: str
    semester_label: str
    semester_key: str
    semester_id: str
    created_at: str
    updated_at: str
    topics: Tuple[_PreparedTopic, ...]
    raw: Mapping[str, Any]


def _text(value: Any) -> str:
    return _clean_text(value)


def _normalized_name(value: str) -> str:
    return _text(value).casefold()


def _timestamp(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _confidence(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_topic_confidence",
                message="Topic confidence is not an integer; imported as NULL.",
                legacy_key=legacy_key,
            )
        )
        return None

    clamped = max(0, min(5, parsed))
    if clamped != parsed:
        issues.append(
            ImportIssue(
                severity="warning",
                code="clamped_topic_confidence",
                message=(
                    "Topic confidence {} is outside 0..5; imported as {}."
                    .format(parsed, clamped)
                ),
                legacy_key=legacy_key,
            )
        )
    return clamped


def _legacy_course_key(
    raw: Mapping[str, Any],
    code: str,
    position: int,
) -> Tuple[str, str]:
    raw_id = _text(raw.get("id"))
    if raw_id:
        return "course:id:{}".format(raw_id), raw_id
    if code:
        return "course:code:{}".format(code.casefold()), ""
    return "course:index:{}".format(position), ""


def _legacy_topic_key(
    course_key: str,
    raw: Mapping[str, Any],
    normalized_name: str,
    position: int,
) -> str:
    raw_id = _text(raw.get("id"))
    if raw_id:
        suffix = "id:{}".format(raw_id)
    elif normalized_name:
        suffix = "name:{}".format(normalized_name)
    else:
        suffix = "index:{}".format(position)
    return "{}/topic:{}".format(course_key, suffix)


def _semester_key(label: str) -> str:
    return "semester:{}".format(label if label else "<unspecified>")


def _semester_name(label: str) -> str:
    if label:
        return "Legacy Semester {}".format(label)
    return "Legacy Semester (unspecified)"


def _enrollment_status(course_status: str) -> str:
    return {
        "active": "enrolled",
        "planned": "planned",
        "completed": "completed",
        "archived": "archived",
    }.get(course_status, "enrolled")


def _prepare_courses(
    snapshot: LegacySourceSnapshot,
    data: Mapping[str, Any],
    imported_at: str,
    issues: List[ImportIssue],
) -> Tuple[Tuple[_PreparedCourse, ...], Dict[str, str]]:
    raw_courses = data.get("courses", [])
    if not isinstance(raw_courses, list):
        raise LegacyImportDataError("courses.json field 'courses' must be an array")

    prepared: List[_PreparedCourse] = []
    active_lookup: Dict[str, str] = {}
    seen_codes = set()
    seen_course_keys = set()

    for course_position, raw_course in enumerate(raw_courses):
        if not isinstance(raw_course, dict):
            raise LegacyImportDataError(
                "course at index {} must be a JSON object".format(course_position)
            )

        code = _text(raw_course.get("code")).upper()
        name = _text(raw_course.get("name"))
        if not code:
            raise LegacyImportDataError(
                "course at index {} has no course code; refusing to invent one"
                .format(course_position)
            )
        if not name:
            raise LegacyImportDataError("course {} has no name".format(code))

        code_key = code.casefold()
        if code_key in seen_codes:
            raise LegacyImportDataError(
                "duplicate legacy course code: {}".format(code)
            )
        seen_codes.add(code_key)

        course_key, raw_legacy_id = _legacy_course_key(
            raw_course,
            code,
            course_position,
        )
        if course_key in seen_course_keys:
            raise LegacyImportDataError(
                "duplicate legacy course identity: {}".format(course_key)
            )
        seen_course_keys.add(course_key)

        target_id = stable_target_id(
            snapshot.canonical_path,
            "course",
            course_key,
        )
        if raw_legacy_id:
            active_lookup[raw_legacy_id] = target_id

        raw_status = _text(raw_course.get("status"))
        course_status = _normalise_status(
            raw_status,
            VALID_COURSE_STATUSES,
            "active",
        )
        normalized_raw_status = (
            raw_status.lower().replace("-", "_").replace(" ", "_")
        )
        if raw_status and normalized_raw_status != course_status:
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="normalized_course_status",
                    message=(
                        "Course status {!r} imported canonically as {!r}."
                        .format(raw_status, course_status)
                    ),
                    legacy_key=course_key,
                )
            )

        semester_label = _text(raw_course.get("semester"))
        semester_key = _semester_key(semester_label)
        semester_id = stable_target_id(
            snapshot.canonical_path,
            "semester_placeholder",
            semester_key,
        )

        raw_topics = raw_course.get("topics", [])
        if raw_topics is None:
            raw_topics = []
        if not isinstance(raw_topics, list):
            raise LegacyImportDataError(
                "topics for course {} must be an array".format(code)
            )

        topics: List[_PreparedTopic] = []
        seen_topic_names = set()
        seen_topic_keys = set()
        for topic_position, raw_topic in enumerate(raw_topics):
            if isinstance(raw_topic, str):
                raw_topic = {"name": raw_topic}
            if not isinstance(raw_topic, dict):
                raise LegacyImportDataError(
                    "topic {} in course {} must be an object or string"
                    .format(topic_position, code)
                )

            topic_name = _text(raw_topic.get("name"))
            if not topic_name:
                raise LegacyImportDataError(
                    "topic {} in course {} has no name"
                    .format(topic_position, code)
                )
            normalized_name = _normalized_name(topic_name)
            if normalized_name in seen_topic_names:
                raise LegacyImportDataError(
                    "duplicate topic name in course {}: {}".format(
                        code,
                        topic_name,
                    )
                )
            seen_topic_names.add(normalized_name)

            topic_key = _legacy_topic_key(
                course_key,
                raw_topic,
                normalized_name,
                topic_position,
            )
            if topic_key in seen_topic_keys:
                raise LegacyImportDataError(
                    "duplicate legacy topic identity: {}".format(topic_key)
                )
            seen_topic_keys.add(topic_key)

            topic_target_id = stable_target_id(
                snapshot.canonical_path,
                "topic",
                topic_key,
            )
            raw_topic_status = _text(raw_topic.get("status"))
            topic_status = _normalise_status(
                raw_topic_status,
                VALID_TOPIC_STATUSES,
                "not_started",
            )
            normalized_raw_topic_status = (
                raw_topic_status.lower().replace("-", "_").replace(" ", "_")
            )
            if raw_topic_status and normalized_raw_topic_status != topic_status:
                issues.append(
                    ImportIssue(
                        severity="warning",
                        code="normalized_topic_status",
                        message=(
                            "Topic status {!r} imported canonically as {!r}."
                            .format(raw_topic_status, topic_status)
                        ),
                        legacy_key=topic_key,
                    )
                )

            topics.append(
                _PreparedTopic(
                    legacy_key=topic_key,
                    target_id=topic_target_id,
                    name=topic_name,
                    normalized_name=normalized_name,
                    status=topic_status,
                    raw_status=(raw_topic_status or None),
                    confidence=_confidence(
                        raw_topic.get("confidence"),
                        issues=issues,
                        legacy_key=topic_key,
                    ),
                    position=topic_position,
                    created_at=imported_at,
                    updated_at=_timestamp(
                        raw_topic.get("last_updated"),
                        imported_at,
                    ),
                    raw=dict(raw_topic),
                )
            )

        prepared.append(
            _PreparedCourse(
                legacy_key=course_key,
                raw_legacy_id=raw_legacy_id,
                target_id=target_id,
                code=code,
                name=name,
                status=course_status,
                semester_label=semester_label,
                semester_key=semester_key,
                semester_id=semester_id,
                created_at=_timestamp(raw_course.get("created_at"), imported_at),
                updated_at=_timestamp(raw_course.get("updated_at"), imported_at),
                topics=tuple(topics),
                raw=dict(raw_course),
            )
        )

    return tuple(prepared), active_lookup


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
                "migration ledger points to a missing {} target: {}"
                .format(target_table, target_id)
            )
        return "matched"

    target_exists = connection.execute(
        existence_sql,
        existence_params,
    ).fetchone()
    return "updated" if target_exists is not None else "created"


def import_courses_and_topics(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> CourseTopicImportResult:
    """Import one verified ``courses.json`` snapshot transactionally."""
    ensure_tables(connection, REQUIRED_TABLES)
    data = load_verified_json(snapshot, expected_kind="object")

    if snapshot.canonical_path != "data/courses.json":
        raise LegacyImportDataError(
            "courses/topics importer requires data/courses.json"
        )
    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")

    issues: List[ImportIssue] = []
    prepared, active_lookup = _prepare_courses(
        snapshot,
        data,
        imported_at,
        issues,
    )

    raw_document_links = data.get("document_links", {})
    if raw_document_links is None:
        raw_document_links = {}
    if not isinstance(raw_document_links, dict):
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_document_links_shape",
                message=(
                    "document_links is not an object; left untouched in JSON "
                    "for a later knowledge/document migration unit."
                ),
            )
        )
        deferred_document_links = 0
    else:
        deferred_document_links = len(raw_document_links)
        if deferred_document_links:
            issues.append(
                ImportIssue(
                    severity="info",
                    code="document_links_deferred",
                    message=(
                        "{} legacy course document link(s) remain deferred to "
                        "the knowledge/document importer."
                        .format(deferred_document_links)
                    ),
                )
            )

    version = data.get("version")
    if version not in (None, 1, "1"):
        issues.append(
            ImportIssue(
                severity="warning",
                code="unexpected_courses_version",
                message=(
                    "courses.json version {!r} was imported without rewriting "
                    "the source."
                ).format(version),
            )
        )

    counters: Dict[str, Dict[str, int]] = {
        "semesters": {},
        "courses": {},
        "semester_courses": {},
        "topics": {},
        "settings": {},
    }
    ledger = MigrationImportLedger(connection)

    distinct_semesters: Dict[str, _PreparedCourse] = {}
    for course in prepared:
        distinct_semesters.setdefault(course.semester_key, course)

    with transaction(connection, immediate=True):
        for semester_key, representative in distinct_semesters.items():
            semester_id = representative.semester_id
            disposition = _ledger_disposition(
                connection,
                ledger,
                snapshot,
                legacy_key=semester_key,
                target_table="semesters",
                target_id=semester_id,
                existence_sql="SELECT 1 FROM semesters WHERE id = ?",
                existence_params=(semester_id,),
            )
            if disposition != "matched":
                connection.execute(
                    "INSERT INTO semesters "
                    "(id, name, academic_year, starts_on, ends_on, status, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, NULL, NULL, 'planned', ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "name = excluded.name, academic_year = excluded.academic_year, "
                    "updated_at = excluded.updated_at",
                    (
                        semester_id,
                        _semester_name(representative.semester_label),
                        "legacy-unknown",
                        imported_at,
                        imported_at,
                    ),
                )
                ledger.record_snapshot_import(
                    snapshot,
                    legacy_key=semester_key,
                    target_table="semesters",
                    target_id=semester_id,
                    details={
                        "kind": "semester_placeholder",
                        "legacy_semester": representative.semester_label,
                        "academic_year": "legacy-unknown",
                    },
                    imported_at=imported_at,
                )
            add_tally(counters["semesters"], disposition)

        for course in prepared:
            disposition = _ledger_disposition(
                connection,
                ledger,
                snapshot,
                legacy_key=course.legacy_key,
                target_table="courses",
                target_id=course.target_id,
                existence_sql="SELECT 1 FROM courses WHERE id = ?",
                existence_params=(course.target_id,),
            )
            if disposition != "matched":
                connection.execute(
                    "INSERT INTO courses "
                    "(id, code, name, status, description, created_at, updated_at, "
                    "deleted_at) VALUES (?, ?, ?, ?, '', ?, ?, NULL) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "code = excluded.code, name = excluded.name, "
                    "status = excluded.status, updated_at = excluded.updated_at",
                    (
                        course.target_id,
                        course.code,
                        course.name,
                        course.status,
                        course.created_at,
                        course.updated_at,
                    ),
                )
                ledger.record_snapshot_import(
                    snapshot,
                    legacy_key=course.legacy_key,
                    target_table="courses",
                    target_id=course.target_id,
                    details={
                        "kind": "course",
                        "legacy_id": course.raw_legacy_id,
                        "raw": dict(course.raw),
                    },
                    imported_at=imported_at,
                )
            add_tally(counters["courses"], disposition)

            link_key = "{}/semester_course".format(course.legacy_key)
            link_target = "{}|{}".format(course.semester_id, course.target_id)
            disposition = _ledger_disposition(
                connection,
                ledger,
                snapshot,
                legacy_key=link_key,
                target_table="semester_courses",
                target_id=link_target,
                existence_sql=(
                    "SELECT 1 FROM semester_courses "
                    "WHERE semester_id = ? AND course_id = ?"
                ),
                existence_params=(course.semester_id, course.target_id),
            )
            if disposition != "matched":
                connection.execute(
                    "INSERT INTO semester_courses "
                    "(semester_id, course_id, credits_milli, instructor, "
                    "enrollment_status) VALUES (?, ?, NULL, '', ?) "
                    "ON CONFLICT(semester_id, course_id) DO UPDATE SET "
                    "enrollment_status = excluded.enrollment_status",
                    (
                        course.semester_id,
                        course.target_id,
                        _enrollment_status(course.status),
                    ),
                )
                ledger.record_snapshot_import(
                    snapshot,
                    legacy_key=link_key,
                    target_table="semester_courses",
                    target_id=link_target,
                    details={
                        "kind": "semester_course",
                        "legacy_semester": course.semester_label,
                        "credits_milli": None,
                    },
                    imported_at=imported_at,
                )
            add_tally(counters["semester_courses"], disposition)

            for topic in course.topics:
                disposition = _ledger_disposition(
                    connection,
                    ledger,
                    snapshot,
                    legacy_key=topic.legacy_key,
                    target_table="topics",
                    target_id=topic.target_id,
                    existence_sql="SELECT 1 FROM topics WHERE id = ?",
                    existence_params=(topic.target_id,),
                )
                if disposition != "matched":
                    connection.execute(
                        "INSERT INTO topics "
                        "(id, course_id, name, normalized_name, position, status, "
                        "confidence, raw_import_status, created_at, updated_at, "
                        "deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "course_id = excluded.course_id, name = excluded.name, "
                        "normalized_name = excluded.normalized_name, "
                        "position = excluded.position, status = excluded.status, "
                        "confidence = excluded.confidence, "
                        "raw_import_status = excluded.raw_import_status, "
                        "updated_at = excluded.updated_at",
                        (
                            topic.target_id,
                            course.target_id,
                            topic.name,
                            topic.normalized_name,
                            topic.position,
                            topic.status,
                            topic.confidence,
                            topic.raw_status,
                            topic.created_at,
                            topic.updated_at,
                        ),
                    )
                    ledger.record_snapshot_import(
                        snapshot,
                        legacy_key=topic.legacy_key,
                        target_table="topics",
                        target_id=topic.target_id,
                        details={
                            "kind": "topic",
                            "course_legacy_key": course.legacy_key,
                            "raw": dict(topic.raw),
                        },
                        imported_at=imported_at,
                    )
                add_tally(counters["topics"], disposition)

        active_legacy_id = _text(data.get("active_course_id"))
        if active_legacy_id:
            active_target_id = active_lookup.get(active_legacy_id)
            if active_target_id is None:
                issues.append(
                    ImportIssue(
                        severity="warning",
                        code="unresolved_active_course",
                        message=(
                            "active_course_id {!r} does not match an explicit "
                            "legacy course id."
                        ).format(active_legacy_id),
                        legacy_key="active_course_id",
                    )
                )
            else:
                setting_key = "active_course_id"
                disposition = _ledger_disposition(
                    connection,
                    ledger,
                    snapshot,
                    legacy_key=setting_key,
                    target_table="app_settings",
                    target_id=setting_key,
                    existence_sql="SELECT 1 FROM app_settings WHERE key = ?",
                    existence_params=(setting_key,),
                )
                if disposition != "matched":
                    connection.execute(
                        "INSERT INTO app_settings (key, value_json, updated_at) "
                        "VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                        "value_json = excluded.value_json, "
                        "updated_at = excluded.updated_at",
                        (
                            setting_key,
                            json.dumps(active_target_id),
                            imported_at,
                        ),
                    )
                    ledger.record_snapshot_import(
                        snapshot,
                        legacy_key=setting_key,
                        target_table="app_settings",
                        target_id=setting_key,
                        details={
                            "kind": "active_course_setting",
                            "legacy_active_course_id": active_legacy_id,
                            "target_course_id": active_target_id,
                        },
                        imported_at=imported_at,
                    )
                add_tally(counters["settings"], disposition)

        # TOCTOU guard: a source change during the transaction aborts everything.
        source_sha256(snapshot)

    # Legacy courses.json has no credit authority. Keep credits NULL rather than
    # inventing values; reconciliation can fill them from approved sources.
    if prepared:
        issues.append(
            ImportIssue(
                severity="info",
                code="credits_deferred",
                message=(
                    "Legacy courses.json has no authoritative credit field; "
                    "semester_courses.credits_milli remains NULL."
                ),
            )
        )

    return CourseTopicImportResult(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        semesters=freeze_tally(counters["semesters"]),
        courses=freeze_tally(counters["courses"]),
        semester_courses=freeze_tally(counters["semester_courses"]),
        topics=freeze_tally(counters["topics"]),
        settings=freeze_tally(counters["settings"]),
        deferred_document_links=deferred_document_links,
        issues=tuple(issues),
    )


__all__ = (
    "CourseTopicImportResult",
    "import_courses_and_topics",
)
