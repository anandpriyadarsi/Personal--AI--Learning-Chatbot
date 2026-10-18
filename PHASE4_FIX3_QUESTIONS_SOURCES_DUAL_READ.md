# Phase 4.3 — Assessment Questions + Question Sources Dual-Read Foundation

## Purpose and authority boundary

Phase 4.3 adds a read-only SQLite shadow for `assessment_workspace.json`
questions and question-source annotations. Legacy JSON remains authoritative for
all application-visible reads and writes. SQLite is not promoted to authority,
no legacy writer is disabled, and `assessment_question_workspace.py` is not
rewired or modified.

The exact Phase 4.3 base is `506b9c3` on `phase4/structured-cutover`.

## Current public architecture

At this base there is no standalone `QuestionService`. The live public API is
still the legacy `assessment_question_workspace.py` module. Creating a new
service and replacing that API in this fix would be an unrelated redesign, so
Phase 4.3 introduces only a repository seam:

- `QuestionRepository` protocol in `repositories/interfaces.py`;
- `LegacyJsonQuestionRepository`, which mirrors legacy `load_store` and
  `save_store` semantics but keeps reads side-effect free;
- `SQLiteQuestionRepository`, an explicitly supplied, read-only SQLite shadow;
- `DualReadQuestionRepository`, which always returns the legacy value and only
  records SQLite parity diagnostics.

Commands through the dual-read seam write only to the legacy JSON repository.
There is no `sqlite`-authoritative backend mode.

## SQLite read model

`SQLiteQuestionRepository` reads the Phase 3 tables `questions` and
`question_sources` plus prerequisite assessment identity evidence. It uses
`migration_imports` only to recover legacy IDs, raw records, source ordering
and source provenance. Actual SQLite relationships are read independently and
are never replaced by ledger expectations.

The adapter validates, among other things:

- question → assessment ownership;
- actual question ordinals against source-order evidence;
- exact question text, canonical imported status/marks, notes and import batch;
- question-source → question ownership;
- exact raw source labels and canonical page/locator values;
- existence of reviewed document/resource/note targets;
- ambiguous multiple source-resolution targets;
- stale question/source rows from older workspace source hashes;
- extra source rows not represented by the latest workspace migration evidence;
- soft-deleted questions that still exist in the latest legacy snapshot.

Every read checks that `connection.total_changes` is unchanged.

## Parity domains

Structured diagnostics compare or report:

- question catalogue and legacy identity;
- question status;
- question → assessment relationship;
- meaningful question order/ordinal;
- question source annotations;
- source ordering as inherited from question order;
- deterministic legacy source identity keys;
- exact raw question identity/status evidence;
- exact raw question records;
- exact raw source-file/page/question-number evidence;
- source version and source SHA-256;
- SQLite structural anomalies.

Raw identity/status/source evidence is not whitespace-normalized merely to make
parity pass.

## Explicitly deferred domains

Phase 3 Fix 6 deliberately did not make nested topic mappings or performance
records authoritative. Phase 4.3 therefore keeps these explicit:

- legacy `topic` / `topic_mapping` evidence is compared to the raw migration
  ledger but relational `question_topic_mappings` remain deferred to Phase 4.4;
- attempts, mistakes and performance remain deferred to their later cutover;
- reviewed `document_id`, `resource_id` or `note_id` source relationships are
  structurally validated, but are reported as deferred because the legacy
  workspace stores only raw source annotations and has no equivalent stable-ID
  fields;
- workspace-level metadata such as workspace `created_at` / `updated_at` was not
  imported by Fix 6 and is reported as deferred instead of silently invented.

## Safety and rollback

Focused tests use only a synthetic workspace fixture and temporary SQLite files.
They verify legacy bytes/hash and SQLite logical state are unchanged by reads,
and exercise both `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.

Rollback before final Phase 4 cutover is trivial: continue using legacy JSON and
discard/rebuild the SQLite shadow. Phase 4.3 creates no dual writes and no
production database.

## Verification

Run from the repository root before staging or committing:

```powershell
.\phase4_fix3_gate.ps1
```

The gate requires branch `phase4/structured-cutover`, exact HEAD `506b9c3`, and
no pre-staged changes. It runs Phase 4.3 focused tests, Phase 4.2 and 4.1
regressions, all Phase 3 tests, the full suite, compilation, dependency checks,
`git diff --check`, and repository hygiene checks.

## Non-goals

Phase 4.3 does not modify `assessment_question_workspace.py`, question-topic
mapping logic, attempts/mistakes/performance, learning memory, progress,
planning, grades, calendar, Notes, Resources, RAG, Obsidian, dashboards, or any
Phase 5 domain. It does not merge malformed parser fragments, guess stable
source relationships, delete legacy data, or make SQLite authoritative.
