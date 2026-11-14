"""Offline diagnostic scripts must never write personal stores or send requests."""
from contextlib import closing
import json
import sqlite3

from test_multimodal_jobs import owners
from test_multimodal_grounding import prepared
from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
from personal_learning_assistant.services.tutor_session_service import TutorSessionService
from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
from scripts.tutor_persistence_probe import probe
from scripts.tutor_selected_evidence_health import diagnose


def test_persistence_probe_saves_only_in_memory_and_preserves_real_owner(owners):
    lib, db = owners
    doc, record = prepared(owners)
    with closing(sqlite3.connect(db, isolation_level=None)) as con:
        service = TutorSessionService(SQLiteTutorRepository(con))
        service.create_session(TutorSessionSpec(
            mode="doubt", source_policy="source_only",
            metadata={
                "source_document_id": record["document_id"],
                "source_version_hash": doc["sha256"],
                "mm_selection": record["locator"]["mm_locator"],
                "mm_source_ref": record["locator"],
            },
        ))
        initial = con.execute("SELECT count(*) FROM tutor_turns").fetchone()[0]
    output = probe(db)
    assert output["probe"] == "PASS"
    assert output["original_modified"] is False
    assert output["provider_calls"] == 0
    with closing(sqlite3.connect(db)) as con:
        assert con.execute("SELECT count(*) FROM tutor_turns").fetchone()[0] == initial


def test_selected_evidence_health_does_not_expose_private_source_values(owners):
    lib, db = owners
    doc, record = prepared(owners)
    with closing(sqlite3.connect(db, isolation_level=None)) as con:
        service = TutorSessionService(SQLiteTutorRepository(con))
        service.create_session(TutorSessionSpec(
            mode="doubt", source_policy="source_only",
            metadata={
                "source_document_id": record["document_id"],
                "source_version_hash": doc["sha256"],
                "mm_selection": record["locator"]["mm_locator"],
                "mm_source_ref": record["locator"],
            },
        ))
    output = diagnose(db, lib.root)
    assert output["read_only"] is True
    assert output["selected_sessions_checked"] >= 1
    first = output["recent_selected_sessions"][0]
    assert first["session_active"] is True
    assert first["selected_evidence_chunk_present"] is True
    assert first["source_binding_valid"] is True
    assert first["native_original_matches"] is True
    assert first["selected_chunk_published"] is True
    assert first["snapshot_columns_valid"] is True
    serialized = json.dumps(output)
    assert doc["id"] not in serialized
    assert doc["sha256"] not in serialized
