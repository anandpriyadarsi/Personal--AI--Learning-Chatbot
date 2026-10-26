# ANVAYA — GATE B3: TRUSTED ATTRIBUTION, AUTHORITY LINEAGE & PROJECTION SAFETY

## PRIMARY EXECUTION INSTRUCTIONS FOR CHATGPT WORK
### One conversation: verify current main → implement independently safe B3 work → test on Linux and Windows → independently review → commit and push feature branch → issue precise handoff

**Project:** `anandpriyadarsi/Personal--AI--Learning-Chatbot`

**Verified entry state, 13 October 2026:**
- `main` HEAD: `e15c347e5a7bf58c7ec29708eee49b1fed13f712`.
- Pull Request #8 merged Gate A + Topic Intelligence B1/B2 into `main`.
- PR integration validation: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38367859776 (Ubuntu, Windows and aggregate successful).
- B2 source-only final feature evidence: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38337824753.
- Existing source migrations: `0001`–`0014` (all applied source checksums must remain immutable).
- User has launched the merged Windows ANVAYA application successfully; the Home dashboard renders academic data. **This is a UI smoke observation, not proof of installed SQLite schema, projection parity, or data authority.**
- `GATE_A_LOCAL_PRODUCTION_AUTHORITY` remains **UNVERIFIED** until evidence proves actual installation, backend, canonical ID lineage, migration parity, and projection freshness.

Treat these facts as a starting checkpoint, not assumptions about the repository when Work runs. **Fetch GitHub and establish current HEAD and latest PRs first.** If B3 already exists, resume and reconcile it rather than duplicating work.

## 1. User's goals and scope

I want ANVAYA to become a trustworthy learning-intelligence system before adding Analysis 2.0, Planning 2.0 or Tutor 2.0. Complete as much of Gate B3 as can be safely implemented now, with minimal hands-on Windows work from me.

Specifically:
1. Stabilize the B3 evidence contract across canonical topics, assessment responses, mapping review, grading confidence, independence/assistance, source IDs and compatibility projections.
2. Develop real, deterministic source code and tests; **do not stop at another architecture audit**.
3. Automate validation with disposable data, full Python/Node suites and real Chromium on Ubuntu and Windows GitHub Actions.
4. Preserve existing courses, assessment scores, completed sessions, Coding Helper 2.0, Notes, Library, Planning, Analysis and the working web app.
5. Separate **DEV CODE READY** from **LOCAL PRODUCTION AUTHORITY VERIFIED** and **PRODUCTION DEPLOYMENT AUTHORIZED**.
6. Ask me for a Windows action only if no safe automation or existing source evidence can establish the needed fact. Limit the remaining manual action to one short, redacted collector invocation whenever technically possible.

**Authorization:** Choose the smallest safe B3 design; implement approved source-only steps without waiting for design approval; create/test/push a dedicated feature branch. Do **not** merge to `main`, run production migrations, change existing academic records, deploy or enable new live read/write paths without a later explicit authorization.

## 2. Recover and verify, do not repeat prior work

Read these tracked GitHub files and any relevant current code/tests:
- `ANVAYA_B2_NEXT_GATE_HANDOFF.md`
- `ANVAYA_TOPIC_INTELLIGENCE_B1_REPORT.md`
- `ANVAYA_TOPIC_INTELLIGENCE_B2_READ_SAFETY_REPORT.md`
- `ANVAYA_GATE_B2_VALIDATION_REPORT.md`
- `ANVAYA_GATE_A_AUTOMATED_VALIDATION_REPORT.md`
- `ANVAYA_PLANNING_ANALYSIS_IMPLEMENTATION_ADDENDUM_2026_10_11.md`
- `ANVAYA_ASSESSMENT_PAUSE_OFFLINE_SUBJECTIVE_SPEC.md`
- `personal_learning_assistant/domain/topic_intelligence.py`
- `personal_learning_assistant/repositories/sqlite/topic_intelligence_repository.py`
- `personal_learning_assistant/repositories/structured_authority_router.py`
- `scripts/architecture_validation.py`
- `scripts/architecture_local_collector.py`
- `.github/workflows/architecture-validation.yml`
- assessment runner, evaluation, intelligence, mapping, import, migration and service code.

Recover the October audit's `ANVAYA_TOPIC_INTELLIGENCE_ARCHITECTURE_SPEC.md` and `ANVAYA_PLANNING_ANALYSIS_IMPLEMENTATION_PLAN.md` if accessible in uploaded/Library material. If not, use the concrete GitHub code plus the required policy invariants below. **Do not fabricate access to unavailable files or insist on another manual upload.**

Run and preserve exact output of:
```bash
pwd
git worktree list --porcelain
git branch --show-current
git rev-parse HEAD
git status --porcelain=v1 -uall
git fetch origin
git rev-parse origin/main
git log -12 --oneline --decorate
git branch -avv
git diff --check
```

Confirm the B1/B2 merge commit, all its ancestors, 14 SQL migration files, and full hosted Ubuntu/Windows PR acceptance. Detect existing dirty/other worktrees. Never reset, clean or overwrite them. Create an isolated feature branch **from the new verified `origin/main`**; proposed name `anvaya/topic-intelligence-b3-attribution-authority` (adjust if already exists). Record original main SHA and merge base. Do not branch from premerge B2, Tutor, Library or Learning Studio.

## 3. Strict architecture boundaries

The current B1 closed-snapshot reader is NOT a live-database reader. It requires an explicitly attested stable closed, sidecar-free artifact and must never be pointed at a live WAL database. B2's normal app read path is a different existing WAL-aware, `mode=ro`/`PRAGMA query_only` boundary.

B3 must preserve:
- Exact canonical `(course_id, topic_id)` identity; no name-based cross-course substitutions or deleted-topic rebinding.
- Existing official assessment score/response/evaluation snapshots and result calculations; no regrading.
- Separate mapping review confidence, grading confidence, assessment authorship confidence, independent-attempt declaration and student self-confidence. Never combine them into an invented score.
- Historical mapping and independence trust as **unknown** unless exact historical provenance is actually available and reviewed. No backfill by `topic_id`, exam mode, provider prose or current mutable mapping.
- Self-entered subjective marks and assisted practice as supporting evidence, not independent confirmed performance.
- Separate provenance for assessment question identity, normalized content-equivalence groups, original source IDs, session ID, evaluation ID and mistake-event bridges. One evaluation remains one observation; bridge rows are not extra attempts.
- GET/preview does not create missing JSON, apply migrations, write a recommendation, start Tutor, call a provider, generate an index or mutate official progress.
- A read-only SQLite connection can legitimately coordinate WAL/SHM; compare logical SQL state and protected-source inventory, and distinguish SQLite coordination from data mutation. Do not delete live sidecars.
- Confidence and absence of evidence are never interpreted as mastery, weakness or a 0% score.

Do not implement recovery thresholds/policy (Gate C), new Analysis/Planning interfaces (Gates D/E), Tutor adaptive logic, Learning Studio integration, assessment pause or paper self-grade in this B3 phase. Preserve the existing designs and document future dependencies.

## 4. B3 work packages: do independent work first

### B3-A — source-only authority and provenance contracts (AUTHORIZED NOW)

Implement actual code and regression tests against disposable databases, even if installed-production evidence is unavailable.

**A1. Authority/inventory inspector and contracts**
- Inspect existing authorities for courses, topics, aliases, question-topic mapping, reviewed imports, session-question snapshots, response evaluations, attempt/mistake bridges, planner projections and compatibility controls.
- Produce a deterministic, read-only, reusable `B3AuthorityManifest`/schema adapter or equivalent design fitted to the actual code, not a duplicate authority store.
- Separate source migration ledger/checksum, normalized FK identity, compatibility projection version/freshness, relationship counts, mapping snapshot availability, and warnings.
- Provide typed unknown/blocked/invalid states, not silent default success. A projection **key count is NOT a parity/freshness check**.
- Add explicit reproducible disposable-fixture checks for legacy backend, promoted backend, missing/partial/corrupt projection, missing controls, stale projection and conflicting canonical IDs.
- Make possible parity checks compare source IDs and revision/fingerprint/watermark when available; if missing, report `UNVERIFIABLE` and propose what minimal verified metadata must be stored later. Do not invent an existing projection watermark.

**A2. Evidence attribution/read models**
- Inspect real B1 DTO and repository plus assessment/evaluation consumers. Reuse them; do not rewrite stable B1/B2.
- Implement immutable, strictly typed forward-compatible attribution DTOs/adapters (or the smallest suitable source-only additions) representing mapping reference/state/method/reviewer/date/confidence, content identity and independence/assistance exposure with `unknown` as a valid default.
- Support exact source IDs, snapshot timestamps, course/topic consistency and time-zone aware provenance.
- Preserve reviewer authority separately from package author confidence, grading confidence, and `declared_independent` status. Never silently treat `exam` or Coding Helper disabled policy as proof of no external assistance.
- For B3-A synthetic fixtures, mark historical attribution unavailable; only an intentionally, explicitly reviewed test fixture may qualify as reviewed evidence.
- Build a deterministic, query-only read composition contract; existing result/recovery reports remain unchanged. If binding to the web app would depend on missing production lineage, DO NOT connect it yet.
- No new policy decisions, automatic recovery, auto task creation, user-facing mastery or live provider call.

**A3. Safe redacted local collector improvement**
- Reuse the tracked `scripts/architecture_local_collector.py`; do not replace it with a second incompatible helper.
- Identify the minimum remaining *production-only* facts not provable by CI: actual launcher and interpreter/checkout match, backend-control mode, copied DB schema ledger, canonical source/projection IDs and revision/freshness evidence.
- Make a minimal tested enhancement or companion `scripts/b3_authority_report.py` if genuinely needed, producing only redacted aggregates, booleans, count-of-mismatches, schema/migration hashes and status/reason codes. **No academic row contents, learner responses, original local paths, credentials or vault text in the shareable JSON.** No uploads to CI.
- Default command must never connect to/copy production database. Any copied-schema inspection needs an *explicit* user acknowledgement that all app/database/backup/sync writers are stopped, a stable copy including main/WAL/SHM where present, copied-path `mode=ro` and `query_only`, post-copy integrity/hash checks, local automatic disposal and fail-closed behavior. Never copy only the main file while WAL is active; no checkpoint or migration against the original.
- Be honest: process enumeration alone does not prove the absence of hidden writers. If consistency cannot be established, `BLOCKED` is correct.
- The collector should have synthetic Windows-compatible regression tests for safe default, malformed control, sidecar presence, stable copy, missing table, projection mismatch, permissions, redaction and no-write behavior.

**A4. Complete DEV validation**
- Run fail-first tests for each behavior actually changed, then focused tests, whole unchanged pytest suite, B1/B2 read-safety tests, fixture orders, all characterization cases, JS, Playwright/Chromium, migration/checksum/FK/integrity tests and `pip check`/compile/diff checks.
- Use `python scripts/architecture_validation.py --output <fresh-owned-external-directory>` with the existing tracked requirements and browser installation; improve the harness only for reproduced portability defects, preserving assertions and test coverage.
- Existing A/B/D/P product-defect characterizations must stay honest. B2's resolved C must not be reintroduced. Do not delete/skip tests to reach green or hide new failures under a baseline allowance.
- In CI, run Ubuntu and Windows at the *exact source SHA* with aggregate required acceptance, bounded realistic test timeouts, artifact upload even after failures, full JUnit case/failure/skip manifests and meaningful Playwright screenshots. Avoid a Windows-only manual screenshot gate.
- Independently review the entire B3-A delta for SQL authorization, mutable review provenance, symlink/path escape, partial transaction, leakage, timestamp and Unicode normalization bugs. Repair Important/Critical findings with regressions; rerun.

**B3-A deliverable:** real tested/pushed source-only feature code and a detailed report. It may finish with `B3_DEV_SOURCE_ONLY=PASS` while production authority remains `BLOCKED`. Do not confuse these.

### B3-B — immutable new-session writer and canonical projection contract (CONDITIONAL)

Proceed with B3-B product-schema/writer implementation **only if genuine installed Windows schema/authority/lineage is available and reviewed** or a separately verifiable, complete authoritative production-compatible schema lineage has been established without unsafe assumptions. A synthetic 0014 schema alone does NOT satisfy this condition.

Prerequisite must establish:
1. Installed `phase7_web.py` launcher, exact checkout/main SHA and interpreter actually used.
2. Authoritative `config.DATABASE_PATH`, control/backend selection and local source identity.
3. Closed/stable read-only copy's `schema_migrations` versions/names/checksums, `integrity_check`, `foreign_key_check`, relevant normalized constraints, and expected source migration ledger.
4. Mapping source and canonical course/topic identities; normalized versus compatibility projection *identity parity*, revision/freshness evidence or a truthful `UNVERIFIABLE` result.
5. Existing writers/transactions/rollback behavior for session start and question snapshots; legacy/current schema compatibility and no collision with parallel Tutor branches' migrations.

When confirmed, design and implement the **minimum prospective additive migration** and new-session transaction snapshot if evidence justifies it:
- Nullable reviewed mapping attribution: exact mapping ID/state, mapping confidence with calibration/provenance, method, reviewer authority/time, review_required, source version and immutable mapping snapshot link.
- Explicit reviewed independence declaration reference/status (`unknown | declared_independent | assisted`), declaration/reviewer authority, scope, timing and known helper exposure, with immutable history/corrections; `declared_independent` means *attested*, not objectively proved unaided.
- Capture the reviewed input at the real assessment session/question start boundary in one transaction. Handle null/unreviewed/ambiguous mappings as unknown rather than rejecting otherwise valid assessments, subject to existing runner policy.
- No historical automatic trusted backfill, no default `1.0` confidence, no exam-mode independence inference, no hidden Coding Helper memory/progress writes.
- Keep established migration SQL files and application score semantics unchanged. Choose an unused migration filename only after verifying exact lineage and colliding branches; no production migration application.
- Test new schema only on disposable copies/fixtures, rollback, interrupted writes, retry/idempotency, unique constraints, cascade/link ownership, promoted/legacy compatibility, concurrent writes, case and Unicode topic identity, and exact scorer/report parity.
- Any read-only production snapshot adapter remains explicitly separated from live runtime reads. B1 immutable source reader is never promoted to a live WAL reader.

If a real-authority prerequisite fails or is missing, **DO NOT implement B3-B or assign a migration number.** Document the exact blocker, run and publish the B3-A feature results, and provide a concise conditional B3-B patch plan ready for the next conversation. No approval of a migration can be inferred from this prompt.

## 5. Exact evidence eligibility constraints to preserve (future Gate C depends on these)

These are design/contract fixtures, **not authorization to implement Gate C**:
- Mapping: explicit confirmed/reviewed and reliable confidence >=0.90, review_required=false, identifiable origin. Score of a mutable `question_topic_mappings` row is not automatically calibrated review confidence.
- Grading: confirmed deterministic/teacher/human accepted, explicitly low numeric confidence <0.75 excluded; null confirmed human confidence is not fabricated as 1.0. AI provisional subjective grades excluded.
- Independence: reviewer-confirmed declaration with no known assistance conflict, scoped to the exact attempt; unknown/assisted historical work excluded from independent automatic decisions.
- Evidence identity: one evaluation is one observation; attempt/mistake records are bridges; duplicate imported questions/retries do not provide independent new question identities.
- Assessments/marks/explicit reports keep their current signed milli-mark rules; self-grading is a supporting signal only.
- Real-time task proposals, recovery eligibility and threshold heuristics remain owned by later Gate C/E. No new computed mastery on B3 ingestion.

## 6. Manual Windows verification — minimize, don't fictionalize

The user wants as little manual Windows verification as possible. **Hosted Windows CI is the default development validation.** Never demand manual installation/setup of a new test environment or dozens of screenshots. Do not ask for a database, vault, secrets, source archive or complete local directory listing.

If B3-B is blocked solely by installed authority and cannot be inferred from available evidence:
- Produce a self-contained, tested **single-command** PowerShell invocation using the **already installed** ANVAYA checkout/interpreter. Do not hardcode a username/path; instruct the user to run it from their existing ANVAYA repo root, which is currently on `main` after the B1/B2 merge.
- Default invocation can collect runtime identity without stopping ANVAYA or accessing the DB. Explain clearly that this identity-only step does not clear schema/projection parity.
- For the genuinely required schema phase, arrange a separate optional command that the user runs only after voluntarily stopping ANVAYA **and all other writers**, after backing up safely. It must use a stable copied DB+sidecars and return only redacted JSON, with explicit user attestation and guards. No automatic process killing.
- Prefer one short, privacy-safe report review and one optional user smoke test *at release time*, not repeating the same checklist on every feature iteration.
- Until that evidence is supplied, perform all source-only B3-A work autonomously and leave `B3_B_PRODUCTION_LINEAGE=BLOCKED`. Do not spend the rest of the conversation waiting.

## 7. Safety, version control and delivery

- Use a feature branch from the current verified `main`; preserve all B1/B2 commits/behavior and current application routes.
- No merge into `main`, no deployment, no production DB schema changes/migrations, no changing academic evidence, no auto-generated recovery/planner tasks.
- No unrelated Tutor 2.0, Learning Studio, Library, Coding Helper 2.0, Notes or Assessment UX changes. Existing pause/resume and paper-subjective specs remain deferred.
- Keep server-side course scoping, student data privacy, protected-file hash evidence and existing route/assessment contracts.
- Prefer real implementation over new broad diagrams. Only write the docs needed to make verified code and future work operable.
- If a new feature branch already exists, inspect its HEAD, test evidence and cleanliness; resume rather than repeat.
- Never push an untested/failed feature tip. Use a fresh isolated worktree and original current main as merge base; run independent delta review. After local green code, commit and push the feature branch only; then verify hosted Ubuntu/Windows CI at that exact commit. If CI fails, inspect logs and repair with another reviewed/tested commit. Do not declare success before hosted acceptance.
- Save the authoritative report and next-phase prompt as tracked Markdown in the feature branch, plus reusable source/test/CI artifacts. Provide an accessible evidence ZIP as a convenience, **not** as the only recovery source. Ensure GitHub remains sufficient when Work credits expire or the ZIP disappears.

### Required GitHub-tracked files / output artifacts

Adapt exact filenames to repository convention if existing versions already exist, but deliver equivalent content:
1. `ANVAYA_B3_AUTHORITY_AND_PROVENANCE_IMPLEMENTATION_REPORT.md` — code paths, ownership map, implemented versus blocked, exact SHA.
2. `ANVAYA_B3_AUTOMATED_VALIDATION_REPORT.md` — all test counts/failure IDs/skips, both OS runs with links, exact source hashes, safety proof, independent review and detected limitations.
3. `ANVAYA_B3_AUTHORITY_CONTRACT.md` — typed trust/projection/lineage contract, unknown semantics, B3-B conditional migration/writer plan.
4. `ANVAYA_B3_MINIMAL_WINDOWS_HANDOFF.md` — one-command redacted identity collection, optional closed-schema step with privacy/safety cautions and no routine manual browser checks.
5. `ANVAYA_NEXT_GATE_C_READINESS.md` — explicit prerequisites for pure recovery-policy Gate C; do not claim C unlocked if B3 evidence is incomplete.
6. Source modules, exact regression tests, CI workflow updates as actually implemented.
7. `ANVAYA_B3_FINAL_EVIDENCE.zip` with manifests, relevant logs/JUnit, screenshots, security checks and SHA-256 integrity listing; publish an actual accessible artifact, not just a filename.

### Final report format (mandatory)

Report:
- Starting `main` SHA, feature branch, final tested pushed SHA, worktree status.
- **B3-A DEV SOURCE-ONLY:** PASS / FAIL / BLOCKED, with concrete implemented features and exact tests.
- **B3-B ATTRIBUTION WRITER/SCHEMA:** PASS / FAIL / BLOCKED / NOT STARTED, with reasons.
- **LOCAL WINDOWS PRODUCTION AUTHORITY:** VERIFIED / BLOCKED (no synthetic substitution).
- **PRODUCTION DEPLOYMENT:** NOT AUTHORIZED.
- All CI links/conclusions, source-matched platform test totals and independent review fixes.
- Preservation of old user data and application behavior, including B1/B2, Assessment Studio, Coding Helper.
- The *one* remaining optional Windows step if needed, with no DB/vault upload.
- Recommendation whether feature can be reviewed for a future `main` merge **without** implying Gate C or release readiness.
- Exactly what the next Work/chat session should implement; don't repeat work already completed.

## 8. My priorities

I care more about correctness, educational integrity, and a reliable system than about rushing a green dashboard. I previously lost substantial time repeating Windows setup and test scenarios. Put those scenarios into reproducible synthetic and hosted cross-platform tests. A single truthful `BLOCKED` for real local authority is better than an unsafe migration or another round of manual screenshots.

**Execute the maximum independently safe B3 implementation now; don't stop at a plan. Do not merge or touch production academic data.**
