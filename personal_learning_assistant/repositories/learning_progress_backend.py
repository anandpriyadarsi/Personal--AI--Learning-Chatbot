"""Legacy-authoritative Phase 4.6 Learning Memory + Academic Progress dual read.

The current ``learning_memory.py`` and ``academic_progress.py`` APIs remain
unchanged.  This module provides an observational repository seam: legacy JSON
is authoritative, SQLite is read-only shadow state, and every successful
application-visible read returns the legacy value even when parity fails.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.json.learning_progress_repository import (
    LegacyJsonLearningProgressRepository,
)
from personal_learning_assistant.repositories.sqlite.learning_progress_repository import (
    SQLiteLearningProgressRepository,
)


@dataclass(frozen=True)
class LearningProgressBackendConfig:
    mode: str = "legacy"

    def __post_init__(self):
        normalized = str(self.mode or "").strip().lower().replace("-", "_")
        if normalized not in {"legacy", "dual_read"}:
            raise ValueError(
                "Phase 4.6 backend must be 'legacy' or 'dual_read'."
            )
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class LearningProgressParityDiagnostic:
    domain: str
    status: str
    key: str
    severity: str
    legacy_value: Any
    sqlite_value: Any
    message: str
    entity_type: str = ""
    course_id: str = ""
    topic_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "status": self.status,
            "key": self.key,
            "severity": self.severity,
            "legacy_value": deepcopy(self.legacy_value),
            "sqlite_value": deepcopy(self.sqlite_value),
            "message": self.message,
            "entity_type": self.entity_type,
            "course_id": self.course_id,
            "topic_id": self.topic_id,
        }


@dataclass(frozen=True)
class LearningProgressParityReport:
    operation: str
    diagnostics: Tuple[LearningProgressParityDiagnostic, ...]

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


DiagnosticSink = Callable[[LearningProgressParityReport], None]


def _diagnostic(
    domain: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    key: str = "",
    message: Optional[str] = None,
    entity_type: str = "",
    course_id: str = "",
    topic_id: str = "",
) -> LearningProgressParityDiagnostic:
    equal = legacy_value == sqlite_value
    return LearningProgressParityDiagnostic(
        domain=domain,
        status="matched" if equal else "mismatch",
        key=key,
        severity="info" if equal else "error",
        legacy_value=deepcopy(legacy_value),
        sqlite_value=deepcopy(sqlite_value),
        message=message
        or (
            "Legacy and SQLite semantics match."
            if equal
            else "Legacy and SQLite semantics differ; the mismatch was not normalized away."
        ),
        entity_type=entity_type,
        course_id=course_id,
        topic_id=topic_id,
    )


def _hash_path(path_value: Any) -> Optional[str]:
    if path_value is None:
        return None
    path = Path(path_value)
    if not path.exists():
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _position(entry: Mapping[str, Any]) -> int:
    raw = entry.get("raw")
    if isinstance(raw, Mapping):
        value = raw.get("position")
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    return 0


def _reconstruct_memory_state(sqlite_memory: Mapping[str, Any]) -> Dict[str, Any]:
    scopes: Dict[str, Dict[str, Any]] = {
        "": {
            "weak_topics": [],
            "mastered_topics": [],
            "recent_activity": [],
            "notes": [],
        }
    }
    entries = list(sqlite_memory.get("entries", ()))
    entries.sort(
        key=lambda item: (
            str(item.get("raw_course_id", "")).casefold(),
            str(item.get("kind", "")),
            _position(item),
            str(item.get("legacy_key", "")),
        )
    )
    for item in entries:
        raw_course_id = str(item.get("raw_course_id", ""))
        scope = scopes.setdefault(
            raw_course_id,
            {
                "weak_topics": [],
                "mastered_topics": [],
                "recent_activity": [],
                "notes": [],
            },
        )
        kind = str(item.get("kind", ""))
        raw = item.get("raw") if isinstance(item.get("raw"), Mapping) else {}
        if kind == "weak_topic":
            scope["weak_topics"].append(str(item.get("raw_topic", "")))
        elif kind == "mastered_topic":
            scope["mastered_topics"].append(str(item.get("raw_topic", "")))
        elif kind == "note":
            raw_note = raw.get("note") if isinstance(raw, Mapping) else None
            created_at = None if isinstance(raw_note, str) else item.get("created_at")
            scope["notes"].append(
                {"text": str(item.get("memory_text", "")), "created_at": created_at}
            )
        elif kind == "activity":
            raw_activity = raw.get("activity") if isinstance(raw, Mapping) else None
            mode = "Academic Study"
            if isinstance(raw_activity, Mapping):
                mode = str(raw_activity.get("mode", "Academic Study")).strip()
            scope["recent_activity"].append(
                {
                    "mode": mode,
                    "question": str(item.get("memory_text", "")),
                    "topic": str(item.get("raw_topic", "")),
                    "time": item.get("created_at"),
                }
            )

    global_scope = scopes.pop("")
    course_memory = {
        course_id: scope for course_id, scope in sorted(scopes.items(), key=lambda item: item[0].casefold())
    }
    return {
        "version": 2,
        "weak_topics": global_scope["weak_topics"],
        "mastered_topics": global_scope["mastered_topics"],
        "recent_activity": global_scope["recent_activity"],
        "notes": global_scope["notes"],
        "course_memory": course_memory,
    }


def _resolved_memory_event_projection(sqlite_memory: Mapping[str, Any]) -> Tuple[Tuple[Any, ...], ...]:
    entry_by_target = {
        str(item.get("target_id", "")): item
        for item in sqlite_memory.get("entries", ())
    }
    projected = []
    for event in sqlite_memory.get("events", ()):
        entry = entry_by_target.get(str(event.get("evidence_id", "")))
        if not entry:
            continue
        projected.append(
            (
                str(entry.get("raw_course_id", "")),
                str(entry.get("raw_topic", "")),
                str(event.get("event_type", "")),
                event.get("new_status"),
            )
        )
    return tuple(sorted(projected, key=lambda item: tuple(str(value).casefold() for value in item)))


def _expected_resolved_memory_events(sqlite_memory: Mapping[str, Any]) -> Tuple[Tuple[Any, ...], ...]:
    projected = []
    for entry in sqlite_memory.get("entries", ()):
        kind = str(entry.get("kind", ""))
        topic_id = entry.get("topic_id")
        if not topic_id or kind not in {"weak_topic", "mastered_topic"}:
            continue
        status = "weak" if kind == "weak_topic" else "mastered"
        event_type = "legacy_memory_{}_topic".format("weak" if kind == "weak_topic" else "mastered")
        projected.append(
            (
                str(entry.get("raw_course_id", "")),
                str(entry.get("raw_topic", "")),
                event_type,
                status,
            )
        )
    return tuple(sorted(projected, key=lambda item: tuple(str(value).casefold() for value in item)))


def _reconstruct_progress_history(sqlite_progress: Mapping[str, Any]) -> Dict[str, Any]:
    courses: Dict[str, List[Any]] = {}
    snapshots = list(sqlite_progress.get("snapshots", ()))
    # SQLite projection preserves ledger order inside each course by legacy key/date.
    snapshots.sort(
        key=lambda item: (
            str(item.get("legacy_course_id", "")).casefold(),
            int(item.get("ledger_rowid", 0)),
        )
    )
    for item in snapshots:
        course_id = str(item.get("legacy_course_id", ""))
        raw = item.get("raw")
        if isinstance(raw, Mapping):
            value = deepcopy(dict(raw))
        else:
            value = {
                "date": item.get("snapshot_date"),
                "course_id": course_id,
                "mastered_topics": item.get("counts", {}).get("mastered_topics"),
                "total_topics": item.get("counts", {}).get("total_topics"),
                "progress_percent": item.get("scores", {}).get("progress_percent"),
            }
        courses.setdefault(course_id, []).append(value)
    return {"version": 1, "courses": courses}


def _canonical_current_progress(state: Mapping[str, Any]) -> Dict[str, Any]:
    courses_map: Dict[str, Any] = {}
    for course in state.get("courses", ()):
        if not isinstance(course, Mapping):
            continue
        course_id = str(course.get("id", ""))
        courses_map[course_id] = {
            "code": course.get("code", ""),
            "name": course.get("name", ""),
            "topics": tuple(
                {
                    "name": topic.get("name", ""),
                    "status": topic.get("status", "not_started"),
                    "confidence": topic.get("confidence", 0),
                }
                for topic in course.get("topics", ())
                if isinstance(topic, Mapping)
            ),
        }
    summaries = {
        str(key): deepcopy(value)
        for key, value in dict(state.get("summaries", {})).items()
    }
    return {"courses": courses_map, "summaries": summaries}


def compare_learning_memory_parity(
    legacy_repository: LegacyJsonLearningProgressRepository,
    legacy_memory: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_memory",
) -> LearningProgressParityReport:
    shadow = sqlite_snapshot.get("memory", {})
    reconstructed = _reconstruct_memory_state(shadow)
    diagnostics: List[LearningProgressParityDiagnostic] = [
        _diagnostic(
            "learning_memory_semantics",
            legacy_memory,
            reconstructed,
            message="Weak/mastered topics, notes, activities, course scopes, text, ordering, and persisted timestamps are compared as legacy-visible memory semantics.",
            entity_type="learning_memory",
        ),
        _diagnostic(
            "learning_memory_source_hash",
            _hash_path(legacy_repository.memory_path),
            shadow.get("source_hash"),
            entity_type="source",
        ),
        _diagnostic(
            "learning_memory_source_version",
            legacy_memory.get("version", 2),
            shadow.get("source_version"),
            entity_type="source",
        ),
        _diagnostic(
            "resolved_memory_topic_events",
            _expected_resolved_memory_events(shadow),
            _resolved_memory_event_projection(shadow),
            message="Resolved weak/mastered memory evidence is compared with append-only topic_progress_events without treating those events as current topic status.",
            entity_type="topic_progress_event",
        ),
    ]

    anomalies = tuple(shadow.get("anomalies", ()))
    diagnostics.append(
        LearningProgressParityDiagnostic(
            domain="learning_memory_sqlite_structure",
            status="matched" if not anomalies else "mismatch",
            key="",
            severity="info" if not anomalies else "error",
            legacy_value=(),
            sqlite_value=anomalies,
            message=(
                "Memory scope/topic ownership, ledger targets, live rows, and evidence relationships are structurally valid."
                if not anomalies
                else "SQLite learning-memory structural anomalies were detected explicitly."
            ),
            entity_type="sqlite_structure",
        )
    )

    unresolved = tuple(
        {
            "legacy_key": item.get("legacy_key"),
            "raw_course_id": item.get("raw_course_id"),
            "raw_topic": item.get("raw_topic"),
        }
        for item in shadow.get("entries", ())
        if item.get("kind") in {"weak_topic", "mastered_topic"}
        and not item.get("topic_id")
    )
    if unresolved:
        diagnostics.append(
            LearningProgressParityDiagnostic(
                domain="unresolved_learning_memory_topics",
                status="deferred",
                key="",
                severity="info",
                legacy_value="raw memory topics remain authoritative",
                sqlite_value=unresolved,
                message="Unresolved/global legacy topic labels remain raw memory evidence and are not guessed onto topic foreign keys.",
                entity_type="learning_memory_entry",
            )
        )

    historical = {
        "entries": tuple(shadow.get("historical_entries", ())),
        "events": tuple(shadow.get("historical_events", ())),
    }
    if historical["entries"] or historical["events"]:
        diagnostics.append(
            LearningProgressParityDiagnostic(
                domain="historical_learning_memory_rows",
                status="deferred",
                key="",
                severity="info",
                legacy_value="current source snapshot",
                sqlite_value=historical,
                message="Older rows retained from prior source hashes remain historical evidence and are not promoted to current legacy authority.",
                entity_type="history",
            )
        )

    return LearningProgressParityReport(operation=operation, diagnostics=tuple(diagnostics))


def compare_academic_progress_parity(
    legacy_repository: LegacyJsonLearningProgressRepository,
    legacy_history: Mapping[str, Any],
    legacy_current: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_progress_history",
) -> LearningProgressParityReport:
    progress = sqlite_snapshot.get("progress_history", {})
    current = sqlite_snapshot.get("current_progress", {})
    diagnostics: List[LearningProgressParityDiagnostic] = [
        _diagnostic(
            "progress_history_semantics",
            legacy_history,
            _reconstruct_progress_history(progress),
            message="Persisted progress-history snapshots are compared from stored historical evidence; no snapshot is regenerated to force parity.",
            entity_type="progress_snapshot",
        ),
        _diagnostic(
            "progress_source_hash",
            _hash_path(legacy_repository.progress_path),
            progress.get("source_hash"),
            entity_type="source",
        ),
        _diagnostic(
            "progress_source_version",
            legacy_history.get("version", 1),
            progress.get("source_version"),
            entity_type="source",
        ),
    ]

    legacy_canonical = _canonical_current_progress(legacy_current)
    sqlite_canonical = _canonical_current_progress(current)
    diagnostics.extend(
        [
            _diagnostic(
                "current_topic_progress_semantics",
                legacy_canonical["courses"],
                sqlite_canonical["courses"],
                message="Current course/topic identity, ordering, status, and confidence are compared against live SQLite topic rows without writing history.",
                entity_type="topic",
            ),
            _diagnostic(
                "current_course_progress_summaries",
                legacy_canonical["summaries"],
                sqlite_canonical["summaries"],
                message="Course-level counts, mastered totals, progress percentage, weak topics, and missing topics mirror the existing pure course_manager progress calculation.",
                entity_type="course_progress",
            ),
        ]
    )

    anomalies = tuple(progress.get("anomalies", ())) + tuple(current.get("anomalies", ()))
    diagnostics.append(
        LearningProgressParityDiagnostic(
            domain="academic_progress_sqlite_structure",
            status="matched" if not anomalies else "mismatch",
            key="",
            severity="info" if not anomalies else "error",
            legacy_value=(),
            sqlite_value=anomalies,
            message=(
                "Progress snapshot ownership and current course/topic relationships are structurally valid."
                if not anomalies
                else "SQLite academic-progress structural anomalies were detected explicitly."
            ),
            entity_type="sqlite_structure",
        )
    )

    historical = tuple(progress.get("historical_snapshots", ()))
    if historical:
        diagnostics.append(
            LearningProgressParityDiagnostic(
                domain="historical_progress_rows",
                status="deferred",
                key="",
                severity="info",
                legacy_value="current source snapshot",
                sqlite_value=historical,
                message="Snapshots evidenced only by older source hashes remain historical evidence and are not deleted or treated as current authority.",
                entity_type="history",
            )
        )

    raw_progress = legacy_repository.load_raw_progress_source()
    if isinstance(raw_progress, Mapping) and "history" in raw_progress and "courses" not in raw_progress:
        diagnostics.append(
            LearningProgressParityDiagnostic(
                domain="legacy_progress_shape",
                status="deferred",
                key="",
                severity="info",
                legacy_value="history",
                sqlite_value="Phase 3 Fix 9 legacy importer shape",
                message="Current academic_progress.load_history reads the 'courses' shape, while older Phase 3 fixtures/import evidence may use 'history'; the difference is exposed rather than silently reconciled.",
                entity_type="source_shape",
            )
        )

    return LearningProgressParityReport(operation=operation, diagnostics=tuple(diagnostics))


class DualReadLearningProgressRepository:
    """Return authoritative legacy values while observing SQLite parity."""

    def __init__(
        self,
        legacy_repository: LegacyJsonLearningProgressRepository,
        sqlite_repository: SQLiteLearningProgressRepository,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ):
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._diagnostic_sink = diagnostic_sink
        self._reports: List[LearningProgressParityReport] = []

    @property
    def last_report(self) -> Optional[LearningProgressParityReport]:
        return self._reports[-1] if self._reports else None

    @property
    def reports(self) -> Tuple[LearningProgressParityReport, ...]:
        return tuple(self._reports)

    def _record(self, report: LearningProgressParityReport) -> None:
        self._reports.append(report)
        if self._diagnostic_sink is not None:
            try:
                self._diagnostic_sink(report)
            except Exception:
                # Diagnostics are observational and cannot break legacy reads.
                pass

    def _record_shadow_error(self, operation: str, error: Exception) -> None:
        self._record(
            LearningProgressParityReport(
                operation=operation,
                diagnostics=(
                    LearningProgressParityDiagnostic(
                        domain="sqlite_read",
                        status="error",
                        key="",
                        severity="error",
                        legacy_value="authoritative legacy result returned",
                        sqlite_value=type(error).__name__,
                        message="SQLite Phase 4.6 shadow read failed: {}".format(error),
                        entity_type="sqlite_shadow",
                    ),
                ),
            )
        )

    def load_memory(self):
        legacy = self.legacy_repository.load_memory()
        try:
            snapshot = self.sqlite_repository.parity_snapshot()
            self._record(
                compare_learning_memory_parity(
                    self.legacy_repository,
                    legacy,
                    snapshot,
                    operation="load_memory",
                )
            )
        except Exception as error:
            self._record_shadow_error("load_memory", error)
        return deepcopy(legacy)

    def load_progress_history(self):
        legacy = self.legacy_repository.load_progress_history()
        current = self.legacy_repository.load_current_progress_state()
        try:
            snapshot = self.sqlite_repository.parity_snapshot()
            self._record(
                compare_academic_progress_parity(
                    self.legacy_repository,
                    legacy,
                    current,
                    snapshot,
                    operation="load_progress_history",
                )
            )
        except Exception as error:
            self._record_shadow_error("load_progress_history", error)
        return deepcopy(legacy)

    def load_current_progress_state(self):
        legacy = self.legacy_repository.load_current_progress_state()
        history = self.legacy_repository.load_progress_history()
        try:
            snapshot = self.sqlite_repository.parity_snapshot()
            self._record(
                compare_academic_progress_parity(
                    self.legacy_repository,
                    history,
                    legacy,
                    snapshot,
                    operation="load_current_progress_state",
                )
            )
        except Exception as error:
            self._record_shadow_error("load_current_progress_state", error)
        return deepcopy(legacy)

    def load_state(self):
        legacy = self.legacy_repository.load_state()
        try:
            snapshot = self.sqlite_repository.parity_snapshot()
            memory_report = compare_learning_memory_parity(
                self.legacy_repository,
                legacy["memory"],
                snapshot,
                operation="load_state:memory",
            )
            progress_report = compare_academic_progress_parity(
                self.legacy_repository,
                legacy["progress_history"],
                legacy["current_progress"],
                snapshot,
                operation="load_state:progress",
            )
            self._record(memory_report)
            self._record(progress_report)
        except Exception as error:
            self._record_shadow_error("load_state", error)
        return deepcopy(legacy)

    def save_memory(self, memory):
        return self.legacy_repository.save_memory(memory)

    def save_progress_history(self, history):
        return self.legacy_repository.save_progress_history(history)


def build_learning_progress_repository(
    config: Union[LearningProgressBackendConfig, str] = LearningProgressBackendConfig(),
    *,
    legacy_repository: Optional[LegacyJsonLearningProgressRepository] = None,
    memory_path: Optional[Union[str, Path]] = None,
    progress_path: Optional[Union[str, Path]] = None,
    courses_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteLearningProgressRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    selected = config if isinstance(config, LearningProgressBackendConfig) else LearningProgressBackendConfig(config)
    legacy = legacy_repository or LegacyJsonLearningProgressRepository(
        memory_path=memory_path,
        progress_path=progress_path,
        courses_path=courses_path,
    )
    if selected.mode == "legacy":
        return legacy
    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteLearningProgressRepository(sqlite_connection)
    return DualReadLearningProgressRepository(
        legacy,
        shadow,
        diagnostic_sink=diagnostic_sink,
    )


create_learning_progress_repository = build_learning_progress_repository


__all__ = (
    "DualReadLearningProgressRepository",
    "LearningProgressBackendConfig",
    "LearningProgressParityDiagnostic",
    "LearningProgressParityReport",
    "build_learning_progress_repository",
    "compare_academic_progress_parity",
    "compare_learning_memory_parity",
    "create_learning_progress_repository",
)
