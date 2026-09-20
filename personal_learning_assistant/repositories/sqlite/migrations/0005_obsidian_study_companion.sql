-- Phase 7.5.12.1: Obsidian Reader active-time history and Companion memory.
-- Vault Markdown remains authoritative; neither table stores note bodies or HTML.

CREATE TABLE obsidian_reading_sessions (
    id TEXT PRIMARY KEY,
    vault_identity TEXT NOT NULL
        CHECK (length(trim(vault_identity)) > 0),
    note_identity TEXT NOT NULL
        CHECK (length(trim(note_identity)) > 0),
    relative_path TEXT NOT NULL
        CHECK (length(trim(relative_path)) > 0),
    source_hash TEXT NOT NULL
        CHECK (length(source_hash) = 64),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    active_seconds INTEGER NOT NULL DEFAULT 0
        CHECK (active_seconds >= 0),
    max_scroll_bps INTEGER NOT NULL DEFAULT 0
        CHECK (max_scroll_bps BETWEEN 0 AND 10000),
    last_event_sequence INTEGER NOT NULL DEFAULT 0
        CHECK (last_event_sequence >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX obsidian_reading_sessions_note_time_ix
    ON obsidian_reading_sessions
       (vault_identity, note_identity, started_at DESC);

CREATE INDEX obsidian_reading_sessions_updated_ix
    ON obsidian_reading_sessions (updated_at DESC);

CREATE TABLE obsidian_companion_entries (
    id TEXT PRIMARY KEY,
    vault_identity TEXT NOT NULL
        CHECK (length(trim(vault_identity)) > 0),
    note_identity TEXT NOT NULL
        CHECK (length(trim(note_identity)) > 0),
    relative_path TEXT NOT NULL
        CHECK (length(trim(relative_path)) > 0),
    entry_type TEXT NOT NULL
        CHECK (entry_type IN ('key_point', 'doubt')),
    entry_text TEXT NOT NULL
        CHECK (length(trim(entry_text)) BETWEEN 1 AND 2000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE INDEX obsidian_companion_entries_note_type_time_ix
    ON obsidian_companion_entries
       (vault_identity, note_identity, entry_type, created_at DESC);
