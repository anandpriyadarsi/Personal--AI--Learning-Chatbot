"""Read-only SQLite shadow for Phase 4.4 question-topic mappings.

Legacy assessment_workspace.json remains authoritative. This adapter reads the
Phase 3 relational mapping rows plus exact migration-ledger evidence and never
writes to SQLite.
"""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from typing import Any, Dict, Mapping, Sequence, Tuple

SOURCE_PATH = "data/assessment_workspace.json"
_REQUIRED = {"migration_imports", "questions", "topics", "question_topic_mappings"}


class SQLiteQuestionTopicMappingError(RuntimeError):
    pass


class SQLiteQuestionTopicMappingSchemaError(SQLiteQuestionTopicMappingError):
    pass


class SQLiteQuestionTopicMappingReadOnlyError(SQLiteQuestionTopicMappingError):
    pass


def _dict_rows(connection: sqlite3.Connection, sql: str, params: Sequence[Any] = ()):
    cursor = connection.execute(sql, tuple(params))
    names = tuple(col[0] for col in cursor.description or ())
    return tuple({names[i]: value for i, value in enumerate(row)} for row in cursor.fetchall())


def _details(raw: Any) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SQLiteQuestionTopicMappingError("invalid migration ledger details_json") from exc
    if not isinstance(value, dict):
        raise SQLiteQuestionTopicMappingError("mapping ledger details_json must be an object")
    return value


class SQLiteQuestionTopicMappingRepository:
    """Observation-only repository for the Phase 4.4 mapping domain."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an open sqlite3.Connection")
        self.connection = connection
        tables = {str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        missing = sorted(_REQUIRED - tables)
        if missing:
            raise SQLiteQuestionTopicMappingSchemaError(
                "Phase 3 mapping tables are missing: {}".format(", ".join(missing))
            )

    def save_state(self, state):
        raise SQLiteQuestionTopicMappingReadOnlyError(
            "Phase 4.4 SQLite question-topic mappings are shadow-only"
        )

    def parity_snapshot(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        rows = list(_dict_rows(
            self.connection,
            "SELECT rowid AS ledger_rowid, source_hash, source_version, legacy_key, "
            "target_table, target_id, details_json FROM migration_imports "
            "WHERE source_path=? AND source_type='legacy_json' ORDER BY imported_at, rowid",
            (SOURCE_PATH,),
        ))
        for row in rows:
            row["details"] = _details(row["details_json"])
        if not rows:
            snapshot = {
                "source_hash": None,
                "source_version": None,
                "raw_topic_evidence": (),
                "mapping_rows": (),
                "review_required": (),
                "anomalies": ("no mapping migration evidence for assessment_workspace.json",),
            }
            if self.connection.total_changes != before:
                raise SQLiteQuestionTopicMappingError("read changed SQLite state")
            return snapshot

        latest_hash = str(rows[-1]["source_hash"])
        latest = [row for row in rows if str(row["source_hash"]) == latest_hash]
        observations = [row for row in latest if row["target_table"] == "questions" and row["details"].get("kind") == "question_topic_mapping_observation"]
        mapping_ledgers = [row for row in latest if row["target_table"] == "question_topic_mappings" and row["details"].get("kind") == "question_topic_mapping"]

        raw_evidence = []
        review = []
        anomalies = []
        expected_mapping_ids = set()
        question_key_by_target = {}
        for obs in observations:
            details = obs["details"]
            question_key = str(details.get("question_legacy_key", ""))
            question_target = str(obs["target_id"])
            question_key_by_target[question_target] = question_key
            raw_evidence.append({
                "question_legacy_key": question_key,
                "raw_topic": deepcopy(details.get("raw_topic")),
                "raw_topic_mapping": deepcopy(details.get("raw_topic_mapping")),
            })
            for item in details.get("candidate_resolutions", []) or []:
                if not isinstance(item, Mapping):
                    anomalies.append("non-object candidate resolution for {}".format(question_key))
                    continue
                if item.get("resolution") != "resolved":
                    review.append({
                        "question_legacy_key": question_key,
                        "legacy_key": str(item.get("legacy_key", "")),
                        "raw_label": deepcopy(item.get("raw_label")),
                        "normalized_label": deepcopy(item.get("normalized_label")),
                        "state": deepcopy(item.get("state")),
                        "resolution": deepcopy(item.get("resolution")),
                        "target_ids": deepcopy(item.get("target_ids", [])),
                    })

        mapping_rows = []
        for ledger in mapping_ledgers:
            target_id = str(ledger["target_id"])
            expected_mapping_ids.add(target_id)
            actual = _dict_rows(
                self.connection,
                "SELECT m.id, m.question_id, m.topic_id, m.score, m.rank, m.method, m.state, "
                "m.reason, m.created_at, m.reviewed_at, t.name AS topic_name, "
                "t.normalized_name AS normalized_topic_name, t.course_id AS topic_course_id "
                "FROM question_topic_mappings AS m JOIN topics AS t ON t.id=m.topic_id WHERE m.id=?",
                (target_id,),
            )
            if not actual:
                anomalies.append("mapping ledger target is missing: {}".format(target_id))
                continue
            row = actual[0]
            details = ledger["details"]
            if str(row["question_id"]) != str(details.get("question_target_id", "")):
                anomalies.append("mapping {} question relationship differs from ledger".format(target_id))
            if str(row["topic_id"]) != str(details.get("topic_target_id", "")):
                anomalies.append("mapping {} topic relationship differs from ledger".format(target_id))
            if str(row["topic_course_id"]) != str(details.get("course_target_id", "")):
                anomalies.append("mapping {} topic belongs to the wrong course".format(target_id))
            if str(row["normalized_topic_name"]) != str(details.get("normalized_label", "")):
                anomalies.append("mapping {} normalized topic differs from ledger".format(target_id))
            mapping_rows.append({
                "legacy_key": str(ledger["legacy_key"]),
                "question_legacy_key": str(details.get("question_legacy_key", "")),
                "raw_label": deepcopy(details.get("raw_label")),
                "normalized_label": deepcopy(details.get("normalized_label")),
                "origins": tuple(details.get("origins", []) or []),
                "topic_name": str(row["topic_name"]),
                "topic_id": str(row["topic_id"]),
                "score": row["score"],
                "rank": row["rank"],
                "method": str(row["method"]),
                "state": str(row["state"]),
                "reason": str(row["reason"]),
                "created_at": str(row["created_at"]),
                "reviewed_at": row["reviewed_at"],
            })

        question_targets = tuple(sorted(question_key_by_target))
        if question_targets:
            placeholders = ",".join("?" for _ in question_targets)
            live = _dict_rows(
                self.connection,
                "SELECT id FROM question_topic_mappings WHERE question_id IN ({})".format(placeholders),
                question_targets,
            )
            extras = sorted(str(row["id"]) for row in live if str(row["id"]) not in expected_mapping_ids)
            if extras:
                anomalies.append("mapping rows exist without latest migration evidence: {}".format(", ".join(extras)))

        versions = {str(row["source_version"]) for row in latest if row.get("source_version") is not None}
        snapshot = {
            "source_hash": latest_hash,
            "source_version": next(iter(versions)) if len(versions) == 1 else tuple(sorted(versions)),
            "raw_topic_evidence": tuple(raw_evidence),
            "mapping_rows": tuple(mapping_rows),
            "review_required": tuple(review),
            "anomalies": tuple(anomalies),
        }
        if self.connection.total_changes != before:
            raise SQLiteQuestionTopicMappingError("read changed SQLite state")
        return snapshot

    load_snapshot = parity_snapshot
