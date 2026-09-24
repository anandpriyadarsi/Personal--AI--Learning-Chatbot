# Phase 7.5.15.8 — Lifecycle + Study Actions Implementation Report

Status: PASS  
Branch: `phase7.5.15/notes-studio-rich`  
15.7 closure baseline: `a43d12e564a80bb2dbabb738ad10645121b3ccb5`

## Objective

Expose recoverable managed-note lifecycle controls and bounded study-status actions in Notes Studio while preserving the existing authority split:

- Markdown remains authoritative for note bodies.
- SQLite remains authoritative for managed-note lifecycle metadata.
- File moves and revision-status changes reuse the established Phase 5.4 command/write protocol.
- Unmanaged Obsidian notes remain read-only with respect to managed lifecycle actions.

## Implemented

### Lifecycle actions

Managed notes now support:

- pin
- unpin
- archive
- unarchive
- move to trash
- restore from trash

Pin/archive state is stored in the existing SQLite lifecycle columns.

The Notes Studio repository now has exact reversible setters for pinned and archived timestamps so unpin/unarchive can clear their own state without disturbing other lifecycle fields.

### Trash and restore

Moving a managed note to Trash uses the existing Notes Studio file-move protocol and requires the current expected source hash.

Trash remains recoverable. No permanent-delete action or route was added.

Notes Studio now provides:

- `GET /notes/trash`
- `POST /notes/restore`

The Trash page exposes metadata only and does not render note bodies.

Restore requires an explicit vault-relative Markdown destination before the move is attempted. Expected-hash conflict protection remains active during trash and restore operations.

### Study actions

The Full Note Reader now exposes bounded study-status commands:

- Needs practice
- Review due
- Revised
- Mastered

These actions update only the existing `revision_status` metadata/frontmatter through `NotesStudioService.update_note()`.

They do not:

- start Tutor
- invoke AI
- create a second study-state system
- rebuild retrieval indexes
- mutate unrelated lifecycle fields

### Canonical lifecycle reads

The canonical Notes Studio read model now overlays managed lifecycle metadata from SQLite using a read-only SQLite connection.

The overlay includes:

- managed
- pinned_at
- archived_at
- trashed_at

Unmanaged notes receive no managed lifecycle state.

### Notes Library

The Notes Library now provides lifecycle navigation:

- Active
- Pinned
- Archived
- Trash

Active view excludes archived/trashed managed notes.

Pinned filtering surfaces pinned notes and pinned cards float to the front while preserving the established deterministic scanner order for other cards.

Archived notes can be viewed separately.

### Full Note Reader

Managed notes now expose:

- lifecycle state
- pin/unpin
- archive/unarchive
- move to trash
- bounded study-status controls

Unmanaged notes do not receive these controls.

## Safety and authority

Phase 7.5.15.8 does not introduce:

- permanent deletion
- a second lifecycle store
- a second note-body store
- direct route-level Markdown writes
- Tutor coupling
- AI calls
- retrieval rebuilds
- a new SQLite migration

All file-moving/status-writing behavior continues through established Notes Studio service boundaries.

## Validation repair

The first focused run exposed a test-only string-match mismatch for the archived lifecycle navigation link. The template correctly used:

`url_for('web.notes', view='archived')`

while the assertion searched for another textual form. The test was corrected to match the actual Jinja route expression. Production lifecycle behavior was not changed for that failure.

## Strict gate evidence

User-executed local strict gate result on 2026-09-24:

- Phase 7.5.15.8 focused lifecycle/study-action tests: PASS
- Phase 5.4 lifecycle/write-protocol regression: PASS
- Phase 7.5.15.7 Knowledge Connections regression: PASS
- Phase 7.5.15.6 Safe Editor regression: PASS
- Phase 7.5.15.5 Rich Visual Blocks regression: PASS
- Phase 7.5.15.4 Templates regression: PASS
- Phase 7.5.15.3 Full Note Reader regression: PASS
- Phase 7.5.15.2 Visual Notes Library regression: PASS
- Phase 7.5.15.1 canonical read-model regression: PASS
- Obsidian renderer/workspace/Reader regressions: PASS
- complete pytest suite: **1383 passed, 6 skipped, 1 deselected**
- compileall: PASS
- dependency consistency / `pip check`: **No broken requirements found**
- production-data protection: PASS
- retrieval-state protection: PASS
- Tutor-code protection: PASS
- SQLite-migration protection: PASS
- configured production-vault protection: PASS
- lifecycle authority protection: PASS
- scoped diff / `git diff --check`: PASS

Final banner:

`PHASE 7.5.15.8 LIFECYCLE + STUDY ACTIONS: PASS`

## Closure

Phase 7.5.15.8 is complete and green.

The next authorized unit in the master sequence is:

**Phase 7.5.15.9 — Reconciliation + Final Gate**

That final Notes Studio unit should reconcile remaining legacy/read/write boundaries, verify the entire Phase 7.5.15 stack end to end, document any deferred migrations, and run the final protected gate before merge consideration.
