from __future__ import annotations

import json
import sqlite3
from datetime import date

import pytest

from personal_learning_assistant.domain.adaptive_mentor_models import (
    AdaptiveMentorReport,
    MentorAction,
    MentorPracticeSummary,
    MentorTopicState,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_workspace_repository import (
    SQLiteTutorWorkspaceRepository,
)
from personal_learning_assistant.services.phase6_closure_service import (
    Phase6ClosureError,
    Phase6ClosureService,
)
from personal_learning_assistant.services.tutor_workspace_service import (
    TutorWorkspaceService,
)


NOW = "2026-09-16T20:00:00Z"


class FakeMentor:
    def advise(self, course_code, **kwargs):
        practice = MentorPracticeSummary(
            available=True,
            session_count=0,
            completed_session_count=0,
            deterministic_attempt_count=0,
            correct_attempt_count=0,
            incorrect_attempt_count=0,
            advisory_attempt_count=0,
            latest_attempt_at=None,
        )
        topic = MentorTopicState(
            topic_id="t1",
            topic_name="LU Factorization",
            status="learning",
            confidence=2,
            navigator_priority_score=80.0,
            exam_priority_score=50.0,
            combined_priority_score=107.5,
            unresolved_mistake_count=0,
            active_memory_count=0,
            upcoming_assessment_count=1,
            target_assessment_in_scope=False,
            practice=practice,
            reasons=("confidence is 2/5",),
        )
        action = MentorAction(
            sequence=1,
            action_type="active_recall",
            topic_id="t1",
            topic_name="LU Factorization",
            title="Run source-grounded active recall on LU Factorization",
            priority_score=120.0,
            reasons=("no deterministic recall attempt is recorded",),
            advisory=True,
        )
        return AdaptiveMentorReport(
            course_id="c1",
            course_code="MA103N",
            course_name="Linear Algebra",
            as_of=str(kwargs["as_of"]),
            target_assessment_id=None,
            target_assessment_title=None,
            practice_history_available=True,
            topics=(topic,),
            actions=(action,),
            llm_called=False,
            writes_performed=False,
            authoritative_state_changes=False,
        )


def _authority(path, sqlite=True):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "storage_backend": "sqlite" if sqlite else "legacy",
                "cutover_id": "cut" if sqlite else "",
                "source_manifest_hash": "a" * 64 if sqlite else "",
                "sqlite_sha256": "b" * 64 if sqlite else "",
                "promoted_at": NOW if sqlite else "",
                "legacy_writes_blocked": bool(sqlite),
            }
        ),
        encoding="utf-8",
    )


def _env(tmp_path, *, sqlite_authority=True):
    db = tmp_path / "db.sqlite"
    applied = apply_migrations(db)
    assert applied[:4] == (1, 2, 3, 4)
    assert apply_migrations(db) == ()

    c = sqlite3.connect(str(db), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")

    c.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
        "confidence,raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t1','c1','LU Factorization','lu factorization',1,'learning',2,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resources(id,resource_type,title,canonical_uri,provider,external_id,status,"
        "rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
        "VALUES ('r1','external_lecture','MIT Lecture 04','https://ocw.mit.edu/l4',"
        "'mit_ocw','mit-l4','in_progress',NULL,'',?,?,NULL,NULL,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) "
        "VALUES ('r1','c1','supporting')"
    )
    c.execute(
        "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
        "VALUES ('r1','t1','reviewed',1.0)"
    )
    c.execute(
        "INSERT INTO assessments(id,course_id,assessment_type,title,due_on,due_time,status,"
        "weight_bps,max_points_milli,earned_points_milli,description,created_at,updated_at,deleted_at) "
        "VALUES ('a1','c1','mid_semester','Mid Semester','2026-09-20',NULL,'pending',"
        "NULL,NULL,NULL,'',?,?,NULL)",
        (NOW, NOW),
    )

    auth = tmp_path / "authority.json"
    _authority(auth, sqlite=sqlite_authority)

    repo = SQLiteTutorWorkspaceRepository(c)
    workspace = TutorWorkspaceService(
        repository=repo,
        mentor_service=FakeMentor(),
    )
    return c, auth, repo, workspace


def _closure(c, auth, workspace, *, hits=1):
    def probe(course_id, query):
        return {
            "generation_id": "g1",
            "source_fingerprint": "f1",
            "lexical_backend": "fts5",
            "semantic_enabled": False,
            "hit_count": hits,
            "hit_chunk_ids": ("k1",) if hits else (),
        }

    return Phase6ClosureService(
        c,
        authority_control_path=auth,
        index_root="unused",
        workspace_service=workspace,
        retrieval_probe=probe,
    )


def test_workspace_unifies_mentor_and_runtime_counts_read_only(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    c.execute(
        "INSERT INTO tutor_sessions(id,course_id,topic_id,assessment_id,resource_id,"
        "mode,source_policy,status,title,metadata_json,created_at,updated_at,completed_at) "
        "VALUES ('ts1','c1','t1',NULL,NULL,'concept','source_only','active',"
        "'LU tutor','{}',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO study_sessions(id,started_at,ended_at,duration_minutes,course_id,"
        "topic_id,resource_id,assessment_id,note_id,plan_item_id,outcome,confidence,note,created_at) "
        "VALUES ('ss1',?,NULL,0,'c1','t1','r1',NULL,NULL,NULL,'',NULL,'',?)",
        (NOW, NOW),
    )
    before = c.total_changes
    snapshot = workspace.snapshot("MA103N", as_of=date(2026, 9, 16))
    assert c.total_changes == before
    assert snapshot.tutor_schema_ready is True
    assert snapshot.practice_schema_ready is True
    assert snapshot.counts.active_tutor_session_count == 1
    assert snapshot.counts.active_lecture_segment_count == 1
    assert len(snapshot.mentor.actions) == 1
    assert snapshot.writes_performed is False
    assert snapshot.provider_called is False
    c.close()


def test_workspace_recent_activity_keeps_tutor_and_lecture_identity(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    c.execute(
        "INSERT INTO tutor_sessions(id,course_id,topic_id,assessment_id,resource_id,"
        "mode,source_policy,status,title,metadata_json,created_at,updated_at,completed_at) "
        "VALUES ('ts1','c1','t1',NULL,NULL,'concept','source_only','active',"
        "'LU tutor','{}',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO study_sessions(id,started_at,ended_at,duration_minutes,course_id,"
        "topic_id,resource_id,assessment_id,note_id,plan_item_id,outcome,confidence,note,created_at) "
        "VALUES ('ss1',?,NULL,0,'c1','t1','r1',NULL,NULL,NULL,'',NULL,'',?)",
        (NOW, NOW),
    )
    snapshot = workspace.snapshot("MA103N", as_of=date(2026, 9, 16))
    kinds = {item.activity_type for item in snapshot.recent_activity}
    assert {"tutor_session", "lecture_segment"}.issubset(kinds)
    lecture = next(
        item
        for item in snapshot.recent_activity
        if item.activity_type == "lecture_segment"
    )
    assert lecture.resource_id == "r1"
    assert lecture.topic_id == "t1"
    c.close()


def test_clean_closure_passes_and_is_read_only(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    before = c.total_changes
    report = _closure(c, auth, workspace).verify(
        "MA103N",
        as_of=date(2026, 9, 16),
    )
    assert c.total_changes == before
    assert report["issue_count"] == 0
    assert report["schema"]["migration_versions"][:4] == (1, 2, 3, 4)
    assert report["retrieval"]["hit_count"] == 1
    assert report["authority"]["sqlite_authoritative"] is True
    c.close()


def test_legacy_authority_blocks_final_closure(tmp_path):
    c, auth, repo, workspace = _env(tmp_path, sqlite_authority=False)
    with pytest.raises(Phase6ClosureError, match="SQLite is not"):
        _closure(c, auth, workspace).verify(
            "MA103N",
            as_of=date(2026, 9, 16),
        )
    c.close()


def test_grounded_tutor_turn_without_evidence_blocks_closure(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    c.execute(
        "INSERT INTO tutor_sessions(id,course_id,topic_id,assessment_id,resource_id,"
        "mode,source_policy,status,title,metadata_json,created_at,updated_at,completed_at) "
        "VALUES ('ts1','c1','t1',NULL,NULL,'concept','source_only','active',"
        "'LU tutor','{}',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO tutor_turns(id,session_id,ordinal,role,content,support_level,"
        "provider_name,provider_model,created_at) "
        "VALUES ('turn1','ts1',1,'assistant','answer','grounded','fake','fake',?)",
        (NOW,),
    )
    with pytest.raises(Phase6ClosureError, match="lack exact chunk evidence"):
        _closure(c, auth, workspace).verify(
            "MA103N",
            as_of=date(2026, 9, 16),
        )
    c.close()


def test_practice_item_without_source_blocks_closure(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    c.execute(
        "INSERT INTO practice_sessions(id,tutor_session_id,course_id,topic_id,resource_id,"
        "mode,difficulty,status,source_query,source_policy,requested_item_count,"
        "generation_provider,generation_model,provider_request_id,created_at,completed_at) "
        "VALUES ('ps1',NULL,'c1','t1',NULL,'fast_quiz','medium','active','LU',"
        "'source_only',1,'fake','fake','req',?,NULL)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO practice_items(id,session_id,ordinal,item_type,prompt,options_json,"
        "answer_key_json,explanation,created_at) "
        "VALUES ('pi1','ps1',1,'single_choice','Q?','[]','{}','E',?)",
        (NOW,),
    )
    with pytest.raises(Phase6ClosureError, match="no exact source chunk"):
        _closure(c, auth, workspace).verify(
            "MA103N",
            as_of=date(2026, 9, 16),
        )
    c.close()


def test_duplicate_open_lecture_segments_block_closure(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    for sid in ("ss1", "ss2"):
        c.execute(
            "INSERT INTO study_sessions(id,started_at,ended_at,duration_minutes,course_id,"
            "topic_id,resource_id,assessment_id,note_id,plan_item_id,outcome,confidence,note,created_at) "
            "VALUES (?, ?,NULL,0,'c1','t1','r1',NULL,NULL,NULL,'',NULL,'',?)",
            (sid, NOW, NOW),
        )
    with pytest.raises(Phase6ClosureError, match="multiple simultaneously open"):
        _closure(c, auth, workspace).verify(
            "MA103N",
            as_of=date(2026, 9, 16),
        )
    c.close()


def test_planned_agent_claim_blocks_closure(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    c.execute(
        "INSERT INTO operation_journal(id,kind,target_path,before_hash,after_hash,state,"
        "error,created_at,updated_at) "
        "VALUES ('oj1','academic_agent_action','fp','fp',NULL,'planned',NULL,?,?)",
        (NOW, NOW),
    )
    with pytest.raises(Phase6ClosureError, match="remain planned"):
        _closure(c, auth, workspace).verify(
            "MA103N",
            as_of=date(2026, 9, 16),
        )
    c.close()


def test_completed_agent_action_requires_matching_outbox(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    c.execute(
        "INSERT INTO operation_journal(id,kind,target_path,before_hash,after_hash,state,"
        "error,created_at,updated_at) "
        "VALUES ('oj1','academic_agent_action','fp','fp','after','completed',NULL,?,?)",
        (NOW, NOW),
    )
    with pytest.raises(Phase6ClosureError, match="lack execution outbox"):
        _closure(c, auth, workspace).verify(
            "MA103N",
            as_of=date(2026, 9, 16),
        )
    c.close()


def test_retrieval_smoke_must_return_course_grounded_hit(tmp_path):
    c, auth, repo, workspace = _env(tmp_path)
    with pytest.raises(Phase6ClosureError, match="no course-grounded hit"):
        _closure(c, auth, workspace, hits=0).verify(
            "MA103N",
            as_of=date(2026, 9, 16),
        )
    c.close()
