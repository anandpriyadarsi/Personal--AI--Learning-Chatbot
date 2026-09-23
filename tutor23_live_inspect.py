"""Read-only ANVAYA Tutor 2.3 live-validation inspector.

Usage:
    python tutor23_live_inspect.py --database PATH --session-id SESSION_ID

The inspector opens SQLite in read-only mode. It does not update Tutor session
metadata, learning memory, progress, retrieval indexes, notes, or vault data.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.tutor.adaptive_state import (
    load_adaptive_state,
)
from personal_learning_assistant.tutor.personalized_policy import (
    build_personalized_teaching_policy,
    teaching_policy_mapping,
)
from personal_learning_assistant.tutor.session_goal import (
    load_session_goal,
)
from personal_learning_assistant.tutor.student_model import (
    build_persistent_student_model,
    student_model_mapping,
)
from personal_learning_assistant.tutor.teaching_orchestrator import (
    load_teaching_plan,
)


_ALLOWED_PENDING_KINDS = {
    "",
    "diagnostic",
    "quiz",
    "practice",
    "exit_check",
    "socratic_check",
}
_ALLOWED_GOAL_STATUSES = {"active", "likely_met", "unresolved"}


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


def _table_count(connection, table):
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (str(table),),
    ).fetchone()
    if row is None:
        return None
    return int(
        connection.execute(
            'SELECT COUNT(*) FROM "{}"'.format(str(table))
        ).fetchone()[0]
    )


def _recent_turns(connection, session_id, limit=20):
    rows = connection.execute(
        "SELECT t.id,t.ordinal,t.role,t.content,t.support_level,"
        "t.provider_name,t.provider_model,t.created_at,"
        "(SELECT COUNT(*) FROM tutor_evidence_links e WHERE e.turn_id=t.id) "
        "AS evidence_count "
        "FROM tutor_turns t WHERE t.session_id=? "
        "ORDER BY t.ordinal DESC LIMIT ?",
        (str(session_id), int(limit)),
    ).fetchall()
    result = []
    for row in reversed(rows):
        result.append(
            {
                "turn_id": str(row["id"]),
                "ordinal": int(row["ordinal"]),
                "role": str(row["role"]),
                "content": str(row["content"]),
                "support_level": str(row["support_level"]),
                "provider_name": str(row["provider_name"]),
                "provider_model": str(row["provider_model"]),
                "created_at": str(row["created_at"]),
                "evidence_count": int(row["evidence_count"] or 0),
            }
        )
    return result


def _state_checks(adaptive, goal, plan):
    pending_kind = str(
        adaptive.get("pending_question_kind") or ""
    ).strip().casefold()
    pending_question = str(
        adaptive.get("pending_question") or ""
    ).strip()
    awaiting = bool(adaptive.get("awaiting_student_answer"))
    practice_level = int(adaptive.get("practice_level") or 0)
    goal_status = str(goal.get("status") or "").strip().casefold()
    next_move = str(plan.get("next_move") or "").strip().casefold()

    checks = [
        {
            "name": "goal_status_allowed",
            "ok": goal_status in _ALLOWED_GOAL_STATUSES,
            "detail": goal_status,
        },
        {
            "name": "pending_question_kind_allowed",
            "ok": pending_kind in _ALLOWED_PENDING_KINDS,
            "detail": pending_kind,
        },
        {
            "name": "pending_question_consistent",
            "ok": (
                (awaiting and bool(pending_question) and bool(pending_kind))
                or (
                    not awaiting
                    and not pending_question
                    and not pending_kind
                )
            ),
            "detail": (
                "awaiting={} kind={} question_present={}".format(
                    awaiting,
                    pending_kind or "(none)",
                    bool(pending_question),
                )
            ),
        },
        {
            "name": "practice_level_bounded",
            "ok": 0 <= practice_level <= 5,
            "detail": str(practice_level),
        },
        {
            "name": "likely_met_has_goal",
            "ok": (
                goal_status != "likely_met"
                or bool(str(goal.get("goal") or "").strip())
            ),
            "detail": str(goal.get("goal") or ""),
        },
        {
            "name": "exit_check_plan_has_question",
            "ok": (
                str(plan.get("reason") or "") not in {
                    "student_reports_understanding",
                    "explicit_exit_check_requested",
                }
                or bool(str(plan.get("exit_check_question") or "").strip())
            ),
            "detail": str(plan.get("reason") or ""),
        },
        {
            "name": "finish_goal_is_exit_answer_only",
            "ok": (
                next_move != "finish_goal"
                or str(plan.get("reason") or "")
                == "pending_exit_check_answer"
            ),
            "detail": "{} / {}".format(
                next_move or "(none)",
                str(plan.get("reason") or "(none)"),
            ),
        },
    ]
    return checks


def inspect_session(database_path, session_id):
    connection = _readonly_connection(database_path)
    try:
        repository = SQLiteTutorRepository(connection)
        session = repository.get_session(str(session_id).strip())
        adaptive = load_adaptive_state(session.metadata)
        goal = load_session_goal(session.metadata)
        plan = load_teaching_plan(session.metadata)
        model = build_persistent_student_model(repository, session)
        policy = build_personalized_teaching_policy(
            model,
            adaptive,
            teaching_intent=adaptive.get("last_intent", ""),
        )
        course = repository.course_identity(session.course_id)
        topic = repository.topic_identity(
            session.topic_id,
            session.course_id,
        )
        checks = _state_checks(adaptive, goal, plan)

        return {
            "session": {
                "session_id": session.session_id,
                "course_id": session.course_id,
                "course": course,
                "topic_id": session.topic_id,
                "topic": topic,
                "mode": session.mode,
                "source_policy": session.source_policy,
                "status": session.status,
                "title": session.title,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            },
            "session_goal": goal,
            "teaching_plan": plan,
            "current_learning_state": adaptive,
            "persistent_student_model": student_model_mapping(model),
            "personalized_teaching_policy": teaching_policy_mapping(policy),
            "recent_turns": _recent_turns(
                connection,
                session.session_id,
            ),
            "protected_table_counts": {
                "learning_memory_entries": _table_count(
                    connection,
                    "learning_memory_entries",
                ),
                "progress_snapshots": _table_count(
                    connection,
                    "progress_snapshots",
                ),
            },
            "state_checks": checks,
            "all_state_checks_pass": all(
                bool(item["ok"]) for item in checks
            ),
        }
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Inspect ANVAYA Tutor 2.3 orchestration state without modifying "
            "SQLite."
        )
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    payload = inspect_session(args.database, args.session_id)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
