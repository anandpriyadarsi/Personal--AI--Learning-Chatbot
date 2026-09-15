"""Read-only Phase 4.5 SQLite shadow for attempts, mistakes, and performance.

Legacy ``data/assessment_workspace.json`` remains authoritative.  This adapter
requires an explicitly supplied ``sqlite3.Connection``.  It reads current Phase
3 Fix 8 rows plus migration-ledger evidence, validates the *actual* relational
ownership, keeps older omitted rows as history, and never writes to SQLite.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


WORKSPACE_SOURCE_PATH = "data/assessment_workspace.json"
_REQUIRED_TABLES = {
    "migration_imports",
    "questions",
    "question_attempts",
    "mistake_events",
}

_VALID_OUTCOMES = {
    "correct",
    "partially_correct",
    "wrong",
    "stuck",
    "unknown",
}
_OUTCOME_ALIASES = {
    "partial": "partially_correct",
    "partially": "partially_correct",
    "partiallycorrect": "partially_correct",
    "partly_correct": "partially_correct",
    "partlycorrect": "partially_correct",
    "incorrect": "wrong",
    "false": "wrong",
    "unable": "stuck",
    "could_not_solve": "stuck",
    "couldn_t_solve": "stuck",
    "not_solved": "stuck",
}
_OUTCOME_WEIGHTS = {
    "correct": 1.0,
    "partially_correct": 0.5,
    "wrong": 0.0,
    "stuck": 0.0,
    "unknown": 0.0,
}


class SQLiteAttemptPerformanceRepositoryError(RuntimeError):
    """Base error for Phase 4.5 SQLite performance reads."""


class SQLiteAttemptPerformanceRepositorySchemaError(
    SQLiteAttemptPerformanceRepositoryError
):
    """Raised when required Phase 3 tables are absent."""


class SQLiteAttemptPerformanceRepositoryDataError(
    SQLiteAttemptPerformanceRepositoryError
):
    """Raised when migration evidence cannot be interpreted safely."""


class SQLiteAttemptPerformanceRepositoryReadOnlyError(
    SQLiteAttemptPerformanceRepositoryError
):
    """Raised for every attempted SQLite write in Phase 4.5."""


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
        raise SQLiteAttemptPerformanceRepositoryDataError(
            "Invalid migration ledger details for {}.".format(context)
        ) from error
    if not isinstance(value, dict):
        raise SQLiteAttemptPerformanceRepositoryDataError(
            "Migration ledger details must be an object for {}.".format(context)
        )
    return value


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _clean_text(value).casefold()).strip("_")


def _canonical_outcome(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return "unknown"
    normalized = _normalized_token(raw)
    compact = normalized.replace("_", "")
    canonical = _OUTCOME_ALIASES.get(normalized)
    if canonical is None:
        canonical = _OUTCOME_ALIASES.get(compact, normalized)
    return canonical if canonical in _VALID_OUTCOMES else "unknown"


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _marks_milli(value: Any) -> Optional[int]:
    parsed = _decimal(value)
    if parsed is None or parsed < 0:
        return None
    return int(
        (parsed * Decimal(1000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _canonical_reference(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return None


def _canonical_weight(outcome: str, value: Any) -> float:
    parsed = _decimal(value)
    if parsed is None:
        return _OUTCOME_WEIGHTS.get(outcome, 0.0)
    as_float = float(parsed)
    if not math.isfinite(as_float):
        return _OUTCOME_WEIGHTS.get(outcome, 0.0)
    return max(0.0, min(1.0, as_float))


def _source_version(rows: Sequence[Mapping[str, Any]]) -> Any:
    versions = {
        str(row.get("source_version", ""))
        for row in rows
        if str(row.get("source_version", ""))
    }
    if not versions:
        return None
    if len(versions) != 1:
        raise SQLiteAttemptPerformanceRepositoryDataError(
            "Latest workspace source hash has conflicting source versions."
        )
    only = next(iter(versions))
    return int(only) if only.isdigit() else only


def _origin_position(legacy_key: str) -> Tuple[str, Optional[int]]:
    marker = "/attempt:"
    if marker not in legacy_key:
        return "", None
    tail = legacy_key.rsplit(marker, 1)[1]
    if ":" not in tail:
        return "", None
    origin, position_text = tail.rsplit(":", 1)
    try:
        position = int(position_text)
    except ValueError:
        return origin, None
    return origin, position


def _summary(
    rows: Sequence[Mapping[str, Any]],
    raw_evidence: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, Any], ...]:
    """Project current nested-performance rows into V10.4 question summaries."""
    grouped: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {
        (str(item.get("assessment_id", "")), str(item.get("question_id", ""))): []
        for item in raw_evidence
    }
    for row in rows:
        if row.get("origin") != "performance.attempts":
            continue
        key = (str(row.get("assessment_id", "")), str(row.get("question_id", "")))
        grouped.setdefault(key, []).append(row)

    result: List[Dict[str, Any]] = []
    for (assessment_id, question_id), attempts in sorted(grouped.items()):
        attempts = sorted(attempts, key=lambda item: int(item.get("attempt_number", 0)))
        weighted_sum = sum(float(item.get("weight", 0.0)) for item in attempts)
        outcomes = {
            "correct": 0,
            "partially_correct": 0,
            "wrong": 0,
            "stuck": 0,
        }
        earned = 0
        maximum = 0
        for item in attempts:
            outcome = str(item.get("outcome", ""))
            if outcome in outcomes:
                outcomes[outcome] += 1
            e = item.get("earned_marks_milli")
            m = item.get("max_marks_milli")
            if e is not None and m is not None and int(m) > 0:
                earned += int(e)
                maximum += int(m)
        result.append(
            {
                "assessment_id": assessment_id,
                "question_id": question_id,
                "attempts": len(attempts),
                "accuracy": weighted_sum / len(attempts) if attempts else 0.0,
                "marks_accuracy": earned / maximum if maximum > 0 else None,
                "outcomes": outcomes,
            }
        )
    return tuple(result)


class SQLiteAttemptPerformanceRepository:
    """Observation-only adapter over one explicit Phase 3 SQLite connection."""

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
            raise SQLiteAttemptPerformanceRepositorySchemaError(
                "Phase 3 attempt/performance tables are missing: {}".format(
                    ", ".join(missing)
                )
            )

    @staticmethod
    def _kind(row: Mapping[str, Any]) -> str:
        details = row.get("details")
        return str(details.get("kind", "")) if isinstance(details, Mapping) else ""

    def _source_rows(self) -> Tuple[Dict[str, Any], ...]:
        rows = list(
            _fetch_dicts(
                self.connection,
                "SELECT rowid AS ledger_rowid, source_hash, source_version, "
                "legacy_key, target_table, target_id, imported_at, details_json "
                "FROM migration_imports "
                "WHERE source_path = ? AND source_type = 'legacy_json' "
                "ORDER BY imported_at, rowid",
                (WORKSPACE_SOURCE_PATH,),
            )
        )
        for row in rows:
            row["details"] = _parse_details(
                row["details_json"], context=str(row.get("legacy_key", ""))
            )
        return tuple(rows)

    def _latest_source_rows(self) -> Tuple[Dict[str, Any], ...]:
        rows = self._source_rows()
        if not rows:
            return ()
        latest_hash = str(rows[-1]["source_hash"])
        return tuple(
            sorted(
                (row for row in rows if str(row["source_hash"]) == latest_hash),
                key=lambda row: int(row["ledger_rowid"]),
            )
        )

    def _question_maps(
        self, latest: Sequence[Mapping[str, Any]]
    ) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, Tuple[str, str]], Dict[str, str]]:
        target_to_identity: Dict[str, Tuple[str, str]] = {}
        key_to_identity: Dict[str, Tuple[str, str]] = {}
        key_to_target: Dict[str, str] = {}
        for row in latest:
            if row.get("target_table") != "questions" or self._kind(row) != "assessment_question_raw_unit":
                continue
            details = row["details"]
            raw = details.get("raw", {})
            if not isinstance(raw, Mapping):
                raw = {}
            question_key = str(row.get("legacy_key", ""))
            assessment_key = _raw_text(details.get("assessment_legacy_key"))
            assessment_id = (
                assessment_key[len("assessment:id:") :]
                if assessment_key.startswith("assessment:id:")
                else assessment_key
            )
            question_id = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id"))
            identity = (assessment_id, question_id)
            target = str(row["target_id"])
            target_to_identity[target] = identity
            key_to_identity[question_key] = identity
            key_to_target[question_key] = target
        return target_to_identity, key_to_identity, key_to_target

    def _raw_performance_evidence(
        self, latest: Sequence[Mapping[str, Any]]
    ) -> Tuple[Dict[str, Any], ...]:
        evidence: List[Dict[str, Any]] = []
        for row in latest:
            if row.get("target_table") != "questions" or self._kind(row) != "assessment_question_raw_unit":
                continue
            details = row["details"]
            raw = details.get("raw", {})
            if not isinstance(raw, Mapping):
                raw = {}
            assessment_key = _raw_text(details.get("assessment_legacy_key"))
            assessment_id = (
                assessment_key[len("assessment:id:") :]
                if assessment_key.startswith("assessment:id:")
                else assessment_key
            )
            question_id = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id"))
            evidence.append(
                {
                    "assessment_id": assessment_id,
                    "question_id": question_id,
                    "attempts": deepcopy(raw.get("attempts")),
                    "mistakes": deepcopy(raw.get("mistakes")),
                    "performance": deepcopy(raw.get("performance")),
                }
            )
        return tuple(evidence)

    def _semantic_snapshot(self) -> Dict[str, Any]:
        all_ledgers = self._source_rows()
        latest = self._latest_source_rows()
        if not latest:
            return {
                "source_version": None,
                "source_hash": None,
                "raw_performance_evidence": (),
                "current_attempt_rows": (),
                "current_mistake_rows": (),
                "performance_summary": (),
                "fallback_times": {},
                "historical_attempt_rows": (),
                "historical_mistake_rows": (),
                "anomalies": ("no data/assessment_workspace.json migration ledger evidence",),
                "state": {"version": 1, "workspaces": {}},
            }

        source_hash = str(latest[0]["source_hash"])
        source_version = _source_version(latest)
        target_to_identity, key_to_identity, key_to_target = self._question_maps(latest)
        anomalies: List[str] = []

        raw_evidence = self._raw_performance_evidence(latest)
        attempt_ledgers = [
            row
            for row in latest
            if row.get("target_table") == "question_attempts"
            and self._kind(row) == "question_attempt"
        ]
        mistake_ledgers = [
            row
            for row in latest
            if row.get("target_table") == "mistake_events"
            and self._kind(row) == "mistake_event"
        ]
        fallback_times = {
            str(row["legacy_key"]): str(row.get("imported_at", ""))
            for row in attempt_ledgers
        }

        attempt_key_to_target = {
            str(row["legacy_key"]): str(row["target_id"])
            for row in attempt_ledgers
        }
        current_attempt_ids = set(attempt_key_to_target.values())
        current_mistake_ids = {str(row["target_id"]) for row in mistake_ledgers}

        current_attempts: List[Dict[str, Any]] = []
        for ledger in attempt_ledgers:
            details = ledger["details"]
            target_id = str(ledger["target_id"])
            row = self.connection.execute(
                "SELECT id, question_id, attempt_number, outcome, earned_marks_milli, "
                "max_marks_milli, response_ref, feedback_ref, occurred_at "
                "FROM question_attempts WHERE id = ?",
                (target_id,),
            ).fetchone()
            if row is None:
                anomalies.append(
                    "current attempt ledger points to missing row {}".format(target_id)
                )
                continue

            legacy_key = str(ledger["legacy_key"])
            question_key = _raw_text(details.get("question_legacy_key"))
            expected_identity = key_to_identity.get(question_key)
            expected_question_target = key_to_target.get(question_key, "")
            actual_question_target = str(row[1])
            actual_identity = target_to_identity.get(actual_question_target)
            if expected_question_target and actual_question_target != expected_question_target:
                anomalies.append(
                    "attempt {} points to a different question than migration evidence".format(
                        legacy_key
                    )
                )
            if actual_identity is None:
                anomalies.append(
                    "attempt {} points to question outside the latest question import".format(
                        legacy_key
                    )
                )
            if expected_identity is not None and actual_identity != expected_identity:
                anomalies.append(
                    "attempt {} legacy question ownership differs from migration evidence".format(
                        legacy_key
                    )
                )

            qrow = self.connection.execute(
                "SELECT deleted_at FROM questions WHERE id = ?", (actual_question_target,)
            ).fetchone()
            if qrow is None or qrow[0] is not None:
                anomalies.append(
                    "attempt {} owns a missing/deleted question".format(legacy_key)
                )

            raw = details.get("raw", {})
            if not isinstance(raw, Mapping):
                raw = {}
            origin, origin_position = _origin_position(legacy_key)
            try:
                expected_number = int(details.get("attempt_number"))
            except (TypeError, ValueError):
                expected_number = -1
            if int(row[2]) != expected_number:
                anomalies.append(
                    "attempt {} number differs from migration evidence".format(legacy_key)
                )

            expected_outcome = _canonical_outcome(raw.get("outcome"))
            if str(row[3]) != expected_outcome:
                anomalies.append(
                    "attempt {} outcome differs from canonical raw evidence".format(
                        legacy_key
                    )
                )
            expected_max = _marks_milli(
                raw.get("max_marks", raw.get("maximum_marks"))
            )
            # Fix 8 may fall back to question marks; exact comparison of that
            # fallback is handled by the dual-read legacy projection.
            if expected_max is not None and row[5] != expected_max:
                anomalies.append(
                    "attempt {} max marks differ from explicit raw evidence".format(
                        legacy_key
                    )
                )

            assessment_id, question_id = actual_identity or expected_identity or ("", "")
            current_attempts.append(
                {
                    "legacy_key": legacy_key,
                    "assessment_id": assessment_id,
                    "question_id": question_id,
                    "origin": origin,
                    "origin_position": origin_position,
                    "attempt_number": int(row[2]),
                    "outcome": str(row[3]),
                    "weight": float(details.get("weight", _OUTCOME_WEIGHTS.get(str(row[3]), 0.0))),
                    "earned_marks_milli": row[4],
                    "max_marks_milli": row[5],
                    "response_ref": row[6],
                    "feedback_ref": row[7],
                    "occurred_at": str(row[8]),
                }
            )

        current_attempts.sort(
            key=lambda item: (
                item["assessment_id"],
                item["question_id"],
                item["attempt_number"],
                item["legacy_key"],
            )
        )

        current_mistakes: List[Dict[str, Any]] = []
        for ledger in mistake_ledgers:
            details = ledger["details"]
            target_id = str(ledger["target_id"])
            row = self.connection.execute(
                "SELECT id, attempt_id, category, mistake_text, created_at, resolved_at "
                "FROM mistake_events WHERE id = ?",
                (target_id,),
            ).fetchone()
            if row is None:
                anomalies.append(
                    "current mistake ledger points to missing row {}".format(target_id)
                )
                continue
            attempt_key = _raw_text(details.get("attempt_legacy_key"))
            expected_attempt_target = attempt_key_to_target.get(attempt_key, "")
            actual_attempt_target = str(row[1])
            if expected_attempt_target and actual_attempt_target != expected_attempt_target:
                anomalies.append(
                    "mistake {} points to a different attempt than migration evidence".format(
                        ledger["legacy_key"]
                    )
                )
            if actual_attempt_target not in current_attempt_ids:
                anomalies.append(
                    "mistake {} points outside the current attempt set".format(
                        ledger["legacy_key"]
                    )
                )

            raw = details.get("raw", {})
            if not isinstance(raw, Mapping):
                raw = {}
            expected_text = raw.get("mistake")
            expected_text = expected_text.strip() if isinstance(expected_text, str) else ""
            if str(row[2]) != "legacy_attempt_mistake":
                anomalies.append(
                    "mistake {} category differs from Fix 8 semantics".format(
                        ledger["legacy_key"]
                    )
                )
            if expected_text and str(row[3]) != expected_text:
                anomalies.append(
                    "mistake {} text differs from exact raw attempt evidence".format(
                        ledger["legacy_key"]
                    )
                )
            if row[5] is not None:
                anomalies.append(
                    "mistake {} is unexpectedly resolved in the current shadow".format(
                        ledger["legacy_key"]
                    )
                )

            attempt_projection = next(
                (
                    item
                    for item in current_attempts
                    if item["legacy_key"] == attempt_key
                ),
                None,
            )
            assessment_id = (
                str(attempt_projection["assessment_id"])
                if attempt_projection is not None
                else ""
            )
            question_id = (
                str(attempt_projection["question_id"])
                if attempt_projection is not None
                else ""
            )
            current_mistakes.append(
                {
                    "legacy_key": str(ledger["legacy_key"]),
                    "assessment_id": assessment_id,
                    "question_id": question_id,
                    "attempt_legacy_key": attempt_key,
                    "category": str(row[2]),
                    "mistake_text": str(row[3]),
                    "created_at": str(row[4]),
                    "resolved_at": row[5],
                }
            )

        current_mistakes.sort(
            key=lambda item: (
                item["assessment_id"],
                item["question_id"],
                item["attempt_legacy_key"],
                item["legacy_key"],
            )
        )

        all_attempt_rows = {
            str(row[0])
            for row in self.connection.execute("SELECT id FROM question_attempts").fetchall()
        }
        all_mistake_rows = {
            str(row[0])
            for row in self.connection.execute("SELECT id FROM mistake_events").fetchall()
        }
        historical_attempt_ids = {
            str(row["target_id"])
            for row in all_ledgers
            if row.get("target_table") == "question_attempts"
            and self._kind(row) == "question_attempt"
            and str(row["source_hash"]) != source_hash
        } - current_attempt_ids
        historical_mistake_ids = {
            str(row["target_id"])
            for row in all_ledgers
            if row.get("target_table") == "mistake_events"
            and self._kind(row) == "mistake_event"
            and str(row["source_hash"]) != source_hash
        } - current_mistake_ids

        unledgered_attempts = sorted(
            all_attempt_rows - current_attempt_ids - historical_attempt_ids
        )
        if unledgered_attempts:
            anomalies.append(
                "unledgered question_attempt rows exist: {}".format(
                    ", ".join(unledgered_attempts)
                )
            )
        unledgered_mistakes = sorted(
            all_mistake_rows - current_mistake_ids - historical_mistake_ids
        )
        if unledgered_mistakes:
            anomalies.append(
                "unledgered mistake_event rows exist: {}".format(
                    ", ".join(unledgered_mistakes)
                )
            )

        historical_attempts = tuple(sorted(all_attempt_rows & historical_attempt_ids))
        historical_mistakes = tuple(sorted(all_mistake_rows & historical_mistake_ids))

        state_workspaces: Dict[str, Dict[str, Any]] = {}
        for item in current_attempts:
            workspace = state_workspaces.setdefault(
                item["assessment_id"],
                {"assessment_id": item["assessment_id"], "questions": {}},
            )
            question = workspace["questions"].setdefault(
                item["question_id"],
                {"id": item["question_id"], "attempts": []},
            )
            question["attempts"].append(deepcopy(item))

        return {
            "source_version": source_version,
            "source_hash": source_hash,
            "raw_performance_evidence": raw_evidence,
            "current_attempt_rows": tuple(current_attempts),
            "current_mistake_rows": tuple(current_mistakes),
            "performance_summary": _summary(current_attempts, raw_evidence),
            "fallback_times": fallback_times,
            "historical_attempt_rows": historical_attempts,
            "historical_mistake_rows": historical_mistakes,
            "anomalies": tuple(anomalies),
            "state": {"version": 1, "workspaces": state_workspaces},
        }

    def parity_snapshot(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        snapshot = self._semantic_snapshot()
        if self.connection.total_changes != before:
            raise SQLiteAttemptPerformanceRepositoryDataError(
                "SQLite attempt/performance read unexpectedly changed state."
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
            raise SQLiteAttemptPerformanceRepositoryDataError(
                "SQLite integrity checks unexpectedly changed state."
            )
        return {
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "pass": integrity == ("ok",) and not foreign_keys,
        }

    def save_state(self, state: Mapping[str, Any]):
        raise SQLiteAttemptPerformanceRepositoryReadOnlyError(
            "Phase 4.5 SQLite attempts/mistakes/performance is read-only; legacy JSON remains authoritative."
        )


__all__ = (
    "WORKSPACE_SOURCE_PATH",
    "SQLiteAttemptPerformanceRepository",
    "SQLiteAttemptPerformanceRepositoryDataError",
    "SQLiteAttemptPerformanceRepositoryError",
    "SQLiteAttemptPerformanceRepositoryReadOnlyError",
    "SQLiteAttemptPerformanceRepositorySchemaError",
)
