# Assessment Studio — Phase C: Timed JEE-style Test Runner + Session/Response Persistence

## Baseline

Phase C starts from verified Assessment Studio Phase B:

`phase7.5.assessment-studio-b/package-import-review @ 3722946411b50718e4abeceb13addd63c52b2bc7`

Phase C does not merge to `main` and does not implement grading or performance analytics.

## Product outcome

Phase C turns an approved canonical ANVAYA assessment into a resumable timed computer-based-test session.

The workflow is:

approved assessment
→ instructions/preflight
→ explicit Start test
→ immutable session-question snapshots
→ timed JEE-style runner
→ autosaved responses + question states + focus-time evidence
→ explicit submission or server timeout
→ persisted session summary.

The runner supports:

- MCQ single-select radio controls;
- MSQ multi-select checkbox controls;
- numerical/fill response input;
- True/False clickable controls;
- short and long subjective text responses;
- Save & Next;
- Clear Response;
- Mark for Review & Next;
- Previous navigation;
- direct question-palette navigation;
- Not Visited;
- Not Answered;
- Answered;
- Marked for Review;
- Answered + Marked for Review;
- autosave;
- interruption/reload recovery;
- one active session per assessment;
- explicit final submission;
- automatic timeout closure.

## Migration 0011

`0011_assessment_timed_test_runner.sql` introduces:

- `assessment_test_sessions`;
- `assessment_test_session_questions`;
- `assessment_test_responses`;
- `assessment_test_events`.

### Session snapshot

When a test starts, ANVAYA creates immutable session-question snapshots. This protects historical attempts if the canonical assessment is edited later.

The snapshot includes the question text/type/order/marks/scoring metadata, public options, academic metadata and the private answer/evaluation material that existed at start time.

The public runner never reads private snapshot fields.

### Server-only private fields

The session snapshot keeps the following server-side for later Phase D evaluation:

- `answer_key_json`;
- `solution_text`;
- `rubric_text`.

These fields must never be emitted in:

- runner HTML;
- autosave responses;
- heartbeat responses;
- question palette data;
- session summary HTML;
- public runner read models.

Public objective options are snapshotted separately without `is_correct`.

## Timer authority

The timer is server-authoritative.

The database session stores:

- `started_at`;
- `expires_at`;
- duration snapshot;
- final status;
- submission reason.

The browser displays a smooth countdown using `performance.now()` so ordinary wall-clock changes do not make the visual timer jump.

The browser periodically asks the server for the remaining time. If the local display reaches zero, it must ask the server rather than declaring the attempt expired itself.

Every server write synchronizes timeout state first.

When server time is at or after `expires_at`:

- the session becomes `expired`;
- `submitted_at` is fixed to the configured expiry instant;
- `submission_reason` becomes `timeout`;
- one meaningful `auto_submitted_timeout` event is recorded;
- further response writes are rejected as terminal.

## Active-session rule

At most one `active` session may exist for an assessment.

Starting an assessment with a still-active session resumes the existing session.

If the previous active session has already expired according to server time, it is terminalized first and a new attempt may start.

Submitted/expired sessions remain immutable historical session records.

## Response model

Every session question owns exactly one `assessment_test_responses` row.

Response payloads are validated against the snapshotted question type.

### MCQ

Stored as:

`{"selected_option_ids":["B"]}`

Zero or one option may be selected.

### MSQ

Stored as:

`{"selected_option_ids":["A","C"]}`

Any valid subset may be selected.

### Numerical / Fill / True-False

Stored as:

`{"value":"..."}`

### Subjective

Stored as:

`{"text":"..."}`

Phase C stores responses only. It does not determine correctness.

## Question state machine

The persisted response state is one of:

- `not_visited`;
- `not_answered`;
- `answered`;
- `marked_for_review`;
- `answered_marked_for_review`.

Opening a question transitions `not_visited → not_answered`.

Saving a non-empty response without a review mark produces `answered`.

Mark for Review with no answer produces `marked_for_review`.

Mark for Review with an answer produces `answered_marked_for_review`.

Clear Response clears the response and review mark and leaves the visited question as `not_answered`.

Autosave preserves the current review-mark state.

## Persistence and interruption recovery

Response changes are persisted through a JSON autosave endpoint and through ordinary form actions.

A browser reload or later resume rebuilds the runner from SQLite:

- selected MCQ/MSQ options;
- numerical/fill value;
- subjective text;
- palette states;
- current question;
- remaining server-authoritative time.

No response state depends exclusively on browser memory/localStorage.

## Timing evidence

Phase C stores bounded focused seconds per session question.

The browser accumulates visible/focused time and reports bounded deltas. The server clamps each delta to 60 seconds, preventing an untrusted client from injecting arbitrarily large timing values.

This is useful evidence for later analytics but is not treated as perfect proctoring data.

Meaningful runner events are recorded for actions such as:

- session start;
- first question visit;
- changed response save/autosave;
- mark-for-review transition;
- clear response;
- manual submission;
- timeout submission.

Keystrokes are not individually logged.

## Exam mode and practice mode

Phase C uses the same secure response runner for both modes.

Exam mode does not expose hints, answer keys, solutions, rubrics or correctness feedback during the attempt.

Phase C also keeps those materials hidden in Practice mode because guided feedback/evaluation is not yet implemented. Later phases may deliberately add practice-only help without weakening Exam mode.

## Submission boundary

Manual submission is explicit and terminal.

Before browser-driven manual submission, the current response and focus delta are flushed.

Submission does not:

- score objective questions;
- grade subjective answers;
- create `question_attempts`;
- create `mistake_events`;
- create `topic_progress_events`;
- modify mastery;
- modify the planner.

Those belong to Phase D/E/F.

## Web surfaces

Phase C adds:

- `GET /assessments/tests` — runnable assessment/session library;
- `GET /assessments/tests/<assessment_id>` — instructions/preflight;
- `POST /assessments/tests/<assessment_id>/start` — start/resume;
- `GET /assessments/sessions/<session_id>` — timed runner;
- response autosave endpoint;
- heartbeat/time-sync endpoint;
- explicit question action endpoint;
- submission endpoint;
- session-summary endpoint.

The Assessment Studio landing page activates the existing Take test entry point.

## Accessibility / responsive behavior

The runner uses real form inputs and labels.

Question palette links carry state labels in `aria-label`.

A visible textual legend accompanies palette styling.

The runner remains usable without JavaScript for explicit Save/Clear/Mark actions and manual submission; JavaScript enhances autosave, timer display/resync and safe palette navigation.

The exam layout collapses to a single-column responsive layout on smaller screens.

## Non-goals

Phase C does not implement:

- correctness scoring;
- partial-mark mathematics;
- negative-mark application;
- objective evaluation;
- subjective AI-assisted evaluation;
- result score;
- solutions display after submission;
- mistake classification;
- chapter/topic analytics;
- progress/mastery evidence;
- planner recommendations;
- retest generation.

The next phase should be Assessment Studio Phase D — Evaluation Engine.
