"""Phase 6.9 unified read-only Tutor Workspace."""

from __future__ import annotations

from datetime import date

from personal_learning_assistant.domain.tutor_workspace_models import (
    TutorWorkspaceSnapshot,
)


class TutorWorkspaceError(RuntimeError):
    pass


class TutorWorkspaceService:
    def __init__(self, *, repository, mentor_service):
        self.repository = repository
        self.mentor_service = mentor_service

    def snapshot(
        self,
        course_code: str,
        *,
        as_of=None,
        target_assessment_id=None,
        limit_topics=5,
        max_actions=10,
        recent_limit=12,
    ):
        as_of = as_of or date.today()
        if int(limit_topics) <= 0 or int(max_actions) <= 0 or int(recent_limit) <= 0:
            raise TutorWorkspaceError("workspace limits must be positive")

        course = self.repository.course_by_code(course_code)
        course_id = str(course["id"])
        mentor = self.mentor_service.advise(
            course_code,
            as_of=as_of,
            target_assessment_id=target_assessment_id,
            limit_topics=limit_topics,
            max_actions=max_actions,
        )
        if mentor.course_id != course_id:
            raise TutorWorkspaceError(
                "workspace and mentor resolved different course identities"
            )

        versions = self.repository.schema_versions()
        return TutorWorkspaceSnapshot(
            course_id=course_id,
            course_code=str(course["code"]),
            course_name=str(course["name"]),
            as_of=as_of.isoformat(),
            schema_versions=versions,
            tutor_schema_ready=3 in versions,
            practice_schema_ready=4 in versions,
            counts=self.repository.counts(course_id),
            recent_activity=self.repository.recent_activity(
                course_id,
                limit=recent_limit,
            ),
            mentor=mentor,
            writes_performed=False,
            provider_called=False,
        )
