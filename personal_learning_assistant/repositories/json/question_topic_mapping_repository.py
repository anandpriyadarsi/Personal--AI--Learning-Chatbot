"""Legacy JSON authority for Phase 4.4 question-topic mapping dual reads.

The existing application still stores question topic decisions inside
``data/assessment_workspace.json`` and ``automatic_topic_mapping.py`` remains
unchanged.  This adapter deliberately reuses the Phase 4.3 workspace repository
shape so dual-read mode can return the exact legacy workspace while comparing
only the mapping sub-domain.
"""

from __future__ import annotations

from personal_learning_assistant.repositories.json.question_repository import (
    LegacyJsonQuestionRepository,
)


class LegacyJsonQuestionTopicMappingRepository(LegacyJsonQuestionRepository):
    """Explicit Phase 4.4 alias for the authoritative legacy workspace store."""


__all__ = ("LegacyJsonQuestionTopicMappingRepository",)
