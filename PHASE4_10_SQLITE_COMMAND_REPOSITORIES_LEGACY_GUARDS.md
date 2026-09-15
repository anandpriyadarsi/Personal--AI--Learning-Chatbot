# Phase 4.10 — Writable SQLite Command Repositories + Legacy Writer Guard Wiring

## Starting point

Phase 4.10 starts from `phase4/structured-cutover` at:

`b76d262b98abacff1a4481ce5b11f499c7f25e8c`

`feat: add Phase 4.9 SQLite authority promotion foundation`

Phase 4.1–4.8, the Final Phase 4 Structured Reconciliation Gate, and Phase 4.9
remain intact.

## Objective

Phase 4.10 adds a **transaction-safe relational command surface** for the
structured SQLite schema and wires the Phase 4.9 legacy-writer guard into both
the Phase-4 legacy JSON repository adapters and the existing top-level
procedural structured-data writer functions.

It deliberately does **not** perform the authority switch.

The repository remains in the pre-promotion state until the later, explicit
locked cutover changes the authority-control file.

## Authority rules

The command repositories accept:

- an already-open `sqlite3.Connection`; and
- an explicit authority-control path.

They never open `data/learning_assistant.db` themselves.

Before every command they read the Phase 4.9 control state. A write is permitted
only when the same atomic state says:

- `storage_backend = sqlite`; and
- `legacy_writes_blocked = true`.

Therefore simply importing, constructing, testing, or committing Phase 4.10
cannot mutate a Phase 3/4 shadow database.

In `legacy` and `dual_read` states the new SQLite command surface fails closed
with `SQLiteAuthorityNotActiveError`.

## New SQLite command repositories

`personal_learning_assistant/repositories/sqlite/command_repositories.py`
contains six explicit command repositories.

### `SQLiteCourseCommandRepository`

Supports relational commands for:

- semesters;
- courses;
- semester/course enrollment and credits;
- topics;
- active-course setting;
- explicit soft deletion for courses/topics.

Course document links are **not** written here. They were explicitly deferred by
Phase 3/4 to the knowledge/document boundary and remain a Phase 5 concern.

### `SQLiteAssessmentCommandRepository`

Supports:

- assessment upsert;
- atomic replacement of assessment-topic relationships;
- explicit assessment soft deletion.

Relationship validation happens before destructive replacement so a bad topic
reference cannot erase the previous mapping set.

### `SQLiteQuestionCommandRepository`

Supports:

- question upsert;
- atomic question-source replacement;
- atomic question-topic mapping replacement;
- attempt upsert;
- mistake-event upsert;
- explicit question soft deletion.

The command surface preserves unresolved source evidence through
`raw_source_label`; it does not invent Phase 5 document/resource/note IDs.

### `SQLiteLearningProgressCommandRepository`

Supports:

- learning-memory entry upsert;
- topic-progress event upsert;
- course progress-snapshot upsert.

Memory entries, topic progress events, and snapshots remain distinct concepts.
No command recalculates historic evidence merely to make it match a current
engine.

### `SQLiteStudyPlanCommandRepository`

Supports:

- plan-header upsert;
- atomic replacement of ordered plan items.

The repository writes persisted plan evidence only. It never invokes weekly,
multi-course, or intelligent planning engines.

### `SQLiteGradeCalendarCommandRepository`

Supports:

- grade-scale upsert;
- atomic grade-band replacement;
- semester/course credit updates;
- semester grade settings;
- manual grade entries;
- semester results;
- academic events.

It does not treat the planning grade scale as verified policy unless the caller
explicitly supplies verified evidence.

## Transaction policy

Every public write command:

1. verifies SQLite authority is active;
2. starts `BEGIN IMMEDIATE`;
3. validates required relationship rows;
4. applies one logical command;
5. commits only on success;
6. rolls back on any exception.

Nested transactions are rejected instead of silently committing somebody else's
transaction.

The `replace_*` commands prepare and validate their incoming rows before deleting
an old relationship set whenever the relationship can be validated in advance.

## Relational-ID boundary

Phase 4.10 command repositories intentionally accept **relational SQLite IDs**.
They do not guess whether an arbitrary legacy string is a course ID, code, topic
label, question key, or migration-ledger identity.

That resolution belongs to the application compatibility/routing layer. Keeping
it out of these command repositories prevents hidden fuzzy matching from becoming
part of authoritative persistence semantics.

This is why Phase 4.10 is not yet permission to flip production authority.

## Legacy JSON writer guard

`personal_learning_assistant/repositories/authority_guard.py` defines the shared
repository-level guard.

The authority-control file is inferred outside the legacy `data/` directory as:

`<project>/.phase4_authority.json`

Keeping it outside `data/` prevents the Phase 3 legacy source scanner from
mistaking backend control state for another user JSON source.

The following existing legacy repository adapters now call the guard before
writing:

- `LegacyJsonCourseRepository`
- `LegacyJsonAssessmentRepository`
- `LegacyJsonQuestionRepository`
- question-topic and attempt/performance adapters through question-repository
  inheritance
- `LegacyJsonLearningProgressRepository`
- `LegacyJsonStudyPlanRepository`
- `LegacyJsonGradeCalendarRepository`

Behavior is unchanged while the control file is missing, `legacy`, or
`dual_read`. Once the atomic control state becomes SQLite-authoritative, these
writers raise `LegacyWriteBlockedError` **before** changing source bytes.

The course repository guard wiring preserves the Phase 2 dependency boundary:
`personal_learning_assistant.repositories.json.course_repository` continues to
use `personal_learning_assistant.domain.course_normalization` and does **not**
reintroduce an import of the root compatibility facade `course_manager`.

## Procedural compatibility-writer guard wiring

The existing top-level structured writer functions are **not rerouted to SQLite
yet**, but they now call the same fail-closed guard immediately before any
legacy JSON mutation:

- `course_manager.save_course_data`
- `assignment_exam_assistant.save_store`
- `assessment_question_workspace.save_store`
- `learning_memory.save_memory`
- `academic_progress.save_history`
- `weekly_planner.save_store`
- `multi_course_planner.save_store`
- `intelligent_study_planner.save_store`
- `semester_grade_intelligence.save_config`

This does not change behavior while authority is missing, `legacy`, or
`dual_read`. Once a later locked cutover atomically promotes SQLite, direct
legacy compatibility calls cannot bypass the repository-layer protection. The
guard is evaluated before directory creation, temporary-file creation, or JSON
replacement.

Phase 4.10 still does **not** route these public APIs to the SQLite command
repositories. That selection remains the Phase 4.11 compatibility-routing unit,
which must be green before production authority is actually promoted.

## Existing Phase 4 read repositories

Phase 4.1–4.8 SQLite repositories remain shadow/read-only and are not edited.
Their regression contracts continue to require `legacy`/`dual_read` only.

Phase 4.10 does not weaken those tests or silently add an SQLite-authority mode to
an old dual-read factory.

The new command repositories are a separate mutation surface so shadow read
semantics and authority-write semantics cannot be confused.

## Tests

`tests/test_phase4_sqlite_command_repositories.py` covers:

- Phase 2 course repository dependency direction remains intact;
- explicit connection requirement;
- incomplete-schema rejection;
- commands disabled in legacy state;
- commands disabled in dual-read state;
- course/semester/topic/active-course writes after SQLite authority;
- explicit soft deletion;
- assessment/topic relational writes;
- atomic rollback when relationship validation fails;
- questions, sources, mappings, attempts and mistakes;
- learning memory, progress events and snapshots;
- study plans and ordered plan items;
- grade scales, bands, credits, settings, results and academic events;
- nested-transaction rejection;
- control-file placement outside `data/`;
- all guarded legacy repository adapters refusing writes after promotion;
- all direct procedural structured writers refusing writes after promotion;
- guards firing before a missing `data/` directory can be created;
- guarded legacy source bytes remaining unchanged on rejection;
- missing/dual-read control preserving old JSON write behavior for repository and procedural paths;
- SQLite commands not touching legacy JSON bytes;
- no implicit production database path or connection opener.

All databases and JSON stores used by focused tests are temporary/synthetic.

## Non-goals

Phase 4.10 does not:

- modify `main`;
- modify `main` branch;
- create a development branch;
- create/open the production SQLite database implicitly;
- change the authority-control state;
- run the final delta import;
- copy a shadow DB into the production path;
- modify Phase 4.1–4.8 shadow readers/backends;
- modify Phase 3 migration importers or migration ledger history;
- reroute top-level procedural application APIs to SQLite yet;
- migrate course document links;
- migrate Notes, Resources, Obsidian, documents, RAG, Dashboard 2, or agents;
- start Phase 5;
- delete or rewrite legacy JSON.

## Gate

Run:

```powershell
.\phase4_fix10_gate.ps1
```

The gate pins Phase 4.9 commit `b76d262`, runs the focused Phase 4.10 tests,
Phase 4.9 authority-promotion regression, the final Phase 4 reconciliation
regression, Phase 4.1–4.8 regressions, all Phase 3 tests, the full suite,
compilation, dependency checks, `git diff --check`, and repository hygiene.

It also verifies that:

- the existing shadow readers/backends are unchanged;
- the old procedural modules change only by adding pre-write authority guards;
- no production DB/control file/private data was created or tracked;
- only the declared Phase 4.10 files changed.

## Next boundary

After Phase 4.10 is committed and pushed, the next required unit is:

**Phase 4.11 — Structured Authority Routing + Compatibility Writer Cutover**

That unit must route existing application-visible structured reads/commands to
legacy/dual-read/SQLite backends according to the explicit authority-control
state, while preserving public signatures.

Only after that routing gate is green should the final locked sequence run:

1. acquire mutation lock;
2. rehash structured legacy sources;
3. import the final delta;
4. run reconciliation/integrity checks;
5. take final JSON + SQLite backup;
6. atomically write `storage_backend=sqlite` + legacy-writes-blocked evidence;
7. release the lock;
8. run post-promotion smoke/reconciliation tests.
