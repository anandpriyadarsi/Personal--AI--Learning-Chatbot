# Library 2.0 execution ledger

Contract: docs/library-2/implementation-contract.md
Base: 2e6d35627ae353835cf777e89fc23e994a4a6e44
Branch: feature/library-2-academic-file-manager-2026-10-30

1. Refresh: main and 14 open PRs match audit; no historical PR merges needed.
2. Backup/export/restore: implemented; stdlib/pytest disk round-trips >100 MiB, v1 import, declared missing originals and swap recovery passed. Further crash/low-space injection pending.
3. Hierarchy/lifecycle/migration: implemented additive native schema 2, stable IDs, authority bindings, opt-in templates, Trash and managed legacy source adapter; focused real-DB tests passed.
4. Formats/import/handoff: passive formats, validation, duplicate choices, batch UI and native MIME registry implemented; JVM/installed receiver checks pending.
5. Queue/canonical bridge/Tutor: leased queue and automatic lexical publication implemented; unique fact/hash/line/course retrieval and immediate disabled/trashed exclusion passed. OS scheduling is not added; jobs resume on open.
6. Mobile UI/legacy adapters: semester/folder UI, metadata/content search, lazy destination chooser, favorites/recent/Unsorted/Trash/repair and original-only Android Knowledge view implemented. Browser and installed UI verification pending.
7. Runtime/performance/regressions: real Runtime upload-blocking navigation test RED then GREEN. Focused service/route/backup run 54 passed. Runtime-focused run 38 passed, 1 JDK skip before final source-adapter changes. Full suite must be rerun with staged files and available browsers; initial full run 3302 passed, 17 failed, 142 errors, 378 skipped (not a release pass).
8. Exact-head CI/review/merge/main CI/APK: pending; no release authorized until gates pass.

Environment: isolated clone from an existing exact-main object store. Original checkout has unrelated backup.py/dashboard.py changes and was left untouched. No AGENTS.md in this checkout. pytest/Flask absent; tracked dependency installation attempted but package network timed out. Existing canonical baseline has not been rerun locally. Stdlib unittest is available for dependency-free boundaries; canonical CI remains required.
Pre-flight: backup validator currently requires native schema 1; upgrade it before schema adoption. Queue output must publish exact extraction hash/generation before UI claims Tutor readiness. File placement scope and canonical relations must update together. Native/Python MIME policy must stay aligned. Publisher must remain gated on canonical main plus installed Android checks.

Ruling: keep desktop /library academic projection backwards compatible, while Android /library redirects to the new file manager; explicit Sources & links views preserve queries/history — avoids breaking non-phone read-only workflows — cost if wrong: desktop users must choose Files to enter the academic file manager.
Ruling: retain legacy PDF paths through a verified managed locator instead of copying originals — preserves canonical IDs and Studio constraints — cost if wrong: both managed root policies must remain validated by backup and FileProvider tests.
Ruling: use durable leased app-open scheduling without WorkManager in this version, as explicitly permitted by the contract — the UI discloses resume-on-open — cost if wrong: processing pauses while Android stops the process.
Ruling: new import UI offers local processing after an explicit notice; absent API indexing field still means disabled — preserves old client opt-outs — cost if wrong: clients bypassing the UI need to pass consent explicitly.
Environment update: transient package-network retries succeeded. Workspace maintenance removed external user-site packages/browser cache; recovered tracked dependencies into the current task directory, outside the repo. Browser executable download is still being retried. No JDK/Android SDK exists locally; remote CI is required.
Independent whole-branch reviewer dispatched; findings pending. No merge/release claim.

## Review and candidate gates

PR #61 candidate: 9af88ac21115b29b92d2d499d3c89bc94e9611ef, tree d9d47afbf8ee417da7683d0277bd8a887fd9e68a.
Independent review found a reproducible trash/index publication race, missing restore availability, incomplete native-schema restore checks, a missing Studio native resolver, legacy imports bypassing the owner, overbroad deletion blocking, Copy-to-root ambiguity, missing native Recent and omitted configured future terms. These are being fixed with behavior regressions; no merge accepted on the first candidate.

First candidate remote build/JVM: PASS. API31/API35 actual picker import test: PASS on both; installed smoke stopped at its old exact /library URL assertion after the intended redirect to /library/files. Fix preserves testing the redirect. Smart feedback found 3 real-browser failures from a test issuing page.goto before the rename reload committed; the test now waits for visible renamed content before navigating.

Local verification since review: source-bound retrieval race regression RED→GREEN with 15 retrieval tests; incomplete-native restore RED→GREEN; native-PDF Studio resolver RED→GREEN; unreferenced indexed deletion RED→GREEN; Copy-to-root and deduplicated evidence RED→GREEN; restore-to-Unsorted and original repair tested; local/legacy scope preservation RED→GREEN. Broad revised integration run: 97 passed. Latest core focused run: 51 passed before the final Recent/recovery-restart additions. Fresh complete candidate runs remain required.

Host benchmark (Linux Flask test client, not Android): 1,000 files, 100 folders, 20 warm samples; folder p95 17.91 ms, metadata search p95 5.75 ms, largest HTML response 72,829 bytes, peak process RSS 77,092 KiB. This does not certify M11 latency, RAM or ANR targets.

Browser installation blocked locally by repeated CDN timeouts. Full local run before dependency recovery: 3,330 passed, 14 failed, 129 browser setup errors, 378 skipped. 12 startup failures were from child PYTHONPATH replacing the temporary dependency path; a task-local user-site now supplies dependencies without changing tests. Other failures were the now-fixed retrieval race, route SQL-boundary violation and old release-version fixture. No full-suite PASS is claimed from that run.

Ruling: preserve existing legacy canonical course relations until an explicit physical placement changes scope; direct course code guessing is not used — protects prior course-filtered evidence — cost if wrong: uncertain originals remain Unsorted until assigned.
Ruling: permit deletion of an unreferenced generated canonical mapping, but block actual lesson/history/resource dependencies — avoids keeping every indexed file forever — cost if wrong: source inventory races need installed/regression evidence before release.
Final review: one independent whole-branch review completed; findings are entering one fix pass. No second review is substituted for behavior tests and green full gates.

Latest revised core suite: 81 passed (backup, hierarchy, repair/restart, legacy scope, native Recent, native-PDF Studio loading, canonical retrieval and existing file-manager routes). Revised runtime/architecture/package-scan integration: 97 passed. Source syntax/JS parsing/diff whitespace checks passed. The next remote head must rerun every required gate; earlier candidate Android/JVM evidence is not reused as proof for changed source.

Post-review completion: passive PDF/DOCX/PNG/JPEG/WebP/TXT/Markdown/CSV/Python fixtures verify exact bytes, current Unicode names and native MIME resolution; Python is never executed, unsupported image extraction stays truthful, and failed fsync preserves existing originals. Native/Python registry alignment has JVM coverage in the required Android job. Last device-verified backup and Trash Undo are now exposed; no automatic Trash purge is added.

Frozen revised candidate core command (nine focused files, including supported-format fixtures): 93 passed in 47.40s. JavaScript parse, Python source compilation and git diff whitespace checks passed. Remote candidate f2ff5d287fc5cb97c90077b4e4e412dea2b454a4 is still undergoing checks; final source additionally records verified backup history and exposes Trash Undo, so no result from an older source is treated as final acceptance.

Continuation: candidate 37411178cff2e58155a025305615b3ce16db6668 passed fast browser feedback and Android source/JVM/build. Installed API31 reached the original-source screen and caught a real dictionary attribute error (500); an actual-runtime source-card regression reproduced it RED, then passed GREEN after correction. API35 failed opening-display capture; its evidence shows a Pixel Launcher ANR dialog obstructing the app, so that run is not acceptance. Canonical Ubuntu/Windows were still running when inspected. No merge or APK release is claimed.

Next candidate adds separate-UID PPTX original-byte/MIME/current-Unicode-name/read-only-grant/slide-entry acceptance, real native file-manager rename, and an Android reboot/original-retention check. These installed additions are pending execution, not host-certified. Storage exposes a same-origin, gesture-only interface-cache clear which retains all study files. Revised host runtime/routes/hierarchy/migration/backup/Tutor/format run: 61 passed in 67.27s; shell/JS syntax and diff whitespace checks passed. Every required remote gate must rerun for the new head.
