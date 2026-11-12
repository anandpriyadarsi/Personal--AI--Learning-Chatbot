-- Explicit owner activation only. Never run on startup or GET.
ALTER TABLE planner_tasks ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
CREATE TABLE planner_command_receipts (
 command_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES planner_tasks(id),
 prior_revision INTEGER NOT NULL, new_revision INTEGER NOT NULL, action TEXT NOT NULL,
 occurred_at TEXT NOT NULL, result_json TEXT NOT NULL
);
CREATE TABLE planner_work_logs (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES planner_tasks(id),
 agenda_item_id TEXT REFERENCES daily_agenda_items(id), actual_minutes INTEGER NOT NULL CHECK(actual_minutes BETWEEN 0 AND 1440),
 occurred_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', evidence_label TEXT NOT NULL DEFAULT 'self_reported',
 supersedes_id TEXT UNIQUE REFERENCES planner_work_logs(id)
);
CREATE INDEX planner_work_logs_task ON planner_work_logs(task_id,occurred_at);
CREATE TABLE planner_task_sources (
 task_id TEXT NOT NULL REFERENCES planner_tasks(id), owner TEXT NOT NULL, kind TEXT NOT NULL,
 identifier TEXT NOT NULL, revision_key TEXT NOT NULL DEFAULT '', sha256 TEXT,
 mapping_status TEXT NOT NULL DEFAULT 'unreviewed',
 PRIMARY KEY(task_id,owner,kind,identifier,revision_key)
);
CREATE TABLE planner_proposals (
 id TEXT PRIMARY KEY, agenda_date TEXT NOT NULL, revision INTEGER NOT NULL,
 command_id TEXT NOT NULL UNIQUE, context_json TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(agenda_date,revision)
);
ALTER TABLE weekly_reviews ADD COLUMN evidence_json TEXT;
ALTER TABLE weekly_reviews ADD COLUMN evidence_fingerprint TEXT;
ALTER TABLE weekly_reviews ADD COLUMN evidence_as_of TEXT;
ALTER TABLE weekly_reviews ADD COLUMN policy_version TEXT;
ALTER TABLE weekly_reviews ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
-- Legacy source adapters and metadata edits also advance optimistic revisions.
CREATE TRIGGER planner_revision_on_legacy_update AFTER UPDATE ON planner_tasks
WHEN NEW.revision = OLD.revision
BEGIN
 UPDATE planner_tasks SET revision=OLD.revision+1 WHERE id=NEW.id;
END;
