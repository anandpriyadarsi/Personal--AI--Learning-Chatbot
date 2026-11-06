-- Explicit backup-first activation only. No edits to canonical modes or study records.
CREATE TABLE tutor_coding_tasks (
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES tutor_sessions(id) ON DELETE RESTRICT,
 revision INTEGER NOT NULL CHECK(revision > 0),
 language TEXT NOT NULL CHECK(language='python'),
 title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
 creation_request_id TEXT NOT NULL,
 creation_digest TEXT NOT NULL,
 template_id TEXT,
 template_version INTEGER,
 snapshot_json TEXT NOT NULL CHECK(length(CAST(snapshot_json AS BLOB)) <= 65536),
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 archived_at TEXT,
 UNIQUE(session_id, creation_request_id)
);
CREATE INDEX tutor_coding_tasks_session_ix ON tutor_coding_tasks(session_id,created_at);
CREATE TABLE tutor_coding_turn_context (
 user_turn_id TEXT PRIMARY KEY REFERENCES tutor_turns(id) ON DELETE RESTRICT,
 assistant_turn_id TEXT NOT NULL UNIQUE REFERENCES tutor_turns(id) ON DELETE RESTRICT,
 task_id TEXT NOT NULL REFERENCES tutor_coding_tasks(id) ON DELETE RESTRICT,
 request_id TEXT NOT NULL,
 request_digest TEXT NOT NULL,
 action TEXT NOT NULL,
 hint_level INTEGER NOT NULL CHECK(hint_level BETWEEN 1 AND 3),
 full_solution INTEGER NOT NULL CHECK(full_solution IN (0,1)),
 request_json TEXT NOT NULL CHECK(length(CAST(request_json AS BLOB)) <= 24576),
 source_snapshot_json TEXT NOT NULL CHECK(length(CAST(source_snapshot_json AS BLOB)) <= 16384),
 provenance TEXT NOT NULL CHECK(provenance='ai_feedback'),
 created_at TEXT NOT NULL,
 UNIQUE(task_id,request_id)
);
CREATE TRIGGER tutor_coding_turn_scope BEFORE INSERT ON tutor_coding_turn_context
WHEN NOT EXISTS (
 SELECT 1 FROM tutor_coding_tasks t
 JOIN tutor_turns u ON u.id=NEW.user_turn_id AND u.session_id=t.session_id AND u.role='user'
 JOIN tutor_turns a ON a.id=NEW.assistant_turn_id AND a.session_id=t.session_id AND a.role='assistant'
 WHERE t.id=NEW.task_id
)
BEGIN SELECT RAISE(ABORT,'coding exchange scope mismatch'); END;
