"""Phase 6.8 explicit Academic Agent Cutover."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from personal_learning_assistant.domain.academic_agent_models import (
    AcademicAgentActionPlan,
    AcademicAgentExecutionResult,
)
from personal_learning_assistant.domain.practice_models import PracticeQuizSpec
from personal_learning_assistant.domain.tutor_models import TutorSessionSpec


class AcademicAgentError(RuntimeError):
    pass


class AcademicAgentConfirmationError(AcademicAgentError):
    pass


class AcademicAgentStaleActionError(AcademicAgentError):
    pass


class AcademicAgentUnsupportedAction(AcademicAgentError):
    pass


CONFIRMATION_PHRASE = "EXECUTE_ACADEMIC_AGENT_ACTION"

_ROUTE = {
    "continue_lecture": ("lecture_learning", True, False),
    "review_note": ("note_handoff", False, False),
    "study_resource": ("resource_handoff", False, False),
    "grounded_tutor": ("tutor_session", True, False),
    "active_recall": ("practice_quiz", True, True),
    "solve_pyq": ("exam_tutor_session", True, False),
    "solve_formal_question": ("exam_tutor_session", True, False),
}


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _fingerprint(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _clean_review_title(title):
    text = str(title or "").strip()
    prefix = "Review "
    return text[len(prefix):].strip() if text.startswith(prefix) else text


class AcademicAgentService:
    """Turn one freshly-revalidated mentor recommendation into one permitted action.

    There is no autonomous loop. Every execution requires:
    1. an exact current mentor action sequence;
    2. the exact fingerprint returned by preview;
    3. the exact operator confirmation phrase.
    """

    def __init__(
        self,
        *,
        mentor_service,
        execution_repository,
        lecture_service=None,
        tutor_session_service=None,
        practice_service=None,
    ):
        self.mentor_service = mentor_service
        self.execution_repository = execution_repository
        self.lecture_service = lecture_service
        self.tutor_session_service = tutor_session_service
        self.practice_service = practice_service

    def plan(
        self,
        course_code: str,
        action_sequence: int,
        *,
        as_of=None,
        target_assessment_id=None,
        limit_topics=5,
        max_actions=10,
    ):
        as_of = as_of or date.today()
        report = self.mentor_service.advise(
            course_code,
            as_of=as_of,
            target_assessment_id=target_assessment_id,
            limit_topics=limit_topics,
            max_actions=max_actions,
        )
        action = next(
            (
                item
                for item in report.actions
                if int(item.sequence) == int(action_sequence)
            ),
            None,
        )
        if action is None:
            raise AcademicAgentError(
                "mentor action sequence {} is not currently available".format(
                    action_sequence
                )
            )
        if action.action_type not in _ROUTE:
            raise AcademicAgentUnsupportedAction(
                "mentor action type is not executable by Phase 6.8: {}".format(
                    action.action_type
                )
            )

        route, writes_expected, provider_expected = _ROUTE[action.action_type]
        note_id = None
        executable = True
        blocked_reason = ""
        if action.action_type == "review_note":
            row = self.execution_repository.resolve_note(
                action.topic_id,
                _clean_review_title(action.title),
            )
            if row is None:
                executable = False
                blocked_reason = (
                    "recommended note could not be resolved to one active note ID"
                )
            else:
                note_id = str(row["id"])
        if action.action_type in {"continue_lecture", "study_resource"}:
            if not action.resource_id:
                executable = False
                blocked_reason = (
                    "recommended resource action has no exact resource ID"
                )
        if action.action_type in {"solve_pyq", "solve_formal_question"}:
            if not action.question_id or not action.assessment_id:
                executable = False
                blocked_reason = (
                    "formal-question action lacks exact question/assessment identity"
                )

        fingerprint_payload = {
            "course_id": report.course_id,
            "course_code": report.course_code,
            "as_of": report.as_of,
            "target_assessment_id": report.target_assessment_id,
            "action_sequence": int(action.sequence),
            "action_type": action.action_type,
            "title": action.title,
            "topic_id": action.topic_id,
            "topic_name": action.topic_name,
            "priority_score": float(action.priority_score),
            "reasons": tuple(action.reasons),
            "resource_id": action.resource_id,
            "note_id": note_id,
            "question_id": action.question_id,
            "assessment_id": action.assessment_id,
            "source_labels": tuple(action.source_labels),
            "route": route,
        }
        return AcademicAgentActionPlan(
            course_id=report.course_id,
            course_code=report.course_code,
            as_of=report.as_of,
            target_assessment_id=report.target_assessment_id,
            action_sequence=int(action.sequence),
            action_type=action.action_type,
            title=action.title,
            topic_id=action.topic_id,
            topic_name=action.topic_name,
            priority_score=float(action.priority_score),
            reasons=tuple(action.reasons),
            resource_id=action.resource_id,
            note_id=note_id,
            question_id=action.question_id,
            assessment_id=action.assessment_id,
            source_labels=tuple(action.source_labels),
            route=route,
            fingerprint=_fingerprint(fingerprint_payload),
            confirmation_phrase=CONFIRMATION_PHRASE,
            writes_expected=writes_expected,
            provider_call_expected=provider_expected,
            executable=executable,
            blocked_reason=blocked_reason,
        )

    def execute(
        self,
        course_code: str,
        action_sequence: int,
        *,
        expected_fingerprint: str,
        confirmation: str,
        as_of=None,
        target_assessment_id=None,
        limit_topics=5,
        max_actions=10,
        practice_item_count=5,
        practice_difficulty="medium",
    ):
        if str(confirmation) != CONFIRMATION_PHRASE:
            raise AcademicAgentConfirmationError(
                "execution requires exact confirmation phrase {}".format(
                    CONFIRMATION_PHRASE
                )
            )

        current = self.plan(
            course_code,
            action_sequence,
            as_of=as_of,
            target_assessment_id=target_assessment_id,
            limit_topics=limit_topics,
            max_actions=max_actions,
        )
        if not current.executable:
            raise AcademicAgentError(
                "current mentor action is not executable: {}".format(
                    current.blocked_reason
                )
            )
        if str(expected_fingerprint).strip() != current.fingerprint:
            raise AcademicAgentStaleActionError(
                "mentor recommendation changed since preview; preview again "
                "and explicitly approve the new fingerprint"
            )

        if not current.writes_expected:
            return self._read_only_handoff(current)

        prior = self.execution_repository.prior_execution(current.fingerprint)
        if prior is not None:
            return AcademicAgentExecutionResult(
                fingerprint=current.fingerprint,
                action_type=current.action_type,
                route=current.route,
                status="already_executed",
                result_type=str(prior.get("result_type", "")),
                result_id=prior.get("result_id"),
                payload=dict(prior.get("payload") or {}),
                writes_performed=False,
                provider_called=bool(prior.get("provider_called", False)),
                already_executed=True,
            )

        journal_id = self.execution_repository.claim(current.fingerprint)
        try:
            result = self._dispatch(
                current,
                practice_item_count=practice_item_count,
                practice_difficulty=practice_difficulty,
            )
        except Exception:
            # Underlying Phase 6 mutation services are transaction-atomic.
            # Synchronous failure therefore releases the pre-action claim.
            # A process crash leaves 'planned' behind and intentionally blocks
            # blind retries.
            self.execution_repository.release_claim(journal_id)
            raise

        audit_payload = {
            "action_type": result.action_type,
            "route": result.route,
            "result_type": result.result_type,
            "result_id": result.result_id,
            "payload": dict(result.payload),
            "writes_performed": result.writes_performed,
            "provider_called": result.provider_called,
        }
        self.execution_repository.complete(
            journal_id,
            current.fingerprint,
            audit_payload,
        )
        return result

    def _read_only_handoff(self, plan):
        if plan.route == "note_handoff":
            payload = self.execution_repository.note_handoff(plan.note_id)
            result_type = "note"
            result_id = plan.note_id
        elif plan.route == "resource_handoff":
            payload = self.execution_repository.resource_handoff(plan.resource_id)
            result_type = "resource"
            result_id = plan.resource_id
        else:
            raise AcademicAgentUnsupportedAction(
                "unsupported read-only route: {}".format(plan.route)
            )
        return AcademicAgentExecutionResult(
            fingerprint=plan.fingerprint,
            action_type=plan.action_type,
            route=plan.route,
            status="handoff",
            result_type=result_type,
            result_id=result_id,
            payload=payload,
            writes_performed=False,
            provider_called=False,
            already_executed=False,
        )

    def _dispatch(self, plan, *, practice_item_count, practice_difficulty):
        if plan.route == "lecture_learning":
            if self.lecture_service is None:
                raise AcademicAgentError("lecture learning service is unavailable")
            snapshot = self.lecture_service.snapshot(plan.resource_id)
            if snapshot.next_action == "resume":
                result = self.lecture_service.resume(
                    plan.resource_id,
                    course_id=plan.course_id,
                    topic_id=plan.topic_id,
                    note="Started by approved Phase 6.8 mentor action.",
                )
                status = "executed"
            elif snapshot.next_action == "start":
                result = self.lecture_service.start(
                    plan.resource_id,
                    course_id=plan.course_id,
                    topic_id=plan.topic_id,
                    note="Started by approved Phase 6.8 mentor action.",
                )
                status = "executed"
            elif snapshot.next_action == "pause_or_checkpoint":
                return AcademicAgentExecutionResult(
                    fingerprint=plan.fingerprint,
                    action_type=plan.action_type,
                    route=plan.route,
                    status="already_active",
                    result_type="lecture_session",
                    result_id=snapshot.active_session_id,
                    payload={
                        "resource_id": plan.resource_id,
                        "current_position": snapshot.current_position,
                        "next_action": snapshot.next_action,
                    },
                    writes_performed=False,
                    provider_called=False,
                    already_executed=False,
                )
            else:
                raise AcademicAgentError(
                    "lecture recommendation is no longer startable/resumable"
                )
            return AcademicAgentExecutionResult(
                fingerprint=plan.fingerprint,
                action_type=plan.action_type,
                route=plan.route,
                status=status,
                result_type="lecture_session",
                result_id=result.segment_id,
                payload={
                    "resource_id": plan.resource_id,
                    "lecture_status": result.snapshot.status,
                    "current_position": result.snapshot.current_position,
                    "next_action": result.snapshot.next_action,
                },
                writes_performed=True,
                provider_called=False,
                already_executed=False,
            )

        if plan.route == "tutor_session":
            if self.tutor_session_service is None:
                raise AcademicAgentError("tutor session service is unavailable")
            session = self.tutor_session_service.create_session(
                TutorSessionSpec(
                    mode="concept",
                    source_policy="source_only",
                    course_id=plan.course_id,
                    topic_id=plan.topic_id,
                    title=plan.title,
                    metadata={
                        "origin": "phase6.8_academic_agent",
                        "agent_action_fingerprint": plan.fingerprint,
                        "mentor_action_sequence": plan.action_sequence,
                    },
                )
            )
            return AcademicAgentExecutionResult(
                fingerprint=plan.fingerprint,
                action_type=plan.action_type,
                route=plan.route,
                status="executed",
                result_type="tutor_session",
                result_id=session.session_id,
                payload={
                    "session_id": session.session_id,
                    "mode": session.mode,
                    "source_policy": session.source_policy,
                    "topic_id": session.topic_id,
                },
                writes_performed=True,
                provider_called=False,
                already_executed=False,
            )

        if plan.route == "exam_tutor_session":
            if self.tutor_session_service is None:
                raise AcademicAgentError("tutor session service is unavailable")
            session = self.tutor_session_service.create_session(
                TutorSessionSpec(
                    mode="exam",
                    source_policy="source_only",
                    course_id=plan.course_id,
                    topic_id=plan.topic_id,
                    assessment_id=plan.assessment_id,
                    title=plan.title,
                    metadata={
                        "origin": "phase6.8_academic_agent",
                        "agent_action_fingerprint": plan.fingerprint,
                        "mentor_action_sequence": plan.action_sequence,
                        "formal_question_id": plan.question_id,
                        "formal_source_labels": list(plan.source_labels),
                    },
                )
            )
            return AcademicAgentExecutionResult(
                fingerprint=plan.fingerprint,
                action_type=plan.action_type,
                route=plan.route,
                status="executed",
                result_type="tutor_session",
                result_id=session.session_id,
                payload={
                    "session_id": session.session_id,
                    "mode": session.mode,
                    "assessment_id": session.assessment_id,
                    "question_id": plan.question_id,
                    "source_labels": plan.source_labels,
                },
                writes_performed=True,
                provider_called=False,
                already_executed=False,
            )

        if plan.route == "practice_quiz":
            if self.practice_service is None:
                raise AcademicAgentError(
                    "practice service is unavailable; migration 0004 and "
                    "configured provider are required"
                )
            item_count = int(practice_item_count)
            if item_count < 1 or item_count > 20:
                raise AcademicAgentError(
                    "practice_item_count must be between 1 and 20"
                )
            difficulty = str(practice_difficulty or "").strip().casefold()
            if difficulty not in {"easy", "medium", "hard", "mixed"}:
                raise AcademicAgentError("unsupported practice difficulty")
            view = self.practice_service.generate(
                PracticeQuizSpec(
                    course_id=plan.course_id,
                    topic_id=plan.topic_id,
                    mode="active_recall",
                    difficulty=difficulty,
                    item_count=item_count,
                    focus="Active recall for {}".format(plan.topic_name),
                )
            )
            return AcademicAgentExecutionResult(
                fingerprint=plan.fingerprint,
                action_type=plan.action_type,
                route=plan.route,
                status="executed",
                result_type="practice_session",
                result_id=view.session_id,
                payload={
                    "session_id": view.session_id,
                    "mode": view.mode,
                    "difficulty": view.difficulty,
                    "item_count": len(view.items),
                    "topic_id": view.topic_id,
                },
                writes_performed=True,
                provider_called=True,
                already_executed=False,
            )

        raise AcademicAgentUnsupportedAction(
            "unsupported execution route: {}".format(plan.route)
        )
