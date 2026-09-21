"""SQLite persistence for Phase 7.5.13 daily agendas, reviews, and rollover events."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class DailyAgendaRepositoryError(RuntimeError):
    """Daily agenda persistence is unavailable or inconsistent."""


class DailyAgendaRepositoryNotFoundError(DailyAgendaRepositoryError):
    """The requested agenda or agenda item does not exist."""


class DailyAgendaRepositoryConflictError(DailyAgendaRepositoryError):
    """The requested agenda transition conflicts with current state."""


def _open(path: Path, *, writable: bool) -> sqlite3.Connection:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise DailyAgendaRepositoryError("Operational planner storage is unavailable.")
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
        raise DailyAgendaRepositoryError("Operational planner storage is unavailable.") from error


class SQLiteDailyAgendaRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _connect(self, *, writable: bool):
        c = _open(self.database_path, writable=writable)
        tables = {str(r[0]) for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        required = {"daily_agendas", "daily_agenda_items", "task_rollover_events", "daily_reviews"}
        if required - tables:
            c.close()
            raise DailyAgendaRepositoryError("Operational planner migration is not applied.")
        return c

    def get_agenda(self, agenda_date):
        c = self._connect(writable=False)
        try:
            row = c.execute(
                "SELECT * FROM daily_agendas WHERE agenda_date=?", (agenda_date,)
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["items"] = tuple(
                dict(item)
                for item in c.execute(
                    "SELECT * FROM daily_agenda_items WHERE agenda_id=? ORDER BY ordinal,id",
                    (row["id"],),
                ).fetchall()
            )
            review = c.execute(
                "SELECT * FROM daily_reviews WHERE agenda_id=?", (row["id"],)
            ).fetchone()
            result["review"] = None if review is None else dict(review)
            return result
        finally:
            c.close()

    def create_or_replace_draft(self, agenda_row, items):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                existing = c.execute(
                    "SELECT id,status FROM daily_agendas WHERE agenda_date=?",
                    (agenda_row["agenda_date"],),
                ).fetchone()
                if existing is not None and str(existing["status"]) not in {"draft"}:
                    raise DailyAgendaRepositoryConflictError(
                        "Only a draft agenda can be regenerated."
                    )
                if existing is None:
                    c.execute(
                        "INSERT INTO daily_agendas "
                        "(id,agenda_date,day_mode,status,generated_at,approved_at,"
                        "closed_at,created_at,updated_at) VALUES (?,?,?,'draft',?,NULL,NULL,?,?)",
                        (
                            agenda_row["id"], agenda_row["agenda_date"],
                            agenda_row["day_mode"], agenda_row["generated_at"],
                            agenda_row["created_at"], agenda_row["updated_at"],
                        ),
                    )
                    agenda_id = agenda_row["id"]
                else:
                    agenda_id = str(existing["id"])
                    c.execute(
                        "UPDATE daily_agendas SET day_mode=?,generated_at=?,updated_at=? "
                        "WHERE id=?",
                        (
                            agenda_row["day_mode"], agenda_row["generated_at"],
                            agenda_row["updated_at"], agenda_id,
                        ),
                    )
                    c.execute("DELETE FROM daily_agenda_items WHERE agenda_id=?", (agenda_id,))
                for index, item in enumerate(items, start=1):
                    c.execute(
                        "INSERT INTO daily_agenda_items "
                        "(id,agenda_id,ordinal,item_kind,source_type,source_id,title,"
                        "priority,starts_at,ends_at,planned_minutes,actual_minutes,"
                        "status,reason,created_at,updated_at,completed_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            item["id"], agenda_id, index, item["item_kind"],
                            item.get("source_type",""), item.get("source_id"),
                            item["title"], item.get("priority"), item.get("starts_at"),
                            item.get("ends_at"), item.get("planned_minutes"),
                            item.get("actual_minutes"), item.get("status","planned"),
                            item.get("reason",""), item["created_at"], item["updated_at"],
                            item.get("completed_at"),
                        ),
                    )
        finally:
            c.close()
        return self.get_agenda(agenda_row["agenda_date"])

    def approve_agenda(self, agenda_date, *, approved_at, updated_at):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                cur = c.execute(
                    "UPDATE daily_agendas SET status='approved',approved_at=?,updated_at=? "
                    "WHERE agenda_date=? AND status='draft'",
                    (approved_at, updated_at, agenda_date),
                )
                if cur.rowcount != 1:
                    raise DailyAgendaRepositoryConflictError(
                        "Only a draft agenda can be approved."
                    )
        finally:
            c.close()
        return self.get_agenda(agenda_date)

    def update_item_status(
        self, agenda_date, item_id, *, status, actual_minutes, completed_at, updated_at
    ):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                agenda = c.execute(
                    "SELECT id,status FROM daily_agendas WHERE agenda_date=?", (agenda_date,)
                ).fetchone()
                if agenda is None:
                    raise DailyAgendaRepositoryNotFoundError("Daily agenda was not found.")
                if str(agenda["status"]) == "closed":
                    raise DailyAgendaRepositoryConflictError("Closed agendas cannot change.")
                item = c.execute(
                    "SELECT source_type,source_id FROM daily_agenda_items "
                    "WHERE id=? AND agenda_id=?",
                    (item_id, agenda["id"]),
                ).fetchone()
                if item is None:
                    raise DailyAgendaRepositoryNotFoundError("Agenda item was not found.")
                c.execute(
                    "UPDATE daily_agenda_items SET status=?,actual_minutes=?,"
                    "completed_at=?,updated_at=? WHERE id=? AND agenda_id=?",
                    (
                        status, actual_minutes, completed_at, updated_at,
                        item_id, agenda["id"],
                    ),
                )
                if (
                    status == "completed"
                    and str(item["source_type"] or "") == "planner_task"
                    and item["source_id"]
                ):
                    c.execute(
                        "UPDATE planner_tasks SET status='completed',completed_at=?,"
                        "updated_at=? WHERE id=? AND status<>'archived'",
                        (completed_at or updated_at, updated_at, item["source_id"]),
                    )
        finally:
            c.close()
        return self.get_agenda(agenda_date)

    def close_agenda(
        self,
        agenda_date,
        *,
        review: dict,
        rollover_rows: tuple[dict, ...],
        closed_at: str,
        updated_at: str,
    ):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                agenda = c.execute(
                    "SELECT id,status FROM daily_agendas WHERE agenda_date=?", (agenda_date,)
                ).fetchone()
                if agenda is None:
                    raise DailyAgendaRepositoryNotFoundError("Daily agenda was not found.")
                if str(agenda["status"]) == "closed":
                    raise DailyAgendaRepositoryConflictError("Daily agenda is already closed.")
                c.execute(
                    "INSERT INTO daily_reviews "
                    "(agenda_id,learned,biggest_confusion,coding_completed,"
                    "coding_independent,data_science_ai_assistance_level,energy_1_to_5,"
                    "sleep_target,tomorrow_first_task,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(agenda_id) DO UPDATE SET "
                    "learned=excluded.learned,biggest_confusion=excluded.biggest_confusion,"
                    "coding_completed=excluded.coding_completed,"
                    "coding_independent=excluded.coding_independent,"
                    "data_science_ai_assistance_level=excluded.data_science_ai_assistance_level,"
                    "energy_1_to_5=excluded.energy_1_to_5,"
                    "sleep_target=excluded.sleep_target,"
                    "tomorrow_first_task=excluded.tomorrow_first_task,"
                    "updated_at=excluded.updated_at",
                    (
                        agenda["id"], review.get("learned",""),
                        review.get("biggest_confusion",""),
                        int(bool(review.get("coding_completed"))),
                        int(bool(review.get("coding_independent"))),
                        review.get("data_science_ai_assistance_level"),
                        review.get("energy_1_to_5"), review.get("sleep_target",""),
                        review.get("tomorrow_first_task",""),
                        review["created_at"], review["updated_at"],
                    ),
                )
                for row in rollover_rows:
                    c.execute(
                        "INSERT INTO task_rollover_events "
                        "(id,task_id,from_date,to_date,decision,reason,created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (
                            row["id"], row["task_id"], row["from_date"],
                            row.get("to_date"), row["decision"], row.get("reason",""),
                            row["created_at"],
                        ),
                    )
                c.execute(
                    "UPDATE daily_agendas SET status='closed',closed_at=?,updated_at=? "
                    "WHERE id=?",
                    (closed_at, updated_at, agenda["id"]),
                )
        finally:
            c.close()
        return self.get_agenda(agenda_date)

    def rollover_for_date(self, agenda_date):
        c = self._connect(writable=False)
        try:
            return tuple(
                dict(row)
                for row in c.execute(
                    "SELECT * FROM task_rollover_events WHERE from_date=? "
                    "ORDER BY created_at,id",
                    (agenda_date,),
                ).fetchall()
            )
        finally:
            c.close()
