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
