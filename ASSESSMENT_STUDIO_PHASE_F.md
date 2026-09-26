# Assessment Studio — Phase F: Adaptive Academic Loop

## Baseline

Phase F starts from verified Assessment Studio Phase E:

`phase7.5.assessment-studio-e/assessment-intelligence @ 3039976fff8d221f6ad35119e9bfbeaa4af833db`

Phase F closes the first Assessment Studio learning loop:

confirmed assessment evidence
→ Assessment Intelligence
→ recovery recommendation
→ human review
→ explicit Apply or Reject
→ existing Operational Planner task backlog.

Phase F does **not** silently change mastery or schedules.

## Repository-grounded planner boundary

The current repository does not expose a modern `ProgressService` / `PlannerService` pair under those names.

The authoritative operational planning boundary is:

- `OperationalTaskService`;
- `SQLitePlannerTaskRepository`;
- `planner_tasks`;
- Operational Planner routes/services.

Phase F therefore does not invent a parallel planner abstraction.

It consumes Phase E confirmed evidence and, only after explicit user approval, hands one recovery task to the existing `OperationalTaskService`.

Legacy `academic_progress.py` remains separate and is not used as a write target.

## Migration 0013

`0013_assessment_adaptive_academic_loop.sql` adds:

- `assessment_recovery_recommendations`;
- `assessment_recovery_recommendation_events`;
- one partial unique index for internal recovery-task external IDs.

The current schema becomes `0001..0013`.

### Recommendation state

A recommendation is one of:

- `pending` — saved proposal awaiting a decision;
- `accepted` — user accepted it; planner application may be in progress/retryable;
- `applied` — an Operational Planner task exists;
- `rejected` — user rejected it;
- `superseded` — newer confirmed evidence replaced an older pending proposal.

Historical applied/rejected recommendations are not overwritten.

## GET / POST boundary

All Phase F GET pages are side-effect free.

A GET may compute live preview recommendations from Phase E, but it does not persist them.

Persistence requires explicit POST:

- Generate selected recommendations;
- Apply recommendation;
- Reject recommendation.

This follows existing ANVAYA PRG conventions.

## Evidence source

Phase F consumes only the Phase E `weak_topics()` read model.

Therefore recommendation generation inherits Phase E's confirmed-only cross-test evidence boundary:

- fully confirmed Phase D sessions;
- confirmed/auto-confirmed response evaluations;
- confirmed mistake classifications.

Provisional grading does not silently generate durable recovery recommendations.

## Evidence snapshots and fingerprints

Each durable recommendation stores an immutable JSON snapshot containing:

- course ID/code/name;
- stable topic ID when available;
- topic label;
- Phase E recovery order;
- confirmed question count;
- confirmed session count;
- confidence-weighted performance;
- full-answer accuracy;
- correct/partial/incorrect/unanswered counts;
- confirmed mistake count/categories;
- time-per-available-mark;
- Phase E recovery signals.

The snapshot is versioned as:

`assessment-intelligence-recovery-v1`.

A SHA-256 fingerprint of the canonical evidence snapshot identifies that exact evidence state.

If Generate is repeated with unchanged evidence:

- no duplicate recommendation is created;
- an existing rejected/applied recommendation is not re-opened.

If evidence changes for the same topic while an old recommendation is still pending:

- the old pending recommendation becomes `superseded`;
- a new pending recommendation is created.

## Deterministic recovery methodology

Phase F does not call an LLM to decide what the student should do.

Recommendation families are deterministic and explainable.

### Limited evidence

If fewer than two confirmed questions exist:

`evidence_check`

Sequence:

1. short closed-book diagnostic;
2. review only uncertain questions;
3. second short check.

The purpose is to collect better evidence before changing study strategy.

### Concept gap

Primary signal: confirmed `concept_gap` mistake or otherwise low confirmed performance without a more specific dominant error.

`concept_rebuild`

Sequence:

1. source/note review;
2. independent explanation attempt;
3. Tutor/Alex help only after that attempt;
4. worked examples;
5. easy independent practice;
6. closed-book retest.

### Wrong method / calculation procedure

Primary signal:

- `wrong_method`;
- `calculation_error`.

`procedure_rebuild`

Sequence:

1. trace one worked solution;
2. guided practice;
3. independent practice;
4. timed familiar problem;
5. fresh retest.

### Formula recall

Primary signal:

`formula_recall`.

`recall_rebuild`

Sequence:

1. formula/condition recall from memory;
2. closed-book recall;
3. application drill;
4. no-notes retest.

### Careless / misread / guessing

Primary signal:

- `careless`;
- `misread`;
- `guessing`.

`accuracy_rebuild`

Sequence:

1. pre-submit checking routine;
2. untimed accuracy set;
3. timed accuracy set;
4. accuracy-focused retest.

### Time pressure

Primary signal:

`time_pressure`.

`speed_rebuild`

Sequence:

1. accurate familiar drill;
2. progressive time limits;
3. short exam simulation;
4. speed + accuracy retest.

### Incomplete reasoning

Primary signal:

`incomplete_reasoning`.

`reasoning_rebuild`

Sequence:

1. inspect model reasoning;
2. reconstruct it closed-book;
3. compare missing logic;
4. solve/write independently;
5. fresh reasoning retest.

## Recommendation priority

Suggested planner priority is descriptive and editable.

Default:

- P0 when at least two confirmed questions exist and weighted performance is below 40%, or confirmed mistake count is at least 3;
- P1 when at least two confirmed questions exist and weighted performance is below 70%, or any confirmed mistake exists;
- otherwise P2.

The user can change priority before Apply.

## Alex / ChatGPT recovery prompt

Each recommendation contains a reusable Alex/ChatGPT prompt grounded in the stored evidence snapshot and deterministic recovery sequence.

ANVAYA does not call an LLM internally in Phase F.

The prompt tells Alex to:

- work on the named course/topic;
- use the confirmed evidence;
- require an independent attempt;
- follow the recovery sequence;
- finish with a closed-book exit check.

A recommended retest is not auto-generated. The user may create it with Alex and import it through the existing ANVAYA Assessment Package workflow.

## Planner application

A pending recommendation must be explicitly accepted before planner application.

The user may edit:

- task title;
- task description;
- P0/P1/P2 priority;
- estimated minutes;
- optional due date.

Course/topic association remains grounded in the recommendation evidence.

Apply creates a normal Operational Planner task in `backlog`.

Phase F does not:

- schedule a calendar slot;
- create a daily agenda item;
- change an existing task;
- automatically start the task.

## Idempotency and interruption recovery

Planner handoff uses internal external ID:

`assessment-recovery:<recommendation_id>`.

Migration 0013 enforces uniqueness for this recovery namespace.

Apply lifecycle:

`pending → accepted → applied`.

The accepted state exists so a failure between decision persistence and planner-task creation can be retried safely.

Retrying Apply:

- reuses an existing recovery planner task if already created;
- never creates duplicate planner tasks;
- resumes an accepted recommendation.

## Rejection

Reject is explicit and only valid for a pending recommendation.

Reject:

- records optional reason;
- creates no planner task;
- preserves recommendation/evidence history.

The same unchanged evidence fingerprint will not immediately regenerate the rejected recommendation.

A genuinely changed evidence snapshot may produce a new recommendation later.

## Optimistic concurrency

Pending recommendation Apply/Reject carries a recommendation revision.

If the recommendation changed after the page was rendered, the command fails with conflict and requires refresh/review.

This prevents stale approval.

## No mastery/progress mutation

Phase F does not write:

- topic status;
- mastery state;
- `topic_progress_events`;
- learning-memory weak/mastered state;
- assessment scores;
- question attempts;
- mistake events.

It does not infer that accepting a recovery task means the topic is weak or later mastered.

Assessment evidence remains evidence.

## No silent planning mutation

Phase F does not create any planner work on:

- GET;
- preview;
- live evidence calculation;
- Generate;
- Reject.

Only explicit Apply may create one planner backlog task.

Generate persists recommendations only.

## Web surfaces

Phase F adds:

- GET `/assessments/adaptive`;
- POST `/assessments/adaptive/generate`;
- POST `/assessments/adaptive/<recommendation_id>/apply`;
- POST `/assessments/adaptive/<recommendation_id>/reject`.

Assessment Studio, Weak Topics and course intelligence expose Adaptive Loop navigation.

## Audit

Recommendation events record:

- generated;
- superseded;
- accepted;
- applied to planner;
- rejected.

The audit does not log unrelated academic content or keystrokes.

## Non-goals

Phase F does not implement:

- automatic mastery changes;
- automatic calendar scheduling;
- automatic daily-agenda insertion;
- autonomous task completion;
- direct LLM calls;
- automatic test generation;
- predictive exam forecasts;
- hidden recommendation scores;
- continuous background recommendation generation.

The user remains the decision-maker at the evidence-to-action boundary.
