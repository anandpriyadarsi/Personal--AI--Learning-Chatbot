from __future__ import annotations

import json
import sqlite3

import pytest

from personal_learning_assistant.domain.practice_models import PracticeQuizSpec
from personal_learning_assistant.domain.retrieval_models import RetrievalHit
from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.practice_repository import (
    PracticeAuthorityError,
    PracticeConflictError,
    SQLitePracticeRepository,
)
from personal_learning_assistant.services.practice_quiz_service import (
    PracticeQuizError,
    PracticeQuizService,
)
from personal_learning_assistant.tutor.quiz_grounding import QuizGroundingError


NOW = "2026-09-16T20:00:00Z"


class FakeRetrieval:
    def __init__(self, hits):
        self.hits = tuple(hits)
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.hits


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, request):
        self.calls.append(request)
        return TutorProviderResponse(
            content=json.dumps(self.payload),
            provider_name="fake",
            provider_model="quiz-test",
            request_id="req-quiz-1",
        )


def _ids():
    values = {}

    def make(prefix):
        values[prefix] = values.get(prefix, 0) + 1
        return "{}-{}".format(prefix, values[prefix])

    return make


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


def _hit():
    return RetrievalHit(
        chunk_id="k1",
        document_id="d1",
        text=(
            "LU factorization writes A = LU, where L is lower triangular "
            "and U is upper triangular."
        ),
        score=0.9,
        lexical_rank=1,
        semantic_rank=None,
        page_number=None,
        locator={"lecture_number": "04", "topic": "LU Factorization"},
        resource_ids=("r1",),
        course_ids=("c1",),
        topic_ids=("t1",),
        providers=("mit_ocw",),
    )


def _payload():
    return {
        "items": [
            {
                "item_type": "single_choice",
                "prompt": "In A = LU, what kind of matrix is L?",
                "options": [
                    {"key": "A", "text": "Lower triangular"},
                    {"key": "B", "text": "Upper triangular"},
                    {"key": "C", "text": "Diagonal only"},
                    {"key": "D", "text": "Symmetric only"},
                ],
                "correct_option": "A",
                "accepted_answers": [],
                "explanation": (
                    "The cited source states that L is lower triangular."
                ),
                "source_labels": ["S1"],
            },
            {
                "item_type": "exact_recall",
                "prompt": "Write the standard two-factor LU form of A.",
                "options": [],
                "correct_option": "",
                "accepted_answers": ["A = LU", "A=LU"],
                "explanation": "The cited source gives the factorization A = LU.",
                "source_labels": ["S1"],
            },
            {
                "item_type": "free_response",
                "prompt": "Explain what the letters L and U represent.",
                "options": [],
                "correct_option": "",
                "accepted_answers": [],
                "explanation": (
                    "Reference: L is lower triangular and U is upper triangular."
                ),
                "source_labels": ["S1"],
            },
        ]
    }


def _env(tmp_path, *, authority=True, payload=None, hits=None):
    db = tmp_path / "db.sqlite"
    assert apply_migrations(db) == (1, 2, 3, 4)
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
        "VALUES ('r1','external_lecture','MIT L04','https://ocw.mit.edu/l4','mit_ocw',"
        "'mit-l4','in_progress',NULL,'',?,?,NULL,NULL,NULL)",
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
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,"
        "content_hash,size_bytes,source_timestamp,extraction_status,extraction_version,"
        "extraction_error,created_at,updated_at) "
        "VALUES ('d1','external_course_chunks',NULL,'mit/chunks.jsonl','application/x-ndjson',"
        "'h1',100,NULL,'completed','v1',NULL,?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO knowledge_chunks(id,document_id,ordinal,page_number,char_start,char_end,"
        "chunk_type,text_hash,extraction_version,chunk_text) "
        "VALUES ('k1','d1',0,NULL,0,10,'text','th1','v1','LU evidence')"
    )
    auth = tmp_path / "authority.json"
    _authority(auth, sqlite=authority)
    repo = SQLitePracticeRepository(c, authority_control_path=auth)
    retrieval = FakeRetrieval((_hit(),) if hits is None else hits)
    provider = FakeProvider(_payload() if payload is None else payload)
    service = PracticeQuizService(
        repository=repo,
        retrieval_service=retrieval,
        provider=provider,
        now=lambda: NOW,
        id_factory=_ids(),
    )
    spec = PracticeQuizSpec(
        course_id="c1",
        topic_id="t1",
        resource_id="r1",
        mode="fast_quiz",
        difficulty="medium",
        item_count=3,
        focus="LU factorization",
    )
    return c, auth, repo, retrieval, provider, service, spec


def _academic_counts(c):
    tables = (
        "topic_progress_events",
        "learning_memory_entries",
        "resource_progress_events",
        "study_sessions",
        "study_plans",
        "questions",
        "question_attempts",
        "mistake_events",
    )
    return {
        name: c.execute(
            'SELECT COUNT(*) FROM "{}"'.format(name)
        ).fetchone()[0]
        for name in tables
    }


def test_0004_migration_is_applied_and_idempotent(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    versions = tuple(
        row[0]
        for row in c.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    )
    assert versions == (1, 2, 3, 4)
    tables = {
        row[0]
        for row in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "practice_sessions",
        "practice_items",
        "practice_item_sources",
        "practice_attempts",
    }.issubset(tables)
    c.close()


def test_preview_is_read_only_and_scope_filtered(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    before = c.total_changes
    plan = service.preview(spec)
    assert c.total_changes == before
    assert plan.evidence_labels == ("S1",)
    query, kwargs = retrieval.calls[-1]
    assert query == "LU factorization"
    assert kwargs["course_ids"] == ("c1",)
    assert kwargs["topic_ids"] == ("t1",)
    assert kwargs["resource_ids"] == ("r1",)
    assert not provider.calls
    c.close()


def test_no_evidence_blocks_generation_without_provider_or_write(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(
        tmp_path, hits=()
    )
    before = c.total_changes
    with pytest.raises(QuizGroundingError, match="no project evidence"):
        service.generate(spec)
    assert c.total_changes == before
    assert not provider.calls
    c.close()


def test_generated_quiz_persists_exact_chunk_sources(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    view = service.generate(spec)
    assert len(view.items) == 3
    assert c.execute("SELECT COUNT(*) FROM practice_items").fetchone()[0] == 3
    assert c.execute(
        "SELECT COUNT(*) FROM practice_item_sources"
    ).fetchone()[0] == 3
    source = c.execute(
        "SELECT chunk_id,document_id,citation_label FROM practice_item_sources "
        "ORDER BY item_id LIMIT 1"
    ).fetchone()
    assert tuple(source) == ("k1", "d1", "S1")
    assert c.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 1
    c.close()


def test_generated_view_never_exposes_answer_key(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    view = service.generate(spec)
    first = view.items[0]
    assert first.item_type == "single_choice"
    assert len(first.options) == 4
    assert not hasattr(first, "correct_option")
    assert not hasattr(first, "accepted_answers")
    c.close()


def test_provider_cannot_cite_unavailable_evidence(tmp_path):
    payload = _payload()
    payload["items"][0]["source_labels"] = ["S9"]
    c, auth, repo, retrieval, provider, service, spec = _env(
        tmp_path, payload=payload
    )
    before = c.total_changes
    with pytest.raises(QuizGroundingError, match="unavailable source"):
        service.generate(spec)
    assert c.total_changes == before
    assert c.execute("SELECT COUNT(*) FROM practice_sessions").fetchone()[0] == 0
    c.close()


def test_single_choice_is_graded_deterministically(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    view = service.generate(spec)
    result = service.submit(view.session_id, 1, "A", self_confidence=4)
    assert result.outcome == "correct"
    assert result.score_bps == 10000
    assert result.grading_mode == "deterministic"
    assert result.self_confidence == 4
    c.close()


def test_single_choice_wrong_answer_is_deterministically_incorrect(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    view = service.generate(spec)
    result = service.submit(view.session_id, 1, "B")
    assert result.outcome == "incorrect"
    assert result.score_bps == 0
    c.close()


def test_exact_recall_uses_strict_casefold_whitespace_match(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    view = service.generate(spec)
    result = service.submit(view.session_id, 2, "  a = lu  ")
    assert result.outcome == "correct"
    assert result.grading_mode == "deterministic"
    c.close()


def test_free_response_is_advisory_not_marked_correct_or_incorrect(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    view = service.generate(spec)
    result = service.submit(
        view.session_id,
        3,
        "L is lower and U is upper.",
    )
    assert result.outcome == "advisory_ungraded"
    assert result.score_bps is None
    assert result.grading_mode == "advisory"
    assert "intentionally not marked" in result.feedback
    c.close()


def test_practice_attempt_does_not_change_mastery_or_formal_attempts(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    before = _academic_counts(c)
    view = service.generate(spec)
    service.submit(view.session_id, 1, "B")
    service.submit(view.session_id, 2, "A=LU")
    assert _academic_counts(c) == before
    assert c.execute("SELECT COUNT(*) FROM practice_attempts").fetchone()[0] == 2
    c.close()


def test_inactive_authority_blocks_generation_write(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(
        tmp_path, authority=False
    )
    with pytest.raises(PracticeAuthorityError):
        service.generate(spec)
    assert c.execute("SELECT COUNT(*) FROM practice_sessions").fetchone()[0] == 0
    c.close()


def test_provider_failure_or_invalid_payload_does_not_partially_write(tmp_path):
    payload = {"items": [{"item_type": "single_choice"}]}
    c, auth, repo, retrieval, provider, service, spec = _env(
        tmp_path, payload=payload
    )
    before = c.total_changes
    with pytest.raises(QuizGroundingError):
        service.generate(spec)
    assert c.total_changes == before
    assert c.execute("SELECT COUNT(*) FROM practice_sessions").fetchone()[0] == 0
    c.close()


def test_finish_requires_every_item_attempted(tmp_path):
    c, auth, repo, retrieval, provider, service, spec = _env(tmp_path)
    view = service.generate(spec)
    service.submit(view.session_id, 1, "A")
    with pytest.raises(PracticeConflictError, match="all practice items"):
        service.finish(view.session_id)
    service.submit(view.session_id, 2, "A=LU")
    service.submit(view.session_id, 3, "L lower; U upper")
    final, changed = service.finish(view.session_id)
    assert changed is True
    assert final.status == "completed"
    final2, changed2 = service.finish(view.session_id)
    assert changed2 is False
    assert final2.status == "completed"
    c.close()
