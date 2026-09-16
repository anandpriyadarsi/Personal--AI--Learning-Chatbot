"""Phase 6.7 read-only Adaptive Mentor CLI."""

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
from personal_learning_assistant.services.adaptive_mentor_service import (
    AdaptiveMentorService,
)
from personal_learning_assistant.services.exam_intelligence_service import (
    ExamIntelligenceService,
)
from personal_learning_assistant.services.knowledge_navigator_service import (
    KnowledgeNavigatorService,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.7 deterministic read-only Adaptive Mentor"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--course-code", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--target-assessment-id")
    parser.add_argument("--limit-topics", type=int, default=5)
    parser.add_argument("--max-actions", type=int, default=10)
    return parser


def _uri(path: Path):
    return "file:{}?mode=ro".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    )


def _serialize(report):
    return {
        "course_id": report.course_id,
        "course_code": report.course_code,
        "course_name": report.course_name,
        "as_of": report.as_of,
        "target_assessment_id": report.target_assessment_id,
        "target_assessment_title": report.target_assessment_title,
        "practice_history_available": report.practice_history_available,
        "llm_called": report.llm_called,
        "writes_performed": report.writes_performed,
        "authoritative_state_changes": report.authoritative_state_changes,
        "topics": [
            {
                "topic_id": topic.topic_id,
                "topic_name": topic.topic_name,
                "status": topic.status,
                "confidence": topic.confidence,
                "navigator_priority_score": topic.navigator_priority_score,
                "exam_priority_score": topic.exam_priority_score,
                "combined_priority_score": topic.combined_priority_score,
                "unresolved_mistake_count": topic.unresolved_mistake_count,
                "active_memory_count": topic.active_memory_count,
                "upcoming_assessment_count": topic.upcoming_assessment_count,
                "target_assessment_in_scope": topic.target_assessment_in_scope,
                "practice": {
                    "available": topic.practice.available,
                    "session_count": topic.practice.session_count,
                    "completed_session_count": (
                        topic.practice.completed_session_count
                    ),
                    "deterministic_attempt_count": (
                        topic.practice.deterministic_attempt_count
                    ),
                    "correct_attempt_count": topic.practice.correct_attempt_count,
                    "incorrect_attempt_count": (
                        topic.practice.incorrect_attempt_count
                    ),
                    "advisory_attempt_count": topic.practice.advisory_attempt_count,
                    "deterministic_accuracy": (
                        None
                        if topic.practice.deterministic_accuracy is None
                        else round(topic.practice.deterministic_accuracy, 4)
                    ),
                    "latest_attempt_at": topic.practice.latest_attempt_at,
                },
                "reasons": topic.reasons,
            }
            for topic in report.topics
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
            for action in report.actions
        ],
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    path = Path(args.database)
    if not path.is_file() or path.is_symlink():
        print("PHASE 6.7 ADAPTIVE MENTOR: BLOCKED", file=sys.stderr)
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

        navigator = KnowledgeNavigatorService(
            SQLiteKnowledgeNavigatorRepository(connection)
        )
        exam = ExamIntelligenceService(
            SQLiteExamIntelligenceRepository(connection)
        )
        evidence = SQLiteAdaptiveMentorRepository(connection)
        report = AdaptiveMentorService(
            navigator_service=navigator,
            exam_intelligence_service=exam,
            evidence_repository=evidence,
        ).advise(
            args.course_code,
            as_of=as_of,
            target_assessment_id=args.target_assessment_id,
            limit_topics=args.limit_topics,
            max_actions=args.max_actions,
        )

        if connection.total_changes != before:
            raise RuntimeError("adaptive mentor unexpectedly wrote SQLite state")

        print("PHASE 6.7 ADAPTIVE MENTOR: PASS")
        print(json.dumps(_serialize(report), indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        print("PHASE 6.7 ADAPTIVE MENTOR: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
