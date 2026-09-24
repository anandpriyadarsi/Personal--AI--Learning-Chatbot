# Phase 7.5.15.9 — Notes Studio Reconciliation Decision

Status: FINAL RECONCILIATION DECISION  
Branch: `phase7.5.15/notes-studio-rich`  
Baseline: Phase 7.5.15.8 closure `f780cab7eaf8f55b2d0e963e4f317d61adcdbe29`

## Decision

**NO AUTOMATIC LEGACY MIGRATION**

Phase 7.5.15 closes the Notes Studio 2.0 implementation without automatically migrating, deleting, rewriting, or adopting records from `data/notes.json`.

The default rich-note authority is the configured **Obsidian Markdown** vault.

SQLite continues to own only the structured responsibilities already approved by the architecture, including managed identity, lifecycle metadata, hashes, tags, operation coordination, and related structured state. It does not become a duplicate note-body authority.

## Default Notes experience

The normal `GET /notes` experience is the Phase 7.5.15 Visual Notes Library backed by the canonical Obsidian/Notes Studio read model.

New rich-note creation uses the Safe Editor path:

`GET /notes/new` -> `POST /notes/new`

Managed-note editing uses:

`GET /notes/edit` -> `POST /notes/edit`

Those writes reuse the existing Phase 5.4 Notes Studio command, expected-hash, atomic-write, journal, and outbox protocol.

## Legacy compatibility decision

The existing `data/notes.json` store remains a **compatibility** store.

The pre-existing Phase 7.5.11 legacy POST endpoints remain preserved so older explicit integrations/tests are not silently broken. The default Notes Studio UI does not use those endpoints for new rich notes.

The legacy GET override remains limited to explicit host/test configuration and does not replace the normal production Notes Studio library.

Phase 7.5.15.9 adds a read-only reconciliation preview that can classify legacy rows as:

- `match_existing`
- `needs_review`
- `create_markdown`

This preview performs no migration.

## Why migration is deferred

A safe legacy migration still requires product decisions that are intentionally outside Phase 7.5.15:

- whether each legacy row should be adopted, merged, or left historical;
- how duplicate titles and partially matching bodies should be reviewed;
- how legacy `topic` and `difficulty` map to richer note metadata;
- whether imported notes should receive templates/course/date/card-summary metadata;
- when legacy POST compatibility endpoints may be retired.

Those decisions require a **separate reviewed migration** unit with its own preview, approval, rollback/recovery evidence, and protected gate.

## Unmanaged Markdown

Unmanaged Markdown notes remain readable in Notes Studio.

They are not silently assigned an `assistant_id`, rewritten, adopted into SQLite lifecycle ownership, or made editable through managed-note mutation controls.

Adoption of an unmanaged note is deferred to an explicit future workflow if desired.

## Migration evidence

Phase 7.5.15.9 introduces **no SQLite migration** for Notes Studio.

During final reconciliation, the production `schema_migrations` table proved that historical migration version 8, `moodle_sync`, had already been applied on `2026-09-22T13:04:58Z`, while its source file was missing from the current branch. Git object history still contained the exact original blob:

`37952ec7145b1cc7e15f7e34fa49e41ae6a7c99d`

The recovered file:

`personal_learning_assistant/repositories/sqlite/migrations/0008_moodle_sync.sql`

has SHA-256:

`915903ca7d7845c1d85c0b9ccb149ecff111d2f20fbf7dd7faa4a6b87e7a8e96`

which exactly matches the checksum already recorded in the production database.

This is **historical migration-source recovery**, not a new migration, not a schema mutation, and not a production-database write. The production database is left unchanged.

The final gate verifies:

- current migration source/history consistency;
- SQLite integrity;
- foreign-key integrity;
- legacy JSON preservation;
- configured-vault preservation;
- retrieval-state preservation;
- Tutor-code preservation;
- no automatic legacy migration;
- no permanent-delete route;
- complete Phase 7.5.15 regression coverage.

## Tutor boundary

Tutor remains outside Notes Studio ownership.

Phase 7.5.15.9 does not modify Tutor reasoning, prompts, sessions, adaptive practice, prerequisite logic, understanding checks, or Tutor state.

Any future Tutor -> Save as Note integration must use a narrow explicit note-draft contract and the same Notes Studio safe write boundary.

## Merge-readiness condition

Phase 7.5.15 is ready for merge consideration only after the Phase 7.5.15.9 final gate is green.

A green final gate means:

- the rich Markdown Notes Studio is the default experience;
- legacy JSON compatibility remains intact and non-destructive;
- no implicit data migration occurred;
- all Phase 7.5.15.1 through 7.5.15.8 capabilities regress cleanly;
- authority, vault, SQLite, retrieval, and Tutor protections remain intact.

This decision does not itself authorize merging to `main`; merge remains a separate integration action after final validation.
