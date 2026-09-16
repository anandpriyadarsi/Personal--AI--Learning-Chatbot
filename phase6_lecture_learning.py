"""Phase 6.4 operator CLI for explicit Lecture Learning Mode."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.lecture_learning_repository import (
    SQLiteLectureLearningRepository,
)
from personal_learning_assistant.services.lecture_learning_service import (
    LectureLearningService,
)


_CONFIRM = {
    "start": "START_LECTURE_SESSION",
    "checkpoint": "CHECKPOINT_LECTURE_SESSION",
    "pause": "PAUSE_LECTURE_SESSION",
    "resume": "RESUME_LECTURE_SESSION",
    "finish": "FINISH_LECTURE_SESSION",
}


def _parser():
    parser = argparse.ArgumentParser(
        description="Phase 6.4 explicit lecture learning operator"
    )
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--authority", default=".phase4_authority.json")

    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list")
    listing.add_argument("--course-code")
    listing.add_argument("--provider")
    listing.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show")
    show.add_argument("--resource-id", required=True)

    for command in ("start", "checkpoint", "pause", "resume", "finish"):
        item = sub.add_parser(command)
        item.add_argument("--resource-id", required=True)
        item.add_argument("--position")
        item.add_argument("--value", type=float)
        item.add_argument("--max-value", type=float)
        item.add_argument("--unit")
        item.add_argument("--note", default="")
        item.add_argument("--confirm", default="")
        if command in {"start", "resume"}:
            item.add_argument("--course-id")
            item.add_argument("--topic-id")
        if command == "finish":
            item.add_argument("--confidence", type=int)

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


def _snapshot_dict(snapshot):
    return {
        "resource_id": snapshot.resource_id,
        "title": snapshot.title,
        "resource_type": snapshot.resource_type,
        "provider": snapshot.provider,
        "canonical_uri": snapshot.canonical_uri,
        "external_id": snapshot.external_id,
        "status": snapshot.status,
        "course_ids": snapshot.course_ids,
        "topic_ids": snapshot.topic_ids,
        "current_position": snapshot.current_position,
        "progress_value": snapshot.progress_value,
        "progress_max_value": snapshot.progress_max_value,
        "progress_unit": snapshot.progress_unit,
        "total_study_minutes": snapshot.total_study_minutes,
        "segment_count": snapshot.segment_count,
        "active_session_id": snapshot.active_session_id,
        "active_started_at": snapshot.active_started_at,
        "current_chunk_count": snapshot.current_chunk_count,
        "next_action": snapshot.next_action,
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    writable = args.command in _CONFIRM
    if writable:
        required = _CONFIRM[args.command]
        if args.confirm != required:
            print("PHASE 6.4 LECTURE LEARNING: BLOCKED", file=sys.stderr)
            print(
                "{} requires --confirm {}".format(args.command, required),
                file=sys.stderr,
            )
            return 2

    connection = None
    try:
        connection = _open(Path(args.database), writable=writable)
        repository = SQLiteLectureLearningRepository(
            connection,
            authority_control_path=Path(args.authority) if writable else None,
        )
        service = LectureLearningService(repository)

        if args.command == "list":
            before = connection.total_changes
            rows = repository.list_lecture_resources(
                course_code=args.course_code,
                provider=args.provider,
                limit=args.limit,
            )
            if connection.total_changes != before:
                raise RuntimeError("lecture listing unexpectedly wrote SQLite state")
            print("PHASE 6.4 LECTURE LEARNING PREVIEW: PASS")
            print(
                json.dumps(
                    {
                        "count": len(rows),
                        "writes_performed": False,
                        "lectures": [
                            {
                                "resource_id": str(row["id"]),
                                "title": str(row["title"]),
                                "provider": str(row["provider"]),
                                "status": str(row["status"]),
                                "canonical_uri": (
                                    None
                                    if row["canonical_uri"] is None
                                    else str(row["canonical_uri"])
                                ),
                                "external_id": (
                                    None
                                    if row["external_id"] is None
                                    else str(row["external_id"])
                                ),
                            }
                            for row in rows
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "show":
            before = connection.total_changes
            snapshot = service.snapshot(args.resource_id)
            if connection.total_changes != before:
                raise RuntimeError("lecture snapshot unexpectedly wrote SQLite state")
            print("PHASE 6.4 LECTURE LEARNING SNAPSHOT: PASS")
            print(json.dumps(_snapshot_dict(snapshot), indent=2, ensure_ascii=False))
            return 0

        common = {
            "position": args.position,
            "value": args.value,
            "max_value": args.max_value,
            "unit": args.unit,
            "note": args.note,
        }
        if args.command == "start":
            result = service.start(
                args.resource_id,
                course_id=args.course_id,
                topic_id=args.topic_id,
                **common
            )
        elif args.command == "checkpoint":
            result = service.checkpoint(args.resource_id, **common)
        elif args.command == "pause":
            result = service.pause(args.resource_id, **common)
        elif args.command == "resume":
            result = service.resume(
                args.resource_id,
                course_id=args.course_id,
                topic_id=args.topic_id,
                **common
            )
        elif args.command == "finish":
            result = service.finish(
                args.resource_id,
                confidence=args.confidence,
                **common
            )
        else:
            raise RuntimeError("unsupported command")

        print("PHASE 6.4 LECTURE LEARNING ACTION: PASS")
        print(
            json.dumps(
                {
                    "action": result.action,
                    "segment_id": result.segment_id,
                    "recorded_minutes": result.recorded_minutes,
                    "snapshot": _snapshot_dict(result.snapshot),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:
        print("PHASE 6.4 LECTURE LEARNING: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
