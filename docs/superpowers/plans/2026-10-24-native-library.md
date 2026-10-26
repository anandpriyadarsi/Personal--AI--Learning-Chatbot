# Native document Library Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Owner explicitly requests implementation through delivery; do not stop for a plan approval.

**Goal:** Preserve original documents and expose a usable mobile file manager with page/slide search.
**Architecture:** Separate additive SQLite metadata/index and content-addressed original blobs. Reuse Flask and existing academic catalogue; preserve all legacy readers.
**Tech Stack:** Python, Flask/Jinja, SQLite FTS5, pypdf, OOXML, optional local OCR, Java Android.
**Spec:** docs/superpowers/specs/2026-10-24-native-library.md

## Global Constraints
No original conversion/replacement, external AI, automatic lessons or destructive migration.
No main merge. Verified results only. Android API31 and newer acceptance must be distinguished from browser verification.

## Review Focus
- Concurrent delete/disable/rebuild versus background publication.
- Malformed/encrypted/large/empty uploads and ZIP resource limits.
- Folder cycles, copied blob ownership, independent course mapping.
- Same-origin actions, unsafe paths/names, private response caching.
- Missing platform parsers/viewers and truthful search readiness.

### Task 1: Original store and index
- [ ] Write and run failing `tests/test_native_document_library.py` against NativeDocumentLibrary.
- [ ] Implement `services/native_document_library.py` storage, metadata, folders, streamed SHA upload, FTS page search and durable worker.
- [ ] Verify integrity, exact phrases, slide order, moves, copy/delete references, interrupted/retry/disable race, scan/OCR and recovery.

### Task 2: Complete web experience
- [ ] Write failing route/browser tests for upload, browse, details/edit/delete and opening a search match.
- [ ] Add web/native_library.py, native_library.html, native_document.html and static assets; register blueprint, link Files from Library.
- [ ] Provide folder and subject filters, action menus, list/grid, background statuses, upload progress/cancel, privacy control, explicit Studio handoff.
- [ ] Run focused legacy and new tests plus actual Chromium at 360px dark/light.

### Task 3: Android integration and delivery
- [ ] Integrate shared commits on isolated Android branch; preserve phone local root and backup behavior.
- [ ] Implement safe open/share through FileProvider, bounded streaming and correct PDF/PPT MIME; PDF page number fallback if native renderer unavailable.
- [ ] Discover SDK/build prerequisites; run build/unit/device gates when available, record blockers otherwise.
- [ ] Review complete diff, run relevant regressions, commit, push branch and open draft PR with verification ledger and limitations.
