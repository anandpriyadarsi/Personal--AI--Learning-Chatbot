"""SQLite persistence for Phase 7.5.13 month-plan imports and provenance."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class MonthPlanImportRepositoryError(RuntimeError):
    """Month-plan import state could not be read or written safely."""


def _open(path: Path, *, writable: bool) -> sqlite3.Connection:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise MonthPlanImportRepositoryError("Operational planner storage is unavailable.")
    uri = quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    try:
        connection = sqlite3.connect(
            "file:{}?mode={}".format(uri, "rw" if writable else "ro"),
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except sqlite3.Error as error:
        raise MonthPlanImportRepositoryError(
            "Operational planner storage is unavailable."
        ) from error


def _row(row):
    return None if row is None else dict(row)


class SQLiteMonthPlanImportRepository:
    REQUIRED = {"month_plan_imports", "month_plan_import_items", "courses"}

    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _connect(self, *, writable: bool):
        connection = _open(self.database_path, writable=writable)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if self.REQUIRED - tables:
            connection.close()
            raise MonthPlanImportRepositoryError(
                "Operational planner migration is not applied."
            )
        return connection

    def course_by_code(self, code: str):
        connection = self._connect(writable=False)
        try:
            row = connection.execute(
                "SELECT id, code, name FROM courses "
                "WHERE code = ? COLLATE NOCASE AND deleted_at IS NULL",
                (str(code or "").strip(),),
            ).fetchone()
            return _row(row)
        finally:
            connection.close()

    def find_by_hash(self, source_sha256: str):
        connection = self._connect(writable=False)
        try:
            return _row(
                connection.execute(
                    "SELECT * FROM month_plan_imports WHERE source_sha256=?",
                    (source_sha256,),
                ).fetchone()
            )
        finally:
            connection.close()

    def active_import(self, plan_id: str):
        connection = self._connect(writable=False)
        try:
            return _row(
                connection.execute(
                    "SELECT * FROM month_plan_imports "
                    "WHERE plan_id=? AND status='active'",
                    (plan_id,),
                ).fetchone()
            )
        finally:
            connection.close()

    def list_import_items(self, import_id: str):
        connection = self._connect(writable=False)
        try:
            return tuple(
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM month_plan_import_items "
                    "WHERE import_id=? ORDER BY entity_type, external_id",
                    (import_id,),
                ).fetchall()
            )
        finally:
            connection.close()

    def event_import_details(self, entity_ids):
        ids = tuple(str(item) for item in entity_ids if str(item))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        connection = self._connect(writable=False)
        try:
            rows = connection.execute(
                "SELECT entity_id, details_json FROM month_plan_import_items "
                "WHERE entity_type='academic_event' "
                "AND entity_id IN ({})".format(placeholders),
                ids,
            ).fetchall()
            result = {}
            for row in rows:
                try:
                    result[str(row["entity_id"])] = json.loads(
                        str(row["details_json"] or "{}")
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    result[str(row["entity_id"])] = {}
            return result
        finally:
            connection.close()

    def create_import(
        self,
        *,
        import_row: dict,
        items: tuple[dict, ...],
        supersede_import_id: str | None,
    ):
        connection = self._connect(writable=True)
        try:
            with transaction(connection, immediate=True):
                if supersede_import_id:
                    connection.execute(
                        "UPDATE month_plan_imports "
                        "SET status='superseded', superseded_at=? "
                        "WHERE id=? AND status='active'",
                        (import_row["approved_at"], supersede_import_id),
                    )
                connection.execute(
                    "INSERT INTO month_plan_imports "
                    "(id,plan_id,schema_version,source_filename,source_sha256,"
                    "title,starts_on,ends_on,timezone,status,created_at,"
                    "approved_at,superseded_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,NULL)",
                    (
                        import_row["id"],
                        import_row["plan_id"],
                        import_row["schema_version"],
                        import_row["source_filename"],
                        import_row["source_sha256"],
                        import_row["title"],
                        import_row["starts_on"],
                        import_row["ends_on"],
                        import_row["timezone"],
                        import_row["created_at"],
                        import_row["approved_at"],
                    ),
                )
                for item in items:
                    connection.execute(
                        "INSERT INTO month_plan_import_items "
                        "(id,import_id,external_id,entity_type,entity_id,"
                        "source_hash,entity_snapshot_hash,details_json,"
                        "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            item["id"],
                            import_row["id"],
                            item["external_id"],
                            item["entity_type"],
                            item["entity_id"],
                            item["source_hash"],
                            item.get("entity_snapshot_hash", ""),
                            item.get("details_json", "{}"),
                            item["created_at"],
                            item["updated_at"],
                        ),
                    )
        except sqlite3.Error as error:
            raise MonthPlanImportRepositoryError(
                "The month plan could not be saved atomically."
            ) from error
        finally:
            connection.close()
        return self.active_import(import_row["plan_id"])

    def approve_bundle(self, bundle: dict):
        """Apply one validated month-plan revision atomically across mapped entities."""
        import_row = bundle["import"]
        existing_hash = self.find_by_hash(import_row["source_sha256"])
        if existing_hash is not None:
            return existing_hash
        active = self.active_import(import_row["plan_id"])

        connection = self._connect(writable=True)
        try:
            with transaction(connection, immediate=True):
                if active is not None:
                    # Refuse silent overwrite if any source-managed task/routine was manually revised.
                    conflict_task = connection.execute(
                        "SELECT 1 FROM planner_tasks "
                        "WHERE source_import_id=? AND manual_revision>0 LIMIT 1",
                        (active["id"],),
                    ).fetchone()
                    conflict_routine = connection.execute(
                        "SELECT 1 FROM routine_templates "
                        "WHERE source_import_id=? AND manual_revision>0 LIMIT 1",
                        (active["id"],),
                    ).fetchone()
                    if conflict_task is not None or conflict_routine is not None:
                        raise MonthPlanImportRepositoryError(
                            "Import conflict: source-managed planner data has manual edits."
                        )
                    connection.execute(
                        "UPDATE month_plan_imports SET status='superseded',superseded_at=? "
                        "WHERE id=? AND status='active'",
                        (import_row["approved_at"], active["id"]),
                    )

                connection.execute(
                    "INSERT INTO month_plan_imports "
                    "(id,plan_id,schema_version,source_filename,source_sha256,title,"
                    "starts_on,ends_on,timezone,status,created_at,approved_at,superseded_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,NULL)",
                    (
                        import_row["id"], import_row["plan_id"], import_row["schema_version"],
                        import_row["source_filename"], import_row["source_sha256"],
                        import_row["title"], import_row["starts_on"], import_row["ends_on"],
                        import_row["timezone"], import_row["created_at"], import_row["approved_at"],
                    ),
                )

                # Assessments: exact course + title match wins; otherwise create deterministic row.
                for item in bundle.get("assessments", ()):
                    existing = connection.execute(
                        "SELECT id FROM assessments WHERE course_id=? "
                        "AND title=? COLLATE NOCASE AND deleted_at IS NULL",
                        (item.get("course_id"), item["title"]),
                    ).fetchone()
                    entity_id = str(existing["id"]) if existing is not None else item["id"]
                    if existing is None:
                        connection.execute(
                            "INSERT INTO assessments "
                            "(id,course_id,assessment_type,title,due_on,due_time,status,"
                            "weight_bps,max_points_milli,earned_points_milli,description,"
                            "created_at,updated_at,deleted_at) "
                            "VALUES (?,?,?,?,?,?,'pending',NULL,NULL,NULL,?,?,?,NULL)",
                            (
                                entity_id, item["course_id"], item["assessment_type"],
                                item["title"], item.get("due_on"), item.get("due_time"),
                                item.get("description",""), item["created_at"], item["updated_at"],
                            ),
                        )
                    item["_entity_id"] = entity_id

                for item in bundle.get("events", ()):
                    course_id = item.get("course_id")
                    date_text = item["first_date"] if item.get("first_date") else item["date"]
                    start_time = item.get("start_time")
                    end_time = item.get("end_time")
                    starts_at = date_text + (("T" + start_time + ":00") if start_time else "T00:00:00")
                    if item.get("end_date"):
                        ends_at = item["end_date"] + "T23:59:59"
                    elif end_time:
                        ends_at = date_text + "T" + end_time + ":00"
                    else:
                        ends_at = None
                    connection.execute(
                        "INSERT INTO academic_events "
                        "(id,semester_id,course_id,event_kind,title,starts_at,ends_at,all_day,"
                        "recurrence_rule,reference_type,reference_id,status,source_entity_type,"
                        "source_entity_id,created_at,updated_at,deleted_at) "
                        "VALUES (?,NULL,?,?,?,?,?,?,?,?,?,'scheduled','month_plan',?,?,?,NULL) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "course_id=excluded.course_id,event_kind=excluded.event_kind,"
                        "title=excluded.title,starts_at=excluded.starts_at,ends_at=excluded.ends_at,"
                        "all_day=excluded.all_day,recurrence_rule=excluded.recurrence_rule,"
                        "reference_type=excluded.reference_type,reference_id=excluded.reference_id,"
                        "source_entity_type='month_plan',source_entity_id=excluded.source_entity_id,"
                        "updated_at=excluded.updated_at,deleted_at=NULL",
                        (
                            item["id"], course_id, item.get("event_kind","event"), item["title"],
                            starts_at, ends_at, int(bool(item.get("all_day"))),
                            item.get("recurrence_rule"), None, None,
                            item["external_id"], item["created_at"], item["updated_at"],
                        ),
                    )

                for item in bundle.get("routines", ()):
                    connection.execute(
                        "INSERT INTO routine_templates "
                        "(id,source_import_id,external_id,title,category,priority,recurrence_rule,"
                        "active_from,active_to,start_time,end_time,duration_minutes,preferred_window,"
                        "preferred_location,condition_text,excluded_dates_json,additional_dates_json,"
                        "status,manual_revision,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',0,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "source_import_id=excluded.source_import_id,"
                        "external_id=excluded.external_id,title=excluded.title,"
                        "category=excluded.category,priority=excluded.priority,"
                        "recurrence_rule=excluded.recurrence_rule,active_from=excluded.active_from,"
                        "active_to=excluded.active_to,start_time=excluded.start_time,"
                        "end_time=excluded.end_time,duration_minutes=excluded.duration_minutes,"
                        "preferred_window=excluded.preferred_window,"
                        "preferred_location=excluded.preferred_location,"
                        "condition_text=excluded.condition_text,"
                        "excluded_dates_json=excluded.excluded_dates_json,"
                        "additional_dates_json=excluded.additional_dates_json,"
                        "status='active',updated_at=excluded.updated_at",
                        (
                            item["id"], import_row["id"], item["external_id"], item["title"],
                            "routine", item.get("priority","P1"), item["recurrence_rule"],
                            item.get("active_from"), item.get("active_to"), item.get("start_time"),
                            item.get("end_time"), item.get("duration_minutes"),
                            item.get("preferred_window"), item.get("preferred_location"),
                            item.get("condition_text",""),
                            json.dumps(list(item.get("excluded_dates") or ()), separators=(",",":")),
                            json.dumps(list(item.get("additional_dates") or ()), separators=(",",":")),
                            item["created_at"], item["updated_at"],
                        ),
                    )

                for item in bundle.get("tasks", ()):
                    connection.execute(
                        "INSERT INTO planner_tasks "
                        "(id,source_import_id,external_id,title,description,priority,course_id,"
                        "topic_id,assessment_id,estimated_minutes,due_on,preferred_day,"
                        "preferred_window,rollover_policy,status,manual_revision,created_at,updated_at,"
                        "completed_at,archived_at) "
                        "VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,?,?,0,?,?,NULL,NULL) "
                        "ON CONFLICT(id) DO UPDATE SET "
                        "source_import_id=excluded.source_import_id,"
                        "external_id=excluded.external_id,title=excluded.title,"
                        "description=excluded.description,priority=excluded.priority,"
                        "course_id=excluded.course_id,estimated_minutes=excluded.estimated_minutes,"
                        "due_on=excluded.due_on,preferred_day=excluded.preferred_day,"
                        "preferred_window=excluded.preferred_window,"
                        "rollover_policy=excluded.rollover_policy,status=excluded.status,"
                        "updated_at=excluded.updated_at",
                        (
                            item["id"], import_row["id"], item["external_id"], item["title"],
                            item.get("description",""), item["priority"], item.get("course_id"),
                            item.get("estimated_minutes"), item.get("due_on"),
                            item.get("preferred_day"), item.get("preferred_window"),
                            item.get("rollover_policy",""), item.get("status","backlog"),
                            item["created_at"], item["updated_at"],
                        ),
                    )

                assessment_ids = {
                    item["external_id"]: item.get("_entity_id", item["id"])
                    for item in bundle.get("assessments", ())
                }
                for ledger in bundle.get("ledger", ()):
                    entity_id = assessment_ids.get(ledger["external_id"], ledger["entity_id"])
                    connection.execute(
                        "INSERT INTO month_plan_import_items "
                        "(id,import_id,external_id,entity_type,entity_id,source_hash,"
                        "entity_snapshot_hash,details_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            ledger["id"], import_row["id"], ledger["external_id"],
                            ledger["entity_type"], entity_id, ledger["source_hash"],
                            ledger.get("entity_snapshot_hash",""), ledger.get("details_json","{}"),
                            ledger["created_at"], ledger["updated_at"],
                        ),
                    )
        except sqlite3.Error as error:
            raise MonthPlanImportRepositoryError(
                "The month plan could not be approved atomically."
            ) from error
        finally:
            connection.close()
        return self.active_import(import_row["plan_id"])
