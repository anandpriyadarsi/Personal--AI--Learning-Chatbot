"""Idempotent Phase 3 importer for ``assessment_workspace.json``.

This is a shadow migration adapter only. It imports verified legacy question
records and their raw source annotations into an explicit SQLite database while
the JSON file remains authoritative. Parser fragments are never merged and raw
source labels are never guessed into document/resource/note relationships.
"""

from __future__ import annotations

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
ASSESSMENT_SOURCE_PATH = "data/assessments.json"

REQUIRED_TABLES = (
    "migration_imports",
    "assessments",
    "questions",
    "question_sources",
)

VALID_QUESTION_STATUSES = {
    "not_started",
    "attempted",
    "stuck",
    "completed",
}

_STATUS_ALIASES = {
    "pending": "not_started",
    "in_progress": "attempted",
    "inprogress": "attempted",
    "done": "completed",
    "complete": "completed",
}


@dataclass(frozen=True)
class AssessmentQuestionReviewItem:
    assessment_legacy_key: str
    assessment_target_id: str
    question_legacy_key: str
    question_target_id: str
    ordinal: int
    question_text: str
    raw_topic_label: str
    raw_source_label: str
    page_number: Optional[int]
    locator: str
    reason: str = "parser_review_required"


@dataclass(frozen=True)
class QuestionSourceImportResult:
    source_path: str
    source_hash: str
    import_batch_id: str
    questions: ImportTally
    question_sources: ImportTally
    deferred_topic_records: int
    deferred_performance_records: int
    review_items: Tuple[AssessmentQuestionReviewItem, ...]
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        return (
            self.questions.created
            + self.questions.updated
            + self.question_sources.created
            + self.question_sources.updated
        )

    @property
    def review_required_questions(self) -> int:
        return len(self.review_items)

    @property
    def unresolved_sources(self) -> int:
        return self.question_sources.total

    @property
    def deferred_topic_mappings(self) -> int:
        return self.deferred_topic_records

    @property
    def deferred_attempts(self) -> int:
        return self.deferred_performance_records


# Compatibility names for callers that use the complete feature title.
AssessmentQuestionImportResult = QuestionSourceImportResult
AssessmentQuestionsImportResult = QuestionSourceImportResult


@dataclass(frozen=True)
class _PreparedQuestionSource:
    legacy_key: str
    target_id: str
    raw_source_label: str
    page_number: Optional[int]
    locator: str
    raw_page_number: Any
    raw_question_number: Any
    created_at: str


@dataclass(frozen=True)
class _PreparedQuestion:
    legacy_key: str
    raw_legacy_id: str
    target_id: str
    ordinal: int
    question_text: str
    max_marks_milli: Optional[int]
    status: str
    user_notes: str
    created_at: str
    updated_at: str
    raw_topic_label: str
    source: Optional[_PreparedQuestionSource]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedWorkspace:
    assessment_legacy_key: str
    raw_assessment_id: str
    questions: Tuple[_PreparedQuestion, ...]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _required_identifier(value: Any, field: str, context: str) -> str:
    if isinstance(value, (dict, list, bool)):
        raise LegacyImportDataError(
            "{} has invalid {}".format(context, field)
        )
    text = _clean_text(value)
    if not text:
        raise LegacyImportDataError(
            "{} has no {}".format(context, field)
        )
    return text


def _timestamp(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip() or fallback


def _normalized_token(value: Any) -> str:
    text = _clean_text(value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _question_status(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> str:
    raw = _clean_text(value)
    if not raw:
        return "not_started"

    normalized = _normalized_token(raw)
    canonical = _STATUS_ALIASES.get(normalized, normalized)
    if canonical not in VALID_QUESTION_STATUSES:
        issues.append(
            ImportIssue(
                severity="warning",
                code="unknown_question_status",
                message=(
                    "Question status {!r} is unsupported; imported as "
                    "'not_started' while the raw record remains in the ledger."
                ).format(raw),
                legacy_key=legacy_key,
            )
        )
        return "not_started"

    if canonical != normalized:
        issues.append(
            ImportIssue(
                severity="warning",
                code="normalized_question_status",
                message="Question status {!r} imported as {!r}.".format(
                    raw,
                    canonical,
                ),
                legacy_key=legacy_key,
            )
        )
    return canonical


def _marks_milli(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        marks = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        marks = Decimal("NaN")

    if not marks.is_finite():
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_question_marks",
                message=(
                    "Question marks {!r} is not a finite number; imported as "
                    "NULL while the raw value remains in the ledger."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
        return None
    if marks < 0:
        issues.append(
            ImportIssue(
                severity="warning",
                code="out_of_range_question_marks",
                message=(
                    "Question marks {!r} is negative; imported as NULL while "
                    "the raw value remains in the ledger."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
        return None

    scaled = marks * Decimal(1000)
    rounded = scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if rounded != scaled:
        issues.append(
            ImportIssue(
                severity="warning",
                code="rounded_question_marks",
                message=(
                    "Question marks {!r} required half-up rounding to milli-"
                    "marks."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
    return int(rounded)


def _page_number(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        page = Decimal("NaN")
    else:
        try:
            page = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            page = Decimal("NaN")

    if not page.is_finite() or page != page.to_integral_value() or page < 1:
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_question_source_page",
                message=(
                    "Question source page {!r} is not a positive integer; "
                    "imported as NULL while the raw value remains in the ledger."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
        return None
    return int(page)


def _source_locator(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list, bool)):
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_question_source_locator",
                message=(
                    "Question source number is not scalar; locator was left "
                    "blank while the raw value remains in the ledger."
                ),
                legacy_key=legacy_key,
            )
        )
        return ""
    text = str(value).strip()
    return "question:{}".format(text) if text else ""


def _string_field(value: Any, field: str, legacy_key: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LegacyImportDataError(
            "question {} field '{}' must be a string".format(
                legacy_key,
                field,
            )
        )
    return value


def _has_deferred_value(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _prepare_source(
    snapshot: LegacySourceSnapshot,
    raw_question: Mapping[str, Any],
    question_key: str,
    created_at: str,
    issues: List[ImportIssue],
) -> Optional[_PreparedQuestionSource]:
    raw_label = raw_question.get("source_file")
    raw_page = raw_question.get("source_page")
    raw_number = raw_question.get("source_question_number")

    page_number = _page_number(
        raw_page,
        issues=issues,
        legacy_key=question_key,
    )
    locator = _source_locator(
        raw_number,
        issues=issues,
        legacy_key=question_key,
    )

    if raw_label is None or raw_label == "":
        if page_number is not None or locator:
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="orphan_question_source_metadata",
                    message=(
                        "Source page/locator exists without source_file; no "
                        "source row was invented and raw values remain in the ledger."
                    ),
                    legacy_key=question_key,
                )
            )
        return None

    if not isinstance(raw_label, str) or not raw_label.strip():
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_question_source_label",
                message=(
                    "Question source_file is not a non-blank string; no source "
                    "row was invented and the raw value remains in the ledger."
                ),
                legacy_key=question_key,
            )
        )
        return None

    source_key = "{}/source:legacy".format(question_key)
    issues.append(
        ImportIssue(
            severity="warning",
            code="question_source_review_required",
            message=(
                "Raw question source label was preserved without an automatic "
                "document, resource, or note link and requires review."
            ),
            legacy_key=source_key,
        )
    )
    return _PreparedQuestionSource(
        legacy_key=source_key,
        target_id=stable_target_id(
            snapshot.canonical_path,
            "question_source",
            source_key,
        ),
        raw_source_label=raw_label,
        page_number=page_number,
        locator=locator,
        raw_page_number=raw_page,
        raw_question_number=raw_number,
        created_at=created_at,
    )


def _prepare_workspaces(
    snapshot: LegacySourceSnapshot,
    data: Mapping[str, Any],
    imported_at: str,
    issues: List[ImportIssue],
) -> Tuple[Tuple[_PreparedWorkspace, ...], int, int]:
    raw_workspaces = data.get("workspaces", {})
    if not isinstance(raw_workspaces, dict):
        raise LegacyImportDataError(
            "assessment_workspace.json field 'workspaces' must be an object"
        )

    prepared: List[_PreparedWorkspace] = []
    seen_assessments = set()
    deferred_topic_records = 0
    deferred_performance_records = 0

    for raw_workspace_key, raw_workspace in raw_workspaces.items():
        workspace_context = "workspace {!r}".format(raw_workspace_key)
        workspace_key = _required_identifier(
            raw_workspace_key,
            "workspace key",
            "assessment workspace",
        )
        if not isinstance(raw_workspace, dict):
            raise LegacyImportDataError(
                "{} must be a JSON object".format(workspace_context)
            )

        assessment_id = _required_identifier(
            raw_workspace.get("assessment_id"),
            "assessment_id",
            workspace_context,
        )
        if workspace_key != assessment_id:
            raise LegacyImportDataError(
                "{} key does not match assessment_id {!r}".format(
                    workspace_context,
                    assessment_id,
                )
            )
        assessment_key = "assessment:id:{}".format(assessment_id)
        if assessment_key in seen_assessments:
            raise LegacyImportDataError(
                "duplicate assessment workspace identity: {}".format(
                    assessment_key
                )
            )
        seen_assessments.add(assessment_key)

        raw_questions = raw_workspace.get("questions", [])
        if raw_questions is None:
            raw_questions = []
        if not isinstance(raw_questions, list):
            raise LegacyImportDataError(
                "questions for {} must be an array".format(assessment_key)
            )

        workspace_created_at = _timestamp(
            raw_workspace.get("created_at"),
            imported_at,
        )
        prepared_questions: List[_PreparedQuestion] = []
        seen_question_keys = set()

        for position, raw_question in enumerate(raw_questions):
            if not isinstance(raw_question, dict):
                raise LegacyImportDataError(
                    "question at index {} for {} must be a JSON object".format(
                        position,
                        assessment_key,
                    )
                )
            raw_question_id = _required_identifier(
                raw_question.get("id"),
                "id",
                "question at index {} for {}".format(position, assessment_key),
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

            question_text = raw_question.get("text")
            if not isinstance(question_text, str) or not question_text.strip():
                raise LegacyImportDataError(
                    "question {} has no non-blank text".format(question_key)
                )
            user_notes = _string_field(
                raw_question.get("notes"),
                "notes",
                question_key,
            )
            created_at = _timestamp(
                raw_question.get("created_at"),
                workspace_created_at,
            )
            updated_at = _timestamp(
                raw_question.get("updated_at"),
                created_at,
            )

            raw_topic = raw_question.get("topic")
            topic_mapping = raw_question.get("topic_mapping")
            if _has_deferred_value(raw_topic) or _has_deferred_value(topic_mapping):
                deferred_topic_records += 1
                issues.append(
                    ImportIssue(
                        severity="info",
                        code="question_topic_data_deferred",
                        message=(
                            "Legacy question topic/mapping data remains in the "
                            "source and ledger for the mapping reconciliation fix."
                        ),
                        legacy_key=question_key,
                    )
                )

            performance_values = (
                raw_question.get("attempts"),
                raw_question.get("performance"),
                raw_question.get("mistakes"),
            )
            if any(_has_deferred_value(value) for value in performance_values):
                deferred_performance_records += 1
                issues.append(
                    ImportIssue(
                        severity="info",
                        code="question_performance_data_deferred",
                        message=(
                            "Legacy attempts/performance data remains in the "
                            "source and ledger for the performance importer."
                        ),
                        legacy_key=question_key,
                    )
                )

            raw_topic_label = raw_topic if isinstance(raw_topic, str) else ""
            source = _prepare_source(
                snapshot,
                raw_question,
                question_key,
                created_at,
                issues,
            )
            issues.append(
                ImportIssue(
                    severity="warning",
                    code="question_parser_review_required",
                    message=(
                        "Legacy question text was preserved as one raw parser "
                        "unit and requires review; no fragments were merged."
                    ),
                    legacy_key=question_key,
                )
            )

            prepared_questions.append(
                _PreparedQuestion(
                    legacy_key=question_key,
                    raw_legacy_id=raw_question_id,
                    target_id=stable_target_id(
                        snapshot.canonical_path,
                        "question",
                        question_key,
                    ),
                    ordinal=position + 1,
                    question_text=question_text,
                    max_marks_milli=_marks_milli(
                        raw_question.get("marks"),
                        issues=issues,
                        legacy_key=question_key,
                    ),
                    status=_question_status(
                        raw_question.get("status"),
                        issues=issues,
                        legacy_key=question_key,
                    ),
                    user_notes=user_notes,
                    created_at=created_at,
                    updated_at=updated_at,
                    raw_topic_label=raw_topic_label,
                    source=source,
                    raw=dict(raw_question),
                )
            )

        prepared.append(
            _PreparedWorkspace(
                assessment_legacy_key=assessment_key,
                raw_assessment_id=assessment_id,
                questions=tuple(prepared_questions),
            )
        )

    return (
        tuple(prepared),
        deferred_topic_records,
        deferred_performance_records,
    )


def _assessment_candidates(
    connection: sqlite3.Connection,
    legacy_key: str,
) -> Tuple[str, ...]:
    rows = connection.execute(
        "SELECT mi.legacy_key, mi.target_id "
        "FROM migration_imports AS mi "
        "JOIN assessments AS a ON a.id = mi.target_id "
        "WHERE mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'assessments' "
        "AND a.deleted_at IS NULL",
        (ASSESSMENT_SOURCE_PATH,),
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


def _resolve_assessment_target(
    connection: sqlite3.Connection,
    legacy_key: str,
) -> str:
    candidates = _assessment_candidates(connection, legacy_key)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise LegacyImportDataError(
            "ambiguous imported assessment mapping for {}".format(legacy_key)
        )
    raise LegacyImportDataError(
        "unresolved {}; import assessments/topics first".format(legacy_key)
    )


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
    target_exists = connection.execute(
        "SELECT 1 FROM {} WHERE id = ?".format(target_table),
        (target_id,),
    ).fetchone()
    if existing is not None:
        if existing.target_id != target_id:
            ledger.record_snapshot_import(
                snapshot,
                legacy_key=legacy_key,
                target_table=target_table,
                target_id=target_id,
            )
        if target_exists is None:
            raise LegacyImportError(
                "migration ledger points to a missing {} target: {}".format(
                    target_table,
                    target_id,
                )
            )
        return "matched"
    return "updated" if target_exists is not None else "created"


def _stage_owned_ordinals(
    connection: sqlite3.Connection,
    assessment_id: str,
    incoming: Tuple[_PreparedQuestion, ...],
) -> Tuple[Tuple[str, int], ...]:
    """Move source-owned rows aside while changed snapshots are reconciled.

    Stable question IDs survive reordering. Rows omitted by a later snapshot are
    retained (never treated as deletions) and appended after current/unrelated
    rows, preserving their prior relative order.
    """
    all_rows = connection.execute(
        "SELECT id, ordinal FROM questions WHERE assessment_id = ? "
        "ORDER BY ordinal, id",
        (assessment_id,),
    ).fetchall()
    owned_rows = connection.execute(
        "SELECT DISTINCT q.id, q.ordinal FROM questions AS q "
        "JOIN migration_imports AS mi ON mi.target_id = q.id "
        "WHERE q.assessment_id = ? AND mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'questions' "
        "ORDER BY q.ordinal, q.id",
        (assessment_id, SOURCE_PATH),
    ).fetchall()

    owned_ids = {str(row[0]) for row in owned_rows}
    incoming_ids = {question.target_id for question in incoming}
    incoming_ordinals = {question.ordinal for question in incoming}
    unrelated_ordinals = {
        int(row[1]) for row in all_rows if str(row[0]) not in owned_ids
    }
    collisions = sorted(incoming_ordinals & unrelated_ordinals)
    if collisions:
        raise LegacyImportDataError(
            "cannot reconcile question ordinals for assessment {}: "
            "non-imported rows occupy {}".format(
                assessment_id,
                ", ".join(str(value) for value in collisions),
            )
        )

    maximum = max((int(row[1]) for row in all_rows), default=0)
    stage_base = maximum + len(owned_rows) + len(incoming) + 1
    for offset, row in enumerate(owned_rows, start=1):
        connection.execute(
            "UPDATE questions SET ordinal = ? WHERE id = ?",
            (stage_base + offset, str(row[0])),
        )

    omitted = [
        str(row[0]) for row in owned_rows if str(row[0]) not in incoming_ids
    ]
    next_ordinal = max(
        len(incoming),
        max(unrelated_ordinals, default=0),
    )
    return tuple(
        (target_id, next_ordinal + position)
        for position, target_id in enumerate(omitted, start=1)
    )


def import_questions_and_sources(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> QuestionSourceImportResult:
    """Import one verified workspace snapshot in one explicit transaction."""
    ensure_tables(connection, REQUIRED_TABLES)
    data = load_verified_json(snapshot, expected_kind="object")

    if snapshot.canonical_path != SOURCE_PATH:
        raise LegacyImportDataError(
            "questions/sources importer requires {}".format(SOURCE_PATH)
        )
    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")

    issues: List[ImportIssue] = []
    (
        prepared,
        deferred_topic_records,
        deferred_performance_records,
    ) = _prepare_workspaces(snapshot, data, imported_at, issues)

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

    import_batch_id = stable_target_id(
        snapshot.canonical_path,
        "question_import_batch",
        snapshot.source_hash,
    )
    counters: Dict[str, Dict[str, int]] = {
        "questions": {},
        "question_sources": {},
    }
    review_items: List[AssessmentQuestionReviewItem] = []
    ledger = MigrationImportLedger(connection)

    with transaction(connection, immediate=True):
        for workspace in prepared:
            assessment_target_id = _resolve_assessment_target(
                connection,
                workspace.assessment_legacy_key,
            )
            question_dispositions = tuple(
                _ledger_disposition(
                    connection,
                    ledger,
                    snapshot,
                    legacy_key=question.legacy_key,
                    target_table="questions",
                    target_id=question.target_id,
                )
                for question in workspace.questions
            )
            changed_questions = any(
                disposition != "matched"
                for disposition in question_dispositions
            )
            omitted_ordinals: Tuple[Tuple[str, int], ...] = ()
            if changed_questions:
                omitted_ordinals = _stage_owned_ordinals(
                    connection,
                    assessment_target_id,
                    workspace.questions,
                )

            for question, disposition in zip(
                workspace.questions,
                question_dispositions,
            ):
                if disposition != "matched" or changed_questions:
                    connection.execute(
                        "INSERT INTO questions "
                        "(id, assessment_id, ordinal, question_text, "
                        "max_marks_milli, status, user_notes, import_batch_id, "
                        "created_at, updated_at, deleted_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "assessment_id = excluded.assessment_id, "
                        "ordinal = excluded.ordinal, "
                        "question_text = excluded.question_text, "
                        "max_marks_milli = excluded.max_marks_milli, "
                        "status = excluded.status, "
                        "user_notes = excluded.user_notes, "
                        "import_batch_id = excluded.import_batch_id, "
                        "updated_at = excluded.updated_at, deleted_at = NULL",
                        (
                            question.target_id,
                            assessment_target_id,
                            question.ordinal,
                            question.question_text,
                            question.max_marks_milli,
                            question.status,
                            question.user_notes,
                            import_batch_id,
                            question.created_at,
                            question.updated_at,
                        ),
                    )
                if disposition != "matched":
                    ledger.record_snapshot_import(
                        snapshot,
                        legacy_key=question.legacy_key,
                        target_table="questions",
                        target_id=question.target_id,
                        details={
                            "kind": "assessment_question_raw_unit",
                            "assessment_legacy_key": (
                                workspace.assessment_legacy_key
                            ),
                            "legacy_id": question.raw_legacy_id,
                            "ordinal": question.ordinal,
                            "import_batch_id": import_batch_id,
                            "parser_state": "review_required",
                            "topic_state": "deferred",
                            "performance_state": "deferred",
                            "raw": dict(question.raw),
                        },
                        imported_at=imported_at,
                    )
                add_tally(counters["questions"], disposition)

                if question.source is not None:
                    source = question.source
                    source_disposition = _ledger_disposition(
                        connection,
                        ledger,
                        snapshot,
                        legacy_key=source.legacy_key,
                        target_table="question_sources",
                        target_id=source.target_id,
                    )
                    if source_disposition != "matched":
                        connection.execute(
                            "INSERT INTO question_sources "
                            "(id, question_id, document_id, resource_id, "
                            "note_id, page_number, locator, raw_source_label, "
                            "created_at) "
                            "VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?) "
                            "ON CONFLICT(id) DO UPDATE SET "
                            "question_id = excluded.question_id, "
                            "page_number = excluded.page_number, "
                            "locator = excluded.locator, "
                            "raw_source_label = excluded.raw_source_label",
                            (
                                source.target_id,
                                question.target_id,
                                source.page_number,
                                source.locator,
                                source.raw_source_label,
                                source.created_at,
                            ),
                        )
                        ledger.record_snapshot_import(
                            snapshot,
                            legacy_key=source.legacy_key,
                            target_table="question_sources",
                            target_id=source.target_id,
                            details={
                                "kind": "question_source_raw_annotation",
                                "question_legacy_key": question.legacy_key,
                                "raw_source_label": source.raw_source_label,
                                "raw_page_number": source.raw_page_number,
                                "raw_question_number": (
                                    source.raw_question_number
                                ),
                                "resolution_state": "review_required",
                            },
                            imported_at=imported_at,
                        )
                    add_tally(
                        counters["question_sources"],
                        source_disposition,
                    )

                review_items.append(
                    AssessmentQuestionReviewItem(
                        assessment_legacy_key=workspace.assessment_legacy_key,
                        assessment_target_id=assessment_target_id,
                        question_legacy_key=question.legacy_key,
                        question_target_id=question.target_id,
                        ordinal=question.ordinal,
                        question_text=question.question_text,
                        raw_topic_label=question.raw_topic_label,
                        raw_source_label=(
                            question.source.raw_source_label
                            if question.source is not None
                            else ""
                        ),
                        page_number=(
                            question.source.page_number
                            if question.source is not None
                            else None
                        ),
                        locator=(
                            question.source.locator
                            if question.source is not None
                            else ""
                        ),
                    )
                )

            for target_id, ordinal in omitted_ordinals:
                connection.execute(
                    "UPDATE questions SET ordinal = ? WHERE id = ?",
                    (ordinal, target_id),
                )

        # TOCTOU guard: a source change during the transaction aborts everything.
        source_sha256(snapshot)

    return QuestionSourceImportResult(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        import_batch_id=import_batch_id,
        questions=freeze_tally(counters["questions"]),
        question_sources=freeze_tally(counters["question_sources"]),
        deferred_topic_records=deferred_topic_records,
        deferred_performance_records=deferred_performance_records,
        review_items=tuple(review_items),
        issues=tuple(issues),
    )


def import_assessment_questions_and_sources(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> QuestionSourceImportResult:
    """Compatibility alias for :func:`import_questions_and_sources`."""
    return import_questions_and_sources(
        connection,
        snapshot,
        imported_at=imported_at,
    )


def import_assessment_questions(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> QuestionSourceImportResult:
    """Short compatibility alias for the complete question/source import."""
    return import_questions_and_sources(
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


def render_assessment_question_review_markdown(
    result: QuestionSourceImportResult,
) -> str:
    """Render a portable parser/source review report without writing a file."""
    lines = [
        "# Assessment Question Review",
        "",
        "- Source: `{}`".format(_markdown_cell(result.source_path)),
        "- Source SHA-256: `{}`".format(result.source_hash),
        "- Import batch: `{}`".format(result.import_batch_id),
        "- Review-required questions: {}".format(
            result.review_required_questions
        ),
        "- Unresolved source annotations: {}".format(
            result.unresolved_sources
        ),
        "",
    ]
    if not result.review_items:
        lines.append("No assessment questions require review.")
        return "\n".join(lines) + "\n"

    lines.extend(
        (
            "| Assessment | Ordinal | Raw question unit | Topic | Source | "
            "Locator | State |",
            "|---|---:|---|---|---|---|---|",
        )
    )
    for item in result.review_items:
        source = item.raw_source_label or "not recorded"
        location_parts = []
        if item.locator:
            location_parts.append(item.locator)
        if item.page_number is not None:
            location_parts.append("page {}".format(item.page_number))
        lines.append(
            "| {} | {} | {} | {} | {} | {} | parser review required |".format(
                _markdown_cell(item.assessment_legacy_key),
                item.ordinal,
                _markdown_cell(item.question_text),
                _markdown_cell(item.raw_topic_label or "unmapped"),
                _markdown_cell(source),
                _markdown_cell(", ".join(location_parts) or "n/a"),
            )
        )
    return "\n".join(lines) + "\n"


def render_question_review_markdown(
    result: QuestionSourceImportResult,
) -> str:
    """Compatibility alias for the assessment-question report renderer."""
    return render_assessment_question_review_markdown(result)


__all__ = (
    "AssessmentQuestionImportResult",
    "AssessmentQuestionReviewItem",
    "AssessmentQuestionsImportResult",
    "QuestionSourceImportResult",
    "import_assessment_questions",
    "import_assessment_questions_and_sources",
    "import_questions_and_sources",
    "render_assessment_question_review_markdown",
    "render_question_review_markdown",
)
