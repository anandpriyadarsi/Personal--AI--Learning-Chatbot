# Assessment Studio Phase C — Implementation Report

## Result

Assessment Studio Phase C — Timed JEE-style Test Runner + Session/Response Persistence is implemented from the verified Phase B baseline:

`phase7.5.assessment-studio-b/package-import-review @ 3722946411b50718e4abeceb13addd63c52b2bc7`

The production target branch is:

`phase7.5.assessment-studio-c/timed-test-runner`

Phase C has not been merged into `main`.

## Delivered

Phase C adds a persistent, resumable, server-authoritative timed CBT runner for approved ANVAYA assessments.

Implemented capabilities include:

- migration `0011_assessment_timed_test_runner.sql`;
- one-active-session-per-assessment enforcement;
- immutable session-question snapshots created at test start;
- server-side private snapshots of answer keys, solutions and rubrics for future Phase D evaluation;
- public runner reads that deliberately exclude private evaluation material;
- MCQ single-select radio controls;
- MSQ multi-select checkbox controls;
- True/False clickable controls;
- numerical/fill response input;
- short/long subjective text responses;
- persisted JEE-style states:
  - Not Visited;
  - Not Answered;
  - Answered;
  - Marked for Review;
  - Answered + Marked for Review;
- Save & Next;
- Clear Response;
- Mark for Review & Next;
- Previous and direct palette navigation;
- AJAX autosave;
- ordinary form-write fallback;
- interruption/reload recovery;
- server-authoritative expiry;
- monotonic browser countdown display with periodic server resynchronization;
- automatic timeout terminalization;
- explicit final submission;
- bounded per-question focus-time accumulation;
- meaningful runner event audit without per-keystroke logging;
- session library/history;
- instruction/preflight screen;
- distraction-reduced responsive exam layout;
- post-submission/timeout session summary.

The Assessment Studio landing page now exposes a functional **Take test** entry point.

## Database

Phase C advances the current schema through migration `0011`.

New tables:

- `assessment_test_sessions`;
- `assessment_test_session_questions`;
- `assessment_test_responses`;
- `assessment_test_events`.

Session-question rows snapshot the canonical question/runtime state at session start so a historical attempt is not silently changed by later assessment edits.

## Answer-key security

The public runner query does not select:

- `answer_key_json`;
- `solution_text`;
- `rubric_text`.

Public option snapshots contain only option ID and display text, never `is_correct`.

Automated web tests verify that runner HTML and session-summary HTML do not contain answer keys, solutions or rubrics.

The validation gate also contains a source-level guard ensuring the public runner query does not reference the private snapshot columns.

## Timer and timeout behavior

The database is authoritative for time.

Each session stores `started_at`, `expires_at`, duration and terminal submission state.

The browser countdown uses `performance.now()` only for smooth display. It periodically resynchronizes with the server.

When the displayed timer reaches zero, the browser asks the server instead of declaring timeout locally. This prevents client clock changes or sub-second rounding from forcing an early timeout.

Every server-side response write/heartbeat/submission synchronizes timeout status first.

A due session becomes:

- status: `expired`;
- submission reason: `timeout`;
- submitted timestamp: configured expiry instant.

The timeout event is recorded once.

## Response persistence

Responses are stored without grading:

- MCQ/MSQ: selected stable option IDs;
- numerical/fill/True-False: value;
- subjective: text.

Autosave preserves the review mark state.

Clear Response clears both the answer and review mark.

Focused seconds are persisted per question and each client delta is clamped to 60 seconds before storage.

## Submission boundary

Manual submission is terminal and idempotent.

Phase C intentionally does not create:

- `question_attempts`;
- `mistake_events`;
- `topic_progress_events`;
- mastery updates;
- planner changes;
- objective scores;
- subjective grades.

Those remain Phase D and later.

## Validation

Final clean GitHub validation for the implementation head completed successfully with:

- focused Assessment Studio Phase C: **9 passed**;
- Phase A/B + existing assessment regressions: **29 passed**;
- SQLite schema + recovery regressions: **22 passed**;
- Python compileall: **PASS**;
- dependency consistency via `pip check`: **PASS**;
- broader clone-safe project suite: **1472 passed, 2 deselected**;
- migrations `0001..0011`: **PASS**;
- SQLite `PRAGMA integrity_check`: **ok**;
- SQLite `PRAGMA foreign_key_check`: **no violations**;
- public answer-key leak guard: **PASS**;
- `git diff --check`: **PASS**.

The two clean-clone deselections remain the established production-data-dependent cases: GitHub runners do not contain the gitignored local `data/learning_assistant.db`. The committed local strict Phase C gate still runs the complete project suite against the real local environment.

## Visual validation

No claim of live localhost browser validation is made from this environment.

Automated Flask/web tests cover:

- test library;
- instruction page;
- start PRG;
- MCQ radio rendering;
- MSQ checkbox rendering;
- question palette/actions;
- autosave;
- response persistence;
- submission;
- summary rendering;
- answer-key/solution/rubric non-disclosure.

## Deferred

The next implementation phase should be **Assessment Studio Phase D — Evaluation Engine**, including deterministic objective scoring, configurable negative/partial marking, rubric-versioned subjective evaluation, provisional/confirmed grading states and mistake classification.
