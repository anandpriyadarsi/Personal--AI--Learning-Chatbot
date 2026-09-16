"""Phase 6.9 final Tutor Workspace / Academic Tutor closure verifier."""

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
from personal_learning_assistant.services.phase6_closure_service import (
    Phase6ClosureService,
)
from personal_learning_assistant.services.tutor_workspace_service import (
    TutorWorkspaceService,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.9 final Tutor Workspace / Phase 6 closure"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--authority", default=".phase4_authority.json")
    parser.add_argument("--index-root", default=".phase5_retrieval")
    parser.add_argument("--course-code", default="MA103N")
    parser.add_argument("--as-of", default="2026-09-16")
    parser.add_argument("--target-assessment-id")
    parser.add_argument(
        "--smoke-query",
        default="LU factorization triangular matrices",
    )
    return parser


def _uri(path: Path):
    return "file:{}?mode=ro".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    )


def main(argv=None):
    args = _parser().parse_args(argv)
    db = Path(args.database)
    if not db.is_file() or db.is_symlink():
        print("PHASE 6 FINAL TUTOR WORKSPACE/CLOSURE: BLOCKED", file=sys.stderr)
        print("production database is missing or not a regular file", file=sys.stderr)
        return 1

    connection = None
    try:
        connection = sqlite3.connect(
            _uri(db),
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
        mentor = AdaptiveMentorService(
            navigator_service=navigator,
            exam_intelligence_service=exam,
            evidence_repository=SQLiteAdaptiveMentorRepository(connection),
        )
        workspace = TutorWorkspaceService(
            repository=SQLiteTutorWorkspaceRepository(connection),
            mentor_service=mentor,
        )
        report = Phase6ClosureService(
            connection,
            authority_control_path=Path(args.authority),
            index_root=Path(args.index_root),
            workspace_service=workspace,
        ).verify(
            args.course_code,
            as_of=date.fromisoformat(args.as_of),
            target_assessment_id=args.target_assessment_id,
            smoke_query=args.smoke_query,
        )
        if connection.total_changes != before:
            raise RuntimeError("Phase 6 closure unexpectedly wrote SQLite state")

        print("PHASE 6 FINAL TUTOR WORKSPACE/CLOSURE: PASS")
        print(json.dumps(report, indent=2, ensure_ascii=False, default=list))
        return 0
    except Exception as error:
        print("PHASE 6 FINAL TUTOR WORKSPACE/CLOSURE: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
