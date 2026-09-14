"""Idempotent Phase 3 importer for legacy question topic mappings.

The importer reads one verified ``assessment_workspace.json`` snapshot after
the Fix 4--6 prerequisite imports. It preserves accepted legacy topic tags and
ranked mapping candidates without re-running the heuristic mapper. Topic links
are made only through exact normalized names inside the assessment's imported
course; unresolved labels remain review items instead of guessed foreign keys.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
ASSESSMENT_SOURCE_PATH = "data/assessments.json"
COURSE_SOURCE_PATH = "data/courses.json"

REQUIRED_TABLES = (
    "migration_imports",
    "assessments",
    "questions",
    "topics",
    "question_topic_mappings",
)

KNOWN_CONFIDENCE_LABELS = {"low", "medium", "high"}


@dataclass(frozen=True)
class QuestionTopicMappingReviewItem:
    assessment_legacy_key: str
    question_legacy_key: str
    question_target_id: str
    ordinal: int
    question_text: str
    raw_topic_label: str
    normalized_topic_label: str
    candidate_rank: Optional[int]
    proposed_state: str
    reason: str


@dataclass(frozen=True)
class QuestionTopicMappingImportResult:
    source_path: str
    source_hash: str
    questions_scanned: int
    mapping_observations: ImportTally
    question_topic_mappings: ImportTally
    accepted_mappings: int
    proposed_mappings: int
    unmapped_questions: int
    unresolved_candidates: int
    review_items: Tuple[QuestionTopicMappingReviewItem, ...]
    issues: Tuple[ImportIssue, ...]

    @property
    def changed_rows(self) -> int:
        return (
            self.question_topic_mappings.created
            + self.question_topic_mappings.updated
        )

    @property
    def review_required_items(self) -> int:
        return len(self.review_items)

    @property
    def review_required_questions(self) -> int:
        return len({item.question_legacy_key for item in self.review_items})

    @property
    def mappings(self) -> ImportTally:
        return self.question_topic_mappings


# Compatibility name for callers using a plural result name.
QuestionTopicMappingsImportResult = QuestionTopicMappingImportResult


@dataclass(frozen=True)
class _PreparedCandidate:
    legacy_key: str
    target_id: str
    raw_label: str
    normalized_label: str
    score: Optional[float]
    rank: Optional[int]
    method: str
    state: str
    reason: str
    created_at: str
    reviewed_at: Optional[str]
    origins: Tuple[str, ...]
    raw_candidate: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedQuestion:
    assessment_legacy_key: str
    question_legacy_key: str
    raw_question_id: str
    ordinal: int
    question_text: str
    raw_topic: str
    raw_topic_mapping: Optional[Mapping[str, Any]]
    suggested_normalized_label: str
    inconsistent_accepted_mapping: bool
    candidates: Tuple[_PreparedCandidate, ...]


@dataclass(frozen=True)
class _PreparedWorkspace:
    assessment_legacy_key: str
    questions: Tuple[_PreparedQuestion, ...]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_label(value: str) -> str:
    return _clean_text(value).casefold()


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


def _optional_label(value: Any, field: str, legacy_key: str) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise LegacyImportDataError(
            "question {} field '{}' must be a string or null".format(
                legacy_key,
                field,
            )
        )
    return value if value.strip() else ""


def _timestamp(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip() or fallback


def _score(
    value: Any,
    *,
    field: str,
    issues: List[ImportIssue],
    legacy_key: str,
) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        parsed = Decimal("NaN")
    else:
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            parsed = Decimal("NaN")

    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_question_topic_score",
                message=(
                    "{} score {!r} is not a finite value in 0..1; imported "
                    "as NULL while the raw value remains in ledger evidence."
                ).format(field, value),
                legacy_key=legacy_key,
            )
        )
        return None
    return float(parsed)


def _method(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> str:
    if value is None or value == "":
        return "legacy_topic_mapping"
    if not isinstance(value, str) or not value.strip():
        issues.append(
            ImportIssue(
                severity="warning",
                code="invalid_question_topic_method",
                message=(
                    "Legacy mapping method is not a non-blank string; "
                    "'legacy_topic_mapping' was used and raw evidence retained."
                ),
                legacy_key=legacy_key,
            )
        )
        return "legacy_topic_mapping"
    return value.strip()


def _confidence_reason(
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
                code="invalid_question_topic_confidence",
                message=(
                    "Legacy mapping confidence is not a scalar label; it was "
                    "kept only in ledger evidence."
                ),
                legacy_key=legacy_key,
            )
        )
        return ""
    text = _clean_text(value).casefold()
    if text not in KNOWN_CONFIDENCE_LABELS:
        issues.append(
            ImportIssue(
                severity="warning",
                code="unknown_question_topic_confidence",
                message=(
                    "Legacy mapping confidence {!r} is unknown; the value was "
                    "preserved in the mapping reason and ledger evidence."
                ).format(value),
                legacy_key=legacy_key,
            )
        )
    return text


def _accepted_flag(
    value: Any,
    *,
    issues: List[ImportIssue],
    legacy_key: str,
) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    issues.append(
        ImportIssue(
            severity="warning",
            code="invalid_question_topic_accepted_flag",
            message=(
                "Legacy mapping accepted flag is not boolean; it was treated "
                "as false so no topic was silently accepted."
            ),
            legacy_key=legacy_key,
        )
    )
    return False


def _candidate_reason(
    origins: Tuple[str, ...],
    confidence: str,
    *,
    score_conflict: bool,
) -> str:
    parts = ["legacy {}".format(" + ".join(origins))]
    if confidence:
        parts.append("confidence={}".format(confidence))
    if score_conflict:
        parts.append("conflicting raw scores; primary suggestion score retained")
    return "; ".join(parts)


def _prepare_candidates(
    snapshot: LegacySourceSnapshot,
    raw_question: Mapping[str, Any],
    question_key: str,
    fallback_time: str,
    issues: List[ImportIssue],
) -> Tuple[
    str,
    Optional[Mapping[str, Any]],
    str,
    bool,
    Tuple[_PreparedCandidate, ...],
]:
    raw_topic = _optional_label(
        raw_question.get("topic"),
        "topic",
        question_key,
    )
    direct_normalized = _normalized_label(raw_topic) if raw_topic else ""

    raw_mapping_value = raw_question.get("topic_mapping")
    if raw_mapping_value is None:
        raw_mapping: Optional[Mapping[str, Any]] = None
        mapping: Mapping[str, Any] = {}
    elif not isinstance(raw_mapping_value, dict):
        raise LegacyImportDataError(
            "question {} field 'topic_mapping' must be an object or null".format(
                question_key
            )
        )
    else:
        raw_mapping = dict(raw_mapping_value)
        mapping = raw_mapping_value

    suggested = _optional_label(
        mapping.get("suggested_topic"),
        "topic_mapping.suggested_topic",
        question_key,
    )
    suggested_normalized = _normalized_label(suggested) if suggested else ""
    method = _method(
        mapping.get("method"),
        issues=issues,
        legacy_key=question_key,
    )
    confidence = _confidence_reason(
        mapping.get("confidence"),
        issues=issues,
        legacy_key=question_key,
    )
    accepted = _accepted_flag(
        mapping.get("accepted"),
        issues=issues,
        legacy_key=question_key,
    )
    mapped_at = _timestamp(mapping.get("mapped_at"), fallback_time)

    raw_alternatives = mapping.get("alternatives", [])
    if raw_alternatives is None:
        raw_alternatives = []
    if not isinstance(raw_alternatives, list):
        raise LegacyImportDataError(
            "question {} topic_mapping.alternatives must be an array".format(
                question_key
            )
        )

    mutable: Dict[str, Dict[str, Any]] = {}
    for position, raw_candidate in enumerate(raw_alternatives):
        if not isinstance(raw_candidate, dict):
            raise LegacyImportDataError(
                "topic alternative {} for question {} must be an object".format(
                    position,
                    question_key,
                )
            )
        label = _optional_label(
            raw_candidate.get("topic"),
            "topic_mapping.alternatives[{}].topic".format(position),
            question_key,
        )
        if not label:
            raise LegacyImportDataError(
                "topic alternative {} for question {} has no label".format(
                    position,
                    question_key,
                )
            )
        normalized = _normalized_label(label)
        if normalized in mutable:
            raise LegacyImportDataError(
                "duplicate topic alternative for question {}: {!r}".format(
                    question_key,
                    label,
                )
            )
        mutable[normalized] = {
            "raw_label": label,
            "score": _score(
                raw_candidate.get("score"),
                field="Alternative",
                issues=issues,
                legacy_key=question_key,
            ),
            "rank": position + 1,
            "origins": ["alternative"],
            "raw_candidate": dict(raw_candidate),
            "score_conflict": False,
        }

    suggested_score = _score(
        mapping.get("score"),
        field="Suggested topic",
        issues=issues,
        legacy_key=question_key,
    )
    if suggested_normalized:
        if suggested_normalized in mutable:
            candidate = mutable[suggested_normalized]
            candidate["origins"].insert(0, "suggested")
            alternative_score = candidate["score"]
            if (
                suggested_score is not None
                and alternative_score is not None
                and not math.isclose(
                    suggested_score,
                    alternative_score,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            ):
                candidate["score_conflict"] = True
                issues.append(
                    ImportIssue(
                        severity="warning",
                        code="conflicting_question_topic_scores",
                        message=(
                            "Suggested-topic and matching alternative scores "
                            "conflict; the primary suggested score was retained."
                        ),
                        legacy_key=question_key,
                    )
                )
            if suggested_score is not None:
                candidate["score"] = suggested_score
        else:
            for candidate in mutable.values():
                candidate["rank"] += 1
            mutable[suggested_normalized] = {
                "raw_label": suggested,
                "score": suggested_score,
                "rank": 1,
                "origins": ["suggested"],
                "raw_candidate": {},
                "score_conflict": False,
            }

    if direct_normalized:
        if direct_normalized in mutable:
            mutable[direct_normalized]["origins"].append("accepted_topic")
        else:
            mutable[direct_normalized] = {
                "raw_label": raw_topic,
                "score": None,
                "rank": None,
                "origins": ["accepted_topic"],
                "raw_candidate": {},
                "score_conflict": False,
            }

    inconsistent_accepted_mapping = bool(
        accepted
        and (
            not suggested_normalized
            or direct_normalized != suggested_normalized
        )
    )
    if inconsistent_accepted_mapping:
        issues.append(
            ImportIssue(
                severity="warning",
                code="inconsistent_accepted_question_topic_mapping",
                message=(
                    "Legacy mapping is marked accepted but suggested_topic and "
                    "the question's current topic do not agree; both raw facts "
                    "were preserved and require review."
                ),
                legacy_key=question_key,
            )
        )

    prepared: List[_PreparedCandidate] = []
    for normalized, candidate in mutable.items():
        origins = tuple(candidate["origins"])
        mapping_origin = bool(
            {"suggested", "alternative"}.intersection(origins)
        )
        state = (
            "accepted"
            if (
                normalized == direct_normalized
                or (accepted and normalized == suggested_normalized)
            )
            else "proposed"
        )
        candidate_method = method if mapping_origin else "legacy_manual_topic"
        created_at = mapped_at if mapping_origin else fallback_time
        reviewed_at = created_at if state == "accepted" else None
        candidate_key = "{}/topic:label:{}".format(question_key, normalized)
        prepared.append(
            _PreparedCandidate(
                legacy_key=candidate_key,
                target_id=stable_target_id(
                    snapshot.canonical_path,
                    "question_topic_mapping",
                    candidate_key,
                ),
                raw_label=candidate["raw_label"],
                normalized_label=normalized,
                score=candidate["score"],
                rank=candidate["rank"],
                method=candidate_method,
                state=state,
                reason=_candidate_reason(
                    origins,
                    confidence,
                    score_conflict=bool(candidate["score_conflict"]),
                ),
                created_at=created_at,
                reviewed_at=reviewed_at,
                origins=origins,
                raw_candidate=candidate["raw_candidate"],
            )
        )

    prepared.sort(
        key=lambda item: (
            item.rank is None,
            item.rank if item.rank is not None else 0,
            item.normalized_label,
        )
    )
    return (
        raw_topic,
        raw_mapping,
        suggested_normalized,
        inconsistent_accepted_mapping,
        tuple(prepared),
    )


def _prepare_workspaces(
    snapshot: LegacySourceSnapshot,
    data: Mapping[str, Any],
    imported_at: str,
    issues: List[ImportIssue],
) -> Tuple[_PreparedWorkspace, ...]:
    raw_workspaces = data.get("workspaces", {})
    if not isinstance(raw_workspaces, dict):
        raise LegacyImportDataError(
            "assessment_workspace.json field 'workspaces' must be an object"
        )

    prepared: List[_PreparedWorkspace] = []
    seen_assessment_keys = set()
    for raw_workspace_key, raw_workspace in raw_workspaces.items():
        workspace_key = _required_identifier(
            raw_workspace_key,
            "workspace key",
            "assessment workspace",
        )
        workspace_context = "workspace {!r}".format(raw_workspace_key)
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
        if assessment_key in seen_assessment_keys:
            raise LegacyImportDataError(
                "duplicate assessment workspace identity: {}".format(
                    assessment_key
                )
            )
        seen_assessment_keys.add(assessment_key)

        raw_questions = raw_workspace.get("questions", [])
        if raw_questions is None:
            raw_questions = []
        if not isinstance(raw_questions, list):
            raise LegacyImportDataError(
                "questions for {} must be an array".format(assessment_key)
            )
        workspace_time = _timestamp(
            raw_workspace.get("updated_at"),
            _timestamp(raw_workspace.get("created_at"), imported_at),
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
            fallback_time = _timestamp(
                raw_question.get("updated_at"),
                _timestamp(raw_question.get("created_at"), workspace_time),
            )
            (
                raw_topic,
                raw_topic_mapping,
                suggested_normalized,
                inconsistent,
                candidates,
            ) = _prepare_candidates(
                snapshot,
                raw_question,
                question_key,
                fallback_time,
                issues,
            )
            prepared_questions.append(
                _PreparedQuestion(
                    assessment_legacy_key=assessment_key,
                    question_legacy_key=question_key,
                    raw_question_id=raw_question_id,
                    ordinal=position + 1,
                    question_text=question_text,
                    raw_topic=raw_topic,
                    raw_topic_mapping=raw_topic_mapping,
                    suggested_normalized_label=suggested_normalized,
                    inconsistent_accepted_mapping=inconsistent,
                    candidates=candidates,
                )
            )

        prepared.append(
            _PreparedWorkspace(
                assessment_legacy_key=assessment_key,
                questions=tuple(prepared_questions),
            )
        )
    return tuple(prepared)


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


def _resolve_question_target(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    legacy_key: str,
    assessment_target_id: str,
) -> str:
    rows = connection.execute(
        "SELECT DISTINCT mi.target_id, q.assessment_id "
        "FROM migration_imports AS mi "
        "JOIN questions AS q ON q.id = mi.target_id "
        "WHERE mi.source_path = ? AND mi.source_hash = ? "
        "AND mi.source_type = ? AND mi.source_version = ? "
        "AND mi.legacy_key = ? AND mi.target_table = 'questions' "
        "AND q.deleted_at IS NULL",
        (
            QUESTION_SOURCE_PATH,
            snapshot.source_hash,
            snapshot.source_type,
            snapshot.source_version,
            legacy_key,
        ),
    ).fetchall()
    candidates = {(str(row[0]), str(row[1])) for row in rows}
    if not candidates:
        raise LegacyImportDataError(
            "unresolved {}; import questions/sources for this snapshot first"
            .format(legacy_key)
        )
    if len(candidates) > 1:
        raise LegacyImportDataError(
            "ambiguous imported question mapping for {}".format(legacy_key)
        )
    question_target_id, actual_assessment_id = next(iter(candidates))
    if actual_assessment_id != assessment_target_id:
        raise LegacyImportDataError(
            "question {} resolves to the wrong assessment".format(legacy_key)
        )
    return question_target_id


def _assessment_course_id(
    connection: sqlite3.Connection,
    assessment_target_id: str,
) -> str:
    row = connection.execute(
        "SELECT course_id FROM assessments WHERE id = ? AND deleted_at IS NULL",
        (assessment_target_id,),
    ).fetchone()
    if row is None:
        raise LegacyImportError(
            "assessment target is missing or deleted: {}".format(
                assessment_target_id
            )
        )
    return str(row[0])


def _topic_candidates(
    connection: sqlite3.Connection,
    course_target_id: str,
    normalized_label: str,
) -> Tuple[str, ...]:
    rows = connection.execute(
        "SELECT DISTINCT mi.target_id "
        "FROM migration_imports AS mi "
        "JOIN topics AS t ON t.id = mi.target_id "
        "WHERE mi.source_path = ? "
        "AND mi.source_type = 'legacy_json' "
        "AND mi.target_table = 'topics' "
        "AND t.course_id = ? AND t.normalized_name = ? "
        "AND t.deleted_at IS NULL",
        (COURSE_SOURCE_PATH, course_target_id, normalized_label),
    ).fetchall()
    return tuple(sorted({str(row[0]) for row in rows}))


def _mapping_disposition(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot: LegacySourceSnapshot,
    candidate: _PreparedCandidate,
) -> str:
    identity = build_import_identity(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        source_type=snapshot.source_type,
        source_version=snapshot.source_version,
        legacy_key=candidate.legacy_key,
        target_table="question_topic_mappings",
    )
    existing = ledger.find(identity)
    target_exists = connection.execute(
        "SELECT 1 FROM question_topic_mappings WHERE id = ?",
        (candidate.target_id,),
    ).fetchone()
    if existing is not None:
        if existing.target_id != candidate.target_id:
            ledger.record_snapshot_import(
                snapshot,
                legacy_key=candidate.legacy_key,
                target_table="question_topic_mappings",
                target_id=candidate.target_id,
            )
        if target_exists is None:
            raise LegacyImportError(
                "migration ledger points to a missing question topic mapping: {}"
                .format(candidate.target_id)
            )
        return "matched"
    return "updated" if target_exists is not None else "created"


def _record_observation(
    connection: sqlite3.Connection,
    ledger: MigrationImportLedger,
    snapshot: LegacySourceSnapshot,
    *,
    question: _PreparedQuestion,
    question_target_id: str,
    course_target_id: str,
    resolution_details: Tuple[Mapping[str, Any], ...],
    imported_at: str,
) -> str:
    observation_key = "{}/topic_mapping:observation".format(
        question.question_legacy_key
    )
    identity = build_import_identity(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        source_type=snapshot.source_type,
        source_version=snapshot.source_version,
        legacy_key=observation_key,
        target_table="questions",
    )
    existing = ledger.find(identity)
    if existing is not None:
        if existing.target_id != question_target_id:
            ledger.record_snapshot_import(
                snapshot,
                legacy_key=observation_key,
                target_table="questions",
                target_id=question_target_id,
            )
        target_exists = connection.execute(
            "SELECT 1 FROM questions WHERE id = ?",
            (question_target_id,),
        ).fetchone()
        if target_exists is None:
            raise LegacyImportError(
                "topic-mapping observation points to a missing question: {}"
                .format(question_target_id)
            )
        return "matched"

    ledger.record_snapshot_import(
        snapshot,
        legacy_key=observation_key,
        target_table="questions",
        target_id=question_target_id,
        details={
            "kind": "question_topic_mapping_observation",
            "question_legacy_key": question.question_legacy_key,
            "course_target_id": course_target_id,
            "raw_topic": question.raw_topic,
            "raw_topic_mapping": (
                dict(question.raw_topic_mapping)
                if question.raw_topic_mapping is not None
                else None
            ),
            "candidate_resolutions": [
                dict(item) for item in resolution_details
            ],
        },
        imported_at=imported_at,
    )
    return "created"


def import_question_topic_mappings(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> QuestionTopicMappingImportResult:
    """Import one verified question-topic mapping snapshot transactionally."""
    ensure_tables(connection, REQUIRED_TABLES)
    data = load_verified_json(snapshot, expected_kind="object")
    if snapshot.canonical_path != SOURCE_PATH:
        raise LegacyImportDataError(
            "question topic mappings importer requires {}".format(SOURCE_PATH)
        )
    imported_at = str(imported_at).strip()
    if not imported_at:
        raise LegacyImportDataError("imported_at must not be empty")

    issues: List[ImportIssue] = []
    prepared = _prepare_workspaces(snapshot, data, imported_at, issues)
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
        "mapping_observations": {},
        "question_topic_mappings": {},
    }
    review_items: List[QuestionTopicMappingReviewItem] = []
    questions_scanned = 0
    accepted_mappings = 0
    proposed_mappings = 0
    unmapped_questions = 0
    unresolved_candidates = 0
    ledger = MigrationImportLedger(connection)

    with transaction(connection, immediate=True):
        for workspace in prepared:
            assessment_target_id = _resolve_assessment_target(
                connection,
                workspace.assessment_legacy_key,
            )
            course_target_id = _assessment_course_id(
                connection,
                assessment_target_id,
            )
            for question in workspace.questions:
                questions_scanned += 1
                question_target_id = _resolve_question_target(
                    connection,
                    snapshot,
                    question.question_legacy_key,
                    assessment_target_id,
                )
                resolved_for_question = 0
                resolution_details: List[Mapping[str, Any]] = []

                if not question.candidates:
                    unmapped_questions += 1
                    issues.append(
                        ImportIssue(
                            severity="warning",
                            code="question_topic_mapping_missing",
                            message=(
                                "Question has no legacy topic tag or mapping "
                                "candidate; no topic was inferred from its text."
                            ),
                            legacy_key=question.question_legacy_key,
                        )
                    )
                    review_items.append(
                        QuestionTopicMappingReviewItem(
                            assessment_legacy_key=(
                                question.assessment_legacy_key
                            ),
                            question_legacy_key=question.question_legacy_key,
                            question_target_id=question_target_id,
                            ordinal=question.ordinal,
                            question_text=question.question_text,
                            raw_topic_label="",
                            normalized_topic_label="",
                            candidate_rank=None,
                            proposed_state="unmapped",
                            reason="no_legacy_topic_mapping",
                        )
                    )

                for candidate in question.candidates:
                    topic_targets = _topic_candidates(
                        connection,
                        course_target_id,
                        candidate.normalized_label,
                    )
                    resolution_state = "resolved"
                    if not topic_targets:
                        resolution_state = "unresolved"
                    elif len(topic_targets) > 1:
                        resolution_state = "ambiguous"
                    resolution_details.append(
                        {
                            "legacy_key": candidate.legacy_key,
                            "raw_label": candidate.raw_label,
                            "normalized_label": candidate.normalized_label,
                            "state": candidate.state,
                            "resolution": resolution_state,
                            "target_ids": list(topic_targets),
                        }
                    )

                    if resolution_state != "resolved":
                        unresolved_candidates += 1
                        code = (
                            "ambiguous_question_topic_label"
                            if resolution_state == "ambiguous"
                            else "unresolved_question_topic_label"
                        )
                        issues.append(
                            ImportIssue(
                                severity="warning",
                                code=code,
                                message=(
                                    "Question topic label {!r} did not resolve "
                                    "to exactly one imported topic in the "
                                    "assessment course; no foreign key was guessed."
                                ).format(candidate.raw_label),
                                legacy_key=candidate.legacy_key,
                            )
                        )
                        review_items.append(
                            QuestionTopicMappingReviewItem(
                                assessment_legacy_key=(
                                    question.assessment_legacy_key
                                ),
                                question_legacy_key=(
                                    question.question_legacy_key
                                ),
                                question_target_id=question_target_id,
                                ordinal=question.ordinal,
                                question_text=question.question_text,
                                raw_topic_label=candidate.raw_label,
                                normalized_topic_label=(
                                    candidate.normalized_label
                                ),
                                candidate_rank=candidate.rank,
                                proposed_state=candidate.state,
                                reason="{}_topic_label".format(
                                    resolution_state
                                ),
                            )
                        )
                        continue

                    topic_target_id = topic_targets[0]
                    resolved_for_question += 1
                    disposition = _mapping_disposition(
                        connection,
                        ledger,
                        snapshot,
                        candidate,
                    )
                    if disposition != "matched":
                        connection.execute(
                            "INSERT INTO question_topic_mappings "
                            "(id, question_id, topic_id, score, rank, method, "
                            "state, reason, created_at, reviewed_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(id) DO UPDATE SET "
                            "question_id = excluded.question_id, "
                            "topic_id = excluded.topic_id, "
                            "score = excluded.score, rank = excluded.rank, "
                            "method = excluded.method, state = excluded.state, "
                            "reason = excluded.reason, "
                            "reviewed_at = excluded.reviewed_at",
                            (
                                candidate.target_id,
                                question_target_id,
                                topic_target_id,
                                candidate.score,
                                candidate.rank,
                                candidate.method,
                                candidate.state,
                                candidate.reason,
                                candidate.created_at,
                                candidate.reviewed_at,
                            ),
                        )
                        ledger.record_snapshot_import(
                            snapshot,
                            legacy_key=candidate.legacy_key,
                            target_table="question_topic_mappings",
                            target_id=candidate.target_id,
                            details={
                                "kind": "question_topic_mapping",
                                "question_legacy_key": (
                                    question.question_legacy_key
                                ),
                                "question_target_id": question_target_id,
                                "course_target_id": course_target_id,
                                "topic_target_id": topic_target_id,
                                "raw_label": candidate.raw_label,
                                "normalized_label": (
                                    candidate.normalized_label
                                ),
                                "origins": list(candidate.origins),
                                "raw_candidate": dict(
                                    candidate.raw_candidate
                                ),
                                "raw_topic": question.raw_topic,
                                "raw_topic_mapping": (
                                    dict(question.raw_topic_mapping)
                                    if question.raw_topic_mapping is not None
                                    else None
                                ),
                                "resolution": "exact_course_topic_name",
                            },
                            imported_at=imported_at,
                        )
                    add_tally(
                        counters["question_topic_mappings"],
                        disposition,
                    )

                    if candidate.state == "accepted":
                        accepted_mappings += 1
                    else:
                        proposed_mappings += 1

                    review_reason = ""
                    if (
                        question.inconsistent_accepted_mapping
                        and (
                            candidate.normalized_label
                            == question.suggested_normalized_label
                            or (
                                not question.suggested_normalized_label
                                and candidate.state == "accepted"
                            )
                        )
                    ):
                        review_reason = "inconsistent_accepted_mapping"
                    elif candidate.state == "proposed":
                        review_reason = "pending_legacy_suggestion"

                    if review_reason:
                        issues.append(
                            ImportIssue(
                                severity="warning",
                                code="question_topic_mapping_review_required",
                                message=(
                                    "Resolved legacy topic candidate remains "
                                    "review-required; it was not silently accepted."
                                ),
                                legacy_key=candidate.legacy_key,
                            )
                        )
                        review_items.append(
                            QuestionTopicMappingReviewItem(
                                assessment_legacy_key=(
                                    question.assessment_legacy_key
                                ),
                                question_legacy_key=(
                                    question.question_legacy_key
                                ),
                                question_target_id=question_target_id,
                                ordinal=question.ordinal,
                                question_text=question.question_text,
                                raw_topic_label=candidate.raw_label,
                                normalized_topic_label=(
                                    candidate.normalized_label
                                ),
                                candidate_rank=candidate.rank,
                                proposed_state=candidate.state,
                                reason=review_reason,
                            )
                        )

                if question.candidates and resolved_for_question == 0:
                    unmapped_questions += 1

                observation_disposition = _record_observation(
                    connection,
                    ledger,
                    snapshot,
                    question=question,
                    question_target_id=question_target_id,
                    course_target_id=course_target_id,
                    resolution_details=tuple(resolution_details),
                    imported_at=imported_at,
                )
                add_tally(
                    counters["mapping_observations"],
                    observation_disposition,
                )

        # TOCTOU guard: a source change during the transaction aborts everything.
        source_sha256(snapshot)

    return QuestionTopicMappingImportResult(
        source_path=snapshot.canonical_path,
        source_hash=snapshot.source_hash,
        questions_scanned=questions_scanned,
        mapping_observations=freeze_tally(counters["mapping_observations"]),
        question_topic_mappings=freeze_tally(
            counters["question_topic_mappings"]
        ),
        accepted_mappings=accepted_mappings,
        proposed_mappings=proposed_mappings,
        unmapped_questions=unmapped_questions,
        unresolved_candidates=unresolved_candidates,
        review_items=tuple(review_items),
        issues=tuple(issues),
    )


def import_topic_mappings(
    connection: sqlite3.Connection,
    snapshot: LegacySourceSnapshot,
    *,
    imported_at: str,
) -> QuestionTopicMappingImportResult:
    """Compatibility alias for :func:`import_question_topic_mappings`."""
    return import_question_topic_mappings(
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


def render_question_topic_mapping_review_markdown(
    result: QuestionTopicMappingImportResult,
) -> str:
    """Render a portable mapping review report without writing a file."""
    lines = [
        "# Question Topic Mapping Review",
        "",
        "- Source: `{}`".format(_markdown_cell(result.source_path)),
        "- Source SHA-256: `{}`".format(result.source_hash),
        "- Questions scanned: {}".format(result.questions_scanned),
        "- Accepted mappings: {}".format(result.accepted_mappings),
        "- Proposed mappings: {}".format(result.proposed_mappings),
        "- Unmapped questions: {}".format(result.unmapped_questions),
        "- Unresolved candidates: {}".format(result.unresolved_candidates),
        "- Review-required questions: {}".format(
            result.review_required_questions
        ),
        "",
    ]
    if not result.review_items:
        lines.append("No question topic mappings require review.")
        return "\n".join(lines) + "\n"

    lines.extend(
        (
            "| Assessment | Question | Ordinal | Raw question unit | "
            "Raw topic label | Rank | State | Review reason |",
            "|---|---|---:|---|---|---:|---|---|",
        )
    )
    for item in result.review_items:
        rank = item.candidate_rank if item.candidate_rank is not None else "n/a"
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                _markdown_cell(item.assessment_legacy_key),
                _markdown_cell(item.question_legacy_key),
                item.ordinal,
                _markdown_cell(item.question_text),
                _markdown_cell(item.raw_topic_label or "not recorded"),
                rank,
                _markdown_cell(item.proposed_state),
                _markdown_cell(item.reason),
            )
        )
    return "\n".join(lines) + "\n"


def render_topic_mapping_review_markdown(
    result: QuestionTopicMappingImportResult,
) -> str:
    """Compatibility alias for the complete review renderer name."""
    return render_question_topic_mapping_review_markdown(result)


__all__ = (
    "QuestionTopicMappingImportResult",
    "QuestionTopicMappingReviewItem",
    "QuestionTopicMappingsImportResult",
    "import_question_topic_mappings",
    "import_topic_mappings",
    "render_question_topic_mapping_review_markdown",
    "render_topic_mapping_review_markdown",
)
