# Notes and native PDF Implementation Plan

> **For agentic workers:** Use the parallel domain workflow for Notes and PDF; the root owns integration, Android acceptance wiring, verification and delivery.

**Goal:** Deliver simplified mobile Notes and safe original-PDF external viewing in the existing unified ANVAYA APK.

**Architecture:** Extend current Notes JSON and nested/media services and native content-addressed Library. Reuse the embedded Python/WebView bridge and FileProvider; no duplicate stores or data reset.

**Tech Stack:** Flask, Jinja, JavaScript/CSS, Java Android, Chaquopy, pytest, Playwright, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-28-notes-native-pdf.md`

## Global Constraints

- Application ID `in.anvaya.privateapp`; SDK24 minimum / SDK35 target; Android12 primary.
- Preserve data roots, metadata, attachments, course mappings and approved static opening.
- Exact tagline: `Personal Learning Intelligence...`.
- Keep AI use explicit; no Tutor redirects or extraction on PDF view.
- No fabricated signing or device verification.

## Review Focus

- Existing legacy notes lacking new pin/archive metadata must retain content and order.
- Narrow screens, the keyboard and bottom navigation must not overlap cards/FAB.
- Renamed Unicode PDFs must retain their bytes and meaningful supplied filename.
- External apps must receive only read access, and no viewer must fail clearly.
- Restart/update/backup must retain original blobs and note/media identities.

### Task 1: Notes library and reading experience

Files: Notes services/repository/routes, `anvaya_notes_library.html`, reader/create templates, scoped JS/CSS, Notes tests.
Interfaces: existing note IDs and optimistic-update versions; existing nested/media endpoints.

- [x] Add failing lifecycle/filter/mobile browser cases.
- [x] Implement compact library, persistent views/FAB, overflow management and additive lifecycle metadata.
- [x] Preserve nested independent editing and make focus strictly read-only.
- [x] Run Notes/service/browser regressions and capture four requested UI screenshots.

### Task 2: Original document native handoff

Files: `native_library.py`, service/template/JS, native Java request/intents/provider, new native handoff tests.
Interfaces: managed document ID -> verified original blob -> read-only content URI; open/default vs chooser vs share/export.

- [x] Reproduce defaults/rename issues in route/JVM/native tests.
- [x] Implement external default PDF handoff, chooser, errors, rename-safe filenames and explicit indexing.
- [x] Exercise retained original bytes, duplicate names, restart and backup; add installed external-UID assertions and screenshots.
- [x] Run Library/Android regression tests without weakening integrity assertions.

### Task 3: Integrated acceptance and release

Files: Android acceptance script and existing test selectors, build version, release workflow, release report.
Interfaces: precise source SHA, one signed APK pair, API31/API35 installed results, release asset hash.

- [ ] Update existing Android journeys to use the new user-visible menu flows.
- [ ] Wire new PDF tests into mandatory installed checks and screenshot extraction.
- [ ] Run baseline/final regression and independent review; fix material issues.
- [ ] Publish branch/PR, inspect exact-source checks, merge only verified compatible code.
- [ ] Build final main, verify signed asset, publish only with honest signing and device limitations.
- [ ] Record passed/failed/skipped checks, screenshots, installation and safe migration instructions.
