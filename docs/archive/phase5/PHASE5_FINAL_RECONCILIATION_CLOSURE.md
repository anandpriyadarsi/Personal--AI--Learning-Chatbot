# Phase 5.9 — Final Reconciliation + Closure

## Starting point

Phase 5.9 starts from commit:

`a2633881eed965251e850b203654e5e365e37d96`

on branch:

`phase5/knowledge-notes-resources`

The starting commit contains the Phase 5.8 compact RAG-context provenance polish.

## Purpose

Phase 5.9 adds no new academic feature and no new storage authority.

It verifies that the complete Phase 5 knowledge system is coherent after the
real MIT 18.06 installation and the first real lexical retrieval build.

The closure chain is:

```text
source package / Obsidian authority
        |
knowledge registry + document identities
        |
Resources 2 relationships
        |
current knowledge_documents / knowledge_chunks
        |
reviewed MIT 18.06 <-> MA103N crosswalk provenance
        |
completed retrieval handoff
        |
current disposable lexical retrieval generation
        |
provenance-preserving search + compact RAG context
```

## Authority boundaries

Phase 5 closure preserves the established authorities:

- SQLite remains authoritative for structured metadata, identities,
  relationships, provenance, ingestion state and job state.
- source files remain authoritative for their original bytes.
- Obsidian Markdown remains authoritative for note bodies.
- retrieval indexes remain disposable derived artifacts.
- the reviewed external-course crosswalk remains explicit review evidence.
- Phase 5.9 performs no LLM call.

## Core reconciliation

The closure verifier checks:

- `PRAGMA integrity_check == ok`;
- `PRAGMA foreign_key_check` has no rows;
- migration history remains exactly `0001` + `0002`;
- no duplicate portable knowledge-document path identity;
- no duplicate active provider/external resource identity;
- every completed/current knowledge document has retrievable current chunks;
- no operation-journal row is left in a non-terminal state.

Historical terminal failures remain evidence and are reported rather than
silently deleted. Pending/failed outbox counts are also reported; pending outbox
events are not automatically treated as corruption because the outbox is a
derived-work coordination boundary.

## MIT 18.06 installation reconciliation

The verifier reads the real package and reviewed crosswalk and checks the
installed SQLite projection against them.

It verifies:

- external course identity;
- every lecture resource exists;
- MA103N course relationships;
- course-level and lecture-level reviewed topic relationships exactly match
  the crosswalk;
- all four package documents exist with exact source hashes;
- the current chunks document is completed;
- current SQLite chunk count exactly matches the package;
- every current chunk preserves the original package chunk ID;
- every current chunk preserves exact package text and text hash;
- MIT source-provider provenance remains intact;
- every current chunk carries the reviewed crosswalk hash;
- chunk-local MA103N topic provenance exactly follows the reviewed crosswalk.

Unresolved reviewed MIT labels remain valid external knowledge. They are not
treated as closure failures.

## Retrieval closure

The current `.phase5_retrieval` generation is verified against authoritative
SQLite:

- manifest file hashes are valid;
- source fingerprint matches current authoritative chunks/relationships;
- manifest chunk count matches authoritative chunk count;
- current production generation is the lexical Phase 5 baseline;
- every active document has a completed current lexical build job;
- no retrieval handoff remains pending;
- a real MIT Lecture 04 retrieval smoke query returns provenance-preserving
  evidence;
- compact RAG context contains explicit chunk provenance and does not regress
  to the old giant raw-locator JSON format.

## Rebuild rehearsal

Closure proves that retrieval is truly disposable.

Using the production SQLite database in read-only mode, the verifier builds a
fresh lexical index in an isolated temporary directory with
`acknowledge=False`.

The rehearsal must:

- produce the same deterministic generation ID as the current lexical index;
- pass manifest/file-hash validation;
- reproduce the same top smoke-query chunk;
- make zero production SQLite changes;
- make zero changes to the current `.phase5_retrieval` generation.

The temporary rebuild directory is deleted afterward.

## Real operator command

```powershell
python .\phase5_verify_closure.py `
  --project-root . `
  --database .\data\learning_assistant.db `
  --authority .\.phase4_authority.json `
  --index-root .\.phase5_retrieval `
  --configured-vault `
  --crosswalk ..\phase5-review\mit1806_ma103n_crosswalk.json `
  --local-course MA103N
```

This command is read-only with respect to production state.

## Gate

`phase5_final_gate.ps1` runs:

1. focused Phase 5.9 tests;
2. real Phase 5 closure verification + isolated retrieval rebuild rehearsal;
3. Phase 5.1-5.8 regressions;
4. Phase 4 post-promotion regressions;
5. Phase 3 foundation/reconciliation/reverse-export regressions;
6. complete promotion-aware project regression suite;
7. compilation;
8. dependency consistency;
9. SQLite integrity/FK read-only check;
10. Git/production/package/crosswalk/current-index immutability checks.

## Non-goals

Phase 5.9 does not:

- build semantic embeddings;
- promote semantic retrieval;
- call an LLM;
- build the Academic Tutor;
- redesign Notes Studio or Resources 2;
- modify the vault;
- add a SQLite migration;
- repair unresolved MIT labels automatically;
- begin Phase 6.

## Closure condition

Phase 5 is closed only when the final gate is green.

A green gate means the knowledge layer is coherent, provenance-preserving,
read-safe, and able to reconstruct its derived lexical retrieval index from
authoritative structured knowledge.

Phase 6 may then consume this stable knowledge layer for tutor/mentor behavior.
