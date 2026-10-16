-- Additive Assessment Studio active-time and paper self-study state.
-- Existing 0001-0014 definitions and academic assessment records are untouched.
-- The self-review is student-entered ONLY; never an official grade, verified
-- independent work, Tutor assessment, Topic mastery or Planner recovery signal.
-- No existing sessions are adopted on migration; opt-in only for new attempts.
CREATE TABLE assessment_extended_scope (scope TEXT PRIMARY KEY CHECK(scope='local-self-study-v1'));
INSERT INTO assessment_extended_scope VALUES ('local-self-study-v1');
CREATE TABLE assessment_extended_execution (
 session_id TEXT PRIMARY KEY REFERENCES assessment_test_sessions(id) ON DELETE RESTRICT,
 revision INTEGER NOT NULL CHECK(revision>0), metadata_json TEXT NOT NULL
);
CREATE TABLE assessment_extended_receipts (
 session_id TEXT NOT NULL REFERENCES assessment_extended_execution(session_id) ON DELETE RESTRICT,
 request_id TEXT NOT NULL, command TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 prior_revision INTEGER NOT NULL, result_revision INTEGER NOT NULL, occurred_at TEXT NOT NULL,
 result_json TEXT NOT NULL, PRIMARY KEY(session_id,request_id)
);
CREATE TRIGGER assessment_extended_receipts_immutable_update BEFORE UPDATE ON assessment_extended_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TRIGGER assessment_extended_receipts_immutable_delete BEFORE DELETE ON assessment_extended_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TABLE assessment_extended_self_reviews (
 session_id TEXT NOT NULL REFERENCES assessment_extended_execution(session_id) ON DELETE RESTRICT,
 revision INTEGER NOT NULL CHECK(revision>0), status TEXT NOT NULL CHECK(status IN ('draft','submitted')),
 provenance TEXT NOT NULL CHECK(provenance='self_assessed'), snapshot_json TEXT NOT NULL,
 PRIMARY KEY(session_id,revision)
);
CREATE UNIQUE INDEX assessment_extended_one_draft ON assessment_extended_self_reviews(session_id) WHERE status='draft';
CREATE TRIGGER assessment_extended_submitted_immutable BEFORE UPDATE ON assessment_extended_self_reviews WHEN OLD.status='submitted' BEGIN SELECT RAISE(ABORT,'immutable submitted review'); END;
CREATE TRIGGER assessment_extended_reviews_immutable_delete BEFORE DELETE ON assessment_extended_self_reviews BEGIN SELECT RAISE(ABORT,'immutable review history'); END;
