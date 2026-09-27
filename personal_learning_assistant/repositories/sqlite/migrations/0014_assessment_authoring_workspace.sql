-- Assessment Studio Authoring UX: persistent authoring classification
-- and editable Alex/ChatGPT master prompt.
--
-- Existing package schema remains unchanged. workspace_kind is user-facing
-- organization metadata for the import library.

ALTER TABLE assessment_import_batches
    ADD COLUMN workspace_kind TEXT
        CHECK (
            workspace_kind IS NULL
            OR workspace_kind IN ('quiz', 'exam', 'test')
        );

CREATE INDEX assessment_import_batches_workspace_kind_ix
    ON assessment_import_batches(workspace_kind, course_id, created_at DESC);

CREATE TABLE assessment_authoring_preferences (
    id TEXT PRIMARY KEY CHECK (id='default'),
    master_prompt TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at TEXT NOT NULL
);
