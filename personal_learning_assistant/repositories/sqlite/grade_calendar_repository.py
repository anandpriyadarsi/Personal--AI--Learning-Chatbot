"""Read-only Phase 4.8 SQLite repository for Grades + Academic Calendar.

SQLite is shadow state only.  An explicit ``sqlite3.Connection`` is required;
this module never opens or creates a database by path and exposes no mutations.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence, Tuple


GRADE_SOURCE_PATH = "data/semester_grade_config.json"
ASSESSMENT_SOURCE_PATH = "data/assessments.json"
COURSE_SOURCE_PATH = "data/courses.json"

_REQUIRED_TABLES = {
    "migration_imports",
    "semesters",
    "courses",
    "semester_courses",
    "assessments",
    "grade_scales",
    "grade_bands",
    "semester_grade_settings",
    "manual_grade_entries",
    "semester_results",
    "academic_events",
}


class SQLiteGradeCalendarRepositoryError(RuntimeError):
    pass


class SQLiteGradeCalendarRepositorySchemaError(SQLiteGradeCalendarRepositoryError):
    pass


class SQLiteGradeCalendarRepositoryDataError(SQLiteGradeCalendarRepositoryError):
    pass


class SQLiteGradeCalendarRepositoryReadOnlyError(SQLiteGradeCalendarRepositoryError):
    pass


def _fetch_dicts(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] = (),
) -> Tuple[Dict[str, Any], ...]:
    cursor = connection.execute(sql, tuple(params))
    columns = tuple(item[0] for item in cursor.description or ())
    return tuple(
        {columns[index]: value for index, value in enumerate(tuple(row))}
        for row in cursor.fetchall()
    )


def _details(raw: Any, *, context: str) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SQLiteGradeCalendarRepositoryDataError(
            f"Invalid migration details for {context}."
        ) from error
    if not isinstance(value, dict):
        raise SQLiteGradeCalendarRepositoryDataError(
            f"Migration details for {context} must be an object."
        )
    return value


class SQLiteGradeCalendarRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("SQLiteGradeCalendarRepository requires sqlite3.Connection")
        self.connection = connection
        self._validate_schema()

    def _validate_schema(self) -> None:
        rows = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        names = {str(row[0]) for row in rows}
        missing = sorted(_REQUIRED_TABLES - names)
        if missing:
            raise SQLiteGradeCalendarRepositorySchemaError(
                "Phase 4.8 SQLite schema is incomplete; missing: {}".format(
                    ", ".join(missing)
                )
            )

    def _ledger_rows(
        self,
        *,
        source_path: str,
        source_hash: Optional[str] = None,
        target_table: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], ...]:
        clauses = ["source_path = ?", "source_type = 'legacy_json'"]
        params: List[Any] = [source_path]
        if source_hash is not None:
            clauses.append("source_hash = ?")
            params.append(source_hash)
        if target_table is not None:
            clauses.append("target_table = ?")
            params.append(target_table)
        return _fetch_dicts(
            self.connection,
            "SELECT source_path, source_hash, source_version, legacy_key, "
            "target_table, target_id, imported_at, details_json "
            "FROM migration_imports WHERE {} "
            "ORDER BY target_table, legacy_key, target_id".format(" AND ".join(clauses)),
            params,
        )

    @staticmethod
    def _duplicate_identity_issues(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, str], set[str]] = {}
        for row in rows:
            key = (str(row["target_table"]), str(row["legacy_key"]))
            grouped.setdefault(key, set()).add(str(row["target_id"]))
        issues = []
        for (table, legacy_key), targets in sorted(grouped.items()):
            if len(targets) > 1:
                issues.append(
                    {
                        "code": "duplicate_legacy_identity",
                        "table": table,
                        "legacy_key": legacy_key,
                        "targets": sorted(targets),
                    }
                )
        return issues

    def load_grade_state(self, source_hash: Optional[str]) -> Dict[str, Any]:
        """Return the current imported grade semantics for one source hash."""
        if source_hash is None:
            return {
                "source_present": False,
                "source_hash": None,
                "source_version": None,
                "scale": None,
                "semester_settings": None,
                "courses": [],
                "manual_entries": [],
                "semester_result": None,
                "historical_rows": 0,
                "issues": [],
            }

        rows = self._ledger_rows(source_path=GRADE_SOURCE_PATH, source_hash=source_hash)
        issues = self._duplicate_identity_issues(rows)
        source_version = rows[0]["source_version"] if rows else None

        scale_rows = [row for row in rows if row["target_table"] == "grade_scales"]
        scale = None
        if len(scale_rows) > 1:
            issues.append({"code": "multiple_current_grade_scales", "count": len(scale_rows)})
        if scale_rows:
            ledger = scale_rows[0]
            db_rows = _fetch_dicts(
                self.connection,
                "SELECT id, name, source, verified, active_from, active_to, created_at, updated_at "
                "FROM grade_scales WHERE id = ?",
                (ledger["target_id"],),
            )
            if not db_rows:
                issues.append({"code": "missing_grade_scale_target", "target_id": ledger["target_id"]})
            else:
                db = db_rows[0]
                bands = _fetch_dicts(
                    self.connection,
                    "SELECT id, minimum_bps, letter_grade, grade_point_milli "
                    "FROM grade_bands WHERE scale_id = ? ORDER BY minimum_bps DESC, id",
                    (db["id"],),
                )
                current_band_targets = {
                    str(row["target_id"])
                    for row in rows
                    if row["target_table"] == "grade_bands"
                }
                actual_band_targets = {str(row["id"]) for row in bands}
                if current_band_targets != actual_band_targets:
                    issues.append(
                        {
                            "code": "grade_band_target_set_mismatch",
                            "ledger_targets": sorted(current_band_targets),
                            "relational_targets": sorted(actual_band_targets),
                        }
                    )
                scale = {
                    "id": str(db["id"]),
                    "name": db["name"],
                    "source": db["source"],
                    "verified": int(db["verified"]),
                    "active_from": db["active_from"],
                    "active_to": db["active_to"],
                    "bands": [
                        {
                            "minimum_bps": int(item["minimum_bps"]),
                            "letter_grade": item["letter_grade"],
                            "grade_point_milli": int(item["grade_point_milli"]),
                        }
                        for item in bands
                    ],
                    "details": _details(ledger["details_json"], context="grade scale"),
                }

        settings_rows = [row for row in rows if row["target_table"] == "semester_grade_settings"]
        settings = None
        if len(settings_rows) > 1:
            issues.append({"code": "multiple_current_semester_grade_settings", "count": len(settings_rows)})
        if settings_rows:
            ledger = settings_rows[0]
            db_rows = _fetch_dicts(
                self.connection,
                "SELECT sgs.semester_id, s.name AS semester_name, sgs.scale_id, "
                "sgs.target_sgpa_milli, sgs.updated_at "
                "FROM semester_grade_settings AS sgs "
                "JOIN semesters AS s ON s.id = sgs.semester_id "
                "WHERE sgs.semester_id = ?",
                (ledger["target_id"],),
            )
            if not db_rows:
                issues.append({"code": "missing_semester_grade_settings_target", "target_id": ledger["target_id"]})
            else:
                db = db_rows[0]
                settings = {
                    "semester_id": str(db["semester_id"]),
                    "semester_name": db["semester_name"],
                    "scale_id": str(db["scale_id"]),
                    "target_sgpa_milli": db["target_sgpa_milli"],
                    "details": _details(ledger["details_json"], context="semester settings"),
                }
                if scale is not None and settings["scale_id"] != scale["id"]:
                    issues.append({"code": "settings_scale_relationship_mismatch"})

        courses: List[Dict[str, Any]] = []
        for ledger in [row for row in rows if row["target_table"] == "semester_courses"]:
            details = _details(ledger["details_json"], context="semester course credit")
            course_id = str(details.get("target_course_id") or "")
            semester_id = settings["semester_id"] if settings else ""
            db_rows = _fetch_dicts(
                self.connection,
                "SELECT sc.semester_id, sc.course_id, sc.credits_milli, c.code "
                "FROM semester_courses AS sc JOIN courses AS c ON c.id = sc.course_id "
                "WHERE sc.semester_id = ? AND sc.course_id = ?",
                (semester_id, course_id),
            ) if semester_id and course_id else ()
            if not db_rows:
                issues.append({"code": "missing_semester_course_target", "legacy_key": ledger["legacy_key"]})
                continue
            db = db_rows[0]
            courses.append(
                {
                    "legacy_key": ledger["legacy_key"],
                    "raw_course_id": str(details.get("raw_course_id") or ""),
                    "course_id": str(db["course_id"]),
                    "course_code": db["code"],
                    "credits_milli": db["credits_milli"],
                    "raw": deepcopy(details.get("raw")),
                }
            )

        manual_entries: List[Dict[str, Any]] = []
        for ledger in [row for row in rows if row["target_table"] == "manual_grade_entries"]:
            details = _details(ledger["details_json"], context="manual grade")
            db_rows = _fetch_dicts(
                self.connection,
                "SELECT id, semester_id, course_id, score_bps, letter_grade, "
                "grade_point_milli, entry_kind, note, recorded_at "
                "FROM manual_grade_entries WHERE id = ?",
                (ledger["target_id"],),
            )
            if not db_rows:
                issues.append({"code": "missing_manual_grade_target", "target_id": ledger["target_id"]})
                continue
            db = db_rows[0]
            if settings and str(db["semester_id"]) != settings["semester_id"]:
                issues.append({"code": "manual_grade_wrong_semester", "target_id": db["id"]})
            manual_entries.append(
                {
                    "id": str(db["id"]),
                    "legacy_key": ledger["legacy_key"],
                    "raw_course_id": str(details.get("raw_course_id") or ""),
                    "course_id": str(db["course_id"]),
                    "score_bps": db["score_bps"],
                    "letter_grade": db["letter_grade"],
                    "grade_point_milli": db["grade_point_milli"],
                    "entry_kind": db["entry_kind"],
                    "note": db["note"],
                    "recorded_at": db["recorded_at"],
                    "raw": deepcopy(details.get("raw")),
                }
            )

        result_rows = [row for row in rows if row["target_table"] == "semester_results"]
        semester_result = None
        if len(result_rows) > 1:
            issues.append({"code": "multiple_current_semester_results", "count": len(result_rows)})
        if result_rows:
            ledger = result_rows[0]
            db_rows = _fetch_dicts(
                self.connection,
                "SELECT id, semester_id, earned_credits_milli, earned_grade_points_milli, "
                "sgpa_milli, verified, source, recorded_at FROM semester_results WHERE id = ?",
                (ledger["target_id"],),
            )
            if not db_rows:
                issues.append({"code": "missing_semester_result_target", "target_id": ledger["target_id"]})
            else:
                db = db_rows[0]
                semester_result = {
                    "id": str(db["id"]),
                    "semester_id": str(db["semester_id"]),
                    "earned_credits_milli": int(db["earned_credits_milli"]),
                    "earned_grade_points_milli": int(db["earned_grade_points_milli"]),
                    "sgpa_milli": int(db["sgpa_milli"]),
                    "verified": int(db["verified"]),
                    "source": db["source"],
                    "recorded_at": db["recorded_at"],
                    "details": _details(ledger["details_json"], context="semester result"),
                }

        all_rows = self._ledger_rows(source_path=GRADE_SOURCE_PATH)
        historical = sum(str(row["source_hash"]) != str(source_hash) for row in all_rows)
        return {
            "source_present": True,
            "source_hash": source_hash,
            "source_version": source_version,
            "scale": scale,
            "semester_settings": settings,
            "courses": courses,
            "manual_entries": manual_entries,
            "semester_result": semester_result,
            "historical_rows": historical,
            "issues": issues,
        }

    def load_calendar_state(self, assessment_source_hash: str) -> Dict[str, Any]:
        rows = self._ledger_rows(
            source_path=ASSESSMENT_SOURCE_PATH,
            source_hash=assessment_source_hash,
            target_table="academic_events",
        )
        issues = self._duplicate_identity_issues(rows)
        events: List[Dict[str, Any]] = []
        for ledger in rows:
            db_rows = _fetch_dicts(
                self.connection,
                "SELECT ae.id, ae.semester_id, ae.course_id, ae.event_kind, ae.title, "
                "ae.starts_at, ae.ends_at, ae.all_day, ae.reference_type, ae.reference_id, "
                "ae.status, ae.source_entity_type, ae.source_entity_id, ae.deleted_at, "
                "a.course_id AS assessment_course_id, a.title AS assessment_title "
                "FROM academic_events AS ae "
                "LEFT JOIN assessments AS a ON a.id = ae.reference_id "
                "WHERE ae.id = ?",
                (ledger["target_id"],),
            )
            if not db_rows:
                issues.append({"code": "missing_academic_event_target", "target_id": ledger["target_id"]})
                continue
            db = db_rows[0]
            assessment_id = str(db["reference_id"] or "")
            assessment_ledger = _fetch_dicts(
                self.connection,
                "SELECT legacy_key, details_json FROM migration_imports "
                "WHERE source_path = ? AND source_hash = ? "
                "AND source_type = 'legacy_json' AND target_table = 'assessments' "
                "AND target_id = ? ORDER BY legacy_key",
                (ASSESSMENT_SOURCE_PATH, assessment_source_hash, assessment_id),
            )
            assessment_legacy_key = assessment_ledger[0]["legacy_key"] if assessment_ledger else ""
            raw_assessment_id = (
                str(assessment_legacy_key)[len("assessment:id:"):]
                if str(assessment_legacy_key).startswith("assessment:id:")
                else str(assessment_legacy_key)
            )
            if not assessment_ledger:
                issues.append({"code": "missing_current_assessment_ledger", "target_id": assessment_id})
            if db["event_kind"] != "assessment_deadline":
                issues.append({"code": "wrong_academic_event_kind", "target_id": db["id"]})
            if db["reference_type"] != "assessment" or db["source_entity_type"] != "assessment":
                issues.append({"code": "wrong_academic_event_reference_type", "target_id": db["id"]})
            if str(db["source_entity_id"] or "") != assessment_id:
                issues.append({"code": "wrong_academic_event_source_id", "target_id": db["id"]})
            if db["assessment_course_id"] is None:
                issues.append({"code": "missing_assessment_relationship", "target_id": db["id"]})
            elif str(db["course_id"] or "") != str(db["assessment_course_id"]):
                issues.append({"code": "academic_event_wrong_course", "target_id": db["id"]})
            events.append(
                {
                    "id": str(db["id"]),
                    "legacy_key": ledger["legacy_key"],
                    "assessment_id": assessment_id,
                    "raw_assessment_id": raw_assessment_id,
                    "assessment_legacy_key": assessment_legacy_key,
                    "course_id": str(db["course_id"] or ""),
                    "semester_id": None if db["semester_id"] is None else str(db["semester_id"]),
                    "title": db["title"],
                    "starts_at": db["starts_at"],
                    "ends_at": db["ends_at"],
                    "all_day": int(db["all_day"]),
                    "status": db["status"],
                    "deleted_at": db["deleted_at"],
                }
            )

        historical_rows = self._ledger_rows(
            source_path=ASSESSMENT_SOURCE_PATH,
            target_table="academic_events",
        )
        historical = sum(
            str(row["source_hash"]) != str(assessment_source_hash)
            for row in historical_rows
        )
        return {
            "source_hash": assessment_source_hash,
            "events": events,
            "historical_rows": historical,
            "issues": issues,
        }

    def load_state(
        self,
        *,
        grade_source_hash: Optional[str],
        assessment_source_hash: str,
    ) -> Dict[str, Any]:
        return {
            "grades": self.load_grade_state(grade_source_hash),
            "calendar": self.load_calendar_state(assessment_source_hash),
        }

    # SQLite remains observation-only throughout Phase 4.8.
    def save_grade_config(self, value: Any) -> None:
        raise SQLiteGradeCalendarRepositoryReadOnlyError(
            "Phase 4.8 SQLite Grades + Academic Calendar repository is read-only."
        )

    def save_state(self, value: Any) -> None:
        raise SQLiteGradeCalendarRepositoryReadOnlyError(
            "Phase 4.8 SQLite Grades + Academic Calendar repository is read-only."
        )


__all__ = (
    "ASSESSMENT_SOURCE_PATH",
    "COURSE_SOURCE_PATH",
    "GRADE_SOURCE_PATH",
    "SQLiteGradeCalendarRepository",
    "SQLiteGradeCalendarRepositoryDataError",
    "SQLiteGradeCalendarRepositoryError",
    "SQLiteGradeCalendarRepositoryReadOnlyError",
    "SQLiteGradeCalendarRepositorySchemaError",
)
