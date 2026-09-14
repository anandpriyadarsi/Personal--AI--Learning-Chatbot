"""Phase 4.2 legacy-authoritative Assessment dual-read backend.

The repository seam is introduced without rewiring the legacy
``assignment_exam_assistant`` public functions.  ``legacy`` and ``dual_read``
are the only supported modes; SQLite is observation-only in Phase 4.2.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.json.assessment_repository import (
    LegacyJsonAssessmentRepository,
)
from personal_learning_assistant.repositories.sqlite.assessment_repository import (
    SQLiteAssessmentRepository,
)


@dataclass(frozen=True)
class AssessmentBackendConfig:
    mode: str = "legacy"

    def __post_init__(self):
        normalized = str(self.mode or "").strip().lower().replace("-", "_")
        if normalized not in {"legacy", "dual_read"}:
            raise ValueError(
                "Phase 4.2 assessment backend must be 'legacy' or 'dual_read'."
            )
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class AssessmentParityDiagnostic:
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
class AssessmentParityReport:
    operation: str
    diagnostics: Tuple[AssessmentParityDiagnostic, ...]

    @property
    def mismatch_count(self) -> int:
        return sum(item.status in {"mismatch", "error"} for item in self.diagnostics)

    @property
    def deferred_count(self) -> int:
        return sum(item.status == "deferred" for item in self.diagnostics)

    @property
    def is_semantically_equal(self) -> bool:
        return self.mismatch_count == 0

    @property
    def status(self) -> str:
        if self.mismatch_count:
            return "mismatch"
        if self.deferred_count:
            return "pass_with_deferred"
        return "pass"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "is_semantically_equal": self.is_semantically_equal,
            "mismatch_count": self.mismatch_count,
            "deferred_count": self.deferred_count,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


DiagnosticSink = Callable[[AssessmentParityReport], None]


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _float_or_none(value: Any):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_raw_source(repository: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    path_value = getattr(repository, "path", None)
    if path_value is None:
        return None, None, "legacy repository does not expose a source path"
    path = Path(path_value)
    if not path.exists():
        return {}, hashlib.sha256(b"").hexdigest(), None
    try:
        payload = path.read_bytes()
        raw = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, None, "unable to read raw legacy assessment evidence: {}".format(error)
    if not isinstance(raw, dict):
        return None, hashlib.sha256(payload).hexdigest(), "raw legacy assessments source is not a JSON object"
    return raw, hashlib.sha256(payload).hexdigest(), None


def _field_alias_evidence(item: Mapping[str, Any]) -> Dict[str, Any]:
    pairs = (
        ("type", "assessment_type"),
        ("due_date", "due_on"),
        ("weightage_percent", "weight"),
        ("total_marks", "max_score"),
        ("obtained_marks", "score"),
    )
    evidence: Dict[str, Any] = {}
    for current, legacy in pairs:
        present = {}
        if current in item:
            present[current] = deepcopy(item.get(current))
        if legacy in item:
            present[legacy] = deepcopy(item.get(legacy))
        if present:
            evidence["{}|{}".format(current, legacy)] = present
    return evidence


def _legacy_snapshot(repository: Any, state: Mapping[str, Any]) -> Dict[str, Any]:
    items = list(state.get("assessments", []) or [])
    catalogue = []
    statuses = []
    course_relationships = []
    assessment_topics = []
    topic_order = []
    raw_identities = []
    deferred_course_credits = []
    field_alias_evidence = []

    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            # The legacy loader keeps malformed list entries.  Preserve them in
            # raw evidence while making the semantic projection explicit.
            catalogue.append({"position": position, "invalid_record": deepcopy(item)})
            continue
        assessment_id = _raw_text(item.get("id"))
        course_id = _raw_text(item.get("course_id"))
        status = _raw_text(item.get("status"))
        catalogue.append(
            {
                "id": assessment_id,
                "course_id": course_id,
                "type": _raw_text(item.get("type")),
                "title": _raw_text(item.get("title")),
                "status": status,
                "due_date": item.get("due_date"),
                "due_time": item.get("due_time"),
                "weightage_percent": _float_or_none(item.get("weightage_percent")),
                "total_marks": _float_or_none(item.get("total_marks")),
                "obtained_marks": _float_or_none(item.get("obtained_marks")),
                "description": _raw_text(item.get("description")),
            }
        )
        statuses.append((assessment_id, status))
        course_relationships.append((assessment_id, course_id))
        labels = item.get("topics", [])
        if not isinstance(labels, list):
            labels = []
        projected_labels = []
        for topic_position, label in enumerate(labels):
            raw_label = _raw_text(label)
            projected_labels.append(raw_label)
            assessment_topics.append(
                {
                    "assessment_id": assessment_id,
                    "course_id": course_id,
                    "position": topic_position,
                    "raw_label": raw_label,
                }
            )
        topic_order.append((assessment_id, tuple(projected_labels)))
        raw_identities.append(
            {
                "position": position,
                "raw_id": _raw_text(item.get("id")),
                "raw_course_id": _raw_text(item.get("course_id")),
                "raw_type": _raw_text(item.get("type")),
                "raw_assessment_type": _raw_text(item.get("assessment_type")),
                "raw_status": _raw_text(item.get("status")),
            }
        )
        if item.get("course_credits") not in (None, ""):
            deferred_course_credits.append((assessment_id, deepcopy(item.get("course_credits"))))
        field_alias_evidence.append((assessment_id, _field_alias_evidence(item)))

    raw, source_hash, raw_error = _read_raw_source(repository)
    source_version: Any = state.get("version", 2)
    raw_records: Tuple[Any, ...] = tuple(deepcopy(items))
    if isinstance(raw, dict):
        source_version = raw.get("version", source_version)
        raw_items = raw.get("assessments", [])
        if isinstance(raw_items, list):
            raw_records = tuple(deepcopy(raw_items[-200:]))

    return {
        "state_version": state.get("version", 2),
        "source_version": source_version,
        "source_hash": source_hash,
        "assessment_catalogue": tuple(catalogue),
        "assessment_order": tuple(
            item.get("id", "") for item in catalogue if "id" in item
        ),
        "assessment_statuses": tuple(statuses),
        "course_relationships": tuple(course_relationships),
        "assessment_topics": tuple(assessment_topics),
        "assessment_topic_order": tuple(topic_order),
        "raw_records": raw_records,
        "raw_identities": tuple(raw_identities),
        "field_alias_evidence": tuple(field_alias_evidence),
        "deferred_course_credits": tuple(deferred_course_credits),
        "raw_evidence_error": raw_error,
    }


def _sqlite_field_alias_evidence(snapshot: Mapping[str, Any]) -> Tuple[Any, ...]:
    result = []
    for item in snapshot.get("raw_records", ()):
        if not isinstance(item, Mapping):
            continue
        result.append((_raw_text(item.get("id")), _field_alias_evidence(item)))
    return tuple(result)


def _diagnostic(
    domain: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    key: str = "",
    message: Optional[str] = None,
) -> AssessmentParityDiagnostic:
    equal = legacy_value == sqlite_value
    return AssessmentParityDiagnostic(
        domain=domain,
        status="matched" if equal else "mismatch",
        key=key,
        severity="info" if equal else "error",
        legacy_value=deepcopy(legacy_value),
        sqlite_value=deepcopy(sqlite_value),
        message=message
        or (
            "Legacy and SQLite semantic values match."
            if equal
            else "Legacy and SQLite semantic values differ; the mismatch was not normalized away."
        ),
    )


def compare_assessment_parity(
    legacy_repository: Any,
    legacy_state: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_state",
) -> AssessmentParityReport:
    legacy = _legacy_snapshot(legacy_repository, legacy_state)
    diagnostics: List[AssessmentParityDiagnostic] = []

    pairs = (
        ("assessment_catalogue", legacy["assessment_catalogue"], tuple(sqlite_snapshot.get("assessment_catalogue", ()))),
        ("assessment_statuses", legacy["assessment_statuses"], tuple(sqlite_snapshot.get("assessment_statuses", ()))),
        ("assessment_course_relationships", legacy["course_relationships"], tuple(sqlite_snapshot.get("course_relationships", ()))),
        ("assessment_ordering", legacy["assessment_order"], tuple(sqlite_snapshot.get("assessment_order", ()))),
        ("assessment_topics", legacy["assessment_topics"], tuple(sqlite_snapshot.get("assessment_topics", ()))),
        ("assessment_topic_ordering", legacy["assessment_topic_order"], tuple(sqlite_snapshot.get("assessment_topic_order", ()))),
        ("raw_identities_and_statuses", legacy["raw_identities"], tuple(sqlite_snapshot.get("raw_identities", ()))),
        ("raw_assessment_records", legacy["raw_records"], tuple(sqlite_snapshot.get("raw_records", ()))),
        ("assessment_field_alias_evidence", legacy["field_alias_evidence"], _sqlite_field_alias_evidence(sqlite_snapshot)),
        ("source_version", legacy["source_version"], sqlite_snapshot.get("source_version")),
        ("source_hash", legacy["source_hash"], sqlite_snapshot.get("source_hash")),
    )
    for domain, left, right in pairs:
        message = None
        if domain in {"assessment_ordering", "assessment_topic_ordering"} and left != right:
            message = "Ordering differs and was compared directly rather than sorted away."
        if domain.startswith("raw_") and left != right:
            message = "Exact raw legacy evidence differs; whitespace, aliases, and status spellings were not canonicalized away."
        diagnostics.append(_diagnostic(domain, left, right, message=message))

    if legacy.get("raw_evidence_error"):
        diagnostics.append(
            AssessmentParityDiagnostic(
                domain="raw_legacy_evidence",
                status="error",
                key="",
                severity="error",
                legacy_value=legacy["raw_evidence_error"],
                sqlite_value=None,
                message="Raw legacy assessment evidence could not be inspected.",
            )
        )

    anomalies = tuple(sqlite_snapshot.get("anomalies", ()))
    diagnostics.append(
        AssessmentParityDiagnostic(
            domain="sqlite_structure",
            status="matched" if not anomalies else "mismatch",
            key="",
            severity="info" if not anomalies else "error",
            legacy_value=(),
            sqlite_value=anomalies,
            message=(
                "SQLite assessment/course/topic relationships are structurally consistent."
                if not anomalies
                else "SQLite assessment structural anomalies were detected explicitly."
            ),
        )
    )

    legacy_credits = legacy["deferred_course_credits"]
    sqlite_credits = tuple(sqlite_snapshot.get("deferred_course_credits", ()))
    if legacy_credits or sqlite_credits:
        diagnostics.append(
            AssessmentParityDiagnostic(
                domain="assessment_course_credits",
                status="deferred" if legacy_credits == sqlite_credits else "mismatch",
                key="",
                severity="info" if legacy_credits == sqlite_credits else "error",
                legacy_value=deepcopy(legacy_credits),
                sqlite_value=deepcopy(sqlite_credits),
                message=(
                    "Assessment-level course_credits are preserved only as raw ledger evidence; Phase 3 intentionally deferred credit authority."
                    if legacy_credits == sqlite_credits
                    else "Deferred course-credit raw evidence differs between legacy JSON and the SQLite migration ledger."
                ),
            )
        )

    resolutions = tuple(sqlite_snapshot.get("resolved_topic_relationships", ()))
    if resolutions:
        diagnostics.append(
            AssessmentParityDiagnostic(
                domain="resolved_assessment_topic_identities",
                status="deferred",
                key="",
                severity="info",
                legacy_value="legacy assessments store raw topic labels only",
                sqlite_value=deepcopy(resolutions),
                message="Resolved SQLite topic identities have no equivalent legacy field; structural validity is checked but semantic authority remains deferred.",
            )
        )
    else:
        diagnostics.append(
            AssessmentParityDiagnostic(
                domain="resolved_assessment_topic_identities",
                status="matched",
                key="",
                severity="info",
                legacy_value=(),
                sqlite_value=(),
                message="Assessment topics remain unresolved raw labels, matching the Phase 3 import policy.",
            )
        )

    diagnostics.append(
        AssessmentParityDiagnostic(
            domain="assessment_alias_tables",
            status="matched",
            key="",
            severity="info",
            legacy_value=False,
            sqlite_value=bool(sqlite_snapshot.get("aliases_supported", False)),
            message="The Phase 3 schema has no assessment alias table; legacy field-alias provenance is compared through exact raw evidence instead.",
        )
    )

    return AssessmentParityReport(operation=operation, diagnostics=tuple(diagnostics))


class DualReadAssessmentRepository:
    """Return legacy results while independently observing SQLite parity."""

    def __init__(
        self,
        legacy_repository: Any,
        sqlite_repository: SQLiteAssessmentRepository,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ):
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._diagnostic_sink = diagnostic_sink
        self._reports: List[AssessmentParityReport] = []

    @property
    def last_report(self) -> Optional[AssessmentParityReport]:
        return self._reports[-1] if self._reports else None

    @property
    def reports(self) -> Tuple[AssessmentParityReport, ...]:
        return tuple(self._reports)

    def _record(self, report: AssessmentParityReport) -> None:
        self._reports.append(report)
        if self._diagnostic_sink is not None:
            try:
                self._diagnostic_sink(report)
            except Exception:
                # Reporting is observational and can never break legacy authority.
                pass

    def _record_sqlite_error(self, operation: str, error: Exception) -> None:
        self._record(
            AssessmentParityReport(
                operation=operation,
                diagnostics=(
                    AssessmentParityDiagnostic(
                        domain="sqlite_read",
                        status="error",
                        key="",
                        severity="error",
                        legacy_value="authoritative result returned",
                        sqlite_value=type(error).__name__,
                        message="SQLite shadow read failed: {}".format(error),
                    ),
                ),
            )
        )

    def load_state(self):
        legacy_state = self.legacy_repository.load_state()
        try:
            sqlite_snapshot = self.sqlite_repository.parity_snapshot()
            self._record(
                compare_assessment_parity(
                    self.legacy_repository,
                    legacy_state,
                    sqlite_snapshot,
                    operation="load_state",
                )
            )
        except Exception as error:
            self._record_sqlite_error("load_state", error)
        return deepcopy(legacy_state)

    def save_state(self, state):
        # Phase 4.2 never dual-writes.  Existing JSON authority remains intact.
        return self.legacy_repository.save_state(state)


def build_assessment_repository(
    config: Union[AssessmentBackendConfig, str] = AssessmentBackendConfig(),
    *,
    legacy_repository: Optional[Any] = None,
    legacy_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteAssessmentRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    selected = (
        config
        if isinstance(config, AssessmentBackendConfig)
        else AssessmentBackendConfig(config)
    )
    legacy = legacy_repository or LegacyJsonAssessmentRepository(path=legacy_path)
    if selected.mode == "legacy":
        return legacy

    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteAssessmentRepository(sqlite_connection)
    return DualReadAssessmentRepository(
        legacy, shadow, diagnostic_sink=diagnostic_sink
    )


create_assessment_repository = build_assessment_repository


__all__ = (
    "AssessmentBackendConfig",
    "AssessmentParityDiagnostic",
    "AssessmentParityReport",
    "DualReadAssessmentRepository",
    "build_assessment_repository",
    "compare_assessment_parity",
    "create_assessment_repository",
)
