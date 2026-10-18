# Phase 5.1 — Knowledge Registry + Operation Journal/Outbox Foundation

## Starting point

This unit starts after the completed Phase 4 closure commit:

`58fbab8fe57fb34e58979c95714f00a42e7a0a2f`

Development branch:

`phase5/knowledge-notes-resources`

Phase 4 has already promoted structured academic state to SQLite. Phase 5.1
must not roll that authority back or modify legacy structured JSON.

## Objective

Activate the knowledge/coordination tables that were deliberately created by
the Phase 3 schema but not yet given an application service boundary:

- `knowledge_documents`
- `knowledge_chunks`
- `index_jobs`
- `operation_journal`
- `outbox_events`

No new migration is required for Phase 5.1. The established `0001` and `0002`
migrations already contain the necessary schema.

## Authority boundaries

Phase 5 deliberately has multiple authorities:

- source PDFs/text/transcripts remain authoritative content files;
- Obsidian Markdown remains authoritative for future note bodies;
- SQLite is authoritative for metadata, identities, relationships, provenance,
  ingestion/index job state and operation coordination;
- lexical/semantic indexes remain disposable derived data.

The Phase 5.1 registry never rewrites source files and never imports source body
content on module import.

## Stable document identity

A document must have at least one durable locator:

- `canonical_uri`, or
- portable `path_key`.

The service derives a stable UUIDv5 from document kind plus the preferred
identity. Content hash is revision evidence, not object identity, so changing
source bytes keeps the same document ID and resets extraction state to pending.

Registration is idempotent for the same identity and hash.

## Extraction/chunk foundation

`record_extraction()` stores versioned chunk metadata in the existing
`knowledge_chunks` table. Stable chunk IDs are derived from:

`document ID + extraction version + ordinal`.

Replacing the same extraction version is transactional and deterministic.
Actual PDF/Markdown/PPTX/transcript extraction belongs to later Phase 5 units.

## Index-job foundation

Index requests use the schema's existing uniqueness key:

`document + content hash + index kind + model + model version + index version`.

Scheduling the same derived work twice returns the existing job instead of
creating duplicates.

The state machine is intentionally small:

`pending -> running -> completed|failed`

No index implementation is introduced in Phase 5.1.

## Operation journal

The journal establishes the protocol that Notes Studio will use before any
future file mutation:

`planned -> file_applied -> database_committed -> completed`

A DB-only operation may use:

`planned -> database_committed -> completed`

Any non-terminal step can fail explicitly. Completed/failed records are
terminal. Phase 5.1 itself performs no Markdown mutation.

## Outbox

Outbox rows represent derived work/events that should happen after authoritative
metadata commits. Payloads are canonical JSON objects. Pending, processed and
failed states remain explicit. This is the foundation for later indexing and
rebuild workers.

## Safety

- every repository requires an explicit `sqlite3.Connection`;
- importing modules does not open/create a database;
- tests use temporary databases only;
- no production/private knowledge source is used in tests;
- no Phase 4 authority control is changed;
- no `0003` migration is introduced in this unit;
- source bodies are not scanned or rewritten;
- integrity/FK checks are read-only.

## Verification

`phase5_verify_registry.py` opens the real promoted database using SQLite
`mode=ro`, validates Phase 5.1 tables/columns, runs integrity/FK checks and
reports counts only. It does not print private note/resource/source content.

## Non-goals

Phase 5.1 does not implement:

- vault scanning or note-link parsing (Phase 5.3);
- Notes Studio file writes (Phase 5.4);
- Resources 2 migration (Phase 5.5);
- source extraction/PPTX/PDF/transcript adapters (Phase 5.6);
- MIT 18.06 package ingestion (Phase 5.7);
- FTS/embeddings/hybrid RAG (Phase 5.8);
- Dashboard 2 or Phase 6 interfaces.

## Next boundary

Phase 5.2 should build **Document Registry + Source Scanner** on top of this
foundation. The scanner should calculate canonical source identity/hash and
call this registry service without moving or rewriting source files.
