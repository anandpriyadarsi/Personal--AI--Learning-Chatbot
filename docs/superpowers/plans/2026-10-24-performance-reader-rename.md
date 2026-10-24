# Performance, reader and document rename implementation plan

**Goal:** Implement the owner's supplied master work prompt against main e94b302ddd6d1013a30415662b431fe1f521f3f7.

**Architecture:** Keep Flask server rendering, immutable source-bound Learning packages and the standalone Android host. Read lesson metadata without the PDF BLOB. Use an adjacent, independently identified SQLite display-metadata store for names: canonical academic tables, filenames and package digests remain untouched. Reuse the reviewed-in-progress reader changes from PR45, then test and repair gaps. Android integrates separately on PR44's existing stack.

**Constraints:** No destructive migration, paid service, external AI, academic record rewrite, unsafe HTML/script execution or invented evidence. Cache only packaged static assets with content-versioned URLs. Dynamic academic responses remain fresh. Duplicate display names are allowed and explained; IDs remain distinct. Names are NFC Unicode, 1–160 characters, without control characters, angle brackets or path separators.

**Execution:** The owner explicitly requested implementation through delivery, rather than a further approval/planning exchange. Execute inline within a new checkout and named feature branch.

## Tasks

- [ ] Baseline: existing feature tests; record 45-sample median/p95 and Python allocation for a 12 MB synthetic source. Browser tests and comparative measurements use the same fixture/environment.
- [ ] Performance: add a failing memory regression test for module reads; exclude source_blob from ordinary _row queries, explicitly include only on source/publish paths. Add versioned private static caching, with changed-byte invalidation and no academic-response cache. Test corruption and conditional requests.
- [ ] Rename: add a dedicated metadata repository and service, explicit same-origin/CSRF POST route, dialog with pending/cancel/errors, optimistic conflict handling. Overlay names in bounded Library queries and existing Knowledge metadata. Test original DB byte identity, restart, duplicates, empty/Unicode/special names, search, source identity, disabled feature, symlinks and stale edits.
- [ ] Reader: incorporate PR45 source, verify mobile layout at 320/360/390/412/768/1366 and landscape. Preserve safe structured graphs, images and MathML. Support safe local Markdown anchors without enabling raw HTML or arbitrary URLs. Repair fullscreen focus history/back/exit and media expansion.
- [ ] Verification: focused Python/Node/browser tests, then broader regression. Capture synthetic screenshots and before/after benchmarks. Add Ubuntu/Windows CI with existing pinned dependencies; inspect actual results.
- [ ] Delivery: logical commits, PR with exact evidence, separate Android integration branch based on PR44. Build/install verification only if actual facilities exist. Keep unverified work unmerged and report precise blockers.

## Review focus

1. Rename must not change canonical source bytes, IDs, filename, citation hashes or progress.
2. First Library GET must not create metadata files, reconcile WAL or perform migrations.
3. Optional display metadata must not turn database unavailability into private path disclosure.
4. Fullscreen Back must restore the same chapter and position rather than leave the reader.
5. Imported links must remain bounded to same-module validated sections; scripts and unsafe URLs remain inert.

## Evidence ledger

Baseline: 353 passed, 88 skipped (84 opt-in browser checks, four unavailable private-source cases). Linux container, Python3.12, SQLite3.53.1. Synthetic 12,000,553-byte source: module median8.53ms/p9510.28ms/peak12,013,410 bytes; note HTTP median38.32ms/p9545.92ms/peak12,038,153 bytes. These are server measurements, not device navigation claims.
