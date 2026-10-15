# Learning Studio V1.4 implementation and acceptance boundaries

V1.4 integrates the verified V1.3 reader with current-main B1/B2 read safety in the dedicated `feature/learning-studio-v1-4-integration-2026-10-15` branch. Main and the old V1.3 branch remain unchanged. See `INTEGRATION_DIFF_AUDIT.md` for ancestry and shared-file ownership.

## Implemented quality improvements

- Learn keeps one selected lesson, with an expandable exact original-page preview/text and one related lesson-scoped practice link. Full-screen/Focus, collapsing Contents, keyboard/history/storage-denial support and explicit All modes are retained.
- Full Exam Revision preserves every companion block and includes every authored lesson concept in expandable source-ordered supplements. Print includes them all. Already-loaded notes remain available offline; no-JS disclosure and print work. This is not an offline caching/download subsystem.
- Quick 5/15-minute modes contain at most 4/12 authored recall cards. Without cards they explicitly report unavailable and link to Full Revision, rather than displaying unbounded notes under a short time promise.
- Each selected card explains its priority: explicit revisit, pages linked to recorded misses, authored misconception, fidelity-review cue, then authored order. These are deterministic review suggestions, not exam predictions or a mastery diagnosis.
- Visible scope summaries disclose omitted blocks, pages without companion citations and author-reported page-review uncertainty. Physical pages/previews/text, cited pages and semantic accuracy have distinct labels.
- Equal-valued blocks keep their original distinct indices; saved recall state is scoped to immutable module revision and block index. New revisions preserve prior history. Activity DOM IDs include rendering scope, avoiding collisions between companion and lesson supplements.
- Revision budgets, source links, lesson detours and return-to-question paths preserve the exact pending question. Source navigation uses the cited lesson independently of stored engagement identity.
- Preflight adds mechanical page-number/locator, possible truncation, cross-lesson citations, verbatim-extract and visual/math material cues. Missing companion citations remain unresolved. The report projects at most 100 warnings and truthfully reports its total/truncation. No package/source checksums are repaired.
- A stale or deleted live course/topic mapping visibly remains unknown. Historical immutable mappings are retained. No new canonical attribution is inferred.

## Retained authority and source boundaries

Server-graded low-stakes MCQs retain their private keys until a valid attempt; wrong→correct remains recovered-needs-recheck. Recall, reflection, reveal and reading are ungraded self-report, separate from official assessment performance. Existing read-only Analysis signals and versioned manual Copy/Download Tutor review briefs remain available. Automatic Tutor consumption stays BLOCKED because no compatible exact immutable consumer/source/session contract has been established.

No Assessment Studio/Coding Helper implementation, Tutor provider/session, active B3/Gate C0 branch, production registry, academic data, migration or official grade is changed. Original source files, question lists, immutable source digests and review ledgers are not rewritten. Private teacher material is absent from the public diff and hosted CI fixtures.

## Acceptance matrix

| Acceptance area | Evidence / disposition |
|---|---|
| Verified V1.3 base and prior hosted CI | Exact `6e520035…`; Ubuntu/Windows run `38578508031` successful |
| Current-main integration | Explicit conflict-free merge; imported B1/B2 code unchanged; characterization/read-safety gates |
| Sidebar/Focus/keyboard/history/storage denial | Retained real Chromium journeys rerun |
| Mobile/tablet/desktop layout | Functional journeys and synthetic screenshots at 360, 390, 768, 1024, 1366, 1536, 1920 |
| Selected source + related practice | New V1.4 browser test on all seven widths; no preattempt key/explanation exposure |
| Full notes/lesson concepts/print/no-JS/offline loaded DOM | New complete-content, print-width and no-JS/offline browser assertions |
| Bounded quick review and honest omissions | Domain/route/browser tests, including no authored cards and priority reasons |
| Exact question/source/lesson return | Unit regression and real Chromium budget→source→lesson→question detour |
| Durable equal-card state and revision isolation | Idempotent event/reopen/new-revision regression, retained persistence tests |
| Source safety/hash/ledger/unsafe import | Retained hard-negative tests plus mechanical diagnostic regressions; no semantic certification |
| Private pilot local structural acceptance | Available original bytes hash matches; 20 lessons, 31 questions and 12 cards retained; all lesson GETs and source download pass in disposable store |
| Private pilot independent semantic review | NOT VERIFIED; all 20 pages retain needs-review status |
| Private original-source Windows acceptance | NOT RUN; public hosted Windows uses synthetic fixtures only |
| Installed production source/data authority | NOT VERIFIED; reference source ID is not proof of installed registration |
| Read-only Analysis/manual Tutor producer | Existing versioned and no-write tests retained; no official grade mutation |
| Automatic Tutor consumer | BLOCKED by exact-source/mapping/session contract and separate Tutor ownership |
| Independent review | Separate engineering/security and learner/UX reviews; reproduced findings fixed with fail-first regressions |
| Raw whole suite | Exact baseline/feature test IDs and exit codes retained; a regression-delta pass is not a raw-suite pass |
| Exact final-SHA Ubuntu/Windows | Final hosted job results and artifacts are recorded in the private exact-SHA acceptance evidence after publishing; do not infer success from this static report |

## Verification and release handoff

Local feature and focused tests use a disposable environment with pinned dependencies. Final hosted acceptance runs `python scripts/learning_studio_validate.py --scope all --base 6e520035b6b9ccf8e14c176b35b43e384c95d103 --output learning-studio-evidence` on Ubuntu and Windows. It requires real Chromium, forbids internal skipped cases and retains exact raw full-suite failures. Only this feature-branch push triggers the Learning matrix; no PR or duplicate workflow dispatch is created.

Zero mandatory manual Windows screenshots or environment rebuilding. Optional, in an already-configured environment, one synthetic launch command is `python -m personal_learning_assistant.learning_studio.demo --directory ../learning-v14-disposable-demo`. Open its displayed `/learning` URL; select a lesson, collapse Contents, use Focus, attempt a practice question, follow Source and return, then open Full Revision and Print. This takes about 3–5 minutes and uses a disposable synthetic store, not production academic data.

## Remaining work and next phase

The next most valuable phase is **private source-and-semantic acceptance**: verify the installed original source ID/hash and permitted roots using safe local redacted checks, then review missing/uncertain concepts, diagrams, equations and question support against the preserved source. Keep all unresolved page/element claims unresolved until actually reviewed. No private DB or keys need uploading.

A separate Tutor-owned explicit-click consumer requires the documented immutable source/owner/mapping/session contract and its scenario gates. It is not authorized by a green Learning Studio producer test. Assessment Pause/Paper, B3 provenance and Gate C0 remain separate workstreams. Main merge/deployment require a subsequent integration/release decision; this branch is not a production rollout.
