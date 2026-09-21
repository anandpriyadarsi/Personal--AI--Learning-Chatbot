-- Phase 7.5.12.2 recovery: unified study interaction memory.
-- Migration 0006 is already owned by Phase 7.5.13 Operational Planner.
-- Historical Obsidian tables remain intact for compatibility/rollback.

CREATE TABLE study_item_reading_sessions (
    id TEXT PRIMARY KEY,
    item_kind TEXT NOT NULL
        CHECK (item_kind IN (
            'obsidian_note',
            'knowledge_document',
            'resource',
            'external_lecture'
        )),
    item_identity TEXT NOT NULL
        CHECK (length(trim(item_identity)) > 0),
    source_version_hash TEXT NOT NULL
        CHECK (length(source_version_hash) = 64),
    source_locator_json TEXT NOT NULL DEFAULT '{}',
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

CREATE INDEX study_item_reading_sessions_item_time_ix
    ON study_item_reading_sessions
       (item_kind, item_identity, started_at DESC);

CREATE INDEX study_item_reading_sessions_version_ix
    ON study_item_reading_sessions
       (item_kind, item_identity, source_version_hash, updated_at DESC);

CREATE TABLE study_item_companion_entries (
    id TEXT PRIMARY KEY,
    item_kind TEXT NOT NULL
        CHECK (item_kind IN (
            'obsidian_note',
            'knowledge_document',
            'resource',
            'external_lecture'
        )),
    item_identity TEXT NOT NULL
        CHECK (length(trim(item_identity)) > 0),
    source_version_hash TEXT NOT NULL
        CHECK (length(source_version_hash) = 64),
    entry_type TEXT NOT NULL
        CHECK (entry_type IN ('key_point', 'doubt', 'personal_note')),
    entry_text TEXT NOT NULL
        CHECK (length(trim(entry_text)) BETWEEN 1 AND 4000),
    locator_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE INDEX study_item_companion_entries_item_type_time_ix
    ON study_item_companion_entries
       (item_kind, item_identity, entry_type, created_at DESC);

-- Deterministic compatibility backfill. Old tables remain untouched.
INSERT INTO study_item_reading_sessions (
    id,item_kind,item_identity,source_version_hash,source_locator_json,
    started_at,ended_at,active_seconds,max_scroll_bps,last_event_sequence,
    created_at,updated_at
)
SELECT
    id,
    'obsidian_note',
    note_identity,
    source_hash,
    '{}',
    started_at,ended_at,active_seconds,max_scroll_bps,last_event_sequence,
    created_at,updated_at
FROM obsidian_reading_sessions;

INSERT INTO study_item_companion_entries (
    id,item_kind,item_identity,source_version_hash,entry_type,entry_text,
    locator_json,created_at,updated_at,archived_at
)
SELECT
    id,
    'obsidian_note',
    note_identity,
    lower(hex(zeroblob(32))),
    entry_type,
    entry_text,
    '{}',
    created_at,updated_at,archived_at
FROM obsidian_companion_entries;
