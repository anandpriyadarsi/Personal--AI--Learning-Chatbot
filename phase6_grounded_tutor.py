"""Phase 6.2 operator CLI for grounded tutor planning and explicit answering."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.retrieval.index_store import RetrievalIndexStore
from personal_learning_assistant.services.grounded_tutor_service import (
    GroundedTutorService,
)
from personal_learning_assistant.services.retrieval_service import RetrievalService
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner
from personal_learning_assistant.tutor.http_provider import (
    OpenAICompatibleTutorProvider,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.2 grounded academic tutor operator CLI"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--index-root", default=".phase5_retrieval")

    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("question")
    preview.add_argument("--course-code")
    preview.add_argument("--topic")
    preview.add_argument("--resource-id")
    preview.add_argument("--mode", default="concept")
    preview.add_argument(
        "--source-policy",
        choices=("source_only", "source_first"),
        default="source_only",
    )
    preview.add_argument("--top-k", type=int)

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--session-id", required=True)
    ask.add_argument("--top-k", type=int)
    ask.add_argument("--confirm", default="")
    return parser


def _uri(path: Path, mode: str):
    return "file:{}?mode={}".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:"),
        mode,
    )


def _open(path: Path, *, writable):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("SQLite database is missing or not a regular file")
    connection = sqlite3.connect(
        _uri(path, "rw" if writable else "ro"),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _resolve_scope(connection, course_code, topic):
    course_id = None
    topic_id = None
    if course_code:
        row = connection.execute(
            "SELECT id FROM courses WHERE upper(code)=upper(?) AND deleted_at IS NULL",
            (course_code,),
        ).fetchone()
        if row is None:
            raise RuntimeError("course code not found: {}".format(course_code))
        course_id = str(row[0])
    if topic:
        if not course_id:
            raise RuntimeError("--topic requires --course-code")
        row = connection.execute(
            "SELECT id FROM topics WHERE course_id=? "
            "AND lower(name)=lower(?) AND deleted_at IS NULL",
            (course_id, topic),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                "topic not found in selected course: {}".format(topic)
            )
        topic_id = str(row[0])
    return course_id, topic_id


class _PreviewSession:
    def __init__(
        self,
        *,
        mode,
        source_policy,
        course_id,
        topic_id,
        resource_id,
    ):
        self.session_id = "preview"
        self.mode = mode
        self.source_policy = source_policy
        self.status = "active"
        self.course_id = course_id
        self.topic_id = topic_id
        self.assessment_id = None
        self.resource_id = resource_id


class _EvidenceAdapter:
    def evidence_from_retrieval_hits(self, hits, *, relation_type="support"):
        from personal_learning_assistant.domain.tutor_models import TutorEvidence

        return tuple(
            TutorEvidence(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                ordinal=index,
                relation_type=relation_type,
                retrieval_score=hit.score,
                citation_label="S{}".format(index),
            )
            for index, hit in enumerate(hits, 1)
        )


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "preview":
            connection = _open(Path(args.database), writable=False)
            try:
                course_id, topic_id = _resolve_scope(
                    connection,
                    args.course_code,
                    args.topic,
                )
            finally:
                connection.close()

            store = RetrievalIndexStore(args.index_root)
            try:
                retrieval = RetrievalService(store)
                adapter = _EvidenceAdapter()
                planner = TutorGroundingPlanner(retrieval, adapter)
                session = _PreviewSession(
                    mode=args.mode,
                    source_policy=args.source_policy,
                    course_id=course_id,
                    topic_id=topic_id,
                    resource_id=args.resource_id,
                )
                plan = planner.plan(
                    session,
                    args.question,
                    transcript=(),
                    top_k=args.top_k,
                )
            finally:
                store.close()

            print("PHASE 6.2 GROUNDED TUTOR PREVIEW: PASS")
            print(
                json.dumps(
                    {
                        "mode": plan.mode,
                        "source_policy": plan.source_policy,
                        "retrieved_chunk_count": len(plan.hits),
                        "chunk_ids": [hit.chunk_id for hit in plan.hits],
                        "evidence_labels": [
                            item.citation_label for item in plan.evidence
                        ],
                        "context_characters": len(plan.context_text),
                        "provider_called": False,
                        "sqlite_writes_performed": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if args.confirm != "ASK_GROUNDED_TUTOR":
            print("PHASE 6.2 GROUNDED TUTOR: BLOCKED", file=sys.stderr)
            print(
                "ask requires --confirm ASK_GROUNDED_TUTOR",
                file=sys.stderr,
            )
            return 2

        connection = _open(Path(args.database), writable=True)
        try:
            repository = SQLiteTutorRepository(connection)
            sessions = TutorSessionService(repository)
            store = RetrievalIndexStore(args.index_root)
            try:
                retrieval = RetrievalService(store)
                provider = OpenAICompatibleTutorProvider()
                engine = GroundedTutorService(
                    tutor_session_service=sessions,
                    retrieval_service=retrieval,
                    provider=provider,
                )
                result = engine.answer(
                    args.session_id,
                    args.question,
                    top_k=args.top_k,
                )
            finally:
                store.close()
        finally:
            connection.close()

        print("PHASE 6.2 GROUNDED TUTOR: PASS")
        print(
            json.dumps(
                {
                    "assistant_turn_id": result.assistant_turn.turn_id,
                    "support_level": result.assistant_turn.support_level,
                    "citations": result.citations,
                    "retrieved_chunk_ids": result.retrieved_chunk_ids,
                    "provider_name": result.assistant_turn.provider_name,
                    "provider_model": result.assistant_turn.provider_model,
                    "answer": result.assistant_turn.content,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:
        print("PHASE 6.2 GROUNDED TUTOR: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
