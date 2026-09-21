-- ANVAYA Moodle read-only connector ledger.
-- Secrets/tokens are never stored here; configuration comes from environment.

CREATE TABLE moodle_sync_files (
    id TEXT PRIMARY KEY,
    moodle_course_id TEXT NOT NULL,
    anvaya_course_id TEXT
        REFERENCES courses(id) ON DELETE SET NULL,
    course_shortname TEXT NOT NULL DEFAULT '',
    course_name TEXT NOT NULL DEFAULT '',
    module_id TEXT NOT NULL DEFAULT '',
    module_name TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT '',
    external_content_hash TEXT NOT NULL DEFAULT '',
    external_modified_at TEXT NOT NULL DEFAULT '',
    local_path TEXT,
    status TEXT NOT NULL DEFAULT 'seen'
        CHECK (status IN ('seen','downloaded','failed','ignored')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    downloaded_at TEXT,
    error TEXT NOT NULL DEFAULT '',
    UNIQUE (moodle_course_id, module_id, file_url)
);

CREATE INDEX moodle_sync_files_course_status_ix
    ON moodle_sync_files (moodle_course_id, status, last_seen_at DESC);

CREATE INDEX moodle_sync_files_local_path_ix
    ON moodle_sync_files (local_path)
    WHERE local_path IS NOT NULL;
