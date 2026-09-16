"""Phase 6.5 source-grounded Active Recall / Fast Quiz service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from personal_learning_assistant.domain.practice_models import (
    PracticeAttemptResult,
    PracticeItemView,
    PracticeQuizView,
)
from personal_learning_assistant.tutor.quiz_grounding import (
    build_generation_request,
    build_plan,
    parse_generated_items,
)


class PracticeQuizError(RuntimeError):
    pass


def _utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _new_id(prefix):
    return "{}-{}".format(prefix, uuid.uuid4())


def _norm_answer(value):
    return " ".join(str(value or "").strip().casefold().split())


class PracticeQuizService:
    def __init__(
        self,
        *,
        repository,
        retrieval_service,
        provider,
        now=_utc_now,
        id_factory=_new_id,
    ):
        self.repository = repository
        self.retrieval_service = retrieval_service
        self.provider = provider
        self._now = now
        self._id_factory = id_factory

    def _validate_scope(self, spec):
        if not self.repository.entity_exists("courses", spec.course_id):
            raise PracticeQuizError("practice course does not exist")
        if spec.topic_id:
            topic_course = self.repository.topic_course_id(spec.topic_id)
            if topic_course is None:
                raise PracticeQuizError("practice topic does not exist")
            if topic_course != spec.course_id:
                raise PracticeQuizError(
                    "practice topic does not belong to selected course"
                )
        if spec.resource_id:
            if not self.repository.entity_exists("resources", spec.resource_id):
                raise PracticeQuizError("practice resource does not exist")
            if not self.repository.resource_has_course(
                spec.resource_id, spec.course_id
            ):
                raise PracticeQuizError(
                    "practice resource is not linked to selected course"
                )
        if spec.tutor_session_id and not self.repository.entity_exists(
            "tutor_sessions", spec.tutor_session_id
        ):
            raise PracticeQuizError("linked tutor session does not exist")

    def preview(self, spec, *, top_k=10, max_chars=16000):
        self._validate_scope(spec)
        return build_plan(
            self.retrieval_service,
            spec,
            top_k=top_k,
            max_chars=max_chars,
        )

    def generate(self, spec, *, top_k=10, max_chars=16000):
        self._validate_scope(spec)
        plan = build_plan(
            self.retrieval_service,
            spec,
            top_k=top_k,
            max_chars=max_chars,
        )
        session_id = self._id_factory("practice-session")
        request = build_generation_request(session_id, plan)
        response = self.provider.complete(request)
        drafts = parse_generated_items(
            response.content,
            expected_count=spec.item_count,
            available_labels=plan.evidence_labels,
        )

        label_to_hit = {
            "S{}".format(i): hit
            for i, hit in enumerate(plan.hits, 1)
        }
        created_at = self._now()
        items = []
        for ordinal, draft in enumerate(drafts, 1):
            item_id = self._id_factory("practice-item")
            answer_key = {
                "correct_option": draft.correct_option,
                "accepted_answers": list(draft.accepted_answers),
            }
            sources = []
            for source_ordinal, label in enumerate(draft.source_labels, 1):
                hit = label_to_hit[label]
                sources.append(
                    {
                        "ordinal": source_ordinal,
                        "chunk_id": hit.chunk_id,
                        "document_id": hit.document_id,
                        "citation_label": label,
                    }
                )
            items.append(
                {
                    "id": item_id,
                    "ordinal": ordinal,
                    "item_type": draft.item_type,
                    "prompt": draft.prompt,
                    "options_json": json.dumps(
                        list(draft.options),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "answer_key_json": json.dumps(
                        answer_key,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "explanation": draft.explanation,
                    "sources": tuple(sources),
                }
            )

        self.repository.create_quiz(
            session_id=session_id,
            tutor_session_id=spec.tutor_session_id,
            course_id=spec.course_id,
            topic_id=spec.topic_id,
            resource_id=spec.resource_id,
            mode=spec.mode,
            difficulty=spec.difficulty,
            source_query=plan.query,
            requested_item_count=spec.item_count,
            generation_provider=str(response.provider_name or ""),
            generation_model=str(response.provider_model or ""),
            provider_request_id=str(response.request_id or ""),
            created_at=created_at,
            items=tuple(items),
            outbox_event_id=self._id_factory("outbox"),
        )
        return self.view(session_id)

    def view(self, session_id: str):
        session = self.repository.session(session_id)
        items = []
        for row in self.repository.items(session_id):
            options = json.loads(str(row["options_json"]))
            items.append(
                PracticeItemView(
                    item_id=str(row["id"]),
                    ordinal=int(row["ordinal"]),
                    item_type=str(row["item_type"]),
                    prompt=str(row["prompt"]),
                    options=tuple(options),
                    attempted=self.repository.attempt_count(str(row["id"])) > 0,
                )
            )
        return PracticeQuizView(
            session_id=str(session["id"]),
            course_id=str(session["course_id"]),
            topic_id=(
                None if session["topic_id"] is None else str(session["topic_id"])
            ),
            resource_id=(
                None
                if session["resource_id"] is None
                else str(session["resource_id"])
            ),
            mode=str(session["mode"]),
            difficulty=str(session["difficulty"]),
            status=str(session["status"]),
            source_query=str(session["source_query"]),
            created_at=str(session["created_at"]),
            items=tuple(items),
        )

    def submit(
        self,
        session_id: str,
        item_ordinal: int,
        response_text: str,
        *,
        self_confidence=None,
    ):
        response = str(response_text or "").strip()
        if not response:
            raise PracticeQuizError("practice response cannot be empty")
        if self_confidence is not None:
            self_confidence = int(self_confidence)
            if self_confidence < 0 or self_confidence > 5:
                raise PracticeQuizError("self_confidence must be between 0 and 5")

        item = self.repository.item_by_ordinal(session_id, int(item_ordinal))
        answer_key = json.loads(str(item["answer_key_json"]))
        item_type = str(item["item_type"])
        explanation = str(item["explanation"])

        if item_type == "single_choice":
            normalized = response.upper()
            if normalized not in {"A", "B", "C", "D"}:
                raise PracticeQuizError(
                    "single_choice response must be A, B, C or D"
                )
            correct = normalized == str(answer_key["correct_option"]).upper()
            outcome = "correct" if correct else "incorrect"
            score_bps = 10000 if correct else 0
            grading_mode = "deterministic"
            feedback = explanation
        elif item_type == "exact_recall":
            accepted = tuple(
                _norm_answer(value)
                for value in answer_key.get("accepted_answers", ())
            )
            correct = _norm_answer(response) in accepted
            outcome = "correct" if correct else "incorrect"
            score_bps = 10000 if correct else 0
            grading_mode = "deterministic"
            feedback = explanation
        elif item_type == "free_response":
            outcome = "advisory_ungraded"
            score_bps = None
            grading_mode = "advisory"
            feedback = (
                "This free response is intentionally not marked correct/incorrect "
                "by Phase 6.5. Compare it with the source-grounded reference: "
                + explanation
            )
        else:
            raise PracticeQuizError("unsupported persisted practice item type")

        attempt_id = self._id_factory("practice-attempt")
        occurred_at = self._now()
        attempt_number = self.repository.record_attempt(
            attempt_id=attempt_id,
            item_id=str(item["id"]),
            response_text=response,
            outcome=outcome,
            score_bps=score_bps,
            grading_mode=grading_mode,
            self_confidence=self_confidence,
            feedback=feedback,
            occurred_at=occurred_at,
            outbox_event_id=self._id_factory("outbox"),
        )
        return PracticeAttemptResult(
            attempt_id=attempt_id,
            session_id=session_id,
            item_id=str(item["id"]),
            item_ordinal=int(item["ordinal"]),
            attempt_number=attempt_number,
            outcome=outcome,
            score_bps=score_bps,
            grading_mode=grading_mode,
            feedback=feedback,
            self_confidence=self_confidence,
        )

    def finish(self, session_id: str):
        changed = self.repository.complete_session(
            session_id,
            completed_at=self._now(),
            outbox_event_id=self._id_factory("outbox"),
        )
        return self.view(session_id), changed
