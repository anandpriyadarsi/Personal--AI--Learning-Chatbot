# Phase 3.1 Fix 8 — Attempts + Mistakes + Assessment Performance Importer

## Purpose

Fix 8 imports the legacy question-performance evidence from a verified
`data/assessment_workspace.json` snapshot after Fixes 4–7 have established
stable courses, topics, assessments, questions, and optional topic mappings.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

This fix does not create `data/learning_assistant.db`, does not rewrite JSON, and
does not mark any topic weak/mastered.

## What is imported

`personal_learning_assistant/migration/attempts_performance_importer.py` imports:

- question attempts into `question_attempts`;
- attempt-attached mistake text into `mistake_events`;
- derived import-result summaries for attempts, outcomes, marks, and review work.

The importer reads attempt evidence from both legacy shapes:

- top-level `question["attempts"]`;
- V10.4 `question["performance"]["attempts"]`.

Attempt-specific `mistake` strings are imported as `legacy_attempt_mistake`
rows. Standalone `performance["mistakes"]` or top-level `mistakes` lists are not
attached to a guessed attempt. They are counted and reported as deferred review
items because the current core schema intentionally requires `mistake_events` to
belong to a real attempt.

## Ordered prerequisites

Fix 8 requires the exact workspace hash to already have Fix 6 question evidence
in `migration_imports`.

The safe order is:

1. Fix 4 imports courses and topics.
2. Fix 5 imports assessments and assessment topic labels.
3. Fix 6 imports questions and raw source labels for the exact workspace hash.
4. Fix 7 optionally imports question-topic decisions.
5. Fix 8 imports attempts, mistakes, and performance evidence.

If the workspace changes after Fix 6, run Fix 6 again first. Fix 8 will reject a
changed workspace whose exact question-hash prerequisite has not been imported.

## Identity and idempotency

Attempt target IDs are deterministic UUID5 values from:

`source_path + entity_type + question legacy key + attempt origin + attempt index`

The target ID deliberately excludes `source_hash`, so a changed source hash can
update the same logical target while the `migration_imports` table records a new
source observation.

For unchanged source hash, re-import:

- creates no duplicate attempt rows;
- creates no duplicate mistake rows;
- creates no duplicate ledger rows;
- does not rewrite matched rows.

## Conservative data handling

Fix 8 keeps migration safe and reviewable:

- unknown/missing outcomes import as `unknown` with warnings;
- earned/max marks use integer milli-units;
- earned marks greater than max marks are imported as `NULL` for earned marks
  and kept in raw ledger details;
- non-string attempt mistakes are not imported as rows and remain in ledger
  details;
- standalone mistakes are deferred rather than guessed onto an attempt;
- no assessment score, course progress, topic mastery, or learning memory is
  modified by this importer.

## Verification

Run:

```powershell
.\phase3_fix8_gate.ps1
```

The focused tests verify:

1. an empty performance snapshot imports no rows and changes no source bytes;
2. attempts and attempt-attached mistakes import correctly;
3. marks and outcomes are converted safely;
4. identical re-import is a no-op;
5. changed workspace hashes require exact Fix 6 question evidence first;
6. changed hashes update stable targets and create new ledger evidence;
7. invalid outcomes/marks do not violate SQLite constraints;
8. source changes after scan are rejected before writes.

The gate also runs every Phase 3 test, the full project regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Non-goals

Fix 8 does **not**:

- create/populate production `data/learning_assistant.db`;
- switch services from JSON to SQLite;
- infer topics from attempts or mistake text;
- mark topics weak/mastered or update learning memory;
- import study plans, grade settings, calendar data, resources, or notes;
- reverse-export or reconcile all migrated data;
- disable legacy JSON writers.

Those remain later Phase 3/Phase 4 units.
