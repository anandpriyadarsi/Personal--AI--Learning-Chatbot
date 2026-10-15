# Learning Studio review and rulings

Independent read-only review completed on the full feature delta. No unresolved critical/important findings remain after repairs.

Fixed with RED→GREEN regressions:
- Registered sources rejected lexical/intermediate symlinks before canonical resolution.
- Missing-module POSTs never initialize an empty store.
- Removed/reintroduced questions cannot reuse an old revision with changed content.
- Malformed locator, option, block, fidelity and optional-preview types produce clean validation errors.
- Source-loader failure between preview/publish is a safe503 without publication or private path leakage.
- A ZIP with a declared two-byte entry hiding an eight/forty-megabyte deflate stream is rejected using bounded inflation. Corrupt deflate becomes a clean validation error.

Deferred minors from independent review:
- Modules mapped to a later-removed course remain available by historical URL, but their cards are not grouped under an unavailable-course bucket.
- Contents/view navigation reloads the reader and loses the transient Focus Reading state; existing sidebar preference remains optional browser state.
- Weak-question Review related lesson opens Learn at its beginning; the precise Source page links still navigate to the referenced page.

Rulings:
- The user's master instruction explicitly authorised choosing the additive design and executing inline, so no extra design/plan approval or integration menu was requested. No merge is authorised.
- An unrelated red production-dependent Tutor gate does not block independently green Learning Studio slices. The whole suite remains honestly red and the same baseline failures are recorded; no test was edited, weakened or excluded from the whole-suite runs.
- The supplied pilot original checksum disagrees with its manifests. Strict adapter rejection stands; no checksum substitution or imported-pilot claim. A synthetic twenty-page module verifies the independent reader capability.
- Legacy course/topic read models do not reliably expose stable topic IDs or academic year. Optional topic_id is only accepted if supplied by the actual catalogue; unknown year remains unspecified.
- /agent cannot consume source-grounded LearningEvidenceSummary. Tutor action stays disabled with an explicit reason; no reasoning/orchestration changes were made.
- Scratch expiry invalidated the initial worktree metadata. A dedicated checkout was rehydrated from the SAME verified base without changing feature content. The source snapshots, commits and full-suite comparison remain based on f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf.

## V1.1 independent review

Read-only reviewer compared the V1.1 delta to pushed9ed585c. No critical source-validator, answer-key, cross-module or production/Tutor boundary defect found. Findings: explicit Focus exit/history precedence; missing-case/new-skip regression gate; erased-course Back link; mixed missing semester labels. Follow-up review found collapsed-sidebar reload consistency and external failure→skip acceptance. All six findings received fail-first tests and fixes. Reviewer confirmed no remaining important findings in the repairs; local final actual-browser feature suite75/0failed/0skipped. Reviewer's environment could not launch Chromium; primary harness ran actual browser cases, including history and collapsed reload. Full final delta has no new failures/missing cases/skips and retains the16 unchanged baseline failures.

Final-tip Windows hydration race: reviewer verified Playwright1.51 click waits navigation commit while inner_text reads first matching static DOM. Deterministic delayed-init RED→GREEN adds one test; exact Focus label/ARIA assertions now retry after DOMContentLoaded, without production changes or weaker requirements. Local final suite76/0failed/0skipped.
