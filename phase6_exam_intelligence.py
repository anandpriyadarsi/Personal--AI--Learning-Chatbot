"""Phase 6.6 read-only PYQ + Exam Intelligence CLI."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.exam_intelligence_repository import (
    SQLiteExamIntelligenceRepository,
)
from personal_learning_assistant.services.exam_intelligence_service import (
    ExamIntelligenceService,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.6 read-only PYQ + Exam Intelligence"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--course-code", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--target-assessment-id")
    parser.add_argument("--limit-topics", type=int, default=12)
    parser.add_argument("--limit-questions", type=int, default=25)
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
        "formal_assessment_count": report.formal_assessment_count,
        "formal_question_count": report.formal_question_count,
        "explicit_pyq_assessment_count": report.explicit_pyq_assessment_count,
        "explicit_pyq_question_count": report.explicit_pyq_question_count,
        "accepted_mapped_question_count": report.accepted_mapped_question_count,
        "proposed_only_question_count": report.proposed_only_question_count,
        "unmapped_question_count": report.unmapped_question_count,
        "source_backed_question_count": report.source_backed_question_count,
        "upcoming_assessment_count": report.upcoming_assessment_count,
        "target_assessment_id": report.target_assessment_id,
        "target_assessment_title": report.target_assessment_title,
        "prediction_performed": report.prediction_performed,
        "writes_performed": report.writes_performed,
        "topics": [
            {
                "topic_id": item.topic_id,
                "topic_name": item.topic_name,
                "position": item.position,
                "status": item.status,
                "confidence": item.confidence,
                "historical_question_count": item.historical_question_count,
                "historical_assessment_count": item.historical_assessment_count,
                "explicit_pyq_question_count": item.explicit_pyq_question_count,
                "total_marks_milli": item.total_marks_milli,
                "missing_marks_question_count": item.missing_marks_question_count,
                "source_backed_question_count": item.source_backed_question_count,
                "attempted_question_count": item.attempted_question_count,
                "unresolved_mistake_count": item.unresolved_mistake_count,
                "target_assessment_in_scope": item.target_assessment_in_scope,
                "preparation_priority_score": item.preparation_priority_score,
                "reasons": item.reasons,
            }
            for item in report.topics
        ],
        "questions": [
            {
                "question_id": item.question_id,
                "assessment_id": item.assessment_id,
                "assessment_title": item.assessment_title,
                "assessment_type": item.assessment_type,
                "explicit_pyq": item.explicit_pyq,
                "ordinal": item.ordinal,
                "question_text": item.question_text,
                "max_marks_milli": item.max_marks_milli,
                "accepted_topic_ids": item.accepted_topic_ids,
                "mapping_state": item.mapping_state,
                "source_count": item.source_count,
                "source_labels": item.source_labels,
                "attempt_count": item.attempt_count,
                "unresolved_mistake_count": item.unresolved_mistake_count,
            }
            for item in report.questions
        ],
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    path = Path(args.database)
    if not path.is_file() or path.is_symlink():
        print("PHASE 6.6 PYQ + EXAM INTELLIGENCE: BLOCKED", file=sys.stderr)
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
        repository = SQLiteExamIntelligenceRepository(connection)
        report = ExamIntelligenceService(repository).analyze(
            args.course_code,
            as_of=as_of,
            target_assessment_id=args.target_assessment_id,
            limit_topics=args.limit_topics,
            limit_questions=args.limit_questions,
        )
        if connection.total_changes != before:
            raise RuntimeError("exam intelligence unexpectedly wrote SQLite state")
        print("PHASE 6.6 PYQ + EXAM INTELLIGENCE: PASS")
        print(json.dumps(_serialize(report), indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        print("PHASE 6.6 PYQ + EXAM INTELLIGENCE: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
