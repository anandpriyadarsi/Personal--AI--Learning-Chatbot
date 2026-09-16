"""Phase 6.1 tutor session and evidence orchestration.

This service writes only tutor_sessions/tutor_turns/tutor_evidence_links/
tutor_feedback. It never mutates learning progress, learning memory, resources,
study plans, grades, assessments, notes, or source documents.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Iterable, Sequence

from personal_learning_assistant.domain.tutor_models import (
    EVIDENCE_RELATIONS,
    SESSION_STATUSES,
    SUPPORT_LEVELS,
    TutorEvidence,
    TutorSessionSpec,
)
from personal_learning_assistant.tutor.policy import (
    get_mode_policy,
    validate_source_policy,
)


class TutorSessionError(RuntimeError):
    pass


def _utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _new_id(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4())


class TutorSessionService:
    def __init__(self, repository, *, now=_utc_now, id_factory=_new_id):
        self.repository = repository
        self._now = now
        self._id_factory = id_factory

    def create_session(self, spec: TutorSessionSpec):
        policy = get_mode_policy(spec.mode)
        source_policy = validate_source_policy(spec.source_policy)

        if spec.course_id and not self.repository.entity_exists(
            "courses", spec.course_id
        ):
            raise TutorSessionError("course does not exist")
        if spec.topic_id:
            topic_course = self.repository.topic_course_id(spec.topic_id)
            if topic_course is None:
                raise TutorSessionError("topic does not exist")
            if spec.course_id and topic_course != spec.course_id:
                raise TutorSessionError("topic does not belong to selected course")
        if spec.assessment_id:
            assessment_course = self.repository.assessment_course_id(
                spec.assessment_id
            )
            if assessment_course is None:
                raise TutorSessionError("assessment does not exist")
            if spec.course_id and assessment_course != spec.course_id:
                raise TutorSessionError(
                    "assessment does not belong to selected course"
                )
        if spec.resource_id:
            if not self.repository.entity_exists("resources", spec.resource_id):
                raise TutorSessionError("resource does not exist")
            if spec.course_id and not self.repository.resource_has_course(
                spec.resource_id, spec.course_id
            ):
                raise TutorSessionError(
                    "resource is not related to selected course"
                )

        try:
            metadata_json = json.dumps(
                dict(spec.metadata),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as error:
            raise TutorSessionError("session metadata must be JSON-serializable") from error

        now = self._now()
        return self.repository.create_session(
            session_id=self._id_factory("tutor-session"),
            course_id=spec.course_id,
            topic_id=spec.topic_id,
            assessment_id=spec.assessment_id,
            resource_id=spec.resource_id,
            mode=policy.mode,
            source_policy=source_policy,
            title=str(spec.title or "").strip(),
            metadata_json=metadata_json,
            created_at=now,
        )

    def add_user_turn(self, session_id: str, content: str):
        clean = str(content or "").strip()
        if not clean:
            raise TutorSessionError("user turn content cannot be empty")
        return self.repository.add_turn(
            turn_id=self._id_factory("tutor-turn"),
            session_id=session_id,
            role="user",
            content=clean,
            support_level="not_evaluated",
            provider_name="",
            provider_model="",
            created_at=self._now(),
            evidence=(),
        )

    def evidence_from_retrieval_hits(self, hits, *, relation_type="support"):
        if relation_type not in EVIDENCE_RELATIONS:
            raise TutorSessionError("unsupported evidence relation")
        result = []
        for rank, hit in enumerate(hits, 1):
            result.append(
                TutorEvidence(
                    chunk_id=str(hit.chunk_id),
                    document_id=str(hit.document_id),
                    ordinal=rank,
                    relation_type=relation_type,
                    retrieval_score=float(hit.score),
                    citation_label="S{}".format(rank),
                )
            )
        return tuple(result)

    def add_assistant_turn(
        self,
        session_id: str,
        content: str,
        *,
        support_level: str,
        evidence: Sequence[TutorEvidence] = (),
        provider_name: str = "",
        provider_model: str = "",
    ):
        clean = str(content or "").strip()
        if not clean:
            raise TutorSessionError("assistant turn content cannot be empty")
        level = str(support_level or "").strip().casefold()
        if level not in SUPPORT_LEVELS or level == "not_evaluated":
            raise TutorSessionError("invalid assistant support level")
        if level in {"grounded", "mixed"} and not evidence:
            raise TutorSessionError(
                "{} assistant turn requires evidence".format(level)
            )

        expected = list(range(1, len(evidence) + 1))
        actual = [int(item.ordinal) for item in evidence]
        if actual != expected:
            raise TutorSessionError(
                "evidence ordinals must be contiguous starting at 1"
            )
        for item in evidence:
            if item.relation_type not in EVIDENCE_RELATIONS:
                raise TutorSessionError("unsupported evidence relation")
            if not str(item.citation_label or "").strip():
                raise TutorSessionError("evidence citation label cannot be empty")

        return self.repository.add_turn(
            turn_id=self._id_factory("tutor-turn"),
            session_id=session_id,
            role="assistant",
            content=clean,
            support_level=level,
            provider_name=str(provider_name or "").strip(),
            provider_model=str(provider_model or "").strip(),
            created_at=self._now(),
            evidence=tuple(evidence),
        )

    def complete_session(self, session_id: str):
        return self.repository.set_session_status(
            session_id, "completed", self._now()
        )

    def abandon_session(self, session_id: str):
        return self.repository.set_session_status(
            session_id, "abandoned", self._now()
        )

    def transcript(self, session_id: str):
        self.repository.get_session(session_id)
        return self.repository.list_turns(session_id)

    def record_feedback(
        self,
        turn_id: str,
        *,
        rating=None,
        helpful=None,
        feedback_text="",
    ):
        if rating is not None:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise TutorSessionError("feedback rating must be between 1 and 5")
        text = str(feedback_text or "").strip()
        if rating is None and helpful is None and not text:
            raise TutorSessionError("feedback must contain rating/helpful/text")
        return self.repository.add_feedback(
            feedback_id=self._id_factory("tutor-feedback"),
            turn_id=turn_id,
            rating=rating,
            helpful=helpful,
            feedback_text=text,
            created_at=self._now(),
        )
