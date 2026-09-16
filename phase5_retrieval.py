"""Operator CLI for Phase 5.8 rebuildable retrieval / RAG context."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.retrieval.embedding import FastEmbedProvider
from personal_learning_assistant.retrieval.index_builder import (
    RetrievalIndexBuilder,
    RetrievalIndexBuildError,
)
from personal_learning_assistant.retrieval.index_store import (
    RetrievalIndexError,
    RetrievalIndexStore,
)
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import (
    RetrievalSourceRepositoryError,
    SQLiteRetrievalSourceRepository,
)
from personal_learning_assistant.services.retrieval_service import RetrievalService


CONFIRMATION_PHRASE = "BUILD_PHASE5_RETRIEVAL_INDEX"


def _parser():
    parser = argparse.ArgumentParser(description="Phase 5.8 retrieval operator CLI")
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--index-root", default=".phase5_retrieval")
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("--semantic", action="store_true")
    preview.add_argument("--model", default="BAAI/bge-small-en-v1.5")

    build = sub.add_parser("build")
    build.add_argument("--semantic", action="store_true")
    build.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    build.add_argument("--confirm", default="")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--semantic", action="store_true")
    search.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    search.add_argument("--course-id", action="append", default=[])
    search.add_argument("--topic-id", action="append", default=[])
    search.add_argument("--lecture", action="append", default=[])
    search.add_argument("--provider", action="append", default=[])
    search.add_argument("--top-k", type=int, default=8)

    context = sub.add_parser("context")
    context.add_argument("query")
    context.add_argument("--semantic", action="store_true")
    context.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    context.add_argument("--course-id", action="append", default=[])
    context.add_argument("--topic-id", action="append", default=[])
    context.add_argument("--lecture", action="append", default=[])
    context.add_argument("--provider", action="append", default=[])
    context.add_argument("--top-k", type=int, default=8)
    context.add_argument("--max-chars", type=int, default=12000)
    return parser


def _uri(path: Path, mode: str):
    value = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode={}".format(quote(value, safe="/:"), mode)


def _open(path: Path, *, writable: bool):
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


def _provider(enabled, model):
    return FastEmbedProvider(model_name=model) if enabled else None


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "build" and args.confirm != CONFIRMATION_PHRASE:
            print("PHASE 5.8 RETRIEVAL BUILD: BLOCKED", file=sys.stderr)
            print(
                "build requires --confirm {}".format(CONFIRMATION_PHRASE),
                file=sys.stderr,
            )
            return 2

        writable = args.command == "build"
        connection = _open(Path(args.database), writable=writable)
        try:
            repository = SQLiteRetrievalSourceRepository(connection)
            provider = _provider(getattr(args, "semantic", False), getattr(args, "model", ""))
            builder = RetrievalIndexBuilder(repository, args.index_root)

            if args.command == "preview":
                before = connection.total_changes
                output = builder.preview(embedding_provider=provider)
                counts = repository.handoff_counts()
                output["handoff_counts"] = counts
                output["preview_writes_performed"] = connection.total_changes != before
                print("PHASE 5.8 RETRIEVAL PREVIEW: PASS")
                print(json.dumps(output, indent=2, sort_keys=True))
                return 0

            if args.command == "build":
                result = builder.build(
                    embedding_provider=provider,
                    acknowledge=True,
                )
                output = {
                    "generation_id": result.generation_id,
                    "directory": result.directory,
                    "chunk_count": result.chunk_count,
                    "lexical_backend": result.lexical_backend,
                    "semantic_enabled": result.semantic_enabled,
                    "embedding_model": result.embedding_model,
                    "embedding_version": result.embedding_version,
                    "source_fingerprint": result.source_fingerprint,
                }
                print("PHASE 5.8 RETRIEVAL BUILD: PASS")
                print(json.dumps(output, indent=2, sort_keys=True))
                return 0
        finally:
            connection.close()

        provider = _provider(args.semantic, args.model)
        store = RetrievalIndexStore(args.index_root, embedding_provider=provider)
        try:
            service = RetrievalService(store)
            kwargs = {
                "course_ids": tuple(args.course_id),
                "topic_ids": tuple(args.topic_id),
                "lecture_numbers": tuple(args.lecture),
                "providers": tuple(args.provider),
                "top_k": args.top_k,
            }
            if args.command == "search":
                hits = service.search(args.query, **kwargs)
                print("PHASE 5.8 RETRIEVAL SEARCH: PASS")
                print(
                    json.dumps(
                        [
                            {
                                "chunk_id": hit.chunk_id,
                                "document_id": hit.document_id,
                                "score": hit.score,
                                "lexical_rank": hit.lexical_rank,
                                "semantic_rank": hit.semantic_rank,
                                "page_number": hit.page_number,
                                "locator": hit.locator,
                                "topic_ids": hit.topic_ids,
                                "course_ids": hit.course_ids,
                                "providers": hit.providers,
                                "text": hit.text,
                            }
                            for hit in hits
                        ],
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 0

            context = service.build_context(
                args.query,
                max_chars=args.max_chars,
                **kwargs,
            )
            print("PHASE 5.8 RAG CONTEXT: PASS")
            print(
                json.dumps(
                    {
                        "query": context.query,
                        "source_count": context.source_count,
                        "total_characters": context.total_characters,
                        "context_text": context.context_text,
                        "llm_called": False,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        finally:
            store.close()
    except (
        OSError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
        RetrievalIndexBuildError,
        RetrievalIndexError,
        RetrievalSourceRepositoryError,
    ) as error:
        print("PHASE 5.8 RETRIEVAL: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
