"""Read-only Phase 4.3 SQLite repository for Assessment Questions + Sources.

SQLite remains shadow state in Phase 4.3.  The adapter requires an explicitly
supplied connection, reads actual relational ownership/ordering, uses the Phase
3 migration ledger only as supporting raw evidence, and rejects every write.
Question-topic mappings and performance remain outside this cutover unit.
"""

from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.repositories.interfaces import QuestionState


WORKSPACE_SOURCE_PATH = "data/assessment_workspace.json"
ASSESSMENT_SOURCE_PATH = "data/assessments.json"
_REQUIRED_TABLES = {
    "migration_imports",
    "assessments",
    "questions",
    "question_sources",
    "knowledge_documents",
    "resources",
    "note_metadata",
    "question_topic_mappings",
}

_STATUS_ALIASES = {
    "pending": "not_started",
    "in_progress": "attempted",
    "inprogress": "attempted",
    "done": "completed",
    "complete": "completed",
}
_VALID_STATUSES = {"not_started", "attempted", "stuck", "completed"}


class SQLiteQuestionRepositoryError(RuntimeError):
    """Base error for Phase 4.3 SQLite question reads."""


class SQLiteQuestionRepositorySchemaError(SQLiteQuestionRepositoryError):
    """Raised when the supplied connection lacks the required Phase 3 schema."""


class SQLiteQuestionRepositoryDataError(SQLiteQuestionRepositoryError):
    """Raised when SQLite rows/evidence cannot be reconciled safely."""


class SQLiteQuestionRepositoryReadOnlyError(SQLiteQuestionRepositoryError):
    """Raised when a caller attempts a Phase 4.3 SQLite write."""


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
        raise SQLiteQuestionRepositoryDataError(
            "Invalid migration ledger details for {}.".format(context)
        ) from error
    if not isinstance(value, dict):
        raise SQLiteQuestionRepositoryDataError(
            "Migration ledger details must be an object for {}.".format(context)
        )
    return value


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_token(value: Any) -> str:
    text = _clean_text(value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _canonical_status(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return "not_started"
    normalized = _normalized_token(raw)
    canonical = _STATUS_ALIASES.get(normalized, normalized)
    return canonical if canonical in _VALID_STATUSES else "not_started"


def _marks_milli(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        marks = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not marks.is_finite() or marks < 0:
        return None
    return int((marks * Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _legacy_marks(value: Any):
    if value is None:
        return None
    integer = int(value)
    if integer % 1000 == 0:
        return integer // 1000
    return integer / 1000.0


def _canonical_page(value: Any) -> Optional[int]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        page = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not page.is_finite() or page != page.to_integral_value() or page < 1:
        return None
    return int(page)


def _canonical_locator(value: Any) -> str:
    if value is None or value == "" or isinstance(value, (dict, list, bool)):
        return ""
    text = str(value).strip()
    return "question:{}".format(text) if text else ""


def _source_version(rows: Sequence[Mapping[str, Any]]) -> Any:
    versions = {
        str(row.get("source_version", ""))
        for row in rows
        if str(row.get("source_version", ""))
    }
    if not versions:
        return None
    if len(versions) != 1:
        raise SQLiteQuestionRepositoryDataError(
            "Latest workspace source hash has conflicting source versions."
        )
    only = next(iter(versions))
    return int(only) if only.isdigit() else only


def _has_deferred(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


class SQLiteQuestionRepository:
    """Read-only question/source adapter over an explicit Phase 3 SQLite DB."""

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
            raise SQLiteQuestionRepositorySchemaError(
                "Phase 3 question/source tables are missing: {}".format(
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
        return tuple(
            sorted(
                (row for row in rows if str(row["source_hash"]) == latest_hash),
                key=lambda row: int(row["ledger_rowid"]),
            )
        )

    def _row_by_id(self, table: str, target_id: str) -> Dict[str, Any]:
        if table not in {
            "assessments",
            "questions",
            "question_sources",
            "knowledge_documents",
            "resources",
            "note_metadata",
        }:
            raise SQLiteQuestionRepositoryDataError(
                "Unsupported Phase 4.3 target table: {}".format(table)
            )
        rows = _fetch_dicts(
            self.connection,
            "SELECT * FROM {} WHERE id = ?".format(table),
            (target_id,),
        )
        if not rows:
            raise SQLiteQuestionRepositoryDataError(
                "Migration/relationship target is missing: {}:{}".format(
                    table, target_id
                )
            )
        return rows[0]

    def _assessment_maps(self):
        rows = self._latest_source_rows(ASSESSMENT_SOURCE_PATH)
        target_to_legacy: Dict[str, str] = {}
        target_to_key: Dict[str, str] = {}
        key_to_legacy: Dict[str, str] = {}
        for row in rows:
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
            target = str(row["target_id"])
            target_to_legacy[target] = legacy_id
            target_to_key[target] = key
            key_to_legacy[key] = legacy_id
        return target_to_legacy, target_to_key, key_to_legacy

    def _semantic_snapshot(self) -> Dict[str, Any]:
        ledger_rows = self._latest_source_rows(WORKSPACE_SOURCE_PATH)
        if not ledger_rows:
            return {
                "source_version": None,
                "source_hash": None,
                "question_catalogue": (),
                "question_statuses": (),
                "assessment_relationships": (),
                "question_order": (),
                "question_sources": (),
                "question_source_order": (),
                "question_source_identities": (),
                "raw_records": (),
                "raw_identities": (),
                "raw_source_evidence": (),
                "deferred_topic_evidence": (),
                "deferred_performance_evidence": (),
                "resolved_source_relationships": (),
                "resolved_topic_mappings": (),
                "workspace_metadata_supported": False,
                "anomalies": ("no data/assessment_workspace.json migration ledger evidence",),
                "state": {"version": 1, "workspaces": {}},
            }

        source_hash = str(ledger_rows[0]["source_hash"])
        source_version = _source_version(ledger_rows)
        question_ledgers = [
            row
            for row in ledger_rows
            if row.get("target_table") == "questions"
            and self._kind(row) == "assessment_question_raw_unit"
        ]
        source_ledgers = [
            row
            for row in ledger_rows
            if row.get("target_table") == "question_sources"
            and self._kind(row) == "question_source_raw_annotation"
        ]

        assessment_target_to_legacy, _, assessment_key_to_legacy = self._assessment_maps()
        anomalies: List[str] = []
        question_target_to_legacy: Dict[str, Tuple[str, str]] = {}
        question_key_to_identity: Dict[str, Tuple[str, str]] = {}
        question_actual_ordinals: Dict[str, int] = {}
        question_expected_order: List[str] = []
        workspace_order: List[str] = []
        prepared_questions: List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], str, str]] = []

        for ledger in question_ledgers:
            target = self._row_by_id("questions", str(ledger["target_id"]))
            details = ledger["details"]
            raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
            if raw is None:
                raw = {}
            if not isinstance(raw, dict):
                raise SQLiteQuestionRepositoryDataError(
                    "Raw question evidence must be an object for {}.".format(
                        ledger.get("legacy_key", "")
                    )
                )
            legacy_id = _raw_text(details.get("legacy_id")) or _raw_text(raw.get("id"))
            question_key = str(ledger.get("legacy_key", ""))
            expected_assessment_key = _raw_text(details.get("assessment_legacy_key"))
            expected_assessment_legacy = assessment_key_to_legacy.get(
                expected_assessment_key, ""
            )
            if not expected_assessment_legacy and expected_assessment_key.startswith("assessment:id:"):
                expected_assessment_legacy = expected_assessment_key[len("assessment:id:") :]
            target_id = str(ledger["target_id"])
            question_target_to_legacy[target_id] = (expected_assessment_legacy, legacy_id)
            question_key_to_identity[question_key] = (expected_assessment_legacy, legacy_id)
            question_expected_order.append(question_key)
            if expected_assessment_legacy and expected_assessment_legacy not in workspace_order:
                workspace_order.append(expected_assessment_legacy)

            actual_assessment_target = str(target.get("assessment_id", ""))
            actual_assessment_legacy = assessment_target_to_legacy.get(
                actual_assessment_target, ""
            )
            if not actual_assessment_legacy:
                anomalies.append(
                    "question {} points to assessment {} outside the latest assessment import".format(
                        question_key, actual_assessment_target or "<missing>"
                    )
                )
            if actual_assessment_legacy != expected_assessment_legacy:
                anomalies.append(
                    "question {} assessment relationship differs from migration evidence".format(
                        question_key
                    )
                )
            if target.get("deleted_at") is not None:
                anomalies.append(
                    "question {} is soft-deleted although it exists in the latest workspace snapshot".format(
                        question_key
                    )
                )

            try:
                actual_ordinal = int(target.get("ordinal"))
            except (TypeError, ValueError):
                actual_ordinal = -1
            try:
                expected_ordinal = int(details.get("ordinal"))
            except (TypeError, ValueError):
                expected_ordinal = -1
            question_actual_ordinals[target_id] = actual_ordinal
            if actual_ordinal != expected_ordinal:
                anomalies.append(
                    "question {} ordinal is {} but migration evidence expects {}".format(
                        question_key, actual_ordinal, expected_ordinal
                    )
                )

            expected_batch = _raw_text(details.get("import_batch_id"))
            actual_batch = _raw_text(target.get("import_batch_id"))
            if expected_batch and actual_batch != expected_batch:
                anomalies.append(
                    "question {} import_batch_id differs from migration evidence".format(
                        question_key
                    )
                )

            if _raw_text(target.get("question_text")) != _raw_text(raw.get("text")):
                anomalies.append(
                    "question {} text differs from exact raw migration evidence".format(
                        question_key
                    )
                )
            if target.get("max_marks_milli") != _marks_milli(raw.get("marks")):
                anomalies.append(
                    "question {} max marks differ from canonical Phase 3 import evidence".format(
                        question_key
                    )
                )
            if _raw_text(target.get("status")) != _canonical_status(raw.get("status")):
                anomalies.append(
                    "question {} status differs from canonical Phase 3 import evidence".format(
                        question_key
                    )
                )
            expected_notes = raw.get("notes")
            expected_notes = "" if expected_notes is None else expected_notes
            if _raw_text(target.get("user_notes")) != _raw_text(expected_notes):
                anomalies.append(
                    "question {} user notes differ from raw migration evidence".format(
                        question_key
                    )
                )

            prepared_questions.append(
                (ledger, target, deepcopy(raw), expected_assessment_legacy, legacy_id)
            )

        # Source rows use actual question ownership; the ledger only supplies raw
        # provenance and the expected owner for corruption diagnostics.
        source_by_question: Dict[str, List[Tuple[int, Dict[str, Any], Dict[str, Any]]]] = {}
        raw_source_evidence: List[Dict[str, Any]] = []
        source_identities: List[Dict[str, Any]] = []
        resolved_source_relationships: List[Dict[str, Any]] = []
        latest_source_targets = set()

        for ledger in source_ledgers:
            target_id = str(ledger["target_id"])
            latest_source_targets.add(target_id)
            target = self._row_by_id("question_sources", target_id)
            details = ledger["details"]
            expected_question_key = _raw_text(details.get("question_legacy_key"))
            expected_identity = question_key_to_identity.get(expected_question_key, ("", ""))
            actual_question_target = str(target.get("question_id", ""))
            actual_identity = question_target_to_legacy.get(actual_question_target, ("", ""))
            if actual_identity == ("", ""):
                anomalies.append(
                    "question source {} points to question {} outside the latest workspace import".format(
                        ledger["legacy_key"], actual_question_target or "<missing>"
                    )
                )
            if actual_identity != expected_identity:
                anomalies.append(
                    "question source {} ownership differs from migration evidence".format(
                        ledger["legacy_key"]
                    )
                )

            raw_label = _raw_text(details.get("raw_source_label"))
            if _raw_text(target.get("raw_source_label")) != raw_label:
                anomalies.append(
                    "question source {} raw_source_label differs from migration evidence".format(
                        ledger["legacy_key"]
                    )
                )
            expected_page = _canonical_page(details.get("raw_page_number"))
            if target.get("page_number") != expected_page:
                anomalies.append(
                    "question source {} page_number differs from Phase 3 import evidence".format(
                        ledger["legacy_key"]
                    )
                )
            expected_locator = _canonical_locator(details.get("raw_question_number"))
            if _raw_text(target.get("locator")) != expected_locator:
                anomalies.append(
                    "question source {} locator differs from Phase 3 import evidence".format(
                        ledger["legacy_key"]
                    )
                )

            links = {
                "document_id": target.get("document_id"),
                "resource_id": target.get("resource_id"),
                "note_id": target.get("note_id"),
            }
            active_links = [(name, value) for name, value in links.items() if value is not None]
            if len(active_links) > 1:
                anomalies.append(
                    "question source {} has multiple resolved relationship targets".format(
                        ledger["legacy_key"]
                    )
                )
            table_for = {
                "document_id": "knowledge_documents",
                "resource_id": "resources",
                "note_id": "note_metadata",
            }
            for field, value in active_links:
                exists = self.connection.execute(
                    "SELECT 1 FROM {} WHERE id = ?".format(table_for[field]),
                    (str(value),),
                ).fetchone()
                if exists is None:
                    anomalies.append(
                        "question source {} {} points to missing target {}".format(
                            ledger["legacy_key"], field, value
                        )
                    )

            assessment_id, question_id = actual_identity
            source_by_question.setdefault(actual_question_target, []).append(
                (int(ledger["ledger_rowid"]), ledger, target)
            )
            source_identities.append(
                {
                    "assessment_id": expected_identity[0],
                    "question_id": expected_identity[1],
                    "legacy_key": str(ledger.get("legacy_key", "")),
                }
            )
            raw_source_evidence.append(
                {
                    "assessment_id": expected_identity[0],
                    "question_id": expected_identity[1],
                    "raw_source_label": _raw_text(details.get("raw_source_label")),
                    "raw_page_number": deepcopy(details.get("raw_page_number")),
                    "raw_question_number": deepcopy(details.get("raw_question_number")),
                }
            )
            if active_links:
                resolved_source_relationships.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "raw_source_label": _raw_text(target.get("raw_source_label")),
                        "document_id": target.get("document_id"),
                        "resource_id": target.get("resource_id"),
                        "note_id": target.get("note_id"),
                    }
                )

        # Extra live source rows under latest questions are not hidden.  Phase 4.3
        # has no SQLite writer, so such rows are shadow divergence unless they are
        # represented by the latest migration evidence.
        latest_question_targets = {str(row["target_id"]) for row in question_ledgers}
        if latest_question_targets:
            placeholders = ",".join("?" for _ in latest_question_targets)
            extra_sources = _fetch_dicts(
                self.connection,
                "SELECT id, question_id FROM question_sources WHERE question_id IN ({})".format(
                    placeholders
                ),
                tuple(sorted(latest_question_targets)),
            )
            extra_source_ids = sorted(
                str(row["id"])
                for row in extra_sources
                if str(row["id"]) not in latest_source_targets
            )
            if extra_source_ids:
                anomalies.append(
                    "question source rows exist without latest workspace migration evidence: {}".format(
                        ", ".join(extra_source_ids)
                    )
                )

        # Build projections from actual SQLite rows, preserving the current source
        # order rather than sorting away relationship/order corruption.
        actual_groups: Dict[str, List[Tuple[int, int, Dict[str, Any], Dict[str, Any], str]]] = {}
        for ledger, target, raw, expected_assessment_id, legacy_id in prepared_questions:
            actual_assessment_target = str(target.get("assessment_id", ""))
            actual_assessment_id = assessment_target_to_legacy.get(actual_assessment_target, "")
            try:
                ordinal = int(target.get("ordinal"))
            except (TypeError, ValueError):
                ordinal = -1
            actual_groups.setdefault(actual_assessment_id, []).append(
                (ordinal, int(ledger["ledger_rowid"]), target, raw, legacy_id)
            )
            if actual_assessment_id and actual_assessment_id not in workspace_order:
                workspace_order.append(actual_assessment_id)

        question_catalogue: List[Dict[str, Any]] = []
        question_statuses: List[Tuple[str, str, str]] = []
        assessment_relationships: List[Tuple[str, str, str]] = []
        question_order: List[Tuple[str, Tuple[str, ...]]] = []
        question_sources: List[Dict[str, Any]] = []
        question_source_order: List[Tuple[str, str]] = []
        raw_records: List[Dict[str, Any]] = []
        raw_identities: List[Dict[str, Any]] = []
        deferred_topic_evidence: List[Dict[str, Any]] = []
        deferred_performance_evidence: List[Dict[str, Any]] = []
        state_workspaces: Dict[str, Any] = {}

        source_raw_by_identity = {
            (item["assessment_id"], item["question_id"]): item
            for item in raw_source_evidence
        }

        for assessment_id in workspace_order:
            group = sorted(actual_groups.get(assessment_id, ()), key=lambda item: (item[0], item[1]))
            if not group:
                continue
            ids: List[str] = []
            state_questions: List[Dict[str, Any]] = []
            for ordinal, _, target, raw, legacy_id in group:
                target_id = str(target.get("id", ""))
                ids.append(legacy_id)
                question_catalogue.append(
                    {
                        "assessment_id": assessment_id,
                        "id": legacy_id,
                        "ordinal": ordinal,
                        "text": _raw_text(target.get("question_text")),
                        "marks": _legacy_marks(target.get("max_marks_milli")),
                        "status": _raw_text(target.get("status")),
                        "notes": _raw_text(target.get("user_notes")),
                    }
                )
                question_statuses.append(
                    (assessment_id, legacy_id, _raw_text(target.get("status")))
                )
                assessment_relationships.append((assessment_id, legacy_id, assessment_id))
                raw_records.append(
                    {
                        "assessment_id": assessment_id,
                        "position": ordinal - 1,
                        "raw": deepcopy(raw),
                    }
                )
                expected_assessment_id = question_target_to_legacy.get(target_id, ("", ""))[0]
                raw_identities.append(
                    {
                        "assessment_id": assessment_id,
                        "expected_assessment_id": expected_assessment_id,
                        "position": ordinal - 1,
                        "raw_id": _raw_text(raw.get("id")),
                        "raw_status": _raw_text(raw.get("status")),
                    }
                )
                topic_mapping = raw.get("topic_mapping")
                if _has_deferred(raw.get("topic")) or _has_deferred(topic_mapping):
                    deferred_topic_evidence.append(
                        {
                            "assessment_id": expected_assessment_id,
                            "question_id": legacy_id,
                            "topic": deepcopy(raw.get("topic")),
                            "topic_mapping": deepcopy(topic_mapping),
                        }
                    )
                if any(
                    _has_deferred(raw.get(key))
                    for key in ("attempts", "performance", "mistakes")
                ):
                    deferred_performance_evidence.append(
                        {
                            "assessment_id": expected_assessment_id,
                            "question_id": legacy_id,
                            "attempts": deepcopy(raw.get("attempts")),
                            "performance": deepcopy(raw.get("performance")),
                            "mistakes": deepcopy(raw.get("mistakes")),
                        }
                    )

                ordered_sources = sorted(
                    source_by_question.get(target_id, ()), key=lambda item: item[0]
                )
                for _, _, source_target in ordered_sources:
                    question_sources.append(
                        {
                            "assessment_id": assessment_id,
                            "question_id": legacy_id,
                            "raw_source_label": _raw_text(source_target.get("raw_source_label")),
                            "page_number": source_target.get("page_number"),
                            "locator": _raw_text(source_target.get("locator")),
                        }
                    )
                    question_source_order.append((assessment_id, legacy_id))

                payload = deepcopy(raw)
                payload["id"] = legacy_id
                payload["text"] = _raw_text(target.get("question_text"))
                if "marks" in payload:
                    payload["marks"] = _legacy_marks(target.get("max_marks_milli"))
                if "status" in payload:
                    payload["status"] = _raw_text(target.get("status"))
                if "notes" in payload:
                    payload["notes"] = _raw_text(target.get("user_notes"))
                source_evidence = source_raw_by_identity.get(
                    (expected_assessment_id, legacy_id)
                )
                if source_evidence is not None and ordered_sources:
                    source_target = ordered_sources[0][2]
                    if "source_file" in payload:
                        payload["source_file"] = _raw_text(source_target.get("raw_source_label"))
                    if "source_page" in payload:
                        payload["source_page"] = source_target.get("page_number")
                    if "source_question_number" in payload:
                        locator = _raw_text(source_target.get("locator"))
                        payload["source_question_number"] = (
                            locator[len("question:") :]
                            if locator.startswith("question:")
                            else locator
                        )
                state_questions.append(payload)

            question_order.append((assessment_id, tuple(ids)))
            state_workspaces[assessment_id] = {
                "assessment_id": assessment_id,
                "questions": state_questions,
            }

        all_rows = self._source_rows(WORKSPACE_SOURCE_PATH)
        latest_question_ids = {str(row["target_id"]) for row in question_ledgers}
        historical_question_ids = {
            str(row["target_id"])
            for row in all_rows
            if row.get("target_table") == "questions"
            and self._kind(row) == "assessment_question_raw_unit"
        }
        historical_source_ids = {
            str(row["target_id"])
            for row in all_rows
            if row.get("target_table") == "question_sources"
            and self._kind(row) == "question_source_raw_annotation"
        }
        stale_questions = tuple(
            sorted(
                target_id
                for target_id in historical_question_ids - latest_question_ids
                if self.connection.execute(
                    "SELECT 1 FROM questions WHERE id = ? AND deleted_at IS NULL",
                    (target_id,),
                ).fetchone()
                is not None
            )
        )
        stale_sources = tuple(
            sorted(
                target_id
                for target_id in historical_source_ids - latest_source_targets
                if self.connection.execute(
                    "SELECT 1 FROM question_sources WHERE id = ?", (target_id,)
                ).fetchone()
                is not None
            )
        )
        if stale_questions:
            anomalies.append(
                "live question rows remain from older workspace imports: {}".format(
                    ", ".join(stale_questions)
                )
            )
        if stale_sources:
            anomalies.append(
                "question-source rows remain from older workspace imports: {}".format(
                    ", ".join(stale_sources)
                )
            )

        resolved_topic_mappings = tuple(
            {
                "mapping_id": str(row["id"]),
                "question_id": question_target_to_legacy.get(
                    str(row["question_id"]), ("", str(row["question_id"]))
                )[1],
                "topic_id": str(row["topic_id"]),
                "state": _raw_text(row.get("state")),
            }
            for row in _fetch_dicts(
                self.connection,
                "SELECT id, question_id, topic_id, state FROM question_topic_mappings "
                "WHERE question_id IN ({}) ORDER BY question_id, rank, id".format(
                    ",".join("?" for _ in latest_question_targets) or "NULL"
                ),
                tuple(sorted(latest_question_targets)),
            )
        ) if latest_question_targets else ()

        return {
            "source_version": source_version,
            "source_hash": source_hash,
            "question_catalogue": tuple(question_catalogue),
            "question_statuses": tuple(question_statuses),
            "assessment_relationships": tuple(assessment_relationships),
            "question_order": tuple(question_order),
            "question_sources": tuple(question_sources),
            "question_source_order": tuple(question_source_order),
            "question_source_identities": tuple(source_identities),
            "raw_records": tuple(raw_records),
            "raw_identities": tuple(raw_identities),
            "raw_source_evidence": tuple(raw_source_evidence),
            "deferred_topic_evidence": tuple(deferred_topic_evidence),
            "deferred_performance_evidence": tuple(deferred_performance_evidence),
            "resolved_source_relationships": tuple(resolved_source_relationships),
            "resolved_topic_mappings": resolved_topic_mappings,
            "workspace_metadata_supported": False,
            "anomalies": tuple(anomalies),
            "state": {"version": 1, "workspaces": state_workspaces},
        }

    def parity_snapshot(self) -> Dict[str, Any]:
        before = self.connection.total_changes
        snapshot = self._semantic_snapshot()
        if self.connection.total_changes != before:
            raise SQLiteQuestionRepositoryDataError(
                "SQLite question/source read unexpectedly changed database state."
            )
        return deepcopy(snapshot)

    def load_state(self) -> QuestionState:
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
            raise SQLiteQuestionRepositoryDataError(
                "SQLite integrity checks unexpectedly changed database state."
            )
        return {
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "pass": integrity == ("ok",) and not foreign_keys,
        }

    def save_state(self, state: QuestionState) -> QuestionState:
        raise SQLiteQuestionRepositoryReadOnlyError(
            "Phase 4.3 SQLite question repository is read-only; legacy JSON remains authoritative."
        )


__all__ = (
    "ASSESSMENT_SOURCE_PATH",
    "WORKSPACE_SOURCE_PATH",
    "SQLiteQuestionRepository",
    "SQLiteQuestionRepositoryDataError",
    "SQLiteQuestionRepositoryError",
    "SQLiteQuestionRepositoryReadOnlyError",
    "SQLiteQuestionRepositorySchemaError",
)
