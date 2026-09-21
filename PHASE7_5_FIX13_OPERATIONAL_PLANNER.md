# Phase 7.5.13 — Operational Planner: Tasks, Calendar & Monthly Plan

## Scope

Phase 7.5.13 makes the ANVAYA planning/calendar web layer operational while preserving existing academic authorities.

Implemented domains:

- safe monthly YAML preview + approval
- import provenance and idempotency
- general P0/P1/P2 planner tasks
- recurring personal routines
- operational month/week/day calendar views
- explicit confirmed assessment scheduling
- daily agenda generation and approval
- completion/skip tracking
- daily review + bounded rollover
- tomorrow draft generation
- weekly review persistence
- Home "Today" summary

## Existing authority reused

The phase reuses:

- `assessments`
- `academic_events`
- `study_plans`
- `study_plan_items`
- `study_sessions`

The phase does not replace those domains.

## Migration

`0006_operational_planner.sql` adds:

- `month_plan_imports`
- `month_plan_import_items`
- `planner_tasks`
- `routine_templates`
- `daily_agendas`
- `daily_agenda_items`
- `task_rollover_events`
- `daily_reviews`
- `weekly_reviews`

## Supported import schema

Only:

`anvaya.external.month_plan/1.0.0`

The parser uses `yaml.safe_load` and `PyYAML==6.0.3`.

Preview is side-effect free. Approval requires the same SHA-256 reviewed in preview.

## Mid-sem rule

Until the official subject-by-subject datesheet is supplied:

- subject exam date remains null
- start time remains null
- end time remains null
- venue remains null
- no subject-specific academic-event row is generated

The 5–10 October academic-calendar period may remain visible as a planning window.

## Recurrence subset

Supported:

- `FREQ=DAILY`
- `FREQ=WEEKLY`
- `BYDAY`
- `UNTIL`
- `COUNT`
- imported excluded dates
- imported additional dates

Unsupported recurrence components fail validation.

Occurrences are calculated for queries; recurring routines are not expanded into 31 persistent rows.

## Daily capacity and rollover

- flexible task ceiling: 5
- deep-work limit: 1 on heavy fixed-commitment days, otherwise 3
- shutdown boundary: 22:10
- unschedulable work remains unscheduled instead of crossing fixed commitments/shutdown
- P0 carry candidate max: 1
- P1 carry candidate max: 1
- P2 automatic carry: 0
- task rows are not cloned during rollover

## NCC presentation

NCC status is not introduced as a planner/dashboard identity field. If historical source material contains it for timetable interpretation, that remains source context rather than primary UI identity.

## Deferred

Not included:

- Google Calendar synchronization
- push/mobile reminders
- email deadline ingestion
- arbitrary PDF plan ingestion
- LLM schedule optimization
- autonomous Academic Agent task execution
- native OS notifications
- Phase 7.5.14

## Real October plan acceptance

The real `ANVAYA_MONTH_PLAN_v1.1.yaml` is not embedded into source code.

After implementation is committed and migration 0006 is safely applied to production SQLite:

1. Open **Planning → Month Plan**.
2. Upload the YAML.
3. Review the dry-run preview.
4. Confirm all individual mid-sem slots remain waiting/empty.
5. Check conflicts/warnings.
6. Approve only after human review.
7. Verify Month/Week/Day calendar and a generated daily agenda.

Runtime personal-plan data is not part of the implementation commit.
