# Assessment Studio — Simplified Authoring UX

## Baseline

This bounded UX refinement starts from:

`phase7.5.assessment-studio-ux/revision-upload @ 3b87d23ddbe7fac78a76badb9ad6480287a084bb`

No Assessment Package schema change and no SQLite migration is introduced.

## Goal

Preserve every Assessment Studio authoring feature while reducing visual and cognitive load.

The primary creation path is:

Assessment Studio
→ Quiz / Exam / Test
→ subject picker
→ focused subject workspace
→ floating Create with Alex companion
→ import JSON
→ blind preflight
→ test.

## Page states

### 1. Assessment type landing

The first authoring view shows only:

- Quiz;
- Exam;
- Test;
- collapsed recent history when history exists;
- floating Create with Alex launcher.

Course cards are not rendered inline on the landing view.

### 2. Subject picker

Selecting Quiz / Exam / Test opens a compact modal subject picker.

All active canonical courses remain available, but they do not expand down the page.

### 3. Focused subject workspace

After a subject is selected, the page shows only that assessment type + subject context.

The focused page contains:

- selected subject identity;
- compact import instructions;
- package file upload;
- filtered history for that type + subject;
- movable Alex companion.

Other subjects are not rendered into the focused workspace.

## Notes Studio visual continuity

Assessment Studio subject cards reuse Notes Studio card templates.

For each canonical course:

1. ANVAYA checks the existing Notes Studio library;
2. when a matching course note exists, the most recent matching note's `card_style` is reused;
3. when no existing note style can be found, the course receives a deterministic fallback from the six Notes Studio `iris-*` templates.

Assessment storage remains independent from Notes storage; this is presentation-only reuse.

## Movable Create with Alex companion

The large fixed prompt/Alex cards are removed from document flow.

A draggable floating launcher based on Notes Studio Study Tools is available on the authoring screen.

The drawer retains all existing functions:

- current Quiz / Exam / Test + subject context;
- Copy personalized prompt;
- Open Alex / ChatGPT;
- Preview prompt;
- Edit master prompt;
- link back to package upload.

The launcher position is persisted in browser localStorage.

## Package history

History cards are fully clickable via a stretched full-card link.

The small "Open package review" text remains a visual cue, but it is not the only clickable target.

## Rejected-package cleanup

Rejected packages may be permanently deleted from Assessment Studio history.

Deletion is permitted only when:

- import status is `rejected`;
- no canonical assessment is linked.

Review or approved packages cannot be deleted through this action.

Staged questions/options are removed by existing ON DELETE CASCADE relations.

## Non-goals

This refinement does not change:

- package schema;
- blind preflight;
- revision upload;
- test runner;
- evaluation;
- assessment intelligence;
- adaptive academic loop;
- canonical assessment deletion semantics.
