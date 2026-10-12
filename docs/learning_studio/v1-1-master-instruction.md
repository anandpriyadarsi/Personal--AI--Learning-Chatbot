# ANVAYA LEARNING STUDIO — V1.1 NEXT-WORK MASTER PROMPT

## Mission: RECOVER THE REAL PILOT → COMPLETE AUTOMATED VALIDATION → FIX REMAINING V1 UX → SAFE EVIDENCE HANDOFF → COMMIT/PUSH/HANDOFF

You are continuing a **partially completed and already pushed** implementation of ANVAYA Learning Studio. **This is an implementation conversation, not another architecture-only audit.** Inspect the actual code and recent CI first, then repair and implement the remaining authorized work. Finish independently safe slices even when a separate external semantic/canonical-mapping/Tutor gate remains blocked. Do not merge to `main`.

**Nonnegotiable product goal:** A student studying roughly six subjects, with 10–12 PPT/PDF lectures per subject, can navigate a compact course → unit/topic → lecture library; read exhaustive source-linked interactive notes with a collapsible sidebar and true full-width Focus Reading; revise one day before an exam; answer questions; and retain an immutable record of misconceptions and retries. The original lecture source remains authoritative and fully accessible. Low-stakes evidence must never masquerade as official marks, mastery or verified Tutor knowledge.

### Primary inputs — inspect all, use repository state as final authority

1. GitHub: `anandpriyadarsi/Personal--AI--Learning-Chatbot`.
2. **Uploaded Work documents:** `ANVAYA_LEARNING_STUDIO_V1_IMPLEMENTATION_REPORT.md`, `ANVAYA_LEARNING_STUDIO_WINDOWS_HANDOFF.md`.
3. **External audit:** `ANVAYA_LEARNING_STUDIO_V1_AUDIT_AND_RECOVERY.md`.
4. **Pilot:** `ANVAYA_Interactive_Learning_Pilot_v3_Source_Reconciled_Candidate.zip`, and optionally original `Hinduism_Buddhism_Jainism_Comparison (3) (1).pdf` and old `ANVAYA_Interactive_Learning_Pilot_Complete_v3.zip`, if provided. Do not silently swap data when those inputs disagree.
5. **Existing repository contracts and verification:**
   - `ANVAYA_LEARNING_STUDIO_IMPORT_SCHEMA.md` and `docs/learning_studio/learning-module-v1.schema.json`
   - `ANVAYA_LEARNING_STUDIO_EVIDENCE_CONTRACT.md`
   - `ANVAYA_LEARNING_STUDIO_FUTURE_AUTOMATION.md`
   - `docs/learning_studio/review.md`
   - `docs/learning_studio/validation/regression-delta.json` and real logs
   - `docs/superpowers/plans/2026-10-11-learning-studio.md`
   - `.github/workflows/learning-studio.yml`
   - Entire `personal_learning_assistant/learning_studio/` and `tests/learning_studio/` code
   - Existing Flask web routes/templates/sidebar/Notes/Obsidian/Knowledge/Analysis boundaries.

### Known historical state — VERIFY, DO NOT ASSUME IT IS STILL CURRENT

- Main at last external read: `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`.
- Existing pushed branch: `feature/learning-studio-v1`, last observed remote HEAD `9ed585ca8e1fbcfb6f5a7e0426d030560109115e` (report/evidence updates). Its core validated implementation commit: `132444dd6e62f5845c871f57f3d3ed17a967bc48`.
- V1 Work report states **55 feature tests passed**, **101 focused regressions passed**, whole baseline **1716 passed/16 failed**, whole feature **1771 passed/the identical 16 failed**. These are reported outcomes; repeat or verify them on the current tree. Whole suite is still **RED** even though regression delta was green.
- GitHub Actions run [38233007085](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38233007085) on implementation SHA had **Ubuntu success and Windows still in progress** at last independent read. Obtain the final current status and do not infer Windows success. A previous run had NumPy and cross-platform ZIP-path issues; those patches are already committed. Do not redo them unless regressions demonstrate a problem.
- Already working in V1: real ANVAYA logo, reused global nav/Focus Reading, `/learning` library, 6×12 synthetic course organization, seven reader views, versioned stage/publish, server-graded append-only questions, `/learning/analysis`, versioned evidence export and safe disabled Tutor handoff.
- Remaining documented minors: a module mapped to a later-deleted course can become undiscoverable via cards; Focus Reading state is lost during internal view navigation; “Review related lesson” opens at the start instead of its precise lesson/question/source anchor.
- **Actual 20-page Hinduism/Buddhism/Jainism pilot was NOT successfully imported in V1.** Source hash blocked strict conversion. Tutor did NOT consume mistakes.

## A. Hard safety / isolation gates — never trade these for speed

1. **DO NOT** merge to `main`, force push, reset/switch a dirty Tutor/planning/architecture worktree, rewrite old V1 commits or delete historical revisions. Use a fresh isolated worktree/checkout. Continue **from the pushed V1 head**, not from an unrelated or stale main checkout.
2. Suggested new branch `feature/learning-studio-v1-1` **from current** `feature/learning-studio-v1` remote HEAD. If it already exists, audit its ancestry, dirty state and ongoing ownership; resume rather than overwrite. Preserve old V1 branch. Commit/push only this new branch. Record exact SHAs.
3. Never modify the real academic SQLite database, official assessment questions/attempts/grades, course registration, Notes JSON/assets, Obsidian vault, Tutor memory/conversations, Knowledge registry, original PDFs/PPTXs, Moodle accounts/files, retrieval indexes, API secrets or another live worktree. All tests and demo imports must use **temporary synthetic or explicitly isolated** SQLite/source directories. Read-only production queries are permitted only when needed and safe, never as a test prerequisite.
4. Preserve existing authority separation: Knowledge/Resource owns original source identity, independent Notes ≠ Obsidian, Learning Studio holds immutable derived artifacts in its isolated feature DB; no client-side authoritative grading. Do not create a second official assessment/mastery store.
5. **No fabricated semantic certainty.** Source-byte hash/page validation is distinct from correctness of a lecture's philosophical/historical claims, visual interpretation or authored teaching text. Keep `needs_review` for the real pilot until a proper semantic review. Present source assertions separately from the system's pedagogical explanations.
6. Never accept malicious HTML/scripts, unsafe links, path traversal/symlinks, ZIP bombs, arbitrary asset paths, tampered grade flags, forged source hashes, unauthorized cross-module assets, or uncontrolled read/write side effects. Preserve strict validation, CSRF/origin checks, immutable revision checks and local-only operation.
7. Preserve Tutor 2.0/2.3, its prompts/reasoning/scenario state and unrelated planning work. If an integration requires modifying that subsystem, **do not make that change under V1.1**; record a bounded integration handoff and complete other safe slices.
8. Do not change tests to skip failures, weaken assertions or make the full suite falsely green. Always distinguish actual green CI, green regression-delta, and overall RED suite.
9. Do not ask for repeated design approvals. Choose safe details independently. If a semantic judgment or actual canonical course mapping needs the user, list **only those genuinely unautomatable items** at the end; never stall independent code/tests on them.

## B. Stage 0 — 10–20 minute factual verification, then IMMEDIATELY EXECUTE

In an isolated checkout, gather evidence:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git worktree list
git remote -v
git fetch origin --prune
git rev-parse origin/main
git rev-parse origin/feature/learning-studio-v1
git log --oneline --decorate -12 origin/feature/learning-studio-v1
```

Inspect the exact V1 code and current CI run(s), including **Ubuntu + Windows job conclusions, failed steps, workflow SHA, workflow artifacts and timestamps**. Review committed package schema, original 16 baseline failures, branch overlap and GitHub Actions permissions. Do not just reread the original broad architecture plan. Produce a compact baseline table and a strictly ordered list of remaining tasks, then start coding.

Create V1.1 branch off the verified V1 tip. If V1 CI is still running, proceed with safe local work; do not claim it passed and do not cancel/re-run a potentially healthy user-owned run needlessly. The V1.1 CI must validate its own exact pushed SHA.

## C. Priority 1 — Recover the 20-page *real* pilot without changing trust rules

The independent review identified a concrete source recovery opportunity:

- Package JSON and fidelity report expect PDF SHA-256:
  `75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411`.
- The earlier **actual user-uploaded original PDF** and V1/V2 archive source have **exactly that byte hash**.
- The original V3 ZIP's enclosed PDF has SHA-256:
  `f812fb27240fc5cd5265a1608f80ac480f241b56f9b27d4826bb6453b319735b`.
- Independent comparison found all **20/20 pages with matching extracted text and identical RGB rendered pixels at 960×540**. That visual comparison alone does NOT overrule the byte-integrity gate.
- A new **candidate ZIP** was prepared by replacing only the V3 member `ORIGINAL_20_Page_Presentation.pdf` with the original byte-for-byte uploaded PDF. Nothing else in the archive was modified; **no manifest hashes were edited**.
- Candidate archive SHA-256:
  `e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923`.
- Its 20 lesson source-text hashes, 20 preview image hashes, and 31 MCQ source SHA/page references passed an independent integrity check. **The candidate has NOT yet been run through ANVAYA's real strict converter.**

Required real recovery workflow:

1. Inspect candidate and old V3 as untrusted ZIP content. Verify its own hash, stored source hash, archive safety, 20 page identities, preview ownership, text references, 31 questions, revisions and every source locator. Preserve immutable source/manifests and uncertainty flags. If artifacts unavailable, use another user-approved matching original already present; never fabricate the hash.
2. Execute `personal_learning_assistant.learning_studio.pilot.convert_pilot` **as actually implemented**, not a copied substitute, using the candidate. Fail closed on any new mismatch; report exact reason. Preserve existing negative test demonstrating original *bad V3* rejection.
3. **Fix test design:** `tests/learning_studio/test_pilot.py` currently treats `ANVAYA_TEST_PILOT_ZIP` as necessarily broken and asserts hash rejection. Do not change that test into an unconditional pass or remove the negative case. Separate tests for **bad original V3 (rejected)** and **corrected candidate (accepted)**, with explicit fixture/env variable names and full source/page/question assertions. Never allow a missing external pilot to create a deceptive passing “real pilot” check. CI can run built-in synthetic acceptance while the real pilot test runs with explicitly attached candidate data, without committing third-party lecture content to GitHub by default.
4. Register the candidate's PDF in a disposable **synthetic Knowledge registry + logical source root** with the correctly computed SHA. Run the real `LearningStudioService.stage`/`publish` lifecycle and its Flask reader in a temporary directory. This is **not** registration in the student's academic database and does **not** imply approved mapping to UC103N. Keep mapping null/“needs review” absent canonical evidence.
5. Verify end-to-end: exact PDF bytes served; 20 readable original page identities and their 20 owned previews; source-versus-extra-teaching distinction; all 20 lessons, full revision, 31 MCQs, per-question page links; wrong → correct → reload → weak history still retained, exported evidence is server-derived; historical revisions stay accessible. Check no missing images, escaping, console exceptions or oversized mobile headings.
6. Capture deterministic JUnit, JSON assertions and Playwright screenshots as evidence. If the candidate fails a deeper semantic/reference validator, **do not relax the validator**. Repair only demonstrably erroneous packaging/adapter logic with a fail-first regression, or mark real-pilot acceptance blocked and continue the remaining work.
7. Do NOT copy a third-party lecture PDF into source control or persist it in an unrelated production directory. Any temporary recovered package is a local validation input or handoff artifact only; no auto-publish into the student's real course.

**Acceptance:** A strict, real, 20-page/31-question pilot conversion and disposable reader is demonstrated, with both the original damaged V3 negative case and corrected candidate positive case verified. A real source-hash match is required; semantic content still says needs review.

## D. Priority 2 — Close documented UI/organization gaps without redesigning V1

Reuse `personal_learning_assistant/ui/web/templates/base.html`, existing global navigation JS/CSS, real logo assets and the existing Learning Studio blueprint. **Do not add a second top-level navbar.** Fix the following three documented issues with source-focused tests before modifying UI:

1. **Deleted/removed course discovery:** an immutable historical module whose formerly reviewed course is no longer in the live catalogue must remain discoverable in a visible “Course unavailable / needs review” bucket, not silently disappear from all cards. Do not silently attach it to a different course or mutate its historical mapping. Handle renamed topics, missing optional academic year/semester and unmapped source identity gracefully.
2. **Focus state during navigation:** while reading Learn/Visualise/Practice/Revision/Weak/Source, toggling internal view or Contents should preserve the user's chosen Focus Reading state until explicitly exited. The reading column must actually expand and topbar/sidebar must truly disappear. Use a safe session or bounded client storage preference; if browser storage is disabled, degrade gracefully without unsafe backend writes. Do not create history bugs or trap keyboard focus. Exit Focus restores the previous standard layout.
3. **Precise related-lesson navigation:** a missed question's “Review related lesson” should lead to its actual lesson section and source page (and question identity where appropriate), rather than always opening Learn at the beginning. Stable anchors must survive revision changes; link to the **original attempted module/question/source revision** where needed, not the latest replacement by accident.

Keep compact `academic year → semester → course → unit/topic → lecture` navigation without inventing metadata the catalogue lacks. At 6 courses × 12 lectures, no landing-page explosion, duplicate card authority, slow full-body parsing or unbounded query patterns. Make imported images/tables/long titles work in dark mode, full width and narrow widths. “Day-before-exam Revision” remains an additional printable knowledge mode, not a destructive summary of the full source.

Browser tests, using **real Chromium via Playwright**, must cover view switching while focused; restored sidebar width >150 px difference on wide desktop; source anchors and weak-question links; deleted course visibility; 390 px mobile no overflow; keyboard/ARIA/Escape/Contents; print-only revision and original-source access; logo dimensions and no placeholder badge. Use additional widths 360, 768, 1024, 1366 and 1920 where cheap. Screenshot evidence must be real browser output, not invented UI mockups.

## E. Priority 3 — Verify evidence durability and keep Tutor integration honest

Do not replace the already working `LearningEvidenceSummary V1` system. Audit and extend **tests before features** for:

- Immutable per-module, per-question and per-source revision identity.
- Idempotent retry/event IDs, same event/different payload conflict, concurrent duplicate posts.
- Wrong → correct retains original mistake; wrong again increases proper history; “recovered, needs recheck” is not a mastery score.
- Source-mismatched, missing or unmapped topic refuses false attribution.
- Public module views do not disclose hidden answer keys before submit.
- Read-only `/learning/evidence`, `/learning/analysis`, `/analysis` link and exports; no side-effect on official Assessment scores, grades, study plans, Note bodies or Tutor memory.
- Outdated question revisions grade against their own immutable original answer key, not the latest revision.
- Explicit small-sample/limited-evidence and empty-state behavior.

The current Tutor entry point is course-code oriented, and the V1 contract **explicitly states it cannot consume versioned LearningEvidenceSummary**. The student's long-term intention is that Tutor/Analysis understands weak concepts. V1.1 must maintain truthful boundaries:

- Keep Analysis grounded, read-only and correctly labelled as *low-stakes practice evidence*.
- Build and test a compact **review-context handoff document / export or “Copy review brief”** from real server-derived evidence if it can be done wholly inside Learning Studio, with verified topic/source/page references, missed question IDs, timestamps and limited-evidence flags. Never include hidden correct answers before grading, raw secrets or cross-course private data. This can offer a useful immediate workaround without pretending the Tutor integration is automatic.
- Do **not** enable “Review with Tutor” as a working automatic consumer unless the exact Tutor source/version contract and scenario gates prove it. Do not modify Tutor 2.0/2.3 reasoning, prompts, orchestrator or test fixtures on this branch. If a safe external contract is unavailable, leave that action visibly disabled and provide a **small V1.2 read-only adapter specification + exact automated acceptance tests**.
- No LLM calls per question; no speculative diagnoses or official progress changes.

## F. Priority 4 — Make automated validation self-sufficient on Linux and Windows

This is the student's overriding operational request: **MINIMIZE MANUAL WINDOWS VERIFICATION**. Complete routine validation using headless browser and synthetic test data, not the student's machine.

### Required CI improvements

1. Ensure `.github/workflows/learning-studio.yml` triggers the new V1.1 branch (or a purpose-scoped replacement workflow); preserve V1 branch behavior. CI jobs on **ubuntu-latest and windows-latest**, pinned Python and dependencies, Python 3.12 where supported, installed Playwright Chromium, no external paid AI API.
2. Run entire `tests/learning_studio` including browser tests unskipped in CI, plus focused startup/web/course/Notes-vs-Obsidian/Analysis/Assessment regressions. Explicitly check failure/skip counts. Missing real-pilot external attachment may skip only the **separately named external-pilot fixture test**, never the built-in strict synthetic importer tests.
3. Exercise the real source integrity and intentionally mismatched ZIP cases on both OSes, including raw Windows backslash/drive/absolute ZIP paths, symlink cases, decompression bounds, checksum tampering, image type/pixel bounds and stale source at publish time. Preserve existing green regression coverage.
4. Run compile/import checks, `git diff --check`, SQLite `PRAGMA integrity_check` and `foreign_key_check`, read-only GET purity, and protected file/source/hash assertions on **temporary test fixtures**. Test that no app data directory/database is created during ordinary GET/startup.
5. Publish machine-readable pytest JUnit, regression summary JSON, screenshots and concise failure excerpts as GitHub Actions artifacts even on failed jobs. Do not expose secrets, confidential personal notes, academic data or large unnecessary PDFs in artifacts.
6. For the full suite, run on an **unchanged base checkout and exact feature checkout using the same pinned Python/dependencies/fixture strategy**, and report comparable failure node IDs and newly failing tests. Do not launder pre-existing raw failures into green. If full suite itself becomes truly green from a narrowly scoped *test-environment-only* fixture repair, show original baseline RED → corrected fail-first evidence and prove no tests/assertions were weakened.
7. The reported 16 legacy failures depend on unavailable production tutor data and `/agent` assumptions. Investigate quickly to distinguish missing synthetic fixtures from genuine product defects, but do not spend the full Work session chasing unrelated Tutor 2.0 scenario bugs. **Do not modify protected Tutor implementation/tests or fabricate production academic DB.** If the 16 cannot be resolved within test-only ownership safely, retain a clear blocked baseline list and complete independent green Learning Studio gates. A regression-delta PASS is different from a full-suite PASS.
8. Run the V1.1 workflow against the final **pushed** V1.1 SHA. Wait for both OS conclusions when possible; if one is pending or unavailable, explicitly mark that gate unverified and give the CI URL. Manual Windows screenshot/click approval is **not** a substitute for missing CI.

### Preferred deterministic commands (adjust only to actual code)

```bash
python -m pip install -r requirements-learning-studio.txt
python -m playwright install chromium
ANVAYA_BROWSER_TESTS=1 python -m pytest -q tests/learning_studio
python -m pytest -q tests/test_phase7_5_web_foundation.py tests/test_phase7_5_courses_topics.py tests/test_main_startup_isolation.py tests/test_phase7_5_15_10_notes_obsidian_separation.py tests/test_phase7_5_15_14_focus_companion_analysis.py
python scripts/learning_studio_regression_gate.py --output learning-studio-evidence/full-suite
python -m compileall -q personal_learning_assistant/learning_studio personal_learning_assistant/ui/web/learning_studio.py
git diff --check
```

**Windows PowerShell equivalent** uses `$env:ANVAYA_BROWSER_TESTS='1'` and `python -m pytest`; do not paste Bash `VAR=1 command` syntax directly into PowerShell. The next handoff should be short because CI does most verification. If all automated gates are green and only production authorisation/mapping remains, the user should need **zero manual layout/test actions**.

## G. Scope and delivery sequence — do not stop at analysis

Proceed in this order. Each safe slice gets fail-first regression, implementation, focused tests, review, then scoped commit. Do not wait for an unrelated unresolvable gate to complete a safe slice.

**Slice G1 — V1/CI fact check and evidence:** audit branch and workflow; preserve exact base and per-OS CI status; establish safe V1.1 branch.

**Slice G2 — real pilot recovery:** test bad old V3 negative, candidate positive, correct source registration inside disposable demo, staging and rendering 20/20 pages, all 31 questions and revision. Capture artifact and no-production-write assertions.

**Slice G3 — UI completion:** discoverable removed-course bucket; focus persistence across view/Contents navigation; exact lesson/weak/source anchors. Browser screenshot and accessibility regressions.

**Slice G4 — evidence and handoff:** read-only durable evidence tests; useful, source-grounded review-context export/copy if bounded; documented Tutor V1.2 adapter boundary without Tutor rewrites.

**Slice G5 — automated cross-platform gates:** green scoped test suite; Ubuntu/Windows CI on actual head; full baseline-vs-feature delta; DB/protected-data checks; independent code-review repair.

**Slice G6 — final documentation, commit and push:** update factual V1 reports and produce V1.1 report/CI evidence; push feature branch; verify exact remote HEAD equals tested HEAD; no merge.

Do NOT expand into full automatic PPT/AI conversion, Moodle scraping, arbitrary source ingestion, production data migration, Tutor 2.0 logic changes, automatic Official Assessment updates, or personal Notes sync in this phase. Those are future components with their own review gates.

## H. Tests that must be visible in the final acceptance matrix

For every criterion, report `PASS`, `PARTIAL`, `BLOCKED`, or `NOT RUN`, exact test or artifact reference and GitHub commit/CI SHA:

1. Recovered matching original source PDF, manifest and 20/20 page previews + 31/31 questions **through the real V1 importer**.
2. Old inconsistent V3 still rejected, without weakening hash policy.
3. Original file remains byte-preserved/readable; citation links locate correct pages and historical revisions.
4. Real logo/left nav/full-width Focus Reading and preservation across view navigation on desktop/mobile.
5. Compact 72-module synthetic organization and removed-course fallback, no fabricated academic mappings.
6. One-day-before-exam printable revision plus recall and weak-question flows.
7. Wrong→correct→reopen history, idempotency, old-question answer key isolation, tamper rejections.
8. Read-only Analysis/evidence/export, honest disabled Tutor integration or independently proven reviewed adapter; no official grade/mastery mutation.
9. Startup/GET writes nothing; synthetic DB integrity/FKs; no regressions in personal Notes, Obsidian, Knowledge, Assessment or Tutor.
10. Pinned automated Linux and Windows CI **for V1.1 final SHA**; accurate raw whole-suite and baseline delta results.
11. Protected original academic files, user's data, main/Tutor branches, secrets and source integrity untouched.
12. Independent diff review, green scoped gates, documented limits and branch push (not merge).

## I. Required files and final response

Update existing contracts when necessary and deliver:

- `ANVAYA_LEARNING_STUDIO_V1_1_RECOVERY_REPORT.md` — actual pilot integrity proof, bad-V3 negative and corrected positive results, exact hashes, page/reference checks, semantic-review limits.
- `ANVAYA_LEARNING_STUDIO_V1_1_IMPLEMENTATION_REPORT.md` — exact branch ancestry, scoped code changes, feature acceptance, tests, screenshots, known gaps.
- `ANVAYA_LEARNING_STUDIO_V1_1_AUTOMATED_VALIDATION.md` — per-OS CI matrix with run URLs, commands, JUnit counts, baseline vs feature failures and preserved source/database checks.
- `ANVAYA_LEARNING_STUDIO_TUTOR_READONLY_HANDOFF_V1_2.md` — narrowly scoped evidence consumer proposal and test contract if true Tutor integration remains unsafe, explicitly distinguish automatic from manual/clipboard handoff.
- Updated `ANVAYA_LEARNING_STUDIO_WINDOWS_HANDOFF.md` — only necessary local demo instructions, ideally zero manual visual-validation steps; disposable isolated fixtures and paths only.
- Source/test/CI changes, all under reviewed paths; new screenshots/evidence under `docs/learning_studio/validation/` or deterministic CI artifacts as repository policy permits.

The final answer **must** include: what was already complete (not re-implemented); what you changed; branch, base SHA, commits, pushed remote SHA; real vs synthetic import proof; exact failed/skipped test counts; **separate** Ubuntu and Windows CI conclusions and URLs; whether source semantic verification remains pending; whether Tutor consumes mistakes automatically (probably not yet); and a concise 5–10 minute Windows demo only if the user wishes to see the reader locally.

**Critical:** Do not declare success on the basis of synthetic reader tests if the real pilot still cannot import. Do not declare whole-suite green if its 16 baseline failures persist. Do not claim an automatic Tutor intelligence connection if only a JSON contract, disabled button or copyable brief exists. Do not claim remote code was pushed without remote SHA verification.

**START NOW**: inspect the actual `feature/learning-studio-v1` tip, old Work reports and new candidate archive, verify latest CI, create a safe V1.1 branch, then IMPLEMENT and TEST the real pilot-recovery slice before any new feature scope. Continue through independent safe slices, review, commit and push. Stop only at a genuinely blocked acceptance gate, with exact evidence and handoff. NO MERGE TO MAIN.
