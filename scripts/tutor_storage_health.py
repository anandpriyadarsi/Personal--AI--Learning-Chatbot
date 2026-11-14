"""Private, read-only Tutor storage triage for a stopped local ANVAYA.

Never migrates, checkpoints, repairs, reindexes, sends provider requests, or
prints personal content/paths/IDs/credentials. Run with both owners stopped.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote


def _read_only(path):
    path = Path(path).expanduser().absolute()
    if not path.is_file() or path.is_symlink():
        raise ValueError("An expected existing owner database is absent or a symlink")
    # mode=ro (not immutable) reflects checkpointed SQLite data. Stop all writers.
    uri = "file:" + quote(str(path).replace("\\", "/"), safe="/:") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _report(path, required, *, library=False):
    with closing(_read_only(path)) as db:
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        tables = {str(row["name"]) for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        # Return a boolean only; never print foreign-key row IDs or table payloads.
        foreign_keys_ok = db.execute("PRAGMA foreign_key_check").fetchone() is None
        status = {
            "quick_check_ok": integrity == "ok",
            "foreign_keys_ok": foreign_keys_ok,
            "required_tables_present": all(name in tables for name in required),
            "missing_table_names": [name for name in required if name not in tables],
            "multimodal_ledger_present": "mm_schema_ledger" in tables,
        }
        if "mm_schema_ledger" in tables:
            status["multimodal_ledger_entries"] = int(
                db.execute("SELECT count(*) FROM mm_schema_ledger").fetchone()[0]
            )
        if library and "mm_provider_requests" in tables:
            # Count only statuses; never print operations, source data or consent.
            counts = db.execute(
                "SELECT status, count(*) AS amount FROM mm_provider_requests GROUP BY status"
            ).fetchall()
            status["provider_requests"] = {
                str(row["status"]): int(row["amount"]) for row in counts
            }
            status["unresolved_paid_request_exists"] = bool(
                status["provider_requests"].get("sending", 0)
                or status["provider_requests"].get("outcome_unknown", 0)
            )
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--library-root", required=True)
    args = parser.parse_args()
    try:
        academic = _report(
            args.database,
            ["tutor_sessions", "tutor_turns", "tutor_evidence_links",
             "knowledge_chunks", "knowledge_documents"],
        )
        native = _report(
            Path(args.library_root) / "library.sqlite3",
            ["documents", "mm_provider_requests", "mm_selections", "mm_artifacts"],
            library=True,
        )
        result = {
            "read_only": True,
            "writers_must_be_stopped": True,
            "academic": academic,
            "library": native,
            "ready_for_repair_triage": (
                academic["quick_check_ok"] and native["quick_check_ok"]
                and academic["foreign_keys_ok"] and native["foreign_keys_ok"]
                and academic["required_tables_present"]
                and native["required_tables_present"]
            ),
        }
    except (OSError, ValueError, sqlite3.Error) as error:
        # Deliberately redact paths and SQLite exception texts.
        print(json.dumps({"read_only": True, "status": "BLOCKED",
                          "reason": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True, indent=2))
    if not result["ready_for_repair_triage"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
