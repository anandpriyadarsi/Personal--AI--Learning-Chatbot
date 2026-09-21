# Phase 7.5.13 — Operational Planner: Tasks, Calendar & Monthly Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable operational planner that safely imports an approved monthly YAML plan, exposes month/week/day calendar views, persists tasks and daily agendas, performs bounded rollover, records daily/weekly reviews, and keeps unknown mid-sem subject slots empty until the official datesheet is supplied.

**Architecture:** Extend the existing SQLite authority rather than replacing it. Reuse `assessments`, `academic_events`, `study_plans`, `study_plan_items`, and `study_sessions`; add feature-owned operational-planning tables in migration `0006_operational_planner.sql`. Keep YAML parsing, recurrence, task/agenda/review rules, and calendar mutation in focused services/repositories; Flask routes remain thin and all GET routes remain side-effect free.

**Tech Stack:** Python 3.x, Flask 3.1.2, SQLite, server-rendered Jinja, progressive enhancement, PowerShell gates, pytest, PyYAML 6.0.3.

**Spec:** `docs/superpowers/specs/2026-09-20-phase7-5-13-operational-planner-design.md`

## Global Constraints

- Baseline is current `main` after `8d6360783433735dba1a2aa32113270eea82107a` (`fix: encode Obsidian deep links correctly`).
- Do not start Phase 7.5.14 or unrelated dashboard work.
- Do not hard-code October 2026 into planner logic.
- `ANVAYA_MONTH_PLAN_v1.1.yaml` is the first real external planning profile, not a source-code fixture and not a database migration.
- The YAML import path supports only `schema_version: anvaya.external.month_plan/1.0.0` in this phase.
- Pin `PyYAML==6.0.3` and parse only with `yaml.safe_load`.
- Preserve exact course-code resolution; no fuzzy matching and no guessed course mapping.
- Subject-specific mid-sem `date`, `start_time`, `end_time`, and `venue` remain null until an official datesheet is explicitly supplied.
- The academic-calendar 5–10 October window may be represented as an academic period but must never create fake subject exam slots.
- `ncc_status` may remain internal source context when timetable logic genuinely requires it, but Phase 7.5.13 must not surface it as a prominent profile/status field.
- GET routes are side-effect free.
- Month-plan upload/preview is side-effect free.
- Approved import is atomic and idempotent.
- Re-importing the exact same YAML hash is a no-op.
- Imported data must retain source provenance and deterministic external identities.
- Manual edits are never silently overwritten by a later import.
- Recurring rules are materialized at query/generation time; do not persist 31 duplicate rows for one routine.
- Rollover moves/references an existing task; it never clones the task.
- P0 automatic carry candidate limit: 1 per day.
- P1 carry candidate limit: 1 per day.
- P2 automatic carry: 0.
- Preserve protected shutdown/sleep rules and never schedule missed work as late-night compensation.
- Routes must not import or call `sqlite3` directly.
- Routes must not parse YAML or evaluate RRULEs.
- No Obsidian Markdown mutation.
- No retrieval-index mutation.
- No Academic Agent action-execution expansion.
- No Google Calendar sync, push notifications, email ingestion, or arbitrary PDF-plan parsing in this phase.
- Implementation stays uncommitted until the complete Phase 7.5.13 gate is green.
- After the separately reviewed plan commit, create one implementation commit only.

## Review Focus

1. **Official exam slots still unknown:** importing the October file must leave each subject assessment unscheduled while preserving the overall exam window.
2. **Re-import after manual edits:** source changes must report a conflict instead of overwriting a user-modified task/event.
3. **Recurrence edge cases:** excluded/additional dates and the 29 October Friday-timetable substitution must not produce duplicate/overlapping occurrences.
4. **Daily overload:** generation must leave work unscheduled rather than violate fixed commitments, shutdown, or deep-work limits.
5. **Rollover accumulation:** repeated day closes must never clone a task or compound P2 backlog.

---

## File Structure

### New production files

- `personal_learning_assistant/repositories/sqlite/migrations/0006_operational_planner.sql`
  - Creates the Phase 7.5.13 feature-owned tables and indexes.
- `personal_learning_assistant/repositories/sqlite/month_plan_import_repository.py`
  - Import ledger, provenance, active revision, reconciliation reads/writes.
- `personal_learning_assistant/repositories/sqlite/planner_task_repository.py`
  - General task persistence and status transitions.
- `personal_learning_assistant/repositories/sqlite/daily_agenda_repository.py`
  - Daily agenda/items, rollover events, daily review persistence.
- `personal_learning_assistant/repositories/sqlite/weekly_review_repository.py`
  - Weekly review persistence.
- `personal_learning_assistant/repositories/sqlite/operational_calendar_repository.py`
  - Operational reads/writes around `academic_events`, confirmed assessment schedule linkage, and recurrence source rows.
- `personal_learning_assistant/services/month_plan_import_service.py`
  - Safe YAML parse/validation/normalization, exact course resolution, dry-run preview, approved atomic import/reconciliation.
- `personal_learning_assistant/services/operational_task_service.py`
  - Task CRUD/status/scheduling validation.
- `personal_learning_assistant/services/operational_calendar_service.py`
  - Month/week/day calendar models, supported recurrence materialization, confirmed assessment scheduling.
- `personal_learning_assistant/services/daily_agenda_service.py`
  - Agenda proposal/generation/approval/completion/close/rollover/tomorrow draft.
- `personal_learning_assistant/services/weekly_review_service.py`
  - Weekly evidence summary and close/update behavior.
- `personal_learning_assistant/services/operational_planner_web_service.py`
  - Thin composition façade for the web layer; delegates business rules to the focused services above.
- `personal_learning_assistant/ui/web/templates/planning_tasks.html`
  - Task workspace.
- `personal_learning_assistant/ui/web/templates/planning_month_plan.html`
  - YAML upload/preview/reconciliation/approval workspace.
- `personal_learning_assistant/ui/web/templates/planning_day.html`
  - Operational daily agenda/checklist/review.
- `personal_learning_assistant/ui/web/templates/planning_weekly_review.html`
  - Weekly review form/evidence summary.
- `PHASE7_5_FIX13_OPERATIONAL_PLANNER.md`
  - Operator/implementation record.
- `phase7_5_fix13_gate.ps1`
  - Strict Phase 7.5.13 gate.

### Modified production files

- `requirements.txt`
  - Add exact `PyYAML==6.0.3`.
- `personal_learning_assistant/ui/web/routes.py`
  - Thin GET/POST endpoints and safe error/PRG handling.
- `personal_learning_assistant/ui/web/templates/planning.html`
  - Operational Planner landing page while preserving existing progress/saved-plan content.
- `personal_learning_assistant/ui/web/templates/calendar.html`
  - Month/week/day controls and operational calendar model while preserving grade read views.
- `personal_learning_assistant/ui/web/templates/home.html`
  - Compact Today panel.
- `personal_learning_assistant/ui/web/static/css/app.css`
  - Planner/calendar/day/review responsive styling.
- `personal_learning_assistant/services/home_dashboard_service.py`
  - Compose a read-only operational-Today summary through a provider boundary; do not calculate task priority here.
- `tests/test_phase7_5_progress_planning.py`
  - Preserve and extend existing planning regression expectations.
- `tests/test_phase7_5_calendar_grades.py`
  - Preserve grades and existing calendar behavior while adding operational view contracts.
- `tests/test_phase7_5_home_dashboard.py`
  - Add compact Today-summary regression coverage.

### New test files

- `tests/test_phase7_5_month_plan_import.py`
- `tests/test_phase7_5_operational_tasks.py`
- `tests/test_phase7_5_operational_calendar.py`
- `tests/test_phase7_5_daily_agenda.py`
- `tests/test_phase7_5_weekly_review.py`
- `tests/test_phase7_5_operational_planner_routes.py`

### Test fixtures

- `tests/fixtures/phase7_5/month_plan_minimal.yaml`
- `tests/fixtures/phase7_5/month_plan_october_shape.yaml`

The October-shape fixture must be sanitized/minimal and test structure/rules only. Do not commit Anand's full personal October plan to the repository unless explicitly approved separately.

---

## Task 0: Preflight, Spec Placement, and Plan Commit

**Files:**
- Create: `docs/superpowers/specs/2026-09-20-phase7-5-13-operational-planner-design.md`
- Create: `docs/superpowers/plans/2026-09-20-phase7-5-13-operational-planner.md`

**Interfaces:**
- Consumes: approved external design and this implementation plan.
- Produces: immutable planning baseline used by the Phase 7.5.13 gate.

- [ ] **Step 1: Verify repository baseline**

Run:

```powershell
git status --short
git branch --show-current
git log --oneline --decorate -8
```

Require:
- branch = `main`
- clean working tree
- `HEAD = 8d6360783433735dba1a2aa32113270eea82107a`

If remote has advanced, stop and reconcile before editing.

- [ ] **Step 2: Copy the approved design into the repository spec path**

Use the approved design without changing scope.

- [ ] **Step 3: Save this implementation plan into the repository plan path**

No TODO/TBD placeholders.

- [ ] **Step 4: Self-review spec and plan against current code**

Confirm:
- highest existing migration is `0005_obsidian_study_companion.sql`;
- Planning/Calendar are currently read-oriented;
- no current monthly YAML importer exists;
- existing Phase 7.5.12.1 behavior is outside the implementation scope.

- [ ] **Step 5: Commit only spec + implementation plan**

```powershell
git add -- `
  docs/superpowers/specs/2026-09-20-phase7-5-13-operational-planner-design.md `
  docs/superpowers/plans/2026-09-20-phase7-5-13-operational-planner.md

git diff --cached --check
git commit -m "docs: add Phase 7.5.13 operational planner plan"
```

Record this commit SHA as `$BaseCommit` for the gate.

---

## Task 1: SQLite Operational Planner Schema

**Files:**
- Create: `personal_learning_assistant/repositories/sqlite/migrations/0006_operational_planner.sql`
- Create: `tests/test_phase7_5_operational_tasks.py`
- Create: `tests/test_phase7_5_daily_agenda.py`
- Create: `tests/test_phase7_5_weekly_review.py`
- Create: `tests/test_phase7_5_month_plan_import.py`

**Interfaces:**
- Consumes: migration runner and existing `0001`–`0005` schema.
- Produces: tables `month_plan_imports`, `month_plan_import_items`, `planner_tasks`, `routine_templates`, `daily_agendas`, `daily_agenda_items`, `task_rollover_events`, `daily_reviews`, `weekly_reviews`.

- [ ] **Step 1: Write RED migration tests**

Assert a fresh database applies `(1, 2, 3, 4, 5, 6)` and all required tables/constraints/indexes exist.

Explicitly test:
- invalid P3 priority rejected;
- negative task duration rejected;
- duplicate `agenda_date` rejected;
- invalid agenda/review enums rejected;
- rollover references a real task;
- import-ledger uniqueness works;
- FK check empty.

- [ ] **Step 2: Run only migration/schema tests and confirm RED**

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_phase7_5_month_plan_import.py `
  tests/test_phase7_5_operational_tasks.py `
  tests/test_phase7_5_daily_agenda.py `
  tests/test_phase7_5_weekly_review.py `
  -k "migration or schema or constraint or index"
```

Expected failure: migration 0006/tables absent.

- [ ] **Step 3: Implement `0006_operational_planner.sql`**

Use the spec fields and indexes. Important schema choices:

`month_plan_imports`
- `id TEXT PRIMARY KEY`
- `plan_id TEXT NOT NULL`
- `schema_version TEXT NOT NULL`
- `source_filename TEXT NOT NULL`
- `source_sha256 TEXT NOT NULL`
- `title TEXT NOT NULL`
- `starts_on TEXT NOT NULL`
- `ends_on TEXT NOT NULL`
- `timezone TEXT NOT NULL`
- `status TEXT NOT NULL CHECK(status IN ('previewed','active','superseded','rejected'))`
- timestamps
- partial unique index: one `active` revision per `plan_id`

`month_plan_import_items`
- FK to import
- unique `(import_id, external_id, entity_type)`

`planner_tasks`
- P0/P1/P2 check
- exact existing course/topic/assessment FKs
- nonnegative optional estimated minutes
- lifecycle status check

`routine_templates`
- recurrence string + bounded lifecycle status
- no expansion table

`daily_agendas`
- unique date and day/status checks

`daily_agenda_items`
- FK to agenda
- no requirement that every item point to a persisted source entity because `manual` exists
- status/item-kind checks

`task_rollover_events`
- FK to task
- decision check

`daily_reviews`
- one per agenda
- AI help 0–7 or null
- energy 1–5 or null

`weekly_reviews`
- week date-range check
- nonnegative counters

- [ ] **Step 4: Rerun migration/schema tests GREEN**

- [ ] **Step 5: Run migration runner regression suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase3_sqlite_connection_migrations.py
```

---

## Task 2: Feature-Owned SQLite Repositories

**Files:**
- Create: `personal_learning_assistant/repositories/sqlite/month_plan_import_repository.py`
- Create: `personal_learning_assistant/repositories/sqlite/planner_task_repository.py`
- Create: `personal_learning_assistant/repositories/sqlite/daily_agenda_repository.py`
- Create: `personal_learning_assistant/repositories/sqlite/weekly_review_repository.py`
- Create: `personal_learning_assistant/repositories/sqlite/operational_calendar_repository.py`
- Test: the five new Phase 7.5.13 test modules.

**Interfaces:**
- Consumes: path to migrated `learning_assistant.db`.
- Produces:
  - `SQLiteMonthPlanImportRepository`
  - `SQLitePlannerTaskRepository`
  - `SQLiteDailyAgendaRepository`
  - `SQLiteWeeklyReviewRepository`
  - `SQLiteOperationalCalendarRepository`

Repository convention:
- open `ro` for reads and `rw` for writes;
- validate required schema at connection time;
- set row factory, foreign keys, busy timeout;
- wrap writes in the existing transaction helper;
- raise feature-owned safe repository errors;
- never create/migrate a DB implicitly.

- [ ] **Step 1: Write RED repository tests**

Test:
- schema validation;
- list/get round trips;
- create/update task;
- agenda + item transaction;
- rollover event round trip;
- review round trip;
- import revision/ledger round trip;
- read-only connection behavior;
- rollback on failure;
- calendar event query by date window;
- assessment schedule update transaction.

- [ ] **Step 2: Run repository tests and confirm RED**

- [ ] **Step 3: Implement smallest repository APIs**

Required interfaces:

```python
class SQLiteMonthPlanImportRepository:
    def find_by_hash(self, source_sha256: str): ...
    def active_import(self, plan_id: str): ...
    def create_preview_record(...): ...
    def activate_import(...): ...
    def list_import_items(import_id: str): ...
    def upsert_import_item(...): ...

class SQLitePlannerTaskRepository:
    def list_tasks(...): ...
    def get_task(task_id: str): ...
    def create_task(...): ...
    def update_task(...): ...
    def set_status(...): ...
    def mark_completed(...): ...
    def archive_task(...): ...

class SQLiteDailyAgendaRepository:
    def get_agenda(agenda_date: str): ...
    def create_agenda(...): ...
    def replace_draft_items(...): ...
    def update_item_status(...): ...
    def record_rollover(...): ...
    def save_daily_review(...): ...
    def close_agenda(...): ...

class SQLiteWeeklyReviewRepository:
    def get_review(week_start: str): ...
    def save_review(...): ...
    def close_review(...): ...

class SQLiteOperationalCalendarRepository:
    def list_academic_events(starts_on: str, ends_on: str): ...
    def list_assessments(...): ...
    def schedule_assessment(...): ...
    def upsert_academic_event(...): ...
```

- [ ] **Step 4: Rerun repository tests GREEN**

- [ ] **Step 5: Add transaction rollback assertions**

A failed import/task/calendar transaction must leave no partial rows.

---

## Task 3: Safe Monthly YAML Parser and Validation Preview

**Files:**
- Modify: `requirements.txt`
- Create: `personal_learning_assistant/services/month_plan_import_service.py`
- Create: `tests/fixtures/phase7_5/month_plan_minimal.yaml`
- Create: `tests/fixtures/phase7_5/month_plan_october_shape.yaml`
- Test: `tests/test_phase7_5_month_plan_import.py`

**Interfaces:**
- Consumes: YAML bytes + course lookup provider + import repository.
- Produces:
  - `MonthPlanImportService.preview(filename: str, payload: bytes) -> dict`
  - normalized immutable import model
  - warnings/errors/conflicts without writes.

- [ ] **Step 1: Add RED dependency + parser tests**

Tests require:
- exact `PyYAML==6.0.3`;
- safe parser accepts the supported schema;
- YAML tags/object construction rejected;
- non-mapping root rejected;
- file-size cap enforced;
- malformed UTF-8 rejected;
- schema mismatch rejected.

- [ ] **Step 2: Add RED semantic-validation tests**

Cover:
- missing `plan_id`;
- invalid date range;
- duplicate external IDs;
- unknown exact course code;
- invalid priority/duration;
- malformed/unsupported RRULE;
- out-of-range event dates;
- exact overlap warnings;
- exam subject slot present while datesheet flag false -> hard validation error;
- null exam subject slots preserved;
- `ncc_status` never becomes a generated task/calendar/profile item.

- [ ] **Step 3: Run parser tests and confirm RED**

- [ ] **Step 4: Pin dependency**

Append exactly:

```text
PyYAML==6.0.3
```

- [ ] **Step 5: Implement parser/validator**

Use:

```python
yaml.safe_load(text)
```

Never `yaml.load`.

Define bounded constants:
- maximum YAML size;
- maximum number of tasks/events/routines;
- maximum title/description lengths.

Supported recurrence subset:
- `FREQ=DAILY`
- `FREQ=WEEKLY`
- `BYDAY`
- `UNTIL`
- `COUNT`
- plus source-level `excluded_dates` / `additional_dates`

Reject unsupported RRULE parts.

- [ ] **Step 6: Build preview summary**

Return fields needed by UI:

```python
{
    "valid": bool,
    "source_sha256": "...",
    "plan": {...},
    "counts": {
        "days": 31,
        "assessments": ...,
        "fixed_events": ...,
        "class_rules": ...,
        "personal_routines": ...,
        "tasks": ...,
        "study_blocks": ...,
        "weekly_reviews": ...,
    },
    "waiting_exam_slots": (...),
    "warnings": (...),
    "errors": (...),
    "reconciliation": {...},
}
```

- [ ] **Step 7: Rerun focused parser/preview tests GREEN**

---

## Task 4: Atomic Month-Plan Approval and Reconciliation

**Files:**
- Modify: `personal_learning_assistant/services/month_plan_import_service.py`
- Modify: all relevant Phase 7.5.13 SQLite repositories.
- Test: `tests/test_phase7_5_month_plan_import.py`

**Interfaces:**
- Consumes: a previously validated preview token/hash and current SQLite state.
- Produces: approved import with provenance rows + mapped internal records.

- [ ] **Step 1: Write RED approval/idempotency tests**

Test:
- preview performs zero writes;
- approval creates one import revision;
- same hash approved twice is a no-op;
- exact course resolution only;
- fixed one-time event -> `academic_events`;
- class recurrence -> recurring `academic_events`;
- personal routine -> `routine_templates`;
- flexible/general task -> `planner_tasks`;
- academic study block -> `study_plan_items` only when links are valid;
- waiting exams produce assessment context but no subject-specific calendar event;
- import item ledger maps source external IDs to internal records.

- [ ] **Step 2: Write RED reconciliation/manual-edit tests**

Changed source with same `plan_id`:
- source-managed untouched record may be proposed for update;
- record edited after import must produce conflict;
- source removal is reported, not silently deleted;
- preview exposes added/changed/removed/conflicted counts.

- [ ] **Step 3: Implement deterministic IDs**

Derive internal IDs from:

```text
plan_id + external_id + entity_type
```

through a stable UUID5 namespace or stable SHA-256-derived UUID strategy documented in code.

Do not use random IDs for imported source-managed records.

- [ ] **Step 4: Implement atomic approval**

All records for one approved revision must commit or rollback together.

Do not write production JSON legacy stores.

- [ ] **Step 5: Rerun importer approval/reconciliation tests GREEN**

---

## Task 5: Operational Task Service

**Files:**
- Create: `personal_learning_assistant/services/operational_task_service.py`
- Test: `tests/test_phase7_5_operational_tasks.py`

**Interfaces:**
- Consumes: `SQLitePlannerTaskRepository`, exact course/topic/assessment lookup providers.
- Produces:
  - `tasks_workspace(...)`
  - `create_task(...)`
  - `update_task(...)`
  - `complete_task(...)`
  - `archive_task(...)`
  - `schedule_candidate(...)`

- [ ] **Step 1: Write RED validation tests**

Cover:
- blank title;
- invalid priority;
- negative/oversized duration;
- invalid date;
- unknown exact course/topic/assessment;
- topic from wrong course;
- invalid rollover policy;
- archived task cannot be completed without restore.

- [ ] **Step 2: Write RED lifecycle tests**

Expected transitions:

```text
backlog -> planned -> scheduled -> in_progress -> completed
backlog/planned/scheduled -> skipped
open -> archived
```

Reject impossible transitions.

- [ ] **Step 3: Implement service**

Keep task semantics separate from calendar-event semantics.

- [ ] **Step 4: Rerun task tests GREEN**

---

## Task 6: Supported Recurrence and Operational Calendar Service

**Files:**
- Create: `personal_learning_assistant/services/operational_calendar_service.py`
- Create: `tests/test_phase7_5_operational_calendar.py`
- Modify: `personal_learning_assistant/repositories/sqlite/operational_calendar_repository.py`

**Interfaces:**
- Consumes: academic events, routine templates, scheduled agenda items/tasks, assessments.
- Produces:
  - `month_view(anchor_date)`
  - `week_view(anchor_date)`
  - `day_view(anchor_date)`
  - `schedule_assessment(...)`
  - occurrence materialization helper.

- [ ] **Step 1: Write RED recurrence tests**

Cover:
- daily;
- weekly `BYDAY`;
- `UNTIL`;
- `COUNT`;
- excluded date;
- additional date;
- no duplicate when additional date matches normal occurrence;
- 29 Oct Friday timetable substitution;
- mid-sem-window suspended classes;
- unsupported RRULE raises validation error.

- [ ] **Step 2: Write RED calendar view tests**

Month:
- grouped date cells/events.

Week:
- fixed commitments + routines + scheduled work.

Day:
- ordered timeline + unscheduled due tasks separately.

- [ ] **Step 3: Write RED confirmed-exam scheduling tests**

When official slot supplied later:
- valid assessment gets date/time/venue;
- conflicting fixed event returns conflict;
- corresponding academic event is created/updated;
- no fuzzy assessment/course lookup;
- only affected future agenda dates are marked stale/proposed for regeneration;
- no entire month re-import required.

- [ ] **Step 4: Implement recurrence and calendar service**

Do not use third-party recurrence libraries unless the supported subset proves impossible with a small deterministic parser.

- [ ] **Step 5: Rerun operational-calendar tests GREEN**

---

## Task 7: Daily Agenda Generation and Capacity Rules

**Files:**
- Create: `personal_learning_assistant/services/daily_agenda_service.py`
- Test: `tests/test_phase7_5_daily_agenda.py`

**Interfaces:**
- Consumes:
  - operational calendar day model;
  - task service/list;
  - saved `study_plan_items`;
  - active routine occurrences;
  - month-plan capacity/rollover settings.
- Produces:
  - `preview_day(date)`
  - `generate_day(date)`
  - `approve_day(date)`
  - `complete_item(...)`
  - `close_day(...)`
  - `tomorrow_proposal(...)`

- [ ] **Step 1: Write RED GET-purity tests**

`preview_day` / route GET must not insert `daily_agendas` or items.

- [ ] **Step 2: Write RED deterministic-selection tests**

Selection order:
1. overdue/due P0;
2. near-exam P0 where a real confirmed exam exists;
3. carried P0;
4. due/value P1;
5. existing study-plan item;
6. P2 only when capacity remains.

Unknown exam slots must not generate fake “T-1” placement.

- [ ] **Step 3: Write RED placement/capacity tests**

Cover:
- no overlap with fixed events;
- `preferred_window`;
- duration fit;
- heavy-day deep-work max 1;
- normal-day deep-work max 3;
- active flexible-task max 5;
- shutdown boundary;
- no late-night compensation;
- unschedulable task remains “unscheduled today”.

- [ ] **Step 4: Implement generation algorithm**

Keep it deterministic and explainable. Each proposed item includes `reason`.

- [ ] **Step 5: Implement approval**

Generation writes a draft only through explicit POST. Approval marks it approved/active.

- [ ] **Step 6: Rerun agenda-generation tests GREEN**

---

## Task 8: Day Close, Daily Review, and Bounded Rollover

**Files:**
- Modify: `personal_learning_assistant/services/daily_agenda_service.py`
- Modify: `personal_learning_assistant/repositories/sqlite/daily_agenda_repository.py`
- Test: `tests/test_phase7_5_daily_agenda.py`

**Interfaces:**
- Consumes: open agenda, task statuses, review fields.
- Produces: closed agenda + persisted review + rollover events + tomorrow draft proposal.

- [ ] **Step 1: Write RED daily-review validation tests**

Validate:
- energy 1–5 or null;
- AI assistance 0–7 or null;
- bounded text;
- one review per agenda;
- already-closed day cannot close twice.

- [ ] **Step 2: Write RED rollover tests**

Test:
- max one P0 candidate;
- max one P1 candidate;
- zero P2;
- completed tasks never carried;
- no duplicate task row;
- repeated close is idempotent/rejected;
- P1 may go later-in-week/backlog;
- rollover reason stored.

- [ ] **Step 3: Implement close transaction**

One transaction must persist:
- review;
- final item statuses;
- rollover decisions;
- agenda close state.

- [ ] **Step 4: Generate tomorrow draft after close**

Tomorrow generation remains a separate persisted draft, never auto-approved.

- [ ] **Step 5: Rerun close/rollover tests GREEN**

---

## Task 9: Weekly Review Service

**Files:**
- Create: `personal_learning_assistant/services/weekly_review_service.py`
- Test: `tests/test_phase7_5_weekly_review.py`

**Interfaces:**
- Consumes:
  - agendas/items for date range;
  - task/rollover events;
  - existing progress/risk providers;
  - study-session evidence where available.
- Produces:
  - evidence summary;
  - editable review;
  - close operation with next-three priorities.

- [ ] **Step 1: Write RED aggregation tests**

Calculate:
- planned/completed count;
- planned/actual focus minutes;
- carry-forward count;
- missed deadlines;
- open P0/P1;
- read-only academic risk projection from existing provider.

Do not duplicate mastery calculation.

- [ ] **Step 2: Write RED review persistence tests**

Require:
- valid week range;
- max three next priorities;
- close once;
- editing an open review allowed;
- closed review read-only unless a future explicit reopen feature is added.

- [ ] **Step 3: Implement service**

- [ ] **Step 4: Rerun weekly-review tests GREEN**

---

## Task 10: Web-Service Composition and Routes

**Files:**
- Create: `personal_learning_assistant/services/operational_planner_web_service.py`
- Modify: `personal_learning_assistant/ui/web/routes.py`
- Create: `tests/test_phase7_5_operational_planner_routes.py`

**Interfaces:**
- Consumes: focused planner services.
- Produces: safe route-facing view models and commands.

- [ ] **Step 1: Write RED service-factory injection tests**

Follow existing Phase 7.5 pattern:

```python
current_app.config["OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY"]
```

Tests can inject a fake without touching production SQLite.

- [ ] **Step 2: Write RED GET route tests**

Required:
- `GET /planning`
- `GET /planning/tasks`
- `GET /planning/month-plan`
- `GET /planning/day/<date>`
- `GET /planning/review/week/<date>`
- `GET /calendar?view=month|week|day&date=...`

Assert side-effect freedom.

- [ ] **Step 3: Write RED POST + PRG tests**

Required:
- create/update/complete/archive task;
- month-plan preview;
- month-plan approval;
- generate/approve day;
- complete day item;
- close day;
- save/close weekly review;
- confirmed assessment schedule.

Form writes return 303 to the relevant read page.

Invalid commands return safe 400/404/409/503 messages without raw SQL/path/tracebacks.

- [ ] **Step 4: Implement façade + thin routes**

Routes may:
- parse primitive form/query values;
- call service;
- render/redirect.

Routes may not:
- open DB;
- parse YAML;
- evaluate recurrence;
- select rollover;
- calculate academic priority.

- [ ] **Step 5: Run route tests GREEN**

---

## Task 11: Planning UI — Tasks, Month Plan, Today, Reviews

**Files:**
- Modify: `personal_learning_assistant/ui/web/templates/planning.html`
- Create: `personal_learning_assistant/ui/web/templates/planning_tasks.html`
- Create: `personal_learning_assistant/ui/web/templates/planning_month_plan.html`
- Create: `personal_learning_assistant/ui/web/templates/planning_day.html`
- Create: `personal_learning_assistant/ui/web/templates/planning_weekly_review.html`
- Modify: `personal_learning_assistant/ui/web/static/css/app.css`
- Test: `tests/test_phase7_5_operational_planner_routes.py`
- Modify: `tests/test_phase7_5_progress_planning.py`

**Interfaces:**
- Consumes: route view models.
- Produces: server-rendered operational planner with usable no-JS forms.

- [ ] **Step 1: Write RED template-contract tests**

Planning landing must expose:

```text
Today
Tasks
Month Plan
Reviews
Progress
Saved Study Plans
```

Preserve existing progress and saved study-plan information.

- [ ] **Step 2: Implement Month Plan preview UI**

Show:
- source file/hash/title/date range;
- counts;
- waiting exam slots;
- validation errors;
- warnings;
- added/changed/removed/conflicted reconciliation;
- `Approve Import` only when preview is valid.

- [ ] **Step 3: Implement Tasks UI**

Filters:
- open;
- priority;
- course;
- due window;
- backlog/scheduled/completed.

Operations work without JS.

- [ ] **Step 4: Implement Daily Agenda UI**

Show:
- fixed timeline;
- P0/P1/P2;
- scheduled blocks;
- unscheduled today;
- carry origin;
- complete controls;
- daily review;
- close day.

Use the same visual philosophy as the revised PDF daily pages but adapt for interactive web use.

- [ ] **Step 5: Implement Weekly Review UI**

- [ ] **Step 6: Add responsive styling**

Desktop:
- timeline + todo columns where space allows.

Narrow:
- stack into one readable column;
- no horizontal overflow;
- controls remain touch-friendly.

- [ ] **Step 7: Rerun planning/template regressions GREEN**

---

## Task 12: Calendar Month / Week / Day UI and Grade Preservation

**Files:**
- Modify: `personal_learning_assistant/ui/web/templates/calendar.html`
- Modify: `personal_learning_assistant/ui/web/static/css/app.css`
- Test: `tests/test_phase7_5_operational_calendar.py`
- Modify: `tests/test_phase7_5_calendar_grades.py`

**Interfaces:**
- Consumes: operational calendar view + existing grade dashboard model.
- Produces: operational calendar without regressing grades.

- [ ] **Step 1: Write RED regression tests**

Existing grades/semester configuration remain visible.

- [ ] **Step 2: Add view selector**

```text
Month | Week | Day
```

- [ ] **Step 3: Month view**

Readable calendar grid/date groups; no fake subject exams.

- [ ] **Step 4: Week view**

Time allocation across fixed events, routines, scheduled work.

- [ ] **Step 5: Day view**

Timeline + unscheduled tasks.

- [ ] **Step 6: Add confirmed-exam edit form**

Only explicit user POST saves a real subject slot.

- [ ] **Step 7: Rerun calendar + grade tests GREEN**

---

## Task 13: Home “Today” Operational Summary

**Files:**
- Modify: `personal_learning_assistant/services/home_dashboard_service.py`
- Modify: `personal_learning_assistant/ui/web/templates/home.html`
- Modify: `tests/test_phase7_5_home_dashboard.py`

**Interfaces:**
- Consumes: injected operational-Today provider output.
- Produces read-only summary:
  - next commitment;
  - open P0 count;
  - scheduled focus minutes;
  - one carry-forward item;
  - daily review status;
  - `Open Today Plan` link.

- [ ] **Step 1: Write RED provider-boundary test**

Home service must not import planner repositories directly at module import time.

- [ ] **Step 2: Write RED degraded-state tests**

Planner unavailable must not break Home.

- [ ] **Step 3: Implement summary composition**

No priority calculation in Home.

- [ ] **Step 4: Rerun Home regression tests GREEN**

---

## Task 14: Phase 7.5.13 Operator Record and Strict Gate

**Files:**
- Create: `PHASE7_5_FIX13_OPERATIONAL_PLANNER.md`
- Create: `phase7_5_fix13_gate.ps1`

**Interfaces:**
- Consumes: plan-commit SHA as `$BaseCommit`.
- Produces: one strict PASS/FAIL gate for the complete implementation.

- [ ] **Step 1: Write operator record**

Document:
- scope;
- architecture;
- supported YAML schema;
- import safety;
- recurrence subset;
- exam-null policy;
- daily/weekly workflow;
- intentionally deferred features;
- manual post-commit import procedure for the real October YAML.

- [ ] **Step 2: Build gate baseline from plan commit**

The gate must fail if HEAD is not the Phase 7.5.13 plan commit while implementation remains uncommitted.

- [ ] **Step 3: Define exact allowed file whitelist**

Include only:
- 0006 migration;
- new Phase 7.5.13 repositories/services/templates/tests;
- approved modifications to routes/planning/calendar/home/CSS/requirements;
- operator record;
- gate itself.

Exclude runtime artifacts:
- `__pycache__`
- `*.pyc`
- `*.pyo`

- [ ] **Step 4: Protect unrelated domains by hash**

Hash before/after:
- migrations 0001–0005;
- Obsidian Reader/Companion code;
- Notes Studio code;
- Resources code;
- retrieval code/index;
- tutor code;
- authority file;
- production JSON;
- configured Obsidian Markdown.

Phase 7.5.13 tests must use temporary SQLite unless a route/service test injects a fake.

- [ ] **Step 5: Add forbidden dependency scans**

Reject in `routes.py`:

```text
import sqlite3
sqlite3.
.execute(
yaml.safe_load
yaml.load
RRULE parser implementation
```

Reject direct JSON/Markdown writes from new planner services.

- [ ] **Step 6: Create staged test sequence**

Recommended 20 stages:

```text
[1/20]  Migration/schema/constraints
[2/20]  Month YAML safe parser + semantic validation
[3/20]  Import preview purity + exact course resolution
[4/20]  Import approval/idempotency/provenance
[5/20]  Import reconciliation/manual-edit conflicts
[6/20]  Task lifecycle/validation
[7/20]  Recurrence materialization
[8/20]  Calendar month/week/day + confirmed exam scheduling
[9/20]  Daily agenda GET purity + deterministic selection
[10/20] Agenda placement/capacity/shutdown
[11/20] Daily review + rollover + tomorrow draft
[12/20] Weekly review aggregation/persistence
[13/20] Operational planner web routes + POST/PRG
[14/20] Existing Planning/Calendar/Home regressions
[15/20] Complete Phase 7.5 web regressions
[16/20] Phase 7.1–7.4 recovery/runtime regressions
[17/20] Complete pytest suite
[18/20] Python compile + exact PyYAML pin + pip check
[19/20] Fresh/production SQLite integrity/FK + protected hashes
[20/20] Scoped git diff + runtime-artifact exclusion
```

- [ ] **Step 7: Fresh DB assertions**

Fresh migration must produce versions:

```python
(1, 2, 3, 4, 5, 6)
```

and:

```text
PRAGMA integrity_check = ok
PRAGMA foreign_key_check = []
```

- [ ] **Step 8: Production DB gate remains read-only**

Do not apply migration 0006 to the production DB merely to run tests. The feature launcher/startup or explicit operator migration flow handles actual production migration after the implementation is approved.

- [ ] **Step 9: Required PASS banner**

```text
PHASE 7.5.13 OPERATIONAL PLANNER + TASKS + CALENDAR: PASS
```

---

## Task 15: Full Verification and One Implementation Commit

**Files:** all approved implementation files only.

**Interfaces:**
- Consumes: completely green 20-stage gate.
- Produces: one implementation commit.

- [ ] **Step 1: Run the complete gate from stage 1**

```powershell
powershell -ExecutionPolicy Bypass -File .\phase7_5_fix13_gate.ps1
```

Do not cherry-pick isolated successes. Final banner must be PASS.

- [ ] **Step 2: Run final diff checks**

```powershell
git diff --check
git status --short
git diff --stat
```

- [ ] **Step 3: Review scope manually**

No unrelated modified files.

- [ ] **Step 4: Commit once**

```powershell
git add -- <exact-approved-files>
git diff --cached --check
git commit -m "feat: add Phase 7.5.13 operational planner"
```

- [ ] **Step 5: Push `main`**

```powershell
git push origin main
```

- [ ] **Step 6: Verify synchronization**

```powershell
git status
git log --oneline --decorate -8
```

Require:
- working tree clean;
- `HEAD -> main` and `origin/main` at the same implementation commit.

---

## Task 16: Local Production Migration and Real October Plan Import Acceptance

**This task happens only after the implementation commit is green and pushed. It is operational acceptance, not part of the implementation commit.**

**External input:**
- `ANVAYA_MONTH_PLAN_v1.1.yaml`

- [ ] **Step 1: Back up production SQLite using the existing project backup workflow**

Do not manually copy/overwrite unrelated data files.

- [ ] **Step 2: Apply migration 0006 to the production SQLite through the approved migration runner**

Verify:
- migration version 6 recorded;
- integrity check `ok`;
- foreign-key check empty.

- [ ] **Step 3: Start ANVAYA**

```powershell
.\.venv\Scripts\python.exe -m personal_learning_assistant.ui.web
```

- [ ] **Step 4: Upload `ANVAYA_MONTH_PLAN_v1.1.yaml` through Month Plan**

First action is Preview only.

- [ ] **Step 5: Verify preview before any approval**

Must show:
- correct 1–31 October range;
- fixed holidays/calendar period;
- recurring class rules;
- routines/tasks/study blocks;
- five weekly review dates;
- individual mid-sem subject slots waiting for official datesheet;
- zero invented exam dates/times/venues;
- no NCC status presented as dashboard identity;
- warnings/conflicts clearly surfaced.

- [ ] **Step 6: Human approval gate**

Do not click `Approve Import` until the user confirms the preview is correct.

- [ ] **Step 7: Approve import**

After explicit user approval, verify:
- no duplicate import on refresh/retry;
- Calendar Month/Week/Day shows correct known commitments;
- Today page can generate a draft;
- P0/P1/P2 tasks are present;
- daily close/review/rollover works on a test date without corrupting another day.

- [ ] **Step 8: Record acceptance result**

Do not alter the implementation commit solely to record personal October runtime data.

---

# Completion Criteria

Phase 7.5.13 is complete only when all of the following are true:

- `0006_operational_planner.sql` is migration-runner compatible.
- The supported YAML schema is safely parsed and validated.
- Preview is write-free.
- Approval is transactional/idempotent/provenanced.
- Unknown exam slots remain null and do not become fake calendar events.
- Tasks have operational lifecycle and explicit scheduling.
- Recurrence is query-materialized without row explosion.
- Calendar Month/Week/Day work.
- Daily agendas persist and are explicitly generated/approved.
- Capacity rules protect fixed commitments and sleep.
- Day close saves review evidence.
- Rollover carries at most one P0 + one P1 and never auto-carries P2.
- Tomorrow is generated as a draft, not auto-approved.
- Weekly review persists evidence and next-three decisions.
- Home surfaces a compact read-only Today summary.
- Existing grades, progress planning, Obsidian, Notes/Resources, retrieval and Academic Agent regressions remain green.
- Full pytest passes with the known intentional legacy deselection handled as in the established Phase 7.5 gate pattern.
- SQLite integrity/FK checks are green.
- Protected unrelated hashes remain unchanged.
- Strict gate ends with:

```text
PHASE 7.5.13 OPERATIONAL PLANNER + TASKS + CALENDAR: PASS
```

- One scoped implementation commit is pushed to `main`.
- The real October YAML is imported only after a successful preview and a separate explicit human approval.
