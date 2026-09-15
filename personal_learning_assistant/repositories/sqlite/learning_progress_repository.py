"""Read-only Phase 4.6 SQLite repository for Learning Memory + Progress.

SQLite remains shadow state.  The repository requires an explicitly supplied
``sqlite3.Connection`` and never opens a database by path.  Migration ledger
rows are used only to identify current imported evidence and raw provenance;
live relational rows are read independently and validated so ledger evidence
cannot hide structural corruption.
"""

from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MEMORY_SOURCE_PATH = "data/learning_memory.json"
PROGRESS_SOURCE_PATH = "data/course_progress_history.json"
COURSE_SOURCE_PATH = "data/courses.json"
_REQUIRED_TABLES = {
    "migration_imports",
    "courses",
    "topics",
    "learning_memory_entries",
    "topic_progress_events",
    "progress_snapshots",
}


class SQLiteLearningProgressRepositoryError(RuntimeError):
    """Base error for Phase 4.6 SQLite shadow reads."""


class SQLiteLearningProgressRepositorySchemaError(SQLiteLearningProgressRepositoryError):
    """Raised when required Phase 3 tables are missing."""


class SQLiteLearningProgressRepositoryDataError(SQLiteLearningProgressRepositoryError):
    """Raised when migration evidence cannot be interpreted safely."""


class SQLiteLearningProgressRepositoryReadOnlyError(SQLiteLearningProgressRepositoryError):
    """Raised for every unsupported SQLite mutation attempt."""


def _fetch_dicts(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] = (),
) -> Tuple[Dict[str, Any], ...]:
    cursor = connection.execute(sql, tuple(params))
    columns = tuple(item[0] for item in cursor.description or ())
    return tuple(
        {columns[index]: value for index, value in enumerate(tuple(row))}
        for row in cursor.fetchall()
    )


def _parse_details(raw: Any, *, context: str) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SQLiteLearningProgressRepositoryDataError(
            "Invalid migration details for {}.".format(context)
        ) from error
    if not isinstance(value, dict):
        raise SQLiteLearningProgressRepositoryDataError(
            "Migration details must be an object for {}.".format(context)
        )
    return value


def _json_value(raw: Any, *, field: str) -> Any:
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SQLiteLearningProgressRepositoryDataError(
            "Invalid JSON stored in {}.".format(field)
        ) from error


def _kind(row: Mapping[str, Any]) -> str:
    details = row.get("details")
    return str(details.get("kind", "")) if isinstance(details, Mapping) else ""


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _source_version(rows: Sequence[Mapping[str, Any]]) -> Any:
    values = {
        str(row.get("source_version", ""))
        for row in rows
        if str(row.get("source_version", ""))
    }
    if not values:
        return None
    if len(values) != 1:
        raise SQLiteLearningProgressRepositoryDataError(
            "Latest source hash has conflicting source versions."
        )
    value = next(iter(values))
    return int(value) if value.isdigit() else value


def _course_id_from_legacy_key(key: str) -> str:
    if key.startswith("course:id:"):
        return key[len("course:id:") :]
    if key.startswith("course:code:"):
        return key[len("course:code:") :]
    return ""


def _scope_course_from_key(key: str) -> str:
    match = re.match(r"^scope:course:(.*?)/kind:", key)
    return match.group(1) if match else ""


def _snapshot_course_from_key(key: str) -> str:
    match = re.match(r"^course:(.*?)/date:", key)
    return match.group(1) if match else ""


class SQLiteLearningProgressRepository:
    """Read-only adapter over the Phase 3 structured learning/progress tables."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an open sqlite3.Connection")
        self.connection = connection
        self._validate_schema()

    def _validate_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise SQLiteLearningProgressRepositorySchemaError(
                "Phase 3 learning/progress tables are missing: {}".format(
                    ", ".join(missing)
                )
            )

    def _source_rows(self, source_path: str) -> Tuple[Dict[str, Any], ...]:
        rows = list(
            _fetch_dicts(
                self.connection,
                "SELECT rowid AS ledger_rowid, source_hash, source_version, "
                "legacy_key, target_table, target_id, imported_at, details_json "
                "FROM migration_imports "
                "WHERE source_path = ? AND source_type = 'legacy_json' "
                "ORDER BY imported_at, rowid",
                (source_path,),
            )
        )
        for row in rows:
            row["details"] = _parse_details(
                row["details_json"], context=str(row.get("legacy_key", ""))
            )
        return tuple(rows)

    def _latest_source_rows(self, source_path: str) -> Tuple[Dict[str, Any], ...]:
        rows = self._source_rows(source_path)
        if not rows:
            return ()
        latest = max(rows, key=lambda row: (str(row.get("imported_at", "")), int(row["ledger_rowid"])))
        latest_hash = str(latest.get("source_hash", ""))
        return tuple(
            sorted(
                (row for row in rows if str(row.get("source_hash", "")) == latest_hash),
                key=lambda row: int(row["ledger_rowid"]),
            )
        )

    def _course_maps(self) -> Tuple[Dict[str, str], Dict[str, str], Tuple[str, ...]]:
        target_to_legacy: Dict[str, str] = {}
        key_to_target: Dict[str, str] = {}
        anomalies: List[str] = []
        seen_legacy: Dict[str, str] = {}
        for row in self._latest_source_rows(COURSE_SOURCE_PATH):
            if row.get("target_table") != "courses" or _kind(row) != "course":
                continue
            target = str(row.get("target_id", ""))
            key = str(row.get("legacy_key", ""))
            details = row["details"]
            raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
            if not isinstance(raw, Mapping):
                raw = {}
            legacy = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id")) or _course_id_from_legacy_key(key)
            actual = self.connection.execute(
                "SELECT id, deleted_at FROM courses WHERE id = ?", (target,)
            ).fetchone()
            if actual is None:
                anomalies.append("course ledger target {} is missing".format(target))
            elif actual[1] is not None:
                anomalies.append("course ledger target {} is soft-deleted".format(target))
            target_to_legacy[target] = legacy
            key_to_target[key] = target
            folded = legacy.casefold()
            if folded:
                previous = seen_legacy.get(folded)
                if previous is not None and previous != target:
                    anomalies.append(
                        "duplicate legacy course identity {!r} maps to {} and {}".format(
                            legacy, previous, target
                        )
                    )
                seen_legacy[folded] = target
        return target_to_legacy, key_to_target, tuple(anomalies)

    def _topic_projection(self) -> Tuple[Tuple[Dict[str, Any], ...], Dict[str, Dict[str, Any]], Tuple[str, ...]]:
        target_to_course_legacy, course_key_to_target, course_anomalies = self._course_maps()
        anomalies = list(course_anomalies)
        projections: List[Dict[str, Any]] = []
        by_target: Dict[str, Dict[str, Any]] = {}
        seen_identity: Dict[Tuple[str, str], str] = {}
        for row in self._latest_source_rows(COURSE_SOURCE_PATH):
            if row.get("target_table") != "topics" or _kind(row) != "topic":
                continue
            target = str(row.get("target_id", ""))
            details = row["details"]
            raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
            if not isinstance(raw, Mapping):
                raw = {}
            course_key = _raw_text(details.get("course_legacy_key"))
            expected_course_target = course_key_to_target.get(course_key, "")
            legacy_course = target_to_course_legacy.get(expected_course_target, "")
            legacy_name = _raw_text(raw.get("name")) or _raw_text(details.get("legacy_name"))
            actual = self.connection.execute(
                "SELECT id, course_id, name, normalized_name, position, status, "
                "confidence, raw_import_status, deleted_at FROM topics WHERE id = ?",
                (target,),
            ).fetchone()
            if actual is None:
                anomalies.append("topic ledger target {} is missing".format(target))
                continue
            if actual[8] is not None:
                anomalies.append("topic ledger target {} is soft-deleted".format(target))
            actual_course = str(actual[1])
            if expected_course_target and actual_course != expected_course_target:
                anomalies.append(
                    "topic {} belongs to course {} but ledger expects {}".format(
                        target, actual_course, expected_course_target
                    )
                )
            projection = {
                "target_id": target,
                "legacy_course_id": legacy_course,
                "legacy_name": legacy_name or _raw_text(actual[2]),
                "actual_name": _raw_text(actual[2]),
                "normalized_name": _raw_text(actual[3]),
                "position": int(actual[4]),
                "status": _raw_text(actual[5]),
                "confidence": 0 if actual[6] is None else int(actual[6]),
                "raw_import_status": actual[7],
                "course_target_id": actual_course,
            }
            projections.append(projection)
            by_target[target] = projection
            identity = (legacy_course.casefold(), projection["legacy_name"].casefold())
            previous = seen_identity.get(identity)
            if identity[0] and identity[1] and previous is not None and previous != target:
                anomalies.append(
                    "duplicate legacy topic identity {!r}/{!r} maps to {} and {}".format(
                        legacy_course, projection["legacy_name"], previous, target
                    )
                )
            seen_identity[identity] = target
        projections.sort(key=lambda item: (item["legacy_course_id"].casefold(), item["position"], item["legacy_name"].casefold()))
        return tuple(projections), by_target, tuple(anomalies)

    def _memory_snapshot(self) -> Dict[str, Any]:
        latest = self._latest_source_rows(MEMORY_SOURCE_PATH)
        all_rows = self._source_rows(MEMORY_SOURCE_PATH)
        topics, topics_by_target, topic_anomalies = self._topic_projection()
        target_to_course_legacy, _, course_anomalies = self._course_maps()
        anomalies: List[str] = list(topic_anomalies) + list(course_anomalies)
        if not latest:
            return {
                "source_hash": None,
                "source_version": None,
                "entries": (),
                "events": (),
                "historical_entries": (),
                "historical_events": (),
                "anomalies": ("no data/learning_memory.json migration ledger evidence",),
            }
        source_hash = str(latest[0].get("source_hash", ""))
        source_version = _source_version(latest)
        entry_ledgers = [
            row for row in latest
            if row.get("target_table") == "learning_memory_entries"
            and _kind(row) == "learning_memory_entry"
        ]
        event_ledgers = [
            row for row in latest
            if row.get("target_table") == "topic_progress_events"
            and _kind(row) == "topic_progress_event_from_learning_memory"
        ]

        key_targets: Dict[str, str] = {}
        current_entry_ids = set()
        entries: List[Dict[str, Any]] = []
        entry_target_to_projection: Dict[str, Dict[str, Any]] = {}
        for ledger in entry_ledgers:
            key = str(ledger.get("legacy_key", ""))
            target = str(ledger.get("target_id", ""))
            previous = key_targets.get(key)
            if previous is not None and previous != target:
                anomalies.append(
                    "duplicate memory legacy identity {} maps to {} and {}".format(key, previous, target)
                )
            key_targets[key] = target
            current_entry_ids.add(target)
            details = ledger["details"]
            actual = self.connection.execute(
                "SELECT id, scope_type, scope_id, kind, topic_id, raw_topic, memory_text, "
                "source_entity_type, source_entity_id, created_at, updated_at, archived_at "
                "FROM learning_memory_entries WHERE id = ?",
                (target,),
            ).fetchone()
            if actual is None:
                anomalies.append("memory ledger target {} is missing".format(target))
                continue
            if actual[11] is not None:
                anomalies.append("current memory target {} is archived".format(target))
            expected_scope_type = _raw_text(details.get("scope_type"))
            expected_scope_id = _raw_text(details.get("scope_id"))
            actual_scope_id = _raw_text(actual[2])
            if expected_scope_type and _raw_text(actual[1]) != expected_scope_type:
                anomalies.append("memory {} scope_type differs from migration evidence".format(target))
            if expected_scope_id and actual_scope_id != expected_scope_id:
                anomalies.append("memory {} scope_id differs from migration evidence".format(target))
            raw_course_id = _scope_course_from_key(key)
            if actual_scope_id:
                actual_legacy_course = target_to_course_legacy.get(actual_scope_id, "")
                if raw_course_id and actual_legacy_course.casefold() != raw_course_id.casefold():
                    anomalies.append(
                        "memory {} is owned by legacy course {!r} instead of {!r}".format(
                            target, actual_legacy_course, raw_course_id
                        )
                    )
            elif _raw_text(actual[1]) == "course":
                anomalies.append("course-scoped memory {} has no scope_id".format(target))

            topic_target = _raw_text(actual[4])
            if topic_target:
                topic = topics_by_target.get(topic_target)
                if topic is None:
                    anomalies.append("memory {} points to topic {} outside current topic import".format(target, topic_target))
                elif actual_scope_id and topic["course_target_id"] != actual_scope_id:
                    anomalies.append("memory {} topic belongs to a different course".format(target))
            expected_topic = _raw_text(details.get("topic_id"))
            if expected_topic and topic_target != expected_topic:
                anomalies.append("memory {} topic relationship differs from migration evidence".format(target))

            projection = {
                "legacy_key": key,
                "target_id": target,
                "scope_type": _raw_text(actual[1]),
                "scope_id": actual_scope_id or None,
                "raw_course_id": raw_course_id,
                "kind": _raw_text(actual[3]),
                "topic_id": topic_target or None,
                "raw_topic": _raw_text(actual[5]),
                "memory_text": _raw_text(actual[6]),
                "source_entity_type": actual[7],
                "source_entity_id": actual[8],
                "created_at": _raw_text(actual[9]),
                "updated_at": _raw_text(actual[10]),
                "raw": deepcopy(details.get("raw")),
            }
            entries.append(projection)
            entry_target_to_projection[target] = projection

        event_key_targets: Dict[str, str] = {}
        current_event_ids = set()
        events: List[Dict[str, Any]] = []
        for ledger in event_ledgers:
            key = str(ledger.get("legacy_key", ""))
            target = str(ledger.get("target_id", ""))
            previous = event_key_targets.get(key)
            if previous is not None and previous != target:
                anomalies.append(
                    "duplicate progress-event legacy identity {} maps to {} and {}".format(key, previous, target)
                )
            event_key_targets[key] = target
            current_event_ids.add(target)
            details = ledger["details"]
            actual = self.connection.execute(
                "SELECT id, topic_id, event_type, previous_status, new_status, confidence, "
                "evidence_type, evidence_id, occurred_at, note "
                "FROM topic_progress_events WHERE id = ?",
                (target,),
            ).fetchone()
            if actual is None:
                anomalies.append("topic-progress ledger target {} is missing".format(target))
                continue
            evidence_id = _raw_text(actual[7])
            evidence_entry = entry_target_to_projection.get(evidence_id)
            if _raw_text(actual[6]) != "learning_memory_entries" or evidence_entry is None:
                anomalies.append("topic-progress event {} has invalid memory evidence ownership".format(target))
            topic_target = _raw_text(actual[1])
            topic = topics_by_target.get(topic_target)
            if topic is None:
                anomalies.append("topic-progress event {} points to missing/stale topic {}".format(target, topic_target))
            elif evidence_entry and evidence_entry.get("scope_id") and topic["course_target_id"] != evidence_entry["scope_id"]:
                anomalies.append("topic-progress event {} crosses memory course ownership".format(target))
            if _raw_text(details.get("topic_id")) and topic_target != _raw_text(details.get("topic_id")):
                anomalies.append("topic-progress event {} topic differs from migration evidence".format(target))
            if _raw_text(details.get("evidence_id")) and evidence_id != _raw_text(details.get("evidence_id")):
                anomalies.append("topic-progress event {} evidence target differs from migration evidence".format(target))
            events.append(
                {
                    "legacy_key": key,
                    "target_id": target,
                    "topic_id": topic_target,
                    "event_type": _raw_text(actual[2]),
                    "previous_status": actual[3],
                    "new_status": actual[4],
                    "confidence": actual[5],
                    "evidence_type": actual[6],
                    "evidence_id": evidence_id,
                    "occurred_at": _raw_text(actual[8]),
                    "note": _raw_text(actual[9]),
                    "raw": deepcopy(details.get("raw")),
                }
            )

        all_entry_ledger_ids = {
            str(row.get("target_id", ""))
            for row in all_rows
            if row.get("target_table") == "learning_memory_entries"
            and _kind(row) == "learning_memory_entry"
        }
        all_event_ledger_ids = {
            str(row.get("target_id", ""))
            for row in all_rows
            if row.get("target_table") == "topic_progress_events"
            and _kind(row) == "topic_progress_event_from_learning_memory"
        }
        live_entry_ids = {
            str(row[0]) for row in self.connection.execute(
                "SELECT id FROM learning_memory_entries WHERE archived_at IS NULL"
            ).fetchall()
        }
        live_event_ids = {
            str(row[0]) for row in self.connection.execute(
                "SELECT id FROM topic_progress_events"
            ).fetchall()
        }
        unledgered_entries = sorted(live_entry_ids - all_entry_ledger_ids)
        unledgered_events = sorted(live_event_ids - all_event_ledger_ids)
        if unledgered_entries:
            anomalies.append("unledgered live learning_memory_entries: {}".format(", ".join(unledgered_entries)))
        if unledgered_events:
            anomalies.append("unledgered live topic_progress_events: {}".format(", ".join(unledgered_events)))

        historical_entries = tuple(sorted((live_entry_ids & all_entry_ledger_ids) - current_entry_ids))
        historical_events = tuple(sorted((live_event_ids & all_event_ledger_ids) - current_event_ids))
        entries.sort(key=lambda item: item["legacy_key"])
        events.sort(key=lambda item: item["legacy_key"])
        return {
            "source_hash": source_hash,
            "source_version": source_version,
            "entries": tuple(entries),
            "events": tuple(events),
            "historical_entries": historical_entries,
            "historical_events": historical_events,
            "anomalies": tuple(anomalies),
        }

    def _progress_snapshot(self) -> Dict[str, Any]:
        latest = self._latest_source_rows(PROGRESS_SOURCE_PATH)
        all_rows = self._source_rows(PROGRESS_SOURCE_PATH)
        target_to_course_legacy, _, course_anomalies = self._course_maps()
        anomalies: List[str] = list(course_anomalies)
        if not latest:
            return {
                "source_hash": None,
                "source_version": None,
                "snapshots": (),
                "historical_snapshots": (),
                "anomalies": ("no data/course_progress_history.json migration ledger evidence",),
            }
        source_hash = str(latest[0].get("source_hash", ""))
        source_version = _source_version(latest)
        ledgers = [
            row for row in latest
            if row.get("target_table") == "progress_snapshots"
            and _kind(row) == "course_progress_snapshot"
        ]
        key_targets: Dict[str, str] = {}
        current_ids = set()
        snapshots: List[Dict[str, Any]] = []
        for ledger in ledgers:
            key = str(ledger.get("legacy_key", ""))
            target = str(ledger.get("target_id", ""))
            previous = key_targets.get(key)
            if previous is not None and previous != target:
                anomalies.append(
                    "duplicate progress-snapshot legacy identity {} maps to {} and {}".format(key, previous, target)
                )
            key_targets[key] = target
            current_ids.add(target)
            details = ledger["details"]
            actual = self.connection.execute(
                "SELECT id, course_id, snapshot_date, counts_json, score_json, engine_version, created_at "
                "FROM progress_snapshots WHERE id = ?",
                (target,),
            ).fetchone()
            if actual is None:
                anomalies.append("progress snapshot ledger target {} is missing".format(target))
                continue
            actual_course = _raw_text(actual[1])
            expected_course = _raw_text(details.get("course_id"))
            if expected_course and actual_course != expected_course:
                anomalies.append("progress snapshot {} course differs from migration evidence".format(target))
            course_legacy = target_to_course_legacy.get(actual_course, "")
            key_course = _snapshot_course_from_key(key)
            if key_course and course_legacy.casefold() != key_course.casefold():
                anomalies.append(
                    "progress snapshot {} belongs to legacy course {!r} instead of {!r}".format(
                        target, course_legacy, key_course
                    )
                )
            exists = self.connection.execute(
                "SELECT deleted_at FROM courses WHERE id = ?", (actual_course,)
            ).fetchone()
            if exists is None or exists[0] is not None:
                anomalies.append("progress snapshot {} owns a missing/deleted course".format(target))
            counts_value = _json_value(actual[3], field="progress_snapshots.counts_json")
            scores_value = _json_value(actual[4], field="progress_snapshots.score_json")
            raw_value = details.get("raw")
            if isinstance(raw_value, Mapping):
                if _raw_text(raw_value.get("date")) and _raw_text(actual[2]) != _raw_text(raw_value.get("date")):
                    anomalies.append("progress snapshot {} date differs from raw migration evidence".format(target))
                if counts_value.get("mastered_topics") != raw_value.get("mastered_topics"):
                    anomalies.append("progress snapshot {} mastered_topics differs from raw migration evidence".format(target))
                if counts_value.get("total_topics") != raw_value.get("total_topics"):
                    anomalies.append("progress snapshot {} total_topics differs from raw migration evidence".format(target))
                if scores_value.get("progress_percent") != raw_value.get("progress_percent"):
                    anomalies.append("progress snapshot {} progress_percent differs from raw migration evidence".format(target))
            expected_engine = _raw_text(details.get("engine_version"))
            if expected_engine and _raw_text(actual[5]) != expected_engine:
                anomalies.append("progress snapshot {} engine version differs from migration evidence".format(target))
            snapshots.append(
                {
                    "legacy_key": key,
                    "ledger_rowid": int(ledger["ledger_rowid"]),
                    "target_id": target,
                    "legacy_course_id": key_course or course_legacy,
                    "course_target_id": actual_course,
                    "snapshot_date": _raw_text(actual[2]),
                    "counts": counts_value,
                    "scores": scores_value,
                    "engine_version": _raw_text(actual[5]),
                    "created_at": _raw_text(actual[6]),
                    "raw": deepcopy(raw_value),
                }
            )

        all_ledger_ids = {
            str(row.get("target_id", ""))
            for row in all_rows
            if row.get("target_table") == "progress_snapshots"
            and _kind(row) == "course_progress_snapshot"
        }
        live_ids = {
            str(row[0]) for row in self.connection.execute("SELECT id FROM progress_snapshots").fetchall()
        }
        unledgered = sorted(live_ids - all_ledger_ids)
        if unledgered:
            anomalies.append("unledgered live progress_snapshots: {}".format(", ".join(unledgered)))
        historical = tuple(sorted((live_ids & all_ledger_ids) - current_ids))
        snapshots.sort(key=lambda item: (item["legacy_course_id"].casefold(), item["ledger_rowid"]))
        return {
            "source_hash": source_hash,
            "source_version": source_version,
            "snapshots": tuple(snapshots),
            "historical_snapshots": historical,
            "anomalies": tuple(anomalies),
        }

    @staticmethod
    def _summary_from_topics(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        valid = ("not_started", "learning", "weak", "review", "practiced", "mastered")
        counts = {name: 0 for name in valid}
        for topic in items:
            status = str(topic.get("status") or "not_started")
            if status in counts:
                counts[status] += 1
        total = len(items)
        mastered = counts["mastered"]
        return {
            "total_topics": total,
            "mastered_topics": mastered,
            "progress_percent": round((mastered / total) * 100) if total else 0,
            "counts": counts,
            "weak_topics": [item["legacy_name"] for item in items if item.get("status") == "weak"],
            "missing_topics": [item["legacy_name"] for item in items if item.get("status") == "not_started"],
        }

    def _current_progress_snapshot(self) -> Dict[str, Any]:
        topics, _, topic_anomalies = self._topic_projection()
        target_to_course_legacy, _, course_anomalies = self._course_maps()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for topic in topics:
            grouped.setdefault(str(topic["legacy_course_id"]), []).append(dict(topic))
        courses = []
        summaries: Dict[str, Any] = {}
        for target_id, legacy_id in sorted(target_to_course_legacy.items(), key=lambda item: item[1].casefold()):
            row = self.connection.execute(
                "SELECT code, name, deleted_at FROM courses WHERE id = ?", (target_id,)
            ).fetchone()
            if row is None or row[2] is not None:
                continue
            course_topics = sorted(grouped.get(legacy_id, []), key=lambda item: item["position"])
            courses.append(
                {
                    "id": legacy_id,
                    "code": _raw_text(row[0]),
                    "name": _raw_text(row[1]),
                    "topics": tuple(
                        {
                            "name": item["legacy_name"],
                            "status": item["status"],
                            "confidence": item["confidence"],
                        }
                        for item in course_topics
                    ),
                }
            )
            summaries[legacy_id] = self._summary_from_topics(course_topics)
        return {
            "courses": tuple(courses),
            "summaries": summaries,
            "anomalies": tuple(list(topic_anomalies) + list(course_anomalies)),
        }

    def parity_snapshot(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        snapshot = {
            "memory": self._memory_snapshot(),
            "progress_history": self._progress_snapshot(),
            "current_progress": self._current_progress_snapshot(),
        }
        if self.connection.total_changes != before:
            raise SQLiteLearningProgressRepositoryReadOnlyError(
                "Phase 4.6 parity read changed SQLite state."
            )
        return snapshot

    def integrity_checks(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = tuple(self.connection.execute("PRAGMA foreign_key_check").fetchall())
        if self.connection.total_changes != before:
            raise SQLiteLearningProgressRepositoryReadOnlyError(
                "SQLite integrity checks changed state."
            )
        return {"integrity_check": integrity, "foreign_key_check": foreign_keys}

    def save_memory(self, *_args, **_kwargs):
        raise SQLiteLearningProgressRepositoryReadOnlyError(
            "SQLite learning-memory writes are disabled during Phase 4.6."
        )

    def save_progress_history(self, *_args, **_kwargs):
        raise SQLiteLearningProgressRepositoryReadOnlyError(
            "SQLite progress-history writes are disabled during Phase 4.6."
        )

    def record_progress_snapshot(self, *_args, **_kwargs):
        raise SQLiteLearningProgressRepositoryReadOnlyError(
            "SQLite progress snapshot writes are disabled during Phase 4.6."
        )


__all__ = (
    "SQLiteLearningProgressRepository",
    "SQLiteLearningProgressRepositoryDataError",
    "SQLiteLearningProgressRepositoryError",
    "SQLiteLearningProgressRepositoryReadOnlyError",
    "SQLiteLearningProgressRepositorySchemaError",
)
