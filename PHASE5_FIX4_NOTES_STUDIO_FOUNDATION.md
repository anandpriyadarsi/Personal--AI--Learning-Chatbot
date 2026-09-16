# Phase 5.4 — Notes Studio Foundation

## Starting point

Phase 5.4 starts from Phase 5.3 commit `09a00dff51fe7f4141d4740032142ada8568e491` on `phase5/knowledge-notes-resources`.

## Storage rule

Markdown in the configured Obsidian vault remains the one authoritative note body. SQLite stores identity, lifecycle state, tags, hashes and operation coordination only. Phase 5.4 never introduces a second database body or a new JSON authority.

## Commands implemented

Foundation commands are `CreateNote`, `UpdateNote`, `PinNote`, `ArchiveNote`, `TrashNote`, and `RestoreNote`.

Create uses a configured inbox (default `01 INBOX`), Windows-safe filenames, readable collision suffixes, a generated UUID `assistant_id`, and an atomic temp-file replace. Update requires the exact expected SHA-256 and refuses to overwrite an external edit. Pin/archive update SQLite only. Trash moves to `.trash/Personal AI Learning Assistant/`; restore requires an explicit destination.

## File + database protocol

File-changing commands use the Phase 5.1 operation journal:

`planned -> file_applied -> database_committed -> completed`

If a failure happens after the Markdown operation, the journal becomes `failed` and preserves evidence for operator recovery. No silent rollback guesses are made.

Successful saves also enqueue a `note.saved` outbox event. Later Phase 5 indexing consumes that event.

## Frontmatter

New Notes Studio notes mirror safe canonical metadata: `assistant_id`, title, note type, confidence, revision status and tags. Existing unknown frontmatter is not bulk-rewritten in Phase 5.4. Updates replace the known Notes Studio frontmatter boundary for Notes Studio-managed notes; unsupported existing vault notes continue to be read-only until explicitly adopted.

## Legacy notes preview

`legacy_note_reconciliation.py` provides read-only preview for `data/notes.json`. It classifies each legacy row as `match_existing`, `create_markdown`, or `needs_review`. It never writes Markdown or edits legacy JSON. Approved import execution is deliberately deferred until a reviewed migration unit.

## Non-goals

This foundation does not yet implement permanent delete, checklist mutation, course/topic/assessment/resource relations, FTS/semantic indexing, AI note actions, UI rendering, or automatic legacy-note import.

## Safety

No new SQLite migration is required. Tests use temporary vaults/databases only. The gate hashes the real vault, production SQLite, authority control and legacy JSON before/after and requires no changes.
