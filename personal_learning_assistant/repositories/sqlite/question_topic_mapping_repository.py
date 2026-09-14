"""Read-only Phase 4.4 SQLite repository for Question <-> Topic mappings.

SQLite remains shadow state.  The repository requires an explicitly supplied
``sqlite3.Connection`` and never opens a database by path.  Current mapping
rows are identified through the latest ``assessment_workspace.json`` migration
ledger evidence; older retained rows are reported as historical mapping state
rather than silently treated as current authority.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Sequence, Tuple


WORKSPACE_SOURCE_PATH = "data/assessment_workspace.json"
ASSESSMENT_SOURCE_PATH = "data/assessments.json"
COURSE_SOURCE_PATH = "data/courses.json"
_REQUIRED_TABLES = {
    "migration_imports",
    "courses",
    "topics",
    "assessments",
    "questions",
    "question_topic_mappings",
}


class SQLiteQuestionTopicMappingRepositoryError(RuntimeError):
    """Base error for Phase 4.4 SQLite mapping reads."""


class SQLiteQuestionTopicMappingRepositorySchemaError(
    SQLiteQuestionTopicMappingRepositoryError
):
    """Raised when the supplied SQLite connection lacks required tables."""


class SQLiteQuestionTopicMappingRepositoryDataError(
    SQLiteQuestionTopicMappingRepositoryError
):
    """Raised when current rows/evidence cannot be reconciled safely."""


class SQLiteQuestionTopicMappingRepositoryReadOnlyError(
    SQLiteQuestionTopicMappingRepositoryError
):
    """Raised for every Phase 4.4 SQLite write attempt."""


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
        raise SQLiteQuestionTopicMappingRepositoryDataError(
            "Invalid migration details for {}.".format(context)
        ) from error
    if not isinstance(value, dict):
        raise SQLiteQuestionTopicMappingRepositoryDataError(
            "Migration details must be an object for {}.".format(context)
        )
    return value


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
        raise SQLiteQuestionTopicMappingRepositoryDataError(
            "Latest workspace source hash has conflicting source versions."
        )
    value = next(iter(values))
    return int(value) if value.isdigit() else value


class SQLiteQuestionTopicMappingRepository:
    """Read-only mapping adapter over an explicit Phase 3 SQLite connection."""

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
            raise SQLiteQuestionTopicMappingRepositorySchemaError(
                "Phase 3 question-topic tables are missing: {}".format(
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
            sorted(
                (row for row in rows if str(row["source_hash"]) == latest_hash),
                key=lambda row: int(row["ledger_rowid"]),
            )
        )

    def _assessment_maps(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        target_to_legacy: Dict[str, str] = {}
        key_to_legacy: Dict[str, str] = {}
        for row in self._latest_source_rows(ASSESSMENT_SOURCE_PATH):
            if row.get("target_table") != "assessments" or self._kind(row) != "assessment":
                continue
            details = row["details"]
            raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
            if not isinstance(raw, Mapping):
                raw = {}
            legacy_id = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id"))
            key = str(row.get("legacy_key", ""))
            if not legacy_id and key.startswith("assessment:id:"):
                legacy_id = key[len("assessment:id:") :]
            target_to_legacy[str(row["target_id"])] = legacy_id
            key_to_legacy[key] = legacy_id
        return target_to_legacy, key_to_legacy

    def _question_maps(self) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, Tuple[str, str]]]:
        _, assessment_key_to_legacy = self._assessment_maps()
        target_to_identity: Dict[str, Tuple[str, str]] = {}
        key_to_identity: Dict[str, Tuple[str, str]] = {}
        for row in self._latest_source_rows(WORKSPACE_SOURCE_PATH):
            if row.get("target_table") != "questions" or self._kind(row) != "assessment_question_raw_unit":
                continue
            details = row["details"]
            raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
            if not isinstance(raw, Mapping):
                raw = {}
            legacy_id = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id"))
            assessment_key = _raw_text(details.get("assessment_legacy_key"))
            assessment_id = assessment_key_to_legacy.get(assessment_key, "")
            if not assessment_id and assessment_key.startswith("assessment:id:"):
                assessment_id = assessment_key[len("assessment:id:") :]
            identity = (assessment_id, legacy_id)
            target_to_identity[str(row["target_id"])] = identity
            key_to_identity[str(row["legacy_key"])] = identity
        return target_to_identity, key_to_identity

    def _topic_maps(self) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        latest_course_rows = self._latest_source_rows(COURSE_SOURCE_PATH)
        for row in latest_course_rows:
            if row.get("target_table") != "topics" or self._kind(row) != "topic":
                continue
            target_id = str(row["target_id"])
            actual = self.connection.execute(
                "SELECT id, course_id, name, normalized_name, deleted_at "
                "FROM topics WHERE id = ?",
                (target_id,),
            ).fetchone()
            if actual is None:
                continue
            result[target_id] = {
                "id": str(actual[0]),
                "course_id": str(actual[1]),
                "name": _raw_text(actual[2]),
                "normalized_name": _raw_text(actual[3]),
                "deleted_at": actual[4],
            }
        return result

    def _semantic_snapshot(self) -> Dict[str, Any]:
        latest_rows = self._latest_source_rows(WORKSPACE_SOURCE_PATH)
        if not latest_rows:
            return {
                "source_version": None,
                "source_hash": None,
                "raw_mapping_observations": (),
                "current_mapping_rows": (),
                "historical_mapping_rows": (),
                "anomalies": ("no data/assessment_workspace.json migration ledger evidence",),
                "state": {"version": 1, "workspaces": {}},
            }

        source_hash = str(latest_rows[0]["source_hash"])
        source_version = _source_version(latest_rows)
        observation_ledgers = [
            row
            for row in latest_rows
            if row.get("target_table") == "questions"
            and self._kind(row) == "question_topic_mapping_observation"
        ]
        mapping_ledgers = [
            row
            for row in latest_rows
            if row.get("target_table") == "question_topic_mappings"
            and self._kind(row) == "question_topic_mapping"
        ]

        question_target_to_identity, question_key_to_identity = self._question_maps()
        assessment_target_to_legacy, _ = self._assessment_maps()
        topics = self._topic_maps()
        anomalies: List[str] = []
        raw_observations: List[Dict[str, Any]] = []
        state_workspaces: Dict[str, Dict[str, Any]] = {}

        for ledger in observation_ledgers:
            details = ledger["details"]
            question_key = _raw_text(details.get("question_legacy_key"))
            identity = question_key_to_identity.get(question_key)
            target_id = str(ledger["target_id"])
            actual_identity = question_target_to_identity.get(target_id)
            if identity is None:
                identity = actual_identity
            if identity is None:
                anomalies.append(
                    "topic-mapping observation {} cannot resolve its legacy question identity".format(
                        ledger["legacy_key"]
                    )
                )
                continue
            assessment_id, question_id = identity
            if actual_identity != identity:
                anomalies.append(
                    "topic-mapping observation {} points to a different question target".format(
                        ledger["legacy_key"]
                    )
                )

            question_row = self.connection.execute(
                "SELECT assessment_id, deleted_at FROM questions WHERE id = ?",
                (target_id,),
            ).fetchone()
            if question_row is None or question_row[1] is not None:
                anomalies.append(
                    "topic-mapping observation {} points to a missing/deleted question".format(
                        ledger["legacy_key"]
                    )
                )
            else:
                actual_assessment_legacy = assessment_target_to_legacy.get(
                    str(question_row[0]), ""
                )
                if actual_assessment_legacy != assessment_id:
                    anomalies.append(
                        "topic-mapping observation {} resolves through the wrong assessment".format(
                            ledger["legacy_key"]
                        )
                    )

            raw_observations.append(
                {
                    "assessment_id": assessment_id,
                    "question_id": question_id,
                    "raw_topic": deepcopy(details.get("raw_topic")),
                    "raw_topic_mapping": deepcopy(details.get("raw_topic_mapping")),
                    "candidate_resolutions": deepcopy(
                        details.get("candidate_resolutions", [])
                    ),
                }
            )
            workspace = state_workspaces.setdefault(
                assessment_id,
                {"assessment_id": assessment_id, "questions": []},
            )
            workspace["questions"].append(
                {
                    "id": question_id,
                    "topic": deepcopy(details.get("raw_topic")),
                    "topic_mapping": deepcopy(details.get("raw_topic_mapping")),
                }
            )

        current_mapping_ids = {str(row["target_id"]) for row in mapping_ledgers}
        current_rows: List[Dict[str, Any]] = []
        rank_seen: Dict[str, set] = {}

        for ledger in mapping_ledgers:
            details = ledger["details"]
            target_id = str(ledger["target_id"])
            row = self.connection.execute(
                "SELECT id, question_id, topic_id, score, rank, method, state, "
                "reason, created_at, reviewed_at "
                "FROM question_topic_mappings WHERE id = ?",
                (target_id,),
            ).fetchone()
            if row is None:
                anomalies.append(
                    "current mapping ledger points to missing row {}".format(target_id)
                )
                continue

            question_target = str(row[1])
            topic_target = str(row[2])
            identity = question_target_to_identity.get(question_target)
            if identity is None:
                anomalies.append(
                    "mapping {} points to question {} outside the latest question import".format(
                        target_id, question_target
                    )
                )
                assessment_id, question_id = "", ""
            else:
                assessment_id, question_id = identity

            expected_question = _raw_text(details.get("question_target_id"))
            expected_topic = _raw_text(details.get("topic_target_id"))
            expected_course = _raw_text(details.get("course_target_id"))
            if expected_question and question_target != expected_question:
                anomalies.append(
                    "mapping {} question relationship differs from migration evidence".format(
                        target_id
                    )
                )
            if expected_topic and topic_target != expected_topic:
                anomalies.append(
                    "mapping {} topic relationship differs from migration evidence".format(
                        target_id
                    )
                )

            question_course = ""
            qrow = self.connection.execute(
                "SELECT q.deleted_at, a.course_id, a.deleted_at "
                "FROM questions AS q JOIN assessments AS a ON a.id = q.assessment_id "
                "WHERE q.id = ?",
                (question_target,),
            ).fetchone()
            if qrow is None or qrow[0] is not None or qrow[2] is not None:
                anomalies.append(
                    "mapping {} owns a missing/deleted question or assessment".format(
                        target_id
                    )
                )
            else:
                question_course = str(qrow[1])

            topic = topics.get(topic_target)
            if topic is None:
                actual_topic = self.connection.execute(
                    "SELECT course_id, name, normalized_name, deleted_at FROM topics WHERE id = ?",
                    (topic_target,),
                ).fetchone()
                if actual_topic is None:
                    anomalies.append(
                        "mapping {} points to missing topic {}".format(
                            target_id, topic_target
                        )
                    )
                    topic = {
                        "course_id": "",
                        "name": "",
                        "normalized_name": "",
                        "deleted_at": None,
                    }
                else:
                    topic = {
                        "course_id": str(actual_topic[0]),
                        "name": _raw_text(actual_topic[1]),
                        "normalized_name": _raw_text(actual_topic[2]),
                        "deleted_at": actual_topic[3],
                    }
                    anomalies.append(
                        "mapping {} points to topic {} outside the latest course/topic import".format(
                            target_id, topic_target
                        )
                    )

            if topic.get("deleted_at") is not None:
                anomalies.append(
                    "mapping {} points to soft-deleted topic {}".format(
                        target_id, topic_target
                    )
                )
            if question_course and str(topic.get("course_id", "")) != question_course:
                anomalies.append(
                    "mapping {} crosses courses between its question and topic".format(
                        target_id
                    )
                )
            if expected_course and question_course and question_course != expected_course:
                anomalies.append(
                    "mapping {} question course differs from migration evidence".format(
                        target_id
                    )
                )
            expected_normalized = _raw_text(details.get("normalized_label"))
            if expected_normalized and _raw_text(topic.get("normalized_name")) != expected_normalized:
                anomalies.append(
                    "mapping {} topic normalized name differs from migration evidence".format(
                        target_id
                    )
                )

            rank = row[4]
            if rank is not None:
                try:
                    rank_value = int(rank)
                except (TypeError, ValueError):
                    rank_value = -1
                seen = rank_seen.setdefault(question_target, set())
                if rank_value in seen:
                    anomalies.append(
                        "question {} has duplicate current mapping rank {}".format(
                            question_id or question_target, rank_value
                        )
                    )
                seen.add(rank_value)

            current_rows.append(
                {
                    "assessment_id": assessment_id,
                    "question_id": question_id,
                    "raw_label": deepcopy(details.get("raw_label")),
                    "normalized_label": _raw_text(topic.get("normalized_name")),
                    "topic_name": _raw_text(topic.get("name")),
                    "score": row[3],
                    "rank": row[4],
                    "method": _raw_text(row[5]),
                    "state": _raw_text(row[6]),
                    "reason": _raw_text(row[7]),
                    "created_at": _raw_text(row[8]),
                    "reviewed_at": row[9],
                }
            )

        all_mapping_ledgers = [
            row
            for row in self._source_rows(WORKSPACE_SOURCE_PATH)
            if row.get("target_table") == "question_topic_mappings"
            and self._kind(row) == "question_topic_mapping"
        ]
        historical_ids = {
            str(row["target_id"])
            for row in all_mapping_ledgers
            if str(row["target_id"]) not in current_mapping_ids
        }
        all_rows = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT id FROM question_topic_mappings"
            ).fetchall()
        }
        unledgered = sorted(all_rows - current_mapping_ids - historical_ids)
        if unledgered:
            anomalies.append(
                "unledgered question-topic mapping rows exist: {}".format(
                    ", ".join(unledgered)
                )
            )

        historical_rows = tuple(sorted(all_rows & historical_ids))
        current_rows.sort(
            key=lambda item: (
                item["assessment_id"],
                item["question_id"],
                item["rank"] is None,
                item["rank"] if item["rank"] is not None else 0,
                item["normalized_label"],
            )
        )

        return {
            "source_version": source_version,
            "source_hash": source_hash,
            "raw_mapping_observations": tuple(raw_observations),
            "current_mapping_rows": tuple(current_rows),
            "historical_mapping_rows": historical_rows,
            "anomalies": tuple(anomalies),
            "state": {"version": 1, "workspaces": state_workspaces},
        }

    def parity_snapshot(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        snapshot = self._semantic_snapshot()
        if self.connection.total_changes != before:
            raise SQLiteQuestionTopicMappingRepositoryDataError(
                "SQLite question-topic mapping read unexpectedly changed state."
            )
        return deepcopy(snapshot)

    def load_state(self) -> Dict[str, Any]:
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
            raise SQLiteQuestionTopicMappingRepositoryDataError(
                "SQLite integrity checks unexpectedly changed state."
            )
        return {
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "pass": integrity == ("ok",) and not foreign_keys,
        }

    def save_state(self, state: Mapping[str, Any]):
        raise SQLiteQuestionTopicMappingRepositoryReadOnlyError(
            "Phase 4.4 SQLite mapping repository is read-only; legacy JSON remains authoritative."
        )


__all__ = (
    "ASSESSMENT_SOURCE_PATH",
    "COURSE_SOURCE_PATH",
    "WORKSPACE_SOURCE_PATH",
    "SQLiteQuestionTopicMappingRepository",
    "SQLiteQuestionTopicMappingRepositoryDataError",
    "SQLiteQuestionTopicMappingRepositoryError",
    "SQLiteQuestionTopicMappingRepositoryReadOnlyError",
    "SQLiteQuestionTopicMappingRepositorySchemaError",
)
