"""Idempotent Phase 3 importer for legacy attempts, mistakes, and performance evidence.

This is a shadow migration adapter only. It reads one verified
``assessment_workspace.json`` snapshot and writes question-level performance
evidence into an explicit temporary SQLite database while JSON remains
authoritative until the Phase 4 cutover gate is approved.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Tuple

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


SOURCE_PATH = "data/assessment_workspace.json"
QUESTION_SOURCE_PATH = SOURCE_PATH

REQUIRED_TABLES = (
    "migration_imports",
    "questions",
    "question_attempts",
    "mistake_events",
)

VALID_OUTCOMES = {
    "correct",
    "partially_correct",
    "wrong",
    "stuck",
    "unknown",
}

OUTCOME_ALIASES = {
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

OUTCOME_WEIGHTS = {
    "correct": 1.0,
    "partially_correct": 0.5,
    "wrong": 0.0,
    "stuck": 0.0,
    "unknown": 0.0,
}


@dataclass(frozen=True)
class AttemptPerformanceReviewItem:
    assessment_legacy_key: str
    question_legacy_key: str
    question_target_id: str
    attempt_legacy_key: str
    attempt_target_id: str
    outcome: str
    reason: str
    raw_detail: str = ""


@dataclass(frozen=True)
class AttemptPerformanceImportResult:
    source_path: str
    source_hash: str
    questions_scanned: int
    questions_with_attempts: int
    attempts: ImportTally
    mistake_events: ImportTally
    total_attempts: int
    total_mistakes: int
    outcome_counts: Mapping[str, int]
    earned_marks_milli: int
    max_marks_milli: int
    marks_evidence_attempts: int
    deferred_mistakes: int
    review_items: Tuple[AttemptPerformanceReviewItem, ...]
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        return (
            self.attempts.created
            + self.attempts.updated
            + self.mistake_events.created
            + self.mistake_events.updated
        )

    @property
    def marks_accuracy(self) -> Optional[float]:
        if self.max_marks_milli <= 0:
            return None
        return self.earned_marks_milli / self.max_marks_milli

    @property
    def attempt_accuracy(self) -> float:
        if self.total_attempts <= 0:
            return 0.0
        weighted = sum(
            OUTCOME_WEIGHTS.get(outcome, 0.0) * count
            for outcome, count in self.outcome_counts.items()
        )
        return weighted / self.total_attempts


# Compatibility names for callers using the full feature title.
AttemptMistakePerformanceImportResult = AttemptPerformanceImportResult
AssessmentPerformanceImportResult = AttemptPerformanceImportResult


@dataclass(frozen=True)
class _PreparedMistake:
    legacy_key: str
    target_id: str
    category: str
    mistake_text: str
    created_at: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedAttempt:
    legacy_key: str
    target_id: str
    attempt_number: int
    outcome: str
    earned_marks_milli: Optional[int]
    max_marks_milli: Optional[int]
    response_ref: Optional[str]
    feedback_ref: Optional[str]
    occurred_at: str
    weight: float
    mistakes: Tuple[_PreparedMistake, ...]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedQuestion:
    assessment_legacy_key: str
    question_legacy_key: str
    raw_question_id: str
    target_id: str
    attempts: Tuple[_PreparedAttempt, ...]
    deferred_mistakes: int


@dataclass(frozen=True)
class _PreparedWorkspace:
    assessment_legacy_key: str
    questions: Tuple[_PreparedQuestion, ...]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_token(value: Any) -> str:
    text = _clean_text(value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _required_identifier(value: Any, field: str, context: str) -> str:
    if isinstance(value, (dict, list, bool)):
        raise LegacyImportDataError(
            "{} has invalid {}".format(context, field)
        )
    text = _clean_text(value)
    if not text:
        raise LegacyImportDataError("{} has no {}".format(context, field))
    return text


def _timestamp(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _json_text_or_none(value: Any, *, field: str, issues: List[ImportIssue], legacy_key: str) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_attempt_reference",
                message=(
                    "Attempt field '{}' was not JSON serializable; stored as NULL "
                    "while the raw attempt remains in ledger details."
                ).format(field),
                legacy_key=legacy_key,
            )
        )
        return None


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def _marks_milli(
    value: Any,
    *,
    field: str,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Optional[int]:
    if value is None or value == "":
        return None

    parsed = _decimal(value)
    if parsed is None:
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_attempt_marks",
                message=(
                    "Attempt field '{}' value {!r} is not a finite number; "
                    "imported as NULL while the raw value remains in ledger details."
                ).format(field, value),
                legacy_key=legacy_key,
            )
        )
        return None

    if parsed < 0:
        issues.append(
            ImportIssue(
                severity="warning",
                code="negative_attempt_marks",
                message=(
                    "Attempt field '{}' value {!r} is negative; imported as NULL "
                    "while the raw value remains in ledger details."
                ).format(field, value),
                legacy_key=legacy_key,
            )
        )
        return None

    scaled = parsed * Decimal(1000)
    rounded = scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if rounded != scaled:
        issues.append(
            ImportIssue(
                severity="warning",
                code="rounded_attempt_marks",
                message=(
                    "Attempt field '{}' value {!r} required half-up rounding to "
                    "milli-marks."
                ).format(field, value),
                legacy_key=legacy_key,
            )
        )
    return int(rounded)


def _outcome(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> str:
    raw = _clean_text(value)
    if not raw:
        issues.append(
            ImportIssue(
                severity="warning",
                code="missing_attempt_outcome",
                message=(
                    "Attempt outcome is missing; imported as 'unknown' while "
                    "the raw attempt remains in ledger details."
                ),
                legacy_key=legacy_key,
            )
        )
        return "unknown"

    normalized = _normalized_token(raw)
    compact = normalized.replace("_", "")
    canonical = OUTCOME_ALIASES.get(normalized)
    if canonical is None:
        canonical = OUTCOME_ALIASES.get(compact, normalized)

    if canonical not in VALID_OUTCOMES:
        issues.append(
            ImportIssue(
                severity="warning",
                code="unknown_attempt_outcome",
                message=(
                    "Attempt outcome {!r} is unsupported; imported as 'unknown' "
                    "while the raw attempt remains in ledger details."
                ).format(raw),
                legacy_key=legacy_key,
            )
        )
        return "unknown"

    if canonical != normalized:
        issues.append(
            ImportIssue(
                severity="warning",
                code="normalized_attempt_outcome",
                message="Attempt outcome {!r} imported as {!r}.".format(
                    raw,
                    canonical,
                ),
                legacy_key=legacy_key,
            )
        )
    return canonical


def _weight_for_outcome(outcome: str, raw_weight: Any) -> float:
    parsed = _decimal(raw_weight)
    if parsed is None:
        return OUTCOME_WEIGHTS.get(outcome, 0.0)
    as_float = float(parsed)
    if not math.isfinite(as_float):
        return OUTCOME_WEIGHTS.get(outcome, 0.0)
    return max(0.0, min(1.0, as_float))


def _attempt_sources(raw_question: Mapping[str, Any], question_key: str) -> Tuple[Tuple[str, List[Any]], ...]:
    sources: List[Tuple[str, List[Any]]] = []

    raw_top_level = raw_question.get("attempts")
    if raw_top_level not in (None, ""):
        if not isinstance(raw_top_level, list):
            raise LegacyImportDataError(
                "question {} field 'attempts' must be an array when present".format(
                    question_key
                )
            )
        if raw_top_level:
            sources.append(("attempts", raw_top_level))

    performance = raw_question.get("performance")
    if performance not in (None, ""):
        if not isinstance(performance, dict):
            raise LegacyImportDataError(
                "question {} field 'performance' must be an object when present".format(
                    question_key
                )
            )
        raw_performance_attempts = performance.get("attempts")
        if raw_performance_attempts not in (None, ""):
            if not isinstance(raw_performance_attempts, list):
                raise LegacyImportDataError(
                    "question {} field 'performance.attempts' must be an array".format(
                        question_key
                    )
                )
            if raw_performance_attempts:
                sources.append(("performance.attempts", raw_performance_attempts))

    return tuple(sources)


def _standalone_mistake_count(raw_question: Mapping[str, Any]) -> int:
    count = 0
    performance = raw_question.get("performance")
    if isinstance(performance, dict) and isinstance(performance.get("mistakes"), list):
        count += len([item for item in performance.get("mistakes", []) if item])
    if isinstance(raw_question.get("mistakes"), list):
        count += len([item for item in raw_question.get("mistakes", []) if item])
    return count


def _prepare_attempt_mistakes(
    snapshot: LegacySourceSnapshot,
    attempt_key: str,
    attempt_id: str,
    raw_attempt: Mapping[str, Any],
    occurred_at: str,
    issues: List[ImportIssue],
) -> Tuple[_PreparedMistake, ...]:
    raw_mistake = raw_attempt.get("mistake")
    if raw_mistake is None or raw_mistake == "":
        return ()

    if not isinstance(raw_mistake, str):
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_attempt_mistake",
                message=(
                    "Attempt mistake is not a string; no mistake row was created "
                    "while the raw attempt remains in ledger details."
                ),
                legacy_key=attempt_key,
            )
        )
        return ()

    mistake_text = raw_mistake.strip()
    if not mistake_text:
        return ()

    mistake_key = "{}/mistake:legacy_attempt".format(attempt_key)
    return (
        _PreparedMistake(
            legacy_key=mistake_key,
            target_id=stable_target_id(
                snapshot.canonical_path,
                "mistake_event",
                mistake_key,
            ),
            category="legacy_attempt_mistake",
            mistake_text=mistake_text,
            created_at=occurred_at,
            raw={
                "attempt_id": attempt_id,
                "mistake": raw_mistake,
            },
        ),
    )


def _prepare_workspaces(
    snapshot: LegacySourceSnapshot,
    data: Mapping[str, Any],
    imported_at: str,
    issues: List[ImportIssue],
) -> Tuple[Tuple[_PreparedWorkspace, ...], int]:
    raw_workspaces = data.get("workspaces", {})
    if not isinstance(raw_workspaces, dict):
        raise LegacyImportDataError(
            "assessment_workspace.json field 'workspaces' must be an object"
        )

    prepared_workspaces: List[_PreparedWorkspace] = []
    questions_scanned = 0

    for raw_workspace_key, raw_workspace in raw_workspaces.items():
        workspace_key = _required_identifier(
            raw_workspace_key,
            "workspace key",
            "assessment workspace",
        )
        context = "workspace {!r}".format(raw_workspace_key)
        if not isinstance(raw_workspace, dict):
            raise LegacyImportDataError("{} must be a JSON object".format(context))

        assessment_id = _required_identifier(
            raw_workspace.get("assessment_id"),
            "assessment_id",
            context,
        )
        if workspace_key != assessment_id:
            raise LegacyImportDataError(
                "{} key does not match assessment_id {!r}".format(
                    context,
                    assessment_id,
                )
            )

        assessment_key = "assessment:id:{}".format(assessment_id)
        raw_questions = raw_workspace.get("questions", [])
        if raw_questions is None:
            raw_questions = []
        if not isinstance(raw_questions, list):
            raise LegacyImportDataError(
                "questions for {} must be an array".format(assessment_key)
            )

        prepared_questions: List[_PreparedQuestion] = []
        seen_question_keys = set()

        for question_position, raw_question in enumerate(raw_questions):
            if not isinstance(raw_question, dict):
                raise LegacyImportDataError(
                    "question at index {} for {} must be a JSON object".format(
                        question_position,
                        assessment_key,
                    )
                )

            raw_question_id = _required_identifier(
                raw_question.get("id"),
                "id",
                "question at index {} for {}".format(
                    question_position,
                    assessment_key,
                ),
            )
            question_key = "{}/question:id:{}".format(
                assessment_key,
                raw_question_id,
            )
            if question_key in seen_question_keys:
                raise LegacyImportDataError(
                    "duplicate legacy question identity: {}".format(question_key)
                )
            seen_question_keys.add(question_key)
            questions_scanned += 1

            source_groups = _attempt_sources(raw_question, question_key)
            prepared_attempts: List[_PreparedAttempt] = []
            attempt_number = 0

            for origin, raw_attempts in source_groups:
                for position, raw_attempt in enumerate(raw_attempts, start=1):
                    if not isinstance(raw_attempt, dict):
                        raise LegacyImportDataError(
                            "{} attempt {} item {} must be an object".format(
                                question_key,
                                origin,
                                position,
                            )
                        )
                    attempt_number += 1
                    attempt_key = "{}/attempt:{}:{}".format(
                        question_key,
                        origin,
                        position,
                    )
                    attempt_id = stable_target_id(
                        snapshot.canonical_path,
                        "question_attempt",
                        attempt_key,
                    )
                    occurred_at = _timestamp(
                        raw_attempt.get("time", raw_attempt.get("occurred_at")),
                        imported_at,
                    )
                    outcome = _outcome(
                        raw_attempt.get("outcome"),
                        issues=issues,
                        legacy_key=attempt_key,
                    )
                    max_marks_milli = _marks_milli(
                        raw_attempt.get(
                            "max_marks",
                            raw_attempt.get("maximum_marks", raw_question.get("marks")),
                        ),
                        field="max_marks",
                        issues=issues,
                        legacy_key=attempt_key,
                    )
                    earned_marks_milli = _marks_milli(
                        raw_attempt.get("earned_marks"),
                        field="earned_marks",
                        issues=issues,
                        legacy_key=attempt_key,
                    )
                    if (
                        earned_marks_milli is not None
                        and max_marks_milli is not None
                        and earned_marks_milli > max_marks_milli
                    ):
                        issues.append(
                            ImportIssue(
                                severity="warning",
                                code="earned_marks_exceed_max",
                                message=(
                                    "Attempt earned marks exceeded max marks; "
                                    "earned marks were imported as NULL while "
                                    "raw values remain in ledger details."
                                ),
                                legacy_key=attempt_key,
                            )
                        )
                        earned_marks_milli = None

                    response_ref = _json_text_or_none(
                        raw_attempt.get("response_ref", raw_attempt.get("response")),
                        field="response_ref",
                        issues=issues,
                        legacy_key=attempt_key,
                    )
                    feedback_ref = _json_text_or_none(
                        raw_attempt.get("feedback_ref", raw_attempt.get("feedback")),
                        field="feedback_ref",
                        issues=issues,
                        legacy_key=attempt_key,
                    )

                    mistakes = _prepare_attempt_mistakes(
                        snapshot,
                        attempt_key,
                        attempt_id,
                        raw_attempt,
                        occurred_at,
                        issues,
                    )
                    prepared_attempts.append(
                        _PreparedAttempt(
                            legacy_key=attempt_key,
                            target_id=attempt_id,
                            attempt_number=attempt_number,
                            outcome=outcome,
                            earned_marks_milli=earned_marks_milli,
                            max_marks_milli=max_marks_milli,
                            response_ref=response_ref,
                            feedback_ref=feedback_ref,
                            occurred_at=occurred_at,
                            weight=_weight_for_outcome(
                                outcome,
                                raw_attempt.get("weight"),
                            ),
                            mistakes=mistakes,
                            raw=dict(raw_attempt),
                        )
                    )

            deferred_mistakes = _standalone_mistake_count(raw_question)
            if deferred_mistakes:
                issues.append(
                    ImportIssue(
                        severity="warning",
                        code="standalone_mistakes_deferred",
                        message=(
                            "Standalone performance mistakes were not attached "
                            "to a guessed attempt; they remain preserved in the "
                            "raw question ledger/source for reconciliation."
                        ),
                        legacy_key=question_key,
                    )
                )

            prepared_questions.append(
                _PreparedQuestion(
                    assessment_legacy_key=assessment_key,
                    question_legacy_key=question_key,
                    raw_question_id=raw_question_id,
                    target_id=stable_target_id(
                        snapshot.canonical_path,
                        "question",
                        question_key,
                    ),
                    attempts=tuple(prepared_attempts),
                    deferred_mistakes=deferred_mistakes,
                )
            )

        prepared_workspaces.append(
            _PreparedWorkspace(
                assessment_legacy_key=assessment_key,
                questions=tuple(prepared_questions),
            )
        )

    return tuple(prepared_workspaces), questions_scanned


def _resolve_question_target(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    legacy_key: str,
    expected_target_id: str,
) -> str:
    row = connection.execute(
        "SELECT mi.target_id FROM migration_imports AS mi "
        "JOIN questions AS q ON q.id = mi.target_id "
        "WHERE mi.source_path = ? "
        "AND mi.source_hash = ? "
        "AND mi.source_type = ? "
        "AND mi.source_version = ? "
        "AND mi.legacy_key = ? "
        "AND mi.target_table = 'questions' "
        "AND q.deleted_at IS NULL",
        (
            snapshot.canonical_path,
            snapshot.source_hash,
            snapshot.source_type,
            snapshot.source_version,
            legacy_key,
        ),
    ).fetchall()

    targets = sorted({str(item[0]) for item in row})
    if len(targets) > 1:
        raise LegacyImportDataError(
            "ambiguous imported question mapping for {}".format(legacy_key)
        )
    if not targets:
        raise LegacyImportDataError(
            "unresolved {}; import questions/sources for this exact workspace hash first".format(
                legacy_key
            )
        )
    if targets[0] != expected_target_id:
        raise LegacyImportDataError(
            "stable question target mismatch for {}".format(legacy_key)
        )
    return targets[0]


def _target_exists_by_id(
    connection: sqlite3.Connection,
    table: str,
    target_id: str,
) -> bool:
    row = connection.execute(
        "SELECT 1 FROM {} WHERE id = ?".format(table),
        (target_id,),
    ).fetchone()
    return row is not None


def _ledger_disposition(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot: LegacySourceSnapshot,
    *,
    legacy_key: str,
    target_table: str,
    target_id: str,
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
    target_exists = _target_exists_by_id(connection, target_table, target_id)

    if existing is not None:
        if existing.target_id != target_id:
            ledger.record_snapshot_import(
                snapshot,
                legacy_key=legacy_key,
                target_table=target_table,
                target_id=target_id,
            )
        if not target_exists:
            raise LegacyImportError(
                "migration ledger points to a missing {} target: {}".format(
                    target_table,
                    target_id,
                )
            )
        return "matched"

    return "updated" if target_exists else "created"


def _ensure_attempt_slot_available(
    connection: sqlite3.Connection,
    question_id: str,
    attempt_number: int,
    target_id: str,
) -> None:
    row = connection.execute(
        "SELECT id FROM question_attempts WHERE question_id = ? "
        "AND attempt_number = ?",
        (question_id, attempt_number),
    ).fetchone()
    if row is not None and str(row[0]) != target_id:
        raise LegacyImportDataError(
            "attempt number {} for question {} is already occupied by another row".format(
                attempt_number,
                question_id,
            )
        )


def import_attempts_mistakes_and_performance(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> AttemptPerformanceImportResult:
    """Import one verified workspace snapshot's attempts/mistakes transactionally."""
    ensure_tables(connection, REQUIRED_TABLES)
    data = load_verified_json(snapshot, expected_kind="object")

    if snapshot.canonical_path != SOURCE_PATH:
        raise LegacyImportDataError(
            "attempt/performance importer requires {}".format(SOURCE_PATH)
        )
    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")

    issues: List[ImportIssue] = []
    prepared, questions_scanned = _prepare_workspaces(
        snapshot,
        data,
        imported_at,
        issues,
    )

    version = data.get("version")
    if version not in (None, 1, "1"):
        issues.append(
            ImportIssue(
                severity="warning",
                code="unexpected_assessment_workspace_version",
                message=(
                    "assessment_workspace.json version {!r} was imported "
                    "without rewriting the source."
                ).format(version),
            )
        )

    counters: Dict[str, Dict[str, int]] = {
        "attempts": {},
        "mistake_events": {},
    }
    outcome_counts: Dict[str, int] = {outcome: 0 for outcome in sorted(VALID_OUTCOMES)}
    review_items: List[AttemptPerformanceReviewItem] = []
    total_attempts = 0
    total_mistakes = 0
    marks_evidence_attempts = 0
    earned_marks_total = 0
    max_marks_total = 0
    questions_with_attempts = 0
    deferred_mistakes = 0

    ledger = MigrationImportLedger(connection)

    with transaction(connection, immediate=True):
        for workspace in prepared:
            for question in workspace.questions:
                question_target_id = _resolve_question_target(
                    connection,
                    snapshot,
                    question.question_legacy_key,
                    question.target_id,
                )
                if question.attempts:
                    questions_with_attempts += 1
                deferred_mistakes += question.deferred_mistakes

                for attempt in question.attempts:
                    _ensure_attempt_slot_available(
                        connection,
                        question_target_id,
                        attempt.attempt_number,
                        attempt.target_id,
                    )
                    disposition = _ledger_disposition(
                        connection,
                        ledger,
                        snapshot,
                        legacy_key=attempt.legacy_key,
                        target_table="question_attempts",
                        target_id=attempt.target_id,
                    )
                    if disposition != "matched":
                        connection.execute(
                            "INSERT INTO question_attempts "
                            "(id, question_id, attempt_number, outcome, "
                            "earned_marks_milli, max_marks_milli, response_ref, "
                            "feedback_ref, occurred_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(id) DO UPDATE SET "
                            "question_id = excluded.question_id, "
                            "attempt_number = excluded.attempt_number, "
                            "outcome = excluded.outcome, "
                            "earned_marks_milli = excluded.earned_marks_milli, "
                            "max_marks_milli = excluded.max_marks_milli, "
                            "response_ref = excluded.response_ref, "
                            "feedback_ref = excluded.feedback_ref, "
                            "occurred_at = excluded.occurred_at",
                            (
                                attempt.target_id,
                                question_target_id,
                                attempt.attempt_number,
                                attempt.outcome,
                                attempt.earned_marks_milli,
                                attempt.max_marks_milli,
                                attempt.response_ref,
                                attempt.feedback_ref,
                                attempt.occurred_at,
                            ),
                        )
                        ledger.record_snapshot_import(
                            snapshot,
                            legacy_key=attempt.legacy_key,
                            target_table="question_attempts",
                            target_id=attempt.target_id,
                            details={
                                "kind": "question_attempt",
                                "assessment_legacy_key": (
                                    workspace.assessment_legacy_key
                                ),
                                "question_legacy_key": question.question_legacy_key,
                                "raw_question_id": question.raw_question_id,
                                "attempt_number": attempt.attempt_number,
                                "outcome": attempt.outcome,
                                "weight": attempt.weight,
                                "raw": dict(attempt.raw),
                            },
                            imported_at=imported_at,
                        )
                    add_tally(counters["attempts"], disposition)

                    total_attempts += 1
                    outcome_counts[attempt.outcome] = (
                        outcome_counts.get(attempt.outcome, 0) + 1
                    )
                    if (
                        attempt.earned_marks_milli is not None
                        and attempt.max_marks_milli is not None
                        and attempt.max_marks_milli > 0
                    ):
                        marks_evidence_attempts += 1
                        earned_marks_total += attempt.earned_marks_milli
                        max_marks_total += attempt.max_marks_milli

                    for mistake in attempt.mistakes:
                        mistake_disposition = _ledger_disposition(
                            connection,
                            ledger,
                            snapshot,
                            legacy_key=mistake.legacy_key,
                            target_table="mistake_events",
                            target_id=mistake.target_id,
                        )
                        if mistake_disposition != "matched":
                            connection.execute(
                                "INSERT INTO mistake_events "
                                "(id, attempt_id, category, mistake_text, "
                                "created_at, resolved_at) "
                                "VALUES (?, ?, ?, ?, ?, NULL) "
                                "ON CONFLICT(id) DO UPDATE SET "
                                "attempt_id = excluded.attempt_id, "
                                "category = excluded.category, "
                                "mistake_text = excluded.mistake_text, "
                                "created_at = excluded.created_at, "
                                "resolved_at = NULL",
                                (
                                    mistake.target_id,
                                    attempt.target_id,
                                    mistake.category,
                                    mistake.mistake_text,
                                    mistake.created_at,
                                ),
                            )
                            ledger.record_snapshot_import(
                                snapshot,
                                legacy_key=mistake.legacy_key,
                                target_table="mistake_events",
                                target_id=mistake.target_id,
                                details={
                                    "kind": "mistake_event",
                                    "question_legacy_key": (
                                        question.question_legacy_key
                                    ),
                                    "attempt_legacy_key": attempt.legacy_key,
                                    "raw": dict(mistake.raw),
                                },
                                imported_at=imported_at,
                            )
                        add_tally(counters["mistake_events"], mistake_disposition)
                        total_mistakes += 1

                    if attempt.outcome == "unknown":
                        review_items.append(
                            AttemptPerformanceReviewItem(
                                assessment_legacy_key=workspace.assessment_legacy_key,
                                question_legacy_key=question.question_legacy_key,
                                question_target_id=question_target_id,
                                attempt_legacy_key=attempt.legacy_key,
                                attempt_target_id=attempt.target_id,
                                outcome=attempt.outcome,
                                reason="unknown_attempt_outcome",
                            )
                        )

                if question.deferred_mistakes:
                    review_items.append(
                        AttemptPerformanceReviewItem(
                            assessment_legacy_key=workspace.assessment_legacy_key,
                            question_legacy_key=question.question_legacy_key,
                            question_target_id=question_target_id,
                            attempt_legacy_key="",
                            attempt_target_id="",
                            outcome="",
                            reason="standalone_mistakes_deferred",
                            raw_detail="{} standalone mistakes".format(
                                question.deferred_mistakes
                            ),
                        )
                    )

        # TOCTOU guard: a source change during the transaction aborts everything.
        source_sha256(snapshot)

    return AttemptPerformanceImportResult(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        questions_scanned=questions_scanned,
        questions_with_attempts=questions_with_attempts,
        attempts=freeze_tally(counters["attempts"]),
        mistake_events=freeze_tally(counters["mistake_events"]),
        total_attempts=total_attempts,
        total_mistakes=total_mistakes,
        outcome_counts=dict(outcome_counts),
        earned_marks_milli=earned_marks_total,
        max_marks_milli=max_marks_total,
        marks_evidence_attempts=marks_evidence_attempts,
        deferred_mistakes=deferred_mistakes,
        review_items=tuple(review_items),
        issues=tuple(issues),
    )


def import_attempts_and_mistakes(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> AttemptPerformanceImportResult:
    """Compatibility alias for :func:`import_attempts_mistakes_and_performance`."""
    return import_attempts_mistakes_and_performance(
        connection,
        snapshot,
        imported_at=imported_at,
    )


def import_assessment_performance(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> AttemptPerformanceImportResult:
    """Compatibility alias for the complete Fix 8 importer."""
    return import_attempts_mistakes_and_performance(
        connection,
        snapshot,
        imported_at=imported_at,
    )


def _markdown_cell(value: Any) -> str:
    return (
        str(value)
        .replace("|", "\\|")
        .replace("\r", "")
        .replace("\n", "<br>")
    )


def render_attempt_performance_review_markdown(
    result: AttemptPerformanceImportResult,
) -> str:
    """Render a portable performance review report without writing a file."""
    lines = [
        "# Attempt / Mistake Performance Import Review",
        "",
        "- Source: `{}`".format(_markdown_cell(result.source_path)),
        "- Source SHA-256: `{}`".format(result.source_hash),
        "- Questions scanned: {}".format(result.questions_scanned),
        "- Questions with attempts: {}".format(result.questions_with_attempts),
        "- Attempts imported/matched: {}".format(result.attempts.total),
        "- Mistake events imported/matched: {}".format(result.mistake_events.total),
        "- Deferred standalone mistakes: {}".format(result.deferred_mistakes),
        "",
        "## Outcome counts",
        "",
    ]
    if result.total_attempts == 0:
        lines.append("No attempt evidence was present in this source snapshot.")
    else:
        for outcome in sorted(result.outcome_counts):
            count = int(result.outcome_counts[outcome])
            if count:
                lines.append("- {}: {}".format(outcome, count))
        lines.append(
            "- Attempt accuracy: {}%".format(
                round(result.attempt_accuracy * 100)
            )
        )
        if result.marks_accuracy is not None:
            lines.append(
                "- Marks accuracy: {}%".format(
                    round(result.marks_accuracy * 100)
                )
            )

    if result.review_items:
        lines.extend(
            (
                "",
                "## Review items",
                "",
                "| Question | Attempt | Outcome | Reason | Detail |",
                "|---|---|---|---|---|",
            )
        )
        for item in result.review_items:
            lines.append(
                "| {} | {} | {} | {} | {} |".format(
                    _markdown_cell(item.question_legacy_key),
                    _markdown_cell(item.attempt_legacy_key or "n/a"),
                    _markdown_cell(item.outcome or "n/a"),
                    _markdown_cell(item.reason),
                    _markdown_cell(item.raw_detail),
                )
            )

    return "\n".join(lines) + "\n"


def render_assessment_performance_review_markdown(
    result: AttemptPerformanceImportResult,
) -> str:
    """Compatibility alias for the Fix 8 review renderer."""
    return render_attempt_performance_review_markdown(result)


__all__ = (
    "AssessmentPerformanceImportResult",
    "AttemptMistakePerformanceImportResult",
    "AttemptPerformanceImportResult",
    "AttemptPerformanceReviewItem",
    "OUTCOME_WEIGHTS",
    "import_assessment_performance",
    "import_attempts_and_mistakes",
    "import_attempts_mistakes_and_performance",
    "render_assessment_performance_review_markdown",
    "render_attempt_performance_review_markdown",
)
