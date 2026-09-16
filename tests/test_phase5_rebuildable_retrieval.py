from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from personal_learning_assistant.domain.retrieval_models import RetrievalFilters
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import (
    SQLiteRetrievalSourceRepository,
)
from personal_learning_assistant.retrieval.index_builder import RetrievalIndexBuilder
from personal_learning_assistant.retrieval.index_store import RetrievalIndexStore
from personal_learning_assistant.services.retrieval_service import RetrievalService


NOW = "2026-09-16T16:00:00Z"


class ToyEmbedding:
    model_name = "toy"
    model_version = "1"

    def embed(self, texts):
        rows = []
        for text in texts:
            low = text.casefold()
            rows.append(
                np.asarray(
                    [
                        low.count("lu") + low.count("factor"),
                        low.count("inverse"),
                        low.count("rank"),
                        low.count("system"),
                    ],
                    dtype=np.float32,
                )
            )
        return rows


def _db(tmp_path):
    path = tmp_path / "db.sqlite"
    apply_migrations(path)
    c = sqlite3.connect(str(path), isolation_level=None)
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
        "VALUES ('t-lu','c1','LU Factorisation','lu factorisation',1,'not_started',"
        "NULL,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resources(id,resource_type,title,canonical_uri,provider,external_id,"
        "status,rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
        "VALUES ('r1','external_lecture','MIT L4','https://ocw.mit.edu/l4','mit_ocw',"
        "'mit-l4','not_started',NULL,'',?,?,NULL,NULL,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) "
        "VALUES ('r1','c1','supporting')"
    )
    c.execute(
        "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
        "VALUES ('r1','t-lu','imported',1.0)"
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
        "INSERT INTO resource_documents(resource_id,document_id,role) "
        "VALUES ('r1','d1','source')"
    )
    locator1 = json.dumps(
        {
            "lecture_number": "04",
            "lecture_numbers": ["04"],
            "source_url": "https://ocw.mit.edu/l4",
            "local_topic_ids": ["t-lu"],
            "package_chunk_id": "mit-L04-a",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    locator2 = json.dumps(
        {
            "lecture_number": "01",
            "lecture_numbers": ["01"],
            "source_url": "https://ocw.mit.edu/l1",
            "local_topic_ids": [],
            "package_chunk_id": "mit-L01-a",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    c.execute(
        "INSERT INTO knowledge_chunks(id,document_id,ordinal,page_number,char_start,char_end,"
        "chunk_type,text_hash,extraction_version,chunk_text) "
        "VALUES ('k1','d1',0,NULL,0,35,?,'th1','v1',"
        "'LU factorization decomposes a matrix into triangular factors.')",
        ("lecture;locator=v1:" + locator1,),
    )
    c.execute(
        "INSERT INTO knowledge_chunks(id,document_id,ordinal,page_number,char_start,char_end,"
        "chunk_type,text_hash,extraction_version,chunk_text) "
        "VALUES ('k2','d1',1,NULL,0,35,?,'th2','v1',"
        "'Systems of linear equations can be interpreted geometrically.')",
        ("lecture;locator=v1:" + locator2,),
    )
    c.execute(
        "INSERT INTO index_jobs(id,document_id,content_hash,index_kind,model_name,model_version,"
        "index_version,status,created_at,started_at,completed_at,failed_at,error) "
        "VALUES ('h1','d1','hash1','retrieval_handoff','','','phase5.8-pending-v1',"
        "'pending',?,NULL,NULL,NULL,NULL)",
        (NOW,),
    )
    return path, c


def test_active_source_uses_current_extraction_and_chunk_local_topics(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    records = repo.active_records()
    assert len(records) == 2
    assert records[0]["topic_ids"] == ("t-lu",)
    assert records[0]["course_ids"] == ("c1",)
    assert records[0]["providers"] == ("mit_ocw",)
    c.close()


def test_source_fingerprint_is_deterministic_and_changes_with_chunk_evidence(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    first = repo.source_fingerprint()
    assert first == repo.source_fingerprint()
    c.execute("UPDATE knowledge_chunks SET text_hash='changed' WHERE id='k1'")
    assert repo.source_fingerprint() != first
    c.close()


def test_lexical_index_build_and_search(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    root = tmp_path / "index"
    result = RetrievalIndexBuilder(repo, root, now=lambda: NOW).build(
        embedding_provider=None,
        acknowledge=False,
    )
    assert result.chunk_count == 2
    store = RetrievalIndexStore(root)
    try:
        hits = RetrievalService(store).search("triangular LU factorization")
        assert hits
        assert hits[0].chunk_id == "k1"
    finally:
        store.close()
        c.close()


def test_semantic_index_and_hybrid_search(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    root = tmp_path / "index"
    RetrievalIndexBuilder(repo, root, now=lambda: NOW).build(
        embedding_provider=ToyEmbedding(),
        acknowledge=False,
    )
    store = RetrievalIndexStore(root, embedding_provider=ToyEmbedding())
    try:
        hits = RetrievalService(store).search("matrix factorization LU")
        assert hits
        assert hits[0].chunk_id == "k1"
        assert hits[0].semantic_rank is not None
    finally:
        store.close()
        c.close()


def test_topic_course_lecture_provider_filters(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    root = tmp_path / "index"
    RetrievalIndexBuilder(repo, root).build(
        embedding_provider=None,
        acknowledge=False,
    )
    store = RetrievalIndexStore(root)
    try:
        service = RetrievalService(store)
        assert service.search("factorization", topic_ids=("t-lu",))[0].chunk_id == "k1"
        assert service.search("factorization", course_ids=("c1",))[0].chunk_id == "k1"
        assert service.search("factorization", lecture_numbers=("04",))[0].chunk_id == "k1"
        assert service.search("factorization", providers=("mit_ocw",))[0].chunk_id == "k1"
        assert service.search("factorization", lecture_numbers=("01",)) == ()
    finally:
        store.close()
        c.close()


def test_rag_context_preserves_source_identity_and_never_calls_llm(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    root = tmp_path / "index"
    RetrievalIndexBuilder(repo, root).build(
        embedding_provider=None,
        acknowledge=False,
    )
    store = RetrievalIndexStore(root)
    try:
        context = RetrievalService(store).build_context(
            "LU factorization",
            topic_ids=("t-lu",),
            max_chars=4000,
        )
        assert context.source_count == 1
        assert "chunk_id=k1" in context.context_text
        assert "MIT L04" in context.context_text
        assert "source_url" in context.context_text
    finally:
        store.close()
        c.close()


def test_rebuild_same_source_is_idempotent_generation(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    root = tmp_path / "index"
    builder = RetrievalIndexBuilder(repo, root, now=lambda: NOW)
    first = builder.build(embedding_provider=None, acknowledge=False)
    second = builder.build(embedding_provider=None, acknowledge=False)
    assert first.generation_id == second.generation_id
    assert builder.preview()["index_is_current"] is True
    c.close()


def test_changed_source_creates_new_generation(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    root = tmp_path / "index"
    builder = RetrievalIndexBuilder(repo, root, now=lambda: NOW)
    first = builder.build(embedding_provider=None, acknowledge=False)
    c.execute("UPDATE knowledge_chunks SET text_hash='newhash' WHERE id='k1'")
    second = builder.build(embedding_provider=None, acknowledge=False)
    assert second.generation_id != first.generation_id
    c.close()


def test_acknowledge_marks_handoff_completed_and_build_job_completed(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    root = tmp_path / "index"
    result = RetrievalIndexBuilder(repo, root, now=lambda: NOW).build(
        embedding_provider=None,
        acknowledge=True,
    )
    handoff = c.execute(
        "SELECT status FROM index_jobs WHERE id='h1'"
    ).fetchone()[0]
    build = c.execute(
        "SELECT status,index_kind,index_version FROM index_jobs "
        "WHERE index_kind='lexical_retrieval'"
    ).fetchone()
    assert handoff == "completed"
    assert tuple(build) == ("completed", "lexical_retrieval", result.generation_id)
    c.close()


def test_preview_performs_zero_sqlite_writes(tmp_path):
    _path, c = _db(tmp_path)
    repo = SQLiteRetrievalSourceRepository(c)
    builder = RetrievalIndexBuilder(repo, tmp_path / "index")
    before = c.total_changes
    preview = builder.preview()
    assert preview["active_chunk_count"] == 2
    assert c.total_changes == before
    c.close()


def test_index_files_are_disposable_and_do_not_change_source_db(tmp_path):
    path, c = _db(tmp_path)
    c.close()
    before = path.read_bytes()
    ro = sqlite3.connect("file:{}?mode=ro".format(path.as_posix()), uri=True)
    ro.row_factory = sqlite3.Row
    repo = SQLiteRetrievalSourceRepository(ro)
    RetrievalIndexBuilder(repo, tmp_path / "index").build(
        embedding_provider=None,
        acknowledge=False,
    )
    ro.close()
    assert path.read_bytes() == before
