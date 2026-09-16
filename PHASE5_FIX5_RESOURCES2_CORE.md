# Phase 5.5 — Resources 2 Core

## Starting point

Phase 5.5 starts from `18ce28b7987643a6eec32b68f2439e1a6f4ce279`
(`feat: add Phase 5.4 Notes Studio foundation`) on
`phase5/knowledge-notes-resources`.

## Objective

Resources 2 replaces the conceptual V1 “list of links” with structured academic
learning objects backed by the existing SQLite schema.

This unit adds:

- typed resource records and commands;
- course/topic/note relationships;
- assessment/document relationships already supported by the schema;
- append-only resource progress/history;
- current materialized status;
- personal rating/quality note;
- duplicate-candidate detection;
- archive/trash/restore metadata lifecycle;
- read-only legacy `resources.json` reconciliation;
- candidate discovery from registered documents and notes.

It does **not** silently import, merge, copy, move or rewrite learning sources.

## Existing schema reused

No migration is added. Phase 3 already provides:

- `resources`
- `resource_courses`
- `resource_topics`
- `resource_notes`
- `resource_assessments`
- `resource_documents`
- `resource_progress_events`

The current Phase 5 knowledge/note registries provide the document and note
foreign-key targets.

## Resource identity

Creation requires a title, type, and at least one usable identity:

- canonical URI/path;
- provider + external ID;
- linked registered document;
- linked registered note.

YouTube URLs are normalized to a canonical watch URL and can infer provider
`youtube` plus video ID when possible.

Ordinary HTTP(S) canonicalization removes fragments and common tracking
parameters while preserving meaningful query parameters.

## Duplicate policy

Duplicate candidates are review evidence, never automatic destructive merges.

Signals:

1. exact provider + external ID;
2. normalized canonical URI;
3. shared registered-document content hash;
4. normalized title + provider candidate.

By default `CreateResource` blocks when candidates exist. A reviewed caller may
use `allow_duplicate=True` for identities that the database can legally keep
separate. The existing unique provider/external-ID constraint still prevents two
resources from claiming the exact same provider object.

## Relationships

Supported core semantics:

- Resource ↔ Course: `primary`, `supporting`, `external_course`, `prerequisite`
- Resource ↔ Topic: `explicit`, `imported`, `suggested` plus optional confidence
- Resource ↔ Note: summary/annotation/revision/source/solution/etc.
- Resource ↔ Assessment: source/reading/question sheet/preparation/etc.
- Resource ↔ Document: primary/transcript/supplement/solution/source/etc.

Relationship replacement is one SQLite transaction. Foreign-key failures roll
the entire operation back.

## Progress/history

`resource_progress_events` remains append-only.

Recording progress accepts:

- status;
- timestamp;
- value/max;
- unit;
- position;
- note.

The resource's materialized status is recalculated from the latest event by
`occurred_at,id`, not blindly from insertion order. A historical/backfilled
event therefore cannot overwrite a newer state.

`completed_at` reflects the current latest completed state. Reopening appends a
new event and clears the materialized completion timestamp while preserving the
older completion event in history.

The existing schema does not yet store course/topic/study-session context on an
individual resource-progress event. Phase 5.5 does not invent side tables merely
to simulate that missing schema. That extension should be added only when a
real consumer requires it.

## Legacy reconciliation

The supplied `data/resources.json` was audited as zero bytes.

The reconciliation preview reads the exact bytes and reports one of:

- `missing`
- `empty_file`
- `invalid_json`
- `wrong_shape`
- `valid_list`

A zero-byte or invalid source is **not** silently converted to `[]`.

Valid legacy rows are classified as:

- `match_existing`
- `create_resource`
- `needs_review`

No legacy row is auto-imported by the preview.

Registered knowledge documents not yet linked to a resource become candidate
resources. Registered Obsidian notes not yet linked to a resource become
`course_notes` candidates. Candidates are not auto-created.

## V1 compatibility

The old `resources.py` / Phase-2 JSON `ResourceService` is intentionally left
unchanged in this unit. Phase 5.5 establishes the Resources 2 service boundary
without silently redirecting old interactive commands or rewriting the
zero-byte legacy file.

A later interface/cutover unit can route the terminal/UI to Resources 2 after
real reconciliation has been reviewed.

## Safety

- explicit SQLite connection required;
- no production DB is opened on module import;
- no PDF/Markdown body bytes are stored in Resources 2 tables;
- no new migration;
- tests use temporary SQLite only;
- preview opens production SQLite read-only;
- gate hashes production SQLite, Phase-4 authority control, legacy JSON and real
  Markdown before/after;
- no real resource creation is performed by the gate.

## Next boundary

Phase 5.6 should build the Unified Ingestion Pipeline: versioned extraction
adapters for registered PDF/Markdown/PPTX/text/transcript sources, deterministic
chunks, provenance, and index-job handoff.
