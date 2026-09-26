"""SQLite persistence for Assessment Studio Phase C timed test sessions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from personal_learning_assistant.repositories.sqlite.connection import transaction


_REQUIRED_TABLES = {
    "courses",
    "assessments",
    "questions",
    "assessment_runtime_specs",
    "assessment_question_specs",
    "question_options",
    "question_topic_mappings",
    "assessment_test_sessions",
    "assessment_test_session_questions",
    "assessment_test_responses",
    "assessment_test_events",
}


class AssessmentRunnerRepositoryError(RuntimeError):
    pass


class AssessmentRunnerRepositorySchemaError(AssessmentRunnerRepositoryError):
    pass


class AssessmentRunnerRepositoryNotFoundError(AssessmentRunnerRepositoryError):
    pass


class AssessmentRunnerRepositoryConflictError(AssessmentRunnerRepositoryError):
    pass


class AssessmentRunnerRepositoryDataError(AssessmentRunnerRepositoryError):
    pass


class SQLiteAssessmentRunnerRepository:
    """Repository for immutable CBT snapshots and mutable in-progress responses."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("explicit sqlite3.Connection required")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self._validate_schema()

    def _validate_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise AssessmentRunnerRepositorySchemaError(
                "Assessment Runner schema is unavailable; missing: {}".format(
                    ", ".join(missing)
                )
            )

    @staticmethod
    def _dict(row):
        return dict(row) if row is not None else None

    def list_runnable_assessments(self, *, limit: int = 100):
        rows = self.connection.execute(
            "SELECT a.id, a.title, a.assessment_type, a.status AS assessment_status, "
            "a.max_points_milli, c.code AS course_code, c.name AS course_name, "
            "r.mode, r.duration_minutes, r.instructions_text, r.origin, "
            "(SELECT COUNT(*) FROM questions q "
            " WHERE q.assessment_id=a.id AND q.deleted_at IS NULL) AS question_count, "
            "(SELECT s.id FROM assessment_test_sessions s "
            " WHERE s.assessment_id=a.id AND s.status='active' "
            " ORDER BY s.started_at DESC LIMIT 1) AS active_session_id, "
            "(SELECT s.expires_at FROM assessment_test_sessions s "
            " WHERE s.assessment_id=a.id AND s.status='active' "
            " ORDER BY s.started_at DESC LIMIT 1) AS active_expires_at, "
            "(SELECT COUNT(*) FROM assessment_test_sessions s "
            " WHERE s.assessment_id=a.id AND s.status IN ('submitted','expired')) "
            " AS completed_session_count "
            "FROM assessments a "
            "JOIN courses c ON c.id=a.course_id "
            "JOIN assessment_runtime_specs r ON r.assessment_id=a.id "
            "WHERE a.deleted_at IS NULL AND c.deleted_at IS NULL "
            "ORDER BY a.created_at DESC, a.title COLLATE NOCASE "
            "LIMIT ?",
            (max(1, min(int(limit), 300)),),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_preflight(self, assessment_id: str):
        row = self.connection.execute(
            "SELECT a.id, a.title, a.assessment_type, a.status AS assessment_status, "
            "a.max_points_milli, a.description, c.code AS course_code, "
            "c.name AS course_name, r.mode, r.duration_minutes, "
            "r.instructions_text, r.origin, r.package_id, r.package_revision, "
            "(SELECT COUNT(*) FROM questions q "
            " WHERE q.assessment_id=a.id AND q.deleted_at IS NULL) AS question_count, "
            "(SELECT s.id FROM assessment_test_sessions s "
            " WHERE s.assessment_id=a.id AND s.status='active' "
            " ORDER BY s.started_at DESC LIMIT 1) AS active_session_id, "
            "(SELECT s.expires_at FROM assessment_test_sessions s "
            " WHERE s.assessment_id=a.id AND s.status='active' "
            " ORDER BY s.started_at DESC LIMIT 1) AS active_expires_at "
            "FROM assessments a "
            "JOIN courses c ON c.id=a.course_id "
            "JOIN assessment_runtime_specs r ON r.assessment_id=a.id "
            "WHERE a.id=? AND a.deleted_at IS NULL AND c.deleted_at IS NULL",
            (str(assessment_id),),
        ).fetchone()
        return self._dict(row)

    def list_sessions(self, *, assessment_id: str | None = None, limit: int = 100):
        where = ""
        params: list[Any] = []
        if assessment_id:
            where = "WHERE s.assessment_id=?"
            params.append(str(assessment_id))
        params.append(max(1, min(int(limit), 300)))
        rows = self.connection.execute(
            "SELECT s.id, s.assessment_id, s.status, s.mode, s.title_snapshot, "
            "s.course_code_snapshot, s.course_name_snapshot, s.duration_seconds, "
            "s.question_count, s.max_marks_milli, s.started_at, s.expires_at, "
            "s.submitted_at, s.submission_reason, s.current_ordinal, s.revision, "
            "(SELECT SUM(r.focus_seconds) FROM assessment_test_responses r "
            " JOIN assessment_test_session_questions q ON q.id=r.session_question_id "
            " WHERE q.session_id=s.id) AS focus_seconds "
            "FROM assessment_test_sessions s {} "
            "ORDER BY s.started_at DESC LIMIT ?".format(where),
            tuple(params),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def _expire_if_due(self, session_id: str, now: str) -> bool:
        row = self.connection.execute(
            "SELECT status, expires_at FROM assessment_test_sessions WHERE id=?",
            (str(session_id),),
        ).fetchone()
        if row is None:
            raise AssessmentRunnerRepositoryNotFoundError("Test session not found.")
        if str(row["status"]) != "active":
            return False
        if str(row["expires_at"]) > str(now):
            return False
        self.connection.execute(
            "UPDATE assessment_test_sessions SET status='expired', submitted_at=expires_at, "
            "submission_reason='timeout', updated_at=?, revision=revision+1 "
            "WHERE id=? AND status='active'",
            (str(now), str(session_id)),
        )
        self.connection.execute(
            "INSERT INTO assessment_test_events "
            "(id, session_id, session_question_id, event_type, details_json, occurred_at) "
            "VALUES (?, ?, NULL, 'auto_submitted_timeout', '{}', ?)",
            (str(uuid.uuid4()), str(session_id), str(now)),
        )
        return True

    def synchronize_timeout(self, session_id: str, *, now: str):
        with transaction(self.connection, immediate=True):
            self._expire_if_due(str(session_id), str(now))
        return self.get_session_header(session_id)

    def _expire_assessment_sessions(self, assessment_id: str, now: str) -> None:
        rows = self.connection.execute(
            "SELECT id FROM assessment_test_sessions "
            "WHERE assessment_id=? AND status='active' AND expires_at<=?",
            (str(assessment_id), str(now)),
        ).fetchall()
        for row in rows:
            self._expire_if_due(str(row["id"]), str(now))

    def _load_assessment_snapshot(self, assessment_id: str):
        header = self.connection.execute(
            "SELECT a.id, a.title, a.max_points_milli, c.code AS course_code, "
            "c.name AS course_name, r.mode, r.duration_minutes, r.instructions_text "
            "FROM assessments a "
            "JOIN courses c ON c.id=a.course_id "
            "JOIN assessment_runtime_specs r ON r.assessment_id=a.id "
            "WHERE a.id=? AND a.deleted_at IS NULL AND c.deleted_at IS NULL",
            (str(assessment_id),),
        ).fetchone()
        if header is None:
            raise AssessmentRunnerRepositoryNotFoundError(
                "Assessment is not available for the timed runner."
            )

        questions = self.connection.execute(
            "SELECT q.id, q.ordinal, q.question_text, q.max_marks_milli, "
            "s.question_number, s.section_label, s.question_type, "
            "s.negative_marks_milli, s.scoring_policy, s.chapter_label, "
            "s.subtopic_label, s.concepts_json, s.difficulty, s.expected_method, "
            "s.answer_json, s.solution_text, s.rubric_text, "
            "(SELECT m.topic_id FROM question_topic_mappings m "
            " WHERE m.question_id=q.id AND m.state='confirmed' "
            " ORDER BY COALESCE(m.rank, 999999), m.created_at, m.id LIMIT 1) AS topic_id "
            "FROM questions q "
            "JOIN assessment_question_specs s ON s.question_id=q.id "
            "WHERE q.assessment_id=? AND q.deleted_at IS NULL "
            "ORDER BY q.ordinal",
            (str(assessment_id),),
        ).fetchall()
        if not questions:
            raise AssessmentRunnerRepositoryDataError(
                "Assessment has no runnable questions."
            )

        result = []
        for row in questions:
            item = dict(row)
            options = self.connection.execute(
                "SELECT option_id, position, option_text "
                "FROM question_options WHERE question_id=? ORDER BY position",
                (str(item["id"]),),
            ).fetchall()
            item["options"] = tuple(dict(option) for option in options)
            result.append(item)
        return dict(header), tuple(result)

    def start_or_resume_session(
        self,
        assessment_id: str,
        *,
        session_id: str,
        started_at: str,
        expires_at: str,
    ):
        with transaction(self.connection, immediate=True):
            self._expire_assessment_sessions(str(assessment_id), str(started_at))
            existing = self.connection.execute(
                "SELECT id FROM assessment_test_sessions "
                "WHERE assessment_id=? AND status='active' "
                "ORDER BY started_at DESC LIMIT 1",
                (str(assessment_id),),
            ).fetchone()
            if existing is not None:
                return {
                    "session_id": str(existing["id"]),
                    "created": False,
                }

            header, questions = self._load_assessment_snapshot(str(assessment_id))
            duration_seconds = int(header["duration_minutes"]) * 60
            max_marks_milli = sum(int(q["max_marks_milli"] or 0) for q in questions)

            self.connection.execute(
                "INSERT INTO assessment_test_sessions "
                "(id, assessment_id, status, mode, title_snapshot, "
                "course_code_snapshot, course_name_snapshot, instructions_snapshot, "
                "duration_seconds, question_count, max_marks_milli, started_at, "
                "expires_at, submitted_at, submission_reason, current_ordinal, "
                "revision, created_at, updated_at) "
                "VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, "
                "1, 1, ?, ?)",
                (
                    str(session_id),
                    str(assessment_id),
                    str(header["mode"]),
                    str(header["title"]),
                    str(header["course_code"]),
                    str(header["course_name"]),
                    str(header["instructions_text"] or ""),
                    duration_seconds,
                    len(questions),
                    max_marks_milli,
                    str(started_at),
                    str(expires_at),
                    str(started_at),
                    str(started_at),
                ),
            )

            for question in questions:
                session_question_id = str(uuid.uuid4())
                public_options = [
                    {
                        "id": str(option["option_id"]),
                        "text": str(option["option_text"]),
                    }
                    for option in question["options"]
                ]
                self.connection.execute(
                    "INSERT INTO assessment_test_session_questions "
                    "(id, session_id, question_id, ordinal, question_number, "
                    "section_label, question_type, question_text, max_marks_milli, "
                    "negative_marks_milli, scoring_policy, topic_id, chapter_label, "
                    "subtopic_label, concepts_json, difficulty, expected_method, "
                    "options_json, answer_key_json, solution_text, rubric_text, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_question_id,
                        str(session_id),
                        str(question["id"]),
                        int(question["ordinal"]),
                        str(question["question_number"] or ""),
                        str(question["section_label"] or ""),
                        str(question["question_type"]),
                        str(question["question_text"]),
                        int(question["max_marks_milli"] or 0),
                        int(question["negative_marks_milli"] or 0),
                        str(question["scoring_policy"] or "standard"),
                        question["topic_id"],
                        str(question["chapter_label"] or ""),
                        str(question["subtopic_label"] or ""),
                        str(question["concepts_json"] or "[]"),
                        str(question["difficulty"] or ""),
                        str(question["expected_method"] or ""),
                        json.dumps(public_options, ensure_ascii=False, separators=(",", ":")),
                        str(question["answer_json"] or "{}"),
                        str(question["solution_text"] or ""),
                        str(question["rubric_text"] or ""),
                        str(started_at),
                    ),
                )
                self.connection.execute(
                    "INSERT INTO assessment_test_responses "
                    "(id, session_question_id, state, response_json, focus_seconds, "
                    "visited_at, answered_at, saved_at, revision, updated_at) "
                    "VALUES (?, ?, 'not_visited', '{}', 0, NULL, NULL, NULL, 1, ?)",
                    (
                        str(uuid.uuid4()),
                        session_question_id,
                        str(started_at),
                    ),
                )

            self.connection.execute(
                "INSERT INTO assessment_test_events "
                "(id, session_id, session_question_id, event_type, details_json, occurred_at) "
                "VALUES (?, ?, NULL, 'session_started', ?, ?)",
                (
                    str(uuid.uuid4()),
                    str(session_id),
                    json.dumps(
                        {
                            "question_count": len(questions),
                            "duration_seconds": duration_seconds,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    str(started_at),
                ),
            )
        return {"session_id": str(session_id), "created": True}

    def get_session_header(self, session_id: str):
        row = self.connection.execute(
            "SELECT id, assessment_id, status, mode, title_snapshot, "
            "course_code_snapshot, course_name_snapshot, instructions_snapshot, "
            "duration_seconds, question_count, max_marks_milli, started_at, "
            "expires_at, submitted_at, submission_reason, current_ordinal, revision "
            "FROM assessment_test_sessions WHERE id=?",
            (str(session_id),),
        ).fetchone()
        return self._dict(row)

    def get_public_session(self, session_id: str):
        header = self.get_session_header(str(session_id))
        if header is None:
            return None
        rows = self.connection.execute(
            "SELECT q.id AS session_question_id, q.question_id, q.ordinal, "
            "q.question_number, q.section_label, q.question_type, q.question_text, "
            "q.max_marks_milli, q.negative_marks_milli, q.scoring_policy, "
            "q.topic_id, q.chapter_label, q.subtopic_label, q.concepts_json, "
            "q.difficulty, q.expected_method, q.options_json, "
            "r.state, r.response_json, r.focus_seconds, r.visited_at, "
            "r.answered_at, r.saved_at, r.revision AS response_revision "
            "FROM assessment_test_session_questions q "
            "JOIN assessment_test_responses r ON r.session_question_id=q.id "
            "WHERE q.session_id=? ORDER BY q.ordinal",
            (str(session_id),),
        ).fetchall()
        result = dict(header)
        result["questions"] = tuple(dict(row) for row in rows)
        return result

    def get_private_question_snapshot(self, session_question_id: str):
        row = self.connection.execute(
            "SELECT q.*, r.state, r.response_json, r.focus_seconds "
            "FROM assessment_test_session_questions q "
            "JOIN assessment_test_responses r ON r.session_question_id=q.id "
            "WHERE q.id=?",
            (str(session_question_id),),
        ).fetchone()
        return self._dict(row)

    def mark_visited(
        self,
        session_id: str,
        session_question_id: str,
        *,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            self._expire_if_due(str(session_id), str(now))
            session = self.connection.execute(
                "SELECT status FROM assessment_test_sessions WHERE id=?",
                (str(session_id),),
            ).fetchone()
            if session is None:
                raise AssessmentRunnerRepositoryNotFoundError("Test session not found.")
            if str(session["status"]) != "active":
                return str(session["status"])

            row = self.connection.execute(
                "SELECT q.ordinal, r.state FROM assessment_test_session_questions q "
                "JOIN assessment_test_responses r ON r.session_question_id=q.id "
                "WHERE q.id=? AND q.session_id=?",
                (str(session_question_id), str(session_id)),
            ).fetchone()
            if row is None:
                raise AssessmentRunnerRepositoryNotFoundError(
                    "Question does not belong to this test session."
                )

            self.connection.execute(
                "UPDATE assessment_test_sessions SET current_ordinal=?, updated_at=?, "
                "revision=revision+1 WHERE id=?",
                (int(row["ordinal"]), str(now), str(session_id)),
            )
            if str(row["state"]) == "not_visited":
                self.connection.execute(
                    "UPDATE assessment_test_responses SET state='not_answered', "
                    "visited_at=?, updated_at=?, revision=revision+1 "
                    "WHERE session_question_id=?",
                    (str(now), str(now), str(session_question_id)),
                )
                self.connection.execute(
                    "INSERT INTO assessment_test_events "
                    "(id, session_id, session_question_id, event_type, details_json, occurred_at) "
                    "VALUES (?, ?, ?, 'question_visited', '{}', ?)",
                    (
                        str(uuid.uuid4()),
                        str(session_id),
                        str(session_question_id),
                        str(now),
                    ),
                )
        return "active"

    def save_response(
        self,
        session_id: str,
        session_question_id: str,
        *,
        response_json: str,
        answered: bool,
        mark_for_review: bool | None,
        focus_seconds_delta: int,
        event_type: str,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            self._expire_if_due(str(session_id), str(now))
            session = self.connection.execute(
                "SELECT status FROM assessment_test_sessions WHERE id=?",
                (str(session_id),),
            ).fetchone()
            if session is None:
                raise AssessmentRunnerRepositoryNotFoundError("Test session not found.")
            if str(session["status"]) != "active":
                return {"status": str(session["status"]), "saved": False}

            row = self.connection.execute(
                "SELECT r.state, r.response_json, r.visited_at, r.answered_at "
                "FROM assessment_test_session_questions q "
                "JOIN assessment_test_responses r ON r.session_question_id=q.id "
                "WHERE q.id=? AND q.session_id=?",
                (str(session_question_id), str(session_id)),
            ).fetchone()
            if row is None:
                raise AssessmentRunnerRepositoryNotFoundError(
                    "Question does not belong to this test session."
                )

            old_state = str(row["state"])
            old_marked = old_state in {
                "marked_for_review",
                "answered_marked_for_review",
            }
            marked = old_marked if mark_for_review is None else bool(mark_for_review)
            if answered and marked:
                new_state = "answered_marked_for_review"
            elif answered:
                new_state = "answered"
            elif marked:
                new_state = "marked_for_review"
            else:
                new_state = "not_answered"

            changed = (
                str(row["response_json"] or "{}") != str(response_json)
                or old_state != new_state
            )
            answered_at = row["answered_at"]
            if answered and answered_at is None:
                answered_at = str(now)

            self.connection.execute(
                "UPDATE assessment_test_responses SET state=?, response_json=?, "
                "focus_seconds=focus_seconds+?, "
                "visited_at=COALESCE(visited_at, ?), answered_at=?, saved_at=?, "
                "updated_at=?, revision=revision+1 "
                "WHERE session_question_id=?",
                (
                    new_state,
                    str(response_json),
                    int(focus_seconds_delta),
                    str(now),
                    answered_at,
                    str(now),
                    str(now),
                    str(session_question_id),
                ),
            )
            if changed:
                self.connection.execute(
                    "INSERT INTO assessment_test_events "
                    "(id, session_id, session_question_id, event_type, details_json, occurred_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        str(session_id),
                        str(session_question_id),
                        str(event_type),
                        json.dumps(
                            {"state": new_state},
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        str(now),
                    ),
                )
        return {"status": "active", "saved": True, "state": new_state}

    def add_focus_time(
        self,
        session_id: str,
        session_question_id: str | None,
        *,
        focus_seconds_delta: int,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            self._expire_if_due(str(session_id), str(now))
            header = self.connection.execute(
                "SELECT status FROM assessment_test_sessions WHERE id=?",
                (str(session_id),),
            ).fetchone()
            if header is None:
                raise AssessmentRunnerRepositoryNotFoundError("Test session not found.")
            if (
                str(header["status"]) == "active"
                and session_question_id
                and int(focus_seconds_delta) > 0
            ):
                cursor = self.connection.execute(
                    "UPDATE assessment_test_responses SET "
                    "focus_seconds=focus_seconds+?, updated_at=?, revision=revision+1 "
                    "WHERE session_question_id=? AND EXISTS ("
                    " SELECT 1 FROM assessment_test_session_questions q "
                    " WHERE q.id=? AND q.session_id=?"
                    ")",
                    (
                        int(focus_seconds_delta),
                        str(now),
                        str(session_question_id),
                        str(session_question_id),
                        str(session_id),
                    ),
                )
                if cursor.rowcount != 1:
                    raise AssessmentRunnerRepositoryNotFoundError(
                        "Question does not belong to this test session."
                    )
        return self.get_session_header(session_id)

    def submit_session(self, session_id: str, *, now: str):
        with transaction(self.connection, immediate=True):
            self._expire_if_due(str(session_id), str(now))
            row = self.connection.execute(
                "SELECT status, submitted_at, submission_reason "
                "FROM assessment_test_sessions WHERE id=?",
                (str(session_id),),
            ).fetchone()
            if row is None:
                raise AssessmentRunnerRepositoryNotFoundError("Test session not found.")
            if str(row["status"]) != "active":
                return {
                    "status": str(row["status"]),
                    "submitted_at": row["submitted_at"],
                    "submission_reason": row["submission_reason"],
                }
            self.connection.execute(
                "UPDATE assessment_test_sessions SET status='submitted', "
                "submitted_at=?, submission_reason='user', updated_at=?, "
                "revision=revision+1 WHERE id=? AND status='active'",
                (str(now), str(now), str(session_id)),
            )
            self.connection.execute(
                "INSERT INTO assessment_test_events "
                "(id, session_id, session_question_id, event_type, details_json, occurred_at) "
                "VALUES (?, ?, NULL, 'session_submitted', '{}', ?)",
                (str(uuid.uuid4()), str(session_id), str(now)),
            )
        return {
            "status": "submitted",
            "submitted_at": str(now),
            "submission_reason": "user",
        }

    def event_count(self, session_id: str, event_type: str):
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM assessment_test_events "
            "WHERE session_id=? AND event_type=?",
            (str(session_id), str(event_type)),
        ).fetchone()
        return int(row["count"]) if row is not None else 0
