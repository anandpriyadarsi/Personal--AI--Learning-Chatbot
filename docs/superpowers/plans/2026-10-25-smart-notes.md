# Smart Notes Implementation Plan

**Goal:** Deliver nested notes, shared attachments, optional Obsidian and light native startup.
**Architecture:** Additive JSON fields and separate Flask blueprints with sanitized lazy section rendering; reuse PR47 media persistence and native content-URI bridge.
**Tech Stack:** Python/Flask/JSON, vanilla JS/CSS, Android Java.
**Spec:** docs/superpowers/specs/2026-10-25-smart-notes-design.md

## Constraints
Preserve note IDs, body, assets, mappings, academic tools and unrelated branches. No internal media player. Never treat unrun Android checks as passes.

## Review focus
Stale edit conflicts; legacy body coexistence; section deletion with attachments; cross-note move rollback; Unicode filenames and duplicate binary ownership.

- [ ] 1. Add failing service tests for section CRUD/order/duplicate/move, stale version, legacy preservation and persistence; implement `NestedNotesService` using repository shared lock.
- [ ] 2. Add failing shared-media tests for typed/image/document/section binding; implement signature allowlist and validated section association with delete/move consistency.
- [ ] 3. Add CSRF/conflict route tests; implement nested blueprint and lazy mobile accordion editor/search, compact reader/list and shared attachment control.
- [ ] 4. Implement and verify optional Obsidian connection/import/disconnect in independent scoped files.
- [ ] 5. Implement and verify Android splash/native document MIME support in independent scoped files.
- [ ] 6. Run focused tests, real mobile Chromium, full regression, review, publish exact tested tree as draft branch/PR; document pending native gates and reproducible commands.
