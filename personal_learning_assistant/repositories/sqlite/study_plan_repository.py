"""Read-only Phase 4.7 SQLite repository for legacy study-plan shadow state.

SQLite remains shadow state.  The repository requires an explicitly supplied
``sqlite3.Connection`` and never opens or creates a database by path.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Sequence, Tuple


WEEKLY_SOURCE_PATH = "data/weekly_study_plans.json"
MULTI_SOURCE_PATH = "data/multi_course_weekly_plans.json"
INTELLIGENT_SOURCE_PATH = "data/intelligent_study_plans.json"
COURSE_SOURCE_PATH = "data/courses.json"
SOURCE_PATHS = (
    WEEKLY_SOURCE_PATH,
    MULTI_SOURCE_PATH,
    INTELLIGENT_SOURCE_PATH,
)

_REQUIRED_TABLES = {
    "migration_imports",
    "courses",
    "topics",
    "study_plans",
    "study_plan_items",
}


class SQLiteStudyPlanRepositoryError(RuntimeError):
    """Base error for Phase 4.7 SQLite study-plan reads."""


class SQLiteStudyPlanRepositorySchemaError(SQLiteStudyPlanRepositoryError):
    """Raised when the supplied connection lacks required Phase 3 tables."""


class SQLiteStudyPlanRepositoryDataError(SQLiteStudyPlanRepositoryError):
    """Raised when migration evidence cannot be parsed safely."""


class SQLiteStudyPlanRepositoryReadOnlyError(SQLiteStudyPlanRepositoryError):
    """Raised for every unsupported SQLite write attempt."""


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
        raise SQLiteStudyPlanRepositoryDataError(
            "Invalid migration details for {}.".format(context)
        ) from error
    if not isinstance(value, dict):
        raise SQLiteStudyPlanRepositoryDataError(
            "Migration details must be an object for {}.".format(context)
        )
    return value


def _text(value: Any) -> str:
    return "" if value is None else str(value)


class SQLiteStudyPlanRepository:
    """Read-only study-plan adapter over an explicit Phase 3 SQLite connection."""

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
            raise SQLiteStudyPlanRepositorySchemaError(
                "Phase 3 study-plan tables are missing: {}".format(
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
        latest_hash = str(rows[-1]["source_hash"])
        return tuple(
            row for row in rows if str(row.get("source_hash")) == latest_hash
        )

    @staticmethod
    def _kind(row: Mapping[str, Any]) -> str:
        details = row.get("details")
        return str(details.get("kind", "")) if isinstance(details, Mapping) else ""

    def _all_supported_ledgers(self) -> Tuple[Dict[str, Any], ...]:
        rows: List[Dict[str, Any]] = []
        for path in SOURCE_PATHS:
            rows.extend(self._source_rows(path))
        return tuple(rows)

    def _course_exists(self, course_id: str) -> bool:
        if not course_id:
            return False
        row = self.connection.execute(
            "SELECT 1 FROM courses WHERE id = ? AND deleted_at IS NULL",
            (course_id,),
        ).fetchone()
        return row is not None

    def _topic_row(self, topic_id: str):
        if not topic_id:
            return None
        return self.connection.execute(
            "SELECT id, course_id, deleted_at FROM topics WHERE id = ?",
            (topic_id,),
        ).fetchone()

    def _snapshot_for_source(self, source_path: str) -> Dict[str, Any]:
        current = self._latest_source_rows(source_path)
        all_rows = self._source_rows(source_path)
        if not current:
            return {
                "source_path": source_path,
                "present": False,
                "source_hash": None,
                "source_version": None,
                "plan_rows": (),
                "item_rows": (),
                "raw_plan_evidence": (),
                "historical_plan_rows": (),
                "historical_item_rows": (),
                "anomalies": (),
            }

        source_hash = str(current[0]["source_hash"])
        versions = {
            _text(row.get("source_version"))
            for row in current
            if _text(row.get("source_version"))
        }
        source_version: Any = None
        if len(versions) == 1:
            only = next(iter(versions))
            source_version = int(only) if only.isdigit() else only
        elif len(versions) > 1:
            raise SQLiteStudyPlanRepositoryDataError(
                "Latest {} ledger has conflicting source versions.".format(source_path)
            )

        plan_ledgers = [
            row for row in current
            if row.get("target_table") == "study_plans"
            and self._kind(row) == "study_plan"
        ]
        item_ledgers = [
            row for row in current
            if row.get("target_table") == "study_plan_items"
            and self._kind(row) == "study_plan_item"
        ]
        plan_target_by_key = {
            str(row["legacy_key"]): str(row["target_id"])
            for row in plan_ledgers
        }
        anomalies: List[str] = []

        # Duplicate current legacy identities must not be hidden by dictionary projection.
        for target_table, rows in (
            ("study_plans", plan_ledgers),
            ("study_plan_items", item_ledgers),
        ):
            seen: Dict[str, str] = {}
            for row in rows:
                key = str(row.get("legacy_key", ""))
                target = str(row.get("target_id", ""))
                previous = seen.get(key)
                if previous is not None and previous != target:
                    anomalies.append(
                        "duplicate current {} legacy identity {} maps to {} and {}".format(
                            target_table, key, previous, target
                        )
                    )
                seen[key] = target

        plan_rows: List[Dict[str, Any]] = []
        raw_plan_evidence: List[Dict[str, Any]] = []
        for ledger in plan_ledgers:
            target_id = str(ledger["target_id"])
            actual = self.connection.execute(
                "SELECT id, kind, horizon, starts_on, ends_on, requested_minutes, "
                "allocated_minutes, status, engine_name, engine_version, rationale, "
                "created_at, updated_at FROM study_plans WHERE id = ?",
                (target_id,),
            ).fetchone()
            if actual is None:
                anomalies.append(
                    "current study-plan ledger points to missing row {}".format(target_id)
                )
                continue
            details = ledger["details"]
            raw_plan = deepcopy(details.get("raw"))
            raw_plan_evidence.append(
                {
                    "legacy_key": str(ledger["legacy_key"]),
                    "raw": raw_plan,
                }
            )
            plan_rows.append(
                {
                    "legacy_key": str(ledger["legacy_key"]),
                    "target_id": target_id,
                    "kind": actual[1],
                    "horizon": actual[2],
                    "starts_on": actual[3],
                    "ends_on": actual[4],
                    "requested_minutes": actual[5],
                    "allocated_minutes": actual[6],
                    "status": actual[7],
                    "engine_name": actual[8],
                    "engine_version": actual[9],
                    "rationale": actual[10],
                    "created_at": actual[11],
                    "updated_at": actual[12],
                    "raw": raw_plan,
                }
            )

        item_rows: List[Dict[str, Any]] = []
        for ledger in item_ledgers:
            target_id = str(ledger["target_id"])
            actual = self.connection.execute(
                "SELECT id, plan_id, plan_date, ordinal, course_id, topic_id, "
                "assessment_id, resource_id, note_id, minutes, action, reason, "
                "score, status FROM study_plan_items WHERE id = ?",
                (target_id,),
            ).fetchone()
            if actual is None:
                anomalies.append(
                    "current study-plan-item ledger points to missing row {}".format(target_id)
                )
                continue
            details = ledger["details"]
            plan_key = _text(details.get("plan_legacy_key"))
            expected_plan_id = plan_target_by_key.get(plan_key, "")
            actual_plan_id = _text(actual[1])
            if expected_plan_id and actual_plan_id != expected_plan_id:
                anomalies.append(
                    "study-plan item {} belongs to the wrong plan".format(target_id)
                )

            expected_course = _text(details.get("target_course_id"))
            actual_course = _text(actual[4])
            if expected_course != actual_course:
                anomalies.append(
                    "study-plan item {} course relationship differs from migration evidence".format(
                        target_id
                    )
                )
            if actual_course and not self._course_exists(actual_course):
                anomalies.append(
                    "study-plan item {} points to missing/deleted course {}".format(
                        target_id, actual_course
                    )
                )

            expected_topic = _text(details.get("target_topic_id"))
            actual_topic = _text(actual[5])
            if expected_topic != actual_topic:
                anomalies.append(
                    "study-plan item {} topic relationship differs from migration evidence".format(
                        target_id
                    )
                )
            topic_row = self._topic_row(actual_topic) if actual_topic else None
            if actual_topic and topic_row is None:
                anomalies.append(
                    "study-plan item {} points to missing topic {}".format(
                        target_id, actual_topic
                    )
                )
            elif topic_row is not None:
                if topic_row[2] is not None:
                    anomalies.append(
                        "study-plan item {} points to soft-deleted topic {}".format(
                            target_id, actual_topic
                        )
                    )
                if actual_course and _text(topic_row[1]) != actual_course:
                    anomalies.append(
                        "study-plan item {} crosses course/topic ownership".format(target_id)
                    )

            if any(value is not None for value in actual[6:9]):
                anomalies.append(
                    "study-plan item {} unexpectedly links assessment/resource/note in Phase 4.7".format(
                        target_id
                    )
                )

            item_rows.append(
                {
                    "legacy_key": str(ledger["legacy_key"]),
                    "target_id": target_id,
                    "plan_legacy_key": plan_key,
                    "plan_id": actual_plan_id,
                    "plan_date": actual[2],
                    "ordinal": actual[3],
                    "raw_course_id": deepcopy(details.get("raw_course_id", "")),
                    "raw_topic": deepcopy(details.get("raw_topic", "")),
                    "course_id": actual[4],
                    "topic_id": actual[5],
                    "minutes": actual[9],
                    "action": actual[10],
                    "reason": actual[11],
                    "score": actual[12],
                    "status": actual[13],
                    "raw": deepcopy(details.get("raw")),
                }
            )

        current_plan_ids = {str(row["target_id"]) for row in plan_ledgers}
        current_item_ids = {str(row["target_id"]) for row in item_ledgers}
        historical_plan_ids = {
            str(row["target_id"])
            for row in all_rows
            if row.get("target_table") == "study_plans"
            and self._kind(row) == "study_plan"
            and str(row.get("source_hash")) != source_hash
        } - current_plan_ids
        historical_item_ids = {
            str(row["target_id"])
            for row in all_rows
            if row.get("target_table") == "study_plan_items"
            and self._kind(row) == "study_plan_item"
            and str(row.get("source_hash")) != source_hash
        } - current_item_ids

        historical_plans = tuple(
            _fetch_dicts(
                self.connection,
                "SELECT id, kind, status, engine_name, engine_version FROM study_plans "
                "WHERE id IN ({}) ORDER BY id".format(
                    ",".join("?" for _ in historical_plan_ids)
                ),
                tuple(sorted(historical_plan_ids)),
            )
        ) if historical_plan_ids else ()
        historical_items = tuple(
            _fetch_dicts(
                self.connection,
                "SELECT id, plan_id, plan_date, ordinal, status FROM study_plan_items "
                "WHERE id IN ({}) ORDER BY plan_id, plan_date, ordinal, id".format(
                    ",".join("?" for _ in historical_item_ids)
                ),
                tuple(sorted(historical_item_ids)),
            )
        ) if historical_item_ids else ()

        return {
            "source_path": source_path,
            "present": True,
            "source_hash": source_hash,
            "source_version": source_version,
            "plan_rows": tuple(plan_rows),
            "item_rows": tuple(item_rows),
            "raw_plan_evidence": tuple(raw_plan_evidence),
            "historical_plan_rows": historical_plans,
            "historical_item_rows": historical_items,
            "anomalies": tuple(anomalies),
        }

    def _unledgered_anomalies(self, source_snapshots: Mapping[str, Mapping[str, Any]]) -> Tuple[str, ...]:
        all_ledgers = self._all_supported_ledgers()
        evidenced_plan_ids = {
            str(row["target_id"])
            for row in all_ledgers
            if row.get("target_table") == "study_plans"
        }
        evidenced_item_ids = {
            str(row["target_id"])
            for row in all_ledgers
            if row.get("target_table") == "study_plan_items"
        }
        anomalies: List[str] = []
        for row in self.connection.execute("SELECT id FROM study_plans ORDER BY id").fetchall():
            plan_id = str(row[0])
            if plan_id not in evidenced_plan_ids:
                anomalies.append("unledgered live study_plan row {}".format(plan_id))
        for row in self.connection.execute("SELECT id FROM study_plan_items ORDER BY id").fetchall():
            item_id = str(row[0])
            if item_id not in evidenced_item_ids:
                anomalies.append("unledgered live study_plan_item row {}".format(item_id))
        return tuple(anomalies)

    def parity_snapshot(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        sources = {path: self._snapshot_for_source(path) for path in SOURCE_PATHS}
        global_anomalies = self._unledgered_anomalies(sources)
        if self.connection.total_changes != before:
            raise SQLiteStudyPlanRepositoryError(
                "Phase 4.7 parity read unexpectedly changed SQLite state."
            )
        return {
            "sources": sources,
            "global_anomalies": global_anomalies,
        }

    def integrity_checks(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        integrity = self.connection.execute("PRAGMA integrity_check").fetchall()
        foreign_keys = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        if self.connection.total_changes != before:
            raise SQLiteStudyPlanRepositoryError(
                "Integrity checks unexpectedly changed SQLite state."
            )
        return {
            "integrity_check": tuple(tuple(row) for row in integrity),
            "foreign_key_check": tuple(tuple(row) for row in foreign_keys),
        }

    def load_state(self):
        return deepcopy(self.parity_snapshot())

    def save_state(self, _state) -> None:
        raise SQLiteStudyPlanRepositoryReadOnlyError(
            "Phase 4.7 SQLite study-plan repository is read-only."
        )

    def save_weekly_store(self, _value) -> None:
        raise SQLiteStudyPlanRepositoryReadOnlyError(
            "Phase 4.7 SQLite study-plan repository is read-only."
        )

    def save_multi_course_store(self, _value) -> None:
        raise SQLiteStudyPlanRepositoryReadOnlyError(
            "Phase 4.7 SQLite study-plan repository is read-only."
        )

    def save_intelligent_store(self, _value) -> None:
        raise SQLiteStudyPlanRepositoryReadOnlyError(
            "Phase 4.7 SQLite study-plan repository is read-only."
        )


__all__ = (
    "INTELLIGENT_SOURCE_PATH",
    "MULTI_SOURCE_PATH",
    "SQLiteStudyPlanRepository",
    "SQLiteStudyPlanRepositoryDataError",
    "SQLiteStudyPlanRepositoryError",
    "SQLiteStudyPlanRepositoryReadOnlyError",
    "SQLiteStudyPlanRepositorySchemaError",
    "WEEKLY_SOURCE_PATH",
)
