from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.tutor.adaptive_state import STATE_KEY
from personal_learning_assistant.tutor.session_goal import commit_session_goal
from personal_learning_assistant.tutor.teaching_orchestrator import (
    commit_teaching_plan,
)
from tutor23_live_inspect import inspect_session


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _environment(tmp_path):
    path = tmp_path / "tutor23_live_validation.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")

    now = "2026-09-23T17:00:00Z"
    connection.execute(
        "INSERT INTO courses("
        "id,code,name,status,description,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,?,?,?,NULL)",
        (
            "course-ma",
            "MA103N",
            "Linear Algebra",
            "active",
            "",
            now,
            now,
        ),
    )
    connection.execute(
        "INSERT INTO topics("
        "id,course_id,name,normalized_name,position,status,confidence,"
        "raw_import_status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,?,'not_started',NULL,NULL,?,?,NULL)",
        (
            "topic-lu",
            "course-ma",
            "LU Factorization",
            "lu factorization",
            1,
            now,
            now,
        ),
    )

    metadata = commit_session_goal(
        {},
        {
            "goal": "Understand LU Factorization",
            "status": "active",
            "goal_evidence": (),
            "source": "inferred",
        },
        now=now,
    )
    metadata = commit_teaching_plan(
        metadata,
        {
            "next_move": "practice",
            "reason": "adaptive_practice_answer",
            "goal_status": "active",
            "practice_active": True,
            "practice_level": 3,
            "practice_level_name": "standard_application",
            "practice_format": "computational",
            "practice_focus": "",
            "practice_reason": "adaptive_practice_answer",
            "practice_after_correct_level": 4,
            "practice_after_partial_level": 3,
            "practice_after_incorrect_level": 2,
            "practice_after_unclear_level": 2,
        },
        now=now,
    )
    metadata[STATE_KEY] = {
        "version": 7,
        "interaction_count": 2,
        "last_intent": "quiz_answer",
        "last_teaching_move": "practice",
        "quiz_active": False,
        "awaiting_student_answer": True,
        "pending_question": "What multiplier eliminates the entry below the pivot?",
        "pending_question_kind": "practice",
        "last_student_answer": "2",
        "last_socratic_outcome": "advance",
        "socratic_step_count": 2,
        "practice_active": True,
        "practice_level": 3,
        "practice_step_count": 2,
        "practice_format": "computational",
        "practice_focus": "",
        "exit_check_count": 0,
        "unresolved_doubt": "",
        "answer_status": "correct",
        "last_evaluation_reason": "Correct elimination multiplier.",
        "last_misconception": "",
        "last_math_verification": "not_applicable",
        "last_math_claims_checked": 0,
    }

    repository = SQLiteTutorRepository(connection)
    counters = {"turn": 0, "other": 0}

    def id_factory(prefix):
        if prefix == "tutor-turn":
            counters["turn"] += 1
            return "turn-{}".format(counters["turn"])
        counters["other"] += 1
        return "{}-{}".format(prefix, counters["other"])

    sessions = TutorSessionService(
        repository,
        now=lambda: now,
        id_factory=id_factory,
    )
    session = sessions.create_session(
        TutorSessionSpec(
            mode="doubt",
            source_policy="source_first",
            course_id="course-ma",
            topic_id="topic-lu",
            title="Tutor 2.3.7 live validation fixture",
            metadata=metadata,
        )
    )
    sessions.add_user_turn(
        session.session_id,
        "Give me a computational LU practice problem.",
    )
    sessions.add_assistant_turn(
        session.session_id,
        "What multiplier eliminates the entry below the pivot?",
        support_level="mixed",
        provider_name="fixture-provider",
        provider_model="fixture-model",
    )
    connection.close()
    return path, session.session_id


def test_live_inspector_exposes_complete_tutor23_state(tmp_path):
    path, session_id = _environment(tmp_path)

    payload = inspect_session(path, session_id)

    assert payload["session"]["course"]["code"] == "MA103N"
    assert payload["session"]["topic"]["name"] == "LU Factorization"
    assert payload["session_goal"]["goal"] == "Understand LU Factorization"
    assert payload["session_goal"]["status"] == "active"
    assert payload["teaching_plan"]["next_move"] == "practice"
    assert payload["teaching_plan"]["practice_level"] == 3
    assert payload["current_learning_state"]["pending_question_kind"] == "practice"
    assert payload["current_learning_state"]["practice_level"] == 3
    assert payload["current_learning_state"]["practice_step_count"] == 2
    assert len(payload["recent_turns"]) == 2
    assert payload["all_state_checks_pass"] is True


def test_live_inspector_is_strictly_read_only(tmp_path):
    path, session_id = _environment(tmp_path)
    before = _sha256(path)

    inspect_session(path, session_id)

    after = _sha256(path)
    assert after == before


def test_live_inspector_reports_protected_table_counts(tmp_path):
    path, session_id = _environment(tmp_path)

    payload = inspect_session(path, session_id)

    assert payload["protected_table_counts"]["learning_memory_entries"] == 0
    assert payload["protected_table_counts"]["progress_snapshots"] == 0


def test_live_inspector_recent_turns_include_support_and_provider(tmp_path):
    path, session_id = _environment(tmp_path)

    turns = inspect_session(path, session_id)["recent_turns"]

    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["support_level"] == "mixed"
    assert turns[1]["provider_name"] == "fixture-provider"
    assert turns[1]["provider_model"] == "fixture-model"
    assert turns[1]["evidence_count"] == 0


def test_live_inspector_missing_database_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        inspect_session(
            tmp_path / "missing.db",
            "tutor-session-missing",
        )


def test_live_inspector_flags_inconsistent_pending_state(tmp_path):
    path, session_id = _environment(tmp_path)
    connection = sqlite3.connect(path, isolation_level=None)
    row = connection.execute(
        "SELECT metadata_json FROM tutor_sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    import json

    metadata = json.loads(str(row[0]))
    state = dict(metadata[STATE_KEY])
    state["awaiting_student_answer"] = False
    state["pending_question"] = "Still pending?"
    state["pending_question_kind"] = "practice"
    metadata[STATE_KEY] = state
    connection.execute(
        "UPDATE tutor_sessions SET metadata_json=? WHERE id=?",
        (json.dumps(metadata, sort_keys=True), session_id),
    )
    connection.close()

    payload = inspect_session(path, session_id)
    check = next(
        item
        for item in payload["state_checks"]
        if item["name"] == "pending_question_consistent"
    )

    assert check["ok"] is False
    assert payload["all_state_checks_pass"] is False


def test_live_validation_protocol_requires_disposable_database_and_manual_result():
    root = Path(__file__).resolve().parents[1]
    protocol = (
        root / "ANVAYA_TUTOR_2_3_LIVE_VALIDATION.md"
    ).read_text(encoding="utf-8")

    assert "Do not run live validation against the production database." in protocol
    assert ".live_validation\\tutor23_live.db" in protocol
    assert "all_state_checks_pass = true" in protocol
    assert "I understand span but why does a basis need linear independence?" in protocol
    assert "NOT YET EXECUTED" in protocol
    assert "necessary but is not sufficient by itself" in protocol


def test_fix7_gate_labels_itself_readiness_not_live_pass():
    root = Path(__file__).resolve().parents[1]
    gate = (root / "tutor23_fix7_gate.ps1").read_text(encoding="utf-8")

    assert "ANVAYA TUTOR 2.3.7 LIVE VALIDATION READINESS: PASS" in gate
    assert "LIVE VALIDATION READINESS only" in gate
    assert "ANVAYA_TUTOR_2_3_LIVE_VALIDATION.md" in gate
