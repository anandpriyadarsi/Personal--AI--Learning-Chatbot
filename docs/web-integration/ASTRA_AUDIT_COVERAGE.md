# Astra audit coverage — web integration

Baseline main: `7ff6b48a2d61f999896f1b2da0a302579c05a95f`. Historical audit: 30 October 2026, 435 lines. Read alongside its 275-line implementation handoff and the attached 4 November web master prompt.

This is a live evidence crosswalk. Candidate code is not passing evidence. No installed private data is available; synthetic tests never certify the user’s existing databases.

## Recovery and conflicts

- PR #61 `594931a35a0ade96d8d5a1e5d18440ab7c419933`: selected shared Python/web/tests/docs diff recovered with three-way application; Android Java/Gradle/emulator/release changes excluded. The shared `android_backup.py` filename denotes the reused backup engine, not APK work.
- PR #68 `3c08caa455c486beea3e355736e2450c9ee21d2a`: all seven web/progress/test files recovered.
- PR #65 `3a33cafaaf17f39aa36ffce77ece3c0de3e99ac8`: all eight web rename/layout/test files recovered.
- All three applied cleanly without text conflicts. Newer PR #66/#67 portable ZIP and course/topic mapping remain in place. Older ancestor branches require no repeated integration; diverged #27/#29 do not authorize unrelated authority changes.

## Findings

| ID | Requirement | Existing implementation | Present status | Acceptance evidence/action |
|---|---|---|---|---|
| F01 | Native→canonical→retrieval bridge | native_tutor_bridge.py; retrieval_source_repository.py | implemented candidate; verification pending | test_library2_tutor_bridge.py |
| F02 | Streaming verified backup/restore | android_backup.py (shared Python backup engine) | implemented candidate; verification pending | test_library2_backup_streaming.py |
| F03 | Original viewer/legacy source adapters | native_library.py; native_legacy_sources.py | implemented candidate; verification pending | test_native_library_routes.py |
| F04 | Explicit native/canonical identities | native_legacy_sources.py; native_library_migrations.py | implemented candidate; verification pending | test_library2_legacy_migration.py |
| F05 | Web request concurrency | native_library.py; native_tutor_bridge.py | implemented candidate; verification pending | test_native_library_routes.py |
| F06 | Destination-aware duplicate decisions | native_document_library.py | implemented candidate; verification pending | test_library2_file_manager.py |
| F07 | Real routed course catalogue | native_academic_files.py | implemented candidate; verification pending | test_library2_file_manager.py |
| F08 | Academic hierarchy and file manager | native_academic_files.py; native_academic_files.js | implemented candidate; verification pending | test_library2_file_manager.py |
| F09 | Android release/signing | No changes authorized | not applicable—Android-only | not applicable—Android-only |
| F10 | Honest extraction capabilities | native_document_extraction.py; native_document_formats.py | implemented candidate; verification pending | test_library2_formats.py |

## Audit sections and historical handoff

| Section | Coverage/action | Status |
|---|---|---|
| B | Keep original-file engine, canonical Courses/Assessment ownership; no second silo | candidate / acceptance pending |
| C | Single compact file manager, original viewer and secondary source links | candidate / acceptance pending |
| D | Five real subjects plus Add subject; format/capability truth | candidate / acceptance pending |
| E | Stable namespaces/hashes, outbox, bounded extraction, retrieval generations | candidate / acceptance pending |
| F | Semester→subject→folder, templates, batch import, Trash, Recent/Favorites | candidate / acceptance pending |
| G | Backup, provenance and local processing before optional OCR/preview enhancements | candidate / acceptance pending |
| H | Additive migration, missing-original tombstones, legacy IDs and rollback | candidate / acceptance pending |
| I | Verified stages recorded in IMPLEMENTATION_LEDGER.md | candidate / acceptance pending |
| J | Every scenario mapped below; exact source gates before merge | candidate / acceptance pending |
| K | No installed private data, sixth subject or vendor conversion capability assumed | candidate / acceptance pending |

Historical handoff sections 0–13: identity/data safety, owners, supported formats, file operations, templates, processing, migration, local UX and test requirements carried forward. Android picker/SAF/FileProvider/WorkManager/signing/APK sections intentionally excluded; Ubuntu/Windows, byte integrity and rollback remain mandatory.

## All 28 behavioral scenarios

| # | Scenario | Web disposition and evidence target | Present status |
|---|---|---|---|
| 1 | Upload integrity | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 2 | Format matrix | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 3 | Nested folder lifecycle | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 4 | Rename/move/copy/delete | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 5 | Duplicates | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 6 | Existing migration | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 7 | PDF handoff | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 8 | PPT/PPTX handoff | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 9 | No viewer/cancel/return | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 10 | Search | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 11 | Background extraction | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 12 | Scanned/mixed PDFs | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 13 | Tutor grounding | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 14 | Offline | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 15 | Low storage | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 16 | Restart/reboot | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 17 | Security | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 18 | Slow device | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 19 | Regressions | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 20 | API31/API35 | Android-only assertions excluded; web exact-source/Linux/Windows provenance required | acceptance pending |
| 21 | Ubuntu/Windows | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 22 | Release/install | Android-only assertions excluded; web exact-source/Linux/Windows provenance required | acceptance pending |
| 23 | Backup/restore | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 24 | Consent/privacy | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 25 | Templates | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 26 | Index mutation races | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 27 | Stale/missing original | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |
| 28 | Accessibility | Adapt to temporary DB/files + real Chromium; see test suites and ledger | acceptance pending |

## New requirements

| Requirement | Candidate / action | Status |
|---|---|---|
| Multi-lecture topic authoring | Implement ordered manifest, source-linked authoring, review rubric, immutable publish | missing |
| Inline quick checks | Reuse PR #68 server grading, no early key serialization, retry and no-JS | implemented candidate |
| Formal assessment handoff/results | Canonical filtered tests; implement consent-aware read-only weak-topic bridge | partial |
| Durable Finish/Continue | Reuse reading_events; verify restart/revision/save failure and reopen | implemented candidate |
| Tutor layout/rename | Reuse PR #65 with CSRF and persistent history | implemented candidate |
| Web lifecycle | Move migration/bootstrap out of GET requests into explicit local startup | partial |
| Original viewers | Secure PDF/image/inert text; Office original download | partial |
| Documentation/demo/performance/accessibility | Reproducible synthetic journey, screenshots and measurements | pending |
