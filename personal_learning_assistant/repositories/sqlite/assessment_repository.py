"""Read-only Phase 4.2 SQLite repository for Assessments + Assessment Topics.

SQLite remains a shadow backend.  This adapter reconstructs legacy-visible
assessment semantics from the Phase 3 relational schema and migration ledger,
while using the *actual* SQLite relationships for course/topic ownership.  It
never opens a database implicitly and rejects every write.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from personal_learning_assistant.repositories.interfaces import AssessmentState


ASSESSMENT_SOURCE_PATH = "data/assessments.json"
COURSE_SOURCE_PATH = "data/courses.json"
_REQUIRED_TABLES = {
    "migration_imports",
    "courses",
    "topics",
    "assessments",
    "assessment_topics",
}


class SQLiteAssessmentRepositoryError(RuntimeError):
    """Base error for Phase 4.2 SQLite assessment reads."""


class SQLiteAssessmentRepositorySchemaError(SQLiteAssessmentRepositoryError):
    """Raised when the supplied connection lacks the Phase 3 schema."""


class SQLiteAssessmentRepositoryDataError(SQLiteAssessmentRepositoryError):
    """Raised when SQLite rows and migration evidence cannot be reconciled."""


class SQLiteAssessmentRepositoryReadOnlyError(SQLiteAssessmentRepositoryError):
    """Raised when a caller attempts a Phase 4.2 SQLite write."""


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


def _parse_object(raw: Any, *, context: str) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SQLiteAssessmentRepositoryDataError(
            "Invalid migration ledger details for {}.".format(context)
        ) from error
    if not isinstance(value, dict):
        raise SQLiteAssessmentRepositoryDataError(
            "Migration ledger details must be an object for {}.".format(context)
        )
    return value


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _legacy_number_from_scaled(value: Any, scale: int):
    if value is None:
        return None
    integer = int(value)
    if integer % scale == 0:
        return integer // scale
    return integer / float(scale)


def _source_version(rows: Sequence[Mapping[str, Any]]) -> Any:
    versions = {
        str(row.get("source_version", ""))
        for row in rows
        if str(row.get("source_version", ""))
    }
    if not versions:
        return None
    if len(versions) != 1:
        raise SQLiteAssessmentRepositoryDataError(
            "Latest assessment source hash has conflicting source versions."
        )
    only = next(iter(versions))
    return int(only) if only.isdigit() else only


class SQLiteAssessmentRepository:
    """Read-only assessment adapter over an explicitly supplied SQLite DB."""

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
            raise SQLiteAssessmentRepositorySchemaError(
                "Phase 3 assessment tables are missing: {}".format(
                    ", ".join(missing)
                )
            )

    @staticmethod
    def _kind(row: Mapping[str, Any]) -> str:
        details = row.get("details")
        return str(details.get("kind", "")) if isinstance(details, Mapping) else ""

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
            row["details"] = _parse_object(
                row["details_json"], context=str(row.get("legacy_key", ""))
            )
        return tuple(rows)

    def _latest_source_rows(self, source_path: str) -> Tuple[Dict[str, Any], ...]:
        rows = self._source_rows(source_path)
        if not rows:
            return ()
        latest_hash = str(rows[-1]["source_hash"])
        # Source order within one imported snapshot is insertion/rowid order.
        return tuple(
            sorted(
                (row for row in rows if str(row["source_hash"]) == latest_hash),
                key=lambda row: int(row["ledger_rowid"]),
            )
        )

    @staticmethod
    def _raw_assessment(row: Mapping[str, Any]) -> Dict[str, Any]:
        details = row.get("details")
        raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise SQLiteAssessmentRepositoryDataError(
                "Raw assessment evidence must be an object for {}.".format(
                    row.get("legacy_key", "")
                )
            )
        return deepcopy(raw)

    def _row_by_id(self, table: str, target_id: str) -> Dict[str, Any]:
        if table not in {"assessments", "assessment_topics", "topics"}:
            raise SQLiteAssessmentRepositoryDataError(
                "Unsupported Phase 4.2 target table: {}".format(table)
            )
        rows = _fetch_dicts(
            self.connection,
            "SELECT * FROM {} WHERE id = ?".format(table),
            (target_id,),
        )
        if not rows:
            raise SQLiteAssessmentRepositoryDataError(
                "Migration ledger target is missing: {}:{}".format(table, target_id)
            )
        return rows[0]

    def _course_identity_maps(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        rows = self._latest_source_rows(COURSE_SOURCE_PATH)
        target_to_legacy: Dict[str, str] = {}
        target_to_key: Dict[str, str] = {}
        for row in rows:
            if row.get("target_table") != "courses" or self._kind(row) != "course":
                continue
            details = row["details"]
            raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
            if not isinstance(raw, Mapping):
                raw = {}
            legacy_id = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id"))
            if not legacy_id:
                key = str(row.get("legacy_key", ""))
                if key.startswith("course:id:"):
                    legacy_id = key[len("course:id:") :]
                elif key.startswith("course:code:"):
                    legacy_id = _raw_text(raw.get("code"))
            target = str(row["target_id"])
            target_to_legacy[target] = legacy_id
            target_to_key[target] = str(row["legacy_key"])
        return target_to_legacy, target_to_key

    def _semantic_snapshot(self) -> Dict[str, Any]:
        ledger_rows = self._latest_source_rows(ASSESSMENT_SOURCE_PATH)
        if not ledger_rows:
            return {
                "source_version": None,
                "source_hash": None,
                "assessment_catalogue": (),
                "assessment_order": (),
                "assessment_statuses": (),
                "course_relationships": (),
                "assessment_topics": (),
                "assessment_topic_order": (),
                "raw_records": (),
                "raw_identities": (),
                "resolved_topic_relationships": (),
                "deferred_course_credits": (),
                "aliases_supported": False,
                "anomalies": ("no data/assessments.json migration ledger evidence",),
                "state": {"version": 2, "assessments": []},
            }

        source_hash = str(ledger_rows[0]["source_hash"])
        source_version = _source_version(ledger_rows)
        assessment_ledgers = [
            row
            for row in ledger_rows
            if row.get("target_table") == "assessments"
            and self._kind(row) == "assessment"
        ]
        topic_ledgers = [
            row
            for row in ledger_rows
            if row.get("target_table") == "assessment_topics"
            and self._kind(row) == "assessment_topic_raw_label"
        ]

        course_target_to_legacy, _ = self._course_identity_maps()
        anomalies: List[str] = []
        assessment_target_to_legacy: Dict[str, str] = {}
        assessment_key_to_legacy: Dict[str, str] = {}
        prepared_assessments: List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], str]] = []

        for ledger in assessment_ledgers:
            target = self._row_by_id("assessments", str(ledger["target_id"]))
            details = ledger["details"]
            raw = self._raw_assessment(ledger)
            legacy_id = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id"))
            if not legacy_id:
                key = str(ledger.get("legacy_key", ""))
                legacy_id = key[len("assessment:id:") :] if key.startswith("assessment:id:") else key
            target_id = str(ledger["target_id"])
            assessment_target_to_legacy[target_id] = legacy_id
            assessment_key_to_legacy[str(ledger["legacy_key"])] = legacy_id
            prepared_assessments.append((ledger, target, raw, legacy_id))

            if target.get("deleted_at") is not None:
                anomalies.append(
                    "assessment {} is soft-deleted although it exists in the latest legacy snapshot".format(
                        legacy_id
                    )
                )

            actual_course_target = str(target.get("course_id", ""))
            actual_course_legacy = course_target_to_legacy.get(actual_course_target, "")
            expected_course_target = _raw_text(details.get("target_course_id"))
            expected_course_legacy = _raw_text(details.get("legacy_course_id"))
            if not actual_course_legacy:
                anomalies.append(
                    "assessment {} points to SQLite course {} outside the latest courses import".format(
                        legacy_id, actual_course_target or "<missing>"
                    )
                )
            if expected_course_target and actual_course_target != expected_course_target:
                anomalies.append(
                    "assessment {} course relationship differs from migration evidence".format(
                        legacy_id
                    )
                )
            if expected_course_legacy and actual_course_legacy != expected_course_legacy:
                anomalies.append(
                    "assessment {} resolves to legacy course {!r}; ledger expected {!r}".format(
                        legacy_id, actual_course_legacy, expected_course_legacy
                    )
                )

        topic_groups: Dict[str, List[Tuple[int, int, Dict[str, Any], Dict[str, Any]]]] = {}
        resolved_topic_relationships: List[Dict[str, Any]] = []
        raw_topic_positions: Dict[str, set] = {}

        for ledger in topic_ledgers:
            target = self._row_by_id("assessment_topics", str(ledger["target_id"]))
            details = ledger["details"]
            expected_assessment_key = _raw_text(details.get("assessment_legacy_key"))
            expected_assessment_legacy = assessment_key_to_legacy.get(
                expected_assessment_key, ""
            )
            actual_assessment_target = str(target.get("assessment_id", ""))
            actual_assessment_legacy = assessment_target_to_legacy.get(
                actual_assessment_target, ""
            )
            if not actual_assessment_legacy:
                anomalies.append(
                    "assessment topic {} points to assessment {} outside the latest assessment import".format(
                        ledger["legacy_key"], actual_assessment_target or "<missing>"
                    )
                )
            if actual_assessment_legacy != expected_assessment_legacy:
                anomalies.append(
                    "assessment topic {} relationship differs from migration evidence".format(
                        ledger["legacy_key"]
                    )
                )

            try:
                position = int(details.get("position", 0))
            except (TypeError, ValueError):
                position = -1
            if position < 0:
                anomalies.append(
                    "assessment topic {} has invalid source position {!r}".format(
                        ledger["legacy_key"], details.get("position")
                    )
                )
            positions = raw_topic_positions.setdefault(actual_assessment_legacy, set())
            if position in positions:
                anomalies.append(
                    "assessment {} has duplicate assessment-topic position {}".format(
                        actual_assessment_legacy or "<unknown>", position
                    )
                )
            positions.add(position)

            expected_raw = _raw_text(details.get("raw_label"))
            actual_raw = _raw_text(target.get("raw_label"))
            if expected_raw != actual_raw:
                anomalies.append(
                    "assessment topic {} raw_label differs from migration evidence".format(
                        ledger["legacy_key"]
                    )
                )

            topic_groups.setdefault(actual_assessment_legacy, []).append(
                (position, int(ledger["ledger_rowid"]), ledger, target)
            )

            linked_topic_id = target.get("topic_id")
            if linked_topic_id is not None:
                linked = self._row_by_id("topics", str(linked_topic_id))
                linked_course_target = str(linked.get("course_id", ""))
                linked_course_legacy = course_target_to_legacy.get(
                    linked_course_target, ""
                )
                assessment_row = next(
                    (
                        item[1]
                        for item in prepared_assessments
                        if str(item[1].get("id", "")) == actual_assessment_target
                    ),
                    None,
                )
                assessment_course_target = (
                    str(assessment_row.get("course_id", ""))
                    if assessment_row is not None
                    else ""
                )
                if linked.get("deleted_at") is not None:
                    anomalies.append(
                        "assessment topic {} links to soft-deleted topic {}".format(
                            ledger["legacy_key"], linked_topic_id
                        )
                    )
                if linked_course_target != assessment_course_target:
                    anomalies.append(
                        "assessment topic {} links across courses: assessment course {} vs topic course {}".format(
                            ledger["legacy_key"],
                            assessment_course_target or "<missing>",
                            linked_course_target or "<missing>",
                        )
                    )
                resolved_topic_relationships.append(
                    {
                        "assessment_id": actual_assessment_legacy,
                        "raw_label": actual_raw,
                        "sqlite_topic_id": str(linked_topic_id),
                        "topic_name": _raw_text(linked.get("name")),
                        "topic_course_id": linked_course_legacy,
                    }
                )

        visible_prepared_assessments = prepared_assessments[-200:]
        visible_assessment_ids = {item[3] for item in visible_prepared_assessments}

        catalogue: List[Dict[str, Any]] = []
        statuses: List[Tuple[str, str]] = []
        course_relationships: List[Tuple[str, str]] = []
        assessment_topics: List[Dict[str, Any]] = []
        topic_order: List[Tuple[str, Tuple[str, ...]]] = []
        raw_records: List[Dict[str, Any]] = []
        raw_identities: List[Dict[str, Any]] = []
        deferred_course_credits: List[Tuple[str, Any]] = []
        state_assessments: List[Dict[str, Any]] = []

        for ledger, target, raw, legacy_id in visible_prepared_assessments:
            actual_course_legacy = course_target_to_legacy.get(
                str(target.get("course_id", "")), ""
            )
            ordered_topics = sorted(
                topic_groups.get(legacy_id, ()), key=lambda item: (item[0], item[1])
            )
            labels = tuple(_raw_text(item[3].get("raw_label")) for item in ordered_topics)
            topic_order.append((legacy_id, labels))
            for position, _, _, topic_target in ordered_topics:
                assessment_topics.append(
                    {
                        "assessment_id": legacy_id,
                        "course_id": actual_course_legacy,
                        "position": position,
                        "raw_label": _raw_text(topic_target.get("raw_label")),
                    }
                )

            catalogue.append(
                {
                    "id": legacy_id,
                    "course_id": actual_course_legacy,
                    "type": _raw_text(target.get("assessment_type")),
                    "title": _raw_text(target.get("title")),
                    "status": _raw_text(target.get("status")),
                    "due_date": target.get("due_on"),
                    "due_time": target.get("due_time"),
                    "weightage_percent": _legacy_number_from_scaled(
                        target.get("weight_bps"), 100
                    ),
                    "total_marks": _legacy_number_from_scaled(
                        target.get("max_points_milli"), 1000
                    ),
                    "obtained_marks": _legacy_number_from_scaled(
                        target.get("earned_points_milli"), 1000
                    ),
                    "description": _raw_text(target.get("description")),
                }
            )
            statuses.append((legacy_id, _raw_text(target.get("status"))))
            course_relationships.append((legacy_id, actual_course_legacy))
            raw_records.append(deepcopy(raw))
            raw_identities.append(
                {
                    "position": len(raw_identities),
                    "raw_id": _raw_text(raw.get("id")),
                    "raw_course_id": _raw_text(raw.get("course_id")),
                    "raw_type": _raw_text(raw.get("type")),
                    "raw_assessment_type": _raw_text(raw.get("assessment_type")),
                    "raw_status": _raw_text(raw.get("status")),
                }
            )
            if raw.get("course_credits") not in (None, ""):
                deferred_course_credits.append((legacy_id, deepcopy(raw.get("course_credits"))))

            # Reconstruct a legacy-shaped shadow state without inventing fields
            # absent from the raw source.  This view is useful for repository
            # contract tests; parity itself uses the explicit projections above.
            payload = deepcopy(raw)
            payload["id"] = legacy_id
            payload["course_id"] = actual_course_legacy
            payload["title"] = _raw_text(target.get("title"))
            payload["status"] = _raw_text(target.get("status"))
            if "type" in payload:
                payload["type"] = _raw_text(target.get("assessment_type"))
            if "assessment_type" in payload:
                payload["assessment_type"] = _raw_text(target.get("assessment_type"))
            if "due_date" in payload:
                payload["due_date"] = target.get("due_on")
            if "due_on" in payload:
                payload["due_on"] = target.get("due_on")
            if "due_time" in payload:
                payload["due_time"] = target.get("due_time")
            if "weightage_percent" in payload:
                payload["weightage_percent"] = _legacy_number_from_scaled(
                    target.get("weight_bps"), 100
                )
            if "weight" in payload:
                payload["weight"] = _legacy_number_from_scaled(
                    target.get("weight_bps"), 100
                )
            if "total_marks" in payload:
                payload["total_marks"] = _legacy_number_from_scaled(
                    target.get("max_points_milli"), 1000
                )
            if "max_score" in payload:
                payload["max_score"] = _legacy_number_from_scaled(
                    target.get("max_points_milli"), 1000
                )
            if "obtained_marks" in payload:
                payload["obtained_marks"] = _legacy_number_from_scaled(
                    target.get("earned_points_milli"), 1000
                )
            if "score" in payload:
                payload["score"] = _legacy_number_from_scaled(
                    target.get("earned_points_milli"), 1000
                )
            if "description" in payload:
                payload["description"] = _raw_text(target.get("description"))
            if "created_at" in payload:
                payload["created_at"] = _raw_text(target.get("created_at"))
            if "updated_at" in payload:
                payload["updated_at"] = _raw_text(target.get("updated_at"))
            payload["topics"] = list(labels)
            state_assessments.append(payload)

        latest_assessment_targets = {
            str(row["target_id"]) for row in assessment_ledgers
        }
        latest_topic_targets = {str(row["target_id"]) for row in topic_ledgers}
        all_source_rows = self._source_rows(ASSESSMENT_SOURCE_PATH)
        historical_assessment_targets = {
            str(row["target_id"])
            for row in all_source_rows
            if row.get("target_table") == "assessments"
            and self._kind(row) == "assessment"
        }
        historical_topic_targets = {
            str(row["target_id"])
            for row in all_source_rows
            if row.get("target_table") == "assessment_topics"
            and self._kind(row) == "assessment_topic_raw_label"
        }
        stale_assessments = tuple(
            sorted(
                target_id
                for target_id in historical_assessment_targets - latest_assessment_targets
                if self.connection.execute(
                    "SELECT 1 FROM assessments WHERE id = ? AND deleted_at IS NULL",
                    (target_id,),
                ).fetchone()
                is not None
            )
        )
        stale_topics = tuple(
            sorted(
                target_id
                for target_id in historical_topic_targets - latest_topic_targets
                if self.connection.execute(
                    "SELECT 1 FROM assessment_topics WHERE id = ?", (target_id,)
                ).fetchone()
                is not None
            )
        )
        if stale_assessments:
            anomalies.append(
                "live assessment rows remain from older data/assessments.json imports: {}".format(
                    ", ".join(stale_assessments)
                )
            )
        if stale_topics:
            anomalies.append(
                "assessment-topic rows remain from older data/assessments.json imports: {}".format(
                    ", ".join(stale_topics)
                )
            )

        return {
            "source_version": source_version,
            "source_hash": source_hash,
            "assessment_catalogue": tuple(catalogue),
            "assessment_order": tuple(item["id"] for item in catalogue),
            "assessment_statuses": tuple(statuses),
            "course_relationships": tuple(course_relationships),
            "assessment_topics": tuple(assessment_topics),
            "assessment_topic_order": tuple(topic_order),
            "raw_records": tuple(raw_records),
            "raw_identities": tuple(raw_identities),
            "resolved_topic_relationships": tuple(
                item
                for item in resolved_topic_relationships
                if item["assessment_id"] in visible_assessment_ids
            ),
            "deferred_course_credits": tuple(deferred_course_credits),
            "aliases_supported": False,
            "anomalies": tuple(anomalies),
            "state": {"version": 2, "assessments": state_assessments[-200:]},
        }

    def parity_snapshot(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        snapshot = self._semantic_snapshot()
        if self.connection.total_changes != before:
            raise SQLiteAssessmentRepositoryDataError(
                "SQLite assessment read unexpectedly changed database state."
            )
        return deepcopy(snapshot)

    def load_state(self) -> AssessmentState:
        return deepcopy(self.parity_snapshot()["state"])

    def integrity_checks(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        integrity = tuple(
            str(row[0])
            for row in self.connection.execute("PRAGMA integrity_check").fetchall()
        )
        foreign_keys = tuple(
            tuple(row)
            for row in self.connection.execute("PRAGMA foreign_key_check").fetchall()
        )
        if self.connection.total_changes != before:
            raise SQLiteAssessmentRepositoryDataError(
                "SQLite integrity checks unexpectedly changed database state."
            )
        return {
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "pass": integrity == ("ok",) and not foreign_keys,
        }

    def save_state(self, state: AssessmentState) -> AssessmentState:
        raise SQLiteAssessmentRepositoryReadOnlyError(
            "Phase 4.2 SQLite assessment repository is read-only; legacy JSON remains authoritative."
        )


__all__ = (
    "ASSESSMENT_SOURCE_PATH",
    "COURSE_SOURCE_PATH",
    "SQLiteAssessmentRepository",
    "SQLiteAssessmentRepositoryDataError",
    "SQLiteAssessmentRepositoryError",
    "SQLiteAssessmentRepositoryReadOnlyError",
    "SQLiteAssessmentRepositorySchemaError",
)
