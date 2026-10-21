# Architecture V2.4 implementation plan

Goal: extend the merged source/practice/evidence/planning journey with a readable lesson, exact-topic contracts, source-bound offline assistance, and review-first conversion.
Architecture: extend existing Learning and academic read projections; all persistent writes remain with existing owner APIs. No migration, provider call or installed-data operation.
Spec: SOURCE_SPEC.md (user supplied execution instructions).
Execution: inline implementation, followed by independent engineering, academic and accessibility reviews.

## Constraints and review focus
- Preserve four original private IKS identities; public absence stays BLOCKED.
- No cross-owner atomicity claim; versioned topic identity uses canonical IDs, never display names.
- Stale/replayed context, foreign question identity, malformed clocks, malicious source instructions, unsupported conversion and missing sources fail closed or explicitly require review.
- Assistance preview is stateless and read-only; canonical Tutor session persistence remains blocked until immutable module bindings are supported.
- Synthetic stores only; original source routes and startup preserved.

## Tasks
1. [x] P0: add versioned canonical topic reference and explicit cross-owner freshness/clock semantics; test identity collisions, unknown mappings, reversed event clocks and stale revisions.
2. [x] P1: build bounded deterministic Tutor consumer from frozen owner data with explicit POST, signed context, exact question/event identity, hint/concept/example/self-check ladder. Never expose unrequested answer keys or persist fabricated assistance history.
3. [x] P1: improve actual Learning Studio lesson typography, outline/checkpoints and source navigation; connect practice and evidence to source-bound help. Preserve original owner reader and record semantics.
4. [x] P1: implement isolated PDF-to-draft source-map preview, review-first and never auto-published. Return exact page order/hash/extraction method and unknown fidelity. PPTX conversion deferred visibly.
5. [ ] Integration: test source → wrong practice → exact offline help → self-check → explicit task → available-window preview → draft → approval → effort → updated evidence; responsive screenshots at 390/768/1366, no-JS and adversarial paths.
6. [ ] Delivery: full regression, Node/compile; dedicated Ubuntu/Windows exact-head CI, independent reviews, documented boundaries and V2.5 handoff; push branch and open PR without merge.

## Execution ledger
- Verified main bf3ca0e7eb1bf6f51d900ab4a6cc69ca83a61eae; PR31 merged. Other open branches preserved.
- Existing checkout EOL normalization restored two historical files without substantive changes.
- User's source explicitly authorizes implementation and delivery; no additional design permission loop.

- First focused P0/P1 run after review fixes: 63 passed; Node 24 passed, compile/whitespace clean. Native browser/full exact-head acceptance still pending.
- Independent reviews exposed revision page misattribution, subject-specific hint assumption, reverse assessment clocks, text-size inheritance, focus parameters, lesson selection and staged routing; fixes documented in IMPLEMENTATION.md.
