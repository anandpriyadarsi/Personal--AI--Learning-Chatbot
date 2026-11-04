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
| F01 | Native→canonical→retrieval bridge | native_tutor_bridge.py; retrieval_source_repository.py | implemented; local focused acceptance | test_library2_tutor_bridge.py |
| F02 | Streaming verified backup/restore | android_backup.py (shared Python backup engine) | implemented; local focused acceptance | test_library2_backup_streaming.py |
| F03 | Original viewer/legacy source adapters | native_library.py; native_legacy_sources.py | implemented; local focused acceptance | test_native_library_routes.py |
| F04 | Explicit native/canonical identities | native_legacy_sources.py; native_library_migrations.py | implemented; local focused acceptance | test_library2_legacy_migration.py |
| F05 | Web request concurrency | native_library.py; native_tutor_bridge.py | implemented; local focused acceptance | test_native_library_routes.py |
| F06 | Destination-aware duplicate decisions | native_document_library.py | implemented; local focused acceptance | test_library2_file_manager.py |
| F07 | Real routed course catalogue | native_academic_files.py | implemented; local focused acceptance | test_library2_file_manager.py |
| F08 | Academic hierarchy and file manager | native_academic_files.py; native_academic_files.js | implemented; local focused acceptance | test_library2_file_manager.py |
| F09 | Android release/signing | No changes authorized | not applicable—Android-only | not applicable—Android-only |
| F10 | Honest extraction capabilities | native_document_extraction.py; native_document_formats.py | implemented; local focused acceptance | test_library2_formats.py |

## Audit sections and historical handoff

| Section | Coverage/action | Status |
|---|---|---|
| B | Keep original-file engine, canonical Courses/Assessment ownership; no second silo | implemented / preserved; see evidence below |
| C | Single compact file manager, original viewer and secondary source links | implemented / preserved; see evidence below |
| D | Five real subjects plus Add subject; format/capability truth | implemented / preserved; see evidence below |
| E | Stable namespaces/hashes, outbox, bounded extraction, retrieval generations | implemented / preserved; see evidence below |
| F | Semester→subject→folder, templates, batch import, Trash, Recent/Favorites | implemented / preserved; see evidence below |
| G | Backup, provenance and local processing before optional OCR/preview enhancements | implemented / preserved; see evidence below |
| H | Additive migration, missing-original tombstones, legacy IDs and rollback | implemented / preserved; see evidence below |
| I | Verified stages recorded in IMPLEMENTATION_LEDGER.md | implemented / preserved; see evidence below |
| J | Every scenario mapped below; exact source gates before merge | implemented / preserved; see evidence below |
| K | No installed private data, sixth subject or vendor conversion capability assumed | implemented / preserved; see evidence below |

Historical handoff sections 0–13: identity/data safety, owners, supported formats, file operations, templates, processing, migration, local UX and test requirements carried forward. Android picker/SAF/FileProvider/WorkManager/signing/APK sections intentionally excluded; Ubuntu/Windows, byte integrity and rollback remain mandatory.

## All 28 behavioral scenarios

| # | Scenario | Web disposition and evidence target | Present status |
|---|---|---|---|
| 1 | Upload integrity | test_native_document_library.py; test_native_library_browser.py | local synthetic acceptance |
| 2 | Format matrix | test_library2_formats.py; test_web_library_lifecycle.py | local synthetic acceptance |
| 3 | Nested folder lifecycle | test_library2_file_manager.py; test_native_document_library.py | local synthetic acceptance |
| 4 | Rename/move/copy/delete | test_library2_file_manager.py; test_library2_tutor_bridge.py; test_native_library_browser.py | local synthetic acceptance |
| 5 | Duplicates | test_library2_file_manager.py | local synthetic acceptance |
| 6 | Existing migration | test_library2_legacy_migration.py | local synthetic acceptance |
| 7 | PDF handoff | test_native_library_browser.py; test_web_library_lifecycle.py | local synthetic acceptance |
| 8 | PPT/PPTX handoff | test_library2_formats.py; test_native_library_browser.py; learning_studio/test_multilecture_web.py | local synthetic acceptance; limits disclosed |
| 9 | No viewer/cancel/return | test_native_library_browser.py; test_web_library_lifecycle.py | local synthetic acceptance; limits disclosed |
| 10 | Search | test_library2_file_manager.py; test_native_library_browser.py | local synthetic acceptance |
| 11 | Background extraction | test_native_library_routes.py; test_library2_tutor_bridge.py | local synthetic acceptance |
| 12 | Scanned/mixed PDFs | test_native_document_library.py (scan/partial states; OCR mocks are not an OCR certification) | local synthetic acceptance; limits disclosed |
| 13 | Tutor grounding | test_library2_tutor_bridge.py; learning_studio/test_multilecture_browser.py | local synthetic acceptance |
| 14 | Offline | learning_studio/test_multilecture_browser.py (zero external browser requests, synthetic provider); local-only extraction | local synthetic acceptance; limits disclosed |
| 15 | Low storage | test_library2_formats.py; test_web_library_lifecycle.py (fsync/metadata/ENOSPC backup failures) | local synthetic acceptance |
| 16 | Restart/reboot | test_native_document_library.py; learning_studio/test_continue_learning.py; learning_studio/test_multilecture_web.py | local synthetic acceptance |
| 17 | Security | test_native_library_routes.py; test_android_backup.py (shared engine); test_library2_formats.py; learning_studio/test_multilecture_web.py | local synthetic acceptance |
| 18 | Slow device | scripts/web_integration_benchmark.py; LOCAL_BENCHMARK.json | local synthetic acceptance; limits disclosed |
| 19 | Regressions | Full canonical Python/browser/Node gate; existing Notes/Assessment/Obsidian/Planning suites | local acceptance + canonical CI gate |
| 20 | API31/API35 | Web source identity in workflow artifact source.json; Android API assertions not applicable | web assertions covered; Android-only assertions excluded |
| 21 | Ubuntu/Windows | .github/workflows/architecture-validation.yml and web-integration.yml; exact PR head and merged main | local acceptance + canonical CI gate |
| 22 | Release/install | Local-only delivery; verified source commits and run guide. APK/install assertions not applicable | web assertions covered; Android-only assertions excluded |
| 23 | Backup/restore | test_library2_backup_streaming.py; test_web_library_lifecycle.py; LOCAL_BENCHMARK.json | local synthetic acceptance |
| 24 | Consent/privacy | learning_studio/test_multilecture_web.py; test_native_library_routes.py; test_library2_legacy_migration.py | local synthetic acceptance |
| 25 | Templates | test_library2_file_manager.py | local synthetic acceptance |
| 26 | Index mutation races | test_library2_tutor_bridge.py; test_native_document_library.py | local synthetic acceptance |
| 27 | Stale/missing original | test_library2_legacy_migration.py; test_native_document_library.py; test_web_library_lifecycle.py | local synthetic acceptance |
| 28 | Accessibility | test_native_library_browser.py keyboard/ESC/focus; learning_studio/test_multilecture_browser.py 390/768/1366 and doubled CSS rendering | local synthetic acceptance |

## New requirements

| Requirement | Candidate / action | Status |
|---|---|---|
| Multi-lecture topic authoring | multilecture_authoring.py; V3 exact original assets/locators; friendly editor, optional consent-bound provider, QA and immutable revisions | implemented; mixed PDF/PPTX/text and ZIP round-trip tests |
| Inline quick checks | Reused PR #68; server grading, no early key serialization, retry and native form | implemented; unit and Chromium acceptance |
| Formal assessment handoff/results | Canonical filtered library; explicit reviewed stable topic link; consent-aware confirmed-result bridge; canonical scheduled/completed metadata | implemented; real canonical quiz submission and read-only score tests |
| Durable Finish/Continue | Existing reading_events; native completion/reopen form; save-before-navigation, idempotency, restart/revision isolation | implemented; unit and Chromium acceptance |
| Tutor layout/rename | Reused PR #65 with CSRF/persistent history and corrected stale tests | implemented; 34 Chromium checks |
| Web lifecycle | Explicit startup migrations/restore; pure GET browse; settings refresh; stable year/term and pinned scope IDs | implemented; web lifecycle/launcher tests |
| Original viewers | Same-origin visual PDF/image; inert escaped text/code; byte-exact Office download; read-only registered-root resolver | implemented; no vendor viewer/conversion certification |
| Documentation/demo/performance/accessibility | LOCAL_WEB_GUIDE.md; recovery guide; four-lecture Chromium journey; synthetic screenshots; latency/streaming benchmark | implemented; platform gate evidence comes from Actions |

## Historical handoff, section by section

| Historical section | Web disposition | Evidence |
|---|---|---|
| Mission and authorization | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 1. Verified baseline to refresh | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 2. Source map and defects to address | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 3. Product scope and course truth | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 4. Data model and ownership decisions | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 5. Original storage, formats and native opening | Original storage and passive-format registry retained. Native Android opening assertions adapted to visual same-origin PDF/image/inert text and Office download. | Code/tests above; implementation ledger; Actions artifacts |
| 6. Automatic extraction, retrieval and privacy | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 7. Mobile interface specification | Academic file-manager UX applied to responsive web; mouse/keyboard/touch, 48px targets and doubled rendering. | Code/tests above; implementation ledger; Actions artifacts |
| 8. Folder templates | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 9. Mandatory backup/migration/rollback | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 10. Test matrix and acceptance gates | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 11. Development phases | Carried into the attached web contract; implemented/preserved through the finding/scenario mappings above. | Code/tests above; implementation ledger; Actions artifacts |
| 12. GitHub and Android release requirements | Keep exact-source GitHub/Ubuntu/Windows gates. Android release/signing/APK requirements excluded by the current task. | Code/tests above; implementation ledger; Actions artifacts |
| 13. Final deliverables | Web source/PR/merge evidence, run/recovery instructions, screenshots and honest capability matrix replace APK delivery. | Code/tests above; implementation ledger; Actions artifacts |

## Additional integration repairs

- Once-pinned namespaced routed→canonical course scopes prevent legacy ID mismatches and reused-code retargeting. No title/filename matching and no canonical Course rewrite.
- Empty lexical generations let Tutor report insufficient evidence after the last active source is removed. Default non-native index-builder empty-input policy is preserved.
- Learning Studio topic feedback requires a reviewed stable canonical link when IDs differ. Reading, informal practice and formal scores retain separate authority.
- Native and registered-original GET routes preserve bytes and expose explicit missing/hash-mismatch recovery states. New startup/index workers are quiesced in read-only characterization tests to avoid attributing authorized background work to a GET.

## Verification boundary

Local evidence includes 166 focused checks with no skips before final keyboard/low-storage additions, 30 Node contracts, real multi-lecture Chromium journeys and the measured benchmark. The first broad run completed with 3,510 passes and three stale assertions; the topic-ID assertion was independently reproduced on baseline main. Those assertions were corrected to the existing/current contract, not suppressed. Final exact-source Ubuntu/Windows canonical and focused web gates are attached to the PR/merge by GitHub Actions; inspect their source.json/validation artifacts rather than inferring success from this document.

No Android app, Gradle/Java/Kotlin, APK release pipeline or emulator work is included. No installed private-data, live paid-provider, optional OCR engine or vendor Office-viewer certification is claimed.
