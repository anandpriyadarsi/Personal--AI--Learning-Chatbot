"""Probe exact Tutor persistence against an IN-MEMORY copy of an existing owner.

No mutations to the original database. No provider, request, file upload, index
write, secrets, original files, session titles, source text or local paths printed.
Stop ANVAYA and its writers before invoking this command.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from personal_learning_assistant.domain.tutor_models import TutorEvidence
from personal_learning_assistant.ingestion.chunking import decode_chunk_type
from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
from personal_learning_assistant.services.tutor_session_service import TutorSessionService
from scripts.tutor_storage_health import _read_only


def probe(path):
    result = {
        "original_modified": False, "provider_calls": 0,
        "mode": "in_memory_sqlite_backup", "probe": "not_run",
    }
    with closing(_read_only(path)) as source:
        with closing(sqlite3.connect(":memory:", isolation_level=None)) as scratch:
            source.backup(scratch)
            scratch.row_factory = sqlite3.Row
            scratch.execute("PRAGMA foreign_keys=ON")
            sessions = scratch.execute(
                "SELECT id,metadata_json FROM tutor_sessions WHERE status='active' "
                "ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
            chosen = None
            matching = None
            for row in sessions:
                try:
                    metadata = json.loads(row["metadata_json"])
                except (TypeError, ValueError):
                    continue
                if not isinstance(metadata, dict) or not metadata.get("mm_selection"):
                    continue
                document_id = metadata.get("source_document_id")
                if not document_id:
                    continue
                rows = scratch.execute(
                    "SELECT id,document_id,chunk_type FROM knowledge_chunks "
                    "WHERE document_id=? LIMIT 2000", (document_id,)
                ).fetchall()
                for candidate in rows:
                    _, locator = decode_chunk_type(candidate["chunk_type"])
                    if locator.get("mm_locator") == metadata["mm_selection"]:
                        chosen = row["id"]
                        matching = candidate
                        break
                if chosen:
                    break
            if not chosen:
                result["probe"] = "BLOCKED_NO_MATCHING_SELECTED_EVIDENCE"
                return result
            repository = SQLiteTutorRepository(scratch)
            service = TutorSessionService(repository)
            before = scratch.execute(
                "SELECT count(*) FROM tutor_turns WHERE session_id=?", (chosen,)
            ).fetchone()[0]
            evidence = TutorEvidence(
                chunk_id=matching["id"], document_id=matching["document_id"],
                ordinal=1, citation_label="S1",
            )
            # This is an in-memory clone. No real user text or provider is used.
            try:
                with repository.atomic_exchange(chosen):
                    service.add_user_turn(chosen, "Offline storage diagnostic.")
                    service.add_assistant_turn(
                        chosen, "Offline synthetic citation [S1].",
                        support_level="grounded", evidence=(evidence,),
                    )
                after = scratch.execute(
                    "SELECT count(*) FROM tutor_turns WHERE session_id=?", (chosen,)
                ).fetchone()[0]
                result["probe"] = "PASS" if after == before + 2 else "FAIL_TURN_COUNT"
                result["citation_rows_saved"] = bool(scratch.execute(
                    "SELECT 1 FROM tutor_evidence_snapshots LIMIT 1"
                ).fetchone())
            except (sqlite3.Error, ValueError, RuntimeError, TypeError) as error:
                # Exception class and standardized SQLite code only, no message.
                result["probe"] = "FAIL"
                category = type(error).__name__
                if category not in {
                    "IntegrityError", "OperationalError", "DatabaseError",
                    "TutorSessionError", "TutorRepositoryError", "ValueError",
                    "RuntimeError", "TypeError",
                }:
                    category = "Other"
                result["exception_class"] = category
                name = str(getattr(error, "sqlite_errorname", "") or "")
                if name.startswith("SQLITE_") and name.replace("_", "").isalnum():
                    result["sqlite_code"] = name[:64]
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    try:
        result = probe(Path(args.database))
    except (OSError, ValueError, sqlite3.Error):
        result = {
            "original_modified": False, "provider_calls": 0,
            "probe": "BLOCKED_OWNER_UNAVAILABLE",
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    if result["probe"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
