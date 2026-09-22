"""Phase 6.2 grounded academic tutor orchestration."""

from __future__ import annotations

import re

from personal_learning_assistant.domain.grounded_tutor_models import (
    GroundedTutorResult,
)
from personal_learning_assistant.tutor.grounding import (
    TutorGroundingError,
    TutorGroundingPlanner,
)


_CITATION = re.compile(r"\[(S[1-9][0-9]*)\]")


class GroundedTutorError(RuntimeError):
    pass


class GroundedTutorService:
    """Retrieve -> prompt -> validate -> persist a grounded tutor exchange.

    Academic progress/memory/plans/resources are not written by this service.
    Only the Phase 6.1 tutor session/turn/evidence tables may be changed.
    """

    def __init__(
        self,
        *,
        tutor_session_service,
        retrieval_service,
        provider,
    ):
        self.tutor_session_service = tutor_session_service
        self.provider = provider
        self.planner = TutorGroundingPlanner(
            retrieval_service,
            tutor_session_service,
        )

    def preview(
        self,
        session_id,
        question,
        *,
        top_k=None,
        max_chars=None,
    ):
        session = self.tutor_session_service.repository.get_session(session_id)
        if session.status != "active":
            raise GroundedTutorError("tutor session is not active")
        transcript = self.tutor_session_service.transcript(session_id)
        return self.planner.plan(
            session,
            question,
            transcript=transcript,
            top_k=top_k,
            max_chars=max_chars,
        )

    def answer(
        self,
        session_id,
        question,
        *,
        top_k=None,
        max_chars=None,
    ):
        session = self.tutor_session_service.repository.get_session(session_id)
        if session.status != "active":
            raise GroundedTutorError("tutor session is not active")

        transcript = self.tutor_session_service.transcript(session_id)
        plan = self.planner.plan(
            session,
            question,
            transcript=transcript,
            top_k=top_k,
            max_chars=max_chars,
        )

        if not plan.evidence and session.source_policy == "source_only":
            user_turn = self.tutor_session_service.add_user_turn(
                session_id, plan.question
            )
            assistant_turn = self.tutor_session_service.add_assistant_turn(
                session_id,
                (
                    "I do not have enough project evidence to answer this "
                    "question within the current tutor scope."
                ),
                support_level="insufficient",
            )
            return GroundedTutorResult(
                question=plan.question,
                user_turn=user_turn,
                assistant_turn=assistant_turn,
                citations=(),
                retrieved_chunk_ids=(),
                provider_request_id="",
            )

        request = self.planner.provider_request(
            session,
            plan,
            transcript=transcript,
        )
        response = self.provider.complete(request)
        content = str(response.content or "").strip()
        if not content:
            raise GroundedTutorError("tutor provider returned an empty answer")

        available = {
            item.citation_label for item in plan.evidence
        }
        citations = tuple(dict.fromkeys(_CITATION.findall(content)))
        unsupported = tuple(
            label for label in citations if label not in available
        )
        if unsupported:
            raise GroundedTutorError(
                "provider cited unavailable evidence label(s): {}".format(
                    ", ".join(unsupported)
                )
            )

        if session.source_policy == "source_only":
            if not citations:
                raise GroundedTutorError(
                    "source_only answer must cite retrieved project evidence"
                )
            if "General explanation (not from project sources)" in content:
                raise GroundedTutorError(
                    "source_only answer attempted to include outside explanation"
                )
            support_level = "grounded"
        else:
            # Source-first may teach from general knowledge when retrieval is empty,
            # but it must never pretend that such an answer came from project files.
            support_level = "mixed" if plan.evidence else "general"

        user_turn = self.tutor_session_service.add_user_turn(
            session_id, plan.question
        )
        assistant_turn = self.tutor_session_service.add_assistant_turn(
            session_id,
            content,
            support_level=support_level,
            evidence=plan.evidence,
            provider_name=response.provider_name,
            provider_model=response.provider_model,
        )
        return GroundedTutorResult(
            question=plan.question,
            user_turn=user_turn,
            assistant_turn=assistant_turn,
            citations=citations,
            retrieved_chunk_ids=tuple(
                item.chunk_id for item in plan.evidence
            ),
            provider_request_id=str(response.request_id or ""),
        )
