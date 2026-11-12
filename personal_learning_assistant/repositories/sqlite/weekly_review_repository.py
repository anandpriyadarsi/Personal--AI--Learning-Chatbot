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
                if row.get('expected_evidence_fingerprint'):
                    from personal_learning_assistant.services.weekly_evidence_service import aggregate_connection, fingerprint
                    current_evidence = aggregate_connection(c,row['week_start'],row['week_end'],as_of=row['evidence_as_of'])
                    if fingerprint(current_evidence) != row['expected_evidence_fingerprint']:
                        raise WeeklyReviewRepositoryConflictError('Evidence changed; reload before saving.')
                columns = {r[1] for r in c.execute('PRAGMA table_info(weekly_reviews)')}
                if row.get('expected_revision') is not None and 'revision' in columns:
                    current = c.execute('SELECT revision FROM weekly_reviews WHERE week_start=? AND week_end=?',
                        (row['week_start'],row['week_end'])).fetchone()
                    try:
                        expected = int(row['expected_revision'])
                    except (ValueError, TypeError):
                        raise WeeklyReviewRepositoryConflictError('Invalid review revision.')
                    if expected != (current[0] if current else 0):
                        raise WeeklyReviewRepositoryConflictError('Review changed; reload before saving.')
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
                        row["planned_focus_minutes"], row["actual_focus_minutes"] if row["actual_focus_minutes"] is not None else 0,
                        row["carry_forward_count"], row["missed_deadline_count"],
                        row.get("what_worked",""), row.get("what_failed",""),
                        row.get("remove_next_week",""), row.get("next_priority_1",""),
                        row.get("next_priority_2",""), row.get("next_priority_3",""),
                        row["created_at"], row["updated_at"], row.get("closed_at"),
                    ),
                )
                columns = {r[1] for r in c.execute('PRAGMA table_info(weekly_reviews)')}
                if 'evidence_json' in columns:
                    c.execute("UPDATE weekly_reviews SET evidence_json=?,evidence_fingerprint=?,evidence_as_of=?,policy_version=?,revision=revision+1 WHERE week_start=? AND week_end=?",
                        (row.get('evidence_json'), row.get('evidence_fingerprint'), row.get('evidence_as_of'), row.get('policy_version'), row['week_start'], row['week_end']))
                elif row.get('closed_at'):
                    raise WeeklyReviewRepositoryError('Apply PAO migration before closing evidence snapshots.')
        finally:
            c.close()
        return self.get_review(row["week_start"], row["week_end"])

    def aggregate_period(self, week_start, week_end, *, as_of=None, course_id='', local_timezone='Asia/Kolkata'):
        from personal_learning_assistant.services.weekly_evidence_service import aggregate_connection
        c = self._connect(writable=False)
        try:
            return aggregate_connection(c, week_start, week_end, as_of=as_of,
                course_id=course_id, local_timezone=local_timezone)
        except sqlite3.Error as error:
            raise WeeklyReviewRepositoryError("Weekly evidence is unavailable.") from error
        finally:
            c.close()
