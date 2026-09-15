"""Legacy JSON authority for Phase 4.5 attempts/mistakes/performance dual reads.

The V10.4 performance engine still persists through the existing question
workspace.  This adapter reuses the Phase 4.3 question-workspace repository so
Phase 4.5 can observe only the performance sub-domain without rewiring the
public ``assessment_performance.py`` API or changing the authoritative writer.
"""

from __future__ import annotations

from personal_learning_assistant.repositories.json.question_repository import (
    LegacyJsonQuestionRepository,
)


class LegacyJsonAttemptPerformanceRepository(LegacyJsonQuestionRepository):
    """Explicit legacy authority for ``data/assessment_workspace.json``."""


__all__ = ("LegacyJsonAttemptPerformanceRepository",)
