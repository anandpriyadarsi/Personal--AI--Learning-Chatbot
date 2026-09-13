"""Typed results for the Phase 2 academic-agent routing boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRoute:
    """View-neutral result of classifying one academic-agent request."""

    original_text: str
    normalized_text: str
    intent: str
    label: str

    @property
    def should_exit(self) -> bool:
        return self.intent == "BACK"

    @property
    def is_help(self) -> bool:
        return self.intent == "HELP"
