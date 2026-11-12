"""Read-only legacy inventory and an explicit, append-only reconciliation ledger."""
import hashlib
import json
from datetime import datetime, timezone


class ObsidianSourceIdentityRepository:
    def __init__(self, connection):
        self.connection = connection

    def preview_identity_migration(self):
        tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        unresolved = {}
        for table in ("study_item_companion_entries", "study_item_reading_sessions"):
            if table not in tables:
                continue
            for identity, count in self.connection.execute("SELECT item_identity, COUNT(*) FROM " + table + " WHERE item_kind='obsidian_note' AND (item_identity LIKE 'assistant:%' OR item_identity LIKE 'path:%') GROUP BY item_identity"):
                row = unresolved.setdefault(identity, {"legacy_identity": identity, "records": 0, "state": "unresolved", "reason": "Bare external UUID does not prove connection ownership."})
                row["records"] += count
        report = {"policy": "obsidian-identity-v3-conservative-1", "unresolved_count": len(unresolved), "unresolved": sorted(unresolved.values(), key=lambda row: row["legacy_identity"]), "automatic_reassignments": 0}
        report["report_hash"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return report

    def apply_identity_migration(self, expected_report_hash):
        # The transaction protects report freshness and ledger replay. This never
        # reassigns ambiguous activity to the currently connected vault.
        if self.connection.in_transaction:
            raise ValueError("Finish the current transaction before reconciliation.")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute("SELECT report_json FROM obsidian_identity_reconciliation WHERE report_hash=?", (expected_report_hash,)).fetchone()
            if existing:
                self.connection.commit()
                return {**json.loads(existing[0]), "replayed": True}
            report = self.preview_identity_migration()
            if report["report_hash"] != expected_report_hash:
                raise ValueError("Identity inventory changed; review a new report before applying.")
            self.connection.execute("INSERT INTO obsidian_identity_reconciliation VALUES (?,?,?)", (expected_report_hash, json.dumps(report, sort_keys=True), datetime.now(timezone.utc).isoformat()))
            self.connection.commit()
            return {**report, "replayed": False}
        except Exception:
            self.connection.rollback()
            raise
