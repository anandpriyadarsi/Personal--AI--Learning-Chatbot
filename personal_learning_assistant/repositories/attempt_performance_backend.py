"""Legacy-authoritative Phase 4.5 Attempts + Mistakes + Performance dual-read.

``assessment_performance.py`` and the question workspace remain the application
API and writer.  This module observes the persisted performance evidence,
compares it with the Phase 3 SQLite shadow, and always returns legacy state.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.json.attempt_performance_repository import (
    LegacyJsonAttemptPerformanceRepository,
)
from personal_learning_assistant.repositories.sqlite.attempt_performance_repository import (
    SQLiteAttemptPerformanceRepository,
)


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


@dataclass(frozen=True)
class AttemptPerformanceBackendConfig:
    mode: str = "legacy"

    def __post_init__(self):
        normalized = str(self.mode or "").strip().lower().replace("-", "_")
        if normalized not in {"legacy", "dual_read"}:
            raise ValueError(
                "Phase 4.5 performance backend must be 'legacy' or 'dual_read'."
            )
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class AttemptPerformanceParityDiagnostic:
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
class AttemptPerformanceParityReport:
    operation: str
    diagnostics: Tuple[AttemptPerformanceParityDiagnostic, ...]

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


DiagnosticSink = Callable[[AttemptPerformanceParityReport], None]


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
    value_as_float = float(parsed)
    if not math.isfinite(value_as_float):
        return _OUTCOME_WEIGHTS.get(outcome, 0.0)
    return max(0.0, min(1.0, value_as_float))


def _raw_evidence(state: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    workspaces = state.get("workspaces", {}) if isinstance(state, Mapping) else {}
    if not isinstance(workspaces, Mapping):
        return ()
    result: List[Dict[str, Any]] = []
    for workspace_key, workspace in workspaces.items():
        if not isinstance(workspace, Mapping):
            continue
        assessment_id = str(workspace.get("assessment_id") or workspace_key)
        questions = workspace.get("questions", [])
        if not isinstance(questions, list):
            continue
        for question in questions:
            if not isinstance(question, Mapping):
                continue
            result.append(
                {
                    "assessment_id": assessment_id,
                    "question_id": str(question.get("id") or ""),
                    "attempts": deepcopy(question.get("attempts")),
                    "mistakes": deepcopy(question.get("mistakes")),
                    "performance": deepcopy(question.get("performance")),
                }
            )
    return tuple(result)


def _read_hash(repository: Any) -> Tuple[Optional[str], Optional[str], Any]:
    path_value = getattr(repository, "path", None)
    if path_value is None:
        return None, "legacy performance repository does not expose a source path", None
    path = Path(path_value)
    if not path.exists():
        return hashlib.sha256(b"").hexdigest(), None, None
    try:
        payload = path.read_bytes()
        raw = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, "unable to read legacy performance source: {}".format(error), None
    return (
        hashlib.sha256(payload).hexdigest(),
        None,
        raw if isinstance(raw, dict) else None,
    )


def _attempt_sources(
    question: Mapping[str, Any],
    question_key: str,
    anomalies: List[str],
) -> Tuple[Tuple[str, Sequence[Any]], ...]:
    sources: List[Tuple[str, Sequence[Any]]] = []
    top_level = question.get("attempts")
    if top_level not in (None, ""):
        if isinstance(top_level, list):
            if top_level:
                sources.append(("attempts", top_level))
        else:
            anomalies.append("{} field attempts is not an array".format(question_key))

    performance = question.get("performance")
    if performance not in (None, ""):
        if not isinstance(performance, Mapping):
            anomalies.append("{} field performance is not an object".format(question_key))
        else:
            nested = performance.get("attempts")
            if nested not in (None, ""):
                if isinstance(nested, list):
                    if nested:
                        sources.append(("performance.attempts", nested))
                else:
                    anomalies.append(
                        "{} field performance.attempts is not an array".format(question_key)
                    )
    return tuple(sources)


def _canonical_attempts(
    state: Mapping[str, Any],
    fallback_times: Mapping[str, Any],
) -> Tuple[Tuple[Dict[str, Any], ...], Tuple[Dict[str, Any], ...], Tuple[str, ...]]:
    attempts: List[Dict[str, Any]] = []
    mistakes: List[Dict[str, Any]] = []
    anomalies: List[str] = []
    workspaces = state.get("workspaces", {}) if isinstance(state, Mapping) else {}
    if not isinstance(workspaces, Mapping):
        return (), (), ("legacy workspaces field is not an object",)

    for workspace_key, workspace in workspaces.items():
        if not isinstance(workspace, Mapping):
            anomalies.append("workspace {!r} is not an object".format(workspace_key))
            continue
        assessment_id = str(workspace.get("assessment_id") or workspace_key)
        questions = workspace.get("questions", [])
        if not isinstance(questions, list):
            anomalies.append("workspace {} questions is not an array".format(assessment_id))
            continue
        for question in questions:
            if not isinstance(question, Mapping):
                continue
            question_id = str(question.get("id") or "")
            question_key = "assessment:id:{}/question:id:{}".format(
                assessment_id, question_id
            )
            attempt_number = 0
            for origin, raw_attempts in _attempt_sources(question, question_key, anomalies):
                for origin_position, raw_attempt in enumerate(raw_attempts, start=1):
                    if not isinstance(raw_attempt, Mapping):
                        anomalies.append(
                            "{} {} attempt {} is not an object".format(
                                question_key, origin, origin_position
                            )
                        )
                        continue
                    attempt_number += 1
                    legacy_key = "{}/attempt:{}:{}".format(
                        question_key, origin, origin_position
                    )
                    outcome = _canonical_outcome(raw_attempt.get("outcome"))
                    max_raw = raw_attempt.get(
                        "max_marks",
                        raw_attempt.get("maximum_marks", question.get("marks")),
                    )
                    max_marks = _marks_milli(max_raw)
                    earned_marks = _marks_milli(raw_attempt.get("earned_marks"))
                    if (
                        earned_marks is not None
                        and max_marks is not None
                        and earned_marks > max_marks
                    ):
                        earned_marks = None
                    time_value = raw_attempt.get("time", raw_attempt.get("occurred_at"))
                    occurred_at = (
                        time_value.strip()
                        if isinstance(time_value, str) and time_value.strip()
                        else str(fallback_times.get(legacy_key, ""))
                    )
                    attempt = {
                        "legacy_key": legacy_key,
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "origin": origin,
                        "origin_position": origin_position,
                        "attempt_number": attempt_number,
                        "outcome": outcome,
                        "weight": _canonical_weight(outcome, raw_attempt.get("weight")),
                        "earned_marks_milli": earned_marks,
                        "max_marks_milli": max_marks,
                        "response_ref": _canonical_reference(
                            raw_attempt.get("response_ref", raw_attempt.get("response"))
                        ),
                        "feedback_ref": _canonical_reference(
                            raw_attempt.get("feedback_ref", raw_attempt.get("feedback"))
                        ),
                        "occurred_at": occurred_at,
                    }
                    attempts.append(attempt)
                    raw_mistake = raw_attempt.get("mistake")
                    if isinstance(raw_mistake, str) and raw_mistake.strip():
                        mistakes.append(
                            {
                                "legacy_key": legacy_key + "/mistake:legacy_attempt",
                                "assessment_id": assessment_id,
                                "question_id": question_id,
                                "attempt_legacy_key": legacy_key,
                                "category": "legacy_attempt_mistake",
                                "mistake_text": raw_mistake.strip(),
                                "created_at": occurred_at,
                                "resolved_at": None,
                            }
                        )

    attempts.sort(
        key=lambda item: (
            item["assessment_id"],
            item["question_id"],
            item["attempt_number"],
            item["legacy_key"],
        )
    )
    mistakes.sort(
        key=lambda item: (
            item["assessment_id"],
            item["question_id"],
            item["attempt_legacy_key"],
            item["legacy_key"],
        )
    )
    return tuple(attempts), tuple(mistakes), tuple(anomalies)


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _legacy_performance_summary(
    state: Mapping[str, Any],
) -> Tuple[Tuple[Dict[str, Any], ...], Tuple[str, ...]]:
    """Mirror the read semantics of assessment_performance.question_performance."""
    summaries: List[Dict[str, Any]] = []
    anomalies: List[str] = []
    workspaces = state.get("workspaces", {}) if isinstance(state, Mapping) else {}
    if not isinstance(workspaces, Mapping):
        return (), ("legacy workspaces field is not an object",)

    for workspace_key, workspace in workspaces.items():
        if not isinstance(workspace, Mapping):
            continue
        assessment_id = str(workspace.get("assessment_id") or workspace_key)
        questions = workspace.get("questions", [])
        if not isinstance(questions, list):
            continue
        for question in questions:
            if not isinstance(question, Mapping):
                continue
            question_id = str(question.get("id") or "")
            performance = question.get("performance")
            performance = performance if isinstance(performance, Mapping) else {}
            nested_attempts = performance.get("attempts", [])
            if not isinstance(nested_attempts, list):
                nested_attempts = []
            weights: List[float] = []
            outcomes = {
                "correct": 0,
                "partially_correct": 0,
                "wrong": 0,
                "stuck": 0,
            }
            earned = 0.0
            maximum = 0.0
            for index, attempt in enumerate(nested_attempts, start=1):
                if not isinstance(attempt, Mapping):
                    anomalies.append(
                        "{}/{} nested performance attempt {} is not an object".format(
                            assessment_id, question_id, index
                        )
                    )
                    continue
                outcome = attempt.get("outcome")
                default_weight = _OUTCOME_WEIGHTS.get(str(outcome), 0.0)
                try:
                    weight = float(attempt.get("weight", default_weight))
                    if not math.isfinite(weight):
                        raise ValueError
                except (TypeError, ValueError):
                    anomalies.append(
                        "{}/{} nested performance attempt {} has invalid weight".format(
                            assessment_id, question_id, index
                        )
                    )
                    weight = 0.0
                weights.append(weight)
                if outcome in outcomes:
                    outcomes[str(outcome)] += 1
                e = _float_or_none(attempt.get("earned_marks"))
                m = _float_or_none(attempt.get("max_marks"))
                if e is not None and m is not None and m > 0:
                    earned += e
                    maximum += m
            summaries.append(
                {
                    "assessment_id": assessment_id,
                    "question_id": question_id,
                    "attempts": len(nested_attempts),
                    "accuracy": sum(weights) / len(weights) if weights else 0.0,
                    "marks_accuracy": earned / maximum if maximum > 0 else None,
                    "outcomes": outcomes,
                }
            )
    summaries.sort(key=lambda item: (item["assessment_id"], item["question_id"]))
    return tuple(summaries), tuple(anomalies)


def _standalone_mistakes(state: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    deferred: List[Dict[str, Any]] = []
    workspaces = state.get("workspaces", {}) if isinstance(state, Mapping) else {}
    if not isinstance(workspaces, Mapping):
        return ()
    for workspace_key, workspace in workspaces.items():
        if not isinstance(workspace, Mapping):
            continue
        assessment_id = str(workspace.get("assessment_id") or workspace_key)
        questions = workspace.get("questions", [])
        if not isinstance(questions, list):
            continue
        for question in questions:
            if not isinstance(question, Mapping):
                continue
            question_id = str(question.get("id") or "")
            performance = question.get("performance")
            perf_mistakes = (
                performance.get("mistakes")
                if isinstance(performance, Mapping)
                else None
            )
            top_mistakes = question.get("mistakes")
            if isinstance(perf_mistakes, list) and any(perf_mistakes):
                deferred.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "origin": "performance.mistakes",
                        "value": deepcopy(perf_mistakes),
                    }
                )
            if isinstance(top_mistakes, list) and any(top_mistakes):
                deferred.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "origin": "mistakes",
                        "value": deepcopy(top_mistakes),
                    }
                )
    return tuple(deferred)


def _diagnostic(
    domain: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    message: Optional[str] = None,
) -> AttemptPerformanceParityDiagnostic:
    equal = legacy_value == sqlite_value
    return AttemptPerformanceParityDiagnostic(
        domain=domain,
        status="matched" if equal else "mismatch",
        key="",
        severity="info" if equal else "error",
        legacy_value=deepcopy(legacy_value),
        sqlite_value=deepcopy(sqlite_value),
        message=message
        or (
            "Legacy and SQLite performance semantics match."
            if equal
            else "Legacy and SQLite performance semantics differ; the mismatch was not normalized away."
        ),
    )


def compare_attempt_performance_parity(
    legacy_repository: Any,
    legacy_state: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_state",
) -> AttemptPerformanceParityReport:
    source_hash, hash_error, raw_source = _read_hash(legacy_repository)
    source_version = legacy_state.get("version", 1)
    if isinstance(raw_source, Mapping):
        source_version = raw_source.get("version", source_version)

    expected_attempts, expected_mistakes, canonical_anomalies = _canonical_attempts(
        legacy_state,
        sqlite_snapshot.get("fallback_times", {}),
    )
    legacy_summary, summary_anomalies = _legacy_performance_summary(legacy_state)

    diagnostics: List[AttemptPerformanceParityDiagnostic] = [
        _diagnostic(
            "raw_performance_evidence",
            _raw_evidence(legacy_state),
            tuple(sqlite_snapshot.get("raw_performance_evidence", ())),
            message="Exact attempts/performance/mistake JSON evidence is compared before canonical relational projection.",
        ),
        _diagnostic(
            "source_version",
            source_version,
            sqlite_snapshot.get("source_version"),
        ),
        _diagnostic("source_hash", source_hash, sqlite_snapshot.get("source_hash")),
        _diagnostic(
            "attempt_semantics_and_order",
            expected_attempts,
            tuple(sqlite_snapshot.get("current_attempt_rows", ())),
            message="Attempt origin, order, ownership, outcome, marks, references, weight evidence, and occurrence time are compared directly.",
        ),
        _diagnostic(
            "attempt_attached_mistakes",
            expected_mistakes,
            tuple(sqlite_snapshot.get("current_mistake_rows", ())),
            message="Only attempt-attached mistake strings map to mistake_events; ownership and text remain explicit.",
        ),
        _diagnostic(
            "question_performance_summary",
            legacy_summary,
            tuple(sqlite_snapshot.get("performance_summary", ())),
            message="Derived nested performance attempt counts, accuracy, marks accuracy, and outcomes are compared with current V10.4 read semantics.",
        ),
    ]

    if hash_error:
        diagnostics.append(
            AttemptPerformanceParityDiagnostic(
                domain="legacy_performance_source",
                status="error",
                key="",
                severity="error",
                legacy_value=hash_error,
                sqlite_value=None,
                message="Legacy performance source could not be hashed safely.",
            )
        )

    shape_anomalies = tuple(canonical_anomalies) + tuple(summary_anomalies)
    if shape_anomalies:
        diagnostics.append(
            AttemptPerformanceParityDiagnostic(
                domain="legacy_performance_shape",
                status="mismatch",
                key="",
                severity="error",
                legacy_value=shape_anomalies,
                sqlite_value="Phase 3 Fix 8 requires unambiguous attempt structures",
                message="Malformed legacy performance evidence is visible and is not silently repaired for parity.",
            )
        )

    sqlite_anomalies = tuple(sqlite_snapshot.get("anomalies", ()))
    diagnostics.append(
        AttemptPerformanceParityDiagnostic(
            domain="sqlite_structure",
            status="matched" if not sqlite_anomalies else "mismatch",
            key="",
            severity="info" if not sqlite_anomalies else "error",
            legacy_value=(),
            sqlite_value=sqlite_anomalies,
            message=(
                "Current attempt/question and mistake/attempt relationships are structurally valid."
                if not sqlite_anomalies
                else "SQLite attempt/performance structural anomalies were detected explicitly."
            ),
        )
    )

    standalone = _standalone_mistakes(legacy_state)
    if standalone:
        diagnostics.append(
            AttemptPerformanceParityDiagnostic(
                domain="standalone_mistakes",
                status="deferred",
                key="",
                severity="info",
                legacy_value=standalone,
                sqlite_value="not attached to guessed attempts",
                message="Standalone performance/top-level mistake lists remain legacy evidence because the SQLite schema requires a real attempt owner.",
            )
        )

    historical_attempts = tuple(sqlite_snapshot.get("historical_attempt_rows", ()))
    if historical_attempts:
        diagnostics.append(
            AttemptPerformanceParityDiagnostic(
                domain="historical_attempt_rows",
                status="deferred",
                key="",
                severity="info",
                legacy_value="current source omission is not deletion authority",
                sqlite_value=historical_attempts,
                message="Older omitted attempt rows remain migration history and are not promoted to current legacy authority.",
            )
        )
    historical_mistakes = tuple(sqlite_snapshot.get("historical_mistake_rows", ()))
    if historical_mistakes:
        diagnostics.append(
            AttemptPerformanceParityDiagnostic(
                domain="historical_mistake_rows",
                status="deferred",
                key="",
                severity="info",
                legacy_value="current source omission is not deletion authority",
                sqlite_value=historical_mistakes,
                message="Older omitted mistake rows remain migration history and are not treated as current mistakes.",
            )
        )

    return AttemptPerformanceParityReport(
        operation=operation,
        diagnostics=tuple(diagnostics),
    )


class DualReadAttemptPerformanceRepository:
    """Return legacy workspace state while independently checking SQLite parity."""

    def __init__(
        self,
        legacy_repository: Any,
        sqlite_repository: SQLiteAttemptPerformanceRepository,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ):
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._diagnostic_sink = diagnostic_sink
        self._reports: List[AttemptPerformanceParityReport] = []

    @property
    def last_report(self) -> Optional[AttemptPerformanceParityReport]:
        return self._reports[-1] if self._reports else None

    @property
    def reports(self) -> Tuple[AttemptPerformanceParityReport, ...]:
        return tuple(self._reports)

    def _record(self, report: AttemptPerformanceParityReport) -> None:
        self._reports.append(report)
        if self._diagnostic_sink is not None:
            try:
                self._diagnostic_sink(report)
            except Exception:
                # Diagnostics are observational; they cannot break an
                # authoritative legacy read.
                pass

    def load_state(self):
        legacy_state = self.legacy_repository.load_state()
        try:
            snapshot = self.sqlite_repository.parity_snapshot()
            self._record(
                compare_attempt_performance_parity(
                    self.legacy_repository,
                    legacy_state,
                    snapshot,
                    operation="load_state",
                )
            )
        except Exception as error:
            self._record(
                AttemptPerformanceParityReport(
                    operation="load_state",
                    diagnostics=(
                        AttemptPerformanceParityDiagnostic(
                            domain="sqlite_read",
                            status="error",
                            key="",
                            severity="error",
                            legacy_value="authoritative legacy result returned",
                            sqlite_value=type(error).__name__,
                            message="SQLite performance shadow read failed: {}".format(
                                error
                            ),
                        ),
                    ),
                )
            )
        return deepcopy(legacy_state)

    def save_state(self, state):
        return self.legacy_repository.save_state(state)


def build_attempt_performance_repository(
    config: Union[AttemptPerformanceBackendConfig, str] = AttemptPerformanceBackendConfig(),
    *,
    legacy_repository: Optional[Any] = None,
    legacy_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteAttemptPerformanceRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    selected = (
        config
        if isinstance(config, AttemptPerformanceBackendConfig)
        else AttemptPerformanceBackendConfig(config)
    )
    legacy = legacy_repository or LegacyJsonAttemptPerformanceRepository(path=legacy_path)
    if selected.mode == "legacy":
        return legacy
    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteAttemptPerformanceRepository(sqlite_connection)
    return DualReadAttemptPerformanceRepository(
        legacy,
        shadow,
        diagnostic_sink=diagnostic_sink,
    )


create_attempt_performance_repository = build_attempt_performance_repository


__all__ = (
    "AttemptPerformanceBackendConfig",
    "AttemptPerformanceParityDiagnostic",
    "AttemptPerformanceParityReport",
    "DualReadAttemptPerformanceRepository",
    "build_attempt_performance_repository",
    "compare_attempt_performance_parity",
    "create_attempt_performance_repository",
)
