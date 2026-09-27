"""SQLite persistence for Assessment Studio Phase F recommendations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Mapping

from personal_learning_assistant.repositories.sqlite.connection import transaction


_REQUIRED_TABLES = {
    "assessment_recovery_recommendations",
    "assessment_recovery_recommendation_events",
    "planner_tasks",
    "courses",
    "topics",
}


class AssessmentRecoveryRepositoryError(RuntimeError):
    pass


class AssessmentRecoveryRepositorySchemaError(AssessmentRecoveryRepositoryError):
    pass


class AssessmentRecoveryRepositoryNotFoundError(AssessmentRecoveryRepositoryError):
    pass


class AssessmentRecoveryRepositoryConflictError(AssessmentRecoveryRepositoryError):
    pass


class SQLiteAssessmentRecoveryRepository:
    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("explicit sqlite3.Connection required")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self._validate_schema()

    def _validate_schema(self):
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise AssessmentRecoveryRepositorySchemaError(
                "Adaptive Academic Loop schema is unavailable; missing: {}".format(
                    ", ".join(missing)
                )
            )

    def _event(
        self,
        connection,
        *,
        recommendation_id: str,
        event_type: str,
        details: Mapping[str, Any] | None,
        now: str,
    ):
        connection.execute(
            "INSERT INTO assessment_recovery_recommendation_events "
            "(id, recommendation_id, event_type, details_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                str(recommendation_id),
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

    def list_courses(self):
        return tuple(dict(row) for row in self.connection.execute(
            "SELECT id, code, name FROM courses WHERE deleted_at IS NULL ORDER BY code, id"
        ).fetchall())

    def list_recommendations(self):
        rows = self.connection.execute(
            "SELECT r.*, c.code AS course_code, c.name AS course_name, "
            "t.name AS canonical_topic_name, pt.status AS planner_task_status "
            "FROM assessment_recovery_recommendations r "
            "JOIN courses c ON c.id=r.course_id "
            "LEFT JOIN topics t ON t.id=r.topic_id "
            "LEFT JOIN planner_tasks pt ON pt.id=r.planner_task_id "
            "ORDER BY "
            "CASE r.status "
            "WHEN 'pending' THEN 0 WHEN 'accepted' THEN 1 WHEN 'applied' THEN 2 "
            "WHEN 'rejected' THEN 3 ELSE 4 END, "
            "r.created_at DESC, r.id DESC"
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_recommendation(self, recommendation_id: str):
        row = self.connection.execute(
            "SELECT r.*, c.code AS course_code, c.name AS course_name, "
            "t.name AS canonical_topic_name, pt.status AS planner_task_status "
            "FROM assessment_recovery_recommendations r "
            "JOIN courses c ON c.id=r.course_id "
            "LEFT JOIN topics t ON t.id=r.topic_id "
            "LEFT JOIN planner_tasks pt ON pt.id=r.planner_task_id "
            "WHERE r.id=?",
            (str(recommendation_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def persist_candidate(self, candidate: Mapping[str, Any], *, now: str):
        fingerprint = str(candidate["evidence_fingerprint"])
        course_id = str(candidate["course_id"])
        topic_id = str(candidate.get("topic_id") or "") or None

        with transaction(self.connection, immediate=True):
            existing = self.connection.execute(
                "SELECT * FROM assessment_recovery_recommendations "
                "WHERE evidence_fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if existing is not None:
                return {
                    "recommendation_id": str(existing["id"]),
                    "created": False,
                    "status": str(existing["status"]),
                }

            if topic_id is None:
                pending = self.connection.execute(
                    "SELECT id FROM assessment_recovery_recommendations "
                    "WHERE course_id=? AND topic_id IS NULL AND status='pending'",
                    (course_id,),
                ).fetchone()
            else:
                pending = self.connection.execute(
                    "SELECT id FROM assessment_recovery_recommendations "
                    "WHERE course_id=? AND topic_id=? AND status='pending'",
                    (course_id, topic_id),
                ).fetchone()

            if pending is not None:
                old_id = str(pending["id"])
                self.connection.execute(
                    "UPDATE assessment_recovery_recommendations SET "
                    "status='superseded', updated_at=?, superseded_at=?, revision=revision+1 "
                    "WHERE id=? AND status='pending'",
                    (str(now), str(now), old_id),
                )
                self._event(
                    self.connection,
                    recommendation_id=old_id,
                    event_type="superseded",
                    details={"replacement_fingerprint": fingerprint},
                    now=str(now),
                )

            recommendation_id = str(candidate["id"])
            self.connection.execute(
                "INSERT INTO assessment_recovery_recommendations "
                "(id, evidence_fingerprint, course_id, topic_id, topic_label, "
                "source_kind, evidence_version, evidence_json, action_family, "
                "action_plan_json, alex_prompt, suggested_title, "
                "suggested_description, suggested_priority, suggested_minutes, "
                "status, planner_task_id, applied_payload_json, rejection_reason, "
                "revision, created_at, updated_at, accepted_at, applied_at, "
                "rejected_at, superseded_at) "
                "VALUES (?, ?, ?, ?, ?, 'assessment_intelligence', ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, 'pending', NULL, '{}', '', 1, ?, ?, NULL, NULL, NULL, NULL)",
                (
                    recommendation_id,
                    fingerprint,
                    course_id,
                    topic_id,
                    str(candidate["topic_label"]),
                    str(candidate["evidence_version"]),
                    str(candidate["evidence_json"]),
                    str(candidate["action_family"]),
                    str(candidate["action_plan_json"]),
                    str(candidate.get("alex_prompt") or ""),
                    str(candidate["suggested_title"]),
                    str(candidate.get("suggested_description") or ""),
                    str(candidate["suggested_priority"]),
                    candidate.get("suggested_minutes"),
                    str(now),
                    str(now),
                ),
            )
            self._event(
                self.connection,
                recommendation_id=recommendation_id,
                event_type="generated",
                details={
                    "evidence_fingerprint": fingerprint,
                    "action_family": str(candidate["action_family"]),
                },
                now=str(now),
            )
        return {
            "recommendation_id": recommendation_id,
            "created": True,
            "status": "pending",
        }

    def accept(
        self,
        recommendation_id: str,
        *,
        expected_revision: int,
        applied_payload_json: str,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT * FROM assessment_recovery_recommendations WHERE id=?",
                (str(recommendation_id),),
            ).fetchone()
            if row is None:
                raise AssessmentRecoveryRepositoryNotFoundError(
                    "Recovery recommendation not found."
                )
            status = str(row["status"])
            if status in {"accepted", "applied"}:
                return dict(row)
            if status != "pending":
                raise AssessmentRecoveryRepositoryConflictError(
                    "Only a pending recommendation can be applied."
                )
            if int(row["revision"]) != int(expected_revision):
                raise AssessmentRecoveryRepositoryConflictError(
                    "This recommendation changed. Refresh and review it again."
                )

            self.connection.execute(
                "UPDATE assessment_recovery_recommendations SET "
                "status='accepted', applied_payload_json=?, accepted_at=?, "
                "updated_at=?, revision=revision+1 WHERE id=? AND status='pending'",
                (
                    str(applied_payload_json),
                    str(now),
                    str(now),
                    str(recommendation_id),
                ),
            )
            self._event(
                self.connection,
                recommendation_id=str(recommendation_id),
                event_type="accepted",
                details=json.loads(str(applied_payload_json or "{}")),
                now=str(now),
            )
        return self.get_recommendation(str(recommendation_id))

    def mark_applied(
        self,
        recommendation_id: str,
        *,
        planner_task_id: str,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT * FROM assessment_recovery_recommendations WHERE id=?",
                (str(recommendation_id),),
            ).fetchone()
            if row is None:
                raise AssessmentRecoveryRepositoryNotFoundError(
                    "Recovery recommendation not found."
                )
            status = str(row["status"])
            if status == "applied":
                if str(row["planner_task_id"] or "") != str(planner_task_id):
                    raise AssessmentRecoveryRepositoryConflictError(
                        "Recommendation is already linked to a different planner task."
                    )
                return dict(row)
            if status != "accepted":
                raise AssessmentRecoveryRepositoryConflictError(
                    "Recommendation must be accepted before planner application."
                )

            self.connection.execute(
                "UPDATE assessment_recovery_recommendations SET "
                "status='applied', planner_task_id=?, applied_at=?, updated_at=?, "
                "revision=revision+1 WHERE id=? AND status='accepted'",
                (
                    str(planner_task_id),
                    str(now),
                    str(now),
                    str(recommendation_id),
                ),
            )
            self._event(
                self.connection,
                recommendation_id=str(recommendation_id),
                event_type="applied_to_planner",
                details={"planner_task_id": str(planner_task_id)},
                now=str(now),
            )
        return self.get_recommendation(str(recommendation_id))

    def reject(
        self,
        recommendation_id: str,
        *,
        expected_revision: int,
        reason: str,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT * FROM assessment_recovery_recommendations WHERE id=?",
                (str(recommendation_id),),
            ).fetchone()
            if row is None:
                raise AssessmentRecoveryRepositoryNotFoundError(
                    "Recovery recommendation not found."
                )
            status = str(row["status"])
            if status == "rejected":
                return dict(row)
            if status != "pending":
                raise AssessmentRecoveryRepositoryConflictError(
                    "Only a pending recommendation can be rejected."
                )
            if int(row["revision"]) != int(expected_revision):
                raise AssessmentRecoveryRepositoryConflictError(
                    "This recommendation changed. Refresh and review it again."
                )
            self.connection.execute(
                "UPDATE assessment_recovery_recommendations SET "
                "status='rejected', rejection_reason=?, rejected_at=?, updated_at=?, "
                "revision=revision+1 WHERE id=? AND status='pending'",
                (
                    str(reason or ""),
                    str(now),
                    str(now),
                    str(recommendation_id),
                ),
            )
            self._event(
                self.connection,
                recommendation_id=str(recommendation_id),
                event_type="rejected",
                details={"reason": str(reason or "")},
                now=str(now),
            )
        return self.get_recommendation(str(recommendation_id))

    def event_count(self, recommendation_id: str, event_type: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count "
            "FROM assessment_recovery_recommendation_events "
            "WHERE recommendation_id=? AND event_type=?",
            (str(recommendation_id), str(event_type)),
        ).fetchone()
        return int(row["count"]) if row is not None else 0
