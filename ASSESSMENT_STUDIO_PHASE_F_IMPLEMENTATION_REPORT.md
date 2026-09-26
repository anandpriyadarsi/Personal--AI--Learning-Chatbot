# Assessment Studio Phase F — Implementation Report

## Result

Assessment Studio Phase F — Adaptive Academic Loop is implemented from the verified Phase E baseline:

`phase7.5.assessment-studio-e/assessment-intelligence @ 3039976fff8d221f6ad35119e9bfbeaa4af833db`

The production target branch is:

`phase7.5.assessment-studio-f/adaptive-academic-loop`

Phase F has not been merged into `main`.

## Delivered loop

Phase F closes the first bounded assessment-to-action loop:

confirmed Phase D evaluation
→ Phase E Assessment Intelligence
→ deterministic recovery proposal
→ user review
→ explicit Generate
→ explicit Apply or Reject
→ existing Operational Planner backlog.

No recommendation is silently applied.

## Repository-grounded planner integration

The current repository does not expose a modern `ProgressService` / `PlannerService` pair under those exact names.

The existing authoritative planning stack is:

- `OperationalTaskService`;
- `SQLitePlannerTaskRepository`;
- `planner_tasks`;
- Operational Planner web/service layer.

Phase F integrates with that stack instead of creating a parallel planner.

Legacy `academic_progress.py` is not used as a Phase F write target.

## Migration 0013

Phase F adds:

`0013_assessment_adaptive_academic_loop.sql`

The authoritative schema is now `0001..0013`.

New durable entities:

- `assessment_recovery_recommendations`;
- `assessment_recovery_recommendation_events`.

A recovery-task namespace unique index was also added to `planner_tasks.external_id`.

## Recommendation lifecycle

Recommendations use:

- pending;
- accepted;
- applied;
- rejected;
- superseded.

The `accepted` state intentionally separates the user's decision from planner task creation.

This makes Apply resumable if planner persistence is temporarily unavailable.

## Live preview and explicit generation

GET `/assessments/adaptive` computes a read-only live preview from Phase E `weak_topics()`.

The preview does not persist recommendations or tasks.

The user chooses evidence cards and explicitly posts **Generate selected recommendations**.

Generation:

- snapshots the current Phase E evidence;
- fingerprints it with SHA-256;
- stores a pending proposal;
- records a generated audit event.

Repeated Generate on identical evidence is idempotent.

If the same topic receives changed confirmed evidence while an old proposal remains pending:

- the old pending proposal becomes superseded;
- the new evidence gets a new pending recommendation.

Applied or rejected history remains immutable decision history.

## Recovery methodology

Phase F uses deterministic evidence-to-method mappings.

Implemented families:

- evidence check;
- concept rebuild;
- procedure rebuild;
- recall rebuild;
- accuracy rebuild;
- speed rebuild;
- reasoning rebuild.

Confirmed mistake categories guide the family:

- concept gap → concept rebuild;
- wrong method / calculation error → procedure rebuild;
- formula recall → recall rebuild;
- careless / misread / guessing → accuracy rebuild;
- time pressure → speed rebuild;
- incomplete reasoning → reasoning rebuild.

With fewer than two confirmed questions, the recommendation is a short diagnostic/evidence check rather than a strong remediation conclusion.

When no more specific error signal exists but confirmed performance is low, concept rebuild is used.

## Planner recommendation preview

Every pending recommendation shows editable planner-task fields:

- title;
- description;
- P0/P1/P2 priority;
- estimated minutes;
- optional due date.

Course/topic linkage remains evidence-grounded.

Suggested priority is transparent and editable.

Phase F does not create a calendar slot or daily agenda item.

## Explicit planner Apply

Only explicit POST Apply may create planner work.

Apply calls the existing `OperationalTaskService`.

Created task characteristics:

- normal `planner_tasks` row;
- status `backlog`;
- course/topic linked when stable IDs exist;
- user-approved task title/description/priority/minutes/due date.

Phase F does not auto-start, auto-schedule or auto-complete the task.

## Apply idempotency

Every recovery planner task receives internal external ID:

`assessment-recovery:<recommendation_id>`.

Migration 0013 enforces uniqueness for that namespace.

`OperationalTaskService.create_assessment_recovery_task()`:

- returns an existing task on retry;
- creates one when absent;
- safely resolves the concurrent-create case.

The recommendation lifecycle is:

`pending → accepted → applied`.

If planner application fails after acceptance:

- recommendation remains `accepted`;
- the UI exposes **Retry planner application**;
- retry reuses the same external ID and cannot duplicate the planner task.

## Reject

Reject is valid only for a pending recommendation.

It:

- records optional rejection reason;
- creates no planner task;
- records a rejected audit event;
- preserves the evidence snapshot and decision.

Unchanged rejected evidence is not immediately regenerated into a new pending recommendation.

## Alex / ChatGPT handoff

Each recommendation includes a reusable recovery prompt for Alex/ChatGPT.

The prompt is generated from:

- course/topic;
- confirmed Phase E evidence;
- deterministic recovery sequence.

It asks for an independent attempt first and finishes with a closed-book exit check.

Phase F does not call an LLM directly.

A recommended retest remains explicit:

Alex/ChatGPT creates it
→ ANVAYA Assessment Package
→ Phase B import/review
→ Phase C test
→ Phase D evaluation
→ Phase E evidence
→ Phase F next recommendation.

This creates a repeatable learning loop without hiding AI actions inside ANVAYA.

## No mastery mutation

Phase F does not write:

- topic status;
- topic progress events;
- learning-memory mastery;
- study-plan items;
- question attempts;
- mistake events.

Applying a recovery task does not mean the topic is automatically weak or mastered.

The focused suite verifies that topic status remains unchanged.

## No silent schedule mutation

GET, Preview, Generate and Reject do not create planner tasks.

Apply creates only a backlog task.

Phase F does not create:

- daily agendas;
- daily agenda items;
- calendar slots.

The user retains the scheduling decision.

## Web surfaces

Implemented:

- GET `/assessments/adaptive`;
- POST `/assessments/adaptive/generate`;
- POST `/assessments/adaptive/<recommendation_id>/apply`;
- POST `/assessments/adaptive/<recommendation_id>/reject`.

Navigation is active from:

- Assessment Studio;
- Weak Topics / Recovery Evidence;
- course Assessment Intelligence.

All mutating commands follow POST/Redirect/GET.

## Audit

Recommendation events record:

- generated;
- superseded;
- accepted;
- applied to planner;
- rejected.

Optimistic recommendation revision prevents stale Apply/Reject decisions.

## Validation

The first clean GitHub validation of the implementation head completed successfully:

- focused Phase F: **10 passed**;
- Assessment Studio Phase A-E + existing assessment regressions: **60 passed**;
- Operational Planner regressions: **13 passed**;
- SQLite schema + recovery regressions: **22 passed**;
- Python compileall: **PASS**;
- dependency consistency via `pip check`: **PASS**;
- broader clone-safe suite: **1504 passed, 2 deselected**;
- migrations `0001..0013`: **PASS**;
- SQLite integrity: **ok**;
- SQLite foreign keys: **no violations**;
- adaptive-loop mastery/planner boundary source guard: **PASS**;
- `git diff --check`: **PASS**.

The two clone-safe deselections remain the established production-database-dependent cases because CI does not contain the gitignored local production database.

## Visual validation

No claim of live localhost browser validation is made from this environment.

Automated Flask coverage verifies the Adaptive Loop page and explicit POST/PRG generation/application flow.

## Final safety model

Phase F establishes the intended authority boundary:

Assessment evidence can recommend.

The recommendation can explain.

Alex can assist.

ANVAYA can persist the decision.

The Operational Planner can receive an approved task.

But only the user chooses whether the recommendation becomes planner work.

Mastery and schedule state are not silently rewritten.
