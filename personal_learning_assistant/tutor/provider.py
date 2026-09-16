"""LLM provider boundary for Phase 6.

Phase 6.1 defines the contract only. No network-backed provider is wired yet.
"""

from __future__ import annotations

from typing import Protocol

from personal_learning_assistant.domain.tutor_models import (
    TutorProviderRequest,
    TutorProviderResponse,
)


class TutorProvider(Protocol):
    def complete(self, request: TutorProviderRequest) -> TutorProviderResponse:
        ...


class TutorProviderUnavailableError(RuntimeError):
    pass


class DisabledTutorProvider:
    """Fail-closed provider used until Phase 6.2 wires grounded generation."""

    def complete(self, request: TutorProviderRequest) -> TutorProviderResponse:
        raise TutorProviderUnavailableError(
            "Tutor answer generation is not enabled in Phase 6.1. "
            "Phase 6.1 provides session/evidence infrastructure only."
        )
