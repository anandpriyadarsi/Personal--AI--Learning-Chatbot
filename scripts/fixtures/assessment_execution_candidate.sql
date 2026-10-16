-- DISPOSABLE FIXTURE ONLY. Not registered in the migration runner.
-- No production migration number/lineage approval is asserted.
CREATE TABLE assessment_candidate_scope (scope TEXT PRIMARY KEY CHECK(scope='disposable-synthetic-only'));
INSERT INTO assessment_candidate_scope VALUES ('disposable-synthetic-only');
CREATE TABLE assessment_candidate_execution (
 session_id TEXT PRIMARY KEY REFERENCES assessment_test_sessions(id) ON DELETE RESTRICT,
 revision INTEGER NOT NULL CHECK(revision>0), metadata_json TEXT NOT NULL
);
CREATE TABLE assessment_candidate_receipts (
 session_id TEXT NOT NULL REFERENCES assessment_candidate_execution(session_id) ON DELETE RESTRICT,
 request_id TEXT NOT NULL, command TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 prior_revision INTEGER NOT NULL, result_revision INTEGER NOT NULL, occurred_at TEXT NOT NULL,
 result_json TEXT NOT NULL, PRIMARY KEY(session_id,request_id)
);
CREATE TRIGGER assessment_candidate_receipts_immutable_update BEFORE UPDATE ON assessment_candidate_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TRIGGER assessment_candidate_receipts_immutable_delete BEFORE DELETE ON assessment_candidate_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TABLE assessment_candidate_self_reviews (
 session_id TEXT NOT NULL REFERENCES assessment_candidate_execution(session_id) ON DELETE RESTRICT,
 revision INTEGER NOT NULL CHECK(revision>0), status TEXT NOT NULL CHECK(status IN ('draft','submitted')),
 provenance TEXT NOT NULL CHECK(provenance='self_assessed'), snapshot_json TEXT NOT NULL,
 PRIMARY KEY(session_id,revision)
);
CREATE UNIQUE INDEX assessment_candidate_one_draft ON assessment_candidate_self_reviews(session_id) WHERE status='draft';
CREATE TRIGGER assessment_candidate_submitted_immutable BEFORE UPDATE ON assessment_candidate_self_reviews WHEN OLD.status='submitted' BEGIN SELECT RAISE(ABORT,'immutable submitted review'); END;
CREATE TRIGGER assessment_candidate_reviews_immutable_delete BEFORE DELETE ON assessment_candidate_self_reviews BEGIN SELECT RAISE(ABORT,'immutable review history'); END;
