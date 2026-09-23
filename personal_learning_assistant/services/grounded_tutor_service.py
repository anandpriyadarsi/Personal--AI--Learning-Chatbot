"""Phase 6.2 grounded academic tutor orchestration."""

from __future__ import annotations

import re

from personal_learning_assistant.domain.grounded_tutor_models import (
    GroundedTutorResult,
)
from personal_learning_assistant.domain.tutor_models import TutorProviderRequest
from personal_learning_assistant.tutor.adaptive_state import (
    STATE_KEY,
    evolve_adaptive_state,
    extract_answer_evaluation,
    mark_math_blocked,
)
from personal_learning_assistant.tutor.correctness import (
    MathVerification,
    extract_and_verify_math,
    required_claim_types,
    requires_deterministic_math,
    sanitize_correctness_prose,
)
from personal_learning_assistant.tutor.grounding import (
    TutorGroundingError,
    TutorGroundingPlanner,
)
from personal_learning_assistant.tutor.student_signals import (
    append_signal_history,
    derive_turn_signals,
)
from personal_learning_assistant.tutor.session_goal import (
    commit_session_goal,
)
from personal_learning_assistant.tutor.teaching_orchestrator import (
    commit_teaching_plan,
)


_CITATION = re.compile(r"\[(S[1-9][0-9]*)\]")


class GroundedTutorError(RuntimeError):
    pass


def _commit_orchestration_metadata(metadata, plan, *, now):
    payload = commit_session_goal(
        metadata,
        plan.session_goal,
        now=now,
    )
    return commit_teaching_plan(
        payload,
        plan.teaching_plan,
        now=now,
    )


_PROVIDER_META_LINE = re.compile(
    r"(?im)^\s*(?:user|response|prompt|content)?\s*safety\s*:\s*"
    r"(?:safe|unsafe|allowed|blocked|passed|ok)\s*$"
)


def _strip_provider_meta(content):
    raw = str(content or "")
    had_meta = bool(_PROVIDER_META_LINE.search(raw))
    clean = _PROVIDER_META_LINE.sub("", raw).strip()
    return clean, had_meta


def _provider_retry_request(request, raw_content):
    return TutorProviderRequest(
        session_id=request.session_id,
        mode=request.mode,
        source_policy=request.source_policy,
        messages=tuple(request.messages)
        + (
            {"role": "assistant", "content": str(raw_content or "")},
            {
                "role": "user",
                "content": (
                    "Your previous response contained provider/safety metadata instead of "
                    "the requested academic Tutor answer. Return only the complete "
                    "student-facing academic answer now. Do not print safety labels, "
                    "provider metadata, or internal moderation status."
                ),
            },
        ),
        metadata=dict(request.metadata or {}, provider_output_retry=True),
    )


def _enforce_required_math_verification(question, verification):
    required_types = required_claim_types(question)
    if requires_deterministic_math(question) and not verification.applicable:
        return MathVerification(
            applicable=True,
            passed=False,
            checked_claims=0,
            issues=(
                "explicit supported computation was requested but the response "
                "did not provide machine-checkable math claims",
            ),
            marker_present=False,
            claim_types=(),
        )
    if required_types:
        missing_types = tuple(
            claim_type
            for claim_type in required_types
            if claim_type not in set(verification.claim_types)
        )
        if missing_types:
            return MathVerification(
                applicable=True,
                passed=False,
                checked_claims=verification.checked_claims,
                issues=tuple(verification.issues)
                + (
                    "required verification claim type(s) missing: {}".format(
                        ", ".join(missing_types)
                    ),
                ),
                marker_present=verification.marker_present,
                claim_types=verification.claim_types,
            )
    return verification


def _process_provider_content(plan, raw_content):
    answer_evaluation = None
    content = str(raw_content or "").strip()
    if plan.teaching_intent == "quiz_answer":
        content, answer_evaluation = extract_answer_evaluation(content)
    content, math_verification = extract_and_verify_math(content)
    content = sanitize_correctness_prose(content)
    return content, answer_evaluation, math_verification


def _correctness_repair_request(request, raw_content, verification):
    issues = "; ".join(verification.issues) or "unknown verification failure"
    repair_message = (
        "ANVAYA's deterministic math verifier rejected the previous worked "
        "calculation. Correct the mathematical error and return the complete Tutor "
        "response again. Do not mention internal verification machinery. Preserve all "
        "original source/citation rules and all original hidden-metadata protocols. "
        "Verifier findings: {}"
    ).format(issues)
    return TutorProviderRequest(
        session_id=request.session_id,
        mode=request.mode,
        source_policy=request.source_policy,
        messages=tuple(request.messages)
        + (
            {"role": "assistant", "content": str(raw_content or "")},
            {"role": "user", "content": repair_message},
        ),
        metadata=dict(request.metadata or {}, correctness_repair=True),
    )


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
            try:
                metadata = _commit_orchestration_metadata(
                    session.metadata,
                    plan,
                    now=assistant_turn.created_at,
                )
                self.tutor_session_service.update_session_metadata(
                    session_id,
                    metadata,
                )
            except Exception:
                pass
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
        correctness_repaired = False
        raw_original = str(response.content or "").strip()
        raw_content, had_provider_meta = _strip_provider_meta(raw_original)

        if not raw_content and had_provider_meta:
            retry_request = _provider_retry_request(request, raw_original)
            retry_response = self.provider.complete(retry_request)
            retry_original = str(retry_response.content or "").strip()
            retry_clean, retry_had_meta = _strip_provider_meta(retry_original)
            if retry_clean:
                response = retry_response
                raw_content = retry_clean
            else:
                safe_content = (
                    "The Tutor provider did not return an academic answer for this turn. "
                    "Your study data was not changed. Please try the question again."
                )
                user_turn = self.tutor_session_service.add_user_turn(
                    session_id,
                    plan.question,
                )
                assistant_turn = self.tutor_session_service.add_assistant_turn(
                    session_id,
                    safe_content,
                    support_level="insufficient",
                    provider_name=str(retry_response.provider_name or ""),
                    provider_model=str(retry_response.provider_model or ""),
                )
                try:
                    metadata = _commit_orchestration_metadata(
                        session.metadata,
                        plan,
                        now=assistant_turn.created_at,
                    )
                    self.tutor_session_service.update_session_metadata(
                        session_id,
                        metadata,
                    )
                except Exception:
                    pass
                return GroundedTutorResult(
                    question=plan.question,
                    user_turn=user_turn,
                    assistant_turn=assistant_turn,
                    citations=(),
                    retrieved_chunk_ids=tuple(
                        item.chunk_id for item in plan.evidence
                    ),
                    provider_request_id=str(
                        retry_response.request_id or response.request_id or ""
                    ),
                )

        if not raw_content:
            raise GroundedTutorError("tutor provider returned an empty answer")

        content, answer_evaluation, math_verification = _process_provider_content(
            plan,
            raw_content,
        )
        math_verification = _enforce_required_math_verification(
            plan.question,
            math_verification,
        )
        if not content:
            raise GroundedTutorError(
                "tutor provider returned metadata without a visible answer"
            )

        if math_verification.applicable and not math_verification.passed:
            repair_request = _correctness_repair_request(
                request,
                raw_content,
                math_verification,
            )
            repaired_response = self.provider.complete(repair_request)
            repaired_raw = str(repaired_response.content or "").strip()
            if repaired_raw:
                (
                    repaired_content,
                    repaired_evaluation,
                    repaired_verification,
                ) = _process_provider_content(plan, repaired_raw)
                repaired_verification = _enforce_required_math_verification(
                    plan.question,
                    repaired_verification,
                )
            else:
                repaired_content = ""
                repaired_evaluation = None
                repaired_verification = math_verification

            if (
                repaired_content
                and repaired_verification.applicable
                and repaired_verification.passed
            ):
                response = repaired_response
                raw_content = repaired_raw
                content = repaired_content
                answer_evaluation = repaired_evaluation
                math_verification = repaired_verification
                correctness_repaired = True
            else:
                safe_content = (
                    "I caught an inconsistency in the worked calculation and did not "
                    "show it as a valid example. Please ask me to try the calculation "
                    "again; I will rebuild it from verified steps."
                )
                blocked_state = mark_math_blocked(
                    plan.adaptive_state,
                    student_message=plan.question,
                    teaching_intent=plan.teaching_intent,
                    checked_claims=repaired_verification.checked_claims,
                )
                user_turn = self.tutor_session_service.add_user_turn(
                    session_id,
                    plan.question,
                )
                assistant_turn = self.tutor_session_service.add_assistant_turn(
                    session_id,
                    safe_content,
                    support_level="insufficient",
                    provider_name=str(repaired_response.provider_name or ""),
                    provider_model=str(repaired_response.provider_model or ""),
                )
                blocked_metadata = dict(session.metadata or {})
                blocked_metadata[STATE_KEY] = blocked_state
                blocked_metadata = append_signal_history(
                    blocked_metadata,
                    derive_turn_signals(
                        session=session,
                        assistant_turn=assistant_turn,
                        teaching_intent=plan.teaching_intent,
                        adaptive_state=blocked_state,
                    ),
                )
                blocked_metadata = _commit_orchestration_metadata(
                    blocked_metadata,
                    plan,
                    now=assistant_turn.created_at,
                )
                try:
                    self.tutor_session_service.update_session_metadata(
                        session_id,
                        blocked_metadata,
                    )
                except Exception:
                    pass

                return GroundedTutorResult(
                    question=plan.question,
                    user_turn=user_turn,
                    assistant_turn=assistant_turn,
                    citations=(),
                    retrieved_chunk_ids=tuple(
                        item.chunk_id for item in plan.evidence
                    ),
                    provider_request_id=str(
                        repaired_response.request_id or response.request_id or ""
                    ),
                )

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
            # Existing Tutor schema uses "mixed" for source-first answers that
            # are not fully grounded in project evidence, including general-only fallback.
            support_level = "mixed"

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

        # Adaptive state is Tutor-session metadata only. It never mutates
        # mastery, grades, plans, notes, or global learning memory.
        next_state = evolve_adaptive_state(
            plan.adaptive_state,
            student_message=plan.question,
            assistant_message=content,
            teaching_intent=plan.teaching_intent,
            answer_evaluation=answer_evaluation,
            math_verification=math_verification,
            math_repaired=correctness_repaired,
        )
        metadata = dict(session.metadata or {})
        metadata[STATE_KEY] = next_state
        metadata = append_signal_history(
            metadata,
            derive_turn_signals(
                session=session,
                assistant_turn=assistant_turn,
                teaching_intent=plan.teaching_intent,
                adaptive_state=next_state,
            ),
        )
        metadata = _commit_orchestration_metadata(
            metadata,
            plan,
            now=assistant_turn.created_at,
        )
        try:
            self.tutor_session_service.update_session_metadata(
                session_id,
                metadata,
            )
        except Exception:
            # The tutoring exchange is already safely persisted. Adaptive state
            # is auxiliary and must not turn a valid answer into a 500 response.
            pass

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
