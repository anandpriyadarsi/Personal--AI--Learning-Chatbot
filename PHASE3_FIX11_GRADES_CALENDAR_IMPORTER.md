# Phase 3.1 Fix 11 — Grades + Academic Calendar Importer

## Purpose

Fix 11 completes the structured academic-data importer sequence after Fix 10.
It imports explicit legacy semester-grade configuration when that optional store
exists, and it creates source-linked academic calendar events from assessment
deadlines already imported by Fix 5.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

This fix does not create `data/learning_assistant.db`, rewrite a JSON file, make
SQLite the application backend, or claim that a planning grade scale is official.

## Sources and ordered prerequisites

`personal_learning_assistant/migration/grades_calendar_importer.py` consumes
verified scanner snapshots for:

1. `data/semester_grade_config.json` — optional; absence means “not configured”
2. `data/assessments.json` — required

Fix 4 must already have imported courses, semester placeholders, and
semester-course links. Fix 5 must already have imported the exact current hash
of `assessments.json`. The calendar importer refuses to project events when the
current assessment snapshot lacks complete Fix 5 ledger evidence.

## Grade targets

When the optional grade configuration exists and is valid, Fix 11 can write:

- `grade_scales`
- `grade_bands`
- `semester_grade_settings`
- `semester_courses.credits_milli`
- `manual_grade_entries`
- `semester_results`, only when a complete explicit result is present
- `migration_imports`

Legacy percentages are stored as basis points, while credits, grade points, and
SGPA are stored in milli-units using decimal half-up rounding.

### Truthful grade semantics

The legacy module describes its default scale as a planning aid rather than
official NITK policy. Fix 11 therefore imports a scale as unverified unless the
source explicitly marks it verified. It never derives an official result from
projections or manual overrides.

A semester result is inserted only when the source explicitly contains valid
earned credits, earned grade points, and SGPA. Partial/invalid result objects are
left for review, with their source bytes untouched.

### Scale history

Each normalized grade-scale definition receives a content fingerprint. An
unchanged definition reuses the same scale and band IDs. A genuinely changed
scale creates a new version, and `semester_grade_settings` points at that new
version. Older imported scale rows remain available instead of being silently
overwritten or deleted.

Manual grade entries are also evidence records: an unchanged explicit entry is
idempotent, while a changed grade becomes a new historical entry.

## Resolution policy

Semester and course links resolve only through Fix 4 migration-ledger evidence
from `data/courses.json`:

- `Semester 1`, `Legacy Semester 1`, and the raw legacy label `1` can resolve to
  the same explicit imported semester identity;
- a missing semester label can use the only imported semester, but never choose
  among multiple candidates;
- course IDs/codes must resolve exactly and the course must belong to the
  resolved semester;
- unresolved or ambiguous grade references are reported and never guessed.

The grade configuration is the first approved source in the migration sequence
that can fill deferred `semester_courses.credits_milli` values.

## Academic calendar projection

Each imported assessment with a valid due date receives one deterministic
`academic_events` row:

- `event_kind = assessment_deadline`
- `reference_type = assessment`
- `reference_id = <assessment ID>`
- `source_entity_type = assessment`
- `source_entity_id = <assessment ID>`

An assessment deadline is therefore never copied into the calendar without a
durable source link. Date-only deadlines become all-day events. A valid due time
creates a timed ISO date-time value. Assessment title/date/time/status changes
update the same stable calendar event after Fix 5 imports the changed snapshot.

An assessment with no valid due date creates no event. If a later authoritative
snapshot removes the date from an event previously projected by this importer,
the event is soft-deleted rather than left active with a stale deadline.

The event links to a semester only when its course belongs to exactly one
semester. With zero or multiple candidate semesters, the course link is kept and
the unresolved semester is reported without guessing.

## Idempotency and safety

The importer records portable source path/hash/version/legacy-key evidence in
`migration_imports`. It imports grades and events in one immediate transaction.

- identical re-import creates no duplicates or timestamp churn;
- changed source hashes create new ledger observations;
- stable assessment identities update the same calendar event;
- source files are hashed before parsing and again before commit;
- a source changed after scanning rolls back the complete Fix 11 transaction;
- a missing optional grade file that appears after scanning is treated as a
  source-change error;
- reports contain portable paths only, never a local Windows/user path.

## Verification

Run:

```powershell
.\phase3_fix11_gate.ps1
```

The focused tests verify:

1. scale, bands, target SGPA, course credit, manual grade, explicit semester
   result, and assessment deadline import correctly;
2. all source bytes remain unchanged;
3. the planning scale remains unverified by default;
4. identical re-import is a no-op;
5. absent grade configuration is accepted and reported as not configured;
6. changed assessment hashes update the same linked event, including timed
   deadlines;
7. changed scale definitions preserve old scale history and manual-grade
   history;
8. unresolved grade-course references remain reviewable and are not guessed;
9. assessments without dates create no calendar event;
10. malformed grade shapes and missing Fix 5 evidence fail before partial
    writes;
11. post-scan source changes are rejected;
12. SQLite integrity and foreign-key checks remain clean.

The gate also runs every Phase 3 test, the full regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Non-goals

Fix 11 does **not**:

- calculate projected course grades or SGPA;
- convert projections into official results;
- create general timetable/holiday/recurring calendar events without a source;
- run calendar workload or study-block algorithms;
- create or import study sessions;
- reverse-export or perform final cross-engine parity reconciliation;
- switch services from JSON to SQLite;
- disable or delete any legacy file or writer.

Those remain later Phase 3 reconciliation and Phase 4 cutover work.
