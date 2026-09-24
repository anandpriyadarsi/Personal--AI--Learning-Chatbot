from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal_learning_assistant.domain.retrieval_models import RetrievalHit
from personal_learning_assistant.domain.study_item_models import StudyItemIdentity
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    DEFAULT_MIGRATIONS_PATH,
    apply_migrations,
)


def _migrated(tmp_path):
    path = tmp_path / "learning_assistant.db"
    # Current migration source includes the recovered historical
    # 0008_moodle_sync migration. Phase 7.5.12.2-specific 0007 tests below
    # still exercise a deliberately bounded 0001..0007 migration set.
    assert apply_migrations(path)[-1] == 8
    return path


def _seed_knowledge(path):
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO courses "
        "(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c-ma','MA103N','Linear Algebra','active','','x','x',NULL)"
    )
    c.execute(
        "INSERT INTO topics "
        "(id,course_id,name,normalized_name,position,status,created_at,updated_at,deleted_at) "
        "VALUES ('t-lu','c-ma','LU Factorization','lu factorization',1,'not_started','x','x',NULL)"
    )
    c.execute(
        "INSERT INTO resources "
        "(id,resource_type,title,canonical_uri,provider,status,quality_note,created_at,updated_at,deleted_at) "
        "VALUES ('r-strang','lecture','MIT 18.06 Lecture 4','https://example.com/lu','MIT OCW','not_started','','x','x',NULL)"
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) VALUES ('r-strang','c-ma','supporting')"
    )
    c.execute(
        "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
        "VALUES ('r-strang','t-lu','test',1.0)"
    )
    c.execute(
        "INSERT INTO knowledge_documents "
        "(id,kind,canonical_uri,path_key,mime_type,content_hash,size_bytes,source_timestamp,"
        "extraction_status,extraction_version,extraction_error,created_at,updated_at) "
        "VALUES ('d-lu','video_transcript','https://example.com/lu',NULL,'text/plain',"
        "?,100,NULL,'completed','v1',NULL,'x','x')",
        ("a" * 64,),
    )
    c.execute(
        "INSERT INTO resource_documents(resource_id,document_id,role) VALUES ('r-strang','d-lu','source')"
    )
    c.execute(
        "INSERT INTO knowledge_chunks "
        "(id,document_id,ordinal,page_number,char_start,char_end,chunk_type,text_hash,"
        "extraction_version,chunk_text) VALUES "
        "('ch-lu','d-lu',0,NULL,0,48,'text',?,'v1','LU factorization eliminates a matrix into triangular factors.')",
        ("b" * 64,),
    )
    c.commit()
    c.close()


def test_0007_migration_backfills_old_obsidian_data_without_deleting_legacy(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for version in range(1, 7):
        source = next(DEFAULT_MIGRATIONS_PATH.glob(f"{version:04d}_*.sql"))
        shutil.copy2(source, migrations / source.name)

    path = tmp_path / "db.sqlite"
    assert apply_migrations(path, migrations_path=migrations) == (1, 2, 3, 4, 5, 6)

    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO obsidian_reading_sessions VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "old-s","vault:" + "1"*64,"path:" + "2"*64,"Math/LU.md","3"*64,
            "2026-09-20T10:00:00Z","2026-09-20T10:01:00Z",60,5000,1,
            "2026-09-20T10:00:00Z","2026-09-20T10:01:00Z",
        ),
    )
    c.execute(
        "INSERT INTO obsidian_companion_entries VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "old-e","vault:" + "1"*64,"path:" + "2"*64,"Math/LU.md",
            "doubt","Why pivot?","x","x",None,
        ),
    )
    c.commit()
    c.close()

    shutil.copy2(
        Path(__file__).resolve().parents[1]
        / "personal_learning_assistant/repositories/sqlite/migrations/0007_unified_study_interactions.sql",
        migrations / "0007_unified_study_interactions.sql",
    )
    assert apply_migrations(path, migrations_path=migrations) == (7,)
    assert apply_migrations(path, migrations_path=migrations) == ()

    c = sqlite3.connect(path)
    assert c.execute("SELECT COUNT(*) FROM obsidian_reading_sessions").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM obsidian_companion_entries").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM study_item_reading_sessions").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM study_item_companion_entries").fetchone()[0] == 1
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    c.close()


def test_unified_interaction_repository_tracks_and_reuses_companion(tmp_path):
    from personal_learning_assistant.repositories.sqlite.study_interaction_repository import (
        SQLiteStudyInteractionRepository,
    )
    from personal_learning_assistant.repositories.sqlite.connection import connect_database

    path = _migrated(tmp_path)
    c = connect_database(path)
    repo = SQLiteStudyInteractionRepository(c)
    identity = StudyItemIdentity("knowledge_document", "d1", "a" * 64)

    created = repo.create_session(
        session_id="s1", identity=identity, locator={"page": 2}, now="t0"
    )
    assert created["active_seconds"] == 0
    first = repo.heartbeat(
        session_id="s1", identity=identity, sequence=1,
        delta_seconds=30, scroll_bps=4000, now="t1"
    )
    assert first["accepted"] is True
    replay = repo.heartbeat(
        session_id="s1", identity=identity, sequence=1,
        delta_seconds=30, scroll_bps=9000, now="t2"
    )
    assert replay["accepted"] is False
    ended = repo.end_session(
        session_id="s1", identity=identity, sequence=2,
        delta_seconds=5, scroll_bps=6000, replayed_delta_seconds=0, now="t3"
    )
    assert ended["active_seconds"] == 35

    entry = repo.add_entry(
        entry_id="e1", identity=identity, entry_type="doubt",
        entry_text="Why does elimination give L?", locator={}, now="t4"
    )
    assert entry["entry_type"] == "doubt"
    assert repo.reading_history(identity)["total_active_seconds"] == 35
    assert repo.list_entries(identity)[0]["id"] == "e1"
    c.close()


def test_obsidian_runtime_adapter_writes_generalized_tables(tmp_path):
    from personal_learning_assistant.repositories.sqlite.obsidian_study_repository_v2 import (
        SQLiteObsidianStudyRepositoryV2,
    )

    path = _migrated(tmp_path)
    repo = SQLiteObsidianStudyRepositoryV2(path)
    repo.create_session(
        session_id="s-v2",
        vault_identity="vault:" + "a"*64,
        note_identity="path:" + "b"*64,
        relative_path="Math/LU.md",
        source_hash="c"*64,
        now="2026-09-20T10:00:00Z",
    )
    repo.add_entry(
        entry_id="e-v2",
        vault_identity="vault:" + "a"*64,
        note_identity="path:" + "b"*64,
        relative_path="Math/LU.md",
        entry_type="key_point",
        entry_text="L records elimination multipliers.",
        source_hash="c"*64,
        now="2026-09-20T10:01:00Z",
    )
    c = sqlite3.connect(path)
    assert c.execute(
        "SELECT COUNT(*) FROM study_item_reading_sessions WHERE id='s-v2'"
    ).fetchone()[0] == 1
    assert c.execute(
        "SELECT COUNT(*) FROM study_item_companion_entries WHERE id='e-v2'"
    ).fetchone()[0] == 1
    assert c.execute(
        "SELECT COUNT(*) FROM obsidian_reading_sessions WHERE id='s-v2'"
    ).fetchone()[0] == 0
    c.close()


def test_search_metadata_uses_human_titles_and_filter_options(tmp_path):
    from personal_learning_assistant.repositories.sqlite.search_metadata_repository import (
        SQLiteSearchMetadataRepository,
    )

    path = _migrated(tmp_path)
    _seed_knowledge(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    repo = SQLiteSearchMetadataRepository(c)
    item = repo.document("d-lu")
    assert item["title"] == "MIT 18.06 Lecture 4"
    assert item["course_labels"] == ("MA103N · Linear Algebra",)
    assert item["topic_labels"] == ("LU Factorization",)
    options = repo.filter_options()
    assert options["courses"][0]["code"] == "MA103N"
    assert "lecture" in options["source_types"]
    c.close()


def test_grounding_planner_constrains_exact_source_document():
    from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner

    class Retrieval:
        def __init__(self):
            self.kwargs = None
        def search(self, query, **kwargs):
            self.kwargs = kwargs
            return ()

    class Sessions:
        @staticmethod
        def evidence_from_retrieval_hits(hits):
            return ()

    retrieval = Retrieval()
    planner = TutorGroundingPlanner(retrieval, Sessions())
    session = SimpleNamespace(
        mode="doubt",
        source_policy="source_only",
        course_id=None,
        topic_id=None,
        assessment_id=None,
        resource_id=None,
        metadata={"source_document_id": "doc-123"},
        session_id="s",
    )
    plan = planner.plan(session, "Why?")
    assert plan.hits == ()
    assert retrieval.kwargs["document_ids"] == ("doc-123",)


def test_runtime_refuses_stale_index(monkeypatch):
    from personal_learning_assistant.services.unified_search_runtime import (
        UnifiedSearchRuntime,
        UnifiedSearchStaleIndexError,
    )

    runtime = UnifiedSearchRuntime()
    runtime._store = SimpleNamespace(
        manifest={"source_fingerprint": "old"},
        close=lambda: None,
    )
    runtime._generation = "g1"
    monkeypatch.setattr(runtime, "_ensure_current", lambda: None)
    monkeypatch.setattr(runtime, "_source_fingerprint", lambda: "new")
    with pytest.raises(UnifiedSearchStaleIndexError):
        runtime.assert_fresh()


def test_knowledge_reader_rejects_stale_version_and_tracks_current_source(tmp_path):
    from personal_learning_assistant.services.knowledge_reader_service import (
        KnowledgeReaderService,
        KnowledgeReaderUnavailableError,
    )

    path = _migrated(tmp_path)
    _seed_knowledge(path)
    service = KnowledgeReaderService(database_path=path)

    item = service.view("d-lu")
    assert item["title"] == "MIT 18.06 Lecture 4"
    assert item["content"][0]["text"].startswith("LU factorization")

    with pytest.raises(KnowledgeReaderUnavailableError):
        service.start_reading(document_id="d-lu", version_hash="f"*64)

    started = service.start_reading(document_id="d-lu", version_hash="a"*64)
    session_id = started["session_id"]
    service.heartbeat(
        document_id="d-lu", version_hash="a"*64, session_id=session_id,
        sequence=1, delta_seconds=10, scroll_bps=2500
    )
    service.end_reading(
        document_id="d-lu", version_hash="a"*64, session_id=session_id,
        sequence=2, delta_seconds=1, scroll_bps=3000,
        replayed_delta_seconds=0,
    )
    service.add_entry(
        document_id="d-lu", version_hash="a"*64, entry_type="key_point",
        entry_text="L stores multipliers."
    )
    reopened = service.view("d-lu")
    assert reopened["history"]["times_opened"] == 1
    assert reopened["history"]["total_active_seconds"] == 11
    assert reopened["companion"]["key_points"][0]["entry_text"] == "L stores multipliers."


def test_unified_search_groups_chunks_into_one_source_result(tmp_path):
    from personal_learning_assistant.services.unified_search_service import (
        UnifiedSearchService,
    )

    path = _migrated(tmp_path)
    _seed_knowledge(path)

    hit1 = RetrievalHit(
        chunk_id="ch1", document_id="d-lu", text="LU factorization triangular",
        score=0.9, lexical_rank=1, semantic_rank=None, page_number=None,
        locator={}, resource_ids=("r-strang",), course_ids=("c-ma",),
        topic_ids=("t-lu",), providers=("MIT OCW",),
    )
    hit2 = RetrievalHit(
        chunk_id="ch2", document_id="d-lu", text="Elimination multipliers",
        score=0.8, lexical_rank=2, semantic_rank=None, page_number=None,
        locator={}, resource_ids=("r-strang",), course_ids=("c-ma",),
        topic_ids=("t-lu",), providers=("MIT OCW",),
    )

    class Runtime:
        def search(self, *args, **kwargs):
            return (hit1, hit2)

    class NoVault:
        def workspace(self, query):
            return {"notes": ()}

    service = UnifiedSearchService(
        database_path=path,
        runtime=Runtime(),
        obsidian_workspace_factory=lambda: NoVault(),
    )
    results = service.search("LU factorization", top_k=8)
    assert len(results) == 1
    assert results[0].title == "MIT 18.06 Lecture 4"
    assert results[0].matched_chunk_ids == ("ch1", "ch2")
    assert "Text match" in results[0].relevance_reasons
