"""Phase 4.4 legacy-authoritative question-topic mapping dual-read backend."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from personal_learning_assistant.repositories.json.question_repository import LegacyJsonQuestionRepository
from personal_learning_assistant.repositories.sqlite.question_topic_mapping_repository import SQLiteQuestionTopicMappingRepository


@dataclass(frozen=True)
class QuestionTopicMappingBackendConfig:
    mode: str = "legacy"
    def __post_init__(self):
        mode = str(self.mode or "").strip().lower().replace("-", "_")
        if mode not in {"legacy", "dual_read"}:
            raise ValueError("Phase 4.4 mapping backend must be 'legacy' or 'dual_read'.")
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True)
class QuestionTopicMappingParityDiagnostic:
    domain: str
    status: str
    legacy_value: Any
    sqlite_value: Any
    message: str


@dataclass(frozen=True)
class QuestionTopicMappingParityReport:
    operation: str
    diagnostics: Tuple[QuestionTopicMappingParityDiagnostic, ...]
    @property
    def mismatch_count(self):
        return sum(d.status in {"mismatch", "error"} for d in self.diagnostics)
    @property
    def review_count(self):
        return sum(d.status == "review_required" for d in self.diagnostics)
    @property
    def status(self):
        if self.mismatch_count:
            return "mismatch"
        if self.review_count:
            return "pass_with_review"
        return "pass"


def _source_hash(repository: Any):
    path = Path(getattr(repository, "path", ""))
    if not path.exists():
        return hashlib.sha256(b"").hexdigest(), None
    try:
        payload = path.read_bytes()
        raw = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        return None, str(exc)
    return hashlib.sha256(payload).hexdigest(), raw if isinstance(raw, dict) else None


def _legacy_snapshot(repository: Any, state: Mapping[str, Any]) -> Dict[str, Any]:
    workspaces = state.get("workspaces", {}) if isinstance(state, Mapping) else {}
    if not isinstance(workspaces, Mapping):
        workspaces = {}
    raw_evidence = []
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
            qid = str(question.get("id", ""))
            if question.get("topic") not in (None, "") or question.get("topic_mapping") not in (None, "", {}):
                raw_evidence.append({
                    "question_legacy_key": "assessment:id:{}/question:id:{}".format(assessment_id, qid),
                    "raw_topic": deepcopy(question.get("topic")),
                    "raw_topic_mapping": deepcopy(question.get("topic_mapping")),
                })
    digest, raw = _source_hash(repository)
    version = state.get("version", 1) if isinstance(state, Mapping) else 1
    if isinstance(raw, dict):
        version = raw.get("version", version)
    return {"source_hash": digest, "source_version": version, "raw_topic_evidence": tuple(raw_evidence)}


def compare_question_topic_mapping_parity(legacy_repository: Any, legacy_state: Mapping[str, Any], sqlite_snapshot: Mapping[str, Any], *, operation="load_state"):
    legacy = _legacy_snapshot(legacy_repository, legacy_state)
    diagnostics: List[QuestionTopicMappingParityDiagnostic] = []
    for domain, left, right in (
        ("raw_question_topic_evidence", legacy["raw_topic_evidence"], tuple(sqlite_snapshot.get("raw_topic_evidence", ()))),
        ("source_hash", legacy["source_hash"], sqlite_snapshot.get("source_hash")),
    ):
        diagnostics.append(QuestionTopicMappingParityDiagnostic(
            domain, "matched" if left == right else "mismatch", deepcopy(left), deepcopy(right),
            "Legacy and SQLite mapping evidence match." if left == right else "Legacy and SQLite mapping evidence differ; raw evidence was not normalized away."
        ))
    sqlite_version = sqlite_snapshot.get("source_version")
    if sqlite_version is not None and str(legacy["source_version"]) != str(sqlite_version):
        diagnostics.append(QuestionTopicMappingParityDiagnostic("source_version", "mismatch", legacy["source_version"], sqlite_version, "Source versions differ."))
    else:
        diagnostics.append(QuestionTopicMappingParityDiagnostic("source_version", "matched", legacy["source_version"], sqlite_version, "Source versions match."))

    anomalies = tuple(sqlite_snapshot.get("anomalies", ()))
    diagnostics.append(QuestionTopicMappingParityDiagnostic(
        "sqlite_mapping_structure", "matched" if not anomalies else "mismatch", (), anomalies,
        "SQLite mapping relationships are structurally consistent." if not anomalies else "SQLite mapping structural anomalies were detected."
    ))
    review = tuple(sqlite_snapshot.get("review_required", ()))
    diagnostics.append(QuestionTopicMappingParityDiagnostic(
        "unresolved_or_ambiguous_topic_candidates", "review_required" if review else "matched", (), review,
        "Unresolved/ambiguous candidates remain review items; no foreign key is guessed." if review else "All observed mapping candidates are either resolved or absent."
    ))
    rows = tuple(sqlite_snapshot.get("mapping_rows", ()))
    diagnostics.append(QuestionTopicMappingParityDiagnostic(
        "resolved_question_topic_mappings", "matched", "legacy nested mapping evidence", rows,
        "Relational rows are observation-only in Phase 4.4; legacy JSON remains authoritative."
    ))
    return QuestionTopicMappingParityReport(operation, tuple(diagnostics))


class DualReadQuestionTopicMappingRepository:
    def __init__(self, legacy_repository: Any, sqlite_repository: SQLiteQuestionTopicMappingRepository, diagnostic_sink: Optional[Callable[[QuestionTopicMappingParityReport], None]] = None):
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._sink = diagnostic_sink
        self._reports: List[QuestionTopicMappingParityReport] = []
    @property
    def last_report(self):
        return self._reports[-1] if self._reports else None
    @property
    def reports(self):
        return tuple(self._reports)
    def load_state(self):
        legacy_state = self.legacy_repository.load_state()
        try:
            report = compare_question_topic_mapping_parity(self.legacy_repository, legacy_state, self.sqlite_repository.parity_snapshot())
        except Exception as exc:
            report = QuestionTopicMappingParityReport("load_state", (QuestionTopicMappingParityDiagnostic("sqlite_read", "error", "authoritative legacy result returned", type(exc).__name__, "SQLite shadow read failed: {}".format(exc)),))
        self._reports.append(report)
        if self._sink is not None:
            try:
                self._sink(report)
            except Exception:
                pass
        return deepcopy(legacy_state)
    def save_state(self, state):
        return self.legacy_repository.save_state(state)


def build_question_topic_mapping_repository(config: Union[QuestionTopicMappingBackendConfig, str] = QuestionTopicMappingBackendConfig(), *, legacy_repository=None, legacy_path=None, sqlite_repository=None, sqlite_connection=None, diagnostic_sink=None):
    selected = config if isinstance(config, QuestionTopicMappingBackendConfig) else QuestionTopicMappingBackendConfig(config)
    legacy = legacy_repository or LegacyJsonQuestionRepository(path=legacy_path)
    if selected.mode == "legacy":
        return legacy
    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError("dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly.")
        shadow = SQLiteQuestionTopicMappingRepository(sqlite_connection)
    return DualReadQuestionTopicMappingRepository(legacy, shadow, diagnostic_sink)

create_question_topic_mapping_repository = build_question_topic_mapping_repository
