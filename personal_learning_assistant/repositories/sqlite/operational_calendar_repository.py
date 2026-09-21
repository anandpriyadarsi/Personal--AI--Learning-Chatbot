"""SQLite calendar/routine adapter for the Phase 7.5.13 Operational Planner."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class OperationalCalendarRepositoryError(RuntimeError):
    """Operational calendar storage is unavailable or inconsistent."""


class OperationalCalendarRepositoryNotFoundError(OperationalCalendarRepositoryError):
    """A requested assessment/calendar item was not found."""


def _open(path: Path, *, writable: bool):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise OperationalCalendarRepositoryError("Operational planner storage is unavailable.")
    uri = quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    c = sqlite3.connect(
        "file:{}?mode={}".format(uri, "rw" if writable else "ro"),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 5000")
    return c


class SQLiteOperationalCalendarRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _connect(self, *, writable: bool):
        c = _open(self.database_path, writable=writable)
        tables = {str(r[0]) for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        required = {
            "academic_events", "routine_templates", "assessments",
            "courses", "month_plan_import_items", "study_plan_items",
        }
        if required - tables:
            c.close()
            raise OperationalCalendarRepositoryError(
                "Operational planner migration is not applied."
            )
        return c

    def list_academic_events(self, starts_on, ends_on):
        c = self._connect(writable=False)
        try:
            rows = c.execute(
                "SELECT * FROM academic_events "
                "WHERE deleted_at IS NULL AND status<>'cancelled' "
                "AND substr(starts_at,1,10)<=? "
                "AND (ends_at IS NULL OR substr(ends_at,1,10)>=?) "
                "ORDER BY starts_at,id",
                (ends_on, starts_on),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                details = c.execute(
                    "SELECT details_json FROM month_plan_import_items "
                    "WHERE entity_type='academic_event' AND entity_id=? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (item["id"],),
                ).fetchone()
                try:
                    item["import_details"] = (
                        {} if details is None else json.loads(str(details[0] or "{}"))
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    item["import_details"] = {}
                result.append(item)
            return tuple(result)
        finally:
            c.close()

    def list_routines(self):
        c = self._connect(writable=False)
        try:
            return tuple(
                dict(row)
                for row in c.execute(
                    "SELECT * FROM routine_templates WHERE status='active' "
                    "ORDER BY title,id"
                ).fetchall()
            )
        finally:
            c.close()

    def list_assessments(self):
        c = self._connect(writable=False)
        try:
            return tuple(
                dict(row)
                for row in c.execute(
                    "SELECT a.*,c.code AS course_code,c.name AS course_name "
                    "FROM assessments a JOIN courses c ON c.id=a.course_id "
                    "WHERE a.deleted_at IS NULL ORDER BY COALESCE(a.due_on,'9999-12-31'),"
                    "c.code,a.title"
                ).fetchall()
            )
        finally:
            c.close()

    def list_study_items(self, plan_date):
        c = self._connect(writable=False)
        try:
            return tuple(
                dict(row)
                for row in c.execute(
                    "SELECT i.*,c.code AS course_code,c.name AS course_name "
                    "FROM study_plan_items i "
                    "LEFT JOIN courses c ON c.id=i.course_id "
                    "WHERE i.plan_date=? AND i.status NOT IN ('completed','cancelled') "
                    "ORDER BY i.ordinal,i.id",
                    (plan_date,),
                ).fetchall()
            )
        finally:
            c.close()

    def create_or_replace_imported_event(self, row):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                existing = c.execute(
                    "SELECT source_entity_type,source_entity_id FROM academic_events "
                    "WHERE id=?",
                    (row["id"],),
                ).fetchone()
                if existing is not None and str(existing["source_entity_type"] or "") not in {
                    "", "month_plan"
                }:
                    raise OperationalCalendarRepositoryError(
                        "A calendar event has a different authority source."
                    )
                c.execute(
                    "INSERT INTO academic_events "
                    "(id,semester_id,course_id,event_kind,title,starts_at,ends_at,"
                    "all_day,recurrence_rule,reference_type,reference_id,status,"
                    "source_entity_type,source_entity_id,created_at,updated_at,deleted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "semester_id=excluded.semester_id,course_id=excluded.course_id,"
                    "event_kind=excluded.event_kind,title=excluded.title,"
                    "starts_at=excluded.starts_at,ends_at=excluded.ends_at,"
                    "all_day=excluded.all_day,recurrence_rule=excluded.recurrence_rule,"
                    "reference_type=excluded.reference_type,reference_id=excluded.reference_id,"
                    "status=excluded.status,source_entity_type=excluded.source_entity_type,"
                    "source_entity_id=excluded.source_entity_id,updated_at=excluded.updated_at",
                    (
                        row["id"], row.get("semester_id"), row.get("course_id"),
                        row["event_kind"], row["title"], row["starts_at"],
                        row.get("ends_at"), int(bool(row.get("all_day"))),
                        row.get("recurrence_rule"), row.get("reference_type"),
                        row.get("reference_id"), row.get("status","scheduled"),
                        row.get("source_entity_type","month_plan"),
                        row.get("source_entity_id"), row["created_at"], row["updated_at"],
                    ),
                )
        finally:
            c.close()
        return row

    def create_or_replace_routine(self, row):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                existing = c.execute(
                    "SELECT manual_revision FROM routine_templates WHERE id=?", (row["id"],)
                ).fetchone()
                if existing is not None and int(existing["manual_revision"]) > 0:
                    raise OperationalCalendarRepositoryError(
                        "An imported routine has manual edits and requires reconciliation."
                    )
                c.execute(
                    "INSERT INTO routine_templates "
                    "(id,source_import_id,external_id,title,category,priority,"
                    "recurrence_rule,active_from,active_to,start_time,end_time,"
                    "duration_minutes,preferred_window,preferred_location,"
                    "condition_text,excluded_dates_json,additional_dates_json,status,"
                    "manual_revision,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',0,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "source_import_id=excluded.source_import_id,"
                    "external_id=excluded.external_id,title=excluded.title,"
                    "category=excluded.category,priority=excluded.priority,"
                    "recurrence_rule=excluded.recurrence_rule,"
                    "active_from=excluded.active_from,active_to=excluded.active_to,"
                    "start_time=excluded.start_time,end_time=excluded.end_time,"
                    "duration_minutes=excluded.duration_minutes,"
                    "preferred_window=excluded.preferred_window,"
                    "preferred_location=excluded.preferred_location,"
                    "condition_text=excluded.condition_text,"
                    "excluded_dates_json=excluded.excluded_dates_json,"
                    "additional_dates_json=excluded.additional_dates_json,"
                    "updated_at=excluded.updated_at",
                    (
                        row["id"], row.get("source_import_id"), row.get("external_id"),
                        row["title"], row.get("category","routine"), row.get("priority","P1"),
                        row["recurrence_rule"], row.get("active_from"), row.get("active_to"),
                        row.get("start_time"), row.get("end_time"),
                        row.get("duration_minutes"), row.get("preferred_window"),
                        row.get("preferred_location"), row.get("condition_text",""),
                        json.dumps(row.get("excluded_dates",[]), separators=(",",":")),
                        json.dumps(row.get("additional_dates",[]), separators=(",",":")),
                        row["created_at"], row["updated_at"],
                    ),
                )
        finally:
            c.close()
        return row

    def schedule_assessment(
        self,
        assessment_id,
        *,
        due_on,
        due_time,
        venue_note,
        event_row,
    ):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                assessment = c.execute(
                    "SELECT * FROM assessments WHERE id=? AND deleted_at IS NULL",
                    (assessment_id,),
                ).fetchone()
                if assessment is None:
                    raise OperationalCalendarRepositoryNotFoundError(
                        "Assessment was not found."
                    )
                description = str(assessment["description"] or "")
                if venue_note:
                    description = (
                        description.rstrip()
                        + ("\n" if description.strip() else "")
                        + "Venue: " + venue_note.strip()
                    )
                c.execute(
                    "UPDATE assessments SET due_on=?,due_time=?,description=?,updated_at=? "
                    "WHERE id=?",
                    (due_on, due_time, description, event_row["updated_at"], assessment_id),
                )
                c.execute(
                    "INSERT INTO academic_events "
                    "(id,semester_id,course_id,event_kind,title,starts_at,ends_at,"
                    "all_day,recurrence_rule,reference_type,reference_id,status,"
                    "source_entity_type,source_entity_id,created_at,updated_at,deleted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "course_id=excluded.course_id,title=excluded.title,"
                    "starts_at=excluded.starts_at,ends_at=excluded.ends_at,"
                    "reference_type=excluded.reference_type,reference_id=excluded.reference_id,"
                    "status=excluded.status,updated_at=excluded.updated_at,deleted_at=NULL",
                    (
                        event_row["id"], event_row.get("semester_id"),
                        assessment["course_id"], "assessment",
                        str(assessment["title"]), event_row["starts_at"],
                        event_row.get("ends_at"), 0, None, "assessment",
                        assessment_id, "scheduled", "user_confirmed_assessment",
                        assessment_id, event_row["created_at"], event_row["updated_at"],
                    ),
                )
        finally:
            c.close()

    def mark_future_agendas_stale(self, from_date):
        """Delete only future drafts so they can be explicitly regenerated."""
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                c.execute(
                    "DELETE FROM daily_agendas WHERE agenda_date>=? AND status='draft'",
                    (from_date,),
                )
        finally:
            c.close()
