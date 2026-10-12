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
