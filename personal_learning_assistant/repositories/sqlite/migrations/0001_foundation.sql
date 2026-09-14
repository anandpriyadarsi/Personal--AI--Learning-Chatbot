-- Phase 3.1 Fix 1: SQLite foundation and migration infrastructure.
-- JSON/current files remain authoritative until the Phase 4 cutover.

CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    name TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    applied_at TEXT NOT NULL
);

CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE migration_imports (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT '',
    legacy_key TEXT NOT NULL DEFAULT '',
    target_table TEXT NOT NULL,
    target_id TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (
        source_path,
        source_hash,
        source_type,
        source_version,
        legacy_key,
        target_table
    )
);

CREATE TABLE operation_journal (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    target_path TEXT,
    before_hash TEXT,
    after_hash TEXT,
    state TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE outbox_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    processed_at TEXT,
    failed_at TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0)
);

CREATE INDEX idx_migration_imports_target
    ON migration_imports (target_table, target_id);

CREATE INDEX idx_operation_journal_state
    ON operation_journal (state, updated_at);

CREATE INDEX idx_outbox_events_pending
    ON outbox_events (processed_at, failed_at, created_at);
