"""Idempotent Phase 3 importer for learning memory and academic progress.

This is a shadow migration adapter only. It reads verified
``learning_memory.json`` and ``course_progress_history.json`` snapshots and
writes portable memory/progress evidence into an explicit temporary SQLite
database while JSON remains authoritative until the Phase 4 cutover gate is
approved.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

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


MEMORY_SOURCE_PATH = "data/learning_memory.json"
PROGRESS_SOURCE_PATH = "data/course_progress_history.json"
COURSE_SOURCE_PATH = "data/courses.json"

REQUIRED_TABLES = (
    "migration_imports",
    "courses",
    "topics",
    "learning_memory_entries",
    "topic_progress_events",
    "progress_snapshots",
)

PROGRESS_ENGINE_VERSION = "legacy_course_progress_history_v1"


@dataclass(frozen=True)
class LearningProgressReviewItem:
    source_path: str
    legacy_key: str
    scope_type: str
    raw_course_id: str
    raw_topic: str
    target_course_id: Optional[str]
    target_topic_id: Optional[str]
    reason: str


@dataclass(frozen=True)
class LearningProgressImportResult:
    memory_source_path: str
    memory_source_hash: str
    progress_source_path: str
    progress_source_hash: str
    learning_memory_entries: ImportTally
    topic_progress_events: ImportTally
    progress_snapshots: ImportTally
    unresolved_courses: int
    unresolved_topics: int
    deferred_activity_records: int
    review_items: Tuple[LearningProgressReviewItem, ...]
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        tallies = (
            self.learning_memory_entries,
            self.topic_progress_events,
            self.progress_snapshots,
        )
        return sum(item.created + item.updated for item in tallies)

    @property
    def review_required_items(self) -> int:
        return len(self.review_items)


# Compatibility names for callers using the complete feature title.
LearningMemoryProgressImportResult = LearningProgressImportResult
AcademicProgressImportResult = LearningProgressImportResult


@dataclass(frozen=True)
class _Scope:
    scope_type: str
    scope_id: Optional[str]
    raw_course_id: str
    legacy_prefix: str


@dataclass(frozen=True)
class _PreparedMemoryEntry:
    legacy_key: str
    target_id: str
    scope_type: str
    scope_id: Optional[str]
    kind: str
    topic_id: Optional[str]
    raw_topic: str
    memory_text: str
    source_entity_type: Optional[str]
    source_entity_id: Optional[str]
    created_at: str
    updated_at: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedTopicProgressEvent:
    legacy_key: str
    target_id: str
    topic_id: str
    event_type: str
    previous_status: Optional[str]
    new_status: Optional[str]
    confidence: Optional[int]
    evidence_type: str
    evidence_id: str
    occurred_at: str
    note: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedProgressSnapshot:
    legacy_key: str
    target_id: str
    course_id: str
    snapshot_date: str
    counts_json: str
    score_json: str
    engine_version: str
    created_at: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedLearningProgress:
    entries: Tuple[_PreparedMemoryEntry, ...]
    events: Tuple[_PreparedTopicProgressEvent, ...]
    snapshots: Tuple[_PreparedProgressSnapshot, ...]
    unresolved_courses: int
    unresolved_topics: int
    deferred_activity_records: int
    review_items: Tuple[LearningProgressReviewItem, ...]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_label(value: Any) -> str:
    return _clean_text(value).casefold()


def _timestamp(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _date_text(value: Any, *, field: str, legacy_key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LegacyImportDataError(
            "{} has no non-blank {}".format(legacy_key, field)
        )
    text = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise LegacyImportDataError(
            "{} field {} must use YYYY-MM-DD".format(legacy_key, field)
        )
    return text


def _list(value: Any, *, field: str, scope_key: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LegacyImportDataError(
            "{} field '{}' must be an array".format(scope_key, field)
        )
    return list(value)


def _dict(value: Any, *, field: str, scope_key: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LegacyImportDataError(
            "{} field '{}' must be an object".format(scope_key, field)
        )
    return value


def _json_dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _course_candidates(
    connection: sqlite3.Connection,
    legacy_key: str,
) -> Tuple[str, ...]:
    rows = connection.execute(
        "SELECT mi.legacy_key, mi.target_id "
        "FROM migration_imports AS mi "
        "JOIN courses AS c ON c.id = mi.target_id "
        "WHERE mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'courses' "
        "AND c.deleted_at IS NULL",
        (COURSE_SOURCE_PATH,),
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
    raw_course_id: str,
) -> Optional[str]:
    legacy_id = _clean_text(raw_course_id)
    if not legacy_id:
        return None

    lookup_keys = (
        "course:id:{}".format(legacy_id),
        "course:code:{}".format(legacy_id.casefold()),
    )
    for lookup_key in lookup_keys:
        candidates = _course_candidates(connection, lookup_key)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise LegacyImportDataError(
                "ambiguous imported course mapping for legacy course_id {!r}"
                .format(raw_course_id)
            )
    return None


def _resolve_topic_target(
    connection: sqlite3.Connection,
    *,
    course_id: Optional[str],
    raw_topic: str,
) -> Optional[str]:
    if not course_id:
        return None
    normalized = _normalized_label(raw_topic)
    if not normalized:
        return None

    rows = connection.execute(
        "SELECT DISTINCT t.id "
        "FROM topics AS t "
        "JOIN migration_imports AS mi ON mi.target_id = t.id "
        "WHERE t.course_id = ? "
        "AND t.normalized_name = ? "
        "AND t.deleted_at IS NULL "
        "AND mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'topics' "
        "ORDER BY t.id",
        (course_id, normalized, COURSE_SOURCE_PATH),
    ).fetchall()
    candidates = tuple(str(row[0]) for row in rows)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise LegacyImportDataError(
            "ambiguous imported topic mapping for {!r}".format(raw_topic)
        )
    return None


def _entry_key(scope: _Scope, kind: str, discriminator: str) -> str:
    return "{}/kind:{}/{}".format(scope.legacy_prefix, kind, discriminator)


def _topic_discriminator(raw_topic: str) -> str:
    normalized = _normalized_label(raw_topic)
    if not normalized:
        raise LegacyImportDataError("learning-memory topic must not be blank")
    return "topic:{}".format(normalized)


def _make_entry(
    snapshot: LegacySourceSnapshot,
    scope: _Scope,
    *,
    kind: str,
    discriminator: str,
    topic_id: Optional[str],
    raw_topic: str,
    memory_text: str,
    created_at: str,
    updated_at: str,
    raw: Mapping[str, Any],
    source_entity_type: Optional[str] = None,
    source_entity_id: Optional[str] = None,
) -> _PreparedMemoryEntry:
    legacy_key = _entry_key(scope, kind, discriminator)
    return _PreparedMemoryEntry(
        legacy_key=legacy_key,
        target_id=stable_target_id(
            snapshot.canonical_path,
            "learning_memory_entry",
            legacy_key,
        ),
        scope_type=scope.scope_type,
        scope_id=scope.scope_id,
        kind=kind,
        topic_id=topic_id,
        raw_topic=raw_topic,
        memory_text=memory_text,
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        created_at=created_at,
        updated_at=updated_at,
        raw=raw,
    )


def _make_topic_event(
    snapshot: LegacySourceSnapshot,
    entry: _PreparedMemoryEntry,
    *,
    event_type: str,
    new_status: str,
    occurred_at: str,
    raw: Mapping[str, Any],
) -> _PreparedTopicProgressEvent:
    if entry.topic_id is None:
        raise LegacyImportDataError(
            "cannot build topic progress event without a resolved topic"
        )
    legacy_key = "{}/topic_progress_event".format(entry.legacy_key)
    return _PreparedTopicProgressEvent(
        legacy_key=legacy_key,
        target_id=stable_target_id(
            snapshot.canonical_path,
            "topic_progress_event",
            legacy_key,
        ),
        topic_id=entry.topic_id,
        event_type=event_type,
        previous_status=None,
        new_status=new_status,
        confidence=None,
        evidence_type="learning_memory_entries",
        evidence_id=entry.target_id,
        occurred_at=occurred_at,
        note="Imported from legacy learning memory without changing topic status.",
        raw=raw,
    )


def _append_topic_entries(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    scope: _Scope,
    raw_topics: Iterable[Any],
    *,
    kind: str,
    new_status: str,
    imported_at: str,
    entries: List[_PreparedMemoryEntry],
    events: List[_PreparedTopicProgressEvent],
    review_items: List[LearningProgressReviewItem],
    issues: List[ImportIssue],
) -> Tuple[int, int]:
    unresolved_courses = 0
    unresolved_topics = 0
    seen = set()

    for position, raw_value in enumerate(raw_topics):
        raw_topic = _clean_text(raw_value)
        if not raw_topic:
            raise LegacyImportDataError(
                "{} {} topic at index {} is blank".format(
                    scope.legacy_prefix,
                    kind,
                    position,
                )
            )
        discriminator = _topic_discriminator(raw_topic)
        if discriminator in seen:
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="duplicate_learning_memory_topic",
                    message=(
                        "Duplicate learning-memory topic {!r} was represented "
                        "once in SQLite; the untouched JSON and ledger keep the raw source."
                    ).format(raw_topic),
                    legacy_key=_entry_key(scope, kind, discriminator),
                )
            )
            continue
        seen.add(discriminator)

        topic_id = _resolve_topic_target(
            connection,
            course_id=scope.scope_id,
            raw_topic=raw_topic,
        )
        entry = _make_entry(
            snapshot,
            scope,
            kind=kind,
            discriminator=discriminator,
            topic_id=topic_id,
            raw_topic=raw_topic,
            memory_text="",
            created_at=imported_at,
            updated_at=imported_at,
            raw={"topic": raw_topic, "position": position},
        )
        entries.append(entry)

        if scope.raw_course_id and scope.scope_id is None:
            unresolved_courses += 1
            review_items.append(
                LearningProgressReviewItem(
                    source_path=snapshot.canonical_path,
                    legacy_key=entry.legacy_key,
                    scope_type=scope.scope_type,
                    raw_course_id=scope.raw_course_id,
                    raw_topic=raw_topic,
                    target_course_id=None,
                    target_topic_id=None,
                    reason="unresolved_legacy_course_scope",
                )
            )
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="learning_memory_course_unresolved",
                    message=(
                        "Learning-memory course scope {!r} could not be linked "
                        "to a Fix 4 course; entry was preserved without a course FK."
                    ).format(scope.raw_course_id),
                    legacy_key=entry.legacy_key,
                )
            )
        elif topic_id is None:
            unresolved_topics += 1
            review_items.append(
                LearningProgressReviewItem(
                    source_path=snapshot.canonical_path,
                    legacy_key=entry.legacy_key,
                    scope_type=scope.scope_type,
                    raw_course_id=scope.raw_course_id,
                    raw_topic=raw_topic,
                    target_course_id=scope.scope_id,
                    target_topic_id=None,
                    reason="unresolved_learning_memory_topic",
                )
            )
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="learning_memory_topic_unresolved",
                    message=(
                        "Learning-memory topic {!r} was preserved as raw_topic "
                        "because exact Fix 4 topic resolution was unavailable."
                    ).format(raw_topic),
                    legacy_key=entry.legacy_key,
                )
            )
        else:
            events.append(
                _make_topic_event(
                    snapshot,
                    entry,
                    event_type="legacy_memory_{}_topic".format(kind.replace("_topic", "")),
                    new_status=new_status,
                    occurred_at=imported_at,
                    raw=entry.raw,
                )
            )

    return unresolved_courses, unresolved_topics


def _note_text_and_time(raw_note: Any, fallback: str, legacy_key: str) -> Tuple[str, str]:
    if isinstance(raw_note, str):
        return raw_note.strip(), fallback
    if isinstance(raw_note, dict):
        text = str(raw_note.get("text") or "").strip()
        return text, _timestamp(raw_note.get("created_at"), fallback)
    raise LegacyImportDataError(
        "{} note must be a string or object".format(legacy_key)
    )


def _append_notes(
    snapshot: LegacySourceSnapshot,
    scope: _Scope,
    raw_notes: Iterable[Any],
    *,
    imported_at: str,
    entries: List[_PreparedMemoryEntry],
) -> None:
    for position, raw_note in enumerate(raw_notes):
        note_key = _entry_key(scope, "note", "index:{}".format(position))
        text, created_at = _note_text_and_time(raw_note, imported_at, note_key)
        if not text:
            raise LegacyImportDataError("{} is blank".format(note_key))
        entries.append(
            _make_entry(
                snapshot,
                scope,
                kind="note",
                discriminator="index:{}".format(position),
                topic_id=None,
                raw_topic="",
                memory_text=text,
                created_at=created_at,
                updated_at=created_at,
                raw={"note": raw_note, "position": position},
            )
        )


def _append_activities(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    scope: _Scope,
    raw_activities: Iterable[Any],
    *,
    imported_at: str,
    entries: List[_PreparedMemoryEntry],
    review_items: List[LearningProgressReviewItem],
    issues: List[ImportIssue],
) -> int:
    deferred = 0
    for position, raw_activity in enumerate(raw_activities):
        activity_key = _entry_key(scope, "activity", "index:{}".format(position))
        if not isinstance(raw_activity, dict):
            raise LegacyImportDataError(
                "{} must be an object".format(activity_key)
            )
        question = _clean_text(raw_activity.get("question"))
        if not question:
            raise LegacyImportDataError(
                "{} has no question/text field".format(activity_key)
            )
        raw_topic = _clean_text(raw_activity.get("topic"))
        topic_id = _resolve_topic_target(
            connection,
            course_id=scope.scope_id,
            raw_topic=raw_topic,
        ) if raw_topic else None
        created_at = _timestamp(raw_activity.get("time"), imported_at)
        entries.append(
            _make_entry(
                snapshot,
                scope,
                kind="activity",
                discriminator="index:{}".format(position),
                topic_id=topic_id,
                raw_topic=raw_topic,
                memory_text=question,
                source_entity_type="legacy_recent_activity",
                source_entity_id=None,
                created_at=created_at,
                updated_at=created_at,
                raw={"activity": raw_activity, "position": position},
            )
        )
        deferred += 1
        if raw_topic and topic_id is None:
            review_items.append(
                LearningProgressReviewItem(
                    source_path=snapshot.canonical_path,
                    legacy_key=activity_key,
                    scope_type=scope.scope_type,
                    raw_course_id=scope.raw_course_id,
                    raw_topic=raw_topic,
                    target_course_id=scope.scope_id,
                    target_topic_id=None,
                    reason="activity_topic_unresolved",
                )
            )
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="learning_activity_topic_unresolved",
                    message=(
                        "Recent-activity topic {!r} was preserved but not linked "
                        "because exact topic resolution was unavailable."
                    ).format(raw_topic),
                    legacy_key=activity_key,
                )
            )
        issues.append(
            ImportIssue(
                severity="info",
                code="learning_activity_imported_as_memory_entry",
                message=(
                    "Legacy recent activity was preserved as a learning-memory "
                    "entry; it was not converted into a study session."
                ),
                legacy_key=activity_key,
            )
        )
    return deferred


def _memory_scopes(
    connection: sqlite3.Connection,
    data: Mapping[str, Any],
) -> Tuple[_Scope, ...]:
    scopes: List[_Scope] = [
        _Scope(
            scope_type="global",
            scope_id=None,
            raw_course_id="",
            legacy_prefix="scope:global",
        )
    ]

    course_memory = _dict(
        data.get("course_memory", {}),
        field="course_memory",
        scope_key="learning_memory",
    )
    for raw_course_id in sorted(course_memory.keys(), key=lambda item: str(item).casefold()):
        course_text = _clean_text(raw_course_id)
        if not course_text:
            raise LegacyImportDataError("learning-memory course scope is blank")
        target = _resolve_course_target(connection, course_text)
        scopes.append(
            _Scope(
                scope_type="course" if target else "legacy_course",
                scope_id=target,
                raw_course_id=course_text,
                legacy_prefix="scope:course:{}".format(course_text),
            )
        )
    return tuple(scopes)


def _scope_payload(data: Mapping[str, Any], scope: _Scope) -> Mapping[str, Any]:
    if scope.scope_type == "global":
        return data
    course_memory = _dict(
        data.get("course_memory", {}),
        field="course_memory",
        scope_key="learning_memory",
    )
    return _dict(
        course_memory.get(scope.raw_course_id, {}),
        field=scope.raw_course_id,
        scope_key="course_memory",
    )


def _prepare_learning_memory(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    data: Mapping[str, Any],
    imported_at: str,
    issues: List[ImportIssue],
) -> Tuple[Tuple[_PreparedMemoryEntry, ...], Tuple[_PreparedTopicProgressEvent, ...], int, int, int, Tuple[LearningProgressReviewItem, ...]]:
    entries: List[_PreparedMemoryEntry] = []
    events: List[_PreparedTopicProgressEvent] = []
    review_items: List[LearningProgressReviewItem] = []
    unresolved_courses = 0
    unresolved_topics = 0
    deferred_activity_records = 0

    for scope in _memory_scopes(connection, data):
        payload = _scope_payload(data, scope)
        weak_topics = _list(payload.get("weak_topics", []), field="weak_topics", scope_key=scope.legacy_prefix)
        mastered_topics = _list(payload.get("mastered_topics", []), field="mastered_topics", scope_key=scope.legacy_prefix)
        notes = _list(payload.get("notes", []), field="notes", scope_key=scope.legacy_prefix)
        recent_activity = payload.get("recent_activity", payload.get("activities", []))
        activities = _list(recent_activity, field="recent_activity", scope_key=scope.legacy_prefix)

        course_count, topic_count = _append_topic_entries(
            connection,
            snapshot,
            scope,
            weak_topics,
            kind="weak_topic",
            new_status="weak",
            imported_at=imported_at,
            entries=entries,
            events=events,
            review_items=review_items,
            issues=issues,
        )
        unresolved_courses += course_count
        unresolved_topics += topic_count

        course_count, topic_count = _append_topic_entries(
            connection,
            snapshot,
            scope,
            mastered_topics,
            kind="mastered_topic",
            new_status="mastered",
            imported_at=imported_at,
            entries=entries,
            events=events,
            review_items=review_items,
            issues=issues,
        )
        unresolved_courses += course_count
        unresolved_topics += topic_count

        _append_notes(
            snapshot,
            scope,
            notes,
            imported_at=imported_at,
            entries=entries,
        )
        deferred_activity_records += _append_activities(
            connection,
            snapshot,
            scope,
            activities,
            imported_at=imported_at,
            entries=entries,
            review_items=review_items,
            issues=issues,
        )

    version = data.get("version")
    if version not in (None, 1, 2, "1", "2"):
        issues.append(
            ImportIssue(
                severity="warning",
                code="unexpected_learning_memory_version",
                message=(
                    "learning_memory.json version {!r} was imported without rewriting the source."
                ).format(version),
            )
        )

    return (
        tuple(entries),
        tuple(events),
        unresolved_courses,
        unresolved_topics,
        deferred_activity_records,
        tuple(review_items),
    )


def _progress_history(data: Mapping[str, Any]) -> Mapping[str, Any]:
    history = data.get("history", {})
    if not isinstance(history, dict):
        raise LegacyImportDataError(
            "course_progress_history.json field 'history' must be an object"
        )
    return history


def _prepare_progress_snapshots(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    data: Mapping[str, Any],
    imported_at: str,
    review_items: List[LearningProgressReviewItem],
    issues: List[ImportIssue],
) -> Tuple[Tuple[_PreparedProgressSnapshot, ...], int]:
    snapshots: List[_PreparedProgressSnapshot] = []
    unresolved_courses = 0

    for raw_course_id, raw_items in sorted(_progress_history(data).items(), key=lambda item: str(item[0]).casefold()):
        course_text = _clean_text(raw_course_id)
        if not course_text:
            raise LegacyImportDataError("progress-history course key is blank")
        if not isinstance(raw_items, list):
            raise LegacyImportDataError(
                "progress history for course {!r} must be an array".format(raw_course_id)
            )

        course_id = _resolve_course_target(connection, course_text)
        if course_id is None:
            unresolved_courses += len(raw_items)
            issue_key = "course:{}".format(course_text)
            review_items.append(
                LearningProgressReviewItem(
                    source_path=snapshot.canonical_path,
                    legacy_key=issue_key,
                    scope_type="course_progress_history",
                    raw_course_id=course_text,
                    raw_topic="",
                    target_course_id=None,
                    target_topic_id=None,
                    reason="unresolved_progress_history_course",
                )
            )
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="progress_history_course_unresolved",
                    message=(
                        "Progress-history course {!r} could not be linked to a Fix 4 course; snapshots were not guessed."
                    ).format(course_text),
                    legacy_key=issue_key,
                )
            )
            continue

        seen_dates = set()
        for position, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise LegacyImportDataError(
                    "progress item {} for course {!r} must be an object".format(
                        position,
                        course_text,
                    )
                )
            legacy_key = "course:{}/snapshot:index:{}".format(course_text, position)
            snapshot_date = _date_text(
                raw_item.get("date"),
                field="date",
                legacy_key=legacy_key,
            )
            if snapshot_date in seen_dates:
                raise LegacyImportDataError(
                    "duplicate progress snapshot date {} for course {!r}".format(
                        snapshot_date,
                        course_text,
                    )
                )
            seen_dates.add(snapshot_date)

            embedded_course = _clean_text(raw_item.get("course_id"))
            if embedded_course and embedded_course != course_text:
                issues.append(
                    ImportIssue(
                        severity="warning",
                        code="progress_history_course_key_mismatch",
                        message=(
                            "Progress-history key {!r} and embedded course_id {!r} differ; key mapping was used."
                        ).format(course_text, embedded_course),
                        legacy_key=legacy_key,
                    )
                )

            counts = {
                "mastered_topics": raw_item.get("mastered_topics"),
                "total_topics": raw_item.get("total_topics"),
            }
            scores = {
                "progress_percent": raw_item.get("progress_percent"),
            }
            stable_key = "course:{}/date:{}/engine:{}".format(
                course_text,
                snapshot_date,
                PROGRESS_ENGINE_VERSION,
            )
            snapshots.append(
                _PreparedProgressSnapshot(
                    legacy_key=stable_key,
                    target_id=stable_target_id(
                        snapshot.canonical_path,
                        "progress_snapshot",
                        stable_key,
                    ),
                    course_id=course_id,
                    snapshot_date=snapshot_date,
                    counts_json=_json_dumps(counts),
                    score_json=_json_dumps(scores),
                    engine_version=PROGRESS_ENGINE_VERSION,
                    created_at=imported_at,
                    raw=dict(raw_item),
                )
            )

    version = data.get("version")
    if version not in (None, 1, "1"):
        issues.append(
            ImportIssue(
                severity="warning",
                code="unexpected_progress_history_version",
                message=(
                    "course_progress_history.json version {!r} was imported without rewriting the source."
                ).format(version),
            )
        )

    return tuple(snapshots), unresolved_courses


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


def _record_entry(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot: LegacySourceSnapshot,
    entry: _PreparedMemoryEntry,
    imported_at: str,
) -> str:
    disposition = _ledger_disposition(
        connection,
        ledger,
        snapshot,
        legacy_key=entry.legacy_key,
        target_table="learning_memory_entries",
        target_id=entry.target_id,
        existence_sql="SELECT 1 FROM learning_memory_entries WHERE id = ?",
        existence_params=(entry.target_id,),
    )
    if disposition != "matched":
        connection.execute(
            "INSERT INTO learning_memory_entries "
            "(id, scope_type, scope_id, kind, topic_id, raw_topic, memory_text, "
            "source_entity_type, source_entity_id, created_at, updated_at, archived_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL) "
            "ON CONFLICT(id) DO UPDATE SET "
            "scope_type = excluded.scope_type, scope_id = excluded.scope_id, "
            "kind = excluded.kind, topic_id = excluded.topic_id, "
            "raw_topic = excluded.raw_topic, memory_text = excluded.memory_text, "
            "source_entity_type = excluded.source_entity_type, "
            "source_entity_id = excluded.source_entity_id, "
            "updated_at = excluded.updated_at, archived_at = NULL",
            (
                entry.target_id,
                entry.scope_type,
                entry.scope_id,
                entry.kind,
                entry.topic_id,
                entry.raw_topic,
                entry.memory_text,
                entry.source_entity_type,
                entry.source_entity_id,
                entry.created_at,
                entry.updated_at,
            ),
        )
        ledger.record_snapshot_import(
            snapshot,
            legacy_key=entry.legacy_key,
            target_table="learning_memory_entries",
            target_id=entry.target_id,
            details={
                "kind": "learning_memory_entry",
                "scope_type": entry.scope_type,
                "scope_id": entry.scope_id,
                "raw_course_id": entry.raw.get("raw_course_id", ""),
                "entry_kind": entry.kind,
                "raw_topic": entry.raw_topic,
                "topic_id": entry.topic_id,
                "raw": dict(entry.raw),
            },
            imported_at=imported_at,
        )
    return disposition


def _record_event(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot: LegacySourceSnapshot,
    event: _PreparedTopicProgressEvent,
    imported_at: str,
) -> str:
    disposition = _ledger_disposition(
        connection,
        ledger,
        snapshot,
        legacy_key=event.legacy_key,
        target_table="topic_progress_events",
        target_id=event.target_id,
        existence_sql="SELECT 1 FROM topic_progress_events WHERE id = ?",
        existence_params=(event.target_id,),
    )
    if disposition != "matched":
        connection.execute(
            "INSERT INTO topic_progress_events "
            "(id, topic_id, event_type, previous_status, new_status, confidence, "
            "evidence_type, evidence_id, occurred_at, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "topic_id = excluded.topic_id, event_type = excluded.event_type, "
            "previous_status = excluded.previous_status, "
            "new_status = excluded.new_status, confidence = excluded.confidence, "
            "evidence_type = excluded.evidence_type, "
            "evidence_id = excluded.evidence_id, occurred_at = excluded.occurred_at, "
            "note = excluded.note",
            (
                event.target_id,
                event.topic_id,
                event.event_type,
                event.previous_status,
                event.new_status,
                event.confidence,
                event.evidence_type,
                event.evidence_id,
                event.occurred_at,
                event.note,
            ),
        )
        ledger.record_snapshot_import(
            snapshot,
            legacy_key=event.legacy_key,
            target_table="topic_progress_events",
            target_id=event.target_id,
            details={
                "kind": "topic_progress_event_from_learning_memory",
                "event_type": event.event_type,
                "new_status": event.new_status,
                "topic_id": event.topic_id,
                "evidence_id": event.evidence_id,
                "raw": dict(event.raw),
            },
            imported_at=imported_at,
        )
    return disposition


def _record_snapshot(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot_source: LegacySourceSnapshot,
    snapshot: _PreparedProgressSnapshot,
    imported_at: str,
) -> str:
    disposition = _ledger_disposition(
        connection,
        ledger,
        snapshot_source,
        legacy_key=snapshot.legacy_key,
        target_table="progress_snapshots",
        target_id=snapshot.target_id,
        existence_sql="SELECT 1 FROM progress_snapshots WHERE id = ?",
        existence_params=(snapshot.target_id,),
    )
    if disposition != "matched":
        connection.execute(
            "INSERT INTO progress_snapshots "
            "(id, course_id, snapshot_date, counts_json, score_json, engine_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "course_id = excluded.course_id, snapshot_date = excluded.snapshot_date, "
            "counts_json = excluded.counts_json, score_json = excluded.score_json, "
            "engine_version = excluded.engine_version, created_at = excluded.created_at",
            (
                snapshot.target_id,
                snapshot.course_id,
                snapshot.snapshot_date,
                snapshot.counts_json,
                snapshot.score_json,
                snapshot.engine_version,
                snapshot.created_at,
            ),
        )
        ledger.record_snapshot_import(
            snapshot_source,
            legacy_key=snapshot.legacy_key,
            target_table="progress_snapshots",
            target_id=snapshot.target_id,
            details={
                "kind": "course_progress_snapshot",
                "course_id": snapshot.course_id,
                "snapshot_date": snapshot.snapshot_date,
                "engine_version": snapshot.engine_version,
                "raw": dict(snapshot.raw),
            },
            imported_at=imported_at,
        )
    return disposition


def import_learning_memory_and_progress(
    connection: sqlite3.Connection,
    memory_snapshot: LegacySourceSnapshot,
    progress_snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> LearningProgressImportResult:
    """Import verified learning-memory and progress-history snapshots.

    Both sources are imported in one transaction so the memory/progress evidence
    and their migration-ledger observations stay consistent.
    """
    ensure_tables(connection, REQUIRED_TABLES)
    if memory_snapshot.canonical_path != MEMORY_SOURCE_PATH:
        raise LegacyImportDataError(
            "learning-memory importer requires {}".format(MEMORY_SOURCE_PATH)
        )
    if progress_snapshot.canonical_path != PROGRESS_SOURCE_PATH:
        raise LegacyImportDataError(
            "progress importer requires {}".format(PROGRESS_SOURCE_PATH)
        )

    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")

    memory_data = load_verified_json(memory_snapshot, expected_kind="object")
    progress_data = load_verified_json(progress_snapshot, expected_kind="object")

    issues: List[ImportIssue] = []
    (
        entries,
        events,
        unresolved_memory_courses,
        unresolved_topics,
        deferred_activity_records,
        memory_review_items,
    ) = _prepare_learning_memory(
        connection,
        memory_snapshot,
        memory_data,
        imported_at,
        issues,
    )
    progress_review_items: List[LearningProgressReviewItem] = []
    snapshots, unresolved_progress_courses = _prepare_progress_snapshots(
        connection,
        progress_snapshot,
        progress_data,
        imported_at,
        progress_review_items,
        issues,
    )

    counters: Dict[str, Dict[str, int]] = {
        "learning_memory_entries": {},
        "topic_progress_events": {},
        "progress_snapshots": {},
    }
    ledger = MigrationImportLedger(connection)

    with transaction(connection, immediate=True):
        for entry in entries:
            add_tally(
                counters["learning_memory_entries"],
                _record_entry(
                    connection,
                    ledger,
                    memory_snapshot,
                    entry,
                    imported_at,
                ),
            )

        for event in events:
            add_tally(
                counters["topic_progress_events"],
                _record_event(
                    connection,
                    ledger,
                    memory_snapshot,
                    event,
                    imported_at,
                ),
            )

        for prepared_snapshot in snapshots:
            add_tally(
                counters["progress_snapshots"],
                _record_snapshot(
                    connection,
                    ledger,
                    progress_snapshot,
                    prepared_snapshot,
                    imported_at,
                ),
            )

        # TOCTOU guard: either source changing during the transaction aborts all writes.
        source_sha256(memory_snapshot)
        source_sha256(progress_snapshot)

    return LearningProgressImportResult(
        memory_source_path=memory_snapshot.canonical_path,
        memory_source_hash=memory_snapshot.source_hash,
        progress_source_path=progress_snapshot.canonical_path,
        progress_source_hash=progress_snapshot.source_hash,
        learning_memory_entries=freeze_tally(counters["learning_memory_entries"]),
        topic_progress_events=freeze_tally(counters["topic_progress_events"]),
        progress_snapshots=freeze_tally(counters["progress_snapshots"]),
        unresolved_courses=unresolved_memory_courses + unresolved_progress_courses,
        unresolved_topics=unresolved_topics,
        deferred_activity_records=deferred_activity_records,
        review_items=tuple(memory_review_items) + tuple(progress_review_items),
        issues=tuple(issues),
    )


def import_learning_memory(
    connection: sqlite3.Connection,
    memory_snapshot: LegacySourceSnapshot,
    progress_snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> LearningProgressImportResult:
    """Compatibility alias for the combined Fix 9 importer."""
    return import_learning_memory_and_progress(
        connection,
        memory_snapshot,
        progress_snapshot,
        imported_at=imported_at,
    )


def import_academic_progress(
    connection: sqlite3.Connection,
    memory_snapshot: LegacySourceSnapshot,
    progress_snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> LearningProgressImportResult:
    """Compatibility alias for the combined Fix 9 importer."""
    return import_learning_memory_and_progress(
        connection,
        memory_snapshot,
        progress_snapshot,
        imported_at=imported_at,
    )


def _markdown_cell(value: Any) -> str:
    return (
        str(value)
        .replace("|", "\\|")
        .replace("\r", "")
        .replace("\n", "<br>")
    )


def render_learning_progress_review_markdown(
    result: LearningProgressImportResult,
) -> str:
    """Render a portable review report without writing a file."""
    lines = [
        "# Learning Memory and Progress Review",
        "",
        "- Memory source: `{}`".format(_markdown_cell(result.memory_source_path)),
        "- Memory SHA-256: `{}`".format(result.memory_source_hash),
        "- Progress source: `{}`".format(_markdown_cell(result.progress_source_path)),
        "- Progress SHA-256: `{}`".format(result.progress_source_hash),
        "- Review-required items: {}".format(result.review_required_items),
        "- Unresolved courses: {}".format(result.unresolved_courses),
        "- Unresolved topics: {}".format(result.unresolved_topics),
        "",
    ]
    if not result.review_items:
        lines.append("No learning-memory/progress items require review.")
        return "\n".join(lines) + "\n"

    lines.extend(
        (
            "| Source | Scope | Legacy key | Course | Topic | Reason |",
            "|---|---|---|---|---|---|",
        )
    )
    for item in result.review_items:
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                _markdown_cell(item.source_path),
                _markdown_cell(item.scope_type),
                _markdown_cell(item.legacy_key),
                _markdown_cell(item.raw_course_id or "global"),
                _markdown_cell(item.raw_topic or "n/a"),
                _markdown_cell(item.reason),
            )
        )
    return "\n".join(lines) + "\n"


__all__ = (
    "AcademicProgressImportResult",
    "LearningMemoryProgressImportResult",
    "LearningProgressImportResult",
    "LearningProgressReviewItem",
    "import_academic_progress",
    "import_learning_memory",
    "import_learning_memory_and_progress",
    "render_learning_progress_review_markdown",
)
