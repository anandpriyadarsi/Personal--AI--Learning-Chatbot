"""Explicit Phase 4.1 Courses/Topics storage backend configuration.

Only ``legacy`` and ``dual_read`` modes are intentionally supported here.
Dual-read always returns/writes the legacy repository while independently
reading the Phase 3 SQLite shadow and recording structured parity diagnostics.
SQLite cannot become authoritative through this module in Phase 4.1.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.json.course_repository import (
    LegacyJsonCourseRepository,
)
from personal_learning_assistant.repositories.sqlite.course_repository import (
    SQLiteCourseRepository,
)


DiagnosticSink = Callable[["CourseParityReport"], None]


@dataclass(frozen=True)
class CourseBackendConfig:
    """Explicit Phase 4.1 backend selection."""

    mode: str = "legacy"

    def __post_init__(self):
        normalized = str(self.mode or "").strip().lower().replace("-", "_")
        if normalized not in {"legacy", "dual_read"}:
            raise ValueError(
                "Phase 4.1 course backend must be 'legacy' or 'dual_read'."
            )
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class ParityDiagnostic:
    """One explicit parity observation; mismatches are never normalized away."""

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
class CourseParityReport:
    """Structured result from one independent JSON-vs-SQLite read comparison."""

    operation: str
    diagnostics: Tuple[ParityDiagnostic, ...]

    @property
    def mismatch_count(self) -> int:
        return sum(
            diagnostic.status in {"mismatch", "error"}
            for diagnostic in self.diagnostics
        )

    @property
    def deferred_count(self) -> int:
        return sum(
            diagnostic.status == "deferred"
            for diagnostic in self.diagnostics
        )

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


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _alias_values(value: Any) -> Tuple[str, ...]:
    """Return raw alias text without hiding whitespace/case differences."""
    if value is None:
        return ()
    if isinstance(value, str):
        candidates: Iterable[Any] = (value,)
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        candidates = (value,)
    result = []
    seen = set()
    for candidate in candidates:
        text = str(candidate)
        if not text.strip() or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _read_legacy_raw(repository: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    path_value = getattr(repository, "path", None)
    if path_value is None:
        return None, "legacy repository does not expose a source path"
    path = Path(path_value)
    if not path.exists():
        return {}, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, "unable to read raw legacy evidence: {}".format(error)
    if not isinstance(raw, dict):
        return None, "raw legacy courses source is not a JSON object"
    return raw, None


def _legacy_semantic_snapshot(
    repository: Any,
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    courses = list(state.get("courses", []) or [])
    catalogue = []
    semester_mappings = []
    topics = []
    course_statuses = []
    topic_statuses = []
    topic_order = []
    for course in courses:
        course_id = str(course.get("id", ""))
        catalogue.append(
            {
                "id": course_id,
                "code": str(course.get("code", "")),
                "name": str(course.get("name", "")),
                "status": str(course.get("status", "active")),
            }
        )
        semester_mappings.append(
            {
                "course_id": course_id,
                "semester": str(course.get("semester", "")),
            }
        )
        course_statuses.append((course_id, str(course.get("status", "active"))))
        names = []
        for topic in course.get("topics", []) or []:
            name = str(topic.get("name", ""))
            names.append(name)
            topics.append(
                {
                    "course_id": course_id,
                    "name": name,
                    "status": str(topic.get("status", "not_started")),
                    "confidence": int(topic.get("confidence", 0) or 0),
                    "last_updated": topic.get("last_updated"),
                }
            )
            topic_statuses.append(
                (course_id, name, str(topic.get("status", "not_started")))
            )
        topic_order.append((course_id, tuple(names)))

    raw, raw_error = _read_legacy_raw(repository)
    raw_course_identities: List[Dict[str, Any]] = []
    raw_topic_identities: List[Dict[str, Any]] = []
    legacy_course_aliases: List[Dict[str, Any]] = []
    legacy_topic_aliases: List[Dict[str, Any]] = []
    raw_document_links: Dict[str, Any] = {}
    raw_version: Any = state.get("version", 1)

    if isinstance(raw, dict):
        raw_version = raw.get("version", raw_version)
        raw_courses = raw.get("courses", [])
        if not isinstance(raw_courses, list):
            raw_courses = []
        normalized_by_position = courses
        for course_position, raw_course in enumerate(raw_courses):
            if not isinstance(raw_course, dict):
                continue
            normalized = (
                normalized_by_position[course_position]
                if course_position < len(normalized_by_position)
                else {}
            )
            legacy_id = str(normalized.get("id", raw_course.get("id", "")))
            code = _clean_text(raw_course.get("code")) or str(normalized.get("code", ""))
            raw_course_identities.append(
                {
                    "position": course_position,
                    "raw_id": _raw_text(raw_course.get("id")),
                    "legacy_id": legacy_id,
                    "code": _raw_text(raw_course.get("code")),
                    "raw_status": _raw_text(raw_course.get("status")),
                }
            )
            aliases = _alias_values(raw_course.get("aliases")) + _alias_values(
                raw_course.get("alias")
            )
            seen_aliases = set()
            for alias in aliases:
                folded = _clean_text(alias).casefold()
                if folded in seen_aliases:
                    continue
                seen_aliases.add(folded)
                legacy_course_aliases.append(
                    {
                        "course_id": legacy_id,
                        "alias": alias,
                        "normalized_alias": folded,
                        "provider": "",
                        "source": "legacy_json",
                    }
                )
            raw_topics = raw_course.get("topics", [])
            if not isinstance(raw_topics, list):
                raw_topics = []
            for topic_position, raw_topic in enumerate(raw_topics):
                if isinstance(raw_topic, str):
                    raw_topic = {"name": raw_topic}
                if not isinstance(raw_topic, dict):
                    continue
                name = _clean_text(raw_topic.get("name"))
                raw_status = _clean_text(raw_topic.get("status"))
                raw_topic_identities.append(
                    {
                        "course_id": legacy_id,
                        "expected_course_id": legacy_id,
                        "position": topic_position,
                        "raw_id": _raw_text(raw_topic.get("id")),
                        "name": _raw_text(raw_topic.get("name")),
                        "raw_status": _raw_text(raw_topic.get("status")),
                        "raw_import_status": raw_status,
                    }
                )
                topic_aliases = _alias_values(raw_topic.get("aliases")) + _alias_values(
                    raw_topic.get("alias")
                )
                seen_topic_aliases = set()
                for alias in topic_aliases:
                    folded = _clean_text(alias).casefold()
                    if folded in seen_topic_aliases:
                        continue
                    seen_topic_aliases.add(folded)
                    legacy_topic_aliases.append(
                        {
                            "course_id": legacy_id,
                            "topic": name,
                            "alias": alias,
                            "normalized_alias": folded,
                            "source": "legacy_json",
                        }
                    )
        document_links = raw.get("document_links", {})
        if isinstance(document_links, dict):
            raw_document_links = deepcopy(document_links)
    else:
        # Without raw evidence, retain semantic state and make the evidence gap
        # explicit in the final diagnostic instead of inventing identities.
        for position, course in enumerate(courses):
            legacy_id = str(course.get("id", ""))
            raw_course_identities.append(
                {
                    "position": position,
                    "raw_id": legacy_id,
                    "legacy_id": legacy_id,
                    "code": str(course.get("code", "")),
                    "raw_status": str(course.get("status", "")),
                }
            )
            for topic_position, topic in enumerate(course.get("topics", []) or []):
                status = str(topic.get("status", ""))
                raw_topic_identities.append(
                    {
                        "course_id": legacy_id,
                        "expected_course_id": legacy_id,
                        "position": topic_position,
                        "raw_id": "",
                        "name": str(topic.get("name", "")),
                        "raw_status": status,
                        "raw_import_status": status,
                    }
                )
        links = state.get("document_links", {})
        if isinstance(links, dict):
            raw_document_links = deepcopy(links)

    return {
        "source_version": raw_version,
        "course_catalogue": tuple(catalogue),
        "active_course_id": state.get("active_course_id"),
        "semester_mappings": tuple(semester_mappings),
        "topics": tuple(topics),
        "course_order": tuple(item["id"] for item in catalogue),
        "topic_order": tuple(topic_order),
        "course_statuses": tuple(course_statuses),
        "topic_statuses": tuple(topic_statuses),
        "raw_identities": {
            "courses": tuple(raw_course_identities),
            "topics": tuple(raw_topic_identities),
        },
        "course_aliases": tuple(legacy_course_aliases),
        "topic_aliases": tuple(legacy_topic_aliases),
        "document_relationships": raw_document_links,
        "raw_evidence_error": raw_error,
    }


def _project_semester_mappings(items: Sequence[Mapping[str, Any]]) -> Tuple[Dict[str, Any], ...]:
    return tuple(
        {
            "course_id": str(item.get("course_id", "")),
            "semester": str(item.get("semester", "")),
        }
        for item in items
    )


def _project_raw_identities(value: Mapping[str, Any]) -> Dict[str, Any]:
    courses = []
    for item in value.get("courses", ()):
        courses.append(
            {
                "position": int(item.get("position", len(courses))),
                "raw_id": str(item.get("raw_id", "")),
                "legacy_id": str(item.get("legacy_id", "")),
                "code": str(item.get("code", "")),
                "raw_status": str(item.get("raw_status", "")),
            }
        )
    topics = []
    for item in value.get("topics", ()):
        topics.append(
            {
                "course_id": str(item.get("course_id", "")),
                "expected_course_id": str(
                    item.get("expected_course_id", item.get("course_id", ""))
                ),
                "position": int(item.get("position", len(topics))),
                "raw_id": str(item.get("raw_id", "")),
                "name": str(item.get("name", "")),
                "raw_status": str(item.get("raw_status", "")),
                "raw_import_status": str(item.get("raw_import_status", "")),
            }
        )
    return {"courses": tuple(courses), "topics": tuple(topics)}


def _normalized_alias_snapshot(
    items: Sequence[Mapping[str, Any]],
    *,
    topic: bool = False,
) -> Tuple[Dict[str, Any], ...]:
    normalized = []
    for item in items:
        row = {
            "course_id": str(item.get("course_id", "")),
            "alias": str(item.get("alias", "")),
            "normalized_alias": str(item.get("normalized_alias", "")),
            "source": str(item.get("source", "")),
        }
        if topic:
            row["topic"] = str(item.get("topic", ""))
        else:
            row["provider"] = str(item.get("provider", ""))
        normalized.append(row)
    return tuple(normalized)


def _diagnostic(
    domain: str,
    legacy_value: Any,
    sqlite_value: Any,
    *,
    key: str = "",
    message: Optional[str] = None,
) -> ParityDiagnostic:
    equal = legacy_value == sqlite_value
    return ParityDiagnostic(
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
            else "Legacy and SQLite semantic values differ; no normalization was applied to hide the mismatch."
        ),
    )


def compare_course_parity(
    legacy_repository: Any,
    legacy_state: Mapping[str, Any],
    sqlite_snapshot: Mapping[str, Any],
    *,
    operation: str = "load_state",
) -> CourseParityReport:
    """Compare all Phase 4.1 Courses/Topics parity domains explicitly."""
    legacy = _legacy_semantic_snapshot(legacy_repository, legacy_state)
    diagnostics: List[ParityDiagnostic] = []

    diagnostics.append(
        _diagnostic(
            "course_catalogue",
            legacy["course_catalogue"],
            tuple(sqlite_snapshot.get("course_catalogue", ())),
        )
    )
    diagnostics.append(
        _diagnostic(
            "active_course",
            legacy["active_course_id"],
            sqlite_snapshot.get("active_course_id"),
        )
    )
    diagnostics.append(
        _diagnostic(
            "semester_mappings",
            legacy["semester_mappings"],
            _project_semester_mappings(sqlite_snapshot.get("semester_mappings", ())),
        )
    )
    diagnostics.append(
        _diagnostic(
            "topics",
            legacy["topics"],
            tuple(sqlite_snapshot.get("topics", ())),
        )
    )
    diagnostics.append(
        _diagnostic(
            "course_statuses",
            legacy["course_statuses"],
            tuple(sqlite_snapshot.get("course_statuses", ())),
        )
    )
    diagnostics.append(
        _diagnostic(
            "topic_statuses",
            legacy["topic_statuses"],
            tuple(sqlite_snapshot.get("topic_statuses", ())),
        )
    )
    diagnostics.append(
        _diagnostic(
            "course_ordering",
            legacy["course_order"],
            tuple(sqlite_snapshot.get("course_order", ())),
            message=(
                "Course ordering matches legacy source order."
                if legacy["course_order"] == tuple(sqlite_snapshot.get("course_order", ()))
                else "Course ordering differs; ordering is meaningful and was not sorted away."
            ),
        )
    )
    diagnostics.append(
        _diagnostic(
            "topic_ordering",
            legacy["topic_order"],
            tuple(sqlite_snapshot.get("topic_order", ())),
            message=(
                "Topic ordering matches legacy order/SQLite position."
                if legacy["topic_order"] == tuple(sqlite_snapshot.get("topic_order", ()))
                else "Topic ordering differs; SQLite positions were compared directly rather than reordered for parity."
            ),
        )
    )
    diagnostics.append(
        _diagnostic(
            "raw_identities_and_statuses",
            _project_raw_identities(legacy["raw_identities"]),
            _project_raw_identities(sqlite_snapshot.get("raw_identities", {})),
            message=(
                "Raw legacy identities/status evidence matches the Phase 3 migration ledger."
                if _project_raw_identities(legacy["raw_identities"])
                == _project_raw_identities(sqlite_snapshot.get("raw_identities", {}))
                else "Raw identities/status evidence differs; canonical status equality does not suppress this mismatch."
            ),
        )
    )
    diagnostics.append(
        _diagnostic(
            "course_aliases",
            _normalized_alias_snapshot(legacy["course_aliases"]),
            _normalized_alias_snapshot(sqlite_snapshot.get("course_aliases", ())),
        )
    )
    diagnostics.append(
        _diagnostic(
            "topic_aliases",
            _normalized_alias_snapshot(legacy["topic_aliases"], topic=True),
            _normalized_alias_snapshot(
                sqlite_snapshot.get("topic_aliases", ()), topic=True
            ),
        )
    )
    diagnostics.append(
        _diagnostic(
            "source_version",
            legacy["source_version"],
            sqlite_snapshot.get("source_version"),
        )
    )

    if legacy.get("raw_evidence_error"):
        diagnostics.append(
            ParityDiagnostic(
                domain="raw_legacy_evidence",
                status="error",
                key="",
                severity="error",
                legacy_value=legacy.get("raw_evidence_error"),
                sqlite_value=None,
                message="Raw legacy evidence could not be inspected; raw-identity parity is not assumed.",
            )
        )

    anomalies = tuple(sqlite_snapshot.get("anomalies", ()))
    diagnostics.append(
        ParityDiagnostic(
            domain="sqlite_structure",
            status="matched" if not anomalies else "mismatch",
            key="",
            severity="info" if not anomalies else "error",
            legacy_value=(),
            sqlite_value=anomalies,
            message=(
                "SQLite course/topic relationship structure is complete."
                if not anomalies
                else "SQLite course/topic structural anomalies were detected explicitly."
            ),
        )
    )

    document_supported = bool(
        sqlite_snapshot.get("document_relationships_supported", False)
    )
    if document_supported:
        diagnostics.append(
            _diagnostic(
                "course_document_relationships",
                legacy["document_relationships"],
                sqlite_snapshot.get("document_relationships", {}),
            )
        )
    else:
        diagnostics.append(
            ParityDiagnostic(
                domain="course_document_relationships",
                status="deferred",
                key="",
                severity="info",
                legacy_value=deepcopy(legacy["document_relationships"]),
                sqlite_value={
                    "supported": False,
                    "reason": sqlite_snapshot.get(
                        "document_relationships_reason",
                        "Phase 3 did not migrate this relationship.",
                    ),
                },
                message=(
                    "Course-document parity is explicitly deferred because Phase 3.1 did not migrate legacy document_links; legacy remains authoritative for this relationship."
                ),
            )
        )

    return CourseParityReport(
        operation=operation,
        diagnostics=tuple(diagnostics),
    )


class DualReadCourseRepository:
    """Legacy-authoritative repository that shadow-reads SQLite on every read."""

    def __init__(
        self,
        legacy_repository: Any,
        sqlite_repository: SQLiteCourseRepository,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ):
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self._diagnostic_sink = diagnostic_sink
        self._reports: List[CourseParityReport] = []

    @property
    def last_report(self) -> Optional[CourseParityReport]:
        return self._reports[-1] if self._reports else None

    @property
    def reports(self) -> Tuple[CourseParityReport, ...]:
        return tuple(self._reports)

    def _record(self, report: CourseParityReport) -> None:
        self._reports.append(report)
        if self._diagnostic_sink is not None:
            try:
                self._diagnostic_sink(report)
            except Exception:
                # Diagnostics are observational only.  A reporting sink must
                # never be able to break an authoritative legacy read.
                pass

    def _record_sqlite_error(self, operation: str, error: Exception) -> None:
        self._record(
            CourseParityReport(
                operation=operation,
                diagnostics=(
                    ParityDiagnostic(
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
            report = compare_course_parity(
                self.legacy_repository,
                legacy_state,
                sqlite_snapshot,
                operation="load_state",
            )
            self._record(report)
        except Exception as error:  # shadow failure must never replace legacy authority
            self._record_sqlite_error("load_state", error)
        return deepcopy(legacy_state)

    def get_document_link(self, document_key: str):
        legacy_value = self.legacy_repository.get_document_link(document_key)
        try:
            sqlite_value = self.sqlite_repository.get_document_link(document_key)
            if self.sqlite_repository.supports_course_document_links:
                diagnostic = _diagnostic(
                    "course_document_relationships",
                    legacy_value,
                    sqlite_value,
                    key=document_key,
                )
            else:
                diagnostic = ParityDiagnostic(
                    domain="course_document_relationships",
                    status="deferred",
                    key=document_key,
                    severity="info",
                    legacy_value=deepcopy(legacy_value),
                    sqlite_value={
                        "supported": False,
                        "reason": self.sqlite_repository.course_document_relationship_support,
                    },
                    message="Legacy document-link read returned authoritatively; SQLite comparison is explicitly deferred in Phase 4.1.",
                )
            self._record(
                CourseParityReport(
                    operation="get_document_link",
                    diagnostics=(diagnostic,),
                )
            )
        except Exception as error:
            self._record_sqlite_error("get_document_link", error)
        return deepcopy(legacy_value)

    def list_document_links(self):
        legacy_value = self.legacy_repository.list_document_links()
        try:
            sqlite_value = self.sqlite_repository.list_document_links()
            if self.sqlite_repository.supports_course_document_links:
                diagnostic = _diagnostic(
                    "course_document_relationships",
                    legacy_value,
                    sqlite_value,
                )
            else:
                diagnostic = ParityDiagnostic(
                    domain="course_document_relationships",
                    status="deferred",
                    key="",
                    severity="info",
                    legacy_value=deepcopy(legacy_value),
                    sqlite_value={
                        "supported": False,
                        "reason": self.sqlite_repository.course_document_relationship_support,
                    },
                    message="Legacy document-link catalogue returned authoritatively; SQLite comparison is explicitly deferred in Phase 4.1.",
                )
            self._record(
                CourseParityReport(
                    operation="list_document_links",
                    diagnostics=(diagnostic,),
                )
            )
        except Exception as error:
            self._record_sqlite_error("list_document_links", error)
        return deepcopy(legacy_value)

    # Commands remain legacy-only.  This intentionally preserves every existing
    # writer while preventing an accidental Phase 4.1 dual-write or authority flip.
    def save_state(self, state):
        return self.legacy_repository.save_state(state)

    def upsert_document_link(self, document_key: str, link):
        return self.legacy_repository.upsert_document_link(document_key, link)

    def delete_document_link(self, document_key: str) -> bool:
        return self.legacy_repository.delete_document_link(document_key)


def build_course_repository(
    config: Union[CourseBackendConfig, str] = CourseBackendConfig(),
    *,
    legacy_repository: Optional[Any] = None,
    legacy_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteCourseRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    """Build an explicit Phase 4.1 course repository backend.

    ``legacy`` returns the existing JSON adapter. ``dual_read`` wraps it with a
    SQLite shadow reader.  No ``sqlite``-authoritative mode exists in Phase 4.1.
    """
    selected = config if isinstance(config, CourseBackendConfig) else CourseBackendConfig(config)
    legacy = legacy_repository or LegacyJsonCourseRepository(path=legacy_path)
    if selected.mode == "legacy":
        return legacy

    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteCourseRepository(sqlite_connection)
    return DualReadCourseRepository(
        legacy,
        shadow,
        diagnostic_sink=diagnostic_sink,
    )


# Discoverable alias for callers that prefer factory naming.
create_course_repository = build_course_repository


__all__ = (
    "CourseBackendConfig",
    "CourseParityReport",
    "DualReadCourseRepository",
    "ParityDiagnostic",
    "build_course_repository",
    "compare_course_parity",
    "create_course_repository",
)
