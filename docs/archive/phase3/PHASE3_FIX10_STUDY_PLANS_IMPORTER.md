# Phase 3.1 Fix 10 — Weekly / Multi-course / Intelligent Study Plans Importer

## Purpose

Fix 10 imports the legacy study-planning stores into the temporary Phase 3
SQLite schema after the earlier course/topic, assessment, question, mapping,
performance, and learning-progress import work.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

This fix does not create `data/learning_assistant.db`, does not rewrite JSON, and
does not make SQLite the application storage backend.

## Sources

`personal_learning_assistant/migration/study_plans_importer.py` imports verified
scanner snapshots from:

1. `data/weekly_study_plans.json`
2. `data/multi_course_weekly_plans.json`
3. `data/intelligent_study_plans.json` — optional/absent is valid

The importer requires the first two stores to be present and `valid_json`. The
intelligent-planner store is optional because it may not exist in older project
states.

## Targets

Fix 10 writes only to existing Fix 2 tables:

- `study_plans`
- `study_plan_items`
- `migration_imports`

Plan source content remains the authority. SQLite stores structured plan
metadata, item rows, exact import evidence, and review warnings.

## Supported legacy shapes

The importer accepts both older fixture-style stores and the current planner
outputs.

### Weekly planner

Supports:

- `plans[].course_id`
- `plans[].total_minutes`
- `plans[].daily_minutes * plans[].study_days`
- `plans[].days[].tasks[]`
- `plans[].days[].sessions[]`

### Multi-course planner

Supports:

- `plans[].requested_minutes`
- `plans[].stored_minutes`
- `plans[].items[]`
- `plans[].days[].sessions[]`
- per-item/session `course_id`, `topic`, `minutes`, and action text

### Intelligent study planner

Supports:

- `kind = today`
- `kind = week`
- `available_minutes`
- `minutes_per_day * study_days`
- top-level `sessions[]`
- weekly `days[].sessions[]`

## Resolution policy

Course links resolve only through existing Fix 4 migration-ledger evidence for
`data/courses.json`. The importer accepts exact legacy course IDs and course-code
fallback identities.

Topic links resolve only when exactly one live imported topic belongs to the
resolved course and has the same normalized topic name. No fuzzy matching,
question-text inference, or cross-course topic guessing is performed.

Unresolved or ambiguous course/topic references are imported with nullable
foreign keys and review warnings rather than being guessed.

## Identity and idempotency

Plan and item primary IDs are deterministic UUID5 values from portable source
path + entity type + legacy identity. The source hash is deliberately excluded
from target IDs.

This means:

- unchanged re-import creates no duplicate rows;
- changed source hashes record new `migration_imports` evidence;
- the same logical legacy plan/item can update the same stable SQLite target;
- omitted old items are not treated as deletion authority.

When a changed plan is re-imported, source-owned old item rows are staged as
`superseded` only to avoid `(plan_id, plan_date, ordinal)` conflicts. The current
snapshot then writes the active item rows back into stable positions.

## Safety decisions

Fix 10 intentionally does **not**:

- generate a new study plan;
- call planner engines;
- run the academic-priority algorithm;
- mark any plan item completed;
- create study-session history;
- update learning memory or topic mastery;
- infer assessment/resource/note links from action text;
- delete legacy plan history because a newer snapshot omits it.

## Verification

Run:

```powershell
.\phase3_fix10_gate.ps1
```

The focused tests verify:

1. weekly and multi-course fixture plans import into `study_plans` and
   `study_plan_items`;
2. optional `intelligent_study_plans.json` absence is accepted;
3. present intelligent planner output imports correctly;
4. source JSON bytes remain unchanged;
5. exact course/topic links resolve only when safe;
6. unresolved course/topic references are reviewable and not guessed;
7. identical re-import is a no-op;
8. changed source hashes update stable targets and add new ledger evidence;
9. malformed plan shapes fail without partial writes;
10. a source changed after scan is rejected before writes.

The gate also runs every Phase 3 test, the full project regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Non-goals

Fix 10 does **not**:

- create/populate production `data/learning_assistant.db`;
- switch services from JSON to SQLite;
- import grade settings or academic calendar events;
- import resources, notes, vault files, or documents;
- reverse-export or reconcile all migrated data;
- disable legacy JSON writers.

Those remain later Phase 3/Phase 4 units.
