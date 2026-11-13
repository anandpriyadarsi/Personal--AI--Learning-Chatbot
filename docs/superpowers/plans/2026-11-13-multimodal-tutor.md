# Multimodal Tutor Phase 1 Implementation Plan

Goal: Extend existing Library and Tutor with selected image/page evidence and timestamped transcripts with supplied frames.
Architecture: Native owner stores optional additive metadata; existing leased jobs publish compatible locators into canonical retrieval. Existing Tutor saves immutable citation snapshots with exchanges. Provider guard defaults to zero spend and separates extraction from answering.
Spec: docs/multimodal/approved-blueprint.md (approved by submission of implementation prompt).

Constraints: Local web only; flags default off; no personal data activation or paid calls; preserve originals and independent owners. Optional media decoding deferred pending Windows/codec evidence.

Review focus: cross-course identical bytes; source replacement in flight; expired/revoked consent and unknown billing; malformed parser inputs; historical citations after replacement/deletion.

- [x] WP0: Focused baseline, synthetic owners and backup/restore harness.
- [x] WP1: Strict source/locator contracts, explicit backup-first activation, durable scoped permissions/reservations and citation snapshots.
- [x] WP2: Tests first for selected raster/PDF processing, user reviews, source-fenced publication and shared PPTX order; integrate existing queue.
- [x] WP4: Direct evidence selection, guards on every provider/retry, atomic saved snapshots and freshness.
- [x] WP5A: Protected scope-review/status/cancel/retry and Tutor handoff in existing Library reader.
- [x] WP3B/WP5B: Bounded transcripts, explicit frame manifests, exact interval selection and cue viewer.
- [x] WP6: Relevant regressions, real browser checks, synthetic evaluation, backup/rollback documentation, review and conditional integration.

Each implementation step: add boundary tests, observe failure, implement, run focused tests, commit. Keep progress and actual commands in docs/multimodal/validation.md. No generic full suite/Android matrix per approved prompt. No live model quality claim from fake-provider results.

Execution evidence: docs/multimodal/validation.md. Optional C, Windows and live educational accuracy remain explicitly unverified/deferred. The approved prompt authorized inline execution and conditional GitHub integration; no additional approval menu was inserted.
