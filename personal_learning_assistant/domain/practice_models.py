"""Typed Phase 6.5 Active Recall / Fast Quiz contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from personal_learning_assistant.domain.retrieval_models import RetrievalHit


@dataclass(frozen=True)
class PracticeQuizSpec:
    course_id: str
    topic_id: Optional[str] = None
    resource_id: Optional[str] = None
    tutor_session_id: Optional[str] = None
    mode: str = "fast_quiz"
    difficulty: str = "medium"
    item_count: int = 5
    focus: str = ""


@dataclass(frozen=True)
class PracticeItemDraft:
    item_type: str
    prompt: str
    options: Tuple[Mapping[str, str], ...]
    correct_option: str
    accepted_answers: Tuple[str, ...]
    explanation: str
    source_labels: Tuple[str, ...]


@dataclass(frozen=True)
class PracticeQuizPlan:
    spec: PracticeQuizSpec
    query: str
    context_text: str
    hits: Tuple[RetrievalHit, ...]
    evidence_labels: Tuple[str, ...]
    provider_messages: Tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class PracticeItemView:
    item_id: str
    ordinal: int
    item_type: str
    prompt: str
    options: Tuple[Mapping[str, str], ...]
    attempted: bool


@dataclass(frozen=True)
class PracticeQuizView:
    session_id: str
    course_id: str
    topic_id: Optional[str]
    resource_id: Optional[str]
    mode: str
    difficulty: str
    status: str
    source_query: str
    created_at: str
    items: Tuple[PracticeItemView, ...]


@dataclass(frozen=True)
class PracticeAttemptResult:
    attempt_id: str
    session_id: str
    item_id: str
    item_ordinal: int
    attempt_number: int
    outcome: str
    score_bps: Optional[int]
    grading_mode: str
    feedback: str
    self_confidence: Optional[int]
