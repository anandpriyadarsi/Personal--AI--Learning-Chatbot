# Phase 4.8 — Grades + Academic Calendar SQLite Dual-Read Cutover Foundation

## Starting point

Phase 4.8 starts from `phase4/structured-cutover` at the completed Phase 4.7 commit:

`c97629d5e741f2c4d4a03713576b7516d649180d`

Phase 4.1–4.7 remain unchanged.

## Objective and authority boundary

Phase 4.8 introduces read-only SQLite shadow support and semantic parity for two related but distinct domains:

1. Semester Grades / Grade Configuration
2. Academic Calendar assessment-deadline events

> Legacy JSON/current storage remains authoritative during Phase 4.8.
> SQLite is shadow-read only.

The existing public modules remain unchanged. `semester_grade_intelligence.py` continues to own the user-visible grade configuration and its legacy writer. `assignment_exam_assistant.py` continues to own assessment deadlines. `academic_calendar_planner.py` remains an advisory/read-only projection over assessments; Phase 4.8 does not replace its algorithms.

There is no `sqlite` or `sqlite_only` authority mode and no dual write.

## Architecture inspected

The implementation follows the actual Phase 4 branch and Phase 3 Fix 11 model, including:

- `semester_grade_intelligence.py` V12.1 grade configuration and SGPA planning semantics;
- `assignment_exam_assistant.py` persisted assessment deadline authority;
- `academic_calendar_planner.py` V12.2 deadline/calendar views;
- Phase 3 Fix 11 `grades_calendar_importer.py`;
- Phase 3 tables `grade_scales`, `grade_bands`, `semester_grade_settings`, `manual_grade_entries`, `semester_results`, `academic_events`, and `semester_courses.credits_milli`;
- migration-ledger course/semester/assessment relationships;
- Phase 4.1–4.7 legacy-authoritative dual-read conventions.

## Repository seam

Phase 4.8 adds:

- `LegacyJsonGradeCalendarRepository`
- `SQLiteGradeCalendarRepository`
- `GradeCalendarBackendConfig`
- `DualReadGradeCalendarRepository`
- structured parity diagnostics

The legacy adapter reads `data/semester_grade_config.json` and `data/assessments.json` without creating missing files during reads. Grade writes, when explicitly invoked through the seam, still write only the legacy grade JSON.

The SQLite repository requires an already-open `sqlite3.Connection`. It never accepts a database path and never creates a database.

## Grade parity

Where the optional legacy grade configuration exists, Phase 4.8 compares persisted semantics including:

- grade-source presence and source hash/version evidence;
- configured semester identity;
- target SGPA;
- grade-scale thresholds;
- letter grades;
- grade points;
- grade-scale source and verified/planning status;
- active-from / active-to evidence where present;
- configured course credits;
- explicit manual grade point / letter / score evidence;
- explicit semester-result values when the legacy source actually stores them;
- current course/semester ownership;
- scale-to-settings relationship;
- migration legacy identities and raw course references;
- retained older source-hash rows as historical/deferred evidence.

The application default grade scale remains a planning aid. Phase 4.8 does not silently mark it official or verified.

Projected grades, projected SGPA, required remaining average, and target-SGPA scenarios are not persisted grade facts and are therefore not written into SQLite by Phase 4.8.

## Academic Calendar parity

The project does not have a separate authoritative calendar JSON store for V12.2. The authoritative persisted deadline data remains `data/assessments.json`.

Phase 3 Fix 11 materializes assessment deadlines into source-linked `academic_events` rows. Phase 4.8 therefore compares the authoritative persisted assessment deadline semantics against those shadow rows:

- one current event for each current assessment with a valid due date;
- event kind `assessment_deadline`;
- assessment source/reference ownership;
- title;
- all-day versus timed deadline;
- `starts_at` date/time;
- scheduled/completed/cancelled state derived by the established Fix 11 policy;
- assessment-to-course ownership;
- semester link when safely resolved;
- missing relational targets;
- stale/historical event evidence from older source hashes.

An assessment without a current due date is not converted into a fabricated active calendar event.

## Important distinction: calendar persistence vs calendar algorithms

Phase 4.8 cuts over only persisted/source-linked deadline evidence. It does **not** rerun or persist:

- 7-day/30-day view calculations;
- workload grouping;
- overload detection;
- deadline-pressure scores;
- recommended study blocks;
- study-plan generation.

Those calculations remain application logic over authoritative assessment data. Dual-read parity never executes them merely to manufacture SQLite values.

## Dual-read flow

Supported modes are only `legacy` and `dual_read`.

In `dual_read`:

1. read the authoritative legacy grade/deadline state;
2. retain that result;
3. independently read SQLite shadow state;
4. compare semantic and structural parity;
5. record structured diagnostics;
6. return the legacy result unchanged.

SQLite read failures, comparison failures, and diagnostic-sink failures never replace a successful legacy read.

## Structured diagnostics

Diagnostics follow the established Phase 4 style and include:

- domain;
- status;
- key;
- severity;
- legacy value;
- SQLite value;
- message;
- entity type;
- course/reference context where useful.

Statuses remain explicit (`match`, `mismatch`, `deferred`, `error`) rather than silently repairing data.

## Structural validation

The SQLite repository validates relational rows rather than trusting migration-ledger claims alone. It detects, where applicable:

- ledger target missing from the relational table;
- duplicate current legacy identity pointing at multiple targets;
- current grade-band target set differing from the current scale relationship;
- grade settings pointing at the wrong scale;
- missing semester-course credit target;
- manual grade attached to the wrong semester;
- missing semester result;
- academic event attached to the wrong course;
- missing current assessment relationship;
- incorrect event/reference/source kinds;
- missing academic-event target.

The migration ledger is supporting evidence, not authority over the relational database.

## History treatment

Phase 3 Fix 11 preserves changed grade-scale versions and manual-grade history. Phase 4.8 does not collapse those rows into current state or delete them. Evidence from older source hashes is reported as deferred historical evidence.

Likewise, changed assessment snapshots can update the stable current deadline event while old ledger observations remain history.

## Side-effect protections

Phase 4.8 dual reads do not call:

- grade projection tools;
- SGPA projection/target engines;
- calendar workload algorithms;
- deadline study-block generation;
- assessment writers;
- planner writers;
- progress/memory writers.

Focused tests verify:

- legacy source bytes/hashes remain unchanged during reads;
- SQLite logical rows remain unchanged;
- `connection.total_changes` remains unchanged;
- repeated reads are deterministic;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no violations;
- SQLite mutation attempts fail explicitly;
- explicit dual-read grade saves write only the legacy JSON authority.

All Phase 4.8 fixtures are synthetic and test databases are temporary.

## Files added

Phase 4.8 adds only:

- `personal_learning_assistant/repositories/json/grade_calendar_repository.py`
- `personal_learning_assistant/repositories/sqlite/grade_calendar_repository.py`
- `personal_learning_assistant/repositories/grade_calendar_backend.py`
- `tests/fixtures/phase4/semester_grade_config.json`
- `tests/test_phase4_grades_calendar_dual_read.py`
- `PHASE4_FIX8_GRADES_ACADEMIC_CALENDAR_DUAL_READ.md`
- `phase4_fix8_gate.ps1`

## Gate

Run before committing:

```powershell
.\phase4_fix8_gate.ps1
```

The gate pins the exact Phase 4.7 baseline and requires focused Phase 4.8 tests, all Phase 4.1–4.7 regressions, all Phase 3 regression/safety tests, the complete pytest suite, Python compilation, dependency consistency, `git diff --check`, and repository-hygiene checks.

## Non-goals

Phase 4.8 does not:

- modify `semester_grade_intelligence.py`;
- modify `academic_calendar_planner.py`;
- modify `assignment_exam_assistant.py`;
- calculate or persist projected grades/SGPA;
- claim the planning grade scale is official;
- create general timetable/holiday/recurring events without a source;
- rerun calendar pressure/overload/study-block algorithms for parity;
- modify study plans;
- modify learning memory/progress;
- cut over notes/resources/RAG/Obsidian/dashboard/agent domains;
- begin Phase 5;
- promote SQLite to sole authority.

After Phase 4.8 passes, the next step should be a final Phase 4 structured-cutover/reconciliation gate before any authority switch is considered.
