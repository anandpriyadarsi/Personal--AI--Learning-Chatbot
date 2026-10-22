# ANVAYA — Architecture V2.4 Next Development Master Work Prompt
**Date:** 21 October 2026  
**Repository:** `anandpriyadarsi/Personal--AI--Learning-Chatbot`  
**Verified starting point:** GitHub `main` at `bf3ca0e7eb1bf6f51d900ab4a6cc69ca83a61eae` (Architecture V2.3 merge, PR #31). Re-fetch `main` at execution time; the actual latest main is authoritative.  
**Suggested branch:** `feature/architecture-v2-4-learning-intelligence-2026-10`  
**Work type:** Real implementation, end-to-end integration, automated verification, visual evidence, independent review and PR handoff—not an audit-only task.

## Primary instruction and priority

Continue development of **ANVAYA Personal AI Learning Intelligence** from the latest verified GitHub `main` and deliver the **next architecture release, Architecture V2.4: Integrated Academic Learning Intelligence**.

**Make V2.4 the main work.** Allocate the great majority of development effort to new, demonstrable architecture capabilities and an improved student learning workflow. Architecture V2.3 has already been merged: do **not** restart V2.3, repeat old architecture audits as the primary deliverable, reopen merged PR #31, or spend the whole session on the four original IKS pilot tests. Perform only the focused V2.3 baseline checks necessary to avoid regressions. Proactively implement all independently safe V2.4 work possible within this session. Where the complete target cannot be finished, ship tested coherent increments with exact blockers and next steps rather than stopping at a plan.

### Baseline facts to verify, not blindly assume

- PR #31 merged Architecture V2.3 into `main`, introducing source-linked `anvaya.academic-evidence.v1`, an academic evidence workspace, an explicit idempotent study-task intent, versioned offline Tutor handoff, and a synthetic UC100N source → practice → evidence → task → Planning → completion workflow.
- V2.3 deliberately **does not** certify real-course source fidelity, installed Windows/B3/WAL production authority, real external IKS sources, automatic Tutor consumption, or independent mastery. Those are separate, explicitly limited capabilities—not silent successes.
- Public Ubuntu/Windows acceptance permits only the **four exact original private IKS cases** to be recorded as skipped or passed while preserving strict failure, missing-identity, duplicate and unexpected-skip checks. The private source-certification workflow still requires genuine original ZIPs and all four tests to pass. Never delete or fake these tests.
- Library & Resources V2, UI V2, Learning Studio, Assessment Studio, Planning & Analysis V2.1, Topic Intelligence, Coding Helper 2.0, Tutor, Obsidian integration and historical academic records must remain working.

## Desired outcome: one complete student learning loop

A first-year NITK CSE student should be able to:

1. Open a course/module and read **well-designed, structured, source-grounded learning material**, rather than dumped PDF/PPT text. Definitions, examples, equations, tables, diagrams and section hierarchy should be clear, responsive and linked to exact source pages/slides.
2. Check understanding through a low-stakes practice question or eligible Assessment Studio result; see **why an answer was wrong** using a precise, reviewable source reference, not a guessed topic or fabricated explanation.
3. Consult an explicitly grounded Tutor explanation with a learning ladder (hint → concept → example → self-check), showing what evidence is known, unknown, or not verified. The Tutor must not invent a course grade or a verified mastery level.
4. Review genuine study evidence and choose an actionable next study step; see the source, reason, uncertainty and exact course/topic link before committing anything.
5. Explicitly create a canonical task, choose an **actually available** study window, preview and separately approve a plan, then record real effort or mark the task done.
6. Return to the original topic and see a coherent, timestamped progress view that distinguishes **practice, self-evaluation, formal assessment, time spent and independent recheck** without misrepresenting any of them.

Implement and browser-test this coherent journey using **synthetic, disposable academic records** first. Do not require private IKS fixtures or mutate the student's installed data to demonstrate it.

## Architecture V2.4 development workstreams (ordered)

### P0 — Authority boundaries, event provenance and consistent topic identity

**Implement, not just describe:**

- Trace the current canonical owners, schemas and exact source/event identities for Learning Studio, Assessment Studio, Topic Intelligence, Planning, and Tutor. Establish one *versioned, stable cross-feature topic reference* or well-tested adapter where authoritative identities differ. Do not create another unowned master database or silently remap a topic by display name.
- Build on V2.3's read-only evidence projection. Add reliable event provenance for question attempts, assessed work, revision/recheck, Tutor assistance level and planned-versus-actual study effort. Attribute every derived field to its specific owner and source; show `unknown`, `unverified`, `unavailable` or `stale` when appropriate. Preserve distinct clocks, exact identifiers, and as-of semantics.
- Guard against stale source revisions, changed module hashes, duplicated retries, missing marks, invalid time order, cross-course leakage, deleted or superseded content, inconsistent transaction snapshots and non-atomic two-owner reads.
- Do not silently redefine grades, count self-awarded subjective marks as official, or mark a topic independently mastered because a user read a lesson, repeatedly practised, asked the Tutor for help, completed a task or studied for 35 minutes.
- Keep all writes in their canonical owner APIs with explicit consent, idempotent receipts, course/topic validation and rollback-sensible transactions. New migrations require detailed design, backup/restore proof, compatibility tests and explicit owner authority; otherwise stay read-only.

**Acceptance:** stable source identity and freshness tests; cross-owner mapping, replay and idempotency tests; tampered/stale provenance tests; no live DB checkpoint or unauthorized WAL mutation.

### P1 — Learning Studio V2.4: source-grounded interactive learning experience

This is a **high-priority product and architecture deliverable**, not a cosmetic reskin.

- Significantly improve the lesson/learn page. Replace the impression of extracted text pasted into a page with a structured reading experience: readable typography, semantic headings, lecture outline, callouts, rendered equations, usable tables, figures with captions, highlighted definitions, worked examples, concept checkpoints, concise revision summaries and source citations.
- Ground every displayed academic assertion and figure in actual available authored content. Do not synthesize "facts from source" without a source link and a clearly identified transformation method. Mark ambiguous OCR/extraction, missing figures, incomplete slides, unsupported math and other uncertainties as requiring review.
- Provide precise page/slide links, page-order fidelity, diagram/image ownership and accessible fallback to the original document. Never replace or corrupt original Learning Studio files.
- Define a **review-first content ingestion/conversion architecture** for PPT/PPTX/PDF notes: parse in isolation, produce a structured draft manifest, show source-to-output mapping and confidence/uncertainty, allow explicit human review and approval before publication. Implement an independently safe vertical slice using synthetic or approved nonprivate examples. No silent bulk import, no automatic actual IKS course import, and no background conversion of private records.
- Add lightweight self-check/revision navigation that genuinely connects a selected lesson, a related practice question, source-evidence page, and next action. Preserve existing course templates (including CY100N Chemistry with Green Chemistry/Spectroscopy/Lab and UC100N Introduction to Data Science), module IDs and previously completed activities.
- Design must be dark-theme consistent, mobile-responsive at 390/768/1366 px, accessible by keyboard, and resilient to missing assets, long formulas and no-JavaScript essentials.

**Acceptance:** real Playwright screenshots of actual Flask/Jinja screens, before/after comparison, fidelity/source-map tests, no horizontal overflow, working navigation, independent original-file access, zero lost course records.

### P1 — Tutor-grounded assistance connected to academic evidence

- Build a **safe, explicitly invoked Tutor consumer** for V2.3's versioned offline handoff if the present owner architecture and policy permit it. First inspect the existing Tutor and Coding Helper assistance ladders, provider interfaces and session ownership. Do not bypass their permissions.
- A Tutor response should know what exact section, source page and student-visible mistake it is discussing; ask or use an appropriate hint before providing a complete answer where learning goals require it.
- Show source references and distinguish authored material, derived explanations, generated suggestions and missing context. If no provider is configured, supply a deterministic offline fallback/preview rather than fake an AI response.
- Store only approved, minimal, versioned learning-session metadata with the canonical owner and correct assistance attribution. No automatic provider calls, no hidden session creation and no silent study-plan writes.
- Include tests for prompt-injection within uploaded notes, cross-course citation contamination, wrong-question association, private source exposure, history bounds and graceful missing-provider behavior.

**Acceptance:** exact source → mistake → consented Tutor help → student self-check handoff, with assistance level and unknowns clearly visible.

### P1 — Assessment + Topic Intelligence + Planning closed loop

- Connect valid Assessment Studio results, step-based subjective self-evaluation, low-stakes practice and genuine revision/recheck signals to a coherent **topic-level evidence view** without conflating their authority. A paper-based rubric is *student-entered evidence*, not an official mark unless independently authenticated.
- Preserve Assessment Studio's **question-palette pause/resume** semantics: one pause control in the palette, saved answers, stopped timer, and Resume Test from the Assessment page at the last question. Include regression tests. Never change grading or timer persistence merely to fit the new UI.
- Surface incorrect questions, underlying concepts and reasons for suggesting study actions. Any topic-status calculation must have explicit policy/version, inputs, counterexamples and caveats; do not invent "mastery %" from insufficient evidence.
- Strengthen Planning & Analysis integration: true availability, no guessed free slots, separate preview/draft/approval, realistic effort estimates marked estimates, explicit actual-duration tracking, retry-safe task creation, timezone/clock validation and visible change after completion.
- Make the Home/Analysis/Topic views consistent with the new source-evidence view and link back to the exact original problem or lesson. Continue to preserve existing UI V2 and Library V2 routes/navigation.

**Acceptance:** complete source → answer → evidence → next action → available window → approved plan → actual effort → updated analysis end-to-end browser flow; tests for empty timetable, overlapping bookings, cancelled drafts, retries, stale source, incomplete/subjective marks and missing events.

### P2 — Library, Knowledge and search integration

Only after P0/P1 have a genuinely tested slice:

- Expose appropriate source-backed lesson/evidence links through the existing Library V2 and Knowledge search rather than introducing a parallel vault or search index.
- Preserve read-only Obsidian and private-file safety boundaries. Improve discoverability, empty/loading/error presentation, pagination and search relevance without weakening original-file authorization.
- Add architectural documentation for later content lifecycle, re-import, side-by-side revision comparison and provenance-preserving course migration; implement only if independently safe and tested.

## Engineering and execution rules

1. **Verify current GitHub:** inspect latest `main`, the V2.3 merge commit and currently open PRs. Use a new dedicated V2.4 branch from verified main; never overwrite, force-push or cherry-pick over active unrelated branches. Do not reopen PR #31.
2. **Small implementation increments:** identify a concrete first vertical slice, modify production code and tests, run tests immediately and push tested commits. Continue to the next slice rather than stopping at analysis. Prefer well-scoped adapters over speculative framework rewrites.
3. **Data preservation is nonnegotiable:** no deletion of academic records, Assessment attempts, Learning modules, original source files, Obsidian vault data, Library artifacts or configuration. No unapproved installed SQLite migrations, WAL checkpoints, DB replacements, or destructive reset. Use disposable fixtures and backups for permitted migration tests.
4. **IKS tests:** retain all four unchanged genuine external pilot acceptance identities. Public CI must still disclose their missing private inputs as `BLOCKED`/exact permitted skip, not PASS. Keep private certification optional and isolated; do not invent ZIPs, weaken hashes, exclude other tests, alter score criteria, or let IKS fixtures consume the V2.4 build effort. If real files become legitimately available, validate them securely with the original guards and without publishing their contents.
5. **Testing:** run real Linux and Windows CI, focused owner/integration unit tests, full-suite regression, Node/compile checks, Chromium Playwright at 390/768/1366, including error/retry/keyboard paths. Distinguish local Linux simulation from a genuine Windows runner. Report exact commit SHA, commands, pass/fail/skip counts, failed tests and artifact URLs. Fix flaky timing by testing the actual lifecycle; do not replace substantive assertions with waits or skips.
6. **Independent reviews:** conduct one engineering/data-safety review, one academic correctness/provenance review, and one frontend/accessibility review. Record findings and fixes, including failure-mode walkthroughs.
7. **Visual evidence:** capture actual before/after browser screenshots for Learning Studio lesson, evidence detail, Tutor/help state, Assessment and Planning/Analysis; include mobile and desktop. Do not substitute mockups or generated screenshots for real app validation.
8. **Operational integrity:** preserve existing launch routes, course names/codes and `python phase7_web.py` startup. Maintain feature flags and explicit user-consent boundaries. If a migration is considered, document upgrade, rollback, owner approval and verified restore before touching any real data.
9. **GitHub delivery:** push the V2.4 branch and open a clearly described PR with commit-linked tests, screenshots and evidence. **Do not automatically merge V2.4 into `main` or deploy**; request my separate authorization after all exact-head mandatory tests pass. V2.3 is already merged, so no further V2.3 merge is needed.

## Prioritization when time or resources are limited

**The P0/P1 new architecture vertical slice takes precedence over exhaustive unrelated cleanup.** A useful minimum independently complete V2.4 increment is:

- A source-grounded, formatted Learning Studio lesson and trustworthy source mapping;
- a real practice/Assessment mistake linked into a provenance-safe topic evidence view;
- an explicitly consented Tutor explanation or deterministic bounded offline handoff;
- a one-click reviewed next study action that writes through the canonical task owner;
- a genuinely available approved schedule and recorded effort;
- a correctly updated Analysis/Topic view;
- browser proof of all of the above on disposable data.

Once that slice is green, extend it. Do not spend most effort re-reporting old V2.3 blockers or building unintegrated V2.4 UI mockups.

## Required final deliverables

1. **Actual GitHub V2.4 branch and PR**, with an accurate change summary and stable commit SHA.
2. **Architecture V2.4 documentation:** owner boundary diagram, versioned identity and evidence contracts, source provenance/freshness semantics, privacy/data model, explicit-consent writes and rollback.
3. **Implemented production changes** by workstream, with links to meaningful code changes, not only proposals.
4. **Working end-to-end academic journey** tested in Flask/Jinja with disposable real data stores, Chromium screenshots and concrete expected-vs-observed results.
5. **Exact Ubuntu, Windows and browser test evidence** on the PR's final SHA; disclose skips, blocked private certification and environment limitations correctly.
6. **Independent engineering, academic and UX review results**, resolved defects and remaining risk register.
7. **A precise V2.5 handoff** identifying genuinely unfinished capabilities, prerequisites, owners and next tests, rather than relabelling incomplete V2.4 work as done.

**Completion rule:** Call a capability COMPLETE only when implemented, source-linked where relevant, passing its applicable genuine tests, accessible in the real app and supported by evidence. Keep blocked installed/private authority distinct from independently successful public V2.4 development. Prioritize delivering the next functioning architecture over repeating analysis of the already merged V2.3.
