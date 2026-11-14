"""Diagnose selected multimodal Tutor evidence using read-only, stopped owners.

This never sends requests, writes data, repairs a database, reveals filenames,
source text, session IDs, paths, transcripts, questions or provider credentials.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from personal_learning_assistant.ingestion.chunking import decode_chunk_type
from scripts.tutor_storage_health import _read_only


SNAPSHOT_COLUMNS = frozenset((
    "id", "turn_id", "label", "source_json", "locator_json", "title", "artifact_hash",
))


def _columns(connection, table):
    return {row["name"] for row in connection.execute(
        'PRAGMA table_info("' + table + '")'
    )}


def diagnose(database, library_root, *, limit=20):
    native_db = Path(library_root) / "library.sqlite3"
    with closing(_read_only(database)) as academic, closing(_read_only(native_db)) as native:
        snap = SNAPSHOT_COLUMNS.issubset(_columns(academic, "tutor_evidence_snapshots"))
        rows = academic.execute(
            "SELECT status,course_id,metadata_json FROM tutor_sessions "
            "ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        report = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"])
                if not isinstance(metadata, dict) or not metadata.get("mm_selection"):
                    continue
                selection = metadata["mm_selection"]
                bound = metadata.get("mm_source_ref") or {}
                source_id = metadata.get("source_document_id")
                native_id = bound.get("native_document_id")
                if not isinstance(selection, dict) or not source_id:
                    report.append({"source_binding_valid": False})
                    continue
                candidates = academic.execute(
                    "SELECT c.chunk_type, c.extraction_version AS chunk_version, "
                    "d.extraction_version AS doc_version, d.extraction_status, d.content_hash "
                    "FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id "
                    "WHERE c.document_id=? LIMIT 2000", (source_id,)
                ).fetchall()
                matching = []
                for candidate in candidates:
                    _, loc = decode_chunk_type(candidate["chunk_type"])
                    if loc.get("mm_locator") != selection:
                        continue
                    matching.append((candidate, loc))
                receipt_matches = []
                for candidate, loc in matching:
                    receipt = native.execute(
                        "SELECT 1 FROM source_links s JOIN processing_jobs j ON j.id=s.operation_id "
                        "WHERE s.namespace='canonical' AND s.document_id=? "
                        "AND s.source_id=? AND s.content_hash=? AND "
                        "s.operation_id=? AND j.state='complete' LIMIT 1",
                        (native_id, source_id, candidate["content_hash"],
                         loc.get("mm_publication_job")),
                    ).fetchone()
                    receipt_matches.append(bool(receipt))
                original_matches = False
                artifact_matches = False
                if native_id:
                    original = native.execute(
                        "SELECT * FROM documents WHERE id=?", (native_id,)
                    ).fetchone()
                    if original:
                        original_matches = (
                            not original["trashed_at"]
                            and original["availability"] == "available"
                            and bool(original["indexing_enabled"])
                            and any(
                                original["sha256"] == c["content_hash"]
                                and original["generation"] == loc.get("native_generation")
                                and original["metadata_revision"] == loc.get("metadata_revision")
                                for c, loc in matching
                            )
                        )
                        for _, loc in matching:
                            if (loc.get("mm_artifact_id") == bound.get("mm_artifact_id")
                                    and loc.get("mm_artifact_hash") == bound.get("mm_artifact_hash")):
                                artifact = native.execute(
                                    "SELECT 1 FROM mm_artifacts "
                                    "WHERE id=? AND content_hash=? AND recipe=? LIMIT 1",
                                    (loc.get("mm_artifact_id"), loc.get("mm_artifact_hash"),
                                     loc.get("mm_recipe")),
                                ).fetchone()
                                if artifact:
                                    artifact_matches = True
                binding_matches = any(
                    all(loc.get(field) == bound.get(field) for field in (
                        "native_document_id", "content_hash", "native_generation",
                        "metadata_revision", "mm_artifact_id", "mm_artifact_hash", "mm_recipe",
                    )) for _, loc in matching
                )
                report.append({
                    "session_active": row["status"] == "active",
                    "selected_evidence_chunk_present": bool(matching),
                    "selected_chunk_published": any(receipt_matches),
                    "canonical_extraction_current": any(
                        c["extraction_status"] == "completed"
                        and c["chunk_version"] == c["doc_version"] and bool(c["doc_version"])
                        for c, _ in matching
                    ),
                    "source_binding_valid": binding_matches,
                    "native_original_matches": original_matches,
                    "native_artifact_present": artifact_matches,
                    "snapshot_columns_valid": snap,
                })
            except (ValueError, KeyError, TypeError, sqlite3.Error):
                report.append({"source_binding_valid": False, "diagnostic_complete": False})
        return {
            "read_only": True, "selected_sessions_checked": len(report),
            "recent_selected_sessions": report,
            "snapshot_columns_valid": snap,
            "personal_contents_exposed": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--library-root", required=True)
    args = parser.parse_args()
    try:
        result = diagnose(args.database, args.library_root)
    except (OSError, ValueError, sqlite3.Error):
        print(json.dumps({"status": "BLOCKED", "read_only": True}))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
