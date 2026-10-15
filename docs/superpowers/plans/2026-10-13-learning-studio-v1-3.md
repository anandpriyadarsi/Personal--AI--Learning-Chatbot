# Learning Studio V1.3 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. The user explicitly authorises implementation without design reapproval.

**Goal:** Useful selected reading, complete exam revision and source-linked mistake recovery.

**Architecture:** Reuse the app sidebar for lesson navigation; derive deterministic key-free cues from existing feature-owned append-only events. Preserve immutable author data, server grading and read-only downstream boundaries; no schema bump or provider integration.

**Tech Stack:** Flask/Jinja, SQLite, local JS/CSS, pytest, real Playwright Chromium, Python 3.12.

**Spec:** Private user-supplied V1.3 master instruction and acceptance matrix, intentionally outside Git.

## Global Constraints

- Verified base `60875195f9b6c3145937c625f107244872d8891a`; separate branch/worktree `feature/learning-studio-v1-3`.
- No merge/main reset, Tutor consumer/provider/session change, Assessment grading change or production migration/write.
- Public tests/CI synthetic; private source, keys, coverage excerpts, student data and screenshots remain private.
- Reading/reflection/reveal/remembered/corrected retry are not mastery; exact module/question revisions remain authoritative.
- No checksum repairs, fabricated mapping or instructor/external certification.

## Review Focus

Drawer focus/storage denial; exact pending question across source, Learn and resume; recall self-report separate from graded recheck; complete Full author notes/cards; stale live mapping and malformed inputs.

### Task 1: Product quality

- [ ] Fail-first domain/browser tests for contextual rail, saved teach-back, exact source/reopen, practice/recheck states, deterministic revision queue and coverage projection.
- [ ] Implement calm selected reader, accessible collapse/drawer/Focus, source zoom, authored heading navigation, printable complete revision and honest short budgets.
- [ ] Verify retained contracts and all widths 360/390/768/1024/1366/1536/1920, including no-JS/storage denial/offline/print.
- [ ] Commit exact owned files after fresh tests and independent reviews.

### Task 2: Authoring and gates

- [x] Reproduce eight fail-first diagnostics/base failures after recovery.
- [x] Restore actionable errors/warnings and explicit review axes; 17 focused authoring tests pass.
- [x] Use verified V1.2 for runner defaults and V1.3 cross-platform CI; retain prior branch baselines.
- [ ] Commit and include final full-suite exact-node comparison.

### Task 3: Acceptance

- [x] Restore exact supplied ZIPs/original and verify all 10 manifest entries after workspace maintenance.
- [ ] Fresh before/after actual-pilot journeys, private source/coverage negatives, independent engineering and learning/UX reviews.
- [ ] Protected/privacy audit, local feature/focused/full regression delta, durable feature push, exact final-SHA Ubuntu/Windows CI.
- [ ] Private evidence archive, G01–G24 matrix, zero mandatory manual Windows steps and one prioritised follow-up.

Dark-only reading stays coherent; author content is unchanged, so no new private pilot revision is needed. Production identity/mapping and automatic Tutor consumption remain separate conditional gates.
