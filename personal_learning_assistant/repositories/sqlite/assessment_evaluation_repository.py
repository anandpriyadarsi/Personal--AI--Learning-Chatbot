"""SQLite persistence for Assessment Studio Phase D evaluation."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Mapping, Sequence

from personal_learning_assistant.repositories.sqlite.connection import transaction


_REQUIRED_TABLES = {
    "assessment_test_sessions",
    "assessment_test_session_questions",
    "assessment_test_responses",
    "assessment_session_evaluations",
    "assessment_response_evaluations",
    "assessment_evaluation_mistakes",
    "assessment_evaluation_events",
    "question_attempts",
    "mistake_events",
}


class AssessmentEvaluationRepositoryError(RuntimeError):
    pass


class AssessmentEvaluationRepositorySchemaError(AssessmentEvaluationRepositoryError):
    pass


class AssessmentEvaluationRepositoryNotFoundError(AssessmentEvaluationRepositoryError):
    pass


class AssessmentEvaluationRepositoryConflictError(AssessmentEvaluationRepositoryError):
    pass


class AssessmentEvaluationRepositoryDataError(AssessmentEvaluationRepositoryError):
    pass


class SQLiteAssessmentEvaluationRepository:
    """Repository for terminal-session evaluation and audit persistence."""

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
            raise AssessmentEvaluationRepositorySchemaError(
                "Assessment Evaluation schema is unavailable; missing: {}".format(
                    ", ".join(missing)
                )
            )
        attempt_columns = {
            str(row[1])
            for row in self.connection.execute(
                "PRAGMA table_info(question_attempts)"
            ).fetchall()
        }
        required_attempt_columns = {"signed_score_milli", "evaluation_ref"}
        missing_columns = sorted(required_attempt_columns - attempt_columns)
        if missing_columns:
            raise AssessmentEvaluationRepositorySchemaError(
                "Phase D question_attempt columns are unavailable: {}".format(
                    ", ".join(missing_columns)
                )
            )

    @staticmethod
    def _dict(row):
        return dict(row) if row is not None else None

    def get_terminal_session(self, session_id: str):
        row = self.connection.execute(
            "SELECT s.id, s.assessment_id, s.status, s.mode, s.title_snapshot, "
            "s.course_code_snapshot, s.course_name_snapshot, s.question_count, "
            "s.max_marks_milli, s.started_at, s.expires_at, s.submitted_at, "
            "s.submission_reason "
            "FROM assessment_test_sessions s WHERE s.id=?",
            (str(session_id),),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_private_session_questions(self, session_id: str):
        rows = self.connection.execute(
            "SELECT q.id AS session_question_id, q.question_id, q.ordinal, "
            "q.question_number, q.section_label, q.question_type, q.question_text, "
            "q.max_marks_milli, q.negative_marks_milli, q.scoring_policy, "
            "q.topic_id, q.chapter_label, q.subtopic_label, q.concepts_json, "
            "q.difficulty, q.expected_method, q.options_json, q.answer_key_json, "
            "q.solution_text, q.rubric_text, "
            "r.id AS response_id, r.state AS response_state, r.response_json, "
            "r.focus_seconds, r.visited_at, r.answered_at, r.saved_at "
            "FROM assessment_test_session_questions q "
            "JOIN assessment_test_responses r ON r.session_question_id=q.id "
            "WHERE q.session_id=? ORDER BY q.ordinal",
            (str(session_id),),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_session_evaluation_id(self, session_id: str):
        row = self.connection.execute(
            "SELECT id FROM assessment_session_evaluations WHERE session_id=?",
            (str(session_id),),
        ).fetchone()
        return str(row["id"]) if row is not None else None

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        session_evaluation_id: str,
        response_evaluation_id: str | None,
        event_type: str,
        details: Mapping[str, Any] | None,
        now: str,
    ) -> None:
        connection.execute(
            "INSERT INTO assessment_evaluation_events "
            "(id, session_evaluation_id, response_evaluation_id, event_type, "
            "details_json, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                str(session_evaluation_id),
                str(response_evaluation_id) if response_evaluation_id else None,
                str(event_type),
                json.dumps(
                    dict(details or {}),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                str(now),
            ),
        )

    def _create_attempt(
        self,
        connection: sqlite3.Connection,
        *,
        evaluation_id: str,
        question_id: str,
        response_id: str,
        outcome: str,
        awarded_marks_milli: int,
        max_marks_milli: int,
        feedback_text: str,
        occurred_at: str,
    ) -> str:
        existing = connection.execute(
            "SELECT question_attempt_id FROM assessment_response_evaluations "
            "WHERE id=?",
            (str(evaluation_id),),
        ).fetchone()
        if existing is None:
            raise AssessmentEvaluationRepositoryNotFoundError(
                "Response evaluation not found."
            )
        if existing["question_attempt_id"]:
            return str(existing["question_attempt_id"])

        attempt_number = int(
            connection.execute(
                "SELECT COALESCE(MAX(attempt_number), 0) + 1 "
                "FROM question_attempts WHERE question_id=?",
                (str(question_id),),
            ).fetchone()[0]
        )
        attempt_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO question_attempts "
            "(id, question_id, attempt_number, outcome, earned_marks_milli, "
            "max_marks_milli, response_ref, feedback_ref, occurred_at, "
            "signed_score_milli, evaluation_ref) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                str(question_id),
                attempt_number,
                str(outcome),
                max(0, int(awarded_marks_milli)),
                int(max_marks_milli),
                "assessment_test_response:{}".format(response_id),
                "assessment_response_evaluation:{}".format(evaluation_id),
                str(occurred_at),
                int(awarded_marks_milli),
                "assessment_response_evaluation:{}".format(evaluation_id),
            ),
        )
        connection.execute(
            "UPDATE assessment_response_evaluations SET question_attempt_id=? "
            "WHERE id=?",
            (attempt_id, str(evaluation_id)),
        )
        return attempt_id

    def _sync_confirmed_mistakes(
        self,
        connection: sqlite3.Connection,
        *,
        response_evaluation_id: str,
        attempt_id: str,
        now: str,
    ) -> None:
        evaluation = connection.execute(
            "SELECT status, outcome, awarded_marks_milli, question_attempt_id "
            "FROM assessment_response_evaluations WHERE id=?",
            (str(response_evaluation_id),),
        ).fetchone()
        # Recheck at the evidence write boundary, including legacy classifications.
        if (evaluation is None or evaluation["status"] not in {"confirmed", "auto_confirmed"}
                or evaluation["outcome"] not in {"incorrect", "partially_correct", "unanswered"}
                or evaluation["awarded_marks_milli"] is None
                or str(evaluation["question_attempt_id"]) != str(attempt_id)):
            return
        rows = connection.execute(
            "SELECT id, category, note FROM assessment_evaluation_mistakes "
            "WHERE response_evaluation_id=? AND status='confirmed' "
            "AND mistake_event_id IS NULL ORDER BY created_at, id",
            (str(response_evaluation_id),),
        ).fetchall()
        for row in rows:
            mistake_event_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO mistake_events "
                "(id, attempt_id, category, mistake_text, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, NULL)",
                (
                    mistake_event_id,
                    str(attempt_id),
                    str(row["category"]),
                    str(row["note"] or ""),
                    str(now),
                ),
            )
            connection.execute(
                "UPDATE assessment_evaluation_mistakes SET mistake_event_id=?, "
                "confirmed_at=COALESCE(confirmed_at, ?) WHERE id=?",
                (mistake_event_id, str(now), str(row["id"])),
            )

    def _refresh_session_status(
        self,
        connection: sqlite3.Connection,
        *,
        session_evaluation_id: str,
        now: str,
    ) -> str:
        rows = connection.execute(
            "SELECT status FROM assessment_response_evaluations "
            "WHERE session_evaluation_id=?",
            (str(session_evaluation_id),),
        ).fetchall()
        statuses = {str(row["status"]) for row in rows}
        if "awaiting_review" in statuses:
            status = "pending_review"
        elif "provisional" in statuses:
            status = "provisional"
        else:
            status = "confirmed"
        confirmed_at = str(now) if status == "confirmed" else None
        connection.execute(
            "UPDATE assessment_session_evaluations SET status=?, updated_at=?, "
            "confirmed_at=? WHERE id=?",
            (
                status,
                str(now),
                confirmed_at,
                str(session_evaluation_id),
            ),
        )
        return status

    def create_evaluation(
        self,
        *,
        session_id: str,
        session_evaluation_id: str,
        engine_version: str,
        rows: Sequence[Mapping[str, Any]],
        now: str,
    ) -> str:
        with transaction(self.connection, immediate=True):
            session = self.connection.execute(
                "SELECT status, submitted_at, expires_at "
                "FROM assessment_test_sessions WHERE id=?",
                (str(session_id),),
            ).fetchone()
            if session is None:
                raise AssessmentEvaluationRepositoryNotFoundError(
                    "Test session not found."
                )
            if str(session["status"]) not in {"submitted", "expired"}:
                raise AssessmentEvaluationRepositoryConflictError(
                    "Only a submitted or expired test can be evaluated."
                )

            existing = self.connection.execute(
                "SELECT id FROM assessment_session_evaluations WHERE session_id=?",
                (str(session_id),),
            ).fetchone()
            if existing is not None:
                return str(existing["id"])

            self.connection.execute(
                "INSERT INTO assessment_session_evaluations "
                "(id, session_id, status, engine_version, created_at, updated_at, confirmed_at) "
                "VALUES (?, ?, 'pending_review', ?, ?, ?, NULL)",
                (
                    str(session_evaluation_id),
                    str(session_id),
                    str(engine_version),
                    str(now),
                    str(now),
                ),
            )

            occurred_at = str(session["submitted_at"] or session["expires_at"] or now)
            for row in rows:
                self.connection.execute(
                    "INSERT INTO assessment_response_evaluations "
                    "(id, session_evaluation_id, session_question_id, question_id, "
                    "response_id, evaluator_type, evaluator_model, status, outcome, "
                    "awarded_marks_milli, max_marks_milli, penalty_marks_milli, "
                    "scoring_policy, rubric_version, confidence, feedback_text, "
                    "details_json, question_attempt_id, created_at, updated_at, confirmed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)",
                    (
                        str(row["id"]),
                        str(session_evaluation_id),
                        str(row["session_question_id"]),
                        str(row["question_id"]),
                        str(row["response_id"]),
                        str(row["evaluator_type"]),
                        str(row.get("evaluator_model") or ""),
                        str(row["status"]),
                        str(row["outcome"]),
                        row.get("awarded_marks_milli"),
                        int(row["max_marks_milli"]),
                        int(row.get("penalty_marks_milli") or 0),
                        str(row["scoring_policy"]),
                        str(row.get("rubric_version") or ""),
                        row.get("confidence"),
                        str(row.get("feedback_text") or ""),
                        str(row.get("details_json") or "{}"),
                        str(now),
                        str(now),
                        (
                            str(now)
                            if str(row["status"]) in {"auto_confirmed", "confirmed"}
                            else None
                        ),
                    ),
                )
                if (
                    str(row["status"]) in {"auto_confirmed", "confirmed"}
                    and row.get("awarded_marks_milli") is not None
                ):
                    attempt_id = self._create_attempt(
                        self.connection,
                        evaluation_id=str(row["id"]),
                        question_id=str(row["question_id"]),
                        response_id=str(row["response_id"]),
                        outcome=str(row["outcome"]),
                        awarded_marks_milli=int(row["awarded_marks_milli"]),
                        max_marks_milli=int(row["max_marks_milli"]),
                        feedback_text=str(row.get("feedback_text") or ""),
                        occurred_at=occurred_at,
                    )
                    self._sync_confirmed_mistakes(
                        self.connection,
                        response_evaluation_id=str(row["id"]),
                        attempt_id=attempt_id,
                        now=str(now),
                    )

            status = self._refresh_session_status(
                self.connection,
                session_evaluation_id=str(session_evaluation_id),
                now=str(now),
            )
            self._insert_event(
                self.connection,
                session_evaluation_id=str(session_evaluation_id),
                response_evaluation_id=None,
                event_type="evaluation_created",
                details={
                    "question_count": len(rows),
                    "status": status,
                    "engine_version": str(engine_version),
                },
                now=str(now),
            )
        return str(session_evaluation_id)

    def get_evaluation(self, session_id: str):
        session = self.connection.execute(
            "SELECT s.id AS session_id, s.assessment_id, s.status AS session_status, "
            "a.course_id, s.mode, s.title_snapshot, s.course_code_snapshot, s.course_name_snapshot, "
            "s.question_count, s.max_marks_milli AS session_max_marks_milli, "
            "s.started_at, s.submitted_at, s.submission_reason, "
            "e.id AS session_evaluation_id, e.status AS evaluation_status, "
            "e.engine_version, e.created_at AS evaluation_created_at, "
            "e.updated_at AS evaluation_updated_at, e.confirmed_at AS evaluation_confirmed_at "
            "FROM assessment_test_sessions s "
            "LEFT JOIN assessments a ON a.id=s.assessment_id "
            "LEFT JOIN assessment_session_evaluations e ON e.session_id=s.id "
            "WHERE s.id=?",
            (str(session_id),),
        ).fetchone()
        if session is None:
            return None
        result = dict(session)
        evaluation_id = result.get("session_evaluation_id")
        result["questions"] = ()
        if not evaluation_id:
            return result

        rows = self.connection.execute(
            "SELECT ev.id AS evaluation_id, ev.session_question_id, ev.question_id, "
            "ev.response_id, ev.evaluator_type, ev.evaluator_model, ev.status, "
            "ev.outcome, ev.awarded_marks_milli, ev.max_marks_milli, "
            "ev.penalty_marks_milli, ev.scoring_policy, ev.rubric_version, "
            "ev.confidence, ev.feedback_text, ev.details_json, "
            "ev.question_attempt_id, ev.created_at, ev.updated_at, ev.confirmed_at, "
            "q.ordinal, q.question_number, q.section_label, q.question_type, "
            "q.question_text, q.topic_id, q.chapter_label, q.subtopic_label, "
            "q.concepts_json, q.difficulty, q.expected_method, q.options_json, "
            "q.answer_key_json, q.solution_text, q.rubric_text, "
            "r.state AS response_state, r.response_json, r.focus_seconds "
            "FROM assessment_response_evaluations ev "
            "JOIN assessment_test_session_questions q ON q.id=ev.session_question_id "
            "JOIN assessment_test_responses r ON r.id=ev.response_id "
            "WHERE ev.session_evaluation_id=? ORDER BY q.ordinal",
            (str(evaluation_id),),
        ).fetchall()
        questions = []
        for row in rows:
            item = dict(row)
            mistakes = self.connection.execute(
                "SELECT id, category, note, source_type, status, mistake_event_id, "
                "created_at, confirmed_at FROM assessment_evaluation_mistakes "
                "WHERE response_evaluation_id=? ORDER BY created_at, id",
                (str(item["evaluation_id"]),),
            ).fetchall()
            item["mistakes"] = tuple(dict(mistake) for mistake in mistakes)
            questions.append(item)
        result["questions"] = tuple(questions)
        return result

    def update_manual_evaluation(
        self,
        evaluation_id: str,
        *,
        evaluator_type: str,
        evaluator_model: str,
        status: str,
        outcome: str,
        awarded_marks_milli: int,
        confidence: float | None,
        feedback_text: str,
        details_json: str,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT ev.*, se.id AS session_evaluation_id, s.submitted_at, s.expires_at "
                "FROM assessment_response_evaluations ev "
                "JOIN assessment_session_evaluations se ON se.id=ev.session_evaluation_id "
                "JOIN assessment_test_sessions s ON s.id=se.session_id "
                "WHERE ev.id=?",
                (str(evaluation_id),),
            ).fetchone()
            if row is None:
                raise AssessmentEvaluationRepositoryNotFoundError(
                    "Response evaluation not found."
                )
            if str(row["status"]) == "auto_confirmed":
                raise AssessmentEvaluationRepositoryConflictError(
                    "Deterministic auto-confirmed evaluations are immutable."
                )
            if str(row["status"]) == "confirmed":
                raise AssessmentEvaluationRepositoryConflictError(
                    "Confirmed manual evaluations are immutable."
                )

            self.connection.execute(
                "UPDATE assessment_response_evaluations SET "
                "evaluator_type=?, evaluator_model=?, status=?, outcome=?, "
                "awarded_marks_milli=?, penalty_marks_milli=?, confidence=?, "
                "feedback_text=?, details_json=?, updated_at=?, confirmed_at=? "
                "WHERE id=?",
                (
                    str(evaluator_type),
                    str(evaluator_model or ""),
                    str(status),
                    str(outcome),
                    int(awarded_marks_milli),
                    max(0, -int(awarded_marks_milli)),
                    confidence,
                    str(feedback_text or ""),
                    str(details_json or "{}"),
                    str(now),
                    str(now) if status == "confirmed" else None,
                    str(evaluation_id),
                ),
            )

            if status == "confirmed":
                occurred_at = str(row["submitted_at"] or row["expires_at"] or now)
                attempt_id = self._create_attempt(
                    self.connection,
                    evaluation_id=str(evaluation_id),
                    question_id=str(row["question_id"]),
                    response_id=str(row["response_id"]),
                    outcome=str(outcome),
                    awarded_marks_milli=int(awarded_marks_milli),
                    max_marks_milli=int(row["max_marks_milli"]),
                    feedback_text=str(feedback_text or ""),
                    occurred_at=occurred_at,
                )
                self._sync_confirmed_mistakes(
                    self.connection,
                    response_evaluation_id=str(evaluation_id),
                    attempt_id=attempt_id,
                    now=str(now),
                )

            overall = self._refresh_session_status(
                self.connection,
                session_evaluation_id=str(row["session_evaluation_id"]),
                now=str(now),
            )
            self._insert_event(
                self.connection,
                session_evaluation_id=str(row["session_evaluation_id"]),
                response_evaluation_id=str(evaluation_id),
                event_type=(
                    "manual_evaluation_confirmed"
                    if status == "confirmed"
                    else "manual_evaluation_provisional"
                ),
                details={
                    "evaluator_type": str(evaluator_type),
                    "awarded_marks_milli": int(awarded_marks_milli),
                    "outcome": str(outcome),
                    "overall_status": overall,
                },
                now=str(now),
            )
        return self.get_response_evaluation(evaluation_id)

    def confirm_provisional_evaluation(self, evaluation_id: str, *, now: str):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT ev.*, se.id AS session_evaluation_id, s.submitted_at, s.expires_at "
                "FROM assessment_response_evaluations ev "
                "JOIN assessment_session_evaluations se ON se.id=ev.session_evaluation_id "
                "JOIN assessment_test_sessions s ON s.id=se.session_id "
                "WHERE ev.id=?",
                (str(evaluation_id),),
            ).fetchone()
            if row is None:
                raise AssessmentEvaluationRepositoryNotFoundError(
                    "Response evaluation not found."
                )
            if str(row["status"]) != "provisional":
                raise AssessmentEvaluationRepositoryConflictError(
                    "Only a provisional evaluation can be confirmed."
                )
            if row["awarded_marks_milli"] is None:
                raise AssessmentEvaluationRepositoryDataError(
                    "Provisional evaluation has no score."
                )

            self.connection.execute(
                "UPDATE assessment_response_evaluations SET status='confirmed', "
                "updated_at=?, confirmed_at=? WHERE id=?",
                (str(now), str(now), str(evaluation_id)),
            )
            occurred_at = str(row["submitted_at"] or row["expires_at"] or now)
            attempt_id = self._create_attempt(
                self.connection,
                evaluation_id=str(evaluation_id),
                question_id=str(row["question_id"]),
                response_id=str(row["response_id"]),
                outcome=str(row["outcome"]),
                awarded_marks_milli=int(row["awarded_marks_milli"]),
                max_marks_milli=int(row["max_marks_milli"]),
                feedback_text=str(row["feedback_text"] or ""),
                occurred_at=occurred_at,
            )
            self._sync_confirmed_mistakes(
                self.connection,
                response_evaluation_id=str(evaluation_id),
                attempt_id=attempt_id,
                now=str(now),
            )
            overall = self._refresh_session_status(
                self.connection,
                session_evaluation_id=str(row["session_evaluation_id"]),
                now=str(now),
            )
            self._insert_event(
                self.connection,
                session_evaluation_id=str(row["session_evaluation_id"]),
                response_evaluation_id=str(evaluation_id),
                event_type="provisional_evaluation_confirmed",
                details={"overall_status": overall},
                now=str(now),
            )
        return self.get_response_evaluation(evaluation_id)

    def get_response_evaluation(self, evaluation_id: str):
        row = self.connection.execute(
            "SELECT ev.*, q.ordinal, q.question_number, q.question_type, q.question_text, "
            "q.negative_marks_milli, q.topic_id, q.options_json, q.answer_key_json, "
            "q.solution_text, q.rubric_text, r.response_json, r.focus_seconds, "
            "se.session_id, s.status AS session_status "
            "FROM assessment_response_evaluations ev "
            "JOIN assessment_test_session_questions q ON q.id=ev.session_question_id "
            "JOIN assessment_test_responses r ON r.id=ev.response_id "
            "JOIN assessment_session_evaluations se ON se.id=ev.session_evaluation_id "
            "JOIN assessment_test_sessions s ON s.id=se.session_id "
            "WHERE ev.id=?",
            (str(evaluation_id),),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        mistakes = self.connection.execute(
            "SELECT id, category, note, source_type, status, mistake_event_id, "
            "created_at, confirmed_at FROM assessment_evaluation_mistakes "
            "WHERE response_evaluation_id=? ORDER BY created_at, id",
            (str(evaluation_id),),
        ).fetchall()
        result["mistakes"] = tuple(dict(item) for item in mistakes)
        return result

    def add_mistake(
        self,
        evaluation_id: str,
        *,
        mistake_id: str,
        category: str,
        note: str,
        source_type: str,
        status: str,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT ev.id, ev.question_attempt_id, ev.session_evaluation_id, "
                "ev.status AS evaluation_status, ev.outcome, ev.awarded_marks_milli "
                "FROM assessment_response_evaluations ev WHERE ev.id=?",
                (str(evaluation_id),),
            ).fetchone()
            if row is None:
                raise AssessmentEvaluationRepositoryNotFoundError(
                    "Response evaluation not found."
                )
            if (row["evaluation_status"] == "awaiting_review"
                    or row["awarded_marks_milli"] is None
                    or row["outcome"] not in {"incorrect", "partially_correct", "unanswered"}):
                raise AssessmentEvaluationRepositoryConflictError(
                    "Mistakes require a graded, non-correct response."
                )
            try:
                self.connection.execute(
                    "INSERT INTO assessment_evaluation_mistakes "
                    "(id, response_evaluation_id, category, note, source_type, status, "
                    "mistake_event_id, created_at, confirmed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                    (
                        str(mistake_id),
                        str(evaluation_id),
                        str(category),
                        str(note or ""),
                        str(source_type),
                        str(status),
                        str(now),
                        str(now) if status == "confirmed" else None,
                    ),
                )
            except sqlite3.IntegrityError as error:
                if "UNIQUE constraint failed" in str(error):
                    raise AssessmentEvaluationRepositoryConflictError(
                        "This mistake category is already recorded for the question."
                    ) from error
                raise

            if status == "confirmed" and row["question_attempt_id"]:
                self._sync_confirmed_mistakes(
                    self.connection,
                    response_evaluation_id=str(evaluation_id),
                    attempt_id=str(row["question_attempt_id"]),
                    now=str(now),
                )
            self._insert_event(
                self.connection,
                session_evaluation_id=str(row["session_evaluation_id"]),
                response_evaluation_id=str(evaluation_id),
                event_type="mistake_classified",
                details={
                    "category": str(category),
                    "source_type": str(source_type),
                    "status": str(status),
                },
                now=str(now),
            )
        return self.get_response_evaluation(evaluation_id)

    def confirm_mistake(self, mistake_id: str, *, now: str):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT m.*, ev.question_attempt_id, ev.session_evaluation_id, "
                "ev.status AS evaluation_status, ev.outcome, ev.awarded_marks_milli "
                "FROM assessment_evaluation_mistakes m "
                "JOIN assessment_response_evaluations ev "
                "ON ev.id=m.response_evaluation_id "
                "WHERE m.id=?",
                (str(mistake_id),),
            ).fetchone()
            if row is None:
                raise AssessmentEvaluationRepositoryNotFoundError(
                    "Mistake classification not found."
                )
            if (row["evaluation_status"] == "awaiting_review"
                    or row["awarded_marks_milli"] is None
                    or row["outcome"] not in {"incorrect", "partially_correct", "unanswered"}):
                raise AssessmentEvaluationRepositoryConflictError(
                    "Mistakes require a graded, non-correct response."
                )
            if str(row["status"]) == "confirmed":
                return self.get_response_evaluation(str(row["response_evaluation_id"]))
            self.connection.execute(
                "UPDATE assessment_evaluation_mistakes SET status='confirmed', "
                "confirmed_at=? WHERE id=?",
                (str(now), str(mistake_id)),
            )
            if row["question_attempt_id"]:
                self._sync_confirmed_mistakes(
                    self.connection,
                    response_evaluation_id=str(row["response_evaluation_id"]),
                    attempt_id=str(row["question_attempt_id"]),
                    now=str(now),
                )
            self._insert_event(
                self.connection,
                session_evaluation_id=str(row["session_evaluation_id"]),
                response_evaluation_id=str(row["response_evaluation_id"]),
                event_type="mistake_classification_confirmed",
                details={"category": str(row["category"])},
                now=str(now),
            )
        return self.get_response_evaluation(str(row["response_evaluation_id"]))

    def event_count(self, session_evaluation_id: str, event_type: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM assessment_evaluation_events "
            "WHERE session_evaluation_id=? AND event_type=?",
            (str(session_evaluation_id), str(event_type)),
        ).fetchone()
        return int(row["count"]) if row is not None else 0
