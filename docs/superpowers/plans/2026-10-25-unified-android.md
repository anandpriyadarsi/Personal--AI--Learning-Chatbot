# Unified ANVAYA Android Integration Implementation Plan

**Goal:** Implement the user-specified consolidated release with traceable PR provenance, verified main and a permanent APK download.
**Architecture:** Start at main 40ef6a76. Integrate stacked Android work once, preserve main reader fixes, then combine independent original-library, review and verification changes. Reconcile older PR patches by behavior and record superseded work explicitly.
**Tech Stack:** Flask/Python/SQLite, browser JavaScript, Android WebView/embedded Python, Gradle, GitHub Actions.
**Spec:** User's complete integration and release requirements in this session.

## Global constraints
No main rewrite, source deletion, academic-data mutation, essential-test weakening, false Android certification or obsolete-branch APK. Source PR bodies do not override this session's explicit integration and merge authorization. External private-source authority remains separate from synthetic acceptance.

## Review focus
- Stacked changes must retain current main reader and mapping behavior.
- Android document URI upload must retain original bytes through restart.
- Planning/Obsidian navigation must exercise actual production routes.
- Submitted-only answer disclosure; active/paused answers remain secret.
- Release publication must pin merged main, include checksum and explicit signing provenance.

### Task 1: Inventory and compatible composition
- [x] Inspect all 20 open PRs, heads, bases, existing main and release collection.
- [ ] Record per-PR ancestor/patch equivalence and conflicts in docs/integration.
- [ ] Merge latest stacked notes/Android lineage, then reader, original-library, assessment and coordinator patches. Inspect every conflict; preserve tests from both branches.
- [ ] Compare older Architecture/B3/C0/Mobile branches to integrated source; retain compatible unique work and record exclusions.
- [ ] Run focused Python/Node/mobile Chromium checks before committing composition.

### Task 2: Runtime defects and provenance
- [ ] Reproduce Planning, Obsidian, PDF and mobile-reader failures using synthetic production runtime.
- [ ] Write reproductions before any repair and rerun owning regression suite.
- [ ] Set distinct version, expose commit identity, verify packaging uses current source.
- [ ] Verify full Python/Node and actual Android JVM/build/installed lifecycle through existing CI; preserve logs.

### Task 3: Review, merge and release
- [ ] Publish exact local source as an integration PR and run canonical Linux/Windows and Android installed gates.
- [ ] Review integration diff; resolve material findings and keep blockers explicit.
- [ ] Merge only after required gates pass; reconfirm main SHA.
- [ ] Build signed or explicitly debug-labelled APK from merged main. Publish versioned GitHub release and verify asset, checksum, size, version, compatibility and actual download.
- [ ] Deliver every PR disposition, feature/test evidence and real-device limitations.
