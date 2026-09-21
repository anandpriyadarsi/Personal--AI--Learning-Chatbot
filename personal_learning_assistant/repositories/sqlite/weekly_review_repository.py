"""SQLite persistence for Phase 7.5.13 weekly operational reviews."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class WeeklyReviewRepositoryError(RuntimeError):
    """Weekly review persistence is unavailable."""


class WeeklyReviewRepositoryConflictError(WeeklyReviewRepositoryError):
    """A closed weekly review cannot be mutated."""


def _open(path: Path, *, writable: bool):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise WeeklyReviewRepositoryError("Operational planner storage is unavailable.")
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


class SQLiteWeeklyReviewRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _connect(self, *, writable: bool):
        c = _open(self.database_path, writable=writable)
        table = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='weekly_reviews'"
        ).fetchone()
        if table is None:
            c.close()
            raise WeeklyReviewRepositoryError("Operational planner migration is not applied.")
        return c

    def get_review(self, week_start, week_end):
        c = self._connect(writable=False)
        try:
            row = c.execute(
                "SELECT * FROM weekly_reviews WHERE week_start=? AND week_end=?",
                (week_start, week_end),
            ).fetchone()
            return None if row is None else dict(row)
        finally:
            c.close()

    def save_review(self, row):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                existing = c.execute(
                    "SELECT closed_at FROM weekly_reviews WHERE week_start=? AND week_end=?",
                    (row["week_start"], row["week_end"]),
                ).fetchone()
                if existing is not None and existing["closed_at"] is not None:
                    raise WeeklyReviewRepositoryConflictError(
                        "Closed weekly reviews cannot be changed."
                    )
                c.execute(
                    "INSERT INTO weekly_reviews "
                    "(id,week_start,week_end,planned_items,completed_items,"
                    "planned_focus_minutes,actual_focus_minutes,carry_forward_count,"
                    "missed_deadline_count,what_worked,what_failed,remove_next_week,"
                    "next_priority_1,next_priority_2,next_priority_3,"
                    "created_at,updated_at,closed_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(week_start,week_end) DO UPDATE SET "
                    "planned_items=excluded.planned_items,"
                    "completed_items=excluded.completed_items,"
                    "planned_focus_minutes=excluded.planned_focus_minutes,"
                    "actual_focus_minutes=excluded.actual_focus_minutes,"
                    "carry_forward_count=excluded.carry_forward_count,"
                    "missed_deadline_count=excluded.missed_deadline_count,"
                    "what_worked=excluded.what_worked,"
                    "what_failed=excluded.what_failed,"
                    "remove_next_week=excluded.remove_next_week,"
                    "next_priority_1=excluded.next_priority_1,"
                    "next_priority_2=excluded.next_priority_2,"
                    "next_priority_3=excluded.next_priority_3,"
                    "updated_at=excluded.updated_at,"
                    "closed_at=excluded.closed_at",
                    (
                        row["id"], row["week_start"], row["week_end"],
                        row["planned_items"], row["completed_items"],
                        row["planned_focus_minutes"], row["actual_focus_minutes"],
                        row["carry_forward_count"], row["missed_deadline_count"],
                        row.get("what_worked",""), row.get("what_failed",""),
                        row.get("remove_next_week",""), row.get("next_priority_1",""),
                        row.get("next_priority_2",""), row.get("next_priority_3",""),
                        row["created_at"], row["updated_at"], row.get("closed_at"),
                    ),
                )
        finally:
            c.close()
        return self.get_review(row["week_start"], row["week_end"])

    def aggregate_period(self, week_start, week_end):
        c = self._connect(writable=False)
        try:
            agenda_rows = c.execute(
                "SELECT id FROM daily_agendas WHERE agenda_date BETWEEN ? AND ?",
                (week_start, week_end),
            ).fetchall()
            agenda_ids = [str(row["id"]) for row in agenda_rows]
            if not agenda_ids:
                return {
                    "planned_items": 0,
                    "completed_items": 0,
                    "planned_focus_minutes": 0,
                    "actual_focus_minutes": 0,
                    "carry_forward_count": 0,
                    "missed_deadline_count": 0,
                }
            placeholders = ",".join("?" for _ in agenda_ids)
            stats = c.execute(
                "SELECT COUNT(*) AS planned_items,"
                "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_items,"
                "COALESCE(SUM(CASE WHEN item_kind IN ('task','study') THEN planned_minutes ELSE 0 END),0) AS planned_focus_minutes,"
                "COALESCE(SUM(CASE WHEN item_kind IN ('task','study') THEN actual_minutes ELSE 0 END),0) AS actual_focus_minutes "
                "FROM daily_agenda_items WHERE agenda_id IN ({})".format(placeholders),
                tuple(agenda_ids),
            ).fetchone()
            carry = c.execute(
                "SELECT COUNT(*) FROM task_rollover_events "
                "WHERE from_date BETWEEN ? AND ? AND decision='carry'",
                (week_start, week_end),
            ).fetchone()[0]
            missed = c.execute(
                "SELECT COUNT(*) FROM planner_tasks "
                "WHERE due_on BETWEEN ? AND ? AND status NOT IN ('completed','archived') "
                "AND due_on < date('now')",
                (week_start, week_end),
            ).fetchone()[0]
            return {
                "planned_items": int(stats["planned_items"] or 0),
                "completed_items": int(stats["completed_items"] or 0),
                "planned_focus_minutes": int(stats["planned_focus_minutes"] or 0),
                "actual_focus_minutes": int(stats["actual_focus_minutes"] or 0),
                "carry_forward_count": int(carry or 0),
                "missed_deadline_count": int(missed or 0),
            }
        finally:
            c.close()
