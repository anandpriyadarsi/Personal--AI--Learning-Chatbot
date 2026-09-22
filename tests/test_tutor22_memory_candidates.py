from __future__ import annotations

import sqlite3

import pytest

from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.tutor.memory_candidates import (
    TutorMemoryCandidateError,
    list_memory_candidates,
    propose_memory_candidate,
    review_memory_candidate,
)


def _database(tmp_path):
    path = tmp_path / "tutor22_candidates.db"
    applied = apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "INSERT INTO courses("
        "id,code,name,status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,'active',?,?,NULL)",
        (
            "course-ma",
            "MA103N",
            "Linear Algebra",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO topics("
        "id,course_id,name,normalized_name,position,status,confidence,"
        "raw_import_status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,1,'active',3,NULL,?,?,NULL)",
        (
            "topic-lu",
            "course-ma",
            "LU Factorization",
            "lu factorization",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
        ),
    )
    return connection, applied


def _signal(
    *,
    kind="misconception",
    text="Confuses L with the matrix after elimination.",
    sessions=2,
    events=2,
    first="2026-09-20T10:00:00Z",
    last="2026-09-22T18:00:00Z",
    provenance=("s1:t1", "s2:t8"),
):
    return {
        "kind": kind,
        "text": text,
        "course_id": "course-ma",
        "topic_id": "topic-lu",
        "event_count": events,
        "session_count": sessions,
        "first_observed_at": first,
        "last_observed_at": last,
        "provenance": tuple(provenance),
    }


def _memory_count(connection):
    return connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]


def test_fresh_migration_includes_tutor_memory_candidate_schema(tmp_path):
    connection, applied = _database(tmp_path)

    assert applied[-1] == 9
    columns = {
        str(row["name"])
        for row in connection.execute(
            "PRAGMA table_info(tutor_memory_candidates)"
        ).fetchall()
    }
    assert {
        "id",
        "course_id",
        "topic_id",
        "signal_kind",
        "candidate_kind",
        "candidate_text",
        "confidence",
        "evidence_count",
        "session_count",
        "provenance_json",
        "status",
        "accepted_memory_entry_id",
        "review_note",
        "reviewed_at",
    }.issubset(columns)
    connection.close()


def test_proposal_requires_cross_session_evidence(tmp_path):
    connection, _applied = _database(tmp_path)

    with pytest.raises(TutorMemoryCandidateError):
        propose_memory_candidate(
            connection,
            _signal(sessions=1, events=3, provenance=("s1:t1",)),
            now="2026-09-23T00:00:00Z",
        )

    assert connection.execute(
        "SELECT COUNT(*) FROM tutor_memory_candidates"
    ).fetchone()[0] == 0
    assert _memory_count(connection) == 0
    connection.close()


def test_propose_creates_candidate_but_not_learning_memory(tmp_path):
    connection, _applied = _database(tmp_path)

    candidate = propose_memory_candidate(
        connection,
        _signal(),
        now="2026-09-23T00:00:00Z",
    )

    assert candidate["status"] == "proposed"
    assert candidate["candidate_kind"] == "misconception"
    assert candidate["confidence"] == 3
    assert candidate["session_count"] == 2
    assert candidate["evidence_count"] == 2
    assert candidate["provenance"] == ("s1:t1", "s2:t8")
    assert "Recurring misconception:" in candidate["candidate_text"]
    assert _memory_count(connection) == 0
    connection.close()


def test_exact_reproposal_is_idempotent(tmp_path):
    connection, _applied = _database(tmp_path)
    signal = _signal()

    first = propose_memory_candidate(
        connection,
        signal,
        now="2026-09-23T00:00:00Z",
    )
    second = propose_memory_candidate(
        connection,
        signal,
        now="2026-09-23T00:05:00Z",
    )

    assert first["id"] == second["id"]
    assert connection.execute(
        "SELECT COUNT(*) FROM tutor_memory_candidates"
    ).fetchone()[0] == 1
    assert _memory_count(connection) == 0
    connection.close()


def test_newer_evidence_supersedes_older_proposed_candidate(tmp_path):
    connection, _applied = _database(tmp_path)

    first = propose_memory_candidate(
        connection,
        _signal(),
        now="2026-09-23T00:00:00Z",
    )
    second = propose_memory_candidate(
        connection,
        _signal(
            sessions=3,
            events=4,
            last="2026-09-23T08:00:00Z",
            provenance=("s1:t1", "s2:t8", "s3:t4"),
        ),
        now="2026-09-23T08:05:00Z",
    )

    old = connection.execute(
        "SELECT status,reviewed_at FROM tutor_memory_candidates WHERE id=?",
        (first["id"],),
    ).fetchone()
    assert str(old["status"]) == "superseded"
    assert str(old["reviewed_at"]) == "2026-09-23T08:05:00Z"
    assert second["status"] == "proposed"
    assert second["supersedes_candidate_id"] == first["id"]
    assert second["confidence"] == 5
    assert _memory_count(connection) == 0
    connection.close()


def test_reject_keeps_authoritative_memory_unchanged(tmp_path):
    connection, _applied = _database(tmp_path)
    candidate = propose_memory_candidate(
        connection,
        _signal(kind="hint_requested", text=""),
        now="2026-09-23T00:00:00Z",
    )

    reviewed = review_memory_candidate(
        connection,
        candidate["id"],
        action="reject",
        review_note="This was caused by a difficult one-off exercise.",
        now="2026-09-23T00:10:00Z",
    )

    assert reviewed["status"] == "rejected"
    assert reviewed["accepted_memory_entry_id"] is None
    assert "one-off exercise" in reviewed["review_note"]
    assert _memory_count(connection) == 0
    connection.close()


def test_accept_creates_exactly_one_provenance_linked_memory_entry(tmp_path):
    connection, _applied = _database(tmp_path)
    candidate = propose_memory_candidate(
        connection,
        _signal(),
        now="2026-09-23T00:00:00Z",
    )

    reviewed = review_memory_candidate(
        connection,
        candidate["id"],
        action="accept",
        review_note="Keep this as a long-term learning reminder.",
        now="2026-09-23T00:10:00Z",
    )

    assert reviewed["status"] == "accepted"
    assert reviewed["accepted_memory_entry_id"]
    assert _memory_count(connection) == 1

    memory = connection.execute(
        "SELECT * FROM learning_memory_entries WHERE id=?",
        (reviewed["accepted_memory_entry_id"],),
    ).fetchone()
    assert str(memory["scope_type"]) == "course"
    assert str(memory["scope_id"]) == "course-ma"
    assert str(memory["topic_id"]) == "topic-lu"
    assert str(memory["raw_topic"]) == "LU Factorization"
    assert str(memory["kind"]) == "misconception"
    assert str(memory["source_entity_type"]) == "tutor_memory_candidate"
    assert str(memory["source_entity_id"]) == candidate["id"]
    assert str(memory["memory_text"]) == candidate["candidate_text"]
    connection.close()


def test_review_is_single_use_and_cannot_duplicate_memory(tmp_path):
    connection, _applied = _database(tmp_path)
    candidate = propose_memory_candidate(
        connection,
        _signal(),
        now="2026-09-23T00:00:00Z",
    )
    review_memory_candidate(
        connection,
        candidate["id"],
        action="accept",
        now="2026-09-23T00:10:00Z",
    )

    with pytest.raises(TutorMemoryCandidateError):
        review_memory_candidate(
            connection,
            candidate["id"],
            action="accept",
            now="2026-09-23T00:20:00Z",
        )

    assert _memory_count(connection) == 1
    connection.close()


def test_candidate_listing_respects_topic_scope(tmp_path):
    connection, _applied = _database(tmp_path)
    connection.execute(
        "INSERT INTO topics("
        "id,course_id,name,normalized_name,position,status,confidence,"
        "raw_import_status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,2,'active',3,NULL,?,?,NULL)",
        (
            "topic-basis",
            "course-ma",
            "Basis",
            "basis",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
        ),
    )

    propose_memory_candidate(
        connection,
        _signal(),
        now="2026-09-23T00:00:00Z",
    )
    basis = dict(_signal())
    basis["topic_id"] = "topic-basis"
    basis["text"] = "Thinks spanning alone guarantees a basis."
    propose_memory_candidate(
        connection,
        basis,
        now="2026-09-23T00:01:00Z",
    )

    lu = list_memory_candidates(
        connection,
        course_id="course-ma",
        topic_id="topic-lu",
    )
    all_course = list_memory_candidates(
        connection,
        course_id="course-ma",
    )

    assert len(lu) == 1
    assert lu[0]["topic_id"] == "topic-lu"
    assert len(all_course) == 2
    connection.close()


def test_candidate_ui_requires_explicit_propose_accept_or_reject():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")
    routes = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "routes.py"
    ).read_text(encoding="utf-8")

    assert "Propose memory" in template
    assert "Accept memory" in template
    assert "Reject" in template
    assert "Stable patterns become long-term memory only after explicit acceptance." in template
    assert "academic_agent_memory_candidate_propose" in routes
    assert "academic_agent_memory_candidate_review" in routes
