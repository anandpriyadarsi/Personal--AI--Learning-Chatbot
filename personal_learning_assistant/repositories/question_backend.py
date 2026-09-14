"""Phase 4.3 legacy-authoritative Question + Source dual-read backend.

The existing ``assessment_question_workspace.py`` public API is intentionally
left untouched.  ``legacy`` and ``dual_read`` are the only supported modes;
SQLite is observation-only in Phase 4.3.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.json.question_repository import (
    LegacyJsonQuestionRepository,
)
from personal_learning_assistant.repositories.sqlite.question_repository import (
    SQLiteQuestionRepository,
)


@dataclass(frozen=True)
class QuestionBackendConfig:
    mode: str = "legacy"

    def __post_init__(self):
        normalized = str(self.mode or "").strip().lower().replace("-", "_")
        if normalized not in {"legacy", "dual_read"}:
            raise ValueError(
                "Phase 4.3 question backend must be 'legacy' or 'dual_read'."
            )
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class QuestionParityDiagnostic:
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
class QuestionParityReport:
    operation: str
    diagnostics: Tuple[QuestionParityDiagnostic, ...]

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


DiagnosticSink = Callable[[QuestionParityReport], None]


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _read_raw_source(repository: Any):
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
        return None, None, "unable to read raw legacy question evidence: {}".format(error)
    if not isinstance(raw, dict):
        return None, hashlib.sha256(payload).hexdigest(), "raw legacy workspace source is not a JSON object"
    return raw, hashlib.sha256(payload).hexdigest(), None


def _canonical_page(value: Any):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    try:
        if float(str(value).strip()) != float(number):
            return None
    except ValueError:
        return None
    return number if number >= 1 else None


def _canonical_locator(value: Any) -> str:
    if value is None or value == "" or isinstance(value, (dict, list, bool)):
        return ""
    text = str(value).strip()
    return "question:{}".format(text) if text else ""


def _has_deferred(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _legacy_snapshot(repository: Any, state: Mapping[str, Any]) -> Dict[str, Any]:
    workspaces = state.get("workspaces", {})
    if not isinstance(workspaces, Mapping):
        workspaces = {}

    catalogue: List[Dict[str, Any]] = []
    statuses: List[Tuple[str, str, str]] = []
    assessment_relationships: List[Tuple[str, str, str]] = []
    question_order: List[Tuple[str, Tuple[str, ...]]] = []
    sources: List[Dict[str, Any]] = []
    source_order: List[Tuple[str, str]] = []
    raw_records: List[Dict[str, Any]] = []
    raw_identities: List[Dict[str, Any]] = []
    raw_source_evidence: List[Dict[str, Any]] = []
    source_identities: List[Dict[str, Any]] = []
    deferred_topics: List[Dict[str, Any]] = []
    deferred_performance: List[Dict[str, Any]] = []
    workspace_metadata: List[Dict[str, Any]] = []

    for workspace_position, (workspace_key, workspace) in enumerate(workspaces.items()):
        if not isinstance(workspace, Mapping):
            raw_records.append(
                {
                    "assessment_id": _raw_text(workspace_key),
                    "position": workspace_position,
                    "raw_workspace": deepcopy(workspace),
                }
            )
            continue
        assessment_id = _raw_text(workspace.get("assessment_id")) or _raw_text(workspace_key)
        metadata = {
            str(key): deepcopy(value)
            for key, value in workspace.items()
            if key not in {"assessment_id", "questions"}
        }
        if metadata:
            workspace_metadata.append(
                {"assessment_id": assessment_id, "metadata": metadata}
            )
        questions = workspace.get("questions", [])
        if not isinstance(questions, list):
            questions = []
        ids: List[str] = []
        for question_position, item in enumerate(questions):
            if not isinstance(item, Mapping):
                raw_records.append(
                    {
                        "assessment_id": assessment_id,
                        "position": question_position,
                        "raw": deepcopy(item),
                    }
                )
                continue
            question_id = _raw_text(item.get("id"))
            ids.append(question_id)
            status = _raw_text(item.get("status"))
            catalogue.append(
                {
                    "assessment_id": assessment_id,
                    "id": question_id,
                    "ordinal": question_position + 1,
                    "text": _raw_text(item.get("text")),
                    "marks": deepcopy(item.get("marks")),
                    "status": status,
                    "notes": _raw_text(item.get("notes")),
                }
            )
            statuses.append((assessment_id, question_id, status))
            assessment_relationships.append((assessment_id, question_id, assessment_id))
            raw_records.append(
                {
                    "assessment_id": assessment_id,
                    "position": question_position,
                    "raw": deepcopy(dict(item)),
                }
            )
            raw_identities.append(
                {
                    "assessment_id": assessment_id,
                    "expected_assessment_id": assessment_id,
                    "position": question_position,
                    "raw_id": _raw_text(item.get("id")),
                    "raw_status": _raw_text(item.get("status")),
                }
            )

            raw_label = item.get("source_file")
            valid_label = isinstance(raw_label, str) and bool(raw_label.strip())
            if valid_label:
                sources.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "raw_source_label": raw_label,
                        "page_number": _canonical_page(item.get("source_page")),
                        "locator": _canonical_locator(item.get("source_question_number")),
                    }
                )
                source_order.append((assessment_id, question_id))
                source_identities.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "legacy_key": "assessment:id:{}/question:id:{}/source:legacy".format(
                            assessment_id, question_id
                        ),
                    }
                )
                raw_source_evidence.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "raw_source_label": raw_label,
                        "raw_page_number": deepcopy(item.get("source_page")),
                        "raw_question_number": deepcopy(item.get("source_question_number")),
                    }
                )
            elif any(
                key in item
                for key in ("source_file", "source_page", "source_question_number")
            ):
                # Invalid/orphan source metadata stays visible through exact raw
                # question evidence.  No semantic source row is invented.
                raw_source_evidence.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "raw_source_label": deepcopy(item.get("source_file")),
                        "raw_page_number": deepcopy(item.get("source_page")),
                        "raw_question_number": deepcopy(item.get("source_question_number")),
                    }
                )

            if _has_deferred(item.get("topic")) or _has_deferred(item.get("topic_mapping")):
                deferred_topics.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "topic": deepcopy(item.get("topic")),
                        "topic_mapping": deepcopy(item.get("topic_mapping")),
                    }
                )
            if any(
                _has_deferred(item.get(key))
                for key in ("attempts", "performance", "mistakes")
            ):
                deferred_performance.append(
                    {
                        "assessment_id": assessment_id,
                        "question_id": question_id,
                        "attempts": deepcopy(item.get("attempts")),
                        "performance": deepcopy(item.get("performance")),
                        "mistakes": deepcopy(item.get("mistakes")),
                    }
                )
        question_order.append((assessment_id, tuple(ids)))

    raw, source_hash, raw_error = _read_raw_source(repository)
    source_version: Any = state.get("version", 1)
    if isinstance(raw, dict):
        source_version = raw.get("version", source_version)

    return {
        "source_version": source_version,
        "source_hash": source_hash,
        "question_catalogue": tuple(catalogue),
        "question_statuses": tuple(statuses),
        "assessment_relationships": tuple(assessment_relationships),
        "question_order": tuple(question_order),
        "question_sources": tuple(sources),
        "question_source_order": tuple(source_order),
        "question_source_identities": tuple(source_identities),
        "raw_records": tuple(raw_records),
        "raw_identities": tuple(raw_identities),
        "raw_source_evidence": tuple(raw_source_evidence),
        "deferred_topic_evidence": tuple(deferred_topics),
        "deferred_performance_evidence": tuple(deferred_performance),
        "workspace_metadata": tuple(workspace_metadata),
        "raw_evidence_error": raw_error,
    }


def _diagnostic(
    domain: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    key: str = "",
    message: Optional[str] = None,
) -> QuestionParityDiagnostic:
    equal = legacy_value == sqlite_value
    return QuestionParityDiagnostic(
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


def _deferred_evidence_diagnostic(
    domain: str,
    legacy_value: Sequence[Any],
    sqlite_value: Sequence[Any],
    *,
    message: str,
) -> QuestionParityDiagnostic:
    left = tuple(legacy_value)
    right = tuple(sqlite_value)
    if left != right:
        return QuestionParityDiagnostic(
            domain=domain,
            status="mismatch",
            key="",
            severity="error",
            legacy_value=deepcopy(left),
            sqlite_value=deepcopy(right),
            message="Deferred raw evidence differs between legacy JSON and SQLite ledger evidence.",
        )
    if left:
        return QuestionParityDiagnostic(
            domain=domain,
            status="deferred",
            key="",
            severity="info",
            legacy_value=deepcopy(left),
            sqlite_value=deepcopy(right),
            message=message,
        )
    return QuestionParityDiagnostic(
        domain=domain,
        status="matched",
        key="",
        severity="info",
        legacy_value=(),
        sqlite_value=(),
        message="No deferred evidence is present in this source snapshot.",
    )


def compare_question_parity(
    legacy_repository: Any,
    legacy_state: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_state",
) -> QuestionParityReport:
    legacy = _legacy_snapshot(legacy_repository, legacy_state)
    diagnostics: List[QuestionParityDiagnostic] = []

    pairs = (
        ("question_catalogue", legacy["question_catalogue"], tuple(sqlite_snapshot.get("question_catalogue", ()))),
        ("question_statuses", legacy["question_statuses"], tuple(sqlite_snapshot.get("question_statuses", ()))),
        ("question_assessment_relationships", legacy["assessment_relationships"], tuple(sqlite_snapshot.get("assessment_relationships", ()))),
        ("question_ordering", legacy["question_order"], tuple(sqlite_snapshot.get("question_order", ()))),
        ("question_sources", legacy["question_sources"], tuple(sqlite_snapshot.get("question_sources", ()))),
        ("question_source_ordering", legacy["question_source_order"], tuple(sqlite_snapshot.get("question_source_order", ()))),
        ("question_source_identities", legacy["question_source_identities"], tuple(sqlite_snapshot.get("question_source_identities", ()))),
        ("raw_identities_and_statuses", legacy["raw_identities"], tuple(sqlite_snapshot.get("raw_identities", ()))),
        ("raw_question_records", legacy["raw_records"], tuple(sqlite_snapshot.get("raw_records", ()))),
        ("raw_question_source_evidence", legacy["raw_source_evidence"], tuple(sqlite_snapshot.get("raw_source_evidence", ()))),
        ("source_version", legacy["source_version"], sqlite_snapshot.get("source_version")),
        ("source_hash", legacy["source_hash"], sqlite_snapshot.get("source_hash")),
    )
    for domain, left, right in pairs:
        message = None
        if domain in {"question_ordering", "question_source_ordering"} and left != right:
            message = "Ordering differs and was compared directly rather than sorted away."
        if domain.startswith("raw_") and left != right:
            message = "Exact raw identities/source/status evidence differs; whitespace and raw spellings were not canonicalized away."
        diagnostics.append(_diagnostic(domain, left, right, message=message))

    if legacy.get("raw_evidence_error"):
        diagnostics.append(
            QuestionParityDiagnostic(
                domain="raw_legacy_evidence",
                status="error",
                key="",
                severity="error",
                legacy_value=legacy["raw_evidence_error"],
                sqlite_value=None,
                message="Raw legacy question evidence could not be inspected.",
            )
        )

    anomalies = tuple(sqlite_snapshot.get("anomalies", ()))
    diagnostics.append(
        QuestionParityDiagnostic(
            domain="sqlite_structure",
            status="matched" if not anomalies else "mismatch",
            key="",
            severity="info" if not anomalies else "error",
            legacy_value=(),
            sqlite_value=anomalies,
            message=(
                "SQLite question/assessment/source relationships are structurally consistent."
                if not anomalies
                else "SQLite question/source structural anomalies were detected explicitly."
            ),
        )
    )

    diagnostics.append(
        _deferred_evidence_diagnostic(
            "question_topic_mappings",
            legacy["deferred_topic_evidence"],
            sqlite_snapshot.get("deferred_topic_evidence", ()),
            message="Question topic/topic_mapping evidence is preserved but relational mapping cutover is deferred to Phase 4.4.",
        )
    )
    diagnostics.append(
        _deferred_evidence_diagnostic(
            "question_performance_records",
            legacy["deferred_performance_evidence"],
            sqlite_snapshot.get("deferred_performance_evidence", ()),
            message="Question attempts/performance/mistakes remain outside Phase 4.3 authority.",
        )
    )

    resolved_mappings = tuple(sqlite_snapshot.get("resolved_topic_mappings", ()))
    if resolved_mappings:
        diagnostics.append(
            QuestionParityDiagnostic(
                domain="resolved_question_topic_mappings",
                status="deferred",
                key="",
                severity="info",
                legacy_value="legacy nested topic fields are not relational authority",
                sqlite_value=deepcopy(resolved_mappings),
                message="Relational question-topic mappings are structurally visible but their parity/cutover is deferred to Phase 4.4.",
            )
        )
    else:
        diagnostics.append(
            QuestionParityDiagnostic(
                domain="resolved_question_topic_mappings",
                status="matched",
                key="",
                severity="info",
                legacy_value=(),
                sqlite_value=(),
                message="No relational question-topic mappings are present in the Phase 4.3 fixture/state.",
            )
        )

    resolved_sources = tuple(sqlite_snapshot.get("resolved_source_relationships", ()))
    if resolved_sources:
        diagnostics.append(
            QuestionParityDiagnostic(
                domain="resolved_question_source_relationships",
                status="deferred",
                key="",
                severity="info",
                legacy_value="legacy stores raw source annotations only",
                sqlite_value=deepcopy(resolved_sources),
                message="Reviewed document/resource/note IDs have no legacy field; their targets are structurally validated but legacy remains authoritative for application-visible source annotations.",
            )
        )
    else:
        diagnostics.append(
            QuestionParityDiagnostic(
                domain="resolved_question_source_relationships",
                status="matched",
                key="",
                severity="info",
                legacy_value=(),
                sqlite_value=(),
                message="Question sources remain unresolved raw annotations, matching the Phase 3 import policy.",
            )
        )

    metadata = legacy["workspace_metadata"]
    diagnostics.append(
        QuestionParityDiagnostic(
            domain="workspace_metadata",
            status="deferred" if metadata else "matched",
            key="",
            severity="info",
            legacy_value=deepcopy(metadata),
            sqlite_value={
                "supported": bool(sqlite_snapshot.get("workspace_metadata_supported", False)),
                "value": (),
            },
            message=(
                "Workspace-level created_at/updated_at/extra metadata was not migrated by Phase 3 Fix 6 and remains explicitly deferred."
                if metadata
                else "No workspace-level metadata requires parity in this source snapshot."
            ),
        )
    )

    return QuestionParityReport(operation=operation, diagnostics=tuple(diagnostics))


class DualReadQuestionRepository:
    """Return legacy results while independently observing SQLite parity."""

    def __init__(
        self,
        legacy_repository: Any,
        sqlite_repository: SQLiteQuestionRepository,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ):
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._diagnostic_sink = diagnostic_sink
        self._reports: List[QuestionParityReport] = []

    @property
    def last_report(self) -> Optional[QuestionParityReport]:
        return self._reports[-1] if self._reports else None

    @property
    def reports(self) -> Tuple[QuestionParityReport, ...]:
        return tuple(self._reports)

    def _record(self, report: QuestionParityReport) -> None:
        self._reports.append(report)
        if self._diagnostic_sink is not None:
            try:
                self._diagnostic_sink(report)
            except Exception:
                # Diagnostics are observational only and cannot break authority.
                pass

    def _record_sqlite_error(self, operation: str, error: Exception) -> None:
        self._record(
            QuestionParityReport(
                operation=operation,
                diagnostics=(
                    QuestionParityDiagnostic(
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
                compare_question_parity(
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
        # Phase 4.3 never dual-writes. Existing JSON authority remains intact.
        return self.legacy_repository.save_state(state)


def build_question_repository(
    config: Union[QuestionBackendConfig, str] = QuestionBackendConfig(),
    *,
    legacy_repository: Optional[Any] = None,
    legacy_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteQuestionRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    selected = (
        config if isinstance(config, QuestionBackendConfig) else QuestionBackendConfig(config)
    )
    legacy = legacy_repository or LegacyJsonQuestionRepository(path=legacy_path)
    if selected.mode == "legacy":
        return legacy

    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteQuestionRepository(sqlite_connection)
    return DualReadQuestionRepository(
        legacy, shadow, diagnostic_sink=diagnostic_sink
    )


create_question_repository = build_question_repository


__all__ = (
    "QuestionBackendConfig",
    "QuestionParityDiagnostic",
    "QuestionParityReport",
    "DualReadQuestionRepository",
    "build_question_repository",
    "compare_question_parity",
    "create_question_repository",
)
