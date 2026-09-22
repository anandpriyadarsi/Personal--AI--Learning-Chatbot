"""Typed Phase 6.2 grounded-tutor planning/result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Tuple

from personal_learning_assistant.domain.retrieval_models import RetrievalHit
from personal_learning_assistant.domain.tutor_models import TutorEvidence, TutorTurn


@dataclass(frozen=True)
class GroundingPlan:
    question: str
    mode: str
    source_policy: str
    context_text: str
    hits: Tuple[RetrievalHit, ...]
    evidence: Tuple[TutorEvidence, ...]
    messages: Tuple[Mapping[str, str], ...]
    retrieval_top_k: int
    context_max_chars: int
    teaching_intent: str = ""
    teaching_instruction: str = ""
    adaptive_state: Mapping[str, object] = field(default_factory=dict)
    retrieval_queries: Tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundedTutorResult:
    question: str
    user_turn: TutorTurn
    assistant_turn: TutorTurn
    citations: Tuple[str, ...]
    retrieved_chunk_ids: Tuple[str, ...]
    provider_request_id: str
