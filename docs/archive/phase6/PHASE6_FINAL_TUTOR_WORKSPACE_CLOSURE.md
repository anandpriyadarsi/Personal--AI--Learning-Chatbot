# Phase 6.9 — Tutor Workspace + Final Closure

## Starting point

Phase 6.9 starts from:

`840a5ee56eab6f197448b8b37265c7b72997d191`

on:

`phase6/academic-tutor-intelligence`

This is the completed Phase 6.8 Academic Agent Cutover commit.

## Objective

Phase 6.9 is an integration and closure phase.

It does **not** add another intelligence engine.

It provides one read-only Tutor Workspace surface over the Phase 6 stack and a
final reconciliation gate proving that the Academic Tutor architecture is
coherent before Phase 6 is closed.

## Tutor Workspace

The workspace combines:

- Phase 6.3 / 6.7 topic priorities and mentor recommendations;
- tutor sessions;
- lecture-learning study-session segments;
- Phase 6.5 practice sessions/attempt counts;
- formal assessment context through the mentor/exam-intelligence layer;
- recent academic-agent execution counts;
- schema readiness.

The workspace is a read model only.

It does not:

- call an LLM/provider;
- execute a mentor action;
- start/resume a lecture;
- generate a quiz;
- create a tutor session;
- modify mastery, memory, progress, plans or grades.

Example:

```powershell
python .\phase6_tutor_workspace.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --as-of 2026-09-16
```

## Final Phase 6 closure invariants

### Authority

- SQLite remains the locked structured authority.
- legacy structured writes remain blocked.

### Schema

The production database must contain the intact migration prefix:

```text
0001 foundation
0002 academic schema
0003 tutor intelligence
0004 practice recall
```

Phase 6.9 introduces no migration.

If production has not yet received migration 0004, final closure intentionally
blocks. Apply it through the explicit Phase 6.5 schema operator before retrying
closure.

### Tutor evidence

For persisted tutor turns:

- grounded/mixed assistant turns must own exact chunk evidence;
- each evidence `document_id` must match the cited chunk's document;
- user turns must not own assistant evidence links.

### Practice grounding

For persisted Phase 6.5 practice:

- every practice item must have at least one exact source chunk;
- each practice chunk/document pair must match;
- deterministic and advisory attempt semantics remain governed by 0004.

Generated practice remains separate from formal assessment/PYQ tables.

### Lecture learning

A resource may not have multiple simultaneously open `study_sessions`
segments.

This closes the duplicate-timer/duplicate-learning-session boundary from
Phase 6.4.

### Academic Agent audit

For Phase 6.8:

- no `academic_agent_action` journal claim may remain `planned`;
- a completed fingerprint may not appear completed more than once;
- each completed fingerprint must have an
  `academic_agent.action_executed` outbox event;
- execution-event JSON must contain the recorded fingerprint.

No real agent action is executed during closure.

### Retrieval

The current Phase 5.8 index must still be readable.

The closure runs a course-scoped MA103N smoke retrieval and requires at least
one current hit.

It does not rebuild or mutate the current retrieval generation.

## Final closure command

```powershell
python .\phase6_verify_closure.py `
  --database .\data\learning_assistant.db `
  --authority .\.phase4_authority.json `
  --index-root .\.phase5_retrieval `
  --course-code MA103N `
  --as-of 2026-09-16
```

This command is read-only.

## What Phase 6 now contains

```text
6.1 Tutor Domain + Session/Evidence Foundation
6.2 Grounded Academic Tutor Engine
6.3 Knowledge Navigator / What Should I Study?
6.4 Lecture Learning Mode
6.5 Active Recall + Fast Quiz
6.6 PYQ + Exam Intelligence
6.7 Adaptive Mentor
6.8 Academic Agent Cutover
6.9 Tutor Workspace + Final Closure
```

The resulting boundary is:

```text
authoritative academic state
        +
grounded knowledge/retrieval
        +
learning activity
        +
formal exam evidence
        |
        v
read-only intelligence
        |
        v
Tutor Workspace / Adaptive Mentor
        |
        v
explicit fingerprinted user approval
        |
        v
one permitted Academic Agent action
```

## Closure gate

`phase6_final_gate.ps1` verifies:

- focused Phase 6.9 tests;
- real MA103N Tutor Workspace preview;
- real Phase 6 final reconciliation;
- all Phase 6.1-6.8 regressions;
- Phase 5 closure/retrieval regressions;
- Phase 4 authority/post-promotion regressions;
- complete project tests;
- compilation/dependency health;
- SQLite integrity/FKs;
- source/runtime immutability;
- no migration changes.

## After Phase 6

Do not begin the next major phase until this gate is green and the Phase 6.9
closure commit is pushed.

The next phase should build on this closed boundary rather than bypassing the
Tutor Workspace, evidence rules or explicit Academic Agent approval contract.
