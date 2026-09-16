"""Read-only operator CLI for Phase 6.3 Knowledge Navigator."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.knowledge_navigator_repository import (
    SQLiteKnowledgeNavigatorRepository,
)
from personal_learning_assistant.services.knowledge_navigator_service import (
    KnowledgeNavigatorService,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.3 explainable read-only study navigator"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--course-code", required=True)
    parser.add_argument("--topic")
    parser.add_argument("--as-of")
    parser.add_argument("--limit-topics", type=int, default=5)
    parser.add_argument("--limit-sources", type=int, default=5)
    return parser


def _uri(path: Path):
    return "file:{}?mode=ro".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    )


def _serialize(result):
    return {
        "course_id": result.course_id,
        "course_code": result.course_code,
        "course_name": result.course_name,
        "as_of": result.as_of,
        "focused_topic_id": result.focused_topic_id,
        "topic_count": result.topic_count,
        "writes_performed": result.writes_performed,
        "topics": [
            {
                "topic_id": topic.topic_id,
                "topic_name": topic.topic_name,
                "status": topic.status,
                "confidence": topic.confidence,
                "priority_score": topic.priority_score,
                "reasons": topic.reasons,
                "nearest_due_on": topic.nearest_due_on,
                "upcoming_assessment_count": topic.upcoming_assessment_count,
                "unresolved_mistake_count": topic.unresolved_mistake_count,
                "active_memory_count": topic.active_memory_count,
                "planned_item_count": topic.planned_item_count,
                "study_minutes": topic.study_minutes,
                "sources": [
                    {
                        "source_kind": source.source_kind,
                        "source_id": source.source_id,
                        "title": source.title,
                        "score": source.score,
                        "reasons": source.reasons,
                        "status": source.status,
                        "provider": source.provider,
                        "resource_type": source.resource_type,
                        "progress_status": source.progress_status,
                        "progress_value": source.progress_value,
                        "progress_max_value": source.progress_max_value,
                        "progress_unit": source.progress_unit,
                        "current_chunk_count": source.current_chunk_count,
                        "study_minutes": source.study_minutes,
                    }
                    for source in topic.sources
                ],
            }
            for topic in result.topics
        ],
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    path = Path(args.database)
    if not path.is_file() or path.is_symlink():
        print("PHASE 6.3 KNOWLEDGE NAVIGATOR: BLOCKED", file=sys.stderr)
        print("database is missing or not a regular file", file=sys.stderr)
        return 1

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
        try:
            repository = SQLiteKnowledgeNavigatorRepository(connection)
            result = KnowledgeNavigatorService(repository).navigate(
                args.course_code,
                topic_name=args.topic,
                as_of=as_of,
                limit_topics=args.limit_topics,
                limit_sources=args.limit_sources,
            )
            if connection.total_changes != before:
                raise RuntimeError("navigator preview unexpectedly wrote SQLite state")
        finally:
            connection.close()

        print("PHASE 6.3 KNOWLEDGE NAVIGATOR: PASS")
        print(json.dumps(_serialize(result), indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        print("PHASE 6.3 KNOWLEDGE NAVIGATOR: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
