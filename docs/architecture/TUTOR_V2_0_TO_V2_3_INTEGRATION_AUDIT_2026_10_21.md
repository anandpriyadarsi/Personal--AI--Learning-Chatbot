# ANVAYA Tutor V2.0–V2.3 audit and controlled integration (21 October 2026)

## Authority and exact baseline

- Reviewed current protected `main`: `bf3ca0e7eb1bf6f51d900ab4a6cc69ca83a61eae` (merged Architecture V2.3).
- Legacy heads remain untouched:
  - `anvaya/tutor-2.0` @ `c4b2b9a9ec54d3c046c8be744a01c3e5d04e0711`.
  - `anvaya/tutor-2.1-adaptive-intelligence` @ `76be911c01b5a6e526f4a38e0bc3722c8f8887f7`.
  - `anvaya/tutor-2.2-student-model` @ `8c65f661c2a5c031a693c43836af5f6dae69bf77`.
  - `anvaya/tutor-2.3-teaching-orchestration` @ `7fd24eb6695d7e1a904494756aa333fee274427b`.
- Current `main` is 575 commits ahead of legacy 2.0/2.1/2.2 merge base and 443 ahead of 2.3 merge base. All four versions diverge. A naïve merge/replacement of legacy routes/templates/services would discard newer Learning, Assessment, UI, Library, Evidence and Planning changes.
- No Tutor V2.0–2.3 pull request currently targets main. Branch existence and local historical gate results do **not** establish current-main compatibility.

## What exists and what is proven

| Historical version | Implemented on historical branch | Current-main acceptance |
|---|---|---|
| 2.0 | Teaching prompts, safe Markdown renderer, source-first UI option, persistent tutor feedback, intent routing and UX controls | **Not certified** on merged V2.3 main |
| 2.1 | Session adaptive quiz state, hidden answer evaluation, bounded rational math checking, context-aware retrieval and topic-shift handling | **Not certified** on merged V2.3 main |
| 2.2 | Cross-session read-only student model, personalized policy, signals, explicit memory candidates and acceptance workflow | **Not certified**; schema/migration collision |
| 2.3 | Session goals, diagnostics, Socratic continuation, prerequisite repair, practice levels and exit checks | **Not certified**; incomplete live scenario acceptance |

The legacy `ANVAYA_TUTOR_2_3_LIVE_VALIDATION.md` describes a local automated *readiness* gate on 24 September 2026 (1,474 passed / 5 skipped / 1 deselected). It explicitly says the full live gate was **not** complete: scenarios A/B passed, scenario C fix needs live retest, and scenarios D–K were pending. The historical report is evidence of work done, not today's green integration gate. The earlier D false-positive repair and C follow-up work must be recovered and independently verified; do not presume the remote legacy head contains all uncommitted local patches.

## Hard integration blockers

1. **Conflicting migration identity.** Legacy Tutor 2.2 adds `personal_learning_assistant/repositories/sqlite/migrations/0009_tutor_memory_candidates.sql`, while current `main` already contains `0009_assessment_studio_foundation.sql` and later 0010–0014 Assessment migrations. Do not graft the old migration or renumber it casually. Review current migration ledger/runner and introduce any needed memory candidate schema only in a separately approved, reversible, migration-safe design (or keep it disabled).
2. **Large stale shared files.** Historical Tutor 2.3 `routes.py` has ~2,698 lines; current main has ~4,501. The historical Tutor templates, `__init__.py`, grounded service and academic agent service also differ. Never overwrite these wholesale; port only bounded changes with exact-route regression coverage.
3. **Missing live acceptance.** Reproduce C waiting-state correctness and D computational practice false-positive, then test all original A–K scenarios through actual browser/provider with disposable DB. Visible question and persisted pending answer state must agree. A practice sequence must never misclassify a normal explanation as a pending graded exercise.
4. **Source policy and evidence authority.** Maintain strict Source Only fail-closed behaviour; Source First general explanation must never acquire fabricated source or grade authority. V2.3 evidence is read-only source provenance, not Tutor automatic consumer consent.
5. **Record preservation.** Never point tests at installed DB, vault or indexes. Tutor 2.2 explicit memory approvals are not automatically authorized by this integration. Do not add uncontrolled LLM/provider calls during GET, silent global learning writes, migrations or import tasks.
6. **No current-head CI.** Historical PowerShell gate totals were run before dozens of newer features; require exact new-head Ubuntu + Windows, entire pytest and browser suite, source/fixture handling per current V2.3 public-private IKS split.

## Integration approach

Create fresh integration changes from current main. Keep historical Tutor branches unchanged. Stage independently:

1. **2.0 readability (this draft's implemented safe slice):** port local HTML-escaped Mistune formatting for assistant turns alone. Keep source labels as text, keep user content escaped, add page-scoped responsive formatting. No DB/schema, provider, route, academic evidence or source trust changes. Unit tests guard output and isolation.
2. **2.0 conversation and feedback:** integrate Tutor-owned feedback APIs and controls after verifying current routes/service schema, CSRF protections, provider isolation, form behaviour and original source policy. Browser-run login/session and persisted feedback cases. Do not merge untested UI.
3. **2.1 adaptation/correctness:** port pure state/verifier/retrieval components, make session-local metadata changes transaction-safe, run adversarial answer/malformed-marker tests and the specific 3x3 LU determinant/matrix checks. Provider failure must fail closed without hiding valid previous transcript.
4. **2.2 student model:** read-only projection first with source scopes, stale-state/consent limits and strict identity checking. Separately design migration and approval for durable memory candidates. Never infer mastery from Tutor session self-reports.
5. **2.3 pedagogy:** port and repair all A–K live scenarios (including C/D), ensure one pending question, explicit topic-shift cancellation, bounded adaptive difficulty, verified exit checks and visible persisted state alignment.
6. **V2.4 evidence bridge:** wire only documented, explicit opt-in source-bound Tutor handoff after V2.4 schema review; don't create automatic writes to other academic owners. Preserve modularity for parallel V2.4 work.

## Acceptance and merge decision

- The branch now contains the historical Tutor 2.1–2.3 backend and isolated regression suites, but **current-main cross-platform and live A–K acceptance is still unverified**. Being committed is not the same as being accepted.
- Require tests for every implemented slice, head-SHA Ubuntu/Windows matrix plus real Playwright source/feedback/question scenarios, hard failure of any unrelated regression, and independent security/data-safety review.
- The public Architecture V2.3 gate may omit only its four exact genuine IKS external test identities under the already merged split. They remain individually BLOCKED under private certification; do not delete, disguise or treat them as passes.
- Full Tutor 2.3 cannot be declared complete without A–K real UI/provid​​er checks, C/D regression fixes, safe migration design and owner-data protection.
- **NO GO for wholesale legacy branch merge or deployment.** Do not merge this initial read-only subset into main until exact-head CI, review and browser checks are green. Merge later slices only when independently safe.
- If an approval or source validation cannot run, report it as blocked rather than inventing proof.

## Useful manual scenario after verified integration

Run a disposable MA103N LU session: diagnose missing elimination-multiplier concept, preserve a hint/pending question, solve one bounded multiplier practice, refuse an invented mastery conclusion, ask a one-shot exit check, then reopen when student reports new confusion. Verify persisted session state after refresh and no changes to grades, planning, Learning resources or installed database.

## Development performed on the dedicated reconciliation branch

The implementation has progressed beyond the initial read-only 2.0 slice:

- Restored the legacy 2.1 adaptive state, bounded deterministic correctness, retrieval planning, and 2.3 teaching orchestration components as separate Python modules.
- Ported the legacy runtime contracts to current Tutor-owned `grounded_tutor_service.py`, `TutorSessionService`, `SQLiteTutorRepository`, and grounding models without replacing the current ANVAYA Flask route map, Home, Learning Studio, Assessment, Planning, Library, or architecture V2.3 evidence UI.
- Added session-state and read-only historical model visibility to the current Tutor route; follow-up buttons populate a draft but **never submit it without explicit student action**.
- Restored a narrow feedback endpoint and secured its POST form with a process-local CSRF token. Feedback does not write grades, plans, mastery or progress.
- Preserved legacy Tutor 2.2 candidate-domain logic but relocated the conflicting `0009_tutor_memory_candidates.sql` to reserved **optional 0016**. The default `apply_migrations(...)` still applies mandatory 0001–0014 only. Assessment optional 0015 and Tutor optional 0016 have separate flags and checksum histories. **Tutor 0016 is never applied by normal startup**. Student memory review routes also require `TUTOR_MEMORY_ENABLED` and a valid CSRF token. Do not enable either in an installed database without a separately approved backup and migration procedure.
- Restored original Tutor 2.1–2.3 regression suites and legacy Tutor 2.3 read-only inspector/Windows live readiness reference. Added a focused native Ubuntu/Windows Actions workflow and a three-width real Chromium Tutor interaction test with fake source/provider and disposable state.
- Changed only the browser new-session choice to Source First by default, with Strict Source Only still available; Knowledge Reader handoffs retain their strict source policy.

### Outstanding acceptance and data-safety checks

1. The current branch's exact SHA must pass **both** Tutor-focused native GitHub runners, architecture synthetic validation, UI V2, Assessment, Learning/Library and real Chromium screen checks. Historical 2026-09 totals are not present-day results.
2. The historical 2.3.7 live A–K script is only a *readiness* protocol. Scenario C must be rerun against the current stack, and D–K require observed sessions. C's provider-generated pending question and D's computational-practice classification must agree with persisted Tutor state. Real configured-provider acceptance is distinct from synthetic browser checks.
3. Independent privacy/identity review for optional 0016 memory candidates, callback CSRF and safe escaping is required before installed opt-in. Do not apply optional schema 0016 or write long-term memory to the user's installed ANVAYA database while validating this branch.
4. Check the current main checkout and all concurrently evolving Architecture V2.4 branches before any merge. This PR is deliberately **draft** and the owner requested to review integration before merging.
5. Cross-studio academic evidence is not automatic Tutor state mutation; a future V2.4 consumer must use explicit source identities and consent. No deployment or personal-data import is authorized.

### Recommended Windows source-only evaluation

Run full tests in a freshly cloned, disposable worktree, with requirements pinned and real Chromium installed. Do **not** run the historical 2.3.7 script against the installed academic database without reviewing its expected source paths. Use `ANVAYA_BROWSER_TESTS=1` for native browser tests. Review all A–K outcomes before changing Tutor memory opt-ins. A branch rollback needs only code changes while optional 0016 remains unapplied.
