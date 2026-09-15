# Phase 4.7 — Study Plans SQLite Dual-Read Cutover Foundation

## Starting point

Phase 4.7 starts from `phase4/structured-cutover` at completed Phase 4.6 commit:

`6959b06e83986b07f3a01b45ca0a3e8459d708cb`

Phase 4.1–4.6 remain unchanged.

## Objective and authority boundary

Phase 4.7 introduces read-only SQLite shadow support and semantic parity for the
three persisted study-plan stores already used by the application:

- V9.1 weekly course plans — `data/weekly_study_plans.json`
- V9.2 multi-course weekly plans — `data/multi_course_weekly_plans.json`
- V11 intelligent today/week plans — `data/intelligent_study_plans.json`

> Legacy JSON/current planner storage remains authoritative during Phase 4.7.
> SQLite is shadow-read only.

The public planner modules are deliberately not rewired or rewritten:
`weekly_planner.py`, `multi_course_planner.py`, and
`intelligent_study_planner.py` remain the writers and application APIs.

There is no SQLite-only mode and no dual write.

## Architecture inspected

The implementation follows the actual current branch and Phase 3 Fix 10 model:

- `weekly_planner.py` V9.1 store and current `days[].sessions[]` shape;
- `multi_course_planner.py` V9.2 course allocation and day/session shape;
- `intelligent_study_planner.py` V11 `today` and `week` shapes;
- Phase 3 Fix 10 `study_plans_importer.py`;
- Phase 3 `study_plans` and `study_plan_items` tables;
- migration-ledger course/topic resolution evidence;
- the legacy-authoritative Phase 4.1–4.6 dual-read pattern.

Phase 3 Fix 10 imports stored plan decisions only. It does not run planner
engines or priority algorithms. Phase 4.7 preserves the same rule.

## Repository seam

Phase 4.7 adds:

- `LegacyJsonStudyPlanRepository`
- `SQLiteStudyPlanRepository`
- `StudyPlanBackendConfig`
- `DualReadStudyPlanRepository`
- structured parity diagnostics

`LegacyJsonStudyPlanRepository` reads the three planner stores without creating
missing files. Explicit writes remain legacy-only and use temp-file replacement.

`SQLiteStudyPlanRepository` requires an already-open `sqlite3.Connection`; it
never accepts a database path and never creates a database.

## Legacy and dual-read modes

Supported backend modes are only:

- `legacy`
- `dual_read`

In `dual_read`:

1. the legacy state is read first;
2. that exact result remains authoritative;
3. SQLite is read independently;
4. semantic and structural parity are compared;
5. diagnostics are recorded;
6. the legacy result is returned unchanged.

SQLite failures, comparison failures, and diagnostic-sink failures never replace
a successful legacy read.

## Parity coverage

Phase 4.7 compares persisted plan semantics including:

- source presence, version, and hash;
- exact raw stored plan JSON through migration-ledger evidence;
- plan identity / legacy key;
- plan kind and horizon;
- start/end dates;
- requested and allocated minutes;
- plan status;
- planner engine name/version;
- rationale/message semantics imported by Phase 3;
- created/updated timestamps where persisted;
- plan item identity and plan ownership;
- plan item date and ordinal/order;
- raw course identity;
- raw topic/task identity;
- minutes;
- action text;
- import reason;
- score/priority value;
- item status;
- actual course/topic relationships in SQLite;
- stale/historical rows from older source hashes;
- unledgered live study-plan rows.

The backend does not regenerate a plan to make parity pass.

## Weekly / Multi-course / Intelligent distinctions

The three plan families remain distinct:

- V9.1 weekly plans are single-course weekly plans;
- V9.2 multi-course plans preserve course allocation and multi-course sessions;
- V11 intelligent plans preserve `today` versus `week` kind and their stored
  sessions.

They share one SQLite schema, but Phase 4.7 does not collapse their legacy
identity or engine version.

## Structural validation

The SQLite repository validates live relational state rather than trusting the
migration ledger alone. It detects:

- current ledger target missing from `study_plans`;
- current item ledger target missing from `study_plan_items`;
- duplicate current legacy identities mapping to different targets;
- item moved to the wrong plan;
- item moved to the wrong course;
- item moved to the wrong topic;
- topic/course cross-ownership;
- missing/deleted course or topic targets;
- unexpected assessment/resource/note relationships in Fix 10-owned rows;
- unledgered live plan/item rows.

Ledger target IDs are supporting evidence, not a substitute for inspecting the
relational rows.

## Historical rows

Phase 3 Fix 10 uses stable target IDs and does not treat omission from a later
legacy snapshot as deletion authority. Rows evidenced only by older source
hashes are therefore reported as `deferred` historical evidence rather than
silently promoted to current authority or automatically deleted.

## Optional V11 store

`data/intelligent_study_plans.json` is optional, matching Phase 3 Fix 10. If it
is absent in both legacy storage and SQLite migration evidence, presence parity
passes. No file is created merely to perform a read.

## Side-effect protections

Phase 4.7 dual reads do not call planner generation or planner save functions.
They do not call:

- `record_progress_snapshot()`;
- course priority engines;
- assessment-performance engines;
- learning-memory writers;
- topic-status writers;
- grade/calendar writers.

Focused tests verify that:

- planner JSON source bytes/hashes are unchanged by reads;
- SQLite `study_plans` and `study_plan_items` rows are unchanged;
- `connection.total_changes` remains unchanged;
- repeated reads are deterministic;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no violations;
- SQLite mutations fail explicitly;
- dual-read saves affect only legacy JSON.

All Phase 4.7 fixtures are synthetic and SQLite test databases are temporary.

## Files added

Phase 4.7 adds only:

- `personal_learning_assistant/repositories/json/study_plan_repository.py`
- `personal_learning_assistant/repositories/sqlite/study_plan_repository.py`
- `personal_learning_assistant/repositories/study_plan_backend.py`
- `tests/fixtures/phase4/weekly_study_plans.json`
- `tests/fixtures/phase4/multi_course_weekly_plans.json`
- `tests/fixtures/phase4/intelligent_study_plans.json`
- `tests/test_phase4_study_plans_dual_read.py`
- `PHASE4_FIX7_STUDY_PLANS_DUAL_READ.md`
- `phase4_fix7_gate.ps1`

## Gate

Before committing run:

```powershell
.\phase4_fix7_gate.ps1
```

The gate requires the exact Phase 4.6 baseline, the correct branch, only the
approved Phase 4.7 change set, focused Phase 4.7 tests, every Phase 4.1–4.6
regression, all Phase 3 tests, the full pytest suite, compilation, dependency
consistency, `git diff --check`, and repository-hygiene checks.

## Rollback

Before final structured cutover, rollback remains simple: select `legacy` or
remove the Phase 4.7 observational adapter. The planner modules and JSON writers
remain unchanged and SQLite has no authority over study plans.

## Non-goals

Phase 4.7 does not:

- modify `weekly_planner.py`;
- modify `multi_course_planner.py`;
- modify `intelligent_study_planner.py`;
- regenerate or recalculate saved plans;
- create study-session history;
- mark plan items completed;
- change topic mastery/confidence;
- change learning memory/progress;
- cut over grades or academic calendar;
- cut over notes/resources/RAG/Obsidian/dashboard/agent domains;
- begin Phase 5;
- promote SQLite to sole authority.

The next Phase 4 boundary is Grades + Academic Calendar.
