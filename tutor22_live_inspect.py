"""Read-only Tutor 2.2 live-validation inspector.

Usage:
    python tutor22_live_inspect.py --database PATH --session-id SESSION_ID

This tool opens SQLite in read-only mode and prints the session-local state,
cross-session student model, derived personalized teaching policy, and memory
candidates. It performs no writes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.tutor.adaptive_state import load_adaptive_state
from personal_learning_assistant.tutor.personalized_policy import (
    build_personalized_teaching_policy,
    teaching_policy_mapping,
)
from personal_learning_assistant.tutor.student_model import (
    build_persistent_student_model,
    student_model_mapping,
)


def _readonly_connection(path):
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    connection = sqlite3.connect(
        resolved.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def inspect_session(database_path, session_id):
    connection = _readonly_connection(database_path)
    try:
        repository = SQLiteTutorRepository(connection)
        session = repository.get_session(str(session_id).strip())
        adaptive = load_adaptive_state(session.metadata)
        model = build_persistent_student_model(repository, session)
        policy = build_personalized_teaching_policy(
            model,
            adaptive,
            teaching_intent=adaptive.get("last_intent", ""),
        )

        try:
            rows = connection.execute(
                "SELECT id,signal_kind,candidate_kind,candidate_text,"
                "confidence,evidence_count,session_count,status,"
                "accepted_memory_entry_id,review_note,first_observed_at,"
                "last_observed_at,provenance_json "
                "FROM tutor_memory_candidates "
                "WHERE course_id=? "
                "AND (? IS NULL OR topic_id=?) "
                "ORDER BY created_at DESC,id DESC LIMIT 30",
                (
                    str(session.course_id or ""),
                    session.topic_id,
                    session.topic_id,
                ),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = ()

        candidates = []
        for row in rows:
            item = {key: row[key] for key in row.keys()}
            try:
                item["provenance"] = json.loads(
                    str(item.pop("provenance_json") or "[]")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                item["provenance"] = []
            candidates.append(item)

        return {
            "session": {
                "session_id": session.session_id,
                "course_id": session.course_id,
                "topic_id": session.topic_id,
                "mode": session.mode,
                "source_policy": session.source_policy,
                "title": session.title,
            },
            "current_learning_state": adaptive,
            "persistent_student_model": student_model_mapping(model),
            "personalized_teaching_policy": teaching_policy_mapping(policy),
            "memory_candidates": candidates,
        }
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Inspect Tutor 2.2 state without modifying SQLite."
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    payload = inspect_session(args.database, args.session_id)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
