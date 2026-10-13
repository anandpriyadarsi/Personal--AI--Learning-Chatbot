# ANVAYA Learning Studio V1.2 — Learning experience and content quality

## 0. Execution instruction and intended outcome

Continue the existing ANVAYA Learning Studio. This is an implementation task: inspect → implement → validate → independently review → commit → push → handoff. Do not finish after an audit, specification, mockup, or unexecuted test plan.

Anand is a first-year NITK CSE student. He receives roughly 10–12 lecture presentations per subject across about six subjects. He wants to learn actively from complete, trustworthy notes, revise efficiently before exams, and use mistakes to guide subsequent study. He values product quality more than speed and wants the agent to absorb setup, debugging, testing, and repetitive checking. Additional agent time is acceptable; repetitive manual Windows testing is not the default handoff.

Build V1.2 as a coherent improvement to the actual learning experience. A green engineering gate does not establish good teaching or complete source interpretation. Evaluate both independently. No claim that the product is “perfect,” that an exam question is guaranteed, or that all semantics are certified without evidence.

Choose the best implementation within the requirements below. Routine design choices, an internal written plan, isolated feature-store changes, automated fixture operations, implementation commits, and a feature-branch push are authorized by this prompt. Do not ask for repeated design approval or stop at an environment problem. If an action needs a new external permission, production change, or materially wider scope, complete independent authorized work first and identify that precise boundary.

You may use independent agents for bounded implementation and read-only reviews. Assign disjoint files or sequence shared edits; the primary agent owns integration and executed verification. Do not confuse a reviewer’s opinion with browser or content-validation evidence.

### Outcome required

1. A calm, lesson-oriented reader that restores the prototype’s easy reading experience inside ANVAYA.
2. Complete full notes, strong exam revision, restored recall cards, and useful learning-by-doing interactions.
3. A source-element coverage ledger and targeted review workflow that expose omissions and ambiguities.
4. Durable resume/recheck flows and actionable low-stakes Analysis evidence.
5. A tested, bounded route toward Tutor consuming exact learning mistakes, with honest compatibility limits.
6. A reusable authoring/import workflow that reduces Anand’s copying and package repair work.
7. Automated Ubuntu/Windows gates, exact commit evidence, and zero mandatory routine manual Windows layout steps.

## 1. Authoritative starting point — do not restart

Repository: `anandpriyadarsi/Personal--AI--Learning-Chatbot`.

Verified V1.1 branch: `feature/learning-studio-v1-1`.

Verified V1.1 tip: `775941c730e8160501c849bc4971e8eb178331d1`.

Verified tip tree recorded by the previous Work evidence: `0bb2f119fa67eadb99b1cd43d5481e012a0f93d0`.

Previous V1 base: `9ed585ca8e1fbcfb6f5a7e0426d030560109115e`.

Main as recorded at that checkpoint: `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`. This is historical information, not an instruction to reset main.

Final V1.1 CI: run `38284745183`, at the exact V1.1 tip. Ubuntu job `114930300869` and Windows job `114930301125` succeeded. These jobs were independently checked during preparation of this prompt.

Create an isolated checkout/worktree and branch, suggested `feature/learning-studio-v1-2`, from verified V1.1. Fetch and inspect the live branch before selecting the base. If V1.1 has legitimate newer commits, inspect their ancestry and scope, then report the selected immutable base. If it diverges unexpectedly, preserve it and use the verified checkpoint rather than resetting another workstream. Never start from old main simply because it is the default branch.

Record actual output for:

```text
git worktree list
git branch --show-current
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --short
git log -8 --oneline
git remote -v
```

Fetch through the permitted GitHub connection or existing authenticated Git route. Do not print credentials. Preserve concurrent Tutor, Planning, Assessment, and Learning Studio worktrees. If shell Git cannot push, use the available connector only with exact tested-tree equality and ancestry checks; do not push a reconstructed, untested variant.

### Read first

Read every file in the supplied V1.1 evidence ZIP, including its final acceptance, README, manifest, source integrity, local state, review, raw logs, JUnit, and screenshots. Intermediate red logs are historical, not current failure claims. The one-byte `v11-review-focus-red.log` is incomplete evidence and must not be described as a full reproducible failure record.

Read the accompanying audit and exact recovered pilot. In the selected repository, read:

- `ANVAYA_LEARNING_STUDIO_V1_1_IMPLEMENTATION_REPORT.md`
- `ANVAYA_LEARNING_STUDIO_V1_1_RECOVERY_REPORT.md`
- `ANVAYA_LEARNING_STUDIO_V1_1_AUTOMATED_VALIDATION.md`
- `ANVAYA_LEARNING_STUDIO_TUTOR_READONLY_HANDOFF_V1_2.md`
- `ANVAYA_LEARNING_STUDIO_IMPORT_SCHEMA.md`
- `ANVAYA_LEARNING_STUDIO_EVIDENCE_CONTRACT.md`
- `ANVAYA_LEARNING_STUDIO_FUTURE_AUTOMATION.md`
- current feature service/store/validator, Flask routes, templates, CSS/JS, tests, and CI scripts.

The separate uploaded V1 report and V1 Windows handoff are historical. Their PDF blocker, branch, and pending CI statements are superseded by the V1.1 final acceptance.

## 2. Preserve completed capabilities

Reuse the strict canonical importer, source registry resolver, immutable source snapshots, module/question revisions, stage/publish lifecycle, server grading, append-only attempts, idempotency, 72-module synthetic volume demo, real logo, source navigation, persisted Focus, weak-question anchors, read-only evidence and manual review-context producer.

V1.1 already accepted the real pilot locally through the actual converter, registry fixture, importer, publisher and browser reader: 20 pages, 20 previews, 20 lessons, 31 questions. Do not repeat checksum recovery or claim only synthetic capability.

Recorded validation:

| Environment | Feature | Focused | Full baseline → feature | Meaning |
|---|---|---|---|---|
| Local with private attachments | 76 pass, no failures/skips | 101 pass | 1771/16 → 1792/16 pass/fail | No new failures; raw suite red |
| Ubuntu final CI | 72 pass, 4 external skips | 101 pass | 1769/17/1 → 1787/17/4 pass/fail/skip | Scoped/delta green; raw suite red |
| Windows final CI | 72 pass, 4 external skips | 101 pass | 1769/17/1 → 1787/17/4 pass/fail/skip | Scoped/delta green; raw suite red |

Some older committed reports show 75 or 1791; final raw evidence includes the later test-only timing repair. Record new counts from execution, not by copying a report.

Unresolved: all 20 semantic page states remain `needs_review`; canonical mapping is null; automatic Tutor consumption is absent; actual private-candidate Windows validation was not run. Do not turn those into PASS by relabelling them.

## 3. Product issues that this phase must address

These observations are grounded in V1.1 code and evidence, not hypothetical redesign requests:

1. `learning_module.html` loops through all lessons in Learn and Visualise. The real screenshots are 1440×49403 and 390×72423. The user’s primary study path should not require navigating an enormous page.
2. Full raw source extracts appear before the teaching notes. They preserve slide whitespace/columns; on mobile they consume large areas and produce awkward reading order. Preserve them, but improve the reading presentation.
3. The recovered pilot has `revision.cards` containing 12 recall cards. `pilot.convert_pilot` imports revision Markdown only. The 12 interactive cards are not explicitly converted into canonical recall blocks. Restore and validate them.
4. Prototype lesson activities become `objectives` text blocks. The reader does not provide a structured response/reveal/revisit loop for them.
5. V1 flowchart/mindmap data is an ordered array of strings, and the template renders an ordered list. This cannot represent arbitrary relationships or genuine graph topology.
6. Revision is a long companion rather than a guided quick-review experience, and Practice renders every question at once.
7. `/analysis` offers a link to a separate Learning Studio analysis page. It does not yet provide the integrated, actionable learning view Anand expects.
8. `evidence()` counts historical mapped attempts without rechecking current catalogue validity; its labels need to distinguish historic mapping from current attribution. With an initialized store and zero attempts, it can produce Limited evidence rather than No evidence. Reproduce these before fixing.
9. Topic evidence must count distinct versioned questions, not assume five retries mean five independent observations. Inspection of the analysis template shows a per-group attempt threshold; add precise group-level evidence labels.
10. Setup, authoring, and semantic review still require specialist knowledge. Make repeatable work executable and reduce review to unresolved items.

## 4. Work package A — excellent reading and navigation

### Lesson view

Default Learn should show one selected lesson/section with Previous, Next, lesson number, title, source-page chips, and an accessible collapsible left outline. Allow an explicit All lessons view for readers who want it; keep full print/export. No lesson or source information disappears when the presentation changes.

Use a stable section selector on the existing module route, or an equivalent additive route. Validate module/revision/section identity on the server. Keep historical `#lesson-XX`, source, question, and weak-review links working. Translate existing anchor links into the selected lesson where needed. A missing section must produce an honest bounded error or documented fallback, never silently show a different lesson as if it matched.

Changing Learn/Visualise/Practice/Revision/Source and returning should preserve context when meaningful. Keep explicit Focus Exit precedence, browser back/forward, storage-denied URL fallback, and global sidebar restoration. Do not create competing global and lesson sidebars that both crowd the reader. The left outline may replace the contextual panel in Learning Studio; global navigation must remain reachable.

### Reading presentation

Lead with objectives and teaching notes. Move verbatim extract into an accessible “Compare with original” disclosure or source panel, with the original unchanged and one action away. Default source extract presentation should avoid artificial blank-line walls; any normalized reading copy must be identified as such and retain access to verbatim text and original slide image.

Focus should remove app chrome and use the available canvas. Comfortable text measure, adjustable readable text size, and sensible table widths are still required; full screen does not require stretching prose across a 1920px line. Diagrams/tables may use more width. Avoid clipped headings, tiny source chips, excessive all-cap labels, and an oversized module title repeating before every lesson. Preserve the real ANVAYA logo.

Use existing app theme tokens. Verify dark and light rendering where the shell supports them; do not invent a second disconnected theme framework. Include keyboard navigation, visible focus, dialog focus restoration, reduced-motion behavior, meaningful labels, and touch targets. Hidden navigation must not remain keyboard-focusable. Controls may wrap at narrow widths without covering content.

### Source experience

Open the relevant original page, not a 20-image wall by default. Offer page navigation, readable zoom and exact-source download. Desktop comparison may use a split view; mobile should use a source sheet/selected-page view. Maintain text alternatives and original identity/hash. Do not preload every source image merely to render a single lesson; test request behavior with a deterministic fixture.

### Resume

Persist a bounded reading position/preference in the dedicated feature store through explicit guarded writes. Identify module revision and stable section, and offer a Resume action. Reader GET/startup must remain pure; viewing a lesson may issue a separate explicit progress POST. Reading completion is user-reported, not inferred mastery. A newer revision should offer the prior revision or a clear compatible-section choice; do not silently migrate history or reset attempts.

If a transient local preference also exists, the server record is the durable reading state. Denied browser storage should not prevent core use. With JavaScript unavailable, ordinary links, source access, and notes should remain useful.

## 5. Work package B — revision, recall, and learning by doing

### Exam revision

Keep the complete existing revision companion and add clearly scoped 5-minute, 15-minute, and Full revision choices. These are time-budget suggestions, not guarantees of completion. Quick modes may select core distinctions; explicitly link to full revision for the rest. Preserve all names, list members, original classroom shorthand, and caveats in full notes.

Restore all 12 pilot recall cards as structured canonical recall blocks or a compatible versioned representation. Verify prompts, answers, and exact page references against the candidate, and test that cards appear in the actual Flask reader. Do not import its HTML as executable content. Restoring added recall cards does not authorize changing historical published artifacts; create a new module revision.

Include concept comparison, easy-to-forget items, attributed/ambiguous material, source-linked short recall, and a final checklist. Give weak concepts a visible place in revision; explain selection using recorded misses. Correct retries remain recovered-needs-recheck, not mastered.

For the real pilot, preserve at minimum all four Mahāvākyas with their meanings and Upanishad/Veda associations; Vedanta distinctions; Buddhist schools, four truths/three marks/eight factors; Jain jewels/Tirthankara numbers; text lists; and all flagged classroom/quotation material. Do not flatten doctrinal differences into a single universal Hinduism claim.

### Practice and recovery

Offer lesson-specific practice, mixed module practice, and Recheck my mistakes without showing 31 forms by default. Keep an optional question list. Show useful progress, unanswered state, and a pause/resume path suitable for low-stakes practice. Reuse any compatible Assessment Studio presentation component without touching official test timing/scoring.

Embed existing source-linked MCQs in relevant lesson self-checks when useful. Submit through the same server-authoritative attempt boundary. No pre-answer keys in DOM, data attributes, public JSON, or a separate convenience endpoint.

A wrong answer should return an understandable explanation, source/lesson link, and next action. Return from review to the exact pending question. Repeated wrong answers should suggest a targeted reread or alternate authored explanation. Do not make deterministic template messages sound like an AI diagnosis.

Add useful source-appropriate learning-by-doing interactions through a small trusted widget registry. For this qualitative pilot, implement at least two demonstrable interactions such as a compare/reveal builder and predict-then-check reflection. They must require learner action, provide explanatory feedback, and cite the source. A slider or animation that teaches nothing does not satisfy this requirement. Numerical simulations belong only to sources where a real model is justified.

Reflection text, “I remembered,” revealed cards, and ungraded activities are self-report/engagement evidence, not automatically correct answers. They must not affect server-graded accuracy or official grades. If introducing a new graded question type, define strict private-key validation and grading and prove it independently; otherwise keep graded scope to existing MCQs.

### Visual aids

Use meaningful comparisons and relationships, not an automatic “mindmap” for every slide. Implement at least one genuinely relational concept map and one meaningful process flow using trusted data and accessible text alternatives. Do not manufacture historical genealogy from the pilot’s branches schematic.

V1 nodes do not contain edges: preserve their honest legacy rendering, and do not infer arbitrary topology. If adding a new graph/block contract, version it deliberately, bound node/edge counts, validate referenced IDs, and retain V1 imports/history. Render from escaped server-owned templates or another audited local renderer. Imported HTML/SVG/JavaScript, callbacks, remote URLs, eval, or dynamic executable templates remain prohibited. Internally generated SVG is acceptable only from validated trusted graph data with an audited renderer; importing arbitrary SVG remains blocked.

Keep equation rendering readable for MA103N/UC100N fixtures without weakening the current text/raster fallback or adding a mandatory CDN.

## 6. Work package C — source completeness and content review

### Coverage ledger

Original preservation is already verified. Now build a separate source-element ledger that records what the learning notes actually cover. Scope V1.2 extraction to supplied PDFs and already-authored packages; do not promise complete PPTX speaker-note/media extraction in this phase.

For each page, enumerate meaningful text elements, bullets/list members, named terms, table headers/cells, diagram relationships, displayed equations, captions, and visible classroom annotations. Preserve the original text/image. Assign stable feature-local element IDs with page and locator evidence. Each element maps to lesson blocks or an explicit unresolved entry with reason and next action. Distinguish noninstructional decoration/footer from information; exclusions require a reason.

Use clear independent states:

- Original byte/page/preview availability.
- Structural element inventory and mapped coverage.
- Source-to-notes fidelity review.
- External factual/quotation verification.
- Canonical academic mapping review.

These must not collapse into a single green 100% badge. Token overlap, matching hashes, and a model agreeing with itself cannot certify semantics. A mapped claim may still be oversimplified or disputed. Visual-only elements need visible inspection evidence or unresolved status.

Store reviewer/method, source hash, module revision, findings and dates. A source or derived-content change makes affected review assertions stale. Keep old review records and old attempts; do not rewrite the old package. If the current V1 schema cannot carry the ledger, prefer a versioned companion contract in the feature store; introduce a new package schema only for an actual incompatible representation need.

### Real-pilot quality pass

Audit all 20 lessons and all 31 questions, answer indices, distractors, explanations, and citations against the supplied original and recovered authored notes. Do not accept a page reference merely because it is in range. A question should be answerable from its stated source/lesson, not an unstated external fact.

Inspect all original pages visually, including table/column relationships. Keep original claims and added teaching separate. The source’s page 3 genealogy-like schematic, page 6/20 generalization versus page 7 Vedanta diversity, page 7 marginal shorthand, page 11 scientific quotations, page 14/18 attributed quotations, page 15 undefined terminology, and page 17 chronology are known review hotspots. Preserve their wording and explain uncertainty rather than silently correcting the slides or presenting them as independently established facts.

Perform an independent content review distinct from the implementer’s review. Produce a compact unresolved queue, showing original snippet/image location, proposed explanation, issue, and evidence. The agent should complete all mechanically decidable checks and safe improvements first. Human clarification is needed only for genuinely unresolved instructor intent, disputed quotations, or mappings that cannot be resolved from the catalogue. Do not hand Anand 20 generic “please review page” items if only a small subset is uncertain.

Do not auto-set `verified` merely to finish the feature. A recorded agent fidelity review may establish a narrower source-faithfulness result; it is not external historical certification or instructor approval. Honor the actual validator’s meaning of each status and document review authority explicitly.

### Course and topic organization

Preserve Academic year → Semester → Course → Unit/topic → Lecture. Use real catalogue metadata where available and explicit unspecified/unmapped states elsewhere. Test at least six synthetic registered courses with twelve lectures each plus unmapped and removed-course cases.

Add a staged mapping-review affordance that shows exact registered candidates and their evidence. No invented canonical topic ID, course creation, or course name inferred solely from this prompt. Read the current registry without altering it. Apply a confirmed mapping only to a new immutable derived revision after live catalogue validation. A production catalogue or human confirmation being unavailable must not block the rest of V1.2; leave the real pilot source-first/unmapped.

## 7. Work package D — actionable Analysis and bounded Tutor bridge

### Evidence correctness

Reproduce and fix empty-history labels. Distinguish No evidence, Limited evidence, and Low-stakes practice evidence using distinct question versions per displayed scope. Ten retries of one question remain one distinct observation. Keep counts of attempts, unique questions, ever-missed questions, currently wrong, and recovered-needs-recheck separate.

Preserve historical mapping snapshots but expose current mapping validity explicitly. Deleted/renamed topics, unavailable catalogues, and null mappings must not become current reviewed topic evidence. Do not attribute all lecture questions to a narrow topic that their references do not support. A canonical confidence threshold is a necessary check, not proof of semantic correctness.

Create deterministic revision/recheck priorities based on visible evidence, such as repeated unresolved misses, recent misses, recovered items needing recheck, and insufficient evidence. Explain priority in plain language. No invented mastery percentage, mental-state diagnosis, or official exam score.

### Analysis UI

Add a bounded read-only Learning Studio component to existing `/analysis` using the existing extension seam. Include current weak/recovered lecture signals, mapping/review labels, and direct Review lesson / Recheck / Open revision actions. Keep full details on `/learning/analysis`. Empty/unavailable feature storage should show a useful empty state without initializing a database. Do not replace existing Analysis authority, planner policies, official grades, or production progress.

### Tutor integration — inspect the actual interface before coding

Read `ANVAYA_LEARNING_STUDIO_TUTOR_READONLY_HANDOFF_V1_2.md`. V1.1 already has exact-version server projections at `/review-context` and `/review-brief`; they do not create a Tutor session. A course-only `/agent` link is insufficient.

Inspect the selected branch’s existing source-grounded Tutor seams and currently active separate Tutor work. Implement a narrow explicit-action adapter only if it can consume module ID/revision, fetch server evidence, bind the real source/version and owner, and use the existing authorized Tutor session path without editing teaching reasoning, provider grading, memory/mastery, or another branch.

Requirements for a supported adapter:

- GET/navigation/Analysis rendering never creates sessions or calls a provider.
- Explicit guarded POST resolves server evidence; reject caller-supplied correctness, owner, mapping, source hash, and arbitrary redirect/prompt data.
- Fetch only the requested published historical module revision; bound context and preserve source citations and uncertainty.
- Retain wrong→correct history and limited/empty evidence labels.
- Unmapped/stale mapping stays source-first; never fabricates academic attribution.
- Client cannot use the action to read private answer keys. Authorized Tutor source grounding must distinguish teaching support from assessment keys.
- Provider/session writes, if supported, stay within the existing Tutor-owned mechanism and require the explicit learner action. Feature evidence and other authorities remain unchanged.
- Provider unavailable, incompatible session/source contract, and deleted source fail safely; manual brief remains usable.

Write all ten adapter contract tests described in the existing handoff plus context-bounds and duplicate-action tests. Stub providers for deterministic tests; live provider checks are optional only if existing credentials/authorization are available. Do not ask Anand to configure a new provider just to test UI.

If the safe consumer seam does not exist, do not rewrite Tutor to force it. Finish all independent V1.2 packages, implement/test the bounded producer/compatibility boundary, keep the automatic action honestly unavailable, and provide exact interface findings and a small Tutor-owned patch plan. Mark this acceptance row BLOCKED, not implemented. This exception is confined to the incompatible consumer and must not become a reason to stop reader/content/Analysis work.

## 8. Work package E — reusable authoring and one-command verification

Anand’s immediate preferred workflow remains: provide lecture material to ChatGPT, receive a compatible reviewed package, import it into ANVAYA. Do not start Moodle scraping or a broad generative conversion service before the quality contract works.

Deliver a reusable authoring brief/template for future subjects, a canonical example package, and an executable preflight command. The brief must explain complete source preservation, coverage ledger, revision cards, questions, original-vs-added claims, uncertain material, and exact source IDs/hashes. Source IDs come from the real registry or an explicitly synthetic demo, never fabricated production registration.

Preflight should validate package schema, all references/assets, source identity/hash/page count, private/public key projection, canonical mapping availability, review state, and importer limits before storage. Its error report should point to precise fields and actionable repairs. Never “repair” a source mismatch by rewriting the expected checksum. Never write production data to make a test pass.

Provide a pilot export/normalization path using the existing adapter and strict importer so the actual module can be staged in a disposable environment without hand-editing JSON. Publish a safe synthetic canonical example in the repo; the real lecture content and private candidate remain private deliverables unless the owner separately authorizes public redistribution.

Add a cross-platform Python healthcheck/validation runner that discovers the repo root, verifies interpreter/dependencies/browser availability, uses temporary roots/databases, runs gates in a safe order, and emits JSON/JUnit/log paths. It should fail quickly with a specific diagnosis if a dependency is missing, and never silently disable browser tests. Cache ordinary dependencies where safe; do not use production fixtures or hidden environment state.

Name commands clearly in the final handoff, for example `python scripts/learning_studio_validate.py --scope feature --output ...`, if that is the actual script you implement. Do not claim these proposed names already exist. Keep Ubuntu and PowerShell usage semantically equivalent. Do not make Anand manually repeat healthchecks, screenshots, source checksums, or every quiz action.

## 9. Architecture and safety boundaries

Reuse the existing Flask application and package style. Relevant starting paths:

- `personal_learning_assistant/learning_studio/{service,store,validation,archive,sources,pilot,rendering,demo}.py`
- `personal_learning_assistant/ui/web/learning_studio.py`
- `personal_learning_assistant/ui/web/templates/learning_module.html`, `learning_library.html`, `learning_analysis.html`, and existing `analysis.html`
- `personal_learning_assistant/ui/web/static/css/learning_studio.css`
- `personal_learning_assistant/ui/web/static/js/learning_studio.js`
- `tests/learning_studio/`, schema/contracts, `.github/workflows/learning-studio.yml`, existing JUnit/regression gate scripts.

Confirm exact paths in the live checkout. Split responsibilities when adding substantial reader, review, progress, and evidence logic; avoid a giant route/service/template or an unrelated rewrite.

All new persistence belongs to `learning_studio.sqlite3`, with explicit schema versioning and migration tests only for this feature DB. Test migration of a populated V1 store, preserving every old module/publication/asset/attempt row and historical grading. Refuse foreign databases and unsafe/symlink paths. Backups and rollback documentation must match the actual migration; a downgrade that loses new state is not a safe rollback.

Do not modify production academic databases/data, grades/mastery, Moodle, Notes/Obsidian content, retrieval indexes, original sources, active Tutor branch, or main. No merge or force push. No destructive cleanup of other checkouts. No imported executable content. No new Internet dependency for ordinary reading. API/provider errors must not lose reading or recorded practice.

Keep the single-owner local app boundary; do not invent a multi-user authentication project. Reuse current CSRF/same-origin/Fetch Metadata guards for explicit writes. Enforce payload limits, server-owned timestamps and grading, immutable revisions, and idempotency. Ordinary GET/startup, context generation, exports, and Analysis remain read-only.

## 10. Automated acceptance gates

Write a short internal implementation plan mapped to requirements, then execute it. For new behavioral regressions show meaningful fail-first evidence. Avoid testing only that a CSS class or implementation constant exists; assert observable behavior and protected-state boundaries.

### Required engineering tests

1. V1 imports and historical modules/questions remain usable after V1.2/store migration.
2. All twenty real lessons/pages/previews and all thirty-one original questions remain accessible; keys/citations agree; twelve cards are restored.
3. Single-lesson default, outline/Previous/Next/All lessons, old anchors, weak-question review-return, exact source-page navigation, reload/history/Focus and explicit Exit.
4. Durable reading/practice resume across browser/server restart; revision handling; denied storage/JavaScript fallback; no inferred mastery.
5. Revision quick/full modes, reveal interactions, source labels, wrong→correct→reopen→recheck, unanswered questions, duplicate submissions, and graceful network errors.
6. Coverage catches omitted bullet, missing list member, changed comparison relationship, unsupported visual element, source change, invalid locator and stale review. Ambiguous assertions remain flagged.
7. Graph/widget validation rejects malformed IDs/edges, oversized data and injected markup/code/URLs; accessible text fallback agrees with rendered relationships.
8. Empty/limited/per-group distinct evidence; stale mapping attribution; no repeated-retry inflation; exact-version/module isolation and key exclusion.
9. Integrated Analysis remains pure and actionable, including missing feature DB and unavailable catalogue.
10. Tutor tests and boundary disposition from section 7; no accidental provider/session calls on GET.
11. Import/resource limits, source hash tampering, ZIP raw paths/Windows normalization, bomb/CRC, source staleness, immutable publication and CSRF behavior remain enforced.
12. Populated feature DB migration, foreign DB refusal, no initialization on GET/startup, source/academic protected snapshots, and isolated temporary-directory ownership.

### Browser and visual quality

Run actual Playwright Chromium with viewports 1920×1080, 1536×864, 1366×768, 1024×768, 768-wide, 390-wide and a 360-wide narrow edge. Test normal, collapsed, Focus, temporary Contents, selected lesson, revision, practice, weak review, and source. Test both shell themes if supported.

Automated assertions: page does not horizontally overflow; tables/graphs scroll within their own region; titles wrap; controls remain visible/clickable; focus does not expose hidden navigation; modal focus returns; next/review/source locators target the right content; initial lesson view does not contain all twenty lessons; source requests are bounded. Check print output for legibility and complete Full revision notes; quick-mode prints disclose their subset scope.

Capture representative viewport screenshots, inspect them visually, fix defects, and rerun affected gates. Use complex content fixtures, not only a one-line synthetic lesson. Real-source screenshots are private; public CI artifacts should contain synthetic material. Automated accessibility checks plus manual agent keyboard inspection are complementary, not a certificate of universal accessibility.

### Regression and CI

Extend CI to the new branch. Set the full-suite comparison base to the actual selected V1.1 SHA, not the V1 workflow’s old ternary/default main base. Run baseline and feature sequentially in isolated roots to avoid browser/resource interference. Preserve distinct per-run evidence instead of overwriting red logs on rerun.

Run new/old scoped gates, focused authority/startup/Assessment regressions, compile/static checks, and full-suite node-ID comparison on Ubuntu and Windows. Zero newly failing, missing, or newly skipped executed cases. The existing four private-attachment cases may skip only where bytes are unavailable; report each by node ID and never count them as executed real-pilot validation. All new built-in gates must execute, not skip.

At least one local run must execute the bundled real pilot, including new reading/cards/content checks. Match its SHA before use. Actual private-candidate Windows validation is desirable only through an already available authorized private runner/transfer mechanism; do not publish lecture content, add secret infrastructure, or give Anand a mandatory manual testing chore to obtain it. If unavailable, label that exact boundary NOT RUN and use realistic synthetic twenty-page fixtures on both OSes.

Inspect final CI jobs and counts at the exact last pushed SHA, including documentation/test repair commits. Pending is not PASS. A successful workflow with grandfathered baseline failures is scoped/delta success; report the raw suite separately. Do not fix unrelated Tutor/Coding Helper baseline failures, weaken tests, or manufacture production data in this branch.

If an existing baseline fails intermittently, reproduce it with matched environment and sequential execution, retain all observations and explain the evidence. Do not dismiss a new failure as flaky without investigation. Bounded condition-based browser waits are appropriate; arbitrary sleeps or relaxed assertions are not a repair.

## 11. Independent quality reviews and completion

Obtain independent read-only review of the final delta for correctness, immutable/source/data boundaries, rendering/import security, API compatibility and regressions. Obtain a distinct content/learning experience review of all actual pilot lessons/cards/questions and representative reader flows. Reviewers should name exact findings, severity and verification evidence. Fix important findings with focused regressions and rerun affected gates. Complete a final whole-branch review after integration.

Do not wait for Anand to do routine QA. Minimize any human queue to instructor ambiguity, disputed source assertions, or canonical mapping confirmation. Keep it separate from product engineering acceptance. A remaining semantic item does not justify leaving unrelated implementation unfinished.

Commit scoped changes on the V1.2 branch, push without merging, verify remote SHA/tree equals tested code, inspect final exact-SHA CI, then deliver:

1. `ANVAYA_LEARNING_STUDIO_V1_2_IMPLEMENTATION_REPORT.md` — final behavior, architecture delta and verified base/tip/tree.
2. `ANVAYA_LEARNING_STUDIO_V1_2_ACCEPTANCE.md` — requirement-by-requirement PASS/PARTIAL/BLOCKED/NOT RUN, engineering versus content versus Tutor status.
3. `ANVAYA_LEARNING_STUDIO_V1_2_CONTENT_COVERAGE.md` and a machine-readable ledger for all twenty pilot pages.
4. `ANVAYA_LEARNING_STUDIO_V1_2_AUTOMATED_VALIDATION.md` — exact commands, environment, node IDs/counts, raw suite/delta distinction, CI URLs/SHA and skipped/private boundaries.
5. `ANVAYA_LEARNING_STUDIO_AUTHORING_GUIDE.md`, reusable ChatGPT authoring prompt, synthetic canonical example, and preflight/validation commands.
6. `ANVAYA_LEARNING_STUDIO_V1_2_QUICKSTART.md` — separate disposable checkout, one healthcheck/validation command, one demo command; optional Windows use, no mandatory layout checklist.
7. Tutor adapter implementation contract/status, or exact bounded compatibility blocker and future Tutor-owned plan.
8. Private final evidence ZIP with logs/JUnit, manifests, reviews, coverage, acceptance and representative screenshots; keep reports consistent and label historical runs.
9. Private improved pilot package/new revision that preserves the original source and original questions, with restored cards and reviewed additions. If it requires a new schema, include compatible importer/version documentation. Do not imply demo source IDs are production imports.

Preserve a resume checkpoint with selected SHA/worktree, completed tasks, changed paths, test commands/results and precise remaining gates if execution is interrupted. On continuation, inspect that checkpoint and the actual branch; do not repeat completed architecture or setup.

Final summary should tell Anand: what improved for studying; exact feature branch/commit; what truly ran on both OSes; what remains a semantic/mapping/Tutor limitation; and the two commands needed to try the disposable demo. Do not ask him to review dozens of screenshots or report “fully accepted” while important acceptance rows remain blocked.

## 12. Supplied input integrity

- Recovered pilot ZIP SHA-256: `e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923`.
- Original PDF SHA-256: `75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411`.
- Attached V1.1 final evidence ZIP SHA-256: `64d11091a3939df722f4643e2ca737273e4d9d30ddad320ff3a7e57644c19d53`.
- The older damaged V3 PDF SHA was `f812fb27240fc5cd5265a1608f80ac480f241b56f9b27d4826bb6453b319735b`; it remains unacceptable for that expected-source manifest.

Hash input files before/after. Do not modify supplied evidence or the original PDF. The bundle contains the exact recovered candidate; no repeated candidate recovery should be necessary.

Later roadmap, outside this phase: add assisted PDF/PPTX drafting with speaker-note/table/chart/media coverage, then broader course revision and justified numerical simulations; Moodle automation and deeper Tutor adaptation require their own proven contracts. V1.2 should make the reader and quality boundary strong enough to support those phases.
