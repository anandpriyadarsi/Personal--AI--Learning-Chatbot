"""Phase 6.5 operator CLI for source-grounded Active Recall / Fast Quiz."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.domain.practice_models import PracticeQuizSpec
from personal_learning_assistant.repositories.sqlite.practice_repository import (
    SQLitePracticeRepository,
)
from personal_learning_assistant.retrieval.index_store import RetrievalIndexStore
from personal_learning_assistant.services.practice_quiz_service import (
    PracticeQuizService,
)
from personal_learning_assistant.services.retrieval_service import RetrievalService
from personal_learning_assistant.tutor.http_provider import (
    OpenAICompatibleTutorProvider,
)
from personal_learning_assistant.tutor.quiz_grounding import build_plan


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.5 source-grounded Active Recall / Fast Quiz"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--authority", default=".phase4_authority.json")
    parser.add_argument("--index-root", default=".phase5_retrieval")

    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("preview", "generate"):
        item = sub.add_parser(name)
        item.add_argument("focus")
        item.add_argument("--course-code", required=True)
        item.add_argument("--topic")
        item.add_argument("--resource-id")
        item.add_argument(
            "--mode",
            choices=("checkpoint", "fast_quiz", "active_recall"),
            default="fast_quiz",
        )
        item.add_argument(
            "--difficulty",
            choices=("easy", "medium", "hard", "mixed"),
            default="medium",
        )
        item.add_argument("--item-count", type=int, default=5)
        item.add_argument("--top-k", type=int, default=10)
        if name == "generate":
            item.add_argument("--tutor-session-id")
            item.add_argument("--confirm", default="")

    show = sub.add_parser("show")
    show.add_argument("--session-id", required=True)

    submit = sub.add_parser("submit")
    submit.add_argument("--session-id", required=True)
    submit.add_argument("--item", type=int, required=True)
    submit.add_argument("--response", required=True)
    submit.add_argument("--confidence", type=int)
    submit.add_argument("--confirm", default="")

    finish = sub.add_parser("finish")
    finish.add_argument("--session-id", required=True)
    finish.add_argument("--confirm", default="")

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


def _resolve_scope(connection, course_code, topic, resource_id):
    course = connection.execute(
        "SELECT id,code FROM courses WHERE upper(code)=upper(?) "
        "AND deleted_at IS NULL",
        (course_code,),
    ).fetchall()
    if len(course) != 1:
        raise RuntimeError("expected exactly one active course for code")
    course_id = str(course[0]["id"])
    topic_id = None
    if topic:
        clean = " ".join(str(topic).strip().casefold().split())
        rows = connection.execute(
            "SELECT id,name,normalized_name FROM topics "
            "WHERE course_id=? AND deleted_at IS NULL",
            (course_id,),
        ).fetchall()
        matches = [
            row for row in rows
            if clean in {
                " ".join(str(row["name"]).strip().casefold().split()),
                " ".join(str(row["normalized_name"]).strip().casefold().split()),
            }
        ]
        if len(matches) != 1:
            raise RuntimeError("expected exactly one topic match in selected course")
        topic_id = str(matches[0]["id"])
    if resource_id:
        linked = connection.execute(
            "SELECT 1 FROM resource_courses WHERE resource_id=? AND course_id=?",
            (resource_id, course_id),
        ).fetchone()
        if linked is None:
            raise RuntimeError("resource is not linked to selected course")
    return course_id, topic_id


class _PreviewRepository:
    def __init__(self, connection):
        self.connection = connection

    def entity_exists(self, table, entity_id):
        if entity_id is None:
            return True
        row = self.connection.execute(
            'SELECT 1 FROM "{}" WHERE id=?'.format(table),
            (entity_id,),
        ).fetchone()
        return row is not None

    def topic_course_id(self, topic_id):
        row = self.connection.execute(
            "SELECT course_id FROM topics WHERE id=? AND deleted_at IS NULL",
            (topic_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def resource_has_course(self, resource_id, course_id):
        return self.connection.execute(
            "SELECT 1 FROM resource_courses WHERE resource_id=? AND course_id=?",
            (resource_id, course_id),
        ).fetchone() is not None


def _view_dict(view):
    return {
        "session_id": view.session_id,
        "course_id": view.course_id,
        "topic_id": view.topic_id,
        "resource_id": view.resource_id,
        "mode": view.mode,
        "difficulty": view.difficulty,
        "status": view.status,
        "source_query": view.source_query,
        "created_at": view.created_at,
        "items": [
            {
                "ordinal": item.ordinal,
                "item_type": item.item_type,
                "prompt": item.prompt,
                "options": item.options,
                "attempted": item.attempted,
            }
            for item in view.items
        ],
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    connection = None
    store = None
    try:
        if args.command in {"preview", "generate"}:
            writable = args.command == "generate"
            if writable and args.confirm != "GENERATE_GROUNDED_QUIZ":
                print("PHASE 6.5 FAST QUIZ: BLOCKED", file=sys.stderr)
                print(
                    "generate requires --confirm GENERATE_GROUNDED_QUIZ",
                    file=sys.stderr,
                )
                return 2
            connection = _open(Path(args.database), writable=writable)
            course_id, topic_id = _resolve_scope(
                connection,
                args.course_code,
                args.topic,
                args.resource_id,
            )
            spec = PracticeQuizSpec(
                course_id=course_id,
                topic_id=topic_id,
                resource_id=args.resource_id,
                tutor_session_id=(
                    args.tutor_session_id if writable else None
                ),
                mode=args.mode,
                difficulty=args.difficulty,
                item_count=args.item_count,
                focus=args.focus,
            )
            store = RetrievalIndexStore(args.index_root)
            retrieval = RetrievalService(store)

            if args.command == "preview":
                before = connection.total_changes
                plan = build_plan(
                    retrieval,
                    spec,
                    top_k=args.top_k,
                )
                if connection.total_changes != before:
                    raise RuntimeError("practice preview unexpectedly wrote SQLite")
                print("PHASE 6.5 FAST QUIZ PREVIEW: PASS")
                print(
                    json.dumps(
                        {
                            "course_id": course_id,
                            "topic_id": topic_id,
                            "resource_id": args.resource_id,
                            "mode": args.mode,
                            "difficulty": args.difficulty,
                            "requested_item_count": args.item_count,
                            "retrieved_chunk_count": len(plan.hits),
                            "evidence_labels": plan.evidence_labels,
                            "provider_called": False,
                            "sqlite_writes_performed": False,
                        },
                        indent=2,
                    )
                )
                return 0

            repository = SQLitePracticeRepository(
                connection,
                authority_control_path=Path(args.authority),
            )
            provider = OpenAICompatibleTutorProvider()
            service = PracticeQuizService(
                repository=repository,
                retrieval_service=retrieval,
                provider=provider,
            )
            view = service.generate(spec, top_k=args.top_k)
            print("PHASE 6.5 FAST QUIZ GENERATION: PASS")
            print(json.dumps(_view_dict(view), indent=2, ensure_ascii=False))
            return 0

        writable = args.command in {"submit", "finish"}
        if args.command == "submit" and args.confirm != "SUBMIT_PRACTICE_ATTEMPT":
            print("PHASE 6.5 FAST QUIZ: BLOCKED", file=sys.stderr)
            print(
                "submit requires --confirm SUBMIT_PRACTICE_ATTEMPT",
                file=sys.stderr,
            )
            return 2
        if args.command == "finish" and args.confirm != "FINISH_PRACTICE_SESSION":
            print("PHASE 6.5 FAST QUIZ: BLOCKED", file=sys.stderr)
            print(
                "finish requires --confirm FINISH_PRACTICE_SESSION",
                file=sys.stderr,
            )
            return 2

        connection = _open(Path(args.database), writable=writable)
        repository = SQLitePracticeRepository(
            connection,
            authority_control_path=(
                Path(args.authority) if writable else None
            ),
        )
        service = PracticeQuizService(
            repository=repository,
            retrieval_service=None,
            provider=None,
        )

        if args.command == "show":
            before = connection.total_changes
            view = service.view(args.session_id)
            if connection.total_changes != before:
                raise RuntimeError("practice show unexpectedly wrote SQLite")
            print("PHASE 6.5 FAST QUIZ VIEW: PASS")
            print(json.dumps(_view_dict(view), indent=2, ensure_ascii=False))
            return 0

        if args.command == "submit":
            result = service.submit(
                args.session_id,
                args.item,
                args.response,
                self_confidence=args.confidence,
            )
            print("PHASE 6.5 PRACTICE ATTEMPT: PASS")
            print(
                json.dumps(
                    {
                        "attempt_id": result.attempt_id,
                        "session_id": result.session_id,
                        "item_ordinal": result.item_ordinal,
                        "attempt_number": result.attempt_number,
                        "outcome": result.outcome,
                        "score_bps": result.score_bps,
                        "grading_mode": result.grading_mode,
                        "self_confidence": result.self_confidence,
                        "feedback": result.feedback,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "finish":
            view, changed = service.finish(args.session_id)
            print("PHASE 6.5 PRACTICE SESSION FINISH: PASS")
            print(
                json.dumps(
                    {
                        "changed": changed,
                        "session": _view_dict(view),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        raise RuntimeError("unsupported command")
    except Exception as error:
        print("PHASE 6.5 FAST QUIZ: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
