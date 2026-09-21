# Phase 7.5.13 — Operational Planner: Tasks, Calendar & Monthly Plan

**Status:** Draft for approval  
**Date:** 2026-09-20  
**Product:** ANVAYA — Personal Learning Intelligence  
**Baseline:** `main` after Phase 7.5.12.1 and the Obsidian deep-link fix (`8d63607`)  
**Primary external planning profile:** `ANVAYA_MONTH_PLAN_v1.1.yaml`

## 1. Purpose

Phase 7.5.13 turns ANVAYA from a mostly read-oriented academic dashboard into an operational planning system that can run a real month.

The phase must support a reusable monthly-plan import workflow and then turn that plan into:

- calendar commitments;
- recurring routines;
- general tasks;
- study-plan items;
- a saved daily agenda;
- scheduled focus blocks;
- bounded task rollover;
- daily reviews;
- weekly evidence reviews;
- month/week/day calendar views;
- later updates when official exam dates or deadlines become available.

The October 2026 plan is the first real import fixture, but the implementation must not hard-code October.

## 2. Product Outcome

At the end of Phase 7.5.13, ANVAYA should support this loop:

```text
Import monthly YAML plan
        ↓
Validate + preview + conflict report
        ↓
Approve
        ↓
Calendar + routines + tasks + study plan become operational
        ↓
Generate today's agenda
        ↓
Review / schedule / complete / move tasks
        ↓
Close the day
        ↓
Bounded carry-forward proposal
        ↓
Approve tomorrow
        ↓
Weekly evidence report
        ↓
Next week's top 3
```

The system should feel like an academic operating system, not a static web page.

## 3. Important Presentation Decisions

### 3.1 NCC status

`ncc_status` may remain internal planning context where timetable logic genuinely needs it, but it must not appear as a prominent profile/status field on the monthly-plan cover or primary dashboard identity.

### 3.2 Mid-sem dates

The individual mid-sem datesheet has not been officially released.

Therefore:

- subject-specific exam `date`, `start_time`, `end_time`, and `venue` remain null;
- the official academic-calendar exam *window* may remain visible as a planning period;
- ANVAYA must not invent a subject order or time;
- no subject-specific calendar event is created until a confirmed slot is supplied;
- later, the user can add/update the official slot from the Calendar UI without rebuilding the whole monthly plan.

## 4. Source and Authority Model

Authority order for the operational planner:

1. explicit user edits inside ANVAYA;
2. officially confirmed academic events/deadlines;
3. approved monthly-plan import;
4. existing saved study plans;
5. generated daily proposals.

The imported YAML is a planning source, not permission to overwrite user edits silently.

The imported plan must retain:

- `plan_id`;
- `schema_version`;
- source filename;
- SHA-256;
- import timestamp;
- source external IDs;
- provenance on every imported entity.

## 5. Existing Architecture to Reuse

The current SQLite schema already contains:

- `assessments`
- `academic_events`
- `study_plans`
- `study_plan_items`
- `study_sessions`

Phase 7.5.13 must reuse these where their meaning fits.

Do not create parallel replacements for assessments, academic events, study plans, or study sessions.

The current Planning and Calendar web surfaces are read-only adapters. Phase 7.5.13 adds new write-capable operational services without putting SQL or business rules into Flask routes.

## 6. New Persistence Model

Add migration:

```text
0006_operational_planner.sql
```

### 6.1 `month_plan_imports`

Tracks approved or previewed external month plans.

Fields:

```text
id
plan_id
schema_version
source_filename
source_sha256
title
starts_on
ends_on
timezone
status              -- previewed | active | superseded | rejected
created_at
approved_at
superseded_at
```

Constraints:

- one active revision per `plan_id`;
- date range valid;
- timezone non-empty.

### 6.2 `month_plan_import_items`

Idempotency / provenance ledger.

```text
id
import_id
external_id
entity_type
entity_id
source_hash
created_at
updated_at
```

Unique:

```text
(import_id, external_id, entity_type)
```

This allows ANVAYA to prove which internal record came from which YAML item.

### 6.3 `planner_tasks`

General non-event todo work.

```text
id
source_import_id
external_id
title
description
priority            -- P0 | P1 | P2
course_id
topic_id
assessment_id
estimated_minutes
due_on
preferred_day
preferred_window
rollover_policy
status              -- backlog | planned | scheduled | in_progress | completed | skipped | archived
created_at
updated_at
completed_at
archived_at
```

No task requires an exact start time.

### 6.4 `routine_templates`

Recurring personal/planning routines that are not academic-event records.

```text
id
source_import_id
external_id
title
category
priority
recurrence_rule
active_from
active_to
start_time
end_time
duration_minutes
preferred_window
preferred_location
condition_text
status
created_at
updated_at
```

Examples:

- sleep shutdown;
- daily review;
- weekly review;
- English practice;
- conditional swimming.

### 6.5 `daily_agendas`

One saved operational plan per date.

```text
id
agenda_date UNIQUE
day_mode             -- minimum_viable | normal | high_capacity
status               -- draft | approved | active | closed
generated_at
approved_at
closed_at
created_at
updated_at
```

GET rendering must not silently create an agenda. Generation/approval is an explicit command.

### 6.6 `daily_agenda_items`

Stores the actual day-level schedule/to-do snapshot.

```text
id
agenda_id
ordinal
item_kind            -- fixed | routine | task | study | manual
source_type
source_id
title
priority
starts_at
ends_at
planned_minutes
actual_minutes
status               -- planned | in_progress | completed | skipped | moved
reason
created_at
updated_at
completed_at
```

A day remains editable after generation until it is closed.

### 6.7 `task_rollover_events`

Audit trail for movement between days.

```text
id
task_id
from_date
to_date
decision             -- carry | reschedule | backlog | drop | complete
reason
created_at
```

### 6.8 `daily_reviews`

One review per closed agenda.

```text
agenda_id PRIMARY KEY
learned
biggest_confusion
coding_completed
coding_independent
data_science_ai_assistance_level
energy_1_to_5
sleep_target
tomorrow_first_task
created_at
updated_at
```

### 6.9 `weekly_reviews`

One evidence review per review period.

```text
id
week_start
week_end
planned_items
completed_items
planned_focus_minutes
actual_focus_minutes
carry_forward_count
missed_deadline_count
what_worked
what_failed
remove_next_week
next_priority_1
next_priority_2
next_priority_3
created_at
updated_at
closed_at
```

Derived course/topic risk remains owned by existing academic progress services; this table stores review evidence and decisions, not a duplicate mastery engine.

## 7. Monthly YAML Importer

Use a pinned safe YAML parser:

```text
PyYAML==6.0.3
```

Parse with `yaml.safe_load`.

Supported schema initially:

```text
anvaya.external.month_plan/1.0.0
```

### 7.1 Import flow

```text
Upload YAML
   ↓
Parse safely
   ↓
Validate
   ↓
Normalize
   ↓
Resolve exact course codes
   ↓
Conflict detection
   ↓
Dry-run preview
   ↓
Explicit Approve Import
   ↓
Atomic write
   ↓
Reconciliation report
```

No write occurs during upload/preview.

### 7.2 Required validation

Reject or warn on:

- wrong `schema_version`;
- missing `plan_id`;
- date outside declared month range;
- malformed RRULE;
- unknown exact course code;
- duplicate external ID;
- invalid priority;
- negative duration;
- exact-time overlap between fixed commitments;
- task due date outside the month without explicit cross-month allowance;
- subject-specific exam time/date while `official_datesheet_received == false`.

Preserve null exam information.

### 7.3 Mapping

Map imported items as follows:

- `assessments` -> existing `assessments`;
- one-time academic/holiday/fixed events -> existing `academic_events`;
- class timetable recurring entries -> `academic_events.recurrence_rule`;
- personal routines -> `routine_templates`;
- weekly phase / study-plan shell -> existing `study_plans`;
- study/planned blocks -> existing `study_plan_items` where academic semantics fit;
- flexible/general tasks -> `planner_tasks`;
- LinkedIn/video/English/ANVAYA tasks -> `planner_tasks` or `routine_templates` depending on recurrence.

Do not force a general task into `academic_events`.

### 7.4 Idempotency

Re-importing the exact same file hash must be a no-op.

A changed file with the same `plan_id` must produce a reconciliation preview before any write.

The first Phase 7.5.13 implementation may support:

- unchanged;
- added;
- source-managed field changed;
- removed from source.

If an imported record was manually edited after import, do not overwrite it silently. Flag a conflict for user review.

## 8. Calendar Model

Calendar must expose:

```text
Month | Week | Day
```

### Month view

Answers: “What is coming?”

Show:

- holidays;
- classes/labs;
- confirmed exams;
- deadlines;
- important campus events;
- review days;
- planned major blocks.

Unknown subject exam slots must not appear as fake events.

### Week view

Answers: “How is my time allocated?”

Show:

- fixed commitments;
- routines;
- scheduled study blocks;
- scheduled tasks;
- protected sleep/shutdown boundaries;
- unscheduled important tasks separately.

### Day view

Answers: “What should I do today?”

Show:

- fixed timeline;
- P0/P1/P2 todo;
- scheduled focus blocks;
- current/next item;
- carry-forward origin;
- completion controls;
- daily review state.

## 9. Task Operations

User can:

- create task;
- edit task;
- set P0/P1/P2;
- estimate duration;
- set due date;
- link exact course/topic/assessment;
- schedule task into a day/time;
- complete;
- skip;
- return to backlog;
- archive.

Every mutation is explicit POST + 303 except small JSON interactions where progressive enhancement clearly benefits.

GET remains side-effect free.

## 10. Daily Agenda Generation

A proposed day combines:

1. fixed `academic_events` occurrences;
2. active `routine_templates`;
3. `study_plan_items` for that date;
4. due/urgent `planner_tasks`;
5. bounded rollover candidates.

### Capacity rules

Use the imported month-plan rules:

- heavy day deep-work limit: 1;
- normal day deep-work limit: 3;
- active flexible task ceiling: 5;
- preserve protected sleep;
- do not overlap fixed commitments;
- P2 never auto-carries;
- no late-night compensation.

### Task selection

Deterministic priority order:

1. overdue/due P0;
2. near-exam P0;
3. carried P0;
4. due/valuable P1;
5. saved study-plan items;
6. optional P2 only when capacity exists.

### Time placement

If a task has an exact user-selected time, preserve it.

For generated proposals:

- use known free windows between fixed commitments;
- respect `preferred_window`;
- respect estimated minutes;
- never cross protected shutdown;
- never invent a slot if a suitable free window does not exist.

Unplaced tasks remain in “Unscheduled today”, not silently dropped.

## 11. End-of-Day Close and Rollover

Closing a day is an explicit operation.

The close flow:

```text
Review completion
   ↓
Save daily review
   ↓
Evaluate unfinished tasks
   ↓
Create rollover proposal
   ↓
Generate tomorrow draft
   ↓
User approves/adjusts tomorrow
```

### Rollover policy

P0:
- at most one automatic carry candidate;
- only if still relevant/open.

P1:
- at most one candidate;
- may be tomorrow, later this week, or backlog.

P2:
- never automatically carried.

Do not clone tasks. Move/reference the same task and record a rollover event.

## 12. Weekly Review

Weekly review dates come from the imported plan.

The review screen includes:

- planned vs completed items;
- planned vs actual focused minutes;
- open P0/P1;
- carry-forward count;
- missed deadlines;
- existing academic risk/weak-topic signals;
- coding/Data Science evidence where available;
- sleep/recovery self-report fields;
- what worked;
- what failed;
- what to remove;
- next week's top three.

Closing a weekly review does not rewrite academic progress. It records decisions and can seed next-week priorities.

## 13. Updating Official Exam Slots Later

When the official datesheet arrives:

- user opens Calendar / Assessments;
- selects the assessment;
- enters confirmed date/time/venue;
- ANVAYA validates overlaps;
- saves to the existing assessment/calendar authority;
- creates/updates the corresponding confirmed academic event;
- regenerates only affected future daily agendas after explicit approval.

No need to regenerate or re-import the entire October YAML.

## 14. Web Information Architecture

### Planning page

Evolve `/planning` into the Operational Planner.

Suggested tabs/sections:

```text
Today
Tasks
Month Plan
Reviews
Progress
Saved Study Plans
```

Current Progress & Planning content remains available rather than being discarded.

### Calendar page

Keep `/calendar`, add:

```text
Month
Week
Day
```

Grades remain accessible but should visually separate from operational calendar controls.

### Home

Add a compact Today panel:

- next commitment;
- open P0 count;
- scheduled focus minutes;
- one carry-forward item;
- daily review status;
- “Open Today Plan”.

Home must consume service output, not implement planning logic.

## 15. Routes

Representative route design:

```text
GET  /planning
GET  /planning/tasks
POST /planning/tasks
POST /planning/tasks/<task_id>/update
POST /planning/tasks/<task_id>/complete
POST /planning/tasks/<task_id>/archive

GET  /planning/month-plan
POST /planning/month-plan/preview
POST /planning/month-plan/approve

GET  /planning/day/<YYYY-MM-DD>
POST /planning/day/<YYYY-MM-DD>/generate
POST /planning/day/<YYYY-MM-DD>/approve
POST /planning/day/<YYYY-MM-DD>/items/<item_id>/complete
POST /planning/day/<YYYY-MM-DD>/close

GET  /planning/review/week/<YYYY-MM-DD>
POST /planning/review/week/<YYYY-MM-DD>

GET  /calendar?view=month&date=...
GET  /calendar?view=week&date=...
GET  /calendar?view=day&date=...

POST /calendar/assessments/<assessment_id>/schedule
```

Exact naming may be adjusted in the implementation plan to match current route conventions, but the behavior and boundaries must remain.

## 16. Service Boundaries

Create focused services:

```text
month_plan_import_service.py
operational_task_service.py
daily_agenda_service.py
weekly_review_service.py
operational_calendar_service.py
```

Create focused SQLite repositories rather than one giant repository.

Routes must not:

- call `sqlite3` directly;
- parse YAML;
- evaluate RRULEs;
- compute rollover;
- perform academic-priority scoring;
- mutate JSON stores directly.

## 17. Recurrence

Phase 7.5.13 only needs the recurrence forms used by the approved plan:

- DAILY;
- WEEKLY with `BYDAY`;
- `UNTIL`;
- `COUNT`;
- explicit excluded dates;
- explicit additional dates.

Unsupported RRULE parts fail validation rather than being partially interpreted.

Do not expand a recurring routine into 31 persistent database rows merely to display the month.

Materialize occurrences for calendar/day queries.

## 18. Daily PDF vs ANVAYA State

The revised PDF contains one printable daily page for every date in October.

Those pages are a human-readable representation of the operational model.

ANVAYA itself must store the interactive state in SQLite:

```text
daily_agendas
daily_agenda_items
daily_reviews
planner_tasks
task_rollover_events
weekly_reviews
```

The PDF is not the tracking database.

## 19. Safety and Data Integrity

- GET requests are side-effect free.
- Month-plan preview never writes.
- Approved import is transactional.
- No fuzzy course matching.
- Unknown dates remain null.
- No task duplication during rollover.
- No recurring-item row explosion.
- No schedule overlap accepted without warning/explicit resolution.
- No imported source silently overwrites manual edits.
- No plan import mutates Obsidian Markdown.
- No retrieval/RAG index changes.
- No Academic Agent action execution changes.
- SQLite `integrity_check` and `foreign_key_check` must remain green.
- Production hashes for protected unrelated domains remain unchanged through the phase gate.

## 20. User-Facing Import Preview

Before approval ANVAYA shows:

```text
October 2026 Monthly Operational Plan

31 days
5 weekly review dates
N fixed academic events
N recurring class entries
N personal routines
N flexible tasks
N planned/study blocks

Exam slots:
5 subject assessments waiting for official datesheet

Warnings:
- unknown course codes
- timing conflicts
- missing required data
- unsupported recurrence
- overloaded days
```

Buttons:

```text
Approve Import
Cancel
```

No silent import.

## 21. User-Facing Daily Page

Example:

```text
TODAY · 12 OCT

NEXT
09:00 MA103N

FIXED
09:00-09:45 MA103N
10:00-10:45 CY100N
...

P0
[ ] UC100N rebuild from blank
[ ] current academic deadline

P1
[ ] same-day lecture touch

SCHEDULED
14:30-15:45 UC100N rebuild
19:30-20:15 MA103N practice

UNSCHEDULED
[ ] English practice - 15 min

CARRIED FROM YESTERDAY
[ ] Lab record

[Close Day]
```

## 22. Phase Boundary

Phase 7.5.13 is complete when:

- the October YAML can be previewed and approved safely;
- its fixed commitments, routines, tasks and study work are operational;
- unknown exam slots remain empty;
- month/week/day calendar views work;
- tasks can be created/scheduled/completed/archived;
- daily agendas persist;
- daily close produces bounded rollover;
- tomorrow can be generated and approved;
- weekly review is persisted;
- Home can surface a compact Today summary;
- all writes go through services/repositories;
- a strict gate proves no unrelated authority or data was changed.

Not included:

- Google Calendar sync;
- automatic email deadline ingestion;
- push notifications;
- native phone reminders;
- LLM-generated schedule optimization;
- Academic Agent autonomous task execution;
- arbitrary natural-language PDF plan ingestion.

The reusable structured YAML importer is the supported month-plan ingestion path.
