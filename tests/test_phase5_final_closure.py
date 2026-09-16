from __future__ import annotations

import json
from pathlib import Path

import pytest

from personal_learning_assistant.ingestion.chunking import (
    decode_chunk_type,
    encode_chunk_type,
)
from personal_learning_assistant.ingestion.external_course_package import (
    MIT1806PackageReader,
)
from personal_learning_assistant.retrieval.index_builder import RetrievalIndexBuilder
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import (
    SQLiteRetrievalSourceRepository,
)
from personal_learning_assistant.services.phase5_closure_service import (
    Phase5ClosureError,
    Phase5ClosureService,
    _lecture_refs,
)

from tests.test_phase5_external_course_knowledge import _env, _package


def test_lecture_provenance_accepts_single_or_multi_lecture_locators():
    assert _lecture_refs({"lecture_number": "04", "lecture_numbers": []}) == {"04"}
    assert _lecture_refs(
        {"lecture_number": None, "lecture_numbers": ["04", "05"]}
    ) == {"04", "05"}


def _reviewed(service, package, tmp_path):
    value = service.crosswalk.build_template(
        package, local_course_code="MA103N"
    )
    for row in value["mappings"]:
        if row["current_state"] == "exact_mapped":
            continue
        row["decision"] = "leave_unresolved"
        row["reviewed"] = True
        row["review_note"] = "Synthetic explicit closure review."
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return service.crosswalk.load_reviewed(
        path,
        package,
        local_course_code="MA103N",
        require_complete=True,
    )


def _installed(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, external_service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    reviewed = _reviewed(external_service, package, tmp_path)
    external_service.apply(
        package,
        package_key="mit1806-package",
        local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    index_root = tmp_path / "current-index"
    RetrievalIndexBuilder(
        SQLiteRetrievalSourceRepository(connection),
        index_root,
    ).build(embedding_provider=None, acknowledge=True)
    closure = Phase5ClosureService(connection, index_root=index_root)
    return connection, package, reviewed, closure, index_root


def _verify(closure, package, reviewed, tmp_path):
    return closure.verify(
        package=package,
        reviewed_crosswalk=reviewed,
        package_key="mit1806-package",
        local_course_code="MA103N",
        rebuild_root=tmp_path / "rebuild",
        smoke_query="mit l04",
        smoke_provider="mit_ocw",
        smoke_lecture="04",
    )


def test_complete_phase5_install_reconciles_and_rebuilds(tmp_path):
    connection, package, reviewed, closure, _index = _installed(tmp_path)
    report = _verify(closure, package, reviewed, tmp_path)
    assert report["issue_count"] == 0
    assert report["external_course"]["lecture_count"] == 2
    assert report["external_course"]["chunk_count"] == 3
    assert report["retrieval"]["active_chunk_count"] == 3
    assert report["retrieval"]["pending_handoff_count"] == 0
    assert report["retrieval"]["current_index_valid"] is True
    assert report["retrieval"]["rebuild_matches_current"] is True
    connection.close()


def test_closure_verification_performs_zero_sqlite_changes(tmp_path):
    connection, package, reviewed, closure, _index = _installed(tmp_path)
    before = connection.total_changes
    _verify(closure, package, reviewed, tmp_path)
    assert connection.total_changes == before
    connection.close()


def test_pending_retrieval_handoff_blocks_closure(tmp_path):
    connection, package, reviewed, closure, _index = _installed(tmp_path)
    connection.execute(
        "UPDATE index_jobs SET status='pending',completed_at=NULL "
        "WHERE index_kind='retrieval_handoff'"
    )
    with pytest.raises(Phase5ClosureError, match="retrieval handoff"):
        _verify(closure, package, reviewed, tmp_path)
    connection.close()


def test_stale_crosswalk_hash_in_chunk_provenance_blocks_closure(tmp_path):
    connection, package, reviewed, closure, _index = _installed(tmp_path)
    row = connection.execute(
        "SELECT id,chunk_type FROM knowledge_chunks ORDER BY ordinal LIMIT 1"
    ).fetchone()
    kind, locator = decode_chunk_type(row["chunk_type"])
    locator["crosswalk_sha256"] = "0" * 64
    connection.execute(
        "UPDATE knowledge_chunks SET chunk_type=? WHERE id=?",
        (encode_chunk_type(kind, locator), row["id"]),
    )
    with pytest.raises(Phase5ClosureError, match="crosswalk hash"):
        _verify(closure, package, reviewed, tmp_path)
    connection.close()


def test_stale_resource_topic_link_blocks_closure(tmp_path):
    connection, package, reviewed, closure, _index = _installed(tmp_path)
    row = connection.execute(
        "SELECT resource_id,topic_id,relation_source FROM resource_topics LIMIT 1"
    ).fetchone()
    assert row is not None
    connection.execute(
        "DELETE FROM resource_topics WHERE resource_id=? AND topic_id=? "
        "AND relation_source=?",
        (row["resource_id"], row["topic_id"], row["relation_source"]),
    )
    with pytest.raises(Phase5ClosureError, match="topic links"):
        _verify(closure, package, reviewed, tmp_path)
    connection.close()


def test_corrupt_current_index_file_blocks_closure(tmp_path):
    connection, package, reviewed, closure, index_root = _installed(tmp_path)
    current = json.loads(
        (index_root / "current.json").read_text(encoding="utf-8")
    )["generation_id"]
    lexical = index_root / "indexes" / current / "lexical.sqlite3"
    with lexical.open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(Phase5ClosureError, match="manifest hashes"):
        _verify(closure, package, reviewed, tmp_path)
    connection.close()


def test_historical_chunk_version_is_allowed_when_current_is_coherent(tmp_path):
    connection, package, reviewed, closure, _index = _installed(tmp_path)
    current = connection.execute(
        "SELECT id,document_id,chunk_type,text_hash,chunk_text "
        "FROM knowledge_chunks ORDER BY ordinal LIMIT 1"
    ).fetchone()
    connection.execute(
        "INSERT INTO knowledge_chunks "
        "(id,document_id,ordinal,page_number,char_start,char_end,chunk_type,"
        "text_hash,extraction_version,chunk_text) "
        "VALUES ('historical',?,99,NULL,0,10,?,?,'old-version',?)",
        (
            current["document_id"],
            current["chunk_type"],
            current["text_hash"],
            current["chunk_text"],
        ),
    )
    report = _verify(closure, package, reviewed, tmp_path)
    assert report["issue_count"] == 0
    connection.close()


def test_nonterminal_operation_journal_blocks_closure(tmp_path):
    connection, package, reviewed, closure, _index = _installed(tmp_path)
    connection.execute(
        "INSERT INTO operation_journal "
        "(id,kind,target_path,before_hash,after_hash,state,error,created_at,updated_at) "
        "VALUES ('op1','test',NULL,NULL,NULL,'planned',NULL,"
        "'2026-09-16T00:00:00Z','2026-09-16T00:00:00Z')"
    )
    with pytest.raises(Phase5ClosureError, match="non-terminal"):
        _verify(closure, package, reviewed, tmp_path)
    connection.close()
