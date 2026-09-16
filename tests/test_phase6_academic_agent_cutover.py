from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import date

import pytest

from personal_learning_assistant.domain.adaptive_mentor_models import (
    AdaptiveMentorReport,
    MentorAction,
)
from personal_learning_assistant.domain.tutor_models import TutorSession
from personal_learning_assistant.repositories.sqlite.academic_agent_repository import (
    AcademicAgentAmbiguousTarget,
    AcademicAgentAuthorityError,
    AcademicAgentExecutionConflict,
    SQLiteAcademicAgentRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.services.academic_agent_cutover_service import (
    AcademicAgentConfirmationError,
    AcademicAgentError,
    AcademicAgentService,
    AcademicAgentStaleActionError,
)


NOW = "2026-09-16T20:00:00Z"


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


def _report(action):
    return AdaptiveMentorReport(
        course_id="c1",
        course_code="MA103N",
        course_name="Linear Algebra",
        as_of="2026-09-16",
        target_assessment_id="a-mid",
        target_assessment_title="Mid Semester",
        practice_history_available=True,
        topics=(),
        actions=(action,),
        llm_called=False,
        writes_performed=False,
        authoritative_state_changes=False,
    )


def _action(
    action_type="grounded_tutor",
    *,
    resource_id=None,
    question_id=None,
    assessment_id=None,
    title=None,
):
    return MentorAction(
        sequence=1,
        action_type=action_type,
        topic_id="t-lu",
        topic_name="LU Factorization",
        title=title or "Use the grounded tutor for LU Factorization",
        priority_score=100.0,
        reasons=("confidence is 2/5", "one unresolved mistake exists"),
        resource_id=resource_id,
        question_id=question_id,
        assessment_id=assessment_id,
        source_labels=(
            ("Official PYQ PDF page 2 [Q1]",)
            if question_id
            else ()
        ),
        advisory=True,
    )


class FakeMentor:
    def __init__(self, report):
        self.report = report
        self.calls = []

    def advise(self, course_code, **kwargs):
        self.calls.append((course_code, kwargs))
        return self.report


class FakeTutorSessions:
    def __init__(self):
        self.calls = []

    def create_session(self, spec):
        self.calls.append(spec)
        return TutorSession(
            session_id="tutor-agent-1",
            mode=spec.mode,
            source_policy=spec.source_policy,
            status="active",
            course_id=spec.course_id,
            topic_id=spec.topic_id,
            assessment_id=spec.assessment_id,
            resource_id=spec.resource_id,
            title=spec.title,
            metadata=dict(spec.metadata),
            created_at=NOW,
            updated_at=NOW,
            completed_at=None,
        )


class FakeLectureSnapshot:
    def __init__(self, next_action="resume"):
        self.next_action = next_action
        self.active_session_id = (
            "lecture-active-1" if next_action == "pause_or_checkpoint" else None
        )
        self.current_position = "00:20:00"
        self.status = "paused"


class FakeLectureResult:
    def __init__(self, action):
        self.action = action
        self.segment_id = "lecture-segment-2"
        self.recorded_minutes = 0
        self.snapshot = FakeLectureSnapshot("pause_or_checkpoint")
        self.snapshot.status = "in_progress"


class FakeLectureService:
    def __init__(self, next_action="resume", fail=False):
        self.next_action = next_action
        self.fail = fail
        self.calls = []

    def snapshot(self, resource_id):
        self.calls.append(("snapshot", resource_id))
        return FakeLectureSnapshot(self.next_action)

    def resume(self, resource_id, **kwargs):
        self.calls.append(("resume", resource_id, kwargs))
        if self.fail:
            raise RuntimeError("synthetic lecture failure")
        return FakeLectureResult("resume")

    def start(self, resource_id, **kwargs):
        self.calls.append(("start", resource_id, kwargs))
        if self.fail:
            raise RuntimeError("synthetic lecture failure")
        return FakeLectureResult("start")


class FakePracticeView:
    session_id = "practice-agent-1"
    mode = "active_recall"
    difficulty = "medium"
    topic_id = "t-lu"
    items = (1, 2, 3, 4, 5)


class FakePracticeService:
    def __init__(self):
        self.calls = []

    def generate(self, spec):
        self.calls.append(spec)
        return FakePracticeView()


def _env(tmp_path, action, *, authority=True):
    db = tmp_path / "db.sqlite"
    applied = apply_migrations(db)
    assert applied[:4] == (1, 2, 3, 4)
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
        "VALUES ('t-lu','c1','LU Factorization','lu factorization',1,'learning',2,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resources(id,resource_type,title,canonical_uri,provider,external_id,"
        "status,rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
        "VALUES ('r-l4','external_lecture','MIT Lecture 04','https://ocw.mit.edu/l4',"
        "'mit_ocw','mit-l4','paused',NULL,'',?,?,NULL,NULL,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) "
        "VALUES ('r-l4','c1','supporting')"
    )
    c.execute(
        "INSERT INTO assessments(id,course_id,assessment_type,title,due_on,due_time,status,"
        "weight_bps,max_points_milli,earned_points_milli,description,created_at,updated_at,deleted_at) "
        "VALUES ('a-pyq','c1','pyq','Previous Year Paper',NULL,NULL,'completed',"
        "NULL,NULL,NULL,'',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO note_metadata(id,vault_id,relative_path,path_key,title,note_type,confidence,"
        "revision_status,pinned_at,archived_at,trashed_at,source_hash,file_mtime_ns,"
        "frontmatter_extra_json,created_at,updated_at) "
        "SELECT 'n-lu',v.id,'LU.md','lu.md','My LU Note','note',4,'reviewed',NULL,"
        "NULL,NULL,'h',1,'{}',?,? FROM "
        "(SELECT id FROM vaults LIMIT 1) v",
        (NOW, NOW),
    )
    # Fresh schema has no vault row. Create it and retry note insert explicitly.
    if c.execute("SELECT COUNT(*) FROM note_metadata").fetchone()[0] == 0:
        c.execute(
            "INSERT INTO vaults(id,name,root_path,path_key,enabled,last_scanned_at,created_at,updated_at) "
            "VALUES ('v1','Vault','X:/vault','vault',1,NULL,?,?)",
            (NOW, NOW),
        )
        c.execute(
            "INSERT INTO note_metadata(id,vault_id,relative_path,path_key,title,note_type,confidence,"
            "revision_status,pinned_at,archived_at,trashed_at,source_hash,file_mtime_ns,"
            "frontmatter_extra_json,created_at,updated_at) "
            "VALUES ('n-lu','v1','LU.md','lu.md','My LU Note','note',4,'reviewed',NULL,"
            "NULL,NULL,'h',1,'{}',?,?)",
            (NOW, NOW),
        )
    c.execute(
        "INSERT INTO note_topics(note_id,topic_id,relation_source,confidence) "
        "VALUES ('n-lu','t-lu','manual',1.0)"
    )

    auth = tmp_path / "authority.json"
    _authority(auth, sqlite=authority)
    repo = SQLiteAcademicAgentRepository(
        c,
        authority_control_path=auth,
        now=lambda: NOW,
        id_factory=lambda prefix: "{}-fixed".format(prefix),
    )
    mentor = FakeMentor(_report(action))
    return c, auth, repo, mentor


def test_preview_is_deterministic_and_read_only(tmp_path):
    c, auth, repo, mentor = _env(tmp_path, _action())
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
    )
    before = c.total_changes
    first = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    second = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    assert first == second
    assert c.total_changes == before
    assert first.route == "tutor_session"
    assert first.confirmation_phrase == "EXECUTE_ACADEMIC_AGENT_ACTION"
    c.close()


def test_wrong_confirmation_blocks_before_journal_or_dispatch(tmp_path):
    c, auth, repo, mentor = _env(tmp_path, _action())
    tutor = FakeTutorSessions()
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        tutor_session_service=tutor,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    with pytest.raises(AcademicAgentConfirmationError):
        service.execute(
            "MA103N",
            1,
            expected_fingerprint=plan.fingerprint,
            confirmation="yes",
            as_of=date(2026, 9, 16),
        )
    assert not tutor.calls
    assert c.execute("SELECT COUNT(*) FROM operation_journal").fetchone()[0] == 0
    c.close()


def test_stale_fingerprint_blocks_execution(tmp_path):
    c, auth, repo, mentor = _env(tmp_path, _action())
    tutor = FakeTutorSessions()
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        tutor_session_service=tutor,
    )
    with pytest.raises(AcademicAgentStaleActionError):
        service.execute(
            "MA103N",
            1,
            expected_fingerprint="0" * 64,
            confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
            as_of=date(2026, 9, 16),
        )
    assert not tutor.calls
    c.close()


def test_grounded_tutor_action_creates_scoped_session_once(tmp_path):
    c, auth, repo, mentor = _env(tmp_path, _action())
    tutor = FakeTutorSessions()
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        tutor_session_service=tutor,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    first = service.execute(
        "MA103N",
        1,
        expected_fingerprint=plan.fingerprint,
        confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
        as_of=date(2026, 9, 16),
    )
    assert first.status == "executed"
    assert first.result_type == "tutor_session"
    assert first.provider_called is False
    assert len(tutor.calls) == 1
    spec = tutor.calls[0]
    assert spec.mode == "concept"
    assert spec.source_policy == "source_only"
    assert spec.course_id == "c1"
    assert spec.topic_id == "t-lu"
    assert spec.metadata["agent_action_fingerprint"] == plan.fingerprint

    second = service.execute(
        "MA103N",
        1,
        expected_fingerprint=plan.fingerprint,
        confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
        as_of=date(2026, 9, 16),
    )
    assert second.status == "already_executed"
    assert second.already_executed is True
    assert len(tutor.calls) == 1
    assert c.execute(
        "SELECT COUNT(*) FROM operation_journal WHERE kind='academic_agent_action'"
    ).fetchone()[0] == 1
    assert c.execute(
        "SELECT COUNT(*) FROM outbox_events "
        "WHERE event_type='academic_agent.action_executed'"
    ).fetchone()[0] == 1
    c.close()


def test_continue_lecture_routes_to_resume(tmp_path):
    c, auth, repo, mentor = _env(
        tmp_path,
        _action(
            "continue_lecture",
            resource_id="r-l4",
            title="Continue MIT Lecture 04",
        ),
    )
    lecture = FakeLectureService("resume")
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        lecture_service=lecture,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    result = service.execute(
        "MA103N",
        1,
        expected_fingerprint=plan.fingerprint,
        confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
        as_of=date(2026, 9, 16),
    )
    assert result.result_type == "lecture_session"
    assert any(call[0] == "resume" for call in lecture.calls)
    c.close()


def test_already_active_lecture_does_not_open_duplicate_segment(tmp_path):
    c, auth, repo, mentor = _env(
        tmp_path,
        _action(
            "continue_lecture",
            resource_id="r-l4",
            title="Continue MIT Lecture 04",
        ),
    )
    lecture = FakeLectureService("pause_or_checkpoint")
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        lecture_service=lecture,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    result = service.execute(
        "MA103N",
        1,
        expected_fingerprint=plan.fingerprint,
        confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
        as_of=date(2026, 9, 16),
    )
    assert result.status == "already_active"
    assert not any(call[0] in {"resume", "start"} for call in lecture.calls)
    c.close()


def test_active_recall_dispatches_existing_practice_service(tmp_path):
    c, auth, repo, mentor = _env(
        tmp_path,
        _action(
            "active_recall",
            title="Run source-grounded active recall on LU Factorization",
        ),
    )
    practice = FakePracticeService()
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        practice_service=practice,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    result = service.execute(
        "MA103N",
        1,
        expected_fingerprint=plan.fingerprint,
        confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
        as_of=date(2026, 9, 16),
        practice_item_count=5,
        practice_difficulty="medium",
    )
    assert result.result_type == "practice_session"
    assert result.provider_called is True
    assert len(practice.calls) == 1
    spec = practice.calls[0]
    assert spec.course_id == "c1"
    assert spec.topic_id == "t-lu"
    assert spec.mode == "active_recall"
    assert spec.item_count == 5
    c.close()


def test_pyq_action_creates_exam_session_with_formal_identity(tmp_path):
    c, auth, repo, mentor = _env(
        tmp_path,
        _action(
            "solve_pyq",
            question_id="q-pyq",
            assessment_id="a-pyq",
            title="Solve PYQ: Previous Year Paper",
        ),
    )
    tutor = FakeTutorSessions()
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        tutor_session_service=tutor,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    result = service.execute(
        "MA103N",
        1,
        expected_fingerprint=plan.fingerprint,
        confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
        as_of=date(2026, 9, 16),
    )
    spec = tutor.calls[0]
    assert spec.mode == "exam"
    assert spec.assessment_id == "a-pyq"
    assert spec.metadata["formal_question_id"] == "q-pyq"
    assert "Official PYQ PDF" in spec.metadata["formal_source_labels"][0]
    assert result.provider_called is False
    c.close()


def test_review_note_is_exact_read_only_handoff(tmp_path):
    c, auth, repo, mentor = _env(
        tmp_path,
        _action("review_note", title="Review My LU Note"),
    )
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    assert plan.note_id == "n-lu"
    before = c.total_changes
    result = service.execute(
        "MA103N",
        1,
        expected_fingerprint=plan.fingerprint,
        confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
        as_of=date(2026, 9, 16),
    )
    assert result.status == "handoff"
    assert result.result_type == "note"
    assert result.result_id == "n-lu"
    assert result.writes_performed is False
    assert c.total_changes == before
    assert c.execute("SELECT COUNT(*) FROM operation_journal").fetchone()[0] == 0
    c.close()


def test_ambiguous_note_fails_closed_during_plan(tmp_path):
    c, auth, repo, mentor = _env(
        tmp_path,
        _action("review_note", title="Review My LU Note"),
    )
    c.execute(
        "INSERT INTO note_metadata(id,vault_id,relative_path,path_key,title,note_type,confidence,"
        "revision_status,pinned_at,archived_at,trashed_at,source_hash,file_mtime_ns,"
        "frontmatter_extra_json,created_at,updated_at) "
        "VALUES ('n-lu-2','v1','LU2.md','lu2.md','My LU Note','note',4,'reviewed',"
        "NULL,NULL,NULL,'h2',2,'{}',?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO note_topics(note_id,topic_id,relation_source,confidence) "
        "VALUES ('n-lu-2','t-lu','manual',1.0)"
    )
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
    )
    with pytest.raises(AcademicAgentAmbiguousTarget):
        service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    c.close()


def test_inactive_authority_blocks_mutating_action(tmp_path):
    c, auth, repo, mentor = _env(tmp_path, _action(), authority=False)
    tutor = FakeTutorSessions()
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        tutor_session_service=tutor,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    with pytest.raises(AcademicAgentAuthorityError):
        service.execute(
            "MA103N",
            1,
            expected_fingerprint=plan.fingerprint,
            confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
            as_of=date(2026, 9, 16),
        )
    assert not tutor.calls
    c.close()


def test_synchronous_action_failure_releases_claim_for_safe_retry(tmp_path):
    c, auth, repo, mentor = _env(
        tmp_path,
        _action(
            "continue_lecture",
            resource_id="r-l4",
            title="Continue MIT Lecture 04",
        ),
    )
    lecture = FakeLectureService("resume", fail=True)
    service = AcademicAgentService(
        mentor_service=mentor,
        execution_repository=repo,
        lecture_service=lecture,
    )
    plan = service.plan("MA103N", 1, as_of=date(2026, 9, 16))
    with pytest.raises(RuntimeError, match="synthetic lecture failure"):
        service.execute(
            "MA103N",
            1,
            expected_fingerprint=plan.fingerprint,
            confirmation="EXECUTE_ACADEMIC_AGENT_ACTION",
            as_of=date(2026, 9, 16),
        )
    assert c.execute(
        "SELECT COUNT(*) FROM operation_journal WHERE kind='academic_agent_action'"
    ).fetchone()[0] == 0
    c.close()
