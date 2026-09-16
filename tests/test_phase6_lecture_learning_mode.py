from __future__ import annotations

import json
import sqlite3

import pytest

from personal_learning_assistant.repositories.sqlite.lecture_learning_repository import (
    LectureLearningAuthorityError,
    SQLiteLectureLearningRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.services.lecture_learning_service import (
    LectureLearningError,
    LectureLearningService,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)


T0 = "2026-09-16T10:00:00Z"
T1 = "2026-09-16T10:25:30Z"
T2 = "2026-09-16T11:00:00Z"
T3 = "2026-09-16T11:40:00Z"


def _ids():
    values = {}

    def make(prefix):
        values[prefix] = values.get(prefix, 0) + 1
        return "{}-{}".format(prefix, values[prefix])

    return make


def _clock(*values):
    queue = list(values)

    def now():
        if not queue:
            raise AssertionError("test clock exhausted")
        return queue.pop(0)

    return now


def _authority(path, *, sqlite=True):
    payload = {
        "version": 1,
        "storage_backend": "sqlite" if sqlite else "legacy",
        "cutover_id": "test-cutover" if sqlite else "",
        "source_manifest_hash": "a" * 64 if sqlite else "",
        "sqlite_sha256": "b" * 64 if sqlite else "",
        "promoted_at": "2026-09-15T14:34:05Z" if sqlite else "",
        "legacy_writes_blocked": bool(sqlite),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _env(tmp_path, *, times=(T0, T1, T2, T3), two_topics=False):
    db = tmp_path / "db.sqlite"
    apply_migrations(db)
    c = sqlite3.connect(str(db), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")

    c.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (T0, T0),
    )
    c.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
        "confidence,raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t1','c1','LU Factorization','lu factorization',1,'learning',2,NULL,?,?,NULL)",
        (T0, T0),
    )
    if two_topics:
        c.execute(
            "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
            "confidence,raw_import_status,created_at,updated_at,deleted_at) "
            "VALUES ('t2','c1','Matrix Inverse','matrix inverse',2,'learning',3,NULL,?,?,NULL)",
            (T0, T0),
        )

    c.execute(
        "INSERT INTO resources(id,resource_type,title,canonical_uri,provider,external_id,status,"
        "rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
        "VALUES ('r1','external_lecture','MIT 18.06 L04 — Factorization into A = LU',"
        "'https://ocw.mit.edu/l4','mit_ocw','mit-l04','not_started',NULL,'',"
        "?,?,NULL,NULL,NULL)",
        (T0, T0),
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) "
        "VALUES ('r1','c1','supporting')"
    )
    c.execute(
        "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
        "VALUES ('r1','t1','imported',1.0)"
    )
    if two_topics:
        c.execute(
            "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
            "VALUES ('r1','t2','imported',1.0)"
        )

    c.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,content_hash,"
        "size_bytes,source_timestamp,extraction_status,extraction_version,extraction_error,"
        "created_at,updated_at) VALUES "
        "('d1','external_course_chunks',NULL,'mit/chunks.jsonl','application/x-ndjson','h1',"
        "100,NULL,'completed','v1',NULL,?,?)",
        (T0, T0),
    )
    c.execute(
        "INSERT INTO resource_documents(resource_id,document_id,role) "
        "VALUES ('r1','d1','source')"
    )
    c.execute(
        "INSERT INTO knowledge_chunks(id,document_id,ordinal,page_number,char_start,char_end,"
        "chunk_type,text_hash,extraction_version,chunk_text) "
        "VALUES ('k1','d1',0,NULL,0,10,'text','th1','v1','LU evidence')"
    )

    authority = tmp_path / "authority.json"
    _authority(authority)
    repo = SQLiteLectureLearningRepository(
        c, authority_control_path=authority
    )
    service = LectureLearningService(
        repo,
        now=_clock(*times),
        id_factory=_ids(),
    )
    return c, authority, repo, service


def test_initial_snapshot_is_read_only(tmp_path):
    c, authority, repo, service = _env(tmp_path)
    before = c.total_changes
    snapshot = service.snapshot("r1")
    assert c.total_changes == before
    assert snapshot.status == "not_started"
    assert snapshot.next_action == "start"
    assert snapshot.current_chunk_count == 1
    assert snapshot.total_study_minutes == 0
    c.close()


def test_start_creates_open_study_session_and_progress_event(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0,))
    result = service.start(
        "r1",
        position="00:00:00",
        value=0,
        max_value=60,
        unit="minutes",
    )
    assert result.action == "start"
    assert result.snapshot.status == "in_progress"
    assert result.snapshot.active_session_id == "lecture-session-1"
    assert result.snapshot.current_position == "00:00:00"
    assert c.execute(
        "SELECT COUNT(*) FROM study_sessions WHERE ended_at IS NULL"
    ).fetchone()[0] == 1
    assert c.execute(
        "SELECT COUNT(*) FROM resource_progress_events"
    ).fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 1
    c.close()


def test_duplicate_start_is_blocked(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0,))
    service.start("r1")
    with pytest.raises(LectureLearningError, match="active study session"):
        service.start("r1")
    c.close()


def test_checkpoint_updates_position_without_closing_segment(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0, T1))
    service.start("r1", position="00:00:00", value=0, max_value=60, unit="minutes")
    result = service.checkpoint(
        "r1",
        position="00:18:30",
        value=18.5,
    )
    assert result.snapshot.current_position == "00:18:30"
    assert result.snapshot.progress_value == 18.5
    assert result.snapshot.active_session_id == "lecture-session-1"
    assert c.execute(
        "SELECT ended_at FROM study_sessions WHERE id='lecture-session-1'"
    ).fetchone()[0] is None
    c.close()


def test_pause_records_only_explicit_elapsed_time(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0, T1))
    service.start("r1")
    result = service.pause("r1", position="00:25:30")
    assert result.recorded_minutes == 25
    assert result.snapshot.status == "paused"
    assert result.snapshot.total_study_minutes == 25
    assert result.snapshot.next_action == "resume"
    row = c.execute(
        "SELECT ended_at,duration_minutes,outcome FROM study_sessions "
        "WHERE id='lecture-session-1'"
    ).fetchone()
    assert row["ended_at"] == T1
    assert row["duration_minutes"] == 25
    assert row["outcome"] == "paused"
    c.close()


def test_resume_starts_new_segment_and_carries_position(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0, T1, T2))
    service.start("r1", position="00:00:00")
    service.pause("r1", position="00:25:30")
    result = service.resume("r1")
    assert result.action == "resume"
    assert result.snapshot.current_position == "00:25:30"
    assert result.snapshot.active_session_id == "lecture-session-2"
    assert result.snapshot.segment_count == 2
    c.close()


def test_finish_closes_active_segment_and_completes_resource(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0, T1))
    service.start("r1", value=0, max_value=60, unit="minutes")
    result = service.finish(
        "r1",
        position="01:00:00",
        value=60,
        confidence=4,
        note="Completed lecture and understood LU.",
    )
    assert result.recorded_minutes == 25
    assert result.snapshot.status == "completed"
    assert result.snapshot.next_action == "completed"
    assert result.snapshot.total_study_minutes == 25
    row = c.execute(
        "SELECT confidence,outcome FROM study_sessions "
        "WHERE id='lecture-session-1'"
    ).fetchone()
    assert row["confidence"] == 4
    assert row["outcome"] == "completed"
    resource = c.execute(
        "SELECT status,completed_at FROM resources WHERE id='r1'"
    ).fetchone()
    assert resource["status"] == "completed"
    assert resource["completed_at"] == T1
    c.close()


def test_finish_from_paused_state_does_not_invent_extra_minutes(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0, T1, T2))
    service.start("r1")
    service.pause("r1", position="00:25:30")
    result = service.finish("r1", position="01:00:00")
    assert result.recorded_minutes == 0
    assert result.snapshot.total_study_minutes == 25
    assert result.snapshot.status == "completed"
    c.close()


def test_finish_is_idempotent_after_completion(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0, T1))
    service.start("r1")
    service.finish("r1")
    before = c.total_changes
    result = service.finish("r1")
    assert c.total_changes == before
    assert result.snapshot.status == "completed"
    c.close()


def test_multiple_topic_links_are_not_guessed(tmp_path):
    c, authority, repo, service = _env(
        tmp_path, times=(T0,), two_topics=True
    )
    service.start("r1")
    row = c.execute(
        "SELECT course_id,topic_id FROM study_sessions "
        "WHERE id='lecture-session-1'"
    ).fetchone()
    assert row["course_id"] == "c1"
    assert row["topic_id"] is None
    c.close()


def test_single_topic_link_is_inferred_without_guessing(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0,))
    service.start("r1")
    row = c.execute(
        "SELECT course_id,topic_id FROM study_sessions "
        "WHERE id='lecture-session-1'"
    ).fetchone()
    assert row["course_id"] == "c1"
    assert row["topic_id"] == "t1"
    c.close()


def test_inactive_authority_blocks_writes_before_mutation(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0,))
    _authority(authority, sqlite=False)
    before = c.total_changes
    with pytest.raises(LectureLearningAuthorityError):
        service.start("r1")
    assert c.total_changes == before
    assert c.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0] == 0
    c.close()


def test_progress_validation_blocks_impossible_value(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0,))
    with pytest.raises(LectureLearningError, match="cannot exceed"):
        service.start("r1", value=61, max_value=60, unit="minutes")
    c.close()


def test_lecture_actions_do_not_mutate_mastery_memory_or_plans(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0, T1))
    tracked = (
        "topic_progress_events",
        "learning_memory_entries",
        "study_plans",
        "study_plan_items",
        "question_attempts",
        "mistake_events",
    )
    before = {
        table: c.execute(
            'SELECT COUNT(*) FROM "{}"'.format(table)
        ).fetchone()[0]
        for table in tracked
    }
    service.start("r1")
    service.pause("r1")
    after = {
        table: c.execute(
            'SELECT COUNT(*) FROM "{}"'.format(table)
        ).fetchone()[0]
        for table in tracked
    }
    assert after == before
    c.close()


def test_lecture_tutor_session_is_resource_scoped(tmp_path):
    c, authority, repo, service = _env(tmp_path, times=(T0,))
    tutor_repo = SQLiteTutorRepository(c)
    tutor_sessions = TutorSessionService(
        tutor_repo,
        now=lambda: T0,
        id_factory=_ids(),
    )
    session = service.lecture_tutor_session(
        "r1",
        tutor_sessions,
        source_policy="source_only",
    )
    assert session.mode == "lecture"
    assert session.course_id == "c1"
    assert session.topic_id == "t1"
    assert session.resource_id == "r1"
    assert session.metadata["origin"] == "phase6.4_lecture_learning"
    c.close()
