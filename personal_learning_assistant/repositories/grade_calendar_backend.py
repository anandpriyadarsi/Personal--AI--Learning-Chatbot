"""Legacy-authoritative Phase 4.8 Grades + Academic Calendar dual-read backend."""

from __future__ import annotations

import hashlib
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from personal_learning_assistant.repositories.json.grade_calendar_repository import (
    LegacyJsonGradeCalendarRepository,
)
from personal_learning_assistant.repositories.sqlite.grade_calendar_repository import (
    SQLiteGradeCalendarRepository,
)


@dataclass(frozen=True)
class GradeCalendarBackendConfig:
    mode: str = "legacy"

    def __post_init__(self) -> None:
        value = str(self.mode or "").strip().lower().replace("-", "_")
        if value not in {"legacy", "dual_read"}:
            raise ValueError("Phase 4.8 backend must be 'legacy' or 'dual_read'.")
        object.__setattr__(self, "mode", value)


@dataclass(frozen=True)
class GradeCalendarParityDiagnostic:
    domain: str
    status: str
    key: str
    severity: str
    legacy_value: Any
    sqlite_value: Any
    message: str
    entity_type: str = ""
    course_id: str = ""

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
        }


@dataclass(frozen=True)
class GradeCalendarParityReport:
    operation: str
    diagnostics: Tuple[GradeCalendarParityDiagnostic, ...]

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


DiagnosticSink = Callable[[GradeCalendarParityReport], None]


def _hash_if_present(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scaled(value: Any, factor: int, maximum: Optional[Decimal] = None) -> Optional[int]:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    if maximum is not None and number > maximum:
        return None
    return int((number * Decimal(factor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _diag(
    diagnostics: List[GradeCalendarParityDiagnostic],
    *,
    domain: str,
    key: str,
    legacy: Any,
    sqlite: Any,
    message: str,
    entity_type: str,
    course_id: str = "",
    status: Optional[str] = None,
    severity: Optional[str] = None,
) -> None:
    same = legacy == sqlite
    diagnostics.append(
        GradeCalendarParityDiagnostic(
            domain=domain,
            status=status or ("match" if same else "mismatch"),
            key=key,
            severity=severity or ("info" if same else "warning"),
            legacy_value=deepcopy(legacy),
            sqlite_value=deepcopy(sqlite),
            message=message,
            entity_type=entity_type,
            course_id=course_id,
        )
    )


def _legacy_grade_projection(config: Mapping[str, Any]) -> Dict[str, Any]:
    bands = []
    raw_scale = config.get("grade_scale", [])
    if isinstance(raw_scale, list):
        for raw in raw_scale:
            if not isinstance(raw, Mapping):
                continue
            minimum = _scaled(
                raw.get("min_score", raw.get("minimum_score", raw.get("minimum_percent"))),
                100,
                Decimal("100"),
            )
            point = _scaled(
                raw.get("grade_point", raw.get("point", raw.get("gp"))),
                1000,
                Decimal("10"),
            )
            letter = _clean(raw.get("letter", raw.get("letter_grade", raw.get("grade"))))
            if minimum is not None and point is not None and letter:
                bands.append(
                    {
                        "minimum_bps": minimum,
                        "letter_grade": letter,
                        "grade_point_milli": point,
                    }
                )
    bands.sort(key=lambda item: (-item["minimum_bps"], item["letter_grade"]))

    verified_raw = config.get(
        "grade_scale_verified",
        config.get("scale_verified", config.get("verified", False)),
    )
    verified = 1 if verified_raw in {True, 1, "1", "yes", "true", "verified", "official"} else 0
    scale_source = _clean(config.get("grade_scale_source", config.get("scale_source")))
    if not scale_source:
        scale_source = "legacy_json:data/semester_grade_config.json"

    courses = []
    for raw in config.get("courses", []) if isinstance(config.get("courses", []), list) else []:
        if not isinstance(raw, Mapping):
            continue
        raw_course_id = _clean(raw.get("course_id", raw.get("course_code", raw.get("code"))))
        courses.append(
            {
                "raw_course_id": raw_course_id,
                "credits_milli": _scaled(
                    raw.get("credits", raw.get("credit", raw.get("course_credits"))),
                    1000,
                ),
                "score_bps": _scaled(
                    raw.get("manual_score", raw.get("score_percent", raw.get("score"))),
                    100,
                    Decimal("100"),
                ),
                "letter_grade": _clean(raw.get("manual_letter_grade", raw.get("letter_grade"))) or None,
                "grade_point_milli": _scaled(
                    raw.get("manual_grade_point", raw.get("grade_point")),
                    1000,
                    Decimal("10"),
                ),
            }
        )

    raw_result = config.get("semester_result")
    if raw_result is None:
        raw_result = config.get("semester_results")
        if isinstance(raw_result, list):
            raw_result = raw_result[0] if len(raw_result) == 1 else None
    result = None
    if isinstance(raw_result, Mapping):
        earned_credits = _scaled(raw_result.get("earned_credits", raw_result.get("credits_earned")), 1000)
        earned_points = _scaled(raw_result.get("earned_grade_points", raw_result.get("total_grade_points")), 1000)
        sgpa = _scaled(raw_result.get("sgpa"), 1000, Decimal("10"))
        if None not in {earned_credits, earned_points, sgpa}:
            result = {
                "earned_credits_milli": earned_credits,
                "earned_grade_points_milli": earned_points,
                "sgpa_milli": sgpa,
                "verified": 1 if bool(raw_result.get("verified", False)) else 0,
                "source": _clean(raw_result.get("source")),
            }

    return {
        "semester_name": _clean(config.get("semester_name", config.get("semester"))) or "Semester 1",
        "target_sgpa_milli": _scaled(
            config.get("target_sgpa", config.get("sgpa_target")),
            1000,
            Decimal("10"),
        ),
        "scale": {
            "source": scale_source,
            "verified": verified,
            "active_from": config.get("grade_scale_active_from"),
            "active_to": config.get("grade_scale_active_to"),
            "bands": bands,
        },
        "courses": courses,
        "semester_result": result,
    }


def compare_grade_calendar_parity(
    *,
    legacy_grade_present: bool,
    legacy_grade_config: Mapping[str, Any],
    legacy_deadlines: List[Mapping[str, Any]],
    sqlite_state: Mapping[str, Any],
    operation: str = "load_state",
) -> GradeCalendarParityReport:
    diagnostics: List[GradeCalendarParityDiagnostic] = []
    grades = sqlite_state.get("grades", {}) if isinstance(sqlite_state, Mapping) else {}
    calendar = sqlite_state.get("calendar", {}) if isinstance(sqlite_state, Mapping) else {}

    if not legacy_grade_present:
        _diag(
            diagnostics,
            domain="grades",
            key="source_presence",
            legacy=False,
            sqlite=bool(grades.get("source_present")),
            message="Optional semester grade configuration presence matches.",
            entity_type="grade_source",
        )
    else:
        expected = _legacy_grade_projection(legacy_grade_config)
        _diag(
            diagnostics,
            domain="grades",
            key="source_presence",
            legacy=True,
            sqlite=bool(grades.get("source_present")),
            message="Semester grade configuration has current SQLite import evidence.",
            entity_type="grade_source",
        )
        scale = grades.get("scale") or {}
        _diag(diagnostics, domain="grades", key="grade_scale.bands", legacy=expected["scale"]["bands"], sqlite=scale.get("bands", []), message="Grade-scale thresholds, letters and grade points match.", entity_type="grade_scale")
        _diag(diagnostics, domain="grades", key="grade_scale.verified", legacy=expected["scale"]["verified"], sqlite=scale.get("verified"), message="Planning/verified grade-scale status matches.", entity_type="grade_scale")
        _diag(diagnostics, domain="grades", key="grade_scale.source", legacy=expected["scale"]["source"], sqlite=scale.get("source"), message="Grade-scale source semantics match.", entity_type="grade_scale")
        _diag(diagnostics, domain="grades", key="grade_scale.active_from", legacy=expected["scale"]["active_from"], sqlite=scale.get("active_from"), message="Grade-scale active-from evidence matches.", entity_type="grade_scale")
        _diag(diagnostics, domain="grades", key="grade_scale.active_to", legacy=expected["scale"]["active_to"], sqlite=scale.get("active_to"), message="Grade-scale active-to evidence matches.", entity_type="grade_scale")

        settings = grades.get("semester_settings") or {}
        raw_semester = (settings.get("details") or {}).get("semester_name", settings.get("semester_name"))
        _diag(diagnostics, domain="grades", key="semester.name", legacy=expected["semester_name"], sqlite=raw_semester, message="Configured semester identity matches migration evidence.", entity_type="semester_grade_settings")
        _diag(diagnostics, domain="grades", key="semester.target_sgpa", legacy=expected["target_sgpa_milli"], sqlite=settings.get("target_sgpa_milli"), message="Target SGPA matches.", entity_type="semester_grade_settings")

        actual_courses = {str(item.get("raw_course_id")): item for item in grades.get("courses", [])}
        actual_manual = {str(item.get("raw_course_id")): item for item in grades.get("manual_entries", [])}
        for course in expected["courses"]:
            raw_id = course["raw_course_id"]
            actual = actual_courses.get(raw_id)
            _diag(diagnostics, domain="grades", key=f"course:{raw_id}:present", legacy=course["credits_milli"] is not None, sqlite=actual is not None, message="Configured course-credit relationship is represented when credits exist.", entity_type="semester_course", course_id=raw_id)
            if course["credits_milli"] is not None and actual is not None:
                _diag(diagnostics, domain="grades", key=f"course:{raw_id}:credits", legacy=course["credits_milli"], sqlite=actual.get("credits_milli"), message="Course credits match.", entity_type="semester_course", course_id=raw_id)
            expected_manual_present = any(course[key] is not None for key in ("score_bps", "letter_grade", "grade_point_milli"))
            manual = actual_manual.get(raw_id)
            _diag(diagnostics, domain="grades", key=f"course:{raw_id}:manual_present", legacy=expected_manual_present, sqlite=manual is not None, message="Explicit manual grade evidence presence matches.", entity_type="manual_grade_entry", course_id=raw_id)
            if expected_manual_present and manual is not None:
                for field in ("score_bps", "letter_grade", "grade_point_milli"):
                    _diag(diagnostics, domain="grades", key=f"course:{raw_id}:manual:{field}", legacy=course[field], sqlite=manual.get(field), message=f"Manual grade field {field} matches.", entity_type="manual_grade_entry", course_id=raw_id)

        expected_ids = {item["raw_course_id"] for item in expected["courses"] if item["credits_milli"] is not None}
        extra_ids = sorted(set(actual_courses) - expected_ids)
        if extra_ids:
            _diag(diagnostics, domain="grades", key="courses.extra_current", legacy=[], sqlite=extra_ids, message="SQLite has current course-credit evidence not present in legacy configuration.", entity_type="semester_course")

        result = grades.get("semester_result")
        expected_result = expected["semester_result"]
        _diag(diagnostics, domain="grades", key="semester_result.presence", legacy=expected_result is not None, sqlite=result is not None, message="Explicit semester-result presence matches.", entity_type="semester_result")
        if expected_result is not None and result is not None:
            for field in ("earned_credits_milli", "earned_grade_points_milli", "sgpa_milli", "verified", "source"):
                _diag(diagnostics, domain="grades", key=f"semester_result.{field}", legacy=expected_result[field], sqlite=result.get(field), message=f"Semester result field {field} matches persisted evidence.", entity_type="semester_result")

        for issue in grades.get("issues", []):
            diagnostics.append(
                GradeCalendarParityDiagnostic(
                    domain="grades_structure",
                    status="mismatch",
                    key=str(issue.get("code", "structure")),
                    severity="error",
                    legacy_value="valid legacy relationship",
                    sqlite_value=deepcopy(issue),
                    message="SQLite grade relational structure is inconsistent.",
                    entity_type="sqlite_structure",
                )
            )
        if int(grades.get("historical_rows", 0) or 0) > 0:
            diagnostics.append(
                GradeCalendarParityDiagnostic(
                    domain="grades_history",
                    status="deferred",
                    key="older_source_hash_rows",
                    severity="info",
                    legacy_value="current grade configuration",
                    sqlite_value=int(grades.get("historical_rows", 0)),
                    message="Older grade rows remain historical evidence and are not current authority.",
                    entity_type="historical_grade_evidence",
                )
            )

    expected_deadlines = {str(item.get("assessment_id")): dict(item) for item in legacy_deadlines}
    actual_deadlines = {str(item.get("raw_assessment_id")): item for item in calendar.get("events", []) if item.get("deleted_at") is None}
    _diag(diagnostics, domain="academic_calendar", key="deadline_count", legacy=len(expected_deadlines), sqlite=len(actual_deadlines), message="Current assessment-deadline event count matches.", entity_type="academic_event")
    for assessment_id, expected in expected_deadlines.items():
        actual = actual_deadlines.get(assessment_id)
        _diag(diagnostics, domain="academic_calendar", key=f"assessment:{assessment_id}:event_present", legacy=True, sqlite=actual is not None, message="Assessment with a due date has one current calendar event.", entity_type="academic_event")
        if actual is not None:
            for field in ("title", "starts_at", "all_day", "status"):
                _diag(diagnostics, domain="academic_calendar", key=f"assessment:{assessment_id}:{field}", legacy=expected.get(field), sqlite=actual.get(field), message=f"Academic-event field {field} matches authoritative assessment deadline.", entity_type="academic_event", course_id=str(expected.get("course_id") or ""))
    extras = sorted(set(actual_deadlines) - set(expected_deadlines))
    if extras:
        _diag(diagnostics, domain="academic_calendar", key="extra_current_events", legacy=[], sqlite=extras, message="SQLite has current deadline events without an authoritative due-date assessment.", entity_type="academic_event")

    for issue in calendar.get("issues", []):
        diagnostics.append(
            GradeCalendarParityDiagnostic(
                domain="calendar_structure",
                status="mismatch",
                key=str(issue.get("code", "structure")),
                severity="error",
                legacy_value="valid assessment/event relationship",
                sqlite_value=deepcopy(issue),
                message="SQLite academic-event relationship is inconsistent.",
                entity_type="sqlite_structure",
            )
        )
    if int(calendar.get("historical_rows", 0) or 0) > 0:
        diagnostics.append(
            GradeCalendarParityDiagnostic(
                domain="calendar_history",
                status="deferred",
                key="older_source_hash_rows",
                severity="info",
                legacy_value="current assessment deadlines",
                sqlite_value=int(calendar.get("historical_rows", 0)),
                message="Older deadline-event rows remain historical evidence.",
                entity_type="historical_calendar_evidence",
            )
        )

    return GradeCalendarParityReport(operation=operation, diagnostics=tuple(diagnostics))


class DualReadGradeCalendarRepository:
    def __init__(
        self,
        legacy_repository: LegacyJsonGradeCalendarRepository,
        sqlite_repository: SQLiteGradeCalendarRepository,
        *,
        diagnostic_sink: Optional[DiagnosticSink] = None,
    ) -> None:
        self.legacy_repository = legacy_repository
        self.sqlite_repository = sqlite_repository
        self.diagnostic_sink = diagnostic_sink
        self.last_parity_report: Optional[GradeCalendarParityReport] = None

    def _record(self, report: GradeCalendarParityReport) -> None:
        self.last_parity_report = report
        if self.diagnostic_sink is not None:
            try:
                self.diagnostic_sink(report)
            except Exception:
                pass

    def load_state(self) -> Dict[str, Any]:
        legacy_state = self.legacy_repository.load_state()
        try:
            grade_hash = _hash_if_present(self.legacy_repository.grade_config_path)
            assessment_hash = _hash_if_present(self.legacy_repository.assessments_path)
            if assessment_hash is None:
                raise FileNotFoundError("authoritative assessments.json is unavailable")
            sqlite_state = self.sqlite_repository.load_state(
                grade_source_hash=grade_hash,
                assessment_source_hash=assessment_hash,
            )
            report = compare_grade_calendar_parity(
                legacy_grade_present=bool(legacy_state["grade_source_present"]),
                legacy_grade_config=legacy_state["grade_config"],
                legacy_deadlines=legacy_state["calendar_deadlines"],
                sqlite_state=sqlite_state,
                operation="load_state",
            )
            self._record(report)
        except Exception as error:
            self._record(
                GradeCalendarParityReport(
                    operation="load_state",
                    diagnostics=(
                        GradeCalendarParityDiagnostic(
                            domain="sqlite_read",
                            status="error",
                            key="",
                            severity="error",
                            legacy_value="authoritative legacy result returned",
                            sqlite_value=type(error).__name__,
                            message="SQLite Grades + Academic Calendar shadow read failed: {}".format(error),
                            entity_type="grade_calendar_shadow",
                        ),
                    ),
                )
            )
        return deepcopy(legacy_state)

    def load_grade_config(self):
        return deepcopy(self.load_state()["grade_config"])

    def load_calendar_deadlines(self):
        return deepcopy(self.load_state()["calendar_deadlines"])

    def save_grade_config(self, config):
        return self.legacy_repository.save_grade_config(config)


def build_grade_calendar_repository(
    config: Union[GradeCalendarBackendConfig, str] = GradeCalendarBackendConfig(),
    *,
    legacy_repository: Optional[Any] = None,
    grade_config_path: Optional[Union[str, Path]] = None,
    assessments_path: Optional[Union[str, Path]] = None,
    sqlite_repository: Optional[SQLiteGradeCalendarRepository] = None,
    sqlite_connection: Optional[sqlite3.Connection] = None,
    diagnostic_sink: Optional[DiagnosticSink] = None,
):
    selected = config if isinstance(config, GradeCalendarBackendConfig) else GradeCalendarBackendConfig(config)
    if legacy_repository is None:
        kwargs: Dict[str, Any] = {}
        if grade_config_path is not None:
            kwargs["grade_config_path"] = grade_config_path
        if assessments_path is not None:
            kwargs["assessments_path"] = assessments_path
        legacy_repository = LegacyJsonGradeCalendarRepository(**kwargs)
    if selected.mode == "legacy":
        return legacy_repository
    shadow = sqlite_repository
    if shadow is None:
        if sqlite_connection is None:
            raise ValueError(
                "dual_read requires an explicit SQLite connection or repository; no production database is opened implicitly."
            )
        shadow = SQLiteGradeCalendarRepository(sqlite_connection)
    return DualReadGradeCalendarRepository(
        legacy_repository,
        shadow,
        diagnostic_sink=diagnostic_sink,
    )


create_grade_calendar_repository = build_grade_calendar_repository


__all__ = (
    "DualReadGradeCalendarRepository",
    "GradeCalendarBackendConfig",
    "GradeCalendarParityDiagnostic",
    "GradeCalendarParityReport",
    "build_grade_calendar_repository",
    "compare_grade_calendar_parity",
    "create_grade_calendar_repository",
)
