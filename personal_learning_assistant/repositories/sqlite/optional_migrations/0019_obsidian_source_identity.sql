-- Optional, explicit activation only. Keep historical bare UUID records intact.
CREATE TABLE IF NOT EXISTS obsidian_identity_reconciliation (
    report_hash TEXT PRIMARY KEY,
    report_json TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
