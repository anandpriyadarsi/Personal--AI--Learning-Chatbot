"""Phase 6.9 read-only unified Tutor Workspace CLI."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.adaptive_mentor_repository import (
    SQLiteAdaptiveMentorRepository,
)
from personal_learning_assistant.repositories.sqlite.exam_intelligence_repository import (
    SQLiteExamIntelligenceRepository,
)
from personal_learning_assistant.repositories.sqlite.knowledge_navigator_repository import (
    SQLiteKnowledgeNavigatorRepository,
)
from personal_learning_assistant.repositories.sqlite.tutor_workspace_repository import (
    SQLiteTutorWorkspaceRepository,
)
from personal_learning_assistant.services.adaptive_mentor_service import (
    AdaptiveMentorService,
)
from personal_learning_assistant.services.exam_intelligence_service import (
    ExamIntelligenceService,
)
from personal_learning_assistant.services.knowledge_navigator_service import (
    KnowledgeNavigatorService,
)
from personal_learning_assistant.services.tutor_workspace_service import (
    TutorWorkspaceService,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.9 read-only Tutor Workspace"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--course-code", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--target-assessment-id")
    parser.add_argument("--limit-topics", type=int, default=5)
    parser.add_argument("--max-actions", type=int, default=10)
    parser.add_argument("--recent-limit", type=int, default=12)
    return parser


def _uri(path: Path):
    return "file:{}?mode=ro".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    )


def _mentor(connection):
    return AdaptiveMentorService(
        navigator_service=KnowledgeNavigatorService(
            SQLiteKnowledgeNavigatorRepository(connection)
        ),
        exam_intelligence_service=ExamIntelligenceService(
            SQLiteExamIntelligenceRepository(connection)
        ),
        evidence_repository=SQLiteAdaptiveMentorRepository(connection),
    )


def _serialize(snapshot):
    return {
        "course_id": snapshot.course_id,
        "course_code": snapshot.course_code,
        "course_name": snapshot.course_name,
        "as_of": snapshot.as_of,
        "schema_versions": snapshot.schema_versions,
        "tutor_schema_ready": snapshot.tutor_schema_ready,
        "practice_schema_ready": snapshot.practice_schema_ready,
        "writes_performed": snapshot.writes_performed,
        "provider_called": snapshot.provider_called,
        "counts": snapshot.counts.__dict__,
        "recent_activity": [item.__dict__ for item in snapshot.recent_activity],
        "mentor": {
            "target_assessment_id": snapshot.mentor.target_assessment_id,
            "target_assessment_title": snapshot.mentor.target_assessment_title,
            "practice_history_available": (
                snapshot.mentor.practice_history_available
            ),
            "llm_called": snapshot.mentor.llm_called,
            "writes_performed": snapshot.mentor.writes_performed,
            "authoritative_state_changes": (
                snapshot.mentor.authoritative_state_changes
            ),
            "topics": [
                {
                    "topic_id": topic.topic_id,
                    "topic_name": topic.topic_name,
                    "status": topic.status,
                    "confidence": topic.confidence,
                    "combined_priority_score": topic.combined_priority_score,
                    "reasons": topic.reasons,
                }
                for topic in snapshot.mentor.topics
            ],
            "actions": [
                {
                    "sequence": action.sequence,
                    "action_type": action.action_type,
                    "topic_id": action.topic_id,
                    "topic_name": action.topic_name,
                    "title": action.title,
                    "priority_score": action.priority_score,
                    "reasons": action.reasons,
                    "resource_id": action.resource_id,
                    "question_id": action.question_id,
                    "assessment_id": action.assessment_id,
                    "source_labels": action.source_labels,
                    "advisory": action.advisory,
                }
                for action in snapshot.mentor.actions
            ],
        },
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    path = Path(args.database)
    if not path.is_file() or path.is_symlink():
        print("PHASE 6.9 TUTOR WORKSPACE: BLOCKED", file=sys.stderr)
        print("database is missing or not a regular file", file=sys.stderr)
        return 1

    connection = None
    try:
        as_of = date.today() if args.as_of is None else date.fromisoformat(args.as_of)
        connection = sqlite3.connect(
            _uri(path),
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        before = connection.total_changes

        service = TutorWorkspaceService(
            repository=SQLiteTutorWorkspaceRepository(connection),
            mentor_service=_mentor(connection),
        )
        snapshot = service.snapshot(
            args.course_code,
            as_of=as_of,
            target_assessment_id=args.target_assessment_id,
            limit_topics=args.limit_topics,
            max_actions=args.max_actions,
            recent_limit=args.recent_limit,
        )
        if connection.total_changes != before:
            raise RuntimeError("Tutor Workspace unexpectedly wrote SQLite state")

        print("PHASE 6.9 TUTOR WORKSPACE: PASS")
        print(json.dumps(_serialize(snapshot), indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        print("PHASE 6.9 TUTOR WORKSPACE: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
