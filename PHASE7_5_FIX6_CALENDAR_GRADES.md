# Phase 7.5.6 — Calendar & Grades

## Objective

Expose existing academic deadlines and stored grade evidence through the local
Flask interface without adding a browser write path or changing structured
storage authority.

Phase 7.5.6 is a read-only projection layer. It does not create calendar
events, reschedule assessments, estimate missing grades, calculate an SGPA that
is not explicitly stored, save grade configuration, migrate data, or switch
authority.

## Starting point

- Branch: `phase7/deprecation-observation`
- Required base commit: `1f89b26135a7022349eba9d88199921cd9d58ff2`
- Phase 7.5.1–7.5.5 are treated as completed and immutable except for the
  intentionally extended shared route/navigation files.

## Web surface

`GET /calendar`

The page combines:

### Academic calendar

Stored assessments are projected into four read-only groups:

- overdue
- upcoming (within 30 days)
- later
- completed

The page shows stored course identity, title, assessment type, status, due date,
due time when present, and weightage when present. No date is changed and no
calendar record is generated.

### Grades

The page shows only existing semester-grade configuration/evidence:

- semester identity
- target SGPA if configured
- grading-scale source and verification flag
- stored grade-scale bands
- configured course credits
- explicit stored course score / letter / grade point fields
- an explicit semester result when one is already persisted

Missing grade evidence stays missing. Phase 7.5.6 does not infer a letter grade,
grade point, course result, or SGPA from assessments.

## Authority-safe reads

`calendar_grades_dashboard_service.py` lazily imports the existing structured
authority router and legacy grade/calendar adapter only when `/calendar` is
requested.

It reads:

- `semester_grade_config` through `maybe_load_sqlite_structured_store(...)`
  when SQLite authority is active, otherwise through the side-effect-free
  legacy grade repository;
- `assessments` through the same structured-authority router, otherwise through
  the legacy assessment store exposed by the grade/calendar adapter;
- course identity through `CourseService(RoutedCourseRepository())`.

The Flask application factory therefore stays isolated from grade/calendar
storage engines during startup.

## Safety boundary

Phase 7.5.6 contains no:

- POST `/calendar` route;
- HTML form;
- grade save call;
- assessment save call;
- direct SQLite write;
- direct JSON write;
- calendar mutation;
- grade inference;
- database migration;
- deletion;
- authority switch.

Read failures are caught at the web boundary and render a safe unavailable
state without exposing exception content.

## Files

- `personal_learning_assistant/services/calendar_grades_dashboard_service.py`
- `personal_learning_assistant/ui/web/routes.py`
- `personal_learning_assistant/ui/web/templates/base.html`
- `personal_learning_assistant/ui/web/templates/calendar.html`
- `tests/test_phase7_5_calendar_grades.py`
- `PHASE7_5_FIX6_CALENDAR_GRADES.md`
- `phase7_5_fix6_gate.ps1`

No dependency or CSS change is required.

## Gate

Run:

```powershell
.\phase7_5_fix6_gate.ps1
```

The gate verifies focused Calendar & Grades behavior, a real authority-routed
read, GET-only browser behavior, all earlier Phase 7.5 web regressions, Phase
7.1–7.4 regressions, the promotion-aware complete suite, compilation,
dependency consistency, SQLite integrity/foreign keys, scope protection, and
production/runtime immutability.

Do not commit until the complete gate reports `PASS`.
