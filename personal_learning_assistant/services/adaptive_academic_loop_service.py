"""Assessment Studio Phase F: Adaptive Academic Loop."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import config
from personal_learning_assistant.repositories.sqlite.assessment_recovery_repository import (
    AssessmentRecoveryRepositoryConflictError,
    AssessmentRecoveryRepositoryNotFoundError,
    AssessmentRecoveryRepositorySchemaError,
    SQLiteAssessmentRecoveryRepository,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.services.assessment_intelligence_service import (
    AssessmentIntelligenceService,
)
from personal_learning_assistant.services.operational_task_service import (
    OperationalTaskError,
    OperationalTaskService,
    OperationalTaskValidationError,
)
from personal_learning_assistant.repositories.sqlite.planner_task_repository import (
    SQLitePlannerTaskRepository,
)


EVIDENCE_VERSION = "assessment-intelligence-recovery-v1"
MAX_RECOMMENDATIONS = 8

_ACTIONS = {
    "evidence_check": {
        "minutes": 25,
        "label": "Verify with a short diagnostic",
        "steps": (
            ("diagnostic", "Attempt a short closed-book diagnostic before changing your study plan."),
            ("review", "Review only the questions you could not explain confidently."),
            ("retest", "Run a second short check after the review."),
        ),
    },
    "concept_rebuild": {
        "minutes": 60,
        "label": "Rebuild the concept",
        "steps": (
            ("notes", "Review the core note/source and write the main idea in your own words."),
            ("tutor", "Use Tutor/Alex only after an independent explanation attempt."),
            ("worked_examples", "Study two worked examples and explain why each step is valid."),
            ("easy_practice", "Solve a small easy set without looking at the solution."),
            ("retest", "Finish with a closed-book recovery test."),
        ),
    },
    "procedure_rebuild": {
        "minutes": 60,
        "label": "Rebuild the procedure",
        "steps": (
            ("worked_example", "Trace one correct worked solution step by step."),
            ("guided_practice", "Solve one similar problem with hints only when blocked."),
            ("independent_practice", "Solve two problems independently from blank."),
            ("timed_practice", "Repeat one familiar problem under a moderate time limit."),
            ("retest", "Check the method again with a fresh question."),
        ),
    },
    "recall_rebuild": {
        "minutes": 40,
        "label": "Rebuild formula recall",
        "steps": (
            ("formula_review", "Create a minimal formula/condition sheet from memory first."),
            ("closed_book_recall", "Recall definitions, conditions and formulas without notes."),
            ("application_drill", "Use each recalled formula in one short problem."),
            ("retest", "Run a short no-notes recall check."),
        ),
    },
    "accuracy_rebuild": {
        "minutes": 35,
        "label": "Rebuild answer accuracy",
        "steps": (
            ("error_checklist", "Write a three-item pre-submit checking routine for this topic."),
            ("untimed_accuracy", "Solve a short set slowly with zero avoidable errors as the goal."),
            ("timed_accuracy", "Repeat with a realistic time limit while keeping the checklist."),
            ("retest", "Take a short accuracy-focused retest."),
        ),
    },
    "speed_rebuild": {
        "minutes": 45,
        "label": "Build speed safely",
        "steps": (
            ("familiar_drill", "Solve familiar questions accurately before adding time pressure."),
            ("progressive_timing", "Reduce the time limit gradually across similar questions."),
            ("simulation", "Run a short timed section with normal exam navigation."),
            ("retest", "Retest speed and accuracy together."),
        ),
    },
    "reasoning_rebuild": {
        "minutes": 60,
        "label": "Rebuild reasoning",
        "steps": (
            ("model_reasoning", "Read one strong model solution/proof and identify its structure."),
            ("reconstruct", "Close the solution and reconstruct the reasoning from memory."),
            ("compare", "Compare your reconstruction against the model and mark missing logic."),
            ("independent_reasoning", "Write a fresh solution/proof without support."),
            ("retest", "Use a new reasoning question as the exit check."),
        ),
    },
}

_MISTAKE_TO_FAMILY = {
    "concept_gap": "concept_rebuild",
    "wrong_method": "procedure_rebuild",
    "calculation_error": "procedure_rebuild",
    "formula_recall": "recall_rebuild",
    "careless": "accuracy_rebuild",
    "misread": "accuracy_rebuild",
    "guessing": "accuracy_rebuild",
    "time_pressure": "speed_rebuild",
    "incomplete_reasoning": "reasoning_rebuild",
}


class AdaptiveAcademicLoopError(RuntimeError):
    pass


class AdaptiveAcademicLoopValidationError(AdaptiveAcademicLoopError):
    pass


class AdaptiveAcademicLoopNotFoundError(AdaptiveAcademicLoopError):
    pass


class AdaptiveAcademicLoopConflictError(AdaptiveAcademicLoopError):
    pass


class AdaptiveAcademicLoopUnavailableError(AdaptiveAcademicLoopError):
    pass


def _now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _safe_json(raw, fallback):
    try:
        value = json.loads(str(raw or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback
    return value


def _fingerprint(evidence):
    payload = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _priority(topic):
    questions = int(topic.get("question_count") or 0)
    mistakes = int(topic.get("mistake_count") or 0)
    performance = topic.get("weighted_performance_percent")
    if questions >= 2 and performance is not None and float(performance) < 40:
        return "P0"
    if mistakes >= 3:
        return "P0"
    if questions >= 2 and performance is not None and float(performance) < 70:
        return "P1"
    if mistakes:
        return "P1"
    return "P2"


def _dominant_family(topic):
    if int(topic.get("question_count") or 0) < 2:
        return "evidence_check"
    categories = []
    for item in topic.get("mistake_categories") or ():
        categories.append(
            (
                -int(item.get("count") or 0),
                str(item.get("category") or ""),
            )
        )
    for _negative_count, category in sorted(categories):
        family = _MISTAKE_TO_FAMILY.get(category)
        if family:
            return family
    performance = topic.get("weighted_performance_percent")
    if performance is not None and float(performance) < 60:
        return "concept_rebuild"
    if int(topic.get("partial_count") or 0) >= 2:
        return "reasoning_rebuild"
    return "evidence_check"


def _evidence_snapshot(topic):
    return {
        "version": EVIDENCE_VERSION,
        "course_id": str(topic.get("course_id") or ""),
        "course_code": str(topic.get("course_code") or ""),
        "course_name": str(topic.get("course_name") or ""),
        "topic_id": str(topic.get("topic_id") or ""),
        "topic_label": str(topic.get("label") or ""),
        "recovery_order": int(topic.get("recovery_order") or 0),
        "question_count": int(topic.get("question_count") or 0),
        "session_count": int(topic.get("session_count") or 0),
        "weighted_performance_percent": topic.get("weighted_performance_percent"),
        "full_accuracy_percent": topic.get("full_accuracy_percent"),
        "correct_count": int(topic.get("correct_count") or 0),
        "partial_count": int(topic.get("partial_count") or 0),
        "incorrect_count": int(topic.get("incorrect_count") or 0),
        "unanswered_count": int(topic.get("unanswered_count") or 0),
        "mistake_count": int(topic.get("mistake_count") or 0),
        "mistake_categories": [
            {
                "category": str(item.get("category") or ""),
                "count": int(item.get("count") or 0),
            }
            for item in topic.get("mistake_categories") or ()
        ],
        "time_per_available_mark_seconds": topic.get(
            "time_per_available_mark_seconds"
        ),
        "recovery_signals": list(topic.get("recovery_signals") or ()),
    }


def _candidate(topic):
    evidence = _evidence_snapshot(topic)
    family = _dominant_family(topic)
    action = _ACTIONS[family]
    topic_label = evidence["topic_label"] or "Unmapped topic"
    course_code = evidence["course_code"] or "Course"
    priority = _priority(topic)
    action_plan = [
        {"kind": kind, "instruction": instruction}
        for kind, instruction in action["steps"]
    ]
    evidence_json = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = _fingerprint(evidence)
    summary = (
        "{} confirmed question(s), {} session(s), {} weighted marks performance, "
        "{} confirmed mistake(s)."
    ).format(
        evidence["question_count"],
        evidence["session_count"],
        (
            "{}%".format(evidence["weighted_performance_percent"])
            if evidence["weighted_performance_percent"] is not None
            else "no percentage"
        ),
        evidence["mistake_count"],
    )
    step_text = " ".join(
        "{}. {}".format(index, item["instruction"])
        for index, item in enumerate(action_plan, start=1)
    )
    description = (
        "Assessment Studio recovery recommendation for {} · {}. "
        "Evidence: {} Plan: {}"
    ).format(course_code, topic_label, summary, step_text)
    alex_prompt = (
        "Act as my academic tutor for {course} topic '{topic}'. "
        "Use this confirmed ANVAYA assessment evidence: {summary} "
        "Guide me through this recovery sequence without giving final answers "
        "before I attempt them: {steps} Finish with a short closed-book exit "
        "check and tell me whether I can explain the topic from blank."
    ).format(
        course=course_code,
        topic=topic_label,
        summary=summary,
        steps=step_text,
    )
    return {
        "id": str(uuid.uuid4()),
        "evidence_fingerprint": fingerprint,
        "course_id": evidence["course_id"],
        "course_code": evidence["course_code"],
        "course_name": evidence["course_name"],
        "topic_id": evidence["topic_id"],
        "topic_label": topic_label,
        "evidence_version": EVIDENCE_VERSION,
        "evidence": evidence,
        "evidence_json": evidence_json,
        "action_family": family,
        "action_label": action["label"],
        "action_plan": tuple(action_plan),
        "action_plan_json": json.dumps(
            action_plan,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "alex_prompt": alex_prompt,
        "suggested_title": "Recovery: {} — {}".format(
            topic_label, action["label"]
        ),
        "suggested_description": description,
        "suggested_priority": priority,
        "suggested_minutes": int(action["minutes"]),
    }


class AdaptiveAcademicLoopService:
    def __init__(
        self,
        database_path,
        *,
        intelligence_service=None,
        task_service=None,
        now_fn=_now,
    ):
        self.database_path = Path(database_path)
        self.intelligence = intelligence_service or AssessmentIntelligenceService(
            self.database_path
        )
        self.tasks = task_service or OperationalTaskService(
            SQLitePlannerTaskRepository(self.database_path)
        )
        self._now = now_fn

    @contextmanager
    def _repository(self, *, write: bool):
        path = self.database_path
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise AdaptiveAcademicLoopUnavailableError(
                "The authoritative SQLite database is unavailable."
            )
        try:
            if write:
                connection = connect_database(path, synchronous="FULL")
            else:
                uri = "file:{}?mode=ro".format(
                    quote(path.resolve().as_posix(), safe="/:")
                )
                connection = sqlite3.connect(uri, uri=True, isolation_level=None)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA busy_timeout = 5000")
            try:
                yield SQLiteAssessmentRecoveryRepository(connection)
            finally:
                connection.close()
        except AdaptiveAcademicLoopError:
            raise
        except AssessmentRecoveryRepositorySchemaError as error:
            raise AdaptiveAcademicLoopUnavailableError(
                "Assessment Studio Phase F migration 0013 has not been applied."
            ) from error
        except sqlite3.Error as error:
            raise AdaptiveAcademicLoopUnavailableError(
                "Adaptive Academic Loop storage is unavailable."
            ) from error

    @staticmethod
    def _translate(error):
        if isinstance(error, AssessmentRecoveryRepositoryNotFoundError):
            raise AdaptiveAcademicLoopNotFoundError(str(error)) from error
        if isinstance(error, AssessmentRecoveryRepositoryConflictError):
            raise AdaptiveAcademicLoopConflictError(str(error)) from error
        raise error

    def preview(self, *, limit=MAX_RECOMMENDATIONS, course_id=""):
        report = self.intelligence.weak_topics()
        topics = tuple(item for item in report.get("topics") or ()
                       if not course_id or str(item.get("course_id")) == str(course_id))
        candidates = tuple(
            _candidate(topic)
            for topic in topics[: max(1, min(int(limit), MAX_RECOMMENDATIONS))]
            if str(topic.get("course_id") or "")
        )
        return {
            "available": True,
            "has_evidence": bool(candidates),
            "candidates": candidates,
            "source_note": str(report.get("note") or ""),
        }

    @staticmethod
    def _decorate_saved(row):
        item = dict(row)
        item["evidence"] = _safe_json(item.get("evidence_json"), {})
        action_plan = _safe_json(item.get("action_plan_json"), [])
        item["action_plan"] = tuple(
            step for step in action_plan if isinstance(step, dict)
        )
        item["applied_payload"] = _safe_json(
            item.get("applied_payload_json"), {}
        )
        item["status_label"] = str(item.get("status") or "").replace("_", " ").title()
        item["action_label"] = _ACTIONS.get(
            str(item.get("action_family")),
            {"label": str(item.get("action_family") or "").replace("_", " ").title()},
        )["label"]
        return item

    def workspace(self, course_id=""):
        course_id = str(course_id or "").strip()
        preview = self.preview(course_id=course_id)
        with self._repository(write=False) as repository:
            saved = tuple(
                self._decorate_saved(row)
                for row in repository.list_recommendations()
                if not course_id or str(row.get("course_id")) == course_id
            )
            courses = repository.list_courses()
        pending = tuple(item for item in saved if item["status"] == "pending")
        accepted = tuple(item for item in saved if item["status"] == "accepted")
        applied = tuple(item for item in saved if item["status"] == "applied")
        rejected = tuple(item for item in saved if item["status"] == "rejected")
        superseded = tuple(item for item in saved if item["status"] == "superseded")
        return {
            **preview,
            "courses": courses,
            "selected_course_id": course_id,
            "selected_course": next((course for course in courses if course["id"] == course_id), None),
            "saved": saved,
            "pending": pending,
            "accepted": accepted,
            "applied": applied,
            "rejected": rejected,
            "superseded": superseded,
            "summary": {
                "pending": len(pending),
                "accepted": len(accepted),
                "applied": len(applied),
                "rejected": len(rejected),
            },
        }

    def generate(self, fingerprints, *, course_id=""):
        requested = {
            str(value).strip()
            for value in fingerprints or ()
            if str(value).strip()
        }
        if not requested:
            raise AdaptiveAcademicLoopValidationError(
                "Select at least one evidence recommendation to generate."
            )
        preview = self.preview(course_id=course_id)
        by_fingerprint = {
            item["evidence_fingerprint"]: item
            for item in preview["candidates"]
        }
        unknown = requested - set(by_fingerprint)
        if unknown:
            raise AdaptiveAcademicLoopConflictError(
                "Assessment evidence changed. Refresh and review the recommendations again."
            )

        results = []
        now = self._now()
        try:
            with self._repository(write=True) as repository:
                for fingerprint in sorted(requested):
                    results.append(
                        repository.persist_candidate(
                            by_fingerprint[fingerprint],
                            now=now,
                        )
                    )
        except (
            AssessmentRecoveryRepositoryNotFoundError,
            AssessmentRecoveryRepositoryConflictError,
        ) as error:
            self._translate(error)
        return {
            "created_count": sum(1 for item in results if item["created"]),
            "existing_count": sum(1 for item in results if not item["created"]),
            "results": tuple(results),
        }

    def recommendation(self, recommendation_id):
        with self._repository(write=False) as repository:
            row = repository.get_recommendation(str(recommendation_id))
        if row is None:
            raise AdaptiveAcademicLoopNotFoundError(
                "Recovery recommendation not found."
            )
        return self._decorate_saved(row)

    @staticmethod
    def _revision(value):
        try:
            revision = int(value)
        except (TypeError, ValueError) as error:
            raise AdaptiveAcademicLoopValidationError(
                "Recommendation revision is invalid."
            ) from error
        if revision <= 0:
            raise AdaptiveAcademicLoopValidationError(
                "Recommendation revision is invalid."
            )
        return revision

    def apply(self, recommendation_id, payload):
        current = self.recommendation(recommendation_id)
        if current["status"] not in {"pending", "accepted", "applied"}:
            raise AdaptiveAcademicLoopConflictError(
                "This recommendation can no longer be applied."
            )
        if current["status"] == "applied":
            return current

        expected_revision = self._revision(
            payload.get("revision", current["revision"])
        )
        title = str(payload.get("title") or current["suggested_title"]).strip()
        description = str(
            payload.get("description") or current["suggested_description"]
        ).strip()
        priority = str(
            payload.get("priority") or current["suggested_priority"]
        ).strip().upper()
        minutes = payload.get(
            "estimated_minutes",
            current["suggested_minutes"],
        )
        due_on = str(payload.get("due_on") or "").strip()

        applied_payload = {
            "title": title,
            "description": description,
            "priority": priority,
            "estimated_minutes": minutes,
            "due_on": due_on,
            "course_id": current["course_id"],
            "topic_id": current.get("topic_id") or None,
        }
        applied_json = json.dumps(
            applied_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        if current["status"] == "pending":
            try:
                with self._repository(write=True) as repository:
                    current = self._decorate_saved(
                        repository.accept(
                            str(recommendation_id),
                            expected_revision=expected_revision,
                            applied_payload_json=applied_json,
                            now=self._now(),
                        )
                    )
            except (
                AssessmentRecoveryRepositoryNotFoundError,
                AssessmentRecoveryRepositoryConflictError,
            ) as error:
                self._translate(error)
        else:
            stored = current.get("applied_payload") or {}
            if stored:
                applied_payload = dict(stored)

        try:
            task = self.tasks.create_assessment_recovery_task(
                str(recommendation_id),
                title=applied_payload["title"],
                description=applied_payload.get("description", ""),
                priority=applied_payload.get("priority", "P1"),
                estimated_minutes=applied_payload.get("estimated_minutes"),
                due_on=applied_payload.get("due_on") or None,
                course_id=applied_payload.get("course_id") or None,
                topic_id=applied_payload.get("topic_id") or None,
            )
        except OperationalTaskValidationError as error:
            raise AdaptiveAcademicLoopValidationError(str(error)) from error
        except OperationalTaskError as error:
            raise AdaptiveAcademicLoopUnavailableError(
                "The recommendation was accepted, but planner application is pending. "
                "Retry Apply to resume safely."
            ) from error

        try:
            with self._repository(write=True) as repository:
                row = repository.mark_applied(
                    str(recommendation_id),
                    planner_task_id=str(task["id"]),
                    now=self._now(),
                )
        except (
            AssessmentRecoveryRepositoryNotFoundError,
            AssessmentRecoveryRepositoryConflictError,
        ) as error:
            self._translate(error)
        result = self._decorate_saved(row)
        result["planner_task"] = dict(task)
        return result

    def reject(self, recommendation_id, *, revision, reason=""):
        reason = str(reason or "").strip()
        if len(reason) > 1000:
            raise AdaptiveAcademicLoopValidationError(
                "Rejection note is too long."
            )
        try:
            with self._repository(write=True) as repository:
                row = repository.reject(
                    str(recommendation_id),
                    expected_revision=self._revision(revision),
                    reason=reason,
                    now=self._now(),
                )
        except (
            AssessmentRecoveryRepositoryNotFoundError,
            AssessmentRecoveryRepositoryConflictError,
        ) as error:
            self._translate(error)
        return self._decorate_saved(row)


def build_adaptive_academic_loop_service(database_path=None):
    path = database_path or config.DATABASE_PATH
    return AdaptiveAcademicLoopService(path)
