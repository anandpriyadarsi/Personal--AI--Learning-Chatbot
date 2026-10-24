# Handwritten media Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Attach persistent audio/video to handwritten notes and open it in installed Android applications.
**Architecture:** Existing JSON note ownership, streamed files, lazy media routes/UI, gesture-restricted native navigation handoff and read-only FileProvider.
**Tech Stack:** Flask, Python, browser JavaScript/CSS, Android Java, AndroidX Core, Chaquopy.
**Spec:** docs/superpowers/specs/2026-10-24-handwritten-media-design.md

## Global Constraints
No internal player or transcoding. Preserve academic stores. Eight requested formats, 512 MiB/file, 20/batch, 1 GiB/request. No private URLs or raw paths in external intents. Retain Android offline/auth boundaries.

## Review Focus
- Retried simultaneous uploads deduplicate without dropping existing note edits.
- Renames retain extension/MIME and cannot insert paths or header controls.
- Failed uploads or JSON writes roll back files and preserve note pages.
- A stale/tampered path or symlink never exposes another private file.
- Chooser cancellation, missing handlers and activity return keep the note usable.

### Task 1: Persistent streamed media and routes
Files: services/notes_media_service.py, ui/web/notes_media.py, ui/web/__init__.py; tests/test_notes_media.py.
Interface: NotesMediaStore(repository).list/add/rename/delete/resolve. Add accepts (filename, readable stream) pairs and returns public metadata; resolve verifies and returns file metadata plus canonical Path, never bytes. Routes delegate to the existing configured Notes repository. All mutations require process-local CSRF.
- [ ] Write storage/HTTP tests; observe missing feature failures.
- [ ] Implement bounded header/stream validation, hashing, locked atomic metadata mutation, deduplication and rollback.
- [ ] Verify supported formats, restart, rename/remove, corruption, unsafe paths, concurrent retry, partial failure, download headers and CSRF.

### Task 2: Lazy mobile note interface
Files: templates/anvaya_notes_reader.html, static/js/notes_media.js, static/css/notes_media.css; tests/test_notes_media_browser.py.
Consumes public routes. Uses textContent for file names, native ordinary links for open/share, download fallback, existing theme variables and accessible forms.
- [ ] Add browser journey and run it red.
- [ ] Implement simple list/attach/overflow forms; disable duplicate submissions; never render audio/video elements or preload file bytes.
- [ ] Run real 360/390/desktop upload/reopen/rename/delete/layout journey.

### Task 3: Android external application handoff
Files: MainActivity.java, MediaRequest.java, MediaIntents.java, MediaFileProvider.java, media_paths.xml, AndroidManifest.xml, app/build.gradle, notes_media_service.py; JVM and instrumentation tests.
Consumes validated note/attachment IDs. Native resolver consumes filesDir, noteId, assetId and returns path/MIME/name. Keep this interface native-only. ACTION_VIEW/ACTION_SEND receive read-only content URI and ClipData.
- [ ] Write URL, URI/intent/provider and no-handler/return tests before implementation.
- [ ] Implement gesture/origin-gated link interception and background resolver; retain note while dispatching; offer share/export if no player exists.
- [ ] Build/debug JVM tests; run emulator instrumentation via existing workflow if local SDK unavailable.

### Task 4: Delivery
- [ ] Run relevant existing notes/runtime regressions and broader suite; disclose failures/skips.
- [ ] Commit feature only, publish branch/PR with exact verification evidence, trigger existing Android build/regression/emulator workflow.
- [ ] Review whole change; correct important findings with regression tests.
- [ ] Deliver tested APK if build succeeds; clearly distinguish physical player testing from synthetic instrumentation.
