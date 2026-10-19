# Assessment Studio next-level product audit

## Verified baseline and method

Repository: `anandpriyadarsi/Personal--AI--Learning-Chatbot`.
Authoritative branch: `phase7.5.assessment-studio-ux/simplified-authoring`.
Verified remote and local commit: `c01e39d14d8945505e8acfa10a0fc2fb7cd2e058`.
Working branch: `phase7.5.assessment-studio-ux/next-level`; main is untouched.

Read the current A–F specifications and implementation reports, authoring UX,
blind-review/revision and simplified-authoring documents; traced routes,
services, SQLite repositories/migrations, templates, scripts and tests. Reviewed
both supplied desktop screenshots and Notes Studio/shared ANVAYA styling.
Baseline assessment regression: **84 passed**. Fresh-clone `backup.py` and
`dashboard.py` have inherited CRLF normalization differences; `git diff
--ignore-cr-at-eol` is empty. They are unrelated and excluded from the change.

Live browser attempt against the isolated fixture at
`http://127.0.0.1:5057/assessments` returned `net::ERR_BLOCKED_BY_CLIENT`.
This is an environment limitation, not a successful visual check. The supplied
screenshots are evidence of the earlier UI; current source is authoritative.

## What already works

The foundation is substantially complete: normalized templates, strict versioned
packages, atomic approval, attachment-only Alex handoff, immutable attempt
snapshots, server expiry, deterministic signed scoring, provisional grading,
confirmed-only intelligence, and explicit recovery/planner commands. Rebuilding
these systems would add risk without solving the product problem.

The product reads like its implementation phases. Home leads with templates,
creation has its own history, the library has another history, submission opens
an intermediate summary, results show every question and classification form,
and recovery loses the originating course context. The useful workflow exists,
but the student must assemble it.

## Surface audit

| Surface | Repository evidence | Finding and consequence |
|---|---|---|
| Home / information architecture | `templates/assessments.html`, routes `assessments` | Seven peer actions; template management precedes real attempts. No active-session or pending-review continuation. |
| Creation | `assessment_import.html`, `assessment_authoring.js`, package service `workspace` | The type → subject → focused workspace is sound and must remain. Drawer can open without moving focus; subject dialog has no accessible name or no-script path. |
| Package history | import repository `list_batches` | Default 100-row cap, no search or paging; revision histories compete with actionable packages. Rejected deletion is correctly server-guarded. |
| Blind preflight | `assessment_import_review.html`, review service | Strong hiding of content; four metrics, banners and two explanatory panels precede repair. Rejected packages still display a preflight action label. Approved packages link to a generic library instead of their test. |
| Test library | runner repository `list_runnable_assessments`, runner service `library`, `assessment_test_library.html` | Approved tests and sessions are separate lists with 100-row caps. No search/course/type/state filtering. Expired-but-unsynchronised history still says Active. Copy says scoring is a future phase although D exists. |
| Test preflight | `get_preflight`, `assessment_test_preflight.html` | Duration and instructions exist. Marking/section/type overview is absent; the student cannot inspect the negative-marking structure safely before starting. |
| Runner / response correctness | `assessment_runner.js` `responsePayload` | An untouched True/False radio serializes the first radio's value, True, on navigation or submission. Reproduced by running the actual script in a Node DOM/fetch harness. |
| Runner / save reliability | same script `autosave`, navigation, submit handlers | Errors become null and callers continue navigating/submitting. Overlapping debounced requests may finish out of order. Submission can lose an unsaved answer. Reproduced with rejected fetch. |
| Runner / timing and accessibility | script focus collector; `assessment_test_runner.html`; CSS runner rules | Hidden transition checks visibility after it changed, dropping preceding visible seconds. Timer and save messages share an announcement region; mobile palette precedes the question. Native controls and explicit submission already exist. |
| Submission / grading | `assessment_test_summary.html`, evaluation `response_editor`, `assessment_evaluation_review.html` | Submission has a sound explicit evaluate POST. Grading form uses `item.evaluation_id`, while editor returns only `id`, generating `/evaluations//review`. Existing test hand-builds the URL and misses the rendered-form defect. |
| Results / question review | evaluation `results` and `_decorate_question`, `assessment_evaluation_results.html` | Snapshot options, answers, solutions and timing already exist. UI shows option IDs, expands every question and repeats full mistake forms. Important unanswered/wrong/awaiting-grade items are hard to find. |
| Evidence correctness | evaluation repository `add_mistake`, `_sync_confirmed_mistakes` | A pending response may receive a confirmed mistake; subsequent full-credit grading syncs it to canonical mistakes despite a correct outcome. This can misdirect recovery. |
| Intelligence | Phase E service and global/course/session templates | Weighted performance, timing, difficulty, type, topics, trend and sample-size evidence are real. Many equal-weight panels hide the immediate decision. Preserve all analyses while prioritising review/recovery links and disclosing deeper sections. |
| Recovery / retest | adaptive service `workspace`, `assessment_adaptive_loop.html` | Explicit generate/apply and idempotent planner handoff are sound. Global queue loses course context; Alex recovery text is available but lacks a nearby context-preserving creation link. Do not claim a causal retest comparison that is not stored. |
| Visual / shared identity | `base.html`, `app.css`, `_assessment_workspace_subject_visuals`, Notes templates | Dark tokens and iris course styles already exist. Reuse them; do not introduce duplicate course presentation persistence. Large heroes, repetitive borders and extensive paragraphs create unnecessary height. |

Paths in the table are relative to `personal_learning_assistant/ui/web/` for
HTML/JS/CSS, `personal_learning_assistant/services/` for services and
`personal_learning_assistant/repositories/sqlite/` for repositories.

## Ranked improvement matrix

| Rank / candidate | Problem / evidence | Proposed solution / benefit | Complexity | Risk | Replaces or merges UI | Schema | Behavior | Decision |
|---|---|---|---|---|---|---|---|---|
| 1. Reliable exam actions | True/False phantom answer; swallowed saves; overlapping writes | Serialized saves, honest dirty/error status, retry, guarded navigation/submit, explicit unselected radio; preserves student work | Medium | Medium, race-sensitive | Existing runner interaction | None | Corrects defective writes | Now |
| 2. Trustworthy grading | Invalid form action; pending classifications can contaminate evidence | Stable editor ID and graded-outcome guards at service/repository boundaries | Low | Low | Existing grading path | None | Blocks premature mistakes | Now |
| 3. Lifecycle workspace | Home and two separate histories do not identify next work | Metadata-only read model; continue action; searchable, paged library with course/type/state filters and attempt links | Medium | Low, read-only | Home action bank + plain test list; legacy timeline remains disclosed | None | Navigation and presentation only | Now |
| 4. Focused result review | All questions and forms expanded; IDs instead of option text | One selected question with filter/palette, snapshot option texts, outcome/score/time overview and next step | Medium | Low | Existing results surface | None | GET review selection only | Now |
| 5. Compact safe preparation | Repair action buried; duplicate state labels | State-led blind preflight, compact facts, immediate handoff/revision or approve action; collapsed checks/setup | Low | Low | Existing review panels | None | No weaker approval | Now |
| 6. Exam readiness | No aggregate marking overview, narrow palette friction | Safe section/type/marks overview, collapsible palette, submission counts, labelled controls | Medium | Low | Existing preflight and runner layout | None | Presentation | Now |
| 7. Recovery continuity | Global queue loses course | Optional course filter preserved through PRG; direct Alex/retest creation entry, clearly course-wide evidence | Low | Low | Existing recovery surface | None | Filtering, no new authority | Now |
| 8. Shared course identity registry | Fallback depends on displayed catalogue index | Formal shared Notes/Assessment presentation resolver | Medium | Medium, cross-product | Both products | None | Course style lookup | Defer; preserve existing iris identity now |
| 9. Automatic wrong-question variants / question bank | Useful but requires reuse/provenance and leakage contracts | New bank and variant lineage | High | High | Adds subsystem | Likely | New academic behavior | Defer |
| 10. Retest comparison | No explicit original↔retest relationship | Persist lineage then compare confirmed like-for-like evidence | Medium | Medium | Adds comparison | Yes | New evidence semantics | Next candidate, not this change |
| 11. Pacing graph / answer-change replay | Reliable change history is not captured | Explicit event model with timing semantics first | High | High | Adds analytics | Yes | New collection | Defer; do not invent data |
| 12. Exports, calendar, internal AI | Does not remove the current core friction | Separate validated use cases | Medium/high | Medium/high | Adds surfaces | Varies | New behavior | Defer |

## Selected approach and alternatives

Chosen: an additive read-only lifecycle view around the existing command services,
plus focused repair of runner/grading and existing templates. It preserves route
compatibility and all academic authorities.

A cosmetic refresh would leave broken transitions and response loss intact.
A new assessment platform/schema would duplicate proven storage and expand scope.
Neither meets the highest-impact/lowest-risk balance.

Success: a returning student sees the current action first; a blind package needs
no question inspection; a save failure cannot silently discard work; results make
one question reviewable and recovery reachable without asserting unsupported
mastery or prediction. Existing advanced capabilities remain reachable.
