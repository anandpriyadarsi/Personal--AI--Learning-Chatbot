# Tutor V2.3.7 cloud acceptance — 22 October 2026

**Decision: NOT MERGE-READY. Keep PR #32 draft; do not merge or deploy.**

This continuation starts at `a7f0e5d2668834a9affd71575bc1b508fa8dbeb0`
on `integration/tutor-v2-0-2-3-safe-reconciliation-2026-10-21`.
The checked main baseline is `bf3ca0e7eb1bf6f51d900ab4a6cc69ca83a61eae`.
No historical Tutor port was repeated and no parallel Architecture V2.4
branch was modified. The final exact commit, native job results and downloadable
artifacts are recorded in PR #32 and in each generated evidence manifest.

## Actual defects repaired

1. **Scenario F:** the exact acceptance prompt “Skip the practice question.
   Now explain determinant expansion by cofactors. Do not continue LU.”
   cleared the question but retained the LU goal and a practice teaching plan.
   The first real-browser A–K run reproduced this at all three widths:
   **36 passed, 3 failed**. Intent classification counted the cancelled word
   “practice”; goal comparison counted the explicitly rejected LU topic.
   A shared, bounded view of the affirmative teaching request now excludes
   explicit cancellation clauses from intent and goal comparison. A genuine
   topic shift clears stale misconception/practice anchors before processing
   a generic pending-question override. The original text still reaches the
   provider and remains in the transcript.
2. **Normal UI topic scope:** the domain and retrieval planner supported topic
   identity, but the normal Tutor creation form/service did not forward it.
   The form now offers canonical course topics, filters them when the course
   changes, and persists the selected topic through the existing session
   service. Server-side validation rejects missing courses, unknown topics
   and cross-course topics. Whole-course sessions remain available for F/G
   and deliberate topic changes; topic-scoped sessions retain their fixed
   source boundary. Existing sessions are untouched.

The regression tests were observed failing before each production fix.
No original assertion was removed; the explicit workspace-key assertion now
also requires the new `tutor_topics` field.

Independent review reproduced two additional edge cases in the first fix:
negated cancellation ("Do not cancel the question. My answer is 3.") must
remain an answer, and cancelling a question while requesting the same LU
topic must preserve relevant misconception and level context. Four new
regressions were observed failing, then passing after anchoring affirmative
cancellation commands and comparing the pending question together with its
recorded gap. The reviewer exhausted its available runtime before a complete
final review; these findings are addressed, but no complete independent
sign-off is claimed. A separate author review checks the remaining delta.

A second available independent reviewer completed the scoped review and
identified two further Important cases: polite replacement requests and
cancellation without a replacement. Five new regressions reproduced both.
The fix accepts ordinary polite instruction prefixes and handles cancellation
as a deterministic workflow acknowledgement: no new task, provider call or
invented goal. The browser F scenario also checks both variants at every
width. Source First and Source Only cancellation work without a provider.
The review found no additional Critical/Important source-scope or security
defect; its two findings are tracked by the red-to-green tests and final suite.

The final full regression also exposed transient Assessment palette overflow:
at 50% and 75% of its real closing transition, the document could grow to
1941 px in a 1920 px viewport. An intermediate-frame Chromium reproduction
failed deterministically. A scoped `overflow-x: clip` rule contains that
animation without creating a scrolling ancestor for sticky controls; the
original no-overflow assertion is retained. Its regression runs in native
Tutor acceptance as well as the full Assessment suite.

## Browser evidence and honest certification

`tests/test_tutor23_cloud_acceptance.py` launches the **actual Flask
application**, sends forms through **actual Chromium over HTTP**, executes
the production web/Tutor/repository code and independently inspects the
saved SQLite session after each answer and refresh. Only provider generation
is scripted (`SequenceProvider`); retrieval is an observed empty test boundary,
not a claim of live indexed retrieval. Each scenario uses a newly created
synthetic database with canonical MA103N topics. Widths: **390, 768, 1366 px**.

| Scenario | Contract checked in real browser and persisted state | Provider-dependent certification |
|---|---|---|
| A | One deterministic diagnostic; pending question; no provider call | No LLM needed for this branch; broader live certificate blocked |
| B | Hint preserves original question; answer follows Socratic lineage; hidden evaluation absent | BLOCKED without real provider |
| C | One canonical scoped prerequisite; return to LU; stored follow-up; `3` evaluated after refresh | BLOCKED without real provider |
| D | Unsolved computational task; correct +1 and incorrect −1; level 1–5 | BLOCKED without real provider |
| E | Explicit harder/easier retains computational format and changes one level | BLOCKED without real provider |
| F | Cancelled practice cleared; new cofactor goal and explanation plan | BLOCKED without real provider |
| G | Mixed understanding/new basis question stays a teaching request | BLOCKED without real provider |
| H | Single deterministic exit check; evaluated reply yields session-local likely_met, not mastery | Evaluation BLOCKED without real provider |
| I | New confusion reopens likely_met with qualified unresolved evidence | Generated teaching BLOCKED without real provider |
| J | Source Only asks a neutral deterministic exit check without sources or provider; insufficient support disclosed | No LLM needed for this branch |
| K | Correct 3×3 LU matrices render; supported product checked; one repair or fail closed | BLOCKED without real provider |

Browser test results are generated, not inferred: `tutor-AK-*-report.json`
contains the observed response, expected contract, all step-by-step inspector
states, provider label, exact source SHA, native platform and PASS/FAIL.
`tutor-AK-*.png` are unedited full-page Chromium screenshots. K has separate
`passed`, `repaired` and `blocked` subcases. A fail-closed K subcase is a passing
safety contract, **not** a failed calculation presented as a correct answer.

The actual HTTP adapter's unconfigured path is separately exercised through
the browser; a provider error must leave the saved session unchanged.
`tutor-provider-availability.json` records only configuration-presence
booleans, never values. This cloud session had no `LLM_API_URL`, `LLM_API_KEY`
or `LLM_MODEL`; no real-provider generation or charge occurred. Scripted
responses and hidden scripted evaluations do **not** certify the teaching
quality or answer grading of any real model. Full configured-provider A–K
therefore remains **BLOCKED**, not PASS.

## Reproduction without a personal laptop

The existing native GitHub Actions Tutor workflow retains every original
suite and includes the A–K, cancellation and normal topic-scope tests. Its
Ubuntu and Windows jobs install Chromium and upload JUnit, environment,
screenshots and JSON states under the exact checked-out PR head.

From an isolated cloud checkout with the tracked dependencies and Chromium:

```bash
ANVAYA_BROWSER_TESTS=1 ANVAYA_VALIDATION_ARTIFACTS=/tmp/anvaya-tutor-evidence \
python -m pytest -q tests/test_tutor*.py \
  tests/test_phase7_5_academic_agent_web.py \
  tests/learning_studio/test_educational_projection_v23.py \
  --junitxml=/tmp/anvaya-tutor-evidence/tutor.xml
```

Use an external directory for artifacts. On Windows, set the same two
environment variables in PowerShell before the equivalent `python -m pytest`
command, or use the native Actions job. The tests do not require copying or
starting the student's installed database. No manual laptop step is needed
for these reproducible browser contracts.

## Safety and remaining gates

- Each scenario hashes **every row of every non-Tutor table** before/after,
  as well as recording counts. Only Tutor sessions/turns/evidence/feedback
  may change. Hashes catch updates that counts alone would miss.
- Optional Tutor migration 0016 is not applied by these journeys; the
  candidate table must be absent. Optional-schema combinations remain covered
  by the retained dedicated suite. No migration file was changed.
- No installed database, private vault, retrieval index or academic record is
  opened or copied. Their owner-controlled hashes cannot be claimed from a
  cloud run; this absence is disclosed, not replaced with synthetic hashes.
- The four private IKS fixture tests and their exact-identity public exception
  are unchanged. Private fixture certification remains separately BLOCKED.
- Source-policy, rendering/XSS, feedback/CSRF, atomic persistence, receipt replay
  and original studio preservation tests remain in the retained suites.
- Final native and full-suite results must come from the exact current head.
  Running, queued, missing or failed jobs are not a pass. Consult PR #32's
  final evidence rather than historical September readiness totals.
- A secure configured provider is still required for full live certification.
  Once securely supplied to the cloud runtime, repeat the original A–K prompts,
  answer each actual generated question, inspect each saved state and retain
  fresh screenshots. Never submit API credentials in a PR, report or chat log.

Rollback: revert this continuation's commit on the Tutor branch. It makes no
schema change and does not require deleting sessions or academic data.
