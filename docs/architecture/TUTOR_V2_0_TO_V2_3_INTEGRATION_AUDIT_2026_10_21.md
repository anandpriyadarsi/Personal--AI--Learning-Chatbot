# Tutor V2.0–V2.3 integration: implementation and acceptance

Updated 21 October 2026. PR #32 remains **DRAFT / NOT MERGE-READY**. No merge or deployment.

## Baselines and parallel ownership

Continued the existing integration branch at `37cdf8c6825fcab6583e49862f7304fd383d911b`, preserving all 42 integration commits. Main remains `bf3ca0e7eb1bf6f51d900ab4a6cc69ca83a61eae`. Architecture V2.4 PR #33 remains separate at `951e0c75733a4c2f5528b73c7f63c84ff9431361`. Neither branch was overwritten or merged.

Historical read-only references retained:

| Version | Original branch head | Current implementation | Fresh acceptance |
|---|---|---|---|
| 2.0 | `c4b2b9a9ec54d3c046c8be744a01c3e5d04e0711` | Tutor Markdown, followup drafts, feedback, agent routes/templates | Readability, HTTP, CSRF and Chromium suites |
| 2.1 | `76be911c01b5a6e526f4a38e0bc3722c8f8887f7` | Adaptive state, rational verifier, retrieval planner, atomic exchange | Original adaptive/correctness/retrieval suites plus new failure/replay regressions |
| 2.2 | `8c65f661c2a5c031a693c43836af5f6dae69bf77` | Read-only scoped student model, stable signals, policy, optional memory 0016 | Original model/signal/policy/memory suites; new optional-schema matrix |
| 2.3 | `7fd24eb6695d7e1a904494756aa333fee274427b` | Goals, diagnostics, prerequisite repair, adaptive practice, exit checks | Original orchestration suites and real-service browser journey; live A–K BLOCKED |

No stale whole-file replacement of routes, global CSS, Assessment, Learning Studio, Planning, Topic Intelligence, Library or Obsidian. V2.4's offline lesson assistance is not treated as a durable Tutor session/evidence API. No invented V2.4 adapter, broad migration or cross-owner writer was added. Reconcile both PRs explicitly before integration; shared app/Knowledge templates may need line-level composition.

## Actual fixes in this continuation

- Reproduced eight baseline integration failures: seven missing UI teaching/history contracts and SQL schema probing placed in the web adapter. Restored visible diagnostic/prerequisite/practice/exit/history information, with session-local/non-mastery labels, and moved optional-schema probing into the canonical Tutor repository. Original assertions remain; valid browser POST tests now supply the required CSRF token.
- Reproduced Scenario D false positives: explanation/refusal paragraphs became pending practice. Pending imperative tasks now require an explicit task; solved-task suffixes are rejected while task givens and a previous answer followed by a new task remain supported. Scenario C now persists the actual question, without a preceding same-line explanation.
- Strip malformed/private answer-evaluation markers without inventing correctness; reject malformed/unclosed math metadata. Existing supported rational matrix/vector/determinant checks and one bounded repair remain intact.
- Persist both turns, evidence and adaptive metadata in one Tutor-owned transaction. No SQLite lock is held while generating. At the first write, compare the session snapshot under an immediate lock; reject stale concurrent generation. Failed assistant/state writes roll back both turns. Repository/storage failures become a safe recoverable web response.
- Actual browser forms carry request identities and CSRF tokens. The last 32 persisted request receipts reuse the saved answer on retry without another provider call; hashes bind a receipt to its question and session. Eviction uses turn ordinal, surviving sorted JSON serialization. This is a bounded retry window, not indefinite deduplication.
- Helpful buttons maintain one current helpful-only vote per turn; identical retries are idempotent and toggles update that opinion. Rich rating/free-text feedback retains its established owner and append behavior.
- Require CSRF for create, ask, feedback, memory actions and Knowledge Reader Tutor handoffs. Optional memory remains disabled. Provider-authored raw HTML remains escaped and Markdown images remain inert alt text, preventing automatic external image requests.
- Parse explicit LaTeX without Markdown consuming backslashes. Reuse the existing bounded local math DOM renderer for matrices/symbols/indices; preserve code/student literals. Fix complete-command replacement so infinity and unsupported commands remain accurate. Explicit TeX unbraced indices are grouped without changing Assessment's legacy multi-character plain-text index contract. Unsupported LaTeX remains literal and is disclosed; no CDN/remote math dependency.
- Display canonical course code, distinguish uncited general explanations from retrieved context, and link exact evidence identities to the original Knowledge Reader. Retrieved chunks are context, not proof of provider fidelity or academic authority.
- Repair invalid job-level `runner.temp` context in Tutor CI, retain every restored suite, add new integration/browser/schema cases, and name artifacts by the checked-out feature SHA. Native environment and SQLite state evidence accompany captures.
- Full regression after 10:00 UTC exposed a pre-existing V2.3 fixture-clock mismatch: backlog task creation used the wall clock while projection used frozen NOW. Inject the existing frozen clock into the canonical test writer; retain all planning/self-report and future-record rejection assertions. The independent reviewer approved this deterministic fixture repair (20 tests pass). Tutor-focused native Ubuntu/Windows at the first continuation head each passed 234 tests; final-head gates must rerun after this fixture-only followup.

## Fresh deterministic and browser evidence

Local acceptance uses disposable synthetic databases and fake providers, with the real Flask service, repository and Chromium. It is not configured-provider certification. Logs/XML and unedited captures are supplied in the evidence archive; the PR links exact-head native runs when available.

New suites: `tests/test_tutor_final_integration.py`, `tests/test_tutor_final_browser.py`, `tests/test_tutor_optional_schema.py`. Existing suites are retained. Real browser coverage includes create → prerequisite question → refresh → draft hint → answer `3` → computational practice → incorrect answer with one-level reduction → topic shift → mixed understanding question → one-shot exit check → likely_met → reopened confusion → duplicate/toggled feedback → invalid CSRF. The read-only inspector agrees with persisted metadata. Exact-source navigation and strict handoff are separately exercised. Matrix cells, subscripts, infinity, escaped injection, no unexpected external requests, literal code and viewport overflow are asserted at 390/768/1366.

Baseline before fixes: 190 passed, 8 failed, 3 browser-disabled skips. The earlier native head failed full regression on the same eight integration cases (Ubuntu UI full: 2941 passed, 8 failed, 4 private skips). Earlier native Assessment acceptance passed. Those historical results are not current-head certification.

## Live A–K gate

No `LLM_API_URL`, `LLM_API_KEY` or `LLM_MODEL` was configured. No real-provider call or charge was made.

| Scenario | Required observed behavior | Configured-provider result |
|---|---|---|
| A | One diagnostic for vague LU gap | BLOCKED |
| B | Hint preserves question and answer loop | BLOCKED |
| C | Scoped prerequisite repair, answer `3`, return to goal | BLOCKED |
| D | One unsolved computational task, stored pending, bounded adaptation | BLOCKED |
| E | Explicit easier/harder overrides historical policy | BLOCKED |
| F | Topic shift clears obsolete practice/goal anchors | BLOCKED |
| G | Mixed understanding plus basis question remains teaching | BLOCKED |
| H | One exit check, qualified likely_met only after evaluation | BLOCKED |
| I | New confusion reopens qualified session goal | BLOCKED |
| J | Neutral deterministic strict-source exit question | BLOCKED |
| K | Readable 3×3 LU, supported verification, repair/blocking and persistence | BLOCKED |

Original diagnostic/prerequisite/practice/goal/correctness tests and synthetic browser results support these behaviors independently but cannot convert any row into a live pass. Use `ANVAYA_TUTOR_2_3_LIVE_VALIDATION.md` and `tutor23_live_inspect.py` on a disposable course-scoped database once the owner configures a provider. Capture actual conversation, metadata, counts and outcomes per scenario.

## Data safety and rollback

No installed database, vault, academic source or retrieval index was available/used for these changes. Consequently installed-data hash certification is unavailable, rather than fabricated. All test databases live under temporary test paths. The real-service browser test compares every pre-existing non-Tutor table count before/after the journey. The inspector is independently hash-tested as read-only.

Mandatory migrations remain 0001–0014. Tests exercise neither option, Assessment 0015 alone, Tutor 0016 alone, both, default restart after prior optional application, checksum drift, and failed optional DDL rollback. No historical migration changed. Normal startup does not apply 0016; `TUTOR_MEMORY_ENABLED` defaults false. Existing explicit proposal/review domain tests retain source/course checks and one-time approval behavior. Installed memory activation still requires separately reviewed backup and owner authorization.

Code rollback is a revert of this continuation while 0016 stays unapplied; retain all user Tutor rows. Never delete academic records to roll back code, drop optional installed tables, or rewrite checksum history. If 0016 was explicitly applied outside this work, preserve its schema/ledger and perform a separate reviewed compatibility decision.

## Independent review and limits

An independent reviewer reproduced stale writes, malformed state, receipt ordering, CSRF omission, remote Markdown images, feedback toggles and math DOM defects, driving regression fixes. Final review found no unresolved critical/important defect in the reviewed changes. Practice detection is conservative heuristic parsing; provider obedience and calculation/citation fidelity remain live acceptance responsibilities. The math renderer intentionally supports a bounded subset, not arbitrary LaTeX or symbolic verification.

The four original private IKS test identities remain intact and individually BLOCKED without the genuine owner-controlled ZIPs. The merged public skip allowance is unchanged. Hosted Windows is a native synthetic test environment; it does not grant student-installed Windows/B3/WAL authority.

## Safe Windows review commands

Use a fresh disposable review worktree, not the folder holding the installed academic database:

```powershell
git fetch origin
git worktree add ..\ANVAYA-Tutor-review origin/integration/tutor-v2-0-2-3-safe-reconciliation-2026-10-21
Set-Location ..\ANVAYA-Tutor-review
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-assessment-browser.txt
python -m playwright install chromium
$env:ANVAYA_BROWSER_TESTS='1'
$env:ANVAYA_TUTOR_MEMORY_ENABLED='false'
python -m pytest -q tests/test_tutor*.py tests/test_phase7_5_academic_agent_web.py tests/test_phase7_5_12_2_web.py
```

Normal local launch remains `python phase7_web.py` in the normal configured installation. Do not use it as a source-only test: the existing launcher can activate Assessment 0015 and its authorized WAL publisher. This continuation did not run that launcher against installed records or enable Tutor memory. A provider configuration or optional-migration approval is not included in these review commands.

## Merge decision and next phase

**NOT MERGE-READY.** Require green mandatory native jobs on the exact final head, configured-provider A–K, reviewed V2.4 composition, and owner approval before merging. Never use old green jobs as a substitute. Report genuinely blocked private/installed authority separately.

After stable integration, consider new Tutor 2.4 work only against reviewed versioned V2.4 handoff contracts: explicit source-bound assistance attribution, calibrated rechecks and accessible wider math support. No training/fine-tuning or automatic mastery/planner writes are part of this phase.
