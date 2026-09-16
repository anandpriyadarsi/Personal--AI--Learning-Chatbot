# Phase 6.7 — Adaptive Mentor

## Starting point

Phase 6.7 starts from:

`e83692efeb4f79c1f16144ea3a8e91261e63ae7d`

on:

`phase6/academic-tutor-intelligence`

This is the completed Phase 6.6 PYQ + Exam Intelligence commit.

## Objective

Compose the already-built Phase 6 evidence streams into an explainable answer
to:

> What should I do next, and why?

without turning recommendations into authoritative academic state.

Phase 6.7 is deterministic, read-only and advisory.

It does not call an LLM.

## Evidence composition

The mentor reuses:

### Phase 6.3 Knowledge Navigator

- topic status/confidence;
- deadlines;
- unresolved formal mistakes;
- learning-memory presence;
- existing study-plan coverage;
- study time;
- note/resource ordering;
- unfinished lecture/resource progress.

### Phase 6.5 Active Recall

Only persisted deterministic practice outcomes contribute to correctness
evidence.

`free_response` / `advisory_ungraded` attempts are counted as activity but never
treated as correct/incorrect evidence.

If migration 0004 has not yet been applied to a database, the mentor reports
practice history as unavailable instead of failing or guessing.

### Phase 6.6 PYQ + Exam Intelligence

- accepted formal question-topic mappings;
- explicit PYQ/past-paper evidence;
- marks;
- question source provenance;
- unresolved formal mistakes;
- exact selected assessment scope.

Generated Phase 6.5 practice remains separate from formal PYQ history.

## Adaptive behavior

The recommendation chain may include:

- `continue_lecture`
- `review_note`
- `study_resource`
- `grounded_tutor`
- `active_recall`
- `solve_pyq`
- `solve_formal_question`

Examples of deterministic adaptation:

- an explicitly unfinished lecture can be continued before starting a new
  resource;
- low confidence or unresolved formal mistakes can add a grounded-tutor step;
- no deterministic recall evidence can add an active-recall step;
- weak deterministic quiz accuracy increases active-recall urgency;
- strong deterministic quiz accuracy can suppress redundant recall when the
  topic is not a selected assessment target;
- explicit PYQ evidence can add a PYQ-solving step with the exact formal
  question/source IDs preserved.

## Learning-memory boundary

The mentor uses only the fact that active learning-memory entries exist.

It does **not** parse arbitrary memory text and infer a weakness, diagnosis or
mastery claim from it.

The grounded tutor can later use properly scoped knowledge evidence when the
student chooses that action.

## Preparation priority is not prediction

Phase 6.7 may combine the deterministic ordering scores from Knowledge
Navigator and Exam Intelligence.

The resulting priority is a workflow ordering aid.

It does not mean:

- a topic will appear in an exam;
- a student has or has not mastered a topic;
- a predicted score/probability;
- an automatic plan update.

## Read-only operator

```powershell
python .\phase6_adaptive_mentor.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --as-of 2026-09-16 `
  --limit-topics 5 `
  --max-actions 10
```

A selected formal assessment can be supplied:

```powershell
python .\phase6_adaptive_mentor.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --target-assessment-id <assessment-id> `
  --as-of 2026-09-16
```

The CLI opens SQLite with `mode=ro`.

## No writes

Phase 6.7 does not automatically:

- change topic confidence/status;
- write learning memory;
- add/modify study-plan items;
- update resource progress;
- open lecture sessions;
- generate a quiz;
- submit practice attempts;
- modify formal questions/attempts/mistakes;
- create tutor turns;
- call an LLM.

It recommends the next operation; the existing explicit Phase 6.2/6.4/6.5
commands remain responsible for user-selected actions.

## No migration

Phase 6.7 introduces no SQLite migration.

Migration 0004 remains the newest schema version.

## Phase 6.8 boundary

Phase 6.8 — Academic Agent Cutover should add the explicit command/action
dispatcher that can execute a user-approved mentor recommendation.

The important separation is:

```text
Phase 6.7
evidence -> recommendation

Phase 6.8
explicit user approval -> permitted action
```

The agent must not silently convert mentor advice into writes.
