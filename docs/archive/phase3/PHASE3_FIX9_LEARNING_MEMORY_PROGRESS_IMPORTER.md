# Phase 3.1 Fix 9 — Learning Memory + Academic Progress Importer

## Purpose

Fix 9 imports legacy learning-memory and course-progress evidence after Fixes
4--8 have established the structured SQLite foundation and assessment evidence
pipeline.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

This fix does not create `data/learning_assistant.db`, does not rewrite JSON, and
does not directly mark any topic weak or mastered in the current application
state.

## What is imported

`personal_learning_assistant/migration/learning_progress_importer.py` imports:

- global learning-memory weak topics;
- global learning-memory mastered topics;
- global learning-memory notes;
- course-scoped memory from `course_memory`;
- legacy recent activity as memory evidence, not as study sessions;
- course progress-history snapshots.

The importer writes into the existing Fix 2 schema:

- `learning_memory_entries`
- `topic_progress_events`
- `progress_snapshots`
- `migration_imports`

## Ordered prerequisites

Fix 9 requires Fix 4 course/topic evidence first because course and topic links
must be resolved through the migration ledger rather than guessed.

The safe order is:

1. Fix 4 imports courses and topics.
2. Fix 5 imports assessments and assessment topic labels.
3. Fix 6 imports questions and raw source labels.
4. Fix 7 imports question-topic mapping observations.
5. Fix 8 imports attempts, mistakes, and performance evidence.
6. Fix 9 imports learning memory and academic progress evidence.

Fix 9 can technically run after Fix 4 for its own source tables, but the Phase 3
migration plan keeps it after assessment-performance import so later reports can
read the full evidence chain in order.

## Source files

Fix 9 reads exactly these verified scanner snapshots:

- `data/learning_memory.json`
- `data/course_progress_history.json`

Both are re-hashed before parsing and again before transaction commit. Any source
change after scanning aborts the import before partial writes are accepted.

## Resolution policy

Course IDs from legacy memory scopes and progress history are resolved only
through Fix 4 `migration_imports` evidence for `data/courses.json`.

Topic labels from weak/mastered memory and recent activity are linked only when
there is exactly one live Fix 4 topic in the resolved course with the same
normalized name.

Fix 9 does not use fuzzy matching, another course's topic, question text, attempt
mistakes, or AI inference during migration.

If a course or topic cannot be resolved:

- the original raw value is preserved;
- a review item is emitted;
- the importer does not guess a foreign key;
- no `topic_progress_events` row is created for an unresolved topic, because that
  table correctly requires a real topic ID.

## Topic-progress evidence

A resolved weak/mastered learning-memory topic creates an append-only
`topic_progress_events` row:

- weak topic -> `legacy_memory_weak_topic`, `new_status = weak`
- mastered topic -> `legacy_memory_mastered_topic`, `new_status = mastered`

The importer does not update `topics.status`. This is deliberate. The event is
migration evidence only; any final mastery/status decision belongs to later
reconciliation and Phase 4 cutover.

## Progress snapshots

`course_progress_history.json` rows become `progress_snapshots` records with:

- resolved course ID;
- snapshot date;
- count JSON preserving mastered/total topic counts;
- score JSON preserving progress percentage;
- engine version `legacy_course_progress_history_v1`.

Unresolved course snapshots are not guessed and are reported for review.

## Identity and idempotency

Stable target IDs use deterministic UUID5 values from portable source path,
entity type, and legacy identity. They deliberately exclude `source_hash`.

For an unchanged source hash, re-import:

- creates no duplicate memory rows;
- creates no duplicate topic-progress events;
- creates no duplicate progress snapshots;
- creates no duplicate ledger rows;
- does not rewrite matched targets.

For a changed source hash, stable target IDs allow the same logical legacy memory
or progress snapshot to update the same target row, while `migration_imports`
records a new source observation.

## Conservative handling

Fix 9 keeps migration safe and reviewable:

- global topics remain global and unresolved unless a course scope exists;
- course-scoped topics require exact course-topic resolution;
- recent activity is preserved as memory text, not converted into a study
  session;
- malformed list/object shapes fail before writes;
- duplicate progress snapshots for the same course/date are rejected;
- no legacy JSON file is normalized or rewritten.

## Verification

Run:

```powershell
.\phase3_fix9_gate.ps1
```

The focused tests verify:

1. fixture learning memory and progress history import without touching source
   bytes;
2. global unresolved weak/mastered topics are preserved as raw memory evidence;
3. progress snapshots resolve through Fix 4 course evidence;
4. exact course-scoped topic memory creates append-only topic-progress evidence;
5. topic status itself is not mutated;
6. identical re-import is a no-op;
7. changed memory source hashes update stable targets and create new ledger
   observations;
8. unresolved progress-history courses are reported and skipped rather than
   guessed;
9. malformed memory/progress shapes fail without partial writes;
10. source changes after scan are rejected before writes.

The gate also runs every Phase 3 test, the full project regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Non-goals

Fix 9 does **not**:

- create/populate production `data/learning_assistant.db`;
- switch services from JSON to SQLite;
- infer topics from attempt mistakes or question text;
- mutate `topics.status`;
- create study sessions from recent activity;
- import weekly/multi-course/intelligent study plans;
- import grade settings or calendar events;
- reverse-export or reconcile all migrated data;
- disable legacy JSON writers.

Those remain later Phase 3/Phase 4 units.
