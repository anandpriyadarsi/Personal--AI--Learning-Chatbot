from __future__ import annotations

import sqlite3

import pytest

from personal_learning_assistant.domain.retrieval_models import RetrievalHit
from personal_learning_assistant.domain.tutor_models import (
    TutorEvidence,
    TutorSessionSpec,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
    TutorRepositoryError,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionError,
    TutorSessionService,
)
from personal_learning_assistant.tutor.policy import get_mode_policy
from personal_learning_assistant.tutor.provider import (
    DisabledTutorProvider,
    TutorProviderUnavailableError,
)


NOW = "2026-09-16T18:00:00Z"


def _ids():
    counters = {}

    def make(prefix):
        counters[prefix] = counters.get(prefix, 0) + 1
        return "{}-{}".format(prefix, counters[prefix])

    return make


def _env(tmp_path):
    db = tmp_path / "learning_assistant.db"
    applied = apply_migrations(db)
    assert applied[:3] == (1, 2, 3)
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
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c2','UC100N','Data Science','active','',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
        "confidence,raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t1','c1','LU Factorisation','lu factorisation',1,'learning',"
        "2,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
        "confidence,raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t2','c2','Pandas','pandas',1,'not_started',NULL,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resources(id,resource_type,title,canonical_uri,provider,external_id,"
        "status,rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
        "VALUES ('r1','external_lecture','MIT L04','https://ocw.mit.edu/l4','mit_ocw',"
        "'mit-l4','in_progress',NULL,'',?,?,NULL,NULL,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) "
        "VALUES ('r1','c1','supporting')"
    )
    c.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,"
        "content_hash,size_bytes,source_timestamp,extraction_status,extraction_version,"
        "extraction_error,created_at,updated_at) "
        "VALUES ('d1','external_course_chunks',NULL,'mit/chunks.jsonl','application/x-ndjson',"
        "'hash1',100,NULL,'completed','v1',NULL,?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO knowledge_chunks(id,document_id,ordinal,page_number,char_start,char_end,"
        "chunk_type,text_hash,extraction_version,chunk_text) "
        "VALUES ('k1','d1',0,NULL,0,10,'text','th1','v1','LU factorization evidence')"
    )

    repo = SQLiteTutorRepository(c)
    service = TutorSessionService(repo, now=lambda: NOW, id_factory=_ids())
    return db, c, repo, service


def _session(service):
    return service.create_session(
        TutorSessionSpec(
            mode="concept",
            source_policy="source_first",
            course_id="c1",
            topic_id="t1",
            resource_id="r1",
            title="LU help",
            metadata={"origin": "test"},
        )
    )


def _evidence():
    return (
        TutorEvidence(
            chunk_id="k1",
            document_id="d1",
            ordinal=1,
            relation_type="support",
            retrieval_score=0.9,
            citation_label="S1",
        ),
    )


def test_migration_0003_is_applied_and_idempotent(tmp_path):
    db, c, _repo, _service = _env(tmp_path)
    versions = tuple(
        row[0]
        for row in c.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    )
    assert versions[:3] == (1, 2, 3)
    tables = {
        row[0]
        for row in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "tutor_sessions",
        "tutor_turns",
        "tutor_evidence_links",
        "tutor_feedback",
    }.issubset(tables)
    c.close()


def test_repository_rejects_incomplete_schema():
    c = sqlite3.connect(":memory:")
    with pytest.raises(TutorRepositoryError, match="tutor tables missing"):
        SQLiteTutorRepository(c)
    c.close()


def test_create_scoped_session(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    assert session.mode == "concept"
    assert session.course_id == "c1"
    assert session.topic_id == "t1"
    assert session.resource_id == "r1"
    assert session.metadata == {"origin": "test"}
    c.close()


def test_topic_course_mismatch_is_rejected(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    with pytest.raises(TutorSessionError, match="topic does not belong"):
        service.create_session(
            TutorSessionSpec(
                mode="concept",
                course_id="c1",
                topic_id="t2",
            )
        )
    c.close()


def test_resource_course_mismatch_is_rejected(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    with pytest.raises(TutorSessionError, match="resource is not related"):
        service.create_session(
            TutorSessionSpec(
                mode="lecture",
                course_id="c2",
                resource_id="r1",
            )
        )
    c.close()


def test_user_and_grounded_assistant_turns_are_ordered(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    user = service.add_user_turn(session.session_id, "Explain LU")
    assistant = service.add_assistant_turn(
        session.session_id,
        "Grounded explanation",
        support_level="grounded",
        evidence=_evidence(),
        provider_name="fake",
        provider_model="test-model",
    )
    assert user.ordinal == 1
    assert assistant.ordinal == 2
    assert assistant.evidence[0].chunk_id == "k1"
    assert assistant.evidence[0].citation_label == "S1"
    assert [turn.role for turn in service.transcript(session.session_id)] == [
        "user",
        "assistant",
    ]
    c.close()


def test_grounded_turn_without_evidence_is_rejected(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    with pytest.raises(TutorSessionError, match="requires evidence"):
        service.add_assistant_turn(
            session.session_id,
            "Unsupported grounded answer",
            support_level="grounded",
        )
    c.close()


def test_insufficient_turn_may_have_no_evidence(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    turn = service.add_assistant_turn(
        session.session_id,
        "The available sources are insufficient.",
        support_level="insufficient",
    )
    assert turn.evidence == ()
    c.close()


def test_bad_evidence_document_rolls_back_whole_assistant_turn(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    bad = (
        TutorEvidence(
            chunk_id="k1",
            document_id="wrong-document",
            ordinal=1,
            citation_label="S1",
        ),
    )
    with pytest.raises(TutorRepositoryError, match="chunk/document mismatch"):
        service.add_assistant_turn(
            session.session_id,
            "Should roll back",
            support_level="grounded",
            evidence=bad,
        )
    count = c.execute(
        "SELECT COUNT(*) FROM tutor_turns WHERE session_id=?",
        (session.session_id,),
    ).fetchone()[0]
    assert count == 0
    c.close()


def test_evidence_ordinals_must_be_contiguous(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    bad = (
        TutorEvidence(
            chunk_id="k1",
            document_id="d1",
            ordinal=2,
            citation_label="S2",
        ),
    )
    with pytest.raises(TutorSessionError, match="contiguous"):
        service.add_assistant_turn(
            session.session_id,
            "Bad ordering",
            support_level="grounded",
            evidence=bad,
        )
    c.close()


def test_evidence_can_be_created_from_phase5_retrieval_hits(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    hit = RetrievalHit(
        chunk_id="k1",
        document_id="d1",
        text="LU factorization evidence",
        score=0.75,
        lexical_rank=1,
        semantic_rank=None,
        page_number=None,
        locator={"lecture_number": "04"},
        resource_ids=("r1",),
        course_ids=("c1",),
        topic_ids=("t1",),
        providers=("mit_ocw",),
    )
    evidence = service.evidence_from_retrieval_hits((hit,))
    assert evidence[0].chunk_id == "k1"
    assert evidence[0].ordinal == 1
    assert evidence[0].citation_label == "S1"
    assert evidence[0].retrieval_score == 0.75
    c.close()


def test_completion_blocks_new_turns(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    completed = service.complete_session(session.session_id)
    assert completed.status == "completed"
    assert completed.completed_at == NOW
    with pytest.raises(TutorRepositoryError, match="non-active"):
        service.add_user_turn(session.session_id, "too late")
    c.close()


def test_feedback_is_explicit_and_validated(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    session = _session(service)
    turn = service.add_user_turn(session.session_id, "hello")
    feedback = service.record_feedback(
        turn.turn_id,
        rating=4,
        helpful=True,
        feedback_text="Useful session structure",
    )
    assert feedback.rating == 4
    assert feedback.helpful is True
    with pytest.raises(TutorSessionError):
        service.record_feedback(turn.turn_id)
    c.close()


def test_tutor_turns_do_not_modify_academic_state_tables(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    academic_tables = (
        "topic_progress_events",
        "learning_memory_entries",
        "resource_progress_events",
        "study_sessions",
        "study_plans",
        "questions",
        "question_attempts",
        "mistake_events",
    )
    before = {
        table: c.execute('SELECT COUNT(*) FROM "{}"'.format(table)).fetchone()[0]
        for table in academic_tables
    }
    session = _session(service)
    service.add_user_turn(session.session_id, "Explain LU")
    service.add_assistant_turn(
        session.session_id,
        "Grounded",
        support_level="grounded",
        evidence=_evidence(),
    )
    after = {
        table: c.execute('SELECT COUNT(*) FROM "{}"'.format(table)).fetchone()[0]
        for table in academic_tables
    }
    assert after == before
    c.close()


def test_tutor_evidence_does_not_modify_knowledge_chunks(tmp_path):
    _db, c, _repo, service = _env(tmp_path)
    before = tuple(
        c.execute(
            "SELECT id,document_id,text_hash,chunk_text FROM knowledge_chunks"
        ).fetchall()
    )
    session = _session(service)
    service.add_assistant_turn(
        session.session_id,
        "Grounded",
        support_level="grounded",
        evidence=_evidence(),
    )
    after = tuple(
        c.execute(
            "SELECT id,document_id,text_hash,chunk_text FROM knowledge_chunks"
        ).fetchall()
    )
    assert [tuple(row) for row in after] == [tuple(row) for row in before]
    c.close()


def test_provider_boundary_is_fail_closed_and_network_free():
    provider = DisabledTutorProvider()
    with pytest.raises(TutorProviderUnavailableError, match="Phase 6.1"):
        provider.complete(None)


def test_canonical_mode_policy_exists():
    policy = get_mode_policy("exam")
    assert policy.mode == "exam"
    assert policy.preferred_source_roles[0] == "professor"
