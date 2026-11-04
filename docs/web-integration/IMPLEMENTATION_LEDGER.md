# ANVAYA web implementation ledger

## Scope and recovered sources

Baseline main: `7ff6b48a2d61f999896f1b2da0a302579c05a95f`. Historical audit and implementation handoff were read before source work. Attached 4 November web master prompt governs scope. `BRANCH_RECOVERY.json` records refreshed ancestry for every open PR: #57/#55/#52/#51/#49/#44/#43/#41/#39/#35/#13/#9 are already ancestors; #27/#29 diverge and were not blindly merged into unrelated academic authority. Web changes from #61/#68/#65 were recovered with three-way application and no text conflicts; newer #66/#67 work is preserved.

Local recovery commit: `df34c7a`. Local authoring/lifecycle commit: `3e9d1eb`. A final focused integration commit adds identity-boundary repairs, real-source authoring UI, security/failure tests, docs and synthetic screenshots. GitHub transport may assign different commit IDs; tree identities are checked during publication. No private academic data is committed.

## Implemented stages

| Stage | Concrete change | Data/rollback boundary | Evidence |
|---|---|---|---|
| A | Audit crosswalk, refreshed branch ancestry, selected reuse | Main unchanged during development | ASTRA_AUDIT_COVERAGE.md; BRANCH_RECOVERY.json |
| B | Shared streaming backup V2, V1 restore, tombstones, staged swap, Windows fsync fix | Additive native migration with verified backup; no data reset | test_library2_backup_streaming.py; test_library2_legacy_migration.py; web lifecycle tests |
| C | Semester/year/subject/folders, templates, batch files, duplicate decisions, Trash/Undo, favorite/recent, scoped search, original viewers | Immutable original hashes; protected roots; permanent deletion reference checks | file-manager/format/routes and actual Chromium suites |
| D | Leased source queue, canonical chunks, coalesced lexical generation, citations; pinned course identities; empty generation | Exact source/hash/version, idempotent checkpoints; stale sources fail closed | test_library2_tutor_bridge.py; native concurrency tests |
| E | Four-lecture authoring, explicit lecture order/manifest, exact original snapshots, derived companion, friendly editor, optional provider consent, structural/human QA, immutable revisions, portable V2 ZIP | Existing Studio DB/revisions; original assets verified; no notebook/code execution | test_multilecture_web.py; real Chromium journey; legacy ZIP tests |
| F | Server-graded inline questions; formal filtered library; explicit reviewed canonical topic link; consent-aware results/schedule/completion metadata | Read-only canonical Assessment projection; no grades/mastery writes | real formal quiz submission/evaluation; canonical byte-equality assertions |
| G | Finish/Reopen with native form, idempotency, save failures, Continue Learning | Existing reading_events only; revision isolation | test_continue_learning.py; test_multilecture_web.py; Chromium restart |
| H | Tutor full width/branding/rename; content-first layout; inert viewers; dialog keyboard focus; backup/metadata ENOSPC; local performance | Existing Notes/Planning/Obsidian/Assessment owners retained | focused gate; Node contracts; canonical full regressions |
| I | Local run/recovery guides, source-tree publication, exact-head and merged-main web checks | No public deployment or Android release | PR checks and attached source.json / canonical validation artifacts |

## Actual local verification

- Isolated Python 3.12 environment installed from tracked requirements. Full runtime dependencies were installed before the broad regression run.
- Initial recovered core run: 84 passed, two stale Tutor assertions corrected (obsolete selector and printable escapes instead of control characters).
- Focused web gate: **166 passed, zero skips**, in 98.87 seconds. Includes Library data safety and migration, real Chromium Library/Tutor, portable imports, explicit launch ownership, four-lecture authoring and canonical assessment feedback. Later focused additions separately passed: keyboard focus/ESC and ENOSPC/metadata failure recovery.
- Tutor Chromium: **34 passed**. Baseline Library Chromium captures: **6 passed**. Full new synthetic journey: **4 passed**, covering 390/768/1366 CSS-px and 200% CSS rendering.
- Broad Python run: **3,510 passed, 397 skipped, three failures**. Browser gates were not enabled in that diagnostic; the local JDK was unavailable. Failures were stale backup tombstone/UI text assertions plus a topic-ID assertion independently reproduced on unchanged baseline main. All three were corrected with meaningful current-contract assertions; no tests were deselected or weakened to ignore a failure.
- Additional read-only characterization errors during development came from uncommitted new source files being absent in the Git-based isolated copy. After committing the source, characterization + focused stage checks passed (41 checks). This was not a production migration failure.
- A launcher read-only test observed authorized asynchronous derived-index output. Its startup worker is explicitly quiesced before snapshotting, so the GET invariant is tested independently. The launcher suite passed after isolation repair.
- Node: **30 passed, zero skipped**; all web JavaScript files passed syntax checks. `pip check` and `git diff --check` passed.
- Exact final source acceptance is performed again in Ubuntu and Windows CI. This ledger does not predict CI outcomes. The PR's check runs and source.json artifacts are authoritative for the checked commit. Merge remains prohibited until relevant gates pass.

## Measured performance

See LOCAL_BENCHMARK.json, generated by `python scripts/web_integration_benchmark.py --browser --output <outside-repo-file>`.

| Measurement | Samples | p50 | p95 | Provisional target |
|---|---:|---:|---:|---:|
| Warm rendered folder, 1,000 files / 100 folders | 60 | 5.685 ms | 6.805 ms | ≤500 ms p95 |
| Scoped metadata search | 60 | 3.569 ms | 5.204 ms | ≤300 ms p95 |
| Trusted click to next frame with import dialog open, 390×844 | 20 | 12.4 ms | 13.4 ms | ≤100 ms |

A **123,207,680-byte** synthetic payload (>100 MiB) streamed through verified export and staged restore with matching SHA-256. Peak traced Python allocations during export were **4,705,793 bytes**. Tracemalloc does not measure all native RSS. Hardware was the shared Linux executor, Python 3.12.14; these are warm local web measurements, not physical-phone or Windows latency claims.

## Preserved functionality and limits

The canonical full gate covers existing Notes/nesting/focus/media, Obsidian, Planning, Assessments and Tutor. No academic authority promotion, hidden planner write, Android emulator, Java/Gradle modification, APK release or public hosting is part of this task.

Optional OCR/Office conversion and live paid-provider correctness remain dependency/manual boundaries; the app truthfully retains originals and offers local manual authoring. Source snapshots in a portable package are bounded separately from Library's 100 MiB per-file cap. Existing external source roots and unavailable phone records require their actual user-owned assets. No assertion claims those private records were migrated.


## Final contention follow-up

A source review found canonical SQLite publication occurring while the native metadata transaction was held. Publication now commits a durable extracted checkpoint, releases the native lock before waiting on the canonical owner, and rechecks lease/hash/generation/metadata revision before completing the native receipt. Retrieval independently excludes stale generations throughout. Added real Flask/SQLite contention and disable-after-canonical-commit regressions.

The local execution environment became unavailable after the initial source publication. This follow-up and the final Library→Studio handoff are verified by exact-head GitHub Ubuntu/Windows web/canonical checks, not claimed as a new local pass.

Clean server shutdown during extraction now keeps the job pending with its durable checkpoint, instead of treating cancellation as a permanent parser failure. A restart regression verifies the same ID/bytes become Tutor-ready after reopening.

### Final CI follow-ups

- V3 source excerpts accept literal comparisons and code as escaped inert text; teaching/question and legacy package markup guards stay strict. New tests preserve original bytes and prove script-like literals remain escaped in the reader.
- The A–K browser contract measures the compact composer's available row width after Tools/Send and requires the transcript to end above it. This replaces the superseded full-form textarea-width assumption without changing the selected layout.
- Final local execution is unavailable; these final changes require current-source GitHub checks. Earlier cancelled runs do not constitute acceptance.

### Windows acceptance repairs

Windows exposed SQLite fixture contexts that committed without closing OS handles, plus a real rapid Save & Next / Submit timing edge. Fixture transactions now close explicitly; the runner disables final submission during authoritative actions and restores controls after a failed save. The end-to-end journey waits for Save & Next navigation before submitting. A delayed-write Node regression verifies the control state and failure recovery.

### Resumed verification and final geometry correction

At source `7468d5288d010cc6c0c9c481d30a79d0cbe46572`, focused web CI run `41821734549` passed **176 checks with zero skips on each of Ubuntu and Windows**, including the full lecture-to-formal-assessment browser journey. Canonical run `41821734666` executed 3,932 cases on each platform: its only 42 failures shared the Tutor geometry calculation; all other canonical categories passed. Four named external private-fixture checks remained explicitly unavailable.

The geometry calculation counted the absolutely positioned accessibility label as a visible flex control and allocated it a nonexistent gap. It now measures only controls participating in layout; input-width, containment and answer/composer separation assertions remain mandatory. After the local environment returned, **all 43 A–K Chromium checks passed in 91.73 seconds**, plus 26 multi-lecture/background-route checks and 11 Assessment runner JavaScript checks. The final source must still pass fresh GitHub Ubuntu/Windows gates before merge; earlier failed or cancelled runs are not accepted as passes.
