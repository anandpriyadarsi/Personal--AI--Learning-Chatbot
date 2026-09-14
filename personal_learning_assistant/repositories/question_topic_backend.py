"""Legacy-authoritative Phase 4.4 Question <-> Topic mapping dual-read backend.

The application still writes mapping decisions through ``automatic_topic_mapping.py``
and the existing question workspace.  This module only observes those stored decisions,
compares them with the Phase 3 SQLite shadow, and always returns the legacy workspace.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.json.question_topic_mapping_repository import (
    LegacyJsonQuestionTopicMappingRepository,
)
from personal_learning_assistant.repositories.sqlite.question_topic_mapping_repository import (
    SQLiteQuestionTopicMappingRepository,
)


@dataclass(frozen=True)
class QuestionTopicBackendConfig:
    mode: str = "legacy"

    def __post_init__(self):
        normalized = str(self.mode or "").strip().lower().replace("-", "_")
        if normalized not in {"legacy", "dual_read"}:
            raise ValueError(
                "Phase 4.4 mapping backend must be 'legacy' or 'dual_read'."
            )
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class QuestionTopicParityDiagnostic:
    domain: str
    status: str
    key: str
    severity: str
    legacy_value: Any
    sqlite_value: Any
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "status": self.status,
            "key": self.key,
            "severity": self.severity,
            "legacy_value": deepcopy(self.legacy_value),
            "sqlite_value": deepcopy(self.sqlite_value),
            "message": self.message,
        }


@dataclass(frozen=True)
class QuestionTopicParityReport:
    operation: str
    diagnostics: Tuple[QuestionTopicParityDiagnostic, ...]

    @property
    def mismatch_count(self) -> int:
        return sum(item.status in {"mismatch", "error"} for item in self.diagnostics)

    @property
    def deferred_count(self) -> int:
        return sum(item.status == "deferred" for item in self.diagnostics)

    @property
    def status(self) -> str:
        if self.mismatch_count:
            return "mismatch"
        if self.deferred_count:
            return "pass_with_deferred"
        return "pass"

    @property
    def is_semantically_equal(self) -> bool:
        return self.mismatch_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "is_semantically_equal": self.is_semantically_equal,
            "mismatch_count": self.mismatch_count,
            "deferred_count": self.deferred_count,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


DiagnosticSink = Callable[[QuestionTopicParityReport], None]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_label(value: Any) -> str:
    return _clean_text(value).casefold()


def _score(value: Any) -> Optional[float]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        return None
    return float(parsed)


def _method(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "legacy_topic_mapping"


def _confidence(value: Any) -> str:
    if value is None or value == "" or isinstance(value, (dict, list, bool)):
        return ""
    return _clean_text(value).casefold()


def _accepted(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _timestamp(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _candidate_reason(origins: Tuple[str, ...], confidence: str, score_conflict: bool) -> str:
    parts = ["legacy {}".format(" + ".join(origins))]
    if confidence:
        parts.append("confidence={}".format(confidence))
    if score_conflict:
        parts.append("conflicting raw scores; primary suggestion score retained")
    return "; ".join(parts)


def _legacy_candidates(record: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    raw_topic = record.get("topic") if isinstance(record.get("topic"), str) else ""
    direct_normalized = _normalized_label(raw_topic) if str(raw_topic).strip() else ""
    raw_mapping = record.get("topic_mapping")
    mapping = raw_mapping if isinstance(raw_mapping, Mapping) else {}

    suggested = mapping.get("suggested_topic") if isinstance(mapping.get("suggested_topic"), str) else ""
    suggested_normalized = _normalized_label(suggested) if str(suggested).strip() else ""
    method = _method(mapping.get("method"))
    confidence = _confidence(mapping.get("confidence"))
    accepted = _accepted(mapping.get("accepted"))
    fallback = _timestamp(
        record.get("updated_at"),
        _timestamp(record.get("created_at"), record.get("workspace_time", "")),
    )
    mapped_at = _timestamp(mapping.get("mapped_at"), fallback)

    raw_alternatives = mapping.get("alternatives", [])
    if not isinstance(raw_alternatives, list):
        raw_alternatives = []

    mutable: Dict[str, Dict[str, Any]] = {}
    for position, candidate in enumerate(raw_alternatives):
        if not isinstance(candidate, Mapping):
            continue
        label = candidate.get("topic") if isinstance(candidate.get("topic"), str) else ""
        if not label.strip():
            continue
        normalized = _normalized_label(label)
        if normalized in mutable:
            continue
        mutable[normalized] = {
            "raw_label": label,
            "score": _score(candidate.get("score")),
            "rank": position + 1,
            "origins": ["alternative"],
            "score_conflict": False,
        }

    suggested_score = _score(mapping.get("score"))
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
                "score_conflict": False,
            }

    prepared: List[Dict[str, Any]] = []
    for normalized, candidate in mutable.items():
        origins = tuple(candidate["origins"])
        mapping_origin = bool({"suggested", "alternative"}.intersection(origins))
        state = (
            "accepted"
            if normalized == direct_normalized or (accepted and normalized == suggested_normalized)
            else "proposed"
        )
        created_at = mapped_at if mapping_origin else fallback
        prepared.append(
            {
                "assessment_id": record["assessment_id"],
                "question_id": record["question_id"],
                "raw_label": candidate["raw_label"],
                "normalized_label": normalized,
                "score": candidate["score"],
                "rank": candidate["rank"],
                "method": method if mapping_origin else "legacy_manual_topic",
                "state": state,
                "reason": _candidate_reason(
                    origins,
                    confidence,
                    bool(candidate["score_conflict"]),
                ),
                "created_at": created_at,
                "reviewed_at": created_at if state == "accepted" else None,
            }
        )

    prepared.sort(
        key=lambda item: (
            item["rank"] is None,
            item["rank"] if item["rank"] is not None else 0,
            item["normalized_label"],
        )
    )
    return tuple(prepared)


def _read_hash(repository: Any) -> Tuple[Optional[str], Optional[str]]:
    path_value = getattr(repository, "path", None)
    if path_value is None:
        return None, "legacy mapping repository does not expose a source path"
    path = Path(path_value)
    if not path.exists():
        return hashlib.sha256(b"").hexdigest(), None
    try:
        payload = path.read_bytes()
    except OSError as error:
        return None, "unable to read legacy mapping source: {}".format(error)
    return hashlib.sha256(payload).hexdigest(), None


def _legacy_snapshot(repository: Any, state: Mapping[str, Any]) -> Dict[str, Any]:
    workspaces = state.get("workspaces", {})
    if not isinstance(workspaces, Mapping):
        workspaces = {}

    observations: List[Dict[str, Any]] = []
    records: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    accepted_topics: List[Tuple[str, str, Any]] = []
    suggestions: List[Tuple[str, str, Any]] = []

    for workspace_key, workspace in workspaces.items():
        if not isinstance(workspace, Mapping):
            continue
        assessment_id = str(workspace.get("assessment_id") or workspace_key)
        workspace_time = _timestamp(
            workspace.get("updated_at"), _timestamp(workspace.get("created_at"), "")
        )
        questions = workspace.get("questions", [])
        if not isinstance(questions, list):
            continue
        for item in questions:
            if not isinstance(item, Mapping):
                continue
            question_id = str(item.get("id") or "")
            raw_mapping = deepcopy(item.get("topic_mapping"))
            raw_topic = deepcopy(item.get("topic"))
            observation = {
                "assessment_id": assessment_id,
                "question_id": question_id,
                "raw_topic": raw_topic,
                "raw_topic_mapping": raw_mapping,
            }
            observations.append(observation)
            accepted_topics.append((assessment_id, question_id, raw_topic))
            suggested = raw_mapping.get("suggested_topic") if isinstance(raw_mapping, Mapping) else None
            suggestions.append((assessment_id, question_id, deepcopy(suggested)))
            record = {
                "assessment_id": assessment_id,
                "question_id": question_id,
                "topic": raw_topic,
                "topic_mapping": raw_mapping,
                "created_at": deepcopy(item.get("created_at")),
                "updated_at": deepcopy(item.get("updated_at")),
                "workspace_time": workspace_time,
            }
            records.append(record)
            candidates.extend(_legacy_candidates(record))

    source_hash, hash_error = _read_hash(repository)
    return {
        "source_version": state.get("version", 1),
        "source_hash": source_hash,
        "raw_mapping_observations": tuple(observations),
        "accepted_topics": tuple(accepted_topics),
        "suggested_topics": tuple(suggestions),
        "expected_candidates": tuple(candidates),
        "hash_error": hash_error,
    }


def _resolution_lookup(sqlite_snapshot: Mapping[str, Any]) -> Dict[Tuple[str, str, str], str]:
    lookup: Dict[Tuple[str, str, str], str] = {}
    for observation in sqlite_snapshot.get("raw_mapping_observations", ()):
        if not isinstance(observation, Mapping):
            continue
        assessment_id = str(observation.get("assessment_id", ""))
        question_id = str(observation.get("question_id", ""))
        resolutions = observation.get("candidate_resolutions", [])
        if not isinstance(resolutions, list):
            continue
        for item in resolutions:
            if not isinstance(item, Mapping):
                continue
            normalized = _normalized_label(item.get("normalized_label"))
            if normalized:
                lookup[(assessment_id, question_id, normalized)] = str(
                    item.get("resolution", "")
                )
    return lookup


def _resolved_expected_candidates(
    legacy_snapshot: Mapping[str, Any], sqlite_snapshot: Mapping[str, Any]
) -> Tuple[Dict[str, Any], ...]:
    resolution = _resolution_lookup(sqlite_snapshot)
    result = []
    for item in legacy_snapshot.get("expected_candidates", ()):
        key = (
            str(item.get("assessment_id", "")),
            str(item.get("question_id", "")),
            str(item.get("normalized_label", "")),
        )
        if resolution.get(key) == "resolved":
            result.append(deepcopy(dict(item)))
    result.sort(
        key=lambda item: (
            item["assessment_id"],
            item["question_id"],
            item["rank"] is None,
            item["rank"] if item["rank"] is not None else 0,
            item["normalized_label"],
        )
    )
    return tuple(result)


def _actual_candidate_projection(sqlite_snapshot: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    result = []
    for item in sqlite_snapshot.get("current_mapping_rows", ()):
        projected = {
            key: deepcopy(item.get(key))
            for key in (
                "assessment_id",
                "question_id",
                "raw_label",
                "normalized_label",
                "score",
                "rank",
                "method",
                "state",
                "reason",
                "created_at",
                "reviewed_at",
            )
        }
        result.append(projected)
    return tuple(result)


def _diagnostic(
    domain: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    message: Optional[str] = None,
) -> QuestionTopicParityDiagnostic:
    equal = legacy_value == sqlite_value
    return QuestionTopicParityDiagnostic(
        domain=domain,
        status="matched" if equal else "mismatch",
        key="",
        severity="info" if equal else "error",
        legacy_value=deepcopy(legacy_value),
        sqlite_value=deepcopy(sqlite_value),
        message=message
        or (
            "Legacy and SQLite mapping semantics match."
            if equal
            else "Legacy and SQLite mapping semantics differ; the mismatch was not normalized away."
        ),
    )


def compare_question_topic_parity(
    legacy_repository: Any,
    legacy_state: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_state",
) -> QuestionTopicParityReport:
    legacy = _legacy_snapshot(legacy_repository, legacy_state)
    sqlite_observations = tuple(
        {
            "assessment_id": item.get("assessment_id"),
            "question_id": item.get("question_id"),
            "raw_topic": deepcopy(item.get("raw_topic")),
            "raw_topic_mapping": deepcopy(item.get("raw_topic_mapping")),
        }
        for item in sqlite_snapshot.get("raw_mapping_observations", ())
    )
    diagnostics: List[QuestionTopicParityDiagnostic] = [
        _diagnostic(
            "raw_mapping_observations",
            legacy["raw_mapping_observations"],
            sqlite_observations,
            message=(
                "Exact stored topic/topic_mapping evidence is compared without rerunning the heuristic mapper."
                if legacy["raw_mapping_observations"] != sqlite_observations
                else None
            ),
        ),
        _diagnostic(
            "source_version",
            legacy["source_version"],
            sqlite_snapshot.get("source_version"),
        ),
        _diagnostic(
            "source_hash",
            legacy["source_hash"],
            sqlite_snapshot.get("source_hash"),
        ),
        _diagnostic(
            "resolved_mapping_semantics",
            _resolved_expected_candidates(legacy, sqlite_snapshot),
            _actual_candidate_projection(sqlite_snapshot),
            message="Resolved accepted/proposed mapping rows, ranks, scores, methods, state, reason, and review timestamps are compared directly.",
        ),
    ]

    if legacy.get("hash_error"):
        diagnostics.append(
            QuestionTopicParityDiagnostic(
                domain="legacy_mapping_source",
                status="error",
                key="",
                severity="error",
                legacy_value=legacy["hash_error"],
                sqlite_value=None,
                message="Legacy mapping source could not be hashed safely.",
            )
        )

    anomalies = tuple(sqlite_snapshot.get("anomalies", ()))
    diagnostics.append(
        QuestionTopicParityDiagnostic(
            domain="sqlite_structure",
            status="matched" if not anomalies else "mismatch",
            key="",
            severity="info" if not anomalies else "error",
            legacy_value=(),
            sqlite_value=anomalies,
            message=(
                "Question/topic ownership, course boundaries, current ledgers, ranks, and target existence are structurally valid."
                if not anomalies
                else "SQLite question-topic structural anomalies were detected explicitly."
            ),
        )
    )

    unresolved = []
    for observation in sqlite_snapshot.get("raw_mapping_observations", ()):
        for item in observation.get("candidate_resolutions", ()) if isinstance(observation, Mapping) else ():
            if isinstance(item, Mapping) and str(item.get("resolution", "")) != "resolved":
                unresolved.append(deepcopy(dict(item)))
    if unresolved:
        diagnostics.append(
            QuestionTopicParityDiagnostic(
                domain="unresolved_mapping_candidates",
                status="deferred",
                key="",
                severity="info",
                legacy_value="raw candidate evidence retained",
                sqlite_value=tuple(unresolved),
                message="Unresolved/ambiguous legacy candidates remain reviewable and are not guessed into topic foreign keys.",
            )
        )

    historical = tuple(sqlite_snapshot.get("historical_mapping_rows", ()))
    if historical:
        diagnostics.append(
            QuestionTopicParityDiagnostic(
                domain="historical_mapping_rows",
                status="deferred",
                key="",
                severity="info",
                legacy_value="current snapshot does not delete prior mapping history",
                sqlite_value=historical,
                message="Older retained mapping rows are preserved as history and are not promoted to current legacy authority.",
            )
        )

    return QuestionTopicParityReport(operation=operation, diagnostics=tuple(diagnostics))


class DualReadQuestionTopicMappingRepository:
    """Return legacy workspace state while independently observing SQLite parity."""

    def __init__(
        self,
        legacy_repository: Any,
        sqlite_repository: SQLiteQuestionTopicMappingRepository,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ):
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._diagnostic_sink = diagnostic_sink
        self._reports: List[QuestionTopicParityReport] = []

    @property
    def last_report(self) -> Optional[QuestionTopicParityReport]:
        return self._reports[-1] if self._reports else None

    @property
    def reports(self) -> Tuple[QuestionTopicParityReport, ...]:
        return tuple(self._reports)

    def _record(self, report: QuestionTopicParityReport) -> None:
        self._reports.append(report)
        if self._diagnostic_sink is not None:
            try:
                self._diagnostic_sink(report)
            except Exception:
                pass

    def load_state(self):
        legacy_state = self.legacy_repository.load_state()
        try:
            snapshot = self.sqlite_repository.parity_snapshot()
            self._record(
                compare_question_topic_parity(
                    self.legacy_repository,
                    legacy_state,
                    snapshot,
                    operation="load_state",
                )
            )
        except Exception as error:
            self._record(
                QuestionTopicParityReport(
                    operation="load_state",
                    diagnostics=(
                        QuestionTopicParityDiagnostic(
                            domain="sqlite_read",
                            status="error",
                            key="",
                            severity="error",
                            legacy_value="authoritative legacy result returned",
                            sqlite_value=type(error).__name__,
                            message="SQLite mapping shadow read failed: {}".format(error),
                        ),
                    ),
                )
            )
        return deepcopy(legacy_state)

    def save_state(self, state):
        return self.legacy_repository.save_state(state)


def build_question_topic_mapping_repository(
    config: Union[QuestionTopicBackendConfig, str] = QuestionTopicBackendConfig(),
    *,
    legacy_repository: Optional[Any] = None,
    legacy_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteQuestionTopicMappingRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    selected = config if isinstance(config, QuestionTopicBackendConfig) else QuestionTopicBackendConfig(config)
    legacy = legacy_repository or LegacyJsonQuestionTopicMappingRepository(path=legacy_path)
    if selected.mode == "legacy":
        return legacy
    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteQuestionTopicMappingRepository(sqlite_connection)
    return DualReadQuestionTopicMappingRepository(
        legacy,
        shadow,
        diagnostic_sink=diagnostic_sink,
    )


create_question_topic_mapping_repository = build_question_topic_mapping_repository


__all__ = (
    "DualReadQuestionTopicMappingRepository",
    "QuestionTopicBackendConfig",
    "QuestionTopicParityDiagnostic",
    "QuestionTopicParityReport",
    "build_question_topic_mapping_repository",
    "compare_question_topic_parity",
    "create_question_topic_mapping_repository",
)
