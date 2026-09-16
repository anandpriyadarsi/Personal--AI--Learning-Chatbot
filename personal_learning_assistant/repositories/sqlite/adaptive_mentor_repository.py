"""Read-only evidence adapter for Phase 6.7 Adaptive Mentor."""

from __future__ import annotations

import sqlite3

from personal_learning_assistant.domain.adaptive_mentor_models import (
    MentorPracticeSummary,
)


class AdaptiveMentorRepositoryError(RuntimeError):
    pass


class SQLiteAdaptiveMentorRepository:
    """Read-only evidence queries not already exposed by Phase 6.3/6.6."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def table_names(self):
        return {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }

    def practice_history_available(self) -> bool:
        required = {
            "practice_sessions",
            "practice_items",
            "practice_attempts",
        }
        return required.issubset(self.table_names())

    def practice_summary(self, course_id: str, topic_id: str):
        if not self.practice_history_available():
            return MentorPracticeSummary(
                available=False,
                session_count=0,
                completed_session_count=0,
                deterministic_attempt_count=0,
                correct_attempt_count=0,
                incorrect_attempt_count=0,
                advisory_attempt_count=0,
                latest_attempt_at=None,
            )

        session_row = self.connection.execute(
            "SELECT COUNT(*) AS total,"
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed "
            "FROM practice_sessions WHERE course_id=? AND topic_id=?",
            (course_id, topic_id),
        ).fetchone()

        attempt_row = self.connection.execute(
            "SELECT "
            "SUM(CASE WHEN pa.grading_mode='deterministic' THEN 1 ELSE 0 END) "
            "AS deterministic_count,"
            "SUM(CASE WHEN pa.outcome='correct' THEN 1 ELSE 0 END) AS correct_count,"
            "SUM(CASE WHEN pa.outcome='incorrect' THEN 1 ELSE 0 END) AS incorrect_count,"
            "SUM(CASE WHEN pa.outcome='advisory_ungraded' THEN 1 ELSE 0 END) "
            "AS advisory_count,"
            "MAX(pa.occurred_at) AS latest_attempt_at "
            "FROM practice_attempts pa "
            "JOIN practice_items pi ON pi.id=pa.item_id "
            "JOIN practice_sessions ps ON ps.id=pi.session_id "
            "WHERE ps.course_id=? AND ps.topic_id=?",
            (course_id, topic_id),
        ).fetchone()

        return MentorPracticeSummary(
            available=True,
            session_count=int(session_row["total"] or 0),
            completed_session_count=int(session_row["completed"] or 0),
            deterministic_attempt_count=int(
                attempt_row["deterministic_count"] or 0
            ),
            correct_attempt_count=int(attempt_row["correct_count"] or 0),
            incorrect_attempt_count=int(attempt_row["incorrect_count"] or 0),
            advisory_attempt_count=int(attempt_row["advisory_count"] or 0),
            latest_attempt_at=(
                None
                if attempt_row["latest_attempt_at"] is None
                else str(attempt_row["latest_attempt_at"])
            ),
        )
