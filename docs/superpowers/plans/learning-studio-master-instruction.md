# ANVAYA LEARNING STUDIO — MASTER IMPLEMENTATION PROMPT FOR CHATGPT WORK

**Mission:** Audit the current GitHub implementation briefly, make the necessary design decisions, then **implement, test, review, commit, push, and hand off** a dedicated **ANVAYA Learning Studio** feature on an isolated branch. Do not end after an audit, roadmap, specification, or mockup. Do not merge to `main`.

## 0. Repository, authoritative inputs and operating context

- Repository: `anandpriyadarsi/Personal--AI--Learning-Chatbot` (GitHub; connect using the installed GitHub connection).
- Current application: local-first Flask/Python ANVAYA, with structured courses/topics, independent Notes, Obsidian workspace, Knowledge/Resource source registry, Assessment Intelligence, Tutor and Analysis.
- **Attach and inspect the supplied** `ANVAYA_Interactive_Learning_Pilot_Complete_v3.zip` **alongside this prompt.** Treat its HTML prototype, proposed JSON, original 20-page source PDF, full study notes, revision notes, source-fidelity report, integration plan and headless validation reports as **prototype evidence and desired UX**, not as already deployed code or accepted schemas. Unzip and inspect it. If the ZIP is not attached or inaccessible, stop before claiming that the actual pilot has been imported; still proceed with independently safe architecture-independent tests and a synthetic-module renderer where useful, clearly marking the missing fixture dependency.
- User goal: convert Moodle-delivered PPT/PDF lecture material into **source-complete, more engaging, learning-by-doing notes** with mind maps, flowcharts, conceptual comparisons, exercises, day-before-exam revision and course-aware learning analytics. Expect approximately 6 subjects × 10–12 presentations, eventually growing over four years.
- Pilot content is **Hinduism, Buddhism & Jainism** from a 20-page PDF presentation; **UC103N is a course hint, not a verified canonical course mapping**. Do not silently attach the pilot to production course/topic IDs.
- Use actual repository/branch state as source of truth. Do not assume historic SHA values, routes, table definitions, services, branches, or test outcomes are current.

## 1. Non-negotiable safety, authority and development rules

1. Work in a **new dedicated feature branch/worktree**, suggested `feature/learning-studio-v1`, from the best current verified base. Record exact base branch and commit SHA. If branch exists, inspect before reusing; do not overwrite unrelated work. Preserve any dirty working tree; use a clean worktree instead. No merging to main, no force-push.
2. **Never modify production academic data**: original PPT/PDF bytes, user's Notes JSON/assets, Obsidian vault, learning memory, official assessments, historical attempts, existing course registry, production SQLite DB, actual Moodle material, API secrets or retrieval index. Tests and migrations must run only on temporary synthetic fixtures and isolated databases. Hash protected artifacts before/after as feasible.
3. Preserve authority separation: original files belong to existing source/Knowledge/Resource authority, personal Notes remain distinct from Obsidian, Learning Studio modules are **derived versioned educational artifacts**, and retrieval indexes remain rebuildable derived data. Do not introduce a parallel grade/mastery authority or a third personal-Notes store.
4. Do not alter Tutor 2.0/2.3 reasoning, prompting, session orchestration, grading or scenario-validation work. Integrate only via a small, documented, read-only contract unless a separately proven safe bounded adapter is needed. Do not interfere with architecture-audit/planning worktrees, work in progress, or active validation gates.
5. Never claim 100% information preservation or verified semantic fidelity based only on extracted text. Preserve and expose the entire original file and an exact slide/page identity. Unknown content, image-only slides, complex charts, formula fragments, speaker notes and disputed assertions must receive review flags. Additional AI explanation must be visually distinguishable from source claims. Do not silently hallucinate or "correct" professor content.
6. No code execution from imported HTML/JSON, unsafe Markdown, event handlers, arbitrary scripts or raw SVG. Sanitize safe content and media URLs; enforce content type, path traversal, archive bombs, maximum size, symlink and ownership checks; avoid external rendering/network dependencies for local reading.
7. Use explicit, honest green/red validation gates. Do not weaken or skip failing tests or manufacture passing output. Prefer Linux/Windows automated tests and headless browser checks; only request manual Windows validation for genuinely environment-specific evidence that cannot be automated.
8. The goal is a working production-quality **V1 reader, module organization, safe import and low-stakes practice evidence**. Automated Moodle sync, generative PPT authoring, fully automated semantic verification and broad Tutor rewrite are **future phases**, not prerequisites to delivering a useful V1.

## 2. Required short repository audit (then implement)

Inspect exact current code/tests for:

- `personal_learning_assistant/ui/web/templates/base.html`, `static/brand/anvaya-mark.png`, `static/brand/anvaya-wordmark-white.png`, global sidebar CSS/JS and route registration. These assets **already exist on a recent main**; reuse them. The existing ANVAYA app already has collapsible global navigation: **do not build a conflicting second global navbar or duplicate brand assets**.
- `personal_learning_assistant/ui/web/routes.py`, service-builder patterns, template/CSS/JS organization, lazy Flask startup, error behavior.
- Current courses/topics and academic mapping services, including the canonical topic catalogue; no arbitrary course creation.
- `personal_learning_assistant/ingestion/extractors.py` (historic PPTX extractor was primarily text-oriented), Knowledge Reader, source registry, unified ingestion and Study Interaction.
- Independent ANVAYA Notes versus Obsidian: `PHASE7_5_15_10_NOTES_OBSIDIAN_SEPARATION_SPEC.md`; focus/sidebar/Analysis: `PHASE7_5_15_14_FOCUS_COMPANION_ANALYSIS_SPEC.md`; existing practice, Assessment Intelligence and Analysis service.
- Existing schemas, persistence patterns, migrations, tests, CI and protected-data validation gates; inspect concurrent branch overlaps.
- Prototype V3's actual `OPEN_ME_Interactive_Learning_Studio.html`, `ANVAYA_Learning_Module_Proposed_v1.json`, `DAY_BEFORE_EXAM_Revision_Notes.md`, source fidelity report and source PDF.

Write a concise audit/contract note identifying confirmed reuse, necessary new boundaries, risks and scope. **Then immediately implement** within the approved constraints. Choose a sound design yourself; no further feature-design approval is required for safe additive work. Ask the user only for a missing indispensable artifact or truly destructive operation.

## 3. V1 user journey and information architecture

One **Learning Studio** link in the existing ANVAYA Learning navigation. Do not put every PPT, every slide or every generated note on Home or in Personal Notes.

Hierarchy: **Academic year → semester → registered course → unit/canonical topic → lecture/presentation module**.

- Landing `/learning` (or repository-consistent route): compact registered-course cards with course name/code, module count and recent activity; empty-state if none. No module body or all-slide list on landing.
- Course view: grouped topics/units, filtered searchable module cards, compact pagination or efficient lazy loading; 6 courses × 12 modules should remain navigable without oversized pages, duplicated cards, O(N) expensive parsing per request or many queries per card.
- Module view: Overview, **Learn**, **Visualise**, **Practice**, **Day-before-exam Revision**, **My Weak Questions**, and **Original Source**. Preserve all source links; revision is an *additional compact view*, not a destructive replacement for full content.
- Always show breadcrumb course → unit/topic → module and source page/slide link where relevant. Support an explicit "Back to course" action.
- No silent assignment of UC103N unless a reviewed canonical course mapping exists; otherwise show “Unmapped / needs review.”

## 4. Exact UI and navigation requirements

- Replace prototype's placeholder turquoise **"A" badge** with the **real ANVAYA logo**. In the Flask application use existing `static/brand/anvaya-mark.png` / wordmark via `url_for('static',...)`, not a guessed path or hotlinked asset. If updating standalone prototype HTML, embed or package a portable copy of the actual logo. Correct alt text and accessible brand link.
- Use existing ANVAYA shell and **desktop-collapse behavior**, with *module-level navigation only if it does not duplicate/conflict with global nav*. A prominent toggle must hide navigation completely; the reading column must actually expand. No reserved blank gutter.
- **Focus Reading** hides left navigation and distracting header/topbar and allows nearly full viewport reading. It is not sufficient to just change sidebar opacity. Provide a persistent small `Contents` button / temporary overlay and `Exit focus`; restore normal navigation; Escape handling; optional browser Fullscreen API only upon gesture and graceful fallback.
- Mobile: accessible overlay navigation, no horizontal overflow or cut-off headings (especially long titles), visible close/toggle, meaningful keyboard/ARIA behavior, no trapped focus and no duplicate menus. Remember preference when safely possible; support browser storage failures.
- Readability: properly wrapping headings, comfortable typography, clear tables/diagrams, source chips, annotated quotations, maths display, print-friendly revision, consistent dark mode. Avoid wasting reading width when sidebar is hidden.
- Do not introduce heavy SPA frameworks or external CDN if current Flask templates/CSS/vanilla JS suffice.
- Build the desktop and mobile experience using real layouts and deterministic browser checks, not screenshots alone.

## 5. Learning and revision content model

Accept a **versioned, validated, structured learning-module package**. The pilot JSON schema (`anvaya.learning-module.v1`) is *proposed*, not currently an official importer. Inspect it and define a reviewed, documented canonical V1 schema plus a deterministic converter/adapter from the pilot where needed. Do not add dangerous raw HTML injection. Minimum data:

- Immutable `module_id`, `module_revision`, `source_id`, `source_sha256`, original filename/type, per-slide locator, optional `course_id/topic_id` only after canonical mapping review.
- Ordered sections/blocks: sourced explanation, definitions, worked examples, tables, key terms, mindmaps, flowcharts, images/captions, extra teaching explanations, learning objectives, misconception reminders, source references, review flags.
- Revision: **Day-before-exam Notes** with exam-oriented comparisons, high-yield key points, easily confused or forgotten concepts, memory traps, recall questions with optional reveal answers, checklists, source page references, print styling. “Likely exam question” must be framed as an *authoring estimate*, never evidence of actual exam probability unless supported.
- Practice: stable question ID and revision, question type, prompt, options/key kept out of public answer responses before submission where appropriate, explanation, source references, canonical topic mapping status, difficulty and low-stakes status.
- Source fidelity manifest: 100% of original slide/page *identities and bytes must remain available*, but coverage of each extracted semantic element is a distinct reviewed state (`verified`, `needs_review`, `unavailable`). No invented 100% certified badge. A new/changed source creates a new immutable version and invalidates stale previews appropriately.
- Visual blocks retain safe textual alternatives, traceable source references and reversible/editable notation where feasible. Static/interactive concept diagrams must have text alternatives.

Importer must validate schema/version, asset ownership, file type/size, required IDs and references, duplicate IDs, source hash match, question shape, key correctness, mapping confidence/review state and sanitizer rules. Reject unsupported and malformed data without partial production writes. Use transactions/staging and clear diagnostics. Distinguish **preview/stage** from **publish/activate**; block publication of unresolved critical source-integrity failures. Historical module revisions and references must remain intact. Do not automatically save derived module content in Personal Notes or Obsidian. Provide a safe “Save my own note” affordance only if it reuses the proper existing Notes service and requires explicit user action; otherwise defer.

**V1 conversion boundaries:** Implement importing already-authored packages like the supplied pilot, not cloud LLM auto-generation from arbitrary Moodle PPTs. Preserve existing PPTX/PDF ingestion behavior unless safe additive enhancement is fully tested. Document an eventual richer extractor/source coverage architecture rather than misrepresenting the old XML text extractor as visually complete.

## 6. Practice attempts, weak questions, Tutor and Analysis

The user explicitly wants the system to **remember incorrect answers** even after a corrected retry and surface weak concepts for future tutoring and analysis.

Build a minimal, safe, **server-authoritative append-only low-stakes attempt store** in the feature's dedicated data boundary, *only* after its schema/transactional migration is designed and validated with isolated synthetic databases. If adding migration would compromise other active work, implement a gated isolated persistence adapter with documented blocker and keep reader/importer independently shippable. Do not use browser `localStorage` as authoritative learning evidence.

Record: learner/session identity within app's actual auth model (never invent multiuser auth), stable event ID/idempotency key, module ID/revision, source hash, question ID/revision, reviewed canonical course/topic IDs where known, selected response, server-derived correctness, attempt number, timestamp and source page. Keep wrong attempt when the user retries correctly. Grade only against the **exact immutable question version** on the server; ignore forged client `is_correct`, arbitrary course/topic strings and stale/mismatched source versions. Do not mark an imported response as an official Assessment Studio grade.

- `My Weak Questions`: missed questions, latest response, last incorrect, recovered-but-needs-recheck, related lesson and source pages.
- Analysis read-only adapter: grouped counts/trends for low-stakes practice, ever missed/latest correct, repeated misconceptions, reviewed vs unmapped topics; show *limited evidence* where sample size is small. **Never automatically overwrite mastery, assessment scores, grades or progress** from a single practice answer.
- Tutor integration: expose a narrow, versioned `LearningEvidenceSummary` or repository-approved equivalent that can be read when tutoring on a reviewed topic. Provide an explicit “Review with ANVAYA Tutor” deep-link/action with relevant source/topic context. Do not silently invoke an AI model on every answer; do not modify Tutor 2.0/2.3 teaching logic or current scenario workflows. If a compatible read-only Tutor entry point is not available, ship the documented contract and disabled/degraded affordance rather than fabricate a working integration.
- Offline local evidence JSON from the prototype, if import is included, must be schema-validated, associated with this specific module version and regraded server-side; reject duplicated event IDs, tampering and foreign user data. Do not trust client correctness flags.
- Keep a per-question and per-module revision history that cannot be erased by UI retries; design appropriate retention/export without creating duplicate truth stores.

## 7. Storage/API principles and performance

Follow existing service/repository patterns after audit, not invented absolute module paths. Prefer stable domain models, typed validation, explicit service boundary and thin Flask routes. Use existing storage authority for sources; additive metadata may use the repo's approved SQLite boundary or app-managed versioned module artifacts, with deterministic reconciliation. No arbitrary folder scanning on every request. No hidden writes during GET. Index/cache only where safe, rebuildable, versioned and tested.

Include pagination/search/filtering, stable sorting, course/unit grouping, missing/unmapped course behavior, archived or source-changed module status, and clear empty/error states. Source assets should be served with validated scoped IDs and restricted relative paths, not arbitrary filesystem input.

## 8. Implementation sequence; deliver working slices, not just design

Proceed in bounded, testable vertical slices. Each slice must have code, tests, diff review and a green gate before changing the next risky authority:

**Slice A — integration foundation + real logo + reader shell.** New `/learning` route and navigation entry; existing brand assets; module reader with collapsible sidebar and Focus Reading; safe rendering of synthetic modules; accessible mobile; route/error/lazy-startup tests.

**Slice B — structured library + pilot import.** Course→topic→lecture hierarchy; import/validate/stage/publish a versioned module; use the attached 20-page example in *isolated demo fixtures*, preserving original source PDF/visuals; present Learn, Visualise, Original Source, Revision, Practice, Weak Questions. Support 6×12 synthetic modules without clutter. Reject unsafe packages and broken cross-references.

**Slice C — low-stakes attempt evidence.** Authoritative server grading, append-only history across retries/reopens, weak-question view and safe optional evidence export/import. Test all idempotency, corruption and replay cases. No official grade mutation.

**Slice D — read-only Analysis + Tutor handoff.** Expose a bounded Analysis section for Learning Studio low-stakes evidence; link reviewed weak concepts to the existing Tutor entry point *without touching Tutor reasoning*. If actual adapter integration is unsafe, stop this slice only and finish unrelated green slices with an explicit tested interface and blocker.

**Slice E — final polish, documentation, CI and review.** No Moodle automatic scraping or full generative PPT conversion in V1; include a future-phase spec for high-fidelity PPT extraction and Moodle import.

Keep each commit scoped and descriptive. If one high-risk gate is blocked by unavailable production-only verification, keep independently validated slices moving; do not weaken that gate. No final merge.

## 9. Mandatory test strategy (minimal manual Windows work)

Use temporary source roots, synthetic file storage and SQLite fixtures; do not require the user's actual Windows setup or production DB for routine green gates. Implement deterministic pytest contract/unit/integration tests and browser tests (Playwright or existing harness if present), with CI on **Ubuntu + Windows** using pinned dependencies. Use synthetic source modules with:

- 6 registered courses × 12 modules, multiple units, long headings and 20-page sample, pagination/search, correct grouping.
- Source page with pure text, pure image, table, formula, long diagrams, quotations and missing/unverified visual mapping.
- Normal schema, invalid schema, version mismatch, stale source hash, asset escape attempts, malicious Markdown/HTML, duplicate IDs, cross-module asset requests, ZIP bombs if ZIP supported.
- Correct, incorrect, retry-correct, retry-incorrect, replayed event, forged `correct=true`, unknown question, source/version mismatch, user/session mismatch where meaningful, unmapped topic, duplicate import, reopen/history conservation.
- Analysis no-evidence / limited-evidence and Tutor unavailable/degraded state.
- Desktop 1440px and mobile 390px: collapse/expand sidebar **and assert actual content width changes**, Focus Reading hide/restore topbar and rail, Contents overlay, Escape, browser fullscreen denial, no horizontal overflow, title wrapping, keyboard navigation, ARIA, proper logo loading, source page navigation, revision print view and visual blocks.
- Read-only GET purity, lazy Flask import/startup, no regression in Notes vs Obsidian, existing Assessment Intelligence, Home/Analysis, Knowledge Reader and Tutor focused tests.

Report exact commands, output and CI URLs; separate executed validation from unexecuted checks. Run whole pytest suite, static/compile checks, DB integrity/FK checks, diff check and protected-file hashes where applicable. If full suite is expensive, still run it before claiming completion. If CI cannot be enabled, supply workflow plus demonstrable local tests and honestly mark CI unverified. Avoid manual Windows validation unless a residual issue cannot be tested headlessly; provide minimal deterministic handoff for that issue only.

## 10. Acceptance conditions

Do **not** claim feature complete unless all applicable criteria are demonstrated:

1. Real ANVAYA logo shows in Learning Studio (desktop/mobile/Focus states, no "A" placeholder).
2. Main content becomes materially wider when nav is collapsed, and Focus Reading removes distractions without cutting off notes; mobile works.
3. Courses→units/topics→modules hierarchy works with 72 synthetic presentations and small landing page.
4. All original 20 pilot pages are accessible; each module lesson links back to its source; unresolved semantic extraction is explicitly flagged; full content and revision are separate views.
5. Learn, Visualise, Practice, Day-before-exam Revision, My Weak Questions and Original Source work in actual Flask app, not only the standalone HTML mockup.
6. Safe versioned module package import with data validation, source-hash/locator checks and non-destructive revision behavior.
7. Incorrect answers persist after a correct retry/reopen, server-derived grading is authoritative and no official grades/mastery are silently changed.
8. Analysis reports only grounded low-stakes signals. Tutor receives source-grounded context through a reviewed read-only contract where safe, otherwise a fully documented non-deceptive gated integration path.
9. Synthetic fixture gates are green; Ubuntu/Windows CI and headless UI tests are recorded to the extent actually executed; production academic data unchanged.
10. Scope and diff reviewed; feature branch committed and pushed only after green gated work. No merge to main.

## 11. Exact deliverables and handoff

Create, as appropriate within repository conventions:

- `ANVAYA_LEARNING_STUDIO_V1_IMPLEMENTATION_REPORT.md`: baseline/current commit, reused architecture, exact changed paths, feature demonstration, route URLs, screenshots or browser test evidence, limitations and exact test outcomes.
- `ANVAYA_LEARNING_STUDIO_IMPORT_SCHEMA.md` and machine-readable schema/validator, including safe pilot adapter and source-fidelity statuses.
- `ANVAYA_LEARNING_STUDIO_EVIDENCE_CONTRACT.md`: event identity, idempotency, grading authority, topics, Analysis/Tutor read-only boundary, historical revision behavior.
- `ANVAYA_LEARNING_STUDIO_WINDOWS_HANDOFF.md`: **minimal** exact Windows commands only if needed; otherwise explain how CI/headless checks replace manual validation.
- `ANVAYA_LEARNING_STUDIO_FUTURE_AUTOMATION.md`: fully automatic PPT/PDF conversion, rich slides, visual fidelity verification, authorised Moodle ingestion and eventual source-to-lesson AI production plan (separate from V1).
- Working feature code, deterministic tests, fixtures, any isolated migration(s), optional screenshots/recordings, CI configuration, Git branch/commit and PR URL if a PR is permitted. Do not open or merge a PR if repo policy forbids it; report the branch instead.

Final response must clearly distinguish **DONE / VERIFIED**, **IMPLEMENTED BUT UNVERIFIED**, **DEFERRED**, and **BLOCKED**. State the real branch, HEAD, commit(s), pushed state, routes, imports tested, preserved data, exact test counts and failed checks. Give 5–10 minute local usage steps. **Do not claim completed work that was not actually performed.**

**Start now by inspecting the current repository and attached V3 pilot, then implement the first safe vertical slice. Do not stop at analysis or request another design approval.**
