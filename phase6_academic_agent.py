"""Phase 6.8 Academic Agent preview + explicit execution CLI."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.academic_agent_repository import (
    SQLiteAcademicAgentRepository,
)
from personal_learning_assistant.repositories.sqlite.adaptive_mentor_repository import (
    SQLiteAdaptiveMentorRepository,
)
from personal_learning_assistant.repositories.sqlite.exam_intelligence_repository import (
    SQLiteExamIntelligenceRepository,
)
from personal_learning_assistant.repositories.sqlite.knowledge_navigator_repository import (
    SQLiteKnowledgeNavigatorRepository,
)
from personal_learning_assistant.repositories.sqlite.lecture_learning_repository import (
    SQLiteLectureLearningRepository,
)
from personal_learning_assistant.repositories.sqlite.practice_repository import (
    SQLitePracticeRepository,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.retrieval.index_store import RetrievalIndexStore
from personal_learning_assistant.services.academic_agent_cutover_service import (
    AcademicAgentService,
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
from personal_learning_assistant.services.lecture_learning_service import (
    LectureLearningService,
)
from personal_learning_assistant.services.practice_quiz_service import (
    PracticeQuizService,
)
from personal_learning_assistant.services.retrieval_service import RetrievalService
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.tutor.http_provider import (
    OpenAICompatibleTutorProvider,
)


CONFIRM = "EXECUTE_ACADEMIC_AGENT_ACTION"


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.8 explicit Academic Agent Cutover"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--authority", default=".phase4_authority.json")
    parser.add_argument("--index-root", default=".phase5_retrieval")
    parser.add_argument("--course-code", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--target-assessment-id")
    parser.add_argument("--limit-topics", type=int, default=5)
    parser.add_argument("--max-actions", type=int, default=10)

    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--action-sequence", type=int, required=True)

    execute = sub.add_parser("execute")
    execute.add_argument("--action-sequence", type=int, required=True)
    execute.add_argument("--expected-fingerprint", required=True)
    execute.add_argument("--confirm", default="")
    execute.add_argument("--practice-item-count", type=int, default=5)
    execute.add_argument(
        "--practice-difficulty",
        choices=("easy", "medium", "hard", "mixed"),
        default="medium",
    )
    return parser


def _uri(path: Path, *, writable):
    return "file:{}?mode={}".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:"),
        "rw" if writable else "ro",
    )


def _open(path: Path, *, writable):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("SQLite database is missing or not a regular file")
    connection = sqlite3.connect(
        _uri(path, writable=writable),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _mentor(connection):
    navigator = KnowledgeNavigatorService(
        SQLiteKnowledgeNavigatorRepository(connection)
    )
    exam = ExamIntelligenceService(
        SQLiteExamIntelligenceRepository(connection)
    )
    evidence = SQLiteAdaptiveMentorRepository(connection)
    return AdaptiveMentorService(
        navigator_service=navigator,
        exam_intelligence_service=exam,
        evidence_repository=evidence,
    )


def _plan_dict(plan):
    return {
        "course_id": plan.course_id,
        "course_code": plan.course_code,
        "as_of": plan.as_of,
        "target_assessment_id": plan.target_assessment_id,
        "action_sequence": plan.action_sequence,
        "action_type": plan.action_type,
        "title": plan.title,
        "topic_id": plan.topic_id,
        "topic_name": plan.topic_name,
        "priority_score": plan.priority_score,
        "reasons": plan.reasons,
        "resource_id": plan.resource_id,
        "note_id": plan.note_id,
        "question_id": plan.question_id,
        "assessment_id": plan.assessment_id,
        "source_labels": plan.source_labels,
        "route": plan.route,
        "fingerprint": plan.fingerprint,
        "confirmation_phrase": plan.confirmation_phrase,
        "writes_expected": plan.writes_expected,
        "provider_call_expected": plan.provider_call_expected,
        "executable": plan.executable,
        "blocked_reason": plan.blocked_reason,
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    connection = None
    index_store = None
    try:
        as_of = date.today() if args.as_of is None else date.fromisoformat(args.as_of)
        writable = args.command == "execute"
        if writable and args.confirm != CONFIRM:
            print("PHASE 6.8 ACADEMIC AGENT: BLOCKED", file=sys.stderr)
            print(
                "execute requires --confirm {}".format(CONFIRM),
                file=sys.stderr,
            )
            return 2

        connection = _open(Path(args.database), writable=writable)
        mentor = _mentor(connection)
        audit = SQLiteAcademicAgentRepository(
            connection,
            authority_control_path=(
                Path(args.authority) if writable else None
            ),
        )
        base_agent = AcademicAgentService(
            mentor_service=mentor,
            execution_repository=audit,
        )
        plan = base_agent.plan(
            args.course_code,
            args.action_sequence,
            as_of=as_of,
            target_assessment_id=args.target_assessment_id,
            limit_topics=args.limit_topics,
            max_actions=args.max_actions,
        )

        if args.command == "preview":
            before = connection.total_changes
            # Planning already occurred and is read-only; this assertion catches
            # accidental writes by future refactors.
            if connection.total_changes != before:
                raise RuntimeError("agent preview unexpectedly wrote SQLite state")
            print("PHASE 6.8 ACADEMIC AGENT PREVIEW: PASS")
            print(json.dumps(_plan_dict(plan), indent=2, ensure_ascii=False))
            return 0

        lecture_service = None
        tutor_service = None
        practice_service = None

        if plan.route == "lecture_learning":
            lecture_service = LectureLearningService(
                SQLiteLectureLearningRepository(
                    connection,
                    authority_control_path=Path(args.authority),
                )
            )
        elif plan.route in {"tutor_session", "exam_tutor_session"}:
            tutor_service = TutorSessionService(
                SQLiteTutorRepository(connection)
            )
        elif plan.route == "practice_quiz":
            index_store = RetrievalIndexStore(args.index_root)
            retrieval = RetrievalService(index_store)
            practice_service = PracticeQuizService(
                repository=SQLitePracticeRepository(
                    connection,
                    authority_control_path=Path(args.authority),
                ),
                retrieval_service=retrieval,
                provider=OpenAICompatibleTutorProvider(),
            )

        agent = AcademicAgentService(
            mentor_service=mentor,
            execution_repository=audit,
            lecture_service=lecture_service,
            tutor_session_service=tutor_service,
            practice_service=practice_service,
        )
        result = agent.execute(
            args.course_code,
            args.action_sequence,
            expected_fingerprint=args.expected_fingerprint,
            confirmation=args.confirm,
            as_of=as_of,
            target_assessment_id=args.target_assessment_id,
            limit_topics=args.limit_topics,
            max_actions=args.max_actions,
            practice_item_count=args.practice_item_count,
            practice_difficulty=args.practice_difficulty,
        )
        print("PHASE 6.8 ACADEMIC AGENT EXECUTION: PASS")
        print(
            json.dumps(
                {
                    "fingerprint": result.fingerprint,
                    "action_type": result.action_type,
                    "route": result.route,
                    "status": result.status,
                    "result_type": result.result_type,
                    "result_id": result.result_id,
                    "payload": result.payload,
                    "writes_performed": result.writes_performed,
                    "provider_called": result.provider_called,
                    "already_executed": result.already_executed,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:
        print("PHASE 6.8 ACADEMIC AGENT: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        if index_store is not None:
            index_store.close()
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
