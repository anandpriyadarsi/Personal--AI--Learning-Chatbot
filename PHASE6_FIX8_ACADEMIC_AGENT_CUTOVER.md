# Phase 6.8 — Academic Agent Cutover

## Starting point

Phase 6.8 starts from:

`054baf4d46f36ba07b51cdc9b8e155900192c844`

on:

`phase6/academic-tutor-intelligence`

This is the completed Phase 6.7 Adaptive Mentor commit.

## Compatibility boundary

The repository already contains the historical Phase-2/V13 module:

`personal_learning_assistant/services/academic_agent_service.py`

Phase 6.8 MUST NOT replace or modify that compatibility service.  The new
execution service therefore lives in the distinct module:

`personal_learning_assistant/services/academic_agent_cutover_service.py`

This preserves `INTENT_LABELS`, the legacy `AcademicAgentService`, and the
existing `personal_academic_agent.py` / Phase-2 test surface.

## Objective

Phase 6.7 answers:

> What should I do next?

Phase 6.8 adds the controlled boundary:

> I explicitly approve this exact current recommendation. Execute only that
> permitted action.

There is **no autonomous loop**.

The agent never chooses and executes its own recommendation.

## Preview -> fingerprint -> explicit execution

Every executable mentor action is converted to an immutable action plan with a
SHA-256 fingerprint over:

- course identity;
- report date;
- target assessment;
- action sequence/type/title;
- topic identity;
- resource/note/question/assessment identity;
- provenance labels;
- priority and reasons;
- execution route.

Preview is read-only.

Execution requires both:

```text
--expected-fingerprint <exact preview fingerprint>
--confirm EXECUTE_ACADEMIC_AGENT_ACTION
```

Immediately before dispatch, the mentor recommendation is rebuilt.

If the recommendation changed, the fingerprint changes and execution is blocked.

This prevents approving one recommendation and accidentally executing a newer
different recommendation.

## Permitted routes

### `continue_lecture`

Routes to the existing Phase 6.4 Lecture Learning service.

- paused lecture -> `resume`
- startable unfinished lecture -> `start`
- already-active lecture -> no duplicate segment is opened

The Phase 6.4 authority/progress/session rules remain authoritative.

### `grounded_tutor`

Creates a Phase 6.1 tutor session:

- mode = `concept`
- source policy = `source_only`
- exact course/topic scope

It does **not** call the tutor provider yet.

The student still asks the question explicitly through Phase 6.2.

### `active_recall`

Routes to the existing Phase 6.5 Practice Quiz service.

This is the only Phase 6.8 route that may call the configured provider because
quiz generation itself is the approved action.

It still uses the Phase 6.5 source-only evidence and grading boundaries.

### `solve_pyq` / `solve_formal_question`

Creates a Phase 6.1 tutor session:

- mode = `exam`
- source policy = `source_only`
- exact course/topic/assessment scope
- exact formal question ID preserved in metadata
- formal source labels preserved in metadata

No PYQ is generated or rewritten.

### `review_note`

Resolves the Phase 6.7 title/topic recommendation to exactly one active
`note_metadata.id`.

If zero or multiple notes match, execution fails closed.

A successful action is a read-only note handoff.

### `study_resource`

Returns a read-only handoff to the exact recommended `resource_id`.

It does not silently mark progress or start a study session.

## Durable execution safety

Phase 6.8 reuses existing Phase 3/5 infrastructure:

- `operation_journal`
- `outbox_events`

No new migration is required.

For mutating routes:

1. SQLite authority is checked.
2. An `academic_agent_action` journal claim is written.
3. The existing Phase 6 service performs its own atomic mutation.
4. Successful result identity is recorded.
5. `academic_agent.action_executed` is emitted.

A completed fingerprint is idempotent: repeating the same explicit execution
returns the already-recorded result instead of executing it again.

If the process crashes after a claim, the remaining `planned` journal entry
blocks blind retries for operator review.

Normal synchronous service failures release the claim because the underlying
Phase 6 mutation contracts are transaction-atomic.

## No silent authority changes

The agent does not directly mutate:

- topic mastery/status/confidence;
- learning memory;
- study plans;
- formal assessment results;
- grades;
- note bodies;
- knowledge chunks;
- retrieval indexes.

It can execute only the already-defined Phase 6.4/6.5/tutor-session operations.

## Operator workflow

Preview an exact mentor action:

```powershell
python .\phase6_academic_agent.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --as-of 2026-09-16 `
  preview `
  --action-sequence 1
```

Copy the returned fingerprint.

Then, only if you approve that exact action:

```powershell
python .\phase6_academic_agent.py `
  --database .\data\learning_assistant.db `
  --authority .\.phase4_authority.json `
  --index-root .\.phase5_retrieval `
  --course-code MA103N `
  --as-of 2026-09-16 `
  execute `
  --action-sequence 1 `
  --expected-fingerprint <FINGERPRINT> `
  --confirm EXECUTE_ACADEMIC_AGENT_ACTION
```

If the current recommendation has changed since preview, execution is blocked
and you must preview again.

## Provider boundary

Preview never calls a provider.

Most execution routes also call no provider.

Only an explicitly approved `active_recall` generation route may call the Phase
6.5 provider.

Grounded Tutor execution only opens a scoped tutor session; asking an actual
question remains a separate explicit Phase 6.2 action.

## No migration

Phase 6.8 introduces no SQLite migration.

It reuses `operation_journal` and `outbox_events` from migration 0001 and the
domain-specific tables/services introduced in later phases.

## Phase 6.9 boundary

Phase 6.9 should build the Tutor Workspace and final Phase 6 reconciliation /
closure gate around these now-complete layers:

- grounded tutor;
- navigation;
- lecture learning;
- active recall;
- exam intelligence;
- adaptive mentor;
- explicit academic-agent execution.
