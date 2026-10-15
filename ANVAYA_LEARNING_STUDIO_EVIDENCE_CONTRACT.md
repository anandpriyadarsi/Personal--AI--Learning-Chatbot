# LearningEvidenceSummary V1

Authority: server-derived low-stakes practice only. Existing ANVAYA is a single-owner local application, so owner identity is the server constant `local-owner`; no new multiuser/session authentication is invented. Caller-provided learner IDs or academic mapping strings are rejected. The existing app must continue to run locally.

POST /learning/modules/<module_id>/<revision>/attempts accepts event_id, module_revision, source_sha256, question_id, question_revision, integer selection. Optional client is_correct is ignored. Server verifies exact published immutable module/question version, source hash, selection shape and route revision, then grades its private answer key. Public module/package GETs exclude keys and explanations. Feedback reveals the answer/explanation only after a valid submit. Each event stores owner, module/source/question version, selection, derived correctness, attempt number and UTC timestamp.

Writes require a process-local random CSRF token, same-origin checks and compatible Fetch Metadata. Restart invalidates request tokens; refresh the reader. This is a local request guard, not user authentication. No model/provider is invoked during practice.

Unique event IDs provide idempotency. Same ID/same immutable payload returns original feedback; changed response/context conflicts with HTTP409. BEGIN IMMEDIATE serializes attempts; tests verify concurrent identical submissions append once. SQLite triggers reject updates/deletes of module artifacts, publications, assets and attempts. Retries append events; wrong → correct stays ever missed/recovered-needs-recheck. Historical question/module revisions remain separate and gradeable.

GET /learning/evidence exposes schema `anvaya.learning-evidence-summary.v1`: authority, attempt counts, ever_missed, latest_correct, reviewed/unmapped counts, grouped course/topic attempts/incorrect, daily counts and evidence_label. Fewer than five distinct question-version observations are labelled Limited evidence. Mapping is the historical reviewed module snapshot, not a live mutation of registry/mastery. Repeated incorrect counts are signals only, not diagnosis or a mastery model.

GET /learning/evidence/export downloads append-only events (`anvaya.learning-evidence-export.v1`) with module/source/question IDs, selected response, server correctness, number and timestamp. V1 exports evidence only. Offline prototype evidence import is DEFERRED; no client correctness/timestamps are imported or treated as learning truth. There is no UI history-erasure action. Retention is indefinite in the local feature store; backup/export is an explicit owner operation.

Analysis: /analysis includes a link to /learning/analysis; evidence is read-only and never replaces official Assessment Studio scores, academic grades/progress or Tutor memory. All new persistence is inside the dedicated feature boundary.

Tutor: /agent currently accepts course code but has no source/versioned LearningEvidenceSummary consumer. A course-only link cannot truthfully transfer the required evidence. The Review with ANVAYA Tutor affordance is disabled with an explanation. The documented summary contract is available; adding a reviewed consumer is a separate bounded task. No Tutor reasoning, prompts, orchestration, grading, production sessions or scenario gates were modified.

## V1.1 manual review-context projection

The versioned, source-verified `anvaya.learning-review-context.v1` producer and plain-text download are available at `/learning/modules/<id>/<revision>/review-context` and `/review-brief`. Weak Questions offers explicit clipboard/download controls. The context includes only that module revision's server-graded missed questions, historical lesson/question/source locators and current mapping review status. It excludes hidden keys/explanations and never calls Tutor. Clipboard failure selects the text for manual copying. See `ANVAYA_LEARNING_STUDIO_TUTOR_READONLY_HANDOFF_V1_2.md` for the unimplemented consumer acceptance contract.
