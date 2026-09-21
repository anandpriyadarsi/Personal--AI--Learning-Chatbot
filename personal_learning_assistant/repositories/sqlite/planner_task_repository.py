"""SQLite task persistence for the Phase 7.5.13 Operational Planner."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class PlannerTaskRepositoryError(RuntimeError):
    """Task persistence is unavailable or inconsistent."""


class PlannerTaskRepositoryNotFoundError(PlannerTaskRepositoryError):
    """The requested planner task does not exist."""


def _open(path: Path, *, writable: bool) -> sqlite3.Connection:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise PlannerTaskRepositoryError("Operational planner storage is unavailable.")
    uri = quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    try:
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
    except sqlite3.Error as error:
        raise PlannerTaskRepositoryError("Operational planner storage is unavailable.") from error


class SQLitePlannerTaskRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _connect(self, *, writable: bool):
        c = _open(self.database_path, writable=writable)
        tables = {str(r[0]) for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "planner_tasks" not in tables:
            c.close()
            raise PlannerTaskRepositoryError("Operational planner migration is not applied.")
        return c

    def list_tasks(
        self,
        *,
        statuses=None,
        priority=None,
        course_id=None,
        due_from=None,
        due_to=None,
    ):
        sql = "SELECT * FROM planner_tasks WHERE 1=1"
        params = []
        if statuses:
            values = tuple(statuses)
            sql += " AND status IN ({})".format(",".join("?" for _ in values))
            params.extend(values)
        if priority:
            sql += " AND priority=?"
            params.append(priority)
        if course_id:
            sql += " AND course_id=?"
            params.append(course_id)
        if due_from:
            sql += " AND due_on>=?"
            params.append(due_from)
        if due_to:
            sql += " AND due_on<=?"
            params.append(due_to)
        sql += (
            " ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,"
            " COALESCE(due_on,'9999-12-31'), created_at, id"
        )
        c = self._connect(writable=False)
        try:
            return tuple(dict(r) for r in c.execute(sql, tuple(params)).fetchall())
        finally:
            c.close()

    def get_task(self, task_id):
        c = self._connect(writable=False)
        try:
            row = c.execute("SELECT * FROM planner_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise PlannerTaskRepositoryNotFoundError("Planner task was not found.")
            return dict(row)
        finally:
            c.close()

    def create_task(self, row):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                c.execute(
                    "INSERT INTO planner_tasks "
                    "(id,source_import_id,external_id,title,description,priority,"
                    "course_id,topic_id,assessment_id,estimated_minutes,due_on,"
                    "preferred_day,preferred_window,rollover_policy,status,"
                    "manual_revision,created_at,updated_at,completed_at,archived_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["id"], row.get("source_import_id"), row.get("external_id"),
                        row["title"], row.get("description", ""), row["priority"],
                        row.get("course_id"), row.get("topic_id"), row.get("assessment_id"),
                        row.get("estimated_minutes"), row.get("due_on"),
                        row.get("preferred_day"), row.get("preferred_window"),
                        row.get("rollover_policy", ""), row.get("status", "backlog"),
                        int(row.get("manual_revision", 0)), row["created_at"], row["updated_at"],
                        row.get("completed_at"), row.get("archived_at"),
                    ),
                )
        except sqlite3.Error as error:
            raise PlannerTaskRepositoryError("The task could not be saved.") from error
        finally:
            c.close()
        return self.get_task(row["id"])

    def update_task(self, task_id, fields, *, mark_manual=True):
        allowed = {
            "title", "description", "priority", "course_id", "topic_id",
            "assessment_id", "estimated_minutes", "due_on", "preferred_day",
            "preferred_window", "rollover_policy", "status", "completed_at",
            "archived_at", "updated_at",
        }
        values = {k: v for k, v in fields.items() if k in allowed}
        if not values:
            return self.get_task(task_id)
        assignments = ["{}=?".format(k) for k in values]
        params = list(values.values())
        if mark_manual:
            assignments.append("manual_revision=manual_revision+1")
        params.append(task_id)
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                cur = c.execute(
                    "UPDATE planner_tasks SET {} WHERE id=?".format(", ".join(assignments)),
                    tuple(params),
                )
                if cur.rowcount != 1:
                    raise PlannerTaskRepositoryNotFoundError("Planner task was not found.")
        finally:
            c.close()
        return self.get_task(task_id)

    def create_or_replace_imported_task(self, row):
        """Upsert a source-managed task only when the existing row was not manually revised."""
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                existing = c.execute(
                    "SELECT * FROM planner_tasks WHERE id=?", (row["id"],)
                ).fetchone()
                if existing is not None and int(existing["manual_revision"]) > 0:
                    raise PlannerTaskRepositoryError(
                        "An imported task has manual edits and requires reconciliation."
                    )
                if existing is None:
                    c.execute(
                        "INSERT INTO planner_tasks "
                        "(id,source_import_id,external_id,title,description,priority,"
                        "course_id,topic_id,assessment_id,estimated_minutes,due_on,"
                        "preferred_day,preferred_window,rollover_policy,status,"
                        "manual_revision,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                        (
                            row["id"], row.get("source_import_id"), row.get("external_id"),
                            row["title"], row.get("description",""), row["priority"],
                            row.get("course_id"), row.get("topic_id"), row.get("assessment_id"),
                            row.get("estimated_minutes"), row.get("due_on"),
                            row.get("preferred_day"), row.get("preferred_window"),
                            row.get("rollover_policy",""), row.get("status","backlog"),
                            row["created_at"], row["updated_at"],
                        ),
                    )
                else:
                    c.execute(
                        "UPDATE planner_tasks SET source_import_id=?,external_id=?,title=?,"
                        "description=?,priority=?,course_id=?,topic_id=?,assessment_id=?,"
                        "estimated_minutes=?,due_on=?,preferred_day=?,preferred_window=?,"
                        "rollover_policy=?,status=?,updated_at=? WHERE id=?",
                        (
                            row.get("source_import_id"), row.get("external_id"), row["title"],
                            row.get("description",""), row["priority"], row.get("course_id"),
                            row.get("topic_id"), row.get("assessment_id"),
                            row.get("estimated_minutes"), row.get("due_on"),
                            row.get("preferred_day"), row.get("preferred_window"),
                            row.get("rollover_policy",""), row.get("status","backlog"),
                            row["updated_at"], row["id"],
                        ),
                    )
        finally:
            c.close()
        return self.get_task(row["id"])
